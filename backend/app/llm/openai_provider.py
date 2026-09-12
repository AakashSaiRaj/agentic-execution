"""OpenAI-backed LLM provider (optional).

The ``openai`` SDK is imported lazily so it is only required when the provider
is actually selected via LLM_PROVIDER=openai.
"""
from __future__ import annotations

import json
from typing import Optional

from .base import LLMProvider, LLMResponse, ToolCall


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

    def chat(self, messages, *, system=None, tools=None) -> LLMResponse:
        api_messages = []
        if system:
            api_messages.append({"role": "system", "content": system})
        for message in messages:
            role = message.get("role")
            if role == "tool":
                api_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": message.get("tool_call_id"),
                        "content": message.get("content", ""),
                    }
                )
            elif role == "assistant" and message.get("tool_calls"):
                api_messages.append(
                    {
                        "role": "assistant",
                        "content": message.get("content") or None,
                        "tool_calls": [
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": json.dumps(tc["arguments"]),
                                },
                            }
                            for tc in message["tool_calls"]
                        ],
                    }
                )
            else:
                api_messages.append({"role": role or "user", "content": message.get("content", "")})

        kwargs = dict(
            model=self.model,
            messages=api_messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
            kwargs["tool_choice"] = "auto"

        resp = self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        message = choice.message
        tool_calls = []
        for tc in getattr(message, "tool_calls", None) or []:
            try:
                arguments = json.loads(tc.function.arguments or "{}")
            except (ValueError, TypeError):
                arguments = {}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=arguments))
        usage = getattr(resp, "usage", None)
        return LLMResponse(
            text=message.content or "",
            model=self.model,
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
            tool_calls=tool_calls,
            finish_reason=getattr(choice, "finish_reason", None),
            raw=resp,
        )
