"""URL fetch tool: retrieve text content at an http(s) URL (real network)."""
from __future__ import annotations

import httpx

from ..config import get_settings
from .base import Tool, ToolError


class FetchUrlTool(Tool):
    name = "fetch_url"
    description = "Fetch the text content at an http(s) URL (result is truncated)."
    parameters = {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "http(s) URL to fetch"}},
        "required": ["url"],
    }

    def run(self, url: str, **_) -> str:
        settings = get_settings()
        if not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
            raise ToolError("url must start with http:// or https://")
        try:
            response = httpx.get(
                url,
                timeout=settings.tool_timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "aep-fetch/1.0"},
            )
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - normalize to ToolError
            raise ToolError(f"fetch failed: {type(exc).__name__}: {exc}")
        body = response.text[: settings.fetch_max_bytes]
        return f"GET {url} -> {response.status_code} ({len(response.content)} bytes)\n\n{body}"
