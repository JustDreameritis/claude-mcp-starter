# Case Study: Claude MCP Server Starter Template

## Overview

Production-ready Model Context Protocol (MCP) server template for extending Claude with custom tools. This starter kit provides a modular architecture for building MCP servers that give Claude access to file systems, web content, and data transformation capabilities.

## Technical Implementation

### Architecture

```
claude-mcp-starter/
├── server.py              # MCP server entry point (stdio transport)
├── tools/
│   ├── __init__.py
│   ├── file_search.py     # Glob search + file preview tools
│   ├── web_fetch.py       # URL fetching with HTML-to-markdown
│   └── data_transform.py  # JSON/CSV transformation utilities
└── requirements.txt
```

### Core Components

**MCP Server (server.py)**
- Async stdio transport for JSON-RPC communication
- Dynamic tool registration from modular tool files
- Global error handling with Claude-readable error responses
- Configurable logging to stderr (preserves stdout for protocol)

**File Search Tools (file_search.py)**
- `search_files`: Glob-based file discovery with metadata (size, modified date)
- `read_file_summary`: Encoding-aware file preview with chardet detection
- Security: Configurable allowed directories (`ALLOWED_DIRECTORIES` env var)
- Size limits: Configurable max file size (default 10MB)

**Web Fetch Tools (web_fetch.py)**
- URL content fetching with automatic HTML-to-markdown conversion
- Timeout handling and retry logic
- Response caching for repeated requests

**Data Transform Tools (data_transform.py)**
- JSON schema validation and transformation
- CSV parsing with column mapping
- Format conversion utilities

### Security Features

```python
_ALLOWED_DIRS: list[str] = [
    d.strip()
    for d in os.getenv("ALLOWED_DIRECTORIES", ",".join(_DEFAULT_ALLOWED)).split(",")
    if d.strip()
]

def _is_path_allowed(path: str) -> bool:
    resolved = Path(path).resolve()
    return any(
        str(resolved).startswith(str(Path(allowed).resolve()))
        for allowed in _ALLOWED_DIRS
    )
```

All file operations are sandboxed to explicitly allowed directories, preventing path traversal attacks.

## Integration

### Claude Code Configuration

```json
{
  "mcpServers": {
    "custom-tools": {
      "command": "python",
      "args": ["/path/to/claude-mcp-starter/server.py"],
      "env": {
        "ALLOWED_DIRECTORIES": "/home,/tmp,/mnt",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

### Claude Desktop Configuration

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "custom-tools": {
      "command": "python",
      "args": ["C:\\path\\to\\server.py"]
    }
  }
}
```

## Key Features

| Feature | Implementation |
|---------|----------------|
| Tool Registration | Dynamic via Python modules |
| Transport | stdio (JSON-RPC) |
| Error Handling | Claude-readable error responses |
| Security | Directory sandboxing, size limits |
| Encoding | Auto-detection via chardet |
| Logging | Configurable, stderr-only |

## Use Cases

1. **Local file search** - Let Claude search project directories
2. **Web research** - Fetch and parse web pages as markdown
3. **Data pipelines** - Transform JSON/CSV before processing
4. **Custom integrations** - Extend with your own tool modules

## Technical Stats

- **Lines of Code**: ~950
- **Python Version**: 3.10+
- **Dependencies**: mcp, chardet, httpx
- **Protocol**: MCP 1.0 (stdio transport)

## Extension Points

Adding new tools requires two steps:

1. Create tool file in `tools/` with `TOOLS` list and `HANDLERS` dict
2. Import and register in `server.py`

```python
# tools/my_tool.py
MY_TOOLS: list[Tool] = [
    Tool(name="my_tool", description="...", inputSchema={...})
]

async def _my_tool_handler(args: dict) -> list[TextContent]:
    return [TextContent(type="text", text="result")]

MY_HANDLERS = {"my_tool": _my_tool_handler}
```

## Deployment

### Local Development
```bash
pip install -r requirements.txt
python server.py  # Runs stdio server
```

### Production
- Run as subprocess from Claude Code/Desktop
- Configure environment variables for security
- Monitor stderr for operational logging

---

**Author**: JustDreameritis
**Repository**: [github.com/JustDreameritis/claude-mcp-starter](https://github.com/JustDreameritis/claude-mcp-starter)
