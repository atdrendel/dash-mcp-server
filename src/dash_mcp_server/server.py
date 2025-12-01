from typing import Optional
import httpx
import subprocess
import json
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp import Context
from pydantic import BaseModel, Field

mcp = FastMCP("Dash Documentation API")


async def check_api_health(ctx: Context, port: int) -> bool:
    """Check if the Dash API server is responding at the given port."""
    base_url = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{base_url}/health")
            response.raise_for_status()
        await ctx.debug(f"Successfully connected to Dash API at {base_url}")
        return True
    except Exception as e:
        await ctx.debug(f"Health check failed for {base_url}: {e}")
        return False


async def working_api_base_url(ctx: Context) -> Optional[str]:
    dash_running = await ensure_dash_running(ctx)
    if not dash_running:
        return None
    
    port = await get_dash_api_port(ctx)
    if port is None:
        # Try to automatically enable the Dash API Server
        await ctx.info("The Dash API Server is not enabled. Attempting to enable it automatically...")
        try:
            subprocess.run(
                ["defaults", "write", "com.kapeli.dashdoc", "DHAPIServerEnabled", "YES"],
                check=True,
                timeout=10
            )
            subprocess.run(
                ["defaults", "write", "com.kapeli.dash-setapp", "DHAPIServerEnabled", "YES"],
                check=True,
                timeout=10
            )
            # Wait a moment for Dash to pick up the change
            import time
            time.sleep(2)
            
            # Try to get the port again
            port = await get_dash_api_port(ctx)
            if port is None:
                await ctx.error("Failed to enable Dash API Server automatically. Please enable it manually in Dash Settings > Integration")
                return None
            else:
                await ctx.info("Successfully enabled Dash API Server")
        except Exception as e:
            await ctx.error("Failed to enable Dash API Server automatically. Please enable it manually in Dash Settings > Integration")
            return None
    
    return f"http://127.0.0.1:{port}"


async def get_dash_api_port(ctx: Context) -> Optional[int]:
    """Get the Dash API port from the status.json file and verify the API server is responding."""
    status_file = Path.home() / "Library" / "Application Support" / "Dash" / ".dash_api_server" / "status.json"
    
    try:
        with open(status_file, 'r') as f:
            status_data = json.load(f)
            port = status_data.get('port')
            if port is None:
                return None
                
        # Check if the API server is actually responding
        if await check_api_health(ctx, port):
            return port
        else:
            return None
            
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


def check_dash_running() -> bool:
    """Check if Dash app is running by looking for the process."""
    try:
        # Use pgrep to check for Dash process
        result = subprocess.run(
            ["pgrep", "-f", "Dash"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


async def ensure_dash_running(ctx: Context) -> bool:
    """Ensure Dash is running, launching it if necessary."""
    if not check_dash_running():
        await ctx.info("Dash is not running. Launching Dash...")
        try:
            # Launch Dash using the bundle identifier
            result = subprocess.run(
                ["open", "-g", "-j", "-b", "com.kapeli.dashdoc"],
                timeout=10
            )
            if result.returncode != 0:
                # Try Setapp bundle identifier
                subprocess.run(
                    ["open", "-g", "-j", "-b", "com.kapeli.dash-setapp"],
                    check=True,
                    timeout=10
                )
            # Wait a moment for Dash to start
            import time
            time.sleep(4)
            
            # Check again if Dash is now running
            if not check_dash_running():
                await ctx.error("Failed to launch Dash application")
                return False
            else:
                await ctx.info("Dash launched successfully")
                return True
        except subprocess.CalledProcessError:
            await ctx.error("Failed to launch Dash application")
            return False
        except Exception as e:
            await ctx.error(f"Error launching Dash: {e}")
            return False
    else:
        return True



class DocsetResult(BaseModel):
    """Information about a docset."""
    name: str = Field(description="Display name of the docset")
    identifier: str = Field(description="Unique identifier")
    platform: str = Field(description="Platform/type of the docset")
    full_text_search: str = Field(description="Full-text search status: 'not supported', 'disabled', 'indexing', or 'enabled'")
    notice: Optional[str] = Field(description="Optional notice about the docset status", default=None)


class DocsetResults(BaseModel):
    """Result from listing docsets."""
    docsets: list[DocsetResult] = Field(description="List of installed docsets", default_factory=list)
    error: Optional[str] = Field(description="Error message if there was an issue", default=None)


class SearchResult(BaseModel):
    """A search result from documentation."""
    name: str = Field(description="Name of the documentation entry")
    type: str = Field(description="Type of result (Function, Class, etc.)")
    platform: Optional[str] = Field(description="Platform of the result", default=None)
    load_url: str = Field(description="URL to load the documentation")
    docset: Optional[str] = Field(description="Name of the docset", default=None)
    description: Optional[str] = Field(description="Additional description", default=None)
    language: Optional[str] = Field(description="Programming language (snippet results only)", default=None)
    tags: Optional[str] = Field(description="Tags (snippet results only)", default=None)


class SearchResults(BaseModel):
    """Result from searching documentation."""
    results: list[SearchResult] = Field(description="List of search results", default_factory=list)
    error: Optional[str] = Field(description="Error message if there was an issue", default=None)


class DocumentationContent(BaseModel):
    """Full content from a documentation page."""
    load_url: str = Field(description="The URL that was fetched")
    title: str = Field(description="Page title")
    content: str = Field(description="Full documentation content in Markdown format")
    error: Optional[str] = Field(description="Error message if there was an issue", default=None)


def estimate_tokens(obj) -> int:
    """Estimate token count for a serialized object. Rough approximation: 1 token ≈ 4 characters."""
    if isinstance(obj, str):
        return max(1, len(obj) // 4)
    elif isinstance(obj, (list, tuple)):
        return sum(estimate_tokens(item) for item in obj)
    elif isinstance(obj, dict):
        return sum(estimate_tokens(k) + estimate_tokens(v) for k, v in obj.items())
    elif hasattr(obj, 'model_dump'):  # Pydantic model
        return estimate_tokens(obj.model_dump())
    else:
        return max(1, len(str(obj)) // 4)


@mcp.tool()
async def list_installed_docsets(ctx: Context) -> DocsetResults:
    """List all documentation sets the user has installed in Dash.

    Dash is a macOS application that stores offline documentation for programming languages,
    frameworks, and tools. The user has chosen which documentation sets (docsets) to install,
    so this reflects their development environment and preferences.

    Call this tool FIRST before searching, as you need docset identifiers for search_documentation.

    Each docset includes:
    - name: Human-readable name (e.g., "Python 3", "React")
    - identifier: Use this for search_documentation's docset_identifiers parameter
    - full_text_search: Whether content search is available ("enabled", "disabled", "indexing", or "not supported")

    Returns an empty list if no docsets are installed.
    Results are automatically truncated if they would exceed 25,000 tokens."""
    try:
        base_url = await working_api_base_url(ctx)
        if base_url is None:
            return DocsetResults(error="Failed to connect to Dash API Server. Please ensure Dash is running and the API server is enabled (in Dash Settings > Integration).")
        await ctx.debug("Fetching installed docsets from Dash API")
        
        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"{base_url}/docsets/list")
            response.raise_for_status()
            result = response.json()
        
        docsets = result.get("docsets", [])
        await ctx.info(f"Found {len(docsets)} installed docsets")
        
        # Build result list with token limit checking
        token_limit = 25000
        current_tokens = 100  # Base overhead for response structure
        limited_docsets = []
        
        for docset in docsets:
            docset_info = DocsetResult(
                name=docset["name"],
                identifier=docset["identifier"],
                platform=docset["platform"],
                full_text_search=docset["full_text_search"],
                notice=docset.get("notice")
            )
            
            # Estimate tokens for this docset
            docset_tokens = estimate_tokens(docset_info)
            
            if current_tokens + docset_tokens > token_limit:
                await ctx.warning(f"Token limit reached. Returning {len(limited_docsets)} of {len(docsets)} docsets to stay under 25k token limit.")
                break
                
            limited_docsets.append(docset_info)
            current_tokens += docset_tokens
        
        if len(limited_docsets) < len(docsets):
            await ctx.info(f"Returned {len(limited_docsets)} docsets (truncated from {len(docsets)} due to token limit)")
        
        return DocsetResults(docsets=limited_docsets)
        
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            await ctx.warning("No docsets found. Install some in Settings > Downloads.")
            return DocsetResults(error="No docsets found. Instruct the user to install some docsets in Settings > Downloads.")
        return DocsetResults(error=f"HTTP error: {e}")
    except Exception as e:
        await ctx.error(f"Failed to get installed docsets: {e}")
        return DocsetResults(error=f"Failed to get installed docsets: {e}")


@mcp.tool()
async def search_documentation(
    ctx: Context,
    query: str,
    docset_identifiers: str,
    search_snippets: bool = True,
    max_results: int = 100,
) -> SearchResults:
    """
    Search the user's installed documentation for API references, classes, functions, guides, and more.

    Use this to find authoritative documentation from the user's chosen sources. Results include
    a load_url field - pass this to fetch_documentation_content to retrieve the full page content.

    By default, search matches API/symbol names (e.g., "useState", "DataFrame.merge"). To search
    within page content (finding mentions in descriptions and guides), the docset needs full-text
    search enabled - check the full_text_search field from list_installed_docsets.

    Args:
        query: The search query (API names, function names, concepts, etc.)
        docset_identifiers: Comma-separated docset identifiers from list_installed_docsets (e.g., "python3,react,typescript")
        search_snippets: Include user-saved code snippets from Dash in results (default: True)
        max_results: Maximum results to return, 1-1000 (default: 100)

    Typical workflow:
        1. list_installed_docsets -> get identifiers
        2. search_documentation -> find relevant entries
        3. fetch_documentation_content -> get full details for specific entries

    Results are automatically truncated if they would exceed 25,000 tokens.
    """
    if not query.strip():
        await ctx.error("Query cannot be empty")
        return SearchResults(error="Query cannot be empty")
    
    if not docset_identifiers.strip():
        await ctx.error("docset_identifiers cannot be empty. Get the docset identifiers using list_installed_docsets")
        return SearchResults(error="docset_identifiers cannot be empty. Get the docset identifiers using list_installed_docsets")
    
    if max_results < 1 or max_results > 1000:
        await ctx.error("max_results must be between 1 and 1000")
        return SearchResults(error="max_results must be between 1 and 1000")
    
    try:
        base_url = await working_api_base_url(ctx)
        if base_url is None:
            return SearchResults(error="Failed to connect to Dash API Server. Please ensure Dash is running and the API server is enabled (in Dash Settings > Integration).")
        
        params = {
            "query": query,
            "docset_identifiers": docset_identifiers,
            "search_snippets": search_snippets,
            "max_results": max_results,
        }
        
        await ctx.debug(f"Searching Dash API with query: '{query}'")
        
        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"{base_url}/search", params=params)
            response.raise_for_status()
            result = response.json()
        
        # Check for warning message in response
        warning_message = None
        if "message" in result:
            warning_message = result["message"]
            await ctx.warning(warning_message)
        
        results = result.get("results", [])
        await ctx.info(f"Found {len(results)} results")
        
        # Build result list with token limit checking
        token_limit = 25000
        current_tokens = 100  # Base overhead for response structure
        limited_results = []
        
        for item in results:
            search_result = SearchResult(
                name=item["name"],
                type=item["type"],
                platform=item.get("platform"),
                load_url=item["load_url"],
                docset=item.get("docset"),
                description=item.get("description"),
                language=item.get("language"),
                tags=item.get("tags")
            )
            
            # Estimate tokens for this result
            result_tokens = estimate_tokens(search_result)
            
            if current_tokens + result_tokens > token_limit:
                await ctx.warning(f"Token limit reached. Returning {len(limited_results)} of {len(results)} results to stay under 25k token limit.")
                break
                
            limited_results.append(search_result)
            current_tokens += result_tokens
        
        if len(limited_results) < len(results):
            await ctx.info(f"Returned {len(limited_results)} results (truncated from {len(results)} due to token limit)")
        
        return SearchResults(results=limited_results, error=warning_message)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400:
            error_text = e.response.text
            if "Docset with identifier" in error_text and "not found" in error_text:
                await ctx.error("Invalid docset identifier. Run list_installed_docsets to see available docsets.")
                return SearchResults(error="Invalid docset identifier. Run list_installed_docsets to see available docsets, then use the exact identifier from that list.")
            elif "No docsets found" in error_text:
                await ctx.error("No valid docsets found for search.")
                return SearchResults(error="No valid docsets found for search. Either provide valid docset identifiers from list_installed_docsets, or set search_snippets=true to search snippets only.")
            else:
                await ctx.error(f"Bad request: {error_text}")
                return SearchResults(error=f"Bad request: {error_text}. Please ensure Dash is running and the API server is enabled (in Dash Settings > Integration).")
        elif e.response.status_code == 403:
            error_text = e.response.text
            if "API access blocked due to Dash trial expiration" in error_text:
                await ctx.error("Dash trial expired. Purchase Dash to continue using the API.")
                return SearchResults(error="Your Dash trial has expired. Purchase Dash at https://kapeli.com/dash to continue using the API. During trial expiration, API access is blocked.")
            else:
                await ctx.error(f"Forbidden: {error_text}")
                return SearchResults(error=f"Forbidden: {error_text}. Please ensure Dash is running and the API server is enabled (in Dash Settings > Integration).")
        await ctx.error(f"HTTP error: {e}")
        return SearchResults(error=f"HTTP error: {e}. Please ensure Dash is running and the API server is enabled (in Dash Settings > Integration).")
    except Exception as e:
        await ctx.error(f"Search failed: {e}")
        return SearchResults(error=f"Search failed: {e}. Please ensure Dash is running and the API server is enabled (in Dash Settings > Integration).")


@mcp.tool()
async def enable_docset_fts(ctx: Context, identifier: str) -> bool:
    """
    Enable full-text search for a specific docset.

    By default, search_documentation only matches API/symbol names (like "map", "filter", "useState").
    Enabling full-text search (FTS) allows searching within the actual documentation content,
    so you can find pages that mention concepts, patterns, or terms in their descriptions.

    Example: Without FTS, searching "authentication" might return nothing. With FTS enabled,
    it could find guides and API docs that discuss authentication in their content.

    Check list_installed_docsets first - the full_text_search field shows current status:
    - "enabled": Already active, no action needed
    - "disabled": Can be enabled with this tool
    - "indexing": Currently building the index, wait and retry
    - "not supported": This docset doesn't support FTS

    Args:
        identifier: The docset identifier from list_installed_docsets

    Returns:
        True if FTS was successfully enabled, False otherwise
    """
    if not identifier.strip():
        await ctx.error("Docset identifier cannot be empty")
        return False

    try:
        base_url = await working_api_base_url(ctx)
        if base_url is None:
            return False
        
        await ctx.debug(f"Enabling FTS for docset: {identifier}")
        
        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"{base_url}/docsets/enable_fts", params={"identifier": identifier})
            response.raise_for_status()
            result = response.json()
        
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400:
            await ctx.error(f"Bad request: {e.response.text}")
            return False
        elif e.response.status_code == 404:
            await ctx.error(f"Docset not found: {identifier}")
            return False
        await ctx.error(f"HTTP error: {e}")
        return False
    except Exception as e:
        await ctx.error(f"Failed to enable FTS: {e}")
        return False
    return True


@mcp.tool()
async def fetch_documentation_content(ctx: Context, load_url: str) -> DocumentationContent:
    """
    Fetch the full documentation content for a specific entry.

    This tool retrieves the complete documentation page and converts it to Markdown format,
    making it easy for AI models to read and understand. Unlike search results which only
    provide metadata, this returns the actual documentation text including descriptions,
    parameters, code examples, and detailed explanations.

    Args:
        load_url: The load_url from a search result (obtained via search_documentation)

    Returns:
        DocumentationContent with the full page converted to Markdown.
        No content limits - returns the complete documentation.

    Example workflow:
        1. Use search_documentation to find relevant entries
        2. Use fetch_documentation_content with a load_url to get full details
    """
    if not load_url.strip():
        await ctx.error("load_url cannot be empty")
        return DocumentationContent(
            load_url=load_url,
            title="Error",
            content="",
            error="load_url cannot be empty"
        )

    try:
        await ctx.debug(f"Fetching documentation content from: {load_url}")

        # Fetch the HTML content
        with httpx.Client(timeout=30.0) as client:
            response = client.get(load_url)
            response.raise_for_status()
            html_content = response.text

        await ctx.debug(f"Successfully fetched {len(html_content)} bytes of HTML")

        # Convert HTML to Markdown
        from markdownify import markdownify as md

        # Import BeautifulSoup to clean the HTML first
        from bs4 import BeautifulSoup

        # Parse HTML
        soup = BeautifulSoup(html_content, 'html.parser')

        # Extract title
        title_elem = soup.find('title')
        title = title_elem.get_text(strip=True) if title_elem else "Documentation"

        # Remove unwanted elements
        for element in soup.find_all(['script', 'style', 'nav', 'header']):
            element.decompose()

        # Convert to markdown
        # Use strip=False to preserve formatting, heading_style="ATX" for # headings
        markdown_content = md(str(soup), heading_style="ATX", bullets="-")

        # Clean up excessive whitespace while preserving intentional spacing
        import re
        # Replace 3+ newlines with just 2 (preserve paragraph breaks)
        markdown_content = re.sub(r'\n{3,}', '\n\n', markdown_content)
        # Clean up trailing whitespace on lines
        markdown_content = re.sub(r'[ \t]+$', '', markdown_content, flags=re.MULTILINE)

        markdown_content = markdown_content.strip()

        await ctx.info(f"Successfully converted to Markdown: {len(markdown_content)} characters")

        return DocumentationContent(
            load_url=load_url,
            title=title,
            content=markdown_content
        )

    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP error {e.response.status_code}: {e.response.reason_phrase}"
        await ctx.error(error_msg)
        return DocumentationContent(
            load_url=load_url,
            title="Error",
            content="",
            error=error_msg
        )
    except Exception as e:
        error_msg = f"Failed to fetch content: {str(e)}"
        await ctx.error(error_msg)
        return DocumentationContent(
            load_url=load_url,
            title="Error",
            content="",
            error=error_msg
        )


def main():
    mcp.run()


if __name__ == "__main__":
    main()
