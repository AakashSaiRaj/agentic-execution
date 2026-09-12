"""Tool system base types (Phase 4).

A Tool exposes a name, a human description, and a JSON-schema for its arguments
(so it can be advertised to an LLM for function calling). Tools raise ToolError
on failure; the executor turns any failure into a safe ToolResult.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


class ToolError(Exception):
    """Raised by a tool when it cannot complete its work."""


@dataclass
class ToolSpec:
    """Advertised tool definition (name + description + argument schema)."""

    name: str
    description: str
    parameters: dict


@dataclass
class ToolResult:
    ok: bool
    output: str = ""
    error: Optional[str] = None
    duration_ms: float = 0.0


class Tool(ABC):
    name: str = ""
    description: str = ""
    parameters: dict = {}  # JSON schema for the arguments object

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description, parameters=self.parameters
        )

    @abstractmethod
    def run(self, **kwargs: Any) -> str:
        """Execute the tool and return a string result. Raise ToolError on failure."""
        raise NotImplementedError
