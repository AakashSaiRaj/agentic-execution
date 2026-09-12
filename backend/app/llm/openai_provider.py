"""OpenAI-backed LLM provider (optional).

The ``openai`` SDK is imported lazily so it is only required when the provider
is actually selected via LLM_PROVIDER=openai.
"""
from __future__ import annotations

from typing import Optional

from .base import LLMProvider, LLMResponse


class OpenAIProvider(LLMProvider):
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
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "LLM_PROVIDER=openai requires the 'openai' package. "
                "Install it with: pip install 'openai>=1.0'"
            ) from exc
        if not api_key:
            raise RuntimeError("LLM_PROVIDER=openai requires OPENAI_API_KEY to be set.")
        self._client = OpenAI(api_key=api_key)

    def complete(self, prompt: str, *, system: Optional[str] = None) -> LLMResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        return LLMResponse(
            text=text,
            model=self.model,
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
            raw=resp,
        )
