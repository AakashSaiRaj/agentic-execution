"""Tool registry: register tools once and resolve them by name."""
from __future__ import annotations

from typing import Dict, List, Optional

from .base import Tool, ToolSpec
from .calculator import CalculatorTool
from .fetch import FetchUrlTool
from .web_search import WebSearchTool

_REGISTRY: Dict[str, Tool] = {}


def register(tool: Tool) -> None:
    _REGISTRY[tool.name] = tool


def get_tool(name: str) -> Optional[Tool]:
    return _REGISTRY.get(name)


def get_tools(names) -> List[Tool]:
    return [_REGISTRY[n] for n in names if n in _REGISTRY]


def all_specs() -> List[ToolSpec]:
    return [tool.spec() for tool in _REGISTRY.values()]


def _register_defaults() -> None:
    for tool in (CalculatorTool(), WebSearchTool(), FetchUrlTool()):
        register(tool)


_register_defaults()
