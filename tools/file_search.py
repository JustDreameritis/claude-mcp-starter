"""
File Search Tools
=================
Provides two MCP tools:

  search_files      — Glob-based file search with metadata
  read_file_summary — Preview file contents with line count and encoding info
"""

from __future__ import annotations

import glob
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import chardet
from mcp.types import TextContent, Tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Security: only allow access inside these root directories.
# Override with the ALLOWED_DIRECTORIES env var (comma-separated paths).
# ---------------------------------------------------------------------------
_DEFAULT_ALLOWED = ["/home", "/tmp", "/mnt"]
_ALLOWED_DIRS: list[str] = [
    d.strip()
    for d in os.getenv("ALLOWED_DIRECTORIES", ",".join(_DEFAULT_ALLOWED)).split(",")
    if d.strip()
]

MAX_FILE_SIZE_MB: float = float(os.getenv("MAX_FILE_SIZE_MB", "10"))


def _is_path_allowed(path: str) -> bool:
    """Return True if *path* is inside one of the allowed directories."""
    resolved = Path(path).resolve()
    return any(
        str(resolved).startswith(str(Path(allowed).resolve()))
        for allowed in _ALLOWED_DIRS
    )


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

FILE_SEARCH_TOOLS: list[Tool] = [
    Tool(
        name="search_files",
        description=(
            "Search for files matching a glob pattern inside a directory. "
            "Returns matching file paths with sizes and last-modified timestamps."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Root directory to search in (absolute path).",
                },
                "pattern": {
                    "type": "string",
                    "description": (
                        "Glob pattern to match file names, e.g. '*.py', '**/*.json'. "
                        "Supports standard glob syntax."
                    ),
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Whether to search sub-directories recursively. Default: true.",
                    "default": True,
                },
            },
            "required": ["directory", "pattern"],
        },
    ),
    Tool(
        name="read_file_summary",
        description=(
            "Read a text file and return a preview of the first N lines, "
            "along with metadata: total line count, file size, and detected encoding."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to read.",
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Maximum number of lines to include in the preview. Default: 50.",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 500,
                },
            },
            "required": ["file_path"],
        },
    ),
]


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def _search_files(arguments: dict[str, Any]) -> list[TextContent]:
    """
    Glob-search *directory* for files matching *pattern*.

    Parameters
    ----------
    arguments : dict
        directory : str — root dir
        pattern   : str — glob pattern
        recursive : bool — default True
    """
    directory: str = arguments.get("directory", "")
    pattern: str = arguments.get("pattern", "")
    recursive: bool = arguments.get("recursive", True)

    # --- Validation ---
    if not directory:
        raise ValueError("'directory' is required.")
    if not pattern:
        raise ValueError("'pattern' is required.")
    if not os.path.isabs(directory):
        raise ValueError("'directory' must be an absolute path.")
    if not _is_path_allowed(directory):
        raise PermissionError(
            f"Directory '{directory}' is outside the allowed paths: {_ALLOWED_DIRS}"
        )
    if not os.path.isdir(directory):
        raise FileNotFoundError(f"Directory not found: '{directory}'")

    # --- Search ---
    if recursive:
        search_pattern = os.path.join(directory, "**", pattern)
        matches = glob.glob(search_pattern, recursive=True)
        # Also check the root level
        matches += glob.glob(os.path.join(directory, pattern), recursive=False)
        matches = list(dict.fromkeys(matches))  # deduplicate, preserve order
    else:
        search_pattern = os.path.join(directory, pattern)
        matches = glob.glob(search_pattern, recursive=False)

    # Filter to files only (not directories)
    files = [m for m in matches if os.path.isfile(m)]

    if not files:
        return [TextContent(type="text", text=f"No files matched pattern '{pattern}' in '{directory}'.")]

    # --- Format results ---
    lines = [f"Found {len(files)} file(s) matching '{pattern}' in '{directory}':\n"]
    for path in sorted(files):
        try:
            stat = os.stat(path)
            size_kb = stat.st_size / 1024
            mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            lines.append(f"  {path}  ({size_kb:.1f} KB, modified {mtime})")
        except OSError:
            lines.append(f"  {path}  (stat unavailable)")

    return [TextContent(type="text", text="\n".join(lines))]


async def _read_file_summary(arguments: dict[str, Any]) -> list[TextContent]:
    """
    Return a preview of a text file plus metadata.

    Parameters
    ----------
    arguments : dict
        file_path : str  — absolute path
        max_lines : int  — lines to preview (default 50)
    """
    file_path: str = arguments.get("file_path", "")
    max_lines: int = int(arguments.get("max_lines", 50))

    # --- Validation ---
    if not file_path:
        raise ValueError("'file_path' is required.")
    if not os.path.isabs(file_path):
        raise ValueError("'file_path' must be an absolute path.")
    if not _is_path_allowed(file_path):
        raise PermissionError(
            f"Path '{file_path}' is outside the allowed paths: {_ALLOWED_DIRS}"
        )
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: '{file_path}'")

    stat = os.stat(file_path)
    size_bytes = stat.st_size
    size_mb = size_bytes / (1024 * 1024)

    if size_mb > MAX_FILE_SIZE_MB:
        raise ValueError(
            f"File is {size_mb:.1f} MB, which exceeds the {MAX_FILE_SIZE_MB} MB limit."
        )

    # --- Detect encoding ---
    with open(file_path, "rb") as fh:
        raw = fh.read(min(size_bytes, 65536))  # read up to 64 KB for detection

    detected = chardet.detect(raw)
    encoding: str = detected.get("encoding") or "utf-8"
    confidence: float = detected.get("confidence", 0.0) or 0.0

    # --- Read content ---
    try:
        with open(file_path, encoding=encoding, errors="replace") as fh:
            all_lines = fh.readlines()
    except (UnicodeDecodeError, LookupError):
        encoding = "utf-8"
        with open(file_path, encoding="utf-8", errors="replace") as fh:
            all_lines = fh.readlines()

    total_lines = len(all_lines)
    preview_lines = all_lines[:max_lines]
    truncated = total_lines > max_lines

    # --- Format output ---
    mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    header = (
        f"File: {file_path}\n"
        f"Size: {size_bytes:,} bytes ({size_mb:.2f} MB)\n"
        f"Lines: {total_lines:,} total | showing first {len(preview_lines)}\n"
        f"Encoding: {encoding} (confidence {confidence:.0%})\n"
        f"Modified: {mtime}\n"
        f"{'─' * 60}\n"
    )
    content = "".join(preview_lines)
    footer = f"\n{'─' * 60}\n[{total_lines - max_lines} more lines not shown]" if truncated else ""

    return [TextContent(type="text", text=header + content + footer)]


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

FILE_SEARCH_HANDLERS: dict = {
    "search_files": _search_files,
    "read_file_summary": _read_file_summary,
}
