# Adding Dash MCP Server to Claude Code and Codex CLI

This guide provides exact, up-to-date steps for configuring the Dash MCP Server with Claude Code CLI and Codex CLI.

**Repository:** https://github.com/atdrendel/dash-mcp-server

---

## **Claude Code CLI**

### Quick Method (Recommended)

```bash
claude mcp add --transport stdio dash-api -- uvx --from "git+https://github.com/atdrendel/dash-mcp-server.git" "dash-mcp-server"
```

### With Scope Options

**Local scope** (default - only in current project):
```bash
claude mcp add --transport stdio dash-api -- uvx --from "git+https://github.com/atdrendel/dash-mcp-server.git" "dash-mcp-server"
```

**User scope** (available across all projects):
```bash
claude mcp add --transport stdio dash-api --scope user -- uvx --from "git+https://github.com/atdrendel/dash-mcp-server.git" "dash-mcp-server"
```

**Project scope** (shared with team via `.mcp.json`):
```bash
claude mcp add --transport stdio dash-api --scope project -- uvx --from "git+https://github.com/atdrendel/dash-mcp-server.git" "dash-mcp-server"
```

### Verification

```bash
claude mcp list
```

Or inside Claude Code, type:
```bash
/mcp
```

### Alternative: Direct Config File Edit

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "dash-api": {
      "command": "/bin/sh",
      "args": [
        "-l",
        "-c",
        "uvx --from git+https://github.com/atdrendel/dash-mcp-server.git dash-mcp-server"
      ]
    }
  }
}
```

**Note:** We use a login shell (`-l`) to ensure `uvx` is found in your PATH, since Claude Desktop runs with a limited PATH that may not include `~/.local/bin` where `uv` installs executables.

Then restart Claude Code.

---

## **Codex CLI**

### Method 1: Using CLI Command

```bash
codex mcp add dash-api -- uvx --from "git+https://github.com/atdrendel/dash-mcp-server.git" "dash-mcp-server"
```

### Method 2: Edit Config File Directly (Recommended)

Edit `~/.codex/config.toml`:

```toml
[mcp_servers.dash-api]
command = "uvx"
args = ["--from", "git+https://github.com/atdrendel/dash-mcp-server.git", "dash-mcp-server"]
```

**Important:**
- Use `mcp_servers` (with underscore), NOT `mcp-servers` or `mcpservers`
- Using the wrong name will cause Codex to silently ignore the configuration

### With Environment Variables (if needed)

```toml
[mcp_servers.dash-api]
command = "uvx"
args = ["--from", "git+https://github.com/atdrendel/dash-mcp-server.git", "dash-mcp-server"]
env = { CUSTOM_VAR = "value" }
```

### From IDE Extension

1. Click the gear icon in top right corner
2. Click **Codex Settings > Open config.toml**
3. Add the `[mcp_servers.dash-api]` section shown above
4. Save the file

### Verification

Restart Codex and check that the server is loaded. The MCP server should be available in your next session.

---

## **Testing Locally from Working Directory**

If you're developing or testing changes to the MCP server locally, you can point to your local working directory instead of GitHub:

### Claude Code CLI

```bash
# From this project directory
claude mcp add --transport stdio dash-api -- uv --directory /Users/atdrendel/atdrendel/dash-mcp-server run dash-mcp-server
```

Or edit the config file directly:

```json
{
  "mcpServers": {
    "dash-api": {
      "command": "uv",
      "args": [
        "--directory",
        "/Users/atdrendel/atdrendel/dash-mcp-server",
        "run",
        "dash-mcp-server"
      ]
    }
  }
}
```

### Codex CLI

Edit `~/.codex/config.toml`:

```toml
[mcp_servers.dash-api]
command = "uv"
args = ["--directory", "/Users/atdrendel/atdrendel/dash-mcp-server", "run", "dash-mcp-server"]
```

### Manual Testing Without an LLM CLI

**Option 1: MCP Inspector (Recommended)**

```bash
npx @modelcontextprotocol/inspector uv --directory /Users/atdrendel/atdrendel/dash-mcp-server run dash-mcp-server
```

This launches a web UI (usually at http://localhost:5173) where you can:
- Call tools interactively
- See JSON responses
- Inspect the full MCP communication

**Option 2: Quick Python Function Test**

```bash
cd /Users/atdrendel/atdrendel/dash-mcp-server
source .venv/bin/activate

python3 << 'EOF'
import asyncio
import sys
sys.path.insert(0, 'src')

from dash_mcp_server.server import search_documentation, fetch_documentation_content

class MockContext:
    async def debug(self, msg): print(f"[DEBUG] {msg}")
    async def info(self, msg): print(f"[INFO] {msg}")
    async def warning(self, msg): print(f"[WARN] {msg}")
    async def error(self, msg): print(f"[ERROR] {msg}")

async def test():
    ctx = MockContext()

    # Test search
    print("=== Testing search ===")
    results = await search_documentation(
        ctx,
        query="URLSessionDownloadTask",
        docset_identifiers="dainoewq-swift,dainoewq-objc"
    )

    print(f"Found {len(results.results)} results")
    if results.results:
        first = results.results[0]
        print(f"First result: {first.name} ({first.type})")
        print(f"Load URL: {first.load_url}\n")

        # Test fetch content
        print("=== Testing fetch content ===")
        content = await fetch_documentation_content(ctx, first.load_url)
        print(f"Title: {content.title}")
        print(f"Content length: {len(content.content)} chars")
        print(f"First 500 chars:\n{content.content[:500]}")

asyncio.run(test())
EOF
```

---

## **Key Differences**

| Feature | Claude Code | Codex |
|---------|-------------|-------|
| **Config file** | `~/Library/Application Support/Claude/claude_desktop_config.json` | `~/.codex/config.toml` |
| **Quick add** | `claude mcp add` | `codex mcp add` |
| **Scopes** | local, project, user | N/A (all user-level) |
| **Transport types** | stdio, http, sse | stdio only |
| **Shared config** | No (separate for Desktop/Code) | Yes (CLI + IDE extension) |

---

## **Testing Your Setup**

After installation, you can test the new `fetch_documentation_content` tool:

1. **Search for something:**
   ```
   Search for URLSessionDownloadTask in Dash
   ```

2. **Fetch full documentation:**
   ```
   Get the full documentation for URLSessionDownloadTask
   ```

The AI should use `search_documentation` to find it, then `fetch_documentation_content` to retrieve the complete Markdown content!

---

## **Available Tools**

The Dash MCP Server provides the following tools:

### 1. `list_installed_docsets`
Lists all documentation sets installed in Dash with their identifiers and metadata.

### 2. `search_documentation`
Searches across specified docsets for documentation entries. Returns metadata including:
- Name and type (Class, Function, Method, etc.)
- Platform and docset information
- `load_url` for fetching full content

### 3. `fetch_documentation_content` (New!)
Fetches the complete documentation page and converts it to Markdown format. This provides:
- Full descriptions and overviews
- Parameter details
- Code examples
- Related topics
- Complete API reference

**No content limits** - returns the full documentation for the AI to read and understand.

### 4. `enable_docset_fts`
Enables full-text search indexing for a specific docset to improve search results.

---

## **Troubleshooting**

### `spawn uvx ENOENT` Error in Claude Desktop App

If you see `spawn uvx ENOENT` in the Claude Desktop logs, it means `uvx` is not in Claude Desktop's PATH.

**Solution:** Use a login shell wrapper in your config:

```json
{
  "mcpServers": {
    "dash-api": {
      "command": "/bin/sh",
      "args": [
        "-l",
        "-c",
        "uvx --from git+https://github.com/atdrendel/dash-mcp-server.git dash-mcp-server"
      ]
    }
  }
}
```

The `-l` flag runs a login shell, which sources your shell profile (`~/.zprofile`, `~/.bash_profile`, etc.) and ensures your full PATH is available.

**Why this happens:** Claude Desktop runs with a limited PATH (`/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin`) that doesn't include `~/.local/bin`, where `uv` installs executables by default.

### Dash Not Found
- Ensure Dash 8+ is installed from https://kapeli.com/dash
- The MCP server will attempt to launch Dash automatically if not running

### API Server Not Enabled
- The server will attempt to enable the Dash API server automatically
- Manual enable: Dash Settings > Integration > Enable API Server
- Or run: `defaults write com.kapeli.dashdoc DHAPIServerEnabled YES`

### Connection Issues
Use the verification commands above to check server status. For Claude Code, `/mcp` will show connection status for each configured server.
