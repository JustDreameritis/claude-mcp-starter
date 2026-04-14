# Claude MCP Server — Starter Template

A clean, production-quality MCP (Model Context Protocol) server template for **Claude Code** and **Claude Desktop**. Includes 3 ready-to-use tool modules and a simple pattern for adding your own in minutes.

> MCP is the skill that lets you turn Claude into a custom AI agent for any system. This is the template that shows you how.

---

## What is MCP?

MCP (Model Context Protocol) lets Claude call tools you define on your own machine. When Claude needs to search files, hit an API, or transform data — it sends a JSON-RPC request to your local server, your code runs, and Claude gets the result. **Your data never leaves your machine.**

```
Claude Code / Claude Desktop
          │
          │  JSON-RPC over stdio
          ▼
   ┌─────────────────┐
   │   server.py     │   ← MCP server (this repo)
   │   (MCP host)    │
   └────────┬────────┘
            │
     ┌──────┼──────┐
     ▼      ▼      ▼
   File    Web    Data
  Search  Fetch  Transform
```

The protocol is open, vendor-neutral, and supported natively in Claude Code CLI and Claude Desktop. Once you have a working MCP server, every tool you add is instantly available to Claude — no API wrappers, no cloud functions, no rate limits beyond your own.

---

## Included Tools

| Tool | Module | What it does |
|------|--------|-------------|
| `search_files` | file_search | Glob-search any directory; returns paths, sizes, timestamps |
| `read_file_summary` | file_search | Preview first N lines of a file + metadata and encoding |
| `fetch_url` | web_fetch | HTTP GET or POST — returns status code and response body |
| `extract_links` | web_fetch | Fetch a page, extract all anchor links as a list |
| `json_to_csv` | data_transform | Convert a JSON array of objects to a CSV file |
| `csv_stats` | data_transform | Analyze CSV columns: types, unique values, numeric ranges |

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/JustDreameritis/claude-mcp-starter.git
cd claude-mcp-starter
pip install -r requirements.txt
```

Python 3.10+ required.

### 2. Configure for Claude Code

Add to your project's `.claude/settings.json` (or global `~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "starter-tools": {
      "command": "python",
      "args": ["/full/path/to/claude-mcp-starter/server.py"]
    }
  }
}
```

See `.claude/settings.json.example` in this repo for the full schema.

### 3. Configure for Claude Desktop

Add to `claude_desktop_config.json` (location varies by OS):

```json
{
  "mcpServers": {
    "starter-tools": {
      "command": "python",
      "args": ["/full/path/to/claude-mcp-starter/server.py"]
    }
  }
}
```

See `claude_desktop_config.json.example` for the full schema.

### 4. Start a conversation

Restart Claude Code (or Claude Desktop). The tools will appear automatically. Try:

- *"Search for all Python files under /home/me/project"*
- *"Fetch https://news.ycombinator.com and extract all links"*
- *"Convert this JSON array to a CSV at /tmp/output.csv"*

---

## Environment Variables

Copy `.env.example` to `.env` and adjust as needed. The server reads these at startup.

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `MAX_FILE_SIZE_MB` | `10` | Max file size for read/analyze tools |
| `MAX_FETCH_SIZE_KB` | `500` | Max response body size for `fetch_url` |
| `ALLOWED_DIRECTORIES` | `/home,/tmp,/mnt` | Comma-separated root paths file tools may access |

All file tool calls are validated against `ALLOWED_DIRECTORIES`. Attempts to read outside these paths return a permission error — no silent failures.

---

## Project Structure

```
claude-mcp-starter/
├── server.py                       # MCP server entry point
├── tools/
│   ├── __init__.py
│   ├── file_search.py              # search_files, read_file_summary
│   ├── web_fetch.py                # fetch_url, extract_links
│   └── data_transform.py          # json_to_csv, csv_stats
├── docs/
│   └── SOW-template.md            # Upwork statement-of-work template
├── .claude/
│   └── settings.json.example      # Claude Code configuration template
├── claude_desktop_config.json.example
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## Adding Your Own Tools

Each tool module follows the same three-part pattern. Creating a new tool takes about 10 minutes.

### Step 1 — Create `tools/my_tool.py`

```python
from mcp.types import Tool, TextContent

MY_TOOLS = [
    Tool(
        name="my_tool_name",
        description="One clear sentence describing what this tool does.",
        inputSchema={
            "type": "object",
            "properties": {
                "param1": {
                    "type": "string",
                    "description": "What this parameter is for.",
                },
                "param2": {
                    "type": "integer",
                    "description": "Optional count. Default: 10.",
                    "default": 10,
                },
            },
            "required": ["param1"],
        },
    ),
]


async def _my_tool_handler(arguments: dict) -> list[TextContent]:
    param1 = arguments.get("param1", "")
    param2 = int(arguments.get("param2", 10))

    if not param1:
        raise ValueError("'param1' is required.")

    # Your logic here
    result = f"Processed '{param1}' with count={param2}."
    return [TextContent(type="text", text=result)]


MY_HANDLERS = {
    "my_tool_name": _my_tool_handler,
}
```

### Step 2 — Register in `server.py`

```python
from tools.my_tool import MY_TOOLS, MY_HANDLERS

ALL_TOOLS.extend(MY_TOOLS)
TOOL_HANDLERS.update(MY_HANDLERS)
```

### Step 3 — Restart Claude Code

That's it. Your tool is live.

---

## Architecture Notes

### Why stdio transport?

MCP servers communicate with Claude via stdin/stdout using JSON-RPC 2.0. Claude Code spawns the server as a subprocess and manages the lifecycle. This means:

- No network port to open or firewall to configure
- Server starts and stops with Claude
- Logs go to stderr (visible in Claude Code's MCP debug output)
- Multiple MCP servers can run simultaneously without conflicts

### Handler dispatch pattern

`server.py` uses a central dispatch table rather than decorating individual handlers per-tool. This keeps modules independent — each exports a plain dict — and makes it trivial to register, inspect, or disable tools at startup without touching tool code.

### Error handling

All tool errors are caught in `server.py`'s `call_tool` dispatcher and returned as `TextContent` responses. This means Claude always gets a useful error message instead of a protocol-level failure, and can reason about what went wrong and try an alternative approach.

---

## Running the Server Directly (for debugging)

```bash
python server.py
```

The server will wait for JSON-RPC input on stdin. You can test with raw JSON:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | python server.py
```

Or enable debug logging:

```bash
LOG_LEVEL=DEBUG python server.py
```

---

## Tech Stack

- **Python 3.10+**
- **[mcp](https://github.com/anthropics/python-sdk)** — Anthropic's official MCP SDK
- **[httpx](https://www.python-httpx.org/)** — Async HTTP client for web fetch tools
- **[chardet](https://github.com/chardet/chardet)** — Encoding detection for file tools
- Standard library only for everything else (csv, json, glob, pathlib)

---

## Security Considerations

- File tools validate all paths against `ALLOWED_DIRECTORIES` before any I/O
- `fetch_url` enforces a response size cap (`MAX_FETCH_SIZE_KB`) to prevent memory exhaustion
- File read tools enforce a file size cap (`MAX_FILE_SIZE_MB`)
- HTTP requests use a 15-second timeout
- No shell execution, no subprocess spawning, no eval

For production team deployments, consider adding per-tool authentication and audit logging.

---

## Freelance / Upwork

Want to offer this as a service? See `docs/SOW-template.md` for a ready-to-use Statement of Work covering discovery, development, testing, and documentation phases — with tiered pricing from $150 to $800 depending on complexity.

MCP development is an emerging skill with very few practitioners and significant demand as teams start integrating Claude into their internal tooling.

---

## License

MIT — use it, fork it, sell services with it.

---

*Built by [JustDreameritis](https://github.com/JustDreameritis)*
