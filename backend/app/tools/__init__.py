"""Tool system package (Phase 4)."""
from .base import Tool, ToolError, ToolResult, ToolSpec
from .executor import execute_tool
from .registry import all_specs, get_tool, get_tools, register

__all__ = [
    "Tool",
    "ToolError",
    "ToolResult",
    "ToolSpec",
    "execute_tool",
    "all_specs",
    "get_tool",
    "get_tools",
    "register",
]
