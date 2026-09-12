"""LLM provider abstraction.

The rest of the application depends only on this interface, never on a concrete
provider SDK. Swapping providers is a configuration change (LLM_PROVIDER), not a
code change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class ToolCall:
    """A tool/function call requested by the model."""

    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """Normalized response returned by every provider."""

    text: str = ""
    model: str = ""
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: Optional[str] = None
    raw: Optional[Any] = None


class LLMProvider(ABC):
    """Base class for all LLM providers."""

    def __init__(
        self,
        model: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    @abstractmethod
    def complete(self, prompt: str, *, system: Optional[str] = None) -> LLMResponse:
        """Return a completion for ``prompt`` given an optional ``system`` prompt."""
        raise NotImplementedError

    def chat(
        self,
        messages: List[dict],
        *,
        system: Optional[str] = None,
        tools: Optional[list] = None,
    ) -> LLMResponse:
        """Multi-turn / tool-calling entry point.

        Default implementation ignores tools and flattens the conversation into a
        single prompt for ``complete``. Providers that support function calling
        (mock, OpenAI, Anthropic) override this.
        """
        return self.complete(messages_to_prompt(messages), system=system)

    @property
    def name(self) -> str:
        return type(self).__name__


def messages_to_prompt(messages: List[dict]) -> str:
    """Flatten a chat message list into a single prompt string (fallback)."""
    parts = []
    for message in messages:
        role = message.get("role", "user")
        if role == "tool":
            parts.append(f"[tool:{message.get('name', '')}] {message.get('content', '')}")
        else:
            content = message.get("content")
            if content:
                parts.append(str(content))
    return "\n\n".join(parts)
