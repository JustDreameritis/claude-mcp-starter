"""
Data Transform Tools
====================
Provides two MCP tools:

  json_to_csv — Convert a JSON array to a CSV file on disk
  csv_stats   — Analyze a CSV file: column types, unique counts, sample values
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
from collections import Counter
from pathlib import Path
from typing import Any

from mcp.types import TextContent, Tool

logger = logging.getLogger(__name__)

_DEFAULT_ALLOWED = ["/home", "/tmp", "/mnt"]
_ALLOWED_DIRS: list[str] = [
    d.strip()
    for d in os.getenv("ALLOWED_DIRECTORIES", ",".join(_DEFAULT_ALLOWED)).split(",")
    if d.strip()
]
MAX_FILE_SIZE_MB: float = float(os.getenv("MAX_FILE_SIZE_MB", "10"))
_MAX_SAMPLE_VALUES = 5
_MAX_ROWS_STATS = 100_000  # cap to avoid memory issues on huge files


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

DATA_TRANSFORM_TOOLS: list[Tool] = [
    Tool(
        name="json_to_csv",
        description=(
            "Convert a JSON array of objects to a CSV file. "
            "Each object becomes a row; keys become column headers. "
            "Writes the CSV to the specified output path and returns a summary."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "json_data": {
                    "type": "string",
                    "description": (
                        "A JSON string containing an array of objects. "
                        "Example: '[{\"name\": \"Alice\", \"age\": 30}]'"
                    ),
                },
                "output_path": {
                    "type": "string",
                    "description": (
                        "Absolute path where the CSV file should be written. "
                        "Parent directory must exist."
                    ),
                },
            },
            "required": ["json_data", "output_path"],
        },
    ),
    Tool(
        name="csv_stats",
        description=(
            "Read a CSV file and return per-column statistics: "
            "row count, detected data type, unique value count, "
            "and sample values. Useful for quickly understanding a dataset."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the CSV file to analyze.",
                },
            },
            "required": ["file_path"],
        },
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_path_allowed(path: str) -> bool:
    """Return True if *path* resolves inside one of the allowed directories."""
    resolved = Path(path).resolve()
    return any(
        str(resolved).startswith(str(Path(allowed).resolve()))
        for allowed in _ALLOWED_DIRS
    )


def _infer_type(values: list[str]) -> str:
    """
    Heuristically infer the dominant type of a list of string cell values.

    Returns one of: "integer", "float", "boolean", "empty", "string".
    """
    non_empty = [v for v in values if v.strip()]
    if not non_empty:
        return "empty"

    int_count = float_count = bool_count = 0
    bool_tokens = {"true", "false", "yes", "no", "1", "0"}

    for v in non_empty:
        v_lower = v.strip().lower()
        if v_lower in bool_tokens:
            bool_count += 1
        try:
            int(v.strip())
            int_count += 1
            continue
        except ValueError:
            pass
        try:
            float(v.strip())
            float_count += 1
            continue
        except ValueError:
            pass

    n = len(non_empty)
    if int_count == n:
        return "integer"
    if float_count + int_count == n:
        return "float"
    if bool_count == n:
        return "boolean"
    return "string"


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def _json_to_csv(arguments: dict[str, Any]) -> list[TextContent]:
    """
    Convert a JSON array to a CSV file.

    Parameters
    ----------
    arguments : dict
        json_data   : str — JSON array of objects
        output_path : str — destination file path
    """
    json_data: str = arguments.get("json_data", "")
    output_path: str = arguments.get("output_path", "")

    # --- Validation ---
    if not json_data:
        raise ValueError("'json_data' is required.")
    if not output_path:
        raise ValueError("'output_path' is required.")
    if not os.path.isabs(output_path):
        raise ValueError("'output_path' must be an absolute path.")
    if not _is_path_allowed(output_path):
        raise PermissionError(
            f"Output path '{output_path}' is outside allowed directories: {_ALLOWED_DIRS}"
        )

    parent_dir = str(Path(output_path).parent)
    if not os.path.isdir(parent_dir):
        raise FileNotFoundError(
            f"Parent directory does not exist: '{parent_dir}'"
        )

    # --- Parse JSON ---
    try:
        data = json.loads(json_data)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError(
            "json_data must be a JSON array (list of objects). "
            f"Got: {type(data).__name__}"
        )
    if len(data) == 0:
        raise ValueError("json_data array is empty — nothing to convert.")

    # Collect all unique keys across all rows (preserving first-seen order)
    all_keys: list[str] = []
    seen_keys: set[str] = set()
    for row in data:
        if not isinstance(row, dict):
            raise ValueError(
                "Each element in the JSON array must be an object (dict). "
                f"Found: {type(row).__name__}"
            )
        for k in row.keys():
            if k not in seen_keys:
                all_keys.append(k)
                seen_keys.add(k)

    # --- Write CSV ---
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=all_keys,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(data)
    csv_content = buffer.getvalue()

    with open(output_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(csv_content)

    file_size_kb = os.path.getsize(output_path) / 1024

    summary = (
        f"JSON converted to CSV successfully.\n"
        f"Output: {output_path}\n"
        f"Rows: {len(data):,}\n"
        f"Columns ({len(all_keys)}): {', '.join(all_keys)}\n"
        f"File size: {file_size_kb:.1f} KB"
    )
    return [TextContent(type="text", text=summary)]


async def _csv_stats(arguments: dict[str, Any]) -> list[TextContent]:
    """
    Compute per-column statistics for a CSV file.

    Parameters
    ----------
    arguments : dict
        file_path : str — path to CSV
    """
    file_path: str = arguments.get("file_path", "")

    # --- Validation ---
    if not file_path:
        raise ValueError("'file_path' is required.")
    if not os.path.isabs(file_path):
        raise ValueError("'file_path' must be an absolute path.")
    if not _is_path_allowed(file_path):
        raise PermissionError(
            f"Path '{file_path}' is outside allowed directories: {_ALLOWED_DIRS}"
        )
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: '{file_path}'")

    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise ValueError(
            f"File is {size_mb:.1f} MB, exceeding the {MAX_FILE_SIZE_MB} MB limit."
        )

    # --- Read CSV ---
    column_data: dict[str, list[str]] = {}
    total_rows = 0

    with open(file_path, encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            return [TextContent(type="text", text="CSV file appears to be empty or has no headers.")]

        for col in reader.fieldnames:
            column_data[col] = []

        for row in reader:
            if total_rows >= _MAX_ROWS_STATS:
                break
            total_rows += 1
            for col in reader.fieldnames:
                column_data[col].append(row.get(col, "") or "")

    # --- Compute stats per column ---
    lines = [
        f"CSV Analysis: {file_path}",
        f"Rows read: {total_rows:,}{' (capped)' if total_rows >= _MAX_ROWS_STATS else ''}",
        f"Columns: {len(column_data)}",
        "─" * 60,
    ]

    for col, values in column_data.items():
        non_empty = [v for v in values if v.strip()]
        empty_count = len(values) - len(non_empty)
        dtype = _infer_type(values)
        counter: Counter = Counter(non_empty)
        unique_count = len(counter)

        # Sample values — most common up to _MAX_SAMPLE_VALUES
        samples = [v for v, _ in counter.most_common(_MAX_SAMPLE_VALUES)]
        samples_str = ", ".join(f'"{s}"' for s in samples[:_MAX_SAMPLE_VALUES])

        # Numeric range if applicable
        range_str = ""
        if dtype in ("integer", "float"):
            try:
                nums = [float(v) for v in non_empty]
                range_str = f" | range: {min(nums):.4g} – {max(nums):.4g}"
            except ValueError:
                pass

        lines.append(
            f"\n  Column: {col}\n"
            f"    Type:    {dtype}\n"
            f"    Count:   {len(values):,} values ({empty_count:,} empty)\n"
            f"    Unique:  {unique_count:,}{range_str}\n"
            f"    Samples: {samples_str}"
        )

    return [TextContent(type="text", text="\n".join(lines))]


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

DATA_TRANSFORM_HANDLERS: dict = {
    "json_to_csv": _json_to_csv,
    "csv_stats": _csv_stats,
}
