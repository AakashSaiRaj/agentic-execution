"""Anthropic-backed LLM provider (optional).

The ``anthropic`` SDK is imported lazily so it is only required when the
provider is actually selected via LLM_PROVIDER=anthropic.
"""
from __future__ import annotations

from typing import Optional

from .base import LLMProvider, LLMResponse, ToolCall


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

    def chat(self, messages, *, system=None, tools=None) -> LLMResponse:
        api_messages = []
        for message in messages:
            role = message.get("role")
            if role == "assistant" and message.get("tool_calls"):
                content = []
                if message.get("content"):
                    content.append({"type": "text", "text": message["content"]})
                for tc in message["tool_calls"]:
                    content.append(
                        {"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["arguments"]}
                    )
                api_messages.append({"role": "assistant", "content": content})
            elif role == "tool":
                api_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": message.get("tool_call_id"),
                                "content": message.get("content", ""),
                            }
                        ],
                    }
                )
            else:
                api_messages.append({"role": role or "user", "content": message.get("content", "")})

        kwargs = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system or "",
            messages=api_messages,
        )
        if tools:
            kwargs["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in tools
            ]

        resp = self._client.messages.create(**kwargs)
        text_parts = []
        tool_calls = []
        for block in getattr(resp, "content", []):
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_parts.append(getattr(block, "text", ""))
            elif block_type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=getattr(block, "id", ""),
                        name=getattr(block, "name", ""),
                        arguments=getattr(block, "input", {}) or {},
                    )
                )
        usage = getattr(resp, "usage", None)
        input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)
        total = None
        if input_tokens is not None and output_tokens is not None:
            total = input_tokens + output_tokens
        return LLMResponse(
            text="".join(text_parts),
            model=self.model,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            total_tokens=total,
            tool_calls=tool_calls,
            finish_reason=getattr(resp, "stop_reason", None),
            raw=resp,
        )
