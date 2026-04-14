"""
Web Fetch Tools
===============
Provides two MCP tools:

  fetch_url     — HTTP GET or POST a URL, returns status + truncated body
  extract_links — Fetch a page and extract all hyperlinks with their anchor text
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from mcp.types import TextContent, Tool

logger = logging.getLogger(__name__)

MAX_FETCH_SIZE_KB: int = int(os.getenv("MAX_FETCH_SIZE_KB", "500"))
_REQUEST_TIMEOUT: float = 15.0  # seconds
_USER_AGENT = "claude-mcp-starter/1.0 (github.com/JustDreameritis/claude-mcp-starter)"


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

WEB_FETCH_TOOLS: list[Tool] = [
    Tool(
        name="fetch_url",
        description=(
            "Perform an HTTP GET or POST request and return the response status code "
            "and body (truncated to the configured limit). Useful for reading API "
            "endpoints, web pages, or any HTTP resource."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Full URL to fetch (must start with http:// or https://).",
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST"],
                    "description": "HTTP method. Default: GET.",
                    "default": "GET",
                },
                "headers": {
                    "type": "object",
                    "description": "Optional HTTP headers as key/value pairs.",
                    "additionalProperties": {"type": "string"},
                },
                "body": {
                    "type": "string",
                    "description": "Optional request body for POST requests.",
                },
            },
            "required": ["url"],
        },
    ),
    Tool(
        name="extract_links",
        description=(
            "Fetch a web page and extract all hyperlinks (anchor tags). "
            "Returns each link's URL and anchor text, resolved to absolute URLs."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Full URL of the page to fetch.",
                },
            },
            "required": ["url"],
        },
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_url(url: str) -> None:
    """Raise ValueError if *url* is not a valid http/https URL."""
    if not url:
        raise ValueError("'url' is required.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"URL must start with http:// or https://, got: '{url}'"
        )
    if not parsed.netloc:
        raise ValueError(f"URL has no hostname: '{url}'")


def _truncate_body(body: str, max_kb: int) -> tuple[str, bool]:
    """Return (truncated_body, was_truncated)."""
    max_chars = max_kb * 1024
    if len(body) <= max_chars:
        return body, False
    return body[:max_chars], True


def _extract_links_from_html(base_url: str, html: str) -> list[dict[str, str]]:
    """
    Parse anchor tags from *html* and resolve them against *base_url*.

    Returns a list of dicts with 'url' and 'text' keys.
    Uses pure regex — no lxml/BS4 dependency.
    """
    # Match <a href="...">...</a> in a non-greedy fashion
    anchor_re = re.compile(
        r'<a\s[^>]*?href=["\']([^"\']+)["\'][^>]*?>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    tag_re = re.compile(r"<[^>]+>")  # strip inner HTML tags from anchor text

    links: list[dict[str, str]] = []
    seen: set[str] = set()

    for match in anchor_re.finditer(html):
        href = match.group(1).strip()
        text = tag_re.sub("", match.group(2)).strip()
        text = re.sub(r"\s+", " ", text)  # collapse whitespace

        # Skip javascript: and mailto: links
        if href.lower().startswith(("javascript:", "mailto:", "#")):
            continue

        abs_url = urljoin(base_url, href)
        if abs_url not in seen:
            seen.add(abs_url)
            links.append({"url": abs_url, "text": text or "(no text)"})

    return links


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def _fetch_url(arguments: dict[str, Any]) -> list[TextContent]:
    """
    Perform an HTTP GET or POST and return status + body.

    Parameters
    ----------
    arguments : dict
        url     : str  — target URL
        method  : str  — "GET" or "POST" (default "GET")
        headers : dict — optional headers
        body    : str  — optional POST body
    """
    url: str = arguments.get("url", "")
    method: str = arguments.get("method", "GET").upper()
    extra_headers: dict = arguments.get("headers") or {}
    post_body: str | None = arguments.get("body")

    _validate_url(url)

    if method not in ("GET", "POST"):
        raise ValueError(f"Unsupported method '{method}'. Use GET or POST.")

    headers = {"User-Agent": _USER_AGENT, **extra_headers}

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=_REQUEST_TIMEOUT,
    ) as client:
        if method == "GET":
            response = await client.get(url, headers=headers)
        else:
            response = await client.post(url, headers=headers, content=post_body or "")

    body_text = response.text
    body_preview, truncated = _truncate_body(body_text, MAX_FETCH_SIZE_KB)

    result_lines = [
        f"URL: {url}",
        f"Method: {method}",
        f"Status: {response.status_code} {response.reason_phrase}",
        f"Content-Type: {response.headers.get('content-type', 'unknown')}",
        f"Response size: {len(body_text):,} chars"
        + (f" (truncated to {MAX_FETCH_SIZE_KB} KB)" if truncated else ""),
        "─" * 60,
        body_preview,
    ]
    if truncated:
        result_lines.append(
            f"\n[Response truncated. Full response was {len(body_text):,} chars.]"
        )

    return [TextContent(type="text", text="\n".join(result_lines))]


async def _extract_links(arguments: dict[str, Any]) -> list[TextContent]:
    """
    Fetch a page and extract all anchor links.

    Parameters
    ----------
    arguments : dict
        url : str — page URL
    """
    url: str = arguments.get("url", "")
    _validate_url(url)

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=_REQUEST_TIMEOUT,
    ) as client:
        response = await client.get(url, headers={"User-Agent": _USER_AGENT})

    content_type = response.headers.get("content-type", "")
    if "html" not in content_type.lower() and "text" not in content_type.lower():
        return [
            TextContent(
                type="text",
                text=(
                    f"URL returned content-type '{content_type}', "
                    "which is not HTML. Cannot extract links."
                ),
            )
        ]

    links = _extract_links_from_html(url, response.text)

    if not links:
        return [TextContent(type="text", text=f"No links found on '{url}'.")]

    lines = [f"Found {len(links)} link(s) on '{url}':\n"]
    for i, link in enumerate(links, start=1):
        lines.append(f"  [{i:>3}] {link['url']}")
        if link["text"] and link["text"] != "(no text)":
            lines.append(f"        Text: {link['text'][:120]}")

    return [TextContent(type="text", text="\n".join(lines))]


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

WEB_FETCH_HANDLERS: dict = {
    "fetch_url": _fetch_url,
    "extract_links": _extract_links,
}
