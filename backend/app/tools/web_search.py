"""Web search tool.

Offline by default: returns deterministic simulated results so the whole
platform runs without external API keys or network access. Swap the body of
``run`` for a real search backend (e.g. an HTTP search API) to use live data.
"""
from __future__ import annotations

from .base import Tool, ToolError


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web and return the top result snippets for a query."
    parameters = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Search query"}},
        "required": ["query"],
    }

    def run(self, query: str, **_) -> str:
        if not isinstance(query, str) or not query.strip():
            raise ToolError("query must be a non-empty string")
        q = query.strip()
        return (
            f"Top web results for '{q}' (simulated):\n"
            f"1. Overview and definition relevant to '{q}'.\n"
            "2. Comparative pros / cons and common trade-offs.\n"
            "3. Practical guidance and typical pitfalls to avoid.\n"
            "(Offline mock results; configure a real search backend for live data.)"
        )
