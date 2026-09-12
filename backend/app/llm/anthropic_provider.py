"""Anthropic-backed LLM provider (optional).

The ``anthropic`` SDK is imported lazily so it is only required when the
provider is actually selected via LLM_PROVIDER=anthropic.
"""
from __future__ import annotations

from typing import Optional

from .base import LLMProvider, LLMResponse


class AnthropicProvider(LLMProvider):
    def __init__(
        self,
        model: str,
        *,
        api_key: Optional[str],
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> None:
        super().__init__(model, temperature=temperature, max_tokens=max_tokens)
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "LLM_PROVIDER=anthropic requires the 'anthropic' package. "
                "Install it with: pip install 'anthropic>=0.39'"
            ) from exc
        if not api_key:
            raise RuntimeError(
                "LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY to be set."
            )
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, prompt: str, *, system: Optional[str] = None) -> LLMResponse:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system or "",
            messages=[{"role": "user", "content": prompt}],
        )
        # Concatenate any text blocks in the response content.
        text = "".join(
            getattr(block, "text", "") for block in getattr(resp, "content", [])
        )
        usage = getattr(resp, "usage", None)
        input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)
        total = None
        if input_tokens is not None and output_tokens is not None:
            total = input_tokens + output_tokens
        return LLMResponse(
            text=text,
            model=self.model,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            total_tokens=total,
            raw=resp,
        )
