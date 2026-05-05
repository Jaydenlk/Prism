"""WebFetchTool — HTTP GET a URL and return the body as text.

Capability: web_access. Uses httpx with a 30s timeout and 5 MiB response cap.
Auto-follows redirects (max 5). Strips simple HTML to plain text when content
type is text/html so the model doesn't drown in markup.
"""
from __future__ import annotations

import re

import httpx

from executor.tools.base import BaseTool, ToolResult

_TIMEOUT_S = 30.0
_MAX_BYTES = 5 * 1024 * 1024
_MAX_REDIRECTS = 5
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


class WebFetchTool(BaseTool):
    capabilities: list[str] = ["web_access"]

    @property
    def name(self) -> str:
        return "WebFetch"

    @property
    def description(self) -> str:
        return (
            "Fetch a URL via HTTP GET and return the response body. HTML responses are "
            "stripped to plain text (tags removed, whitespace collapsed). 30s timeout, "
            "5 MiB body cap, follows up to 5 redirects."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Absolute http(s) URL."},
            },
            "required": ["url"],
        }

    async def execute(self, tool_input: dict) -> ToolResult:
        url = tool_input.get("url")
        if not url:
            return ToolResult(content="url is required", is_error=True)
        if not (url.startswith("http://") or url.startswith("https://")):
            return ToolResult(content="url must start with http:// or https://", is_error=True)

        try:
            async with httpx.AsyncClient(
                timeout=_TIMEOUT_S, follow_redirects=True, max_redirects=_MAX_REDIRECTS
            ) as client:
                resp = await client.get(url)
        except httpx.HTTPError as e:
            return ToolResult(content=f"Fetch failed: {type(e).__name__}: {e}", is_error=True)

        if len(resp.content) > _MAX_BYTES:
            return ToolResult(
                content=f"Response too large: {len(resp.content)} bytes (cap {_MAX_BYTES}).",
                is_error=True,
            )

        ctype = resp.headers.get("content-type", "")
        body = resp.text
        if "text/html" in ctype:
            body = _HTML_TAG_RE.sub(" ", body)
            body = _WHITESPACE_RE.sub(" ", body).strip()

        header = f"GET {url} → {resp.status_code} ({ctype or 'unknown'})\n\n"
        return ToolResult(content=header + body, is_error=resp.status_code >= 400)
