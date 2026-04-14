"""
Claude MCP Server — Starter Template
=====================================
Main entry point for the MCP server. Registers all tool modules and handles
the JSON-RPC protocol via stdio transport.

Usage:
    python server.py

Configure in Claude Code or Claude Desktop — see README.md.
"""

import asyncio
import logging
import os
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Import tool modules
from tools.file_search import FILE_SEARCH_TOOLS, FILE_SEARCH_HANDLERS
from tools.web_fetch import WEB_FETCH_TOOLS, WEB_FETCH_HANDLERS
from tools.data_transform import DATA_TRANSFORM_TOOLS, DATA_TRANSFORM_HANDLERS

# Configure logging — goes to stderr so it doesn't pollute the JSON-RPC stdout stream
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# Create the MCP server instance
app = Server("claude-mcp-starter")

# Aggregate all tools and handlers from every module
ALL_TOOLS: list[Tool] = []
TOOL_HANDLERS: dict = {}

ALL_TOOLS.extend(FILE_SEARCH_TOOLS)
ALL_TOOLS.extend(WEB_FETCH_TOOLS)
ALL_TOOLS.extend(DATA_TRANSFORM_TOOLS)

TOOL_HANDLERS.update(FILE_SEARCH_HANDLERS)
TOOL_HANDLERS.update(WEB_FETCH_HANDLERS)
TOOL_HANDLERS.update(DATA_TRANSFORM_HANDLERS)

logger.info("Registered %d tools: %s", len(ALL_TOOLS), [t.name for t in ALL_TOOLS])


@app.list_tools()
async def list_tools() -> list[Tool]:
    """Return all available tools to the MCP client."""
    return ALL_TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Dispatch a tool call to the appropriate handler."""
    logger.info("Tool called: %s | args: %s", name, arguments)

    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        raise ValueError(
            f"Unknown tool '{name}'. Available tools: {list(TOOL_HANDLERS.keys())}"
        )

    try:
        result = await handler(arguments)
        logger.info("Tool '%s' completed successfully", name)
        return result
    except Exception as exc:
        logger.error("Tool '%s' raised an error: %s", name, exc, exc_info=True)
        # Return the error as a text response so Claude can reason about it
        return [TextContent(type="text", text=f"Error in tool '{name}': {exc}")]


async def main() -> None:
    """Run the MCP server over stdio."""
    logger.info("Starting claude-mcp-starter server (PID %d)", os.getpid())
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )
    logger.info("Server shut down cleanly")


if __name__ == "__main__":
    asyncio.run(main())
