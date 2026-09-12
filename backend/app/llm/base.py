"""LLM provider abstraction.

The rest of the application depends only on this interface, never on a concrete
provider SDK. Swapping providers is a configuration change (LLM_PROVIDER), not a
code change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class LLMResponse:
    """Normalized response returned by every provider."""

    text: str
    model: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
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

    @property
    def name(self) -> str:
        return type(self).__name__
