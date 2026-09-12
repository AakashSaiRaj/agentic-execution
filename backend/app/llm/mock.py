"""Deterministic mock LLM provider.

Lets the entire platform run end-to-end with no API keys and no network access,
which is ideal for local development, demos and CI. It inspects the prompt to
decide whether it is being asked to *plan* (returns a JSON subtask list) or to
act as an *agent* (returns plausible narrative output).
"""
from __future__ import annotations

import json
import re
from typing import Optional

from .base import LLMProvider, LLMResponse, ToolCall

_REQUEST_RE = re.compile(r'"""(.*?)"""', re.DOTALL)
# Detects an arithmetic expression like "12 * (3 + 4)" or "100 / 4" in free text.
_EXPR_RE = re.compile(r"[-+(]?\s*\d[\d\s+\-*/%().]*[+\-*/%]\s*\d[\d\s+\-*/%().]*")


def _extract_expression(text: str):
    match = _EXPR_RE.search(text or "")
    if not match:
        return None
    expr = match.group(0).strip()
    if any(op in expr for op in "+-*/%") and any(ch.isdigit() for ch in expr):
        return expr
    return None


def _estimate_tokens(text: str) -> int:
    # Rough heuristic: ~4 characters per token.
    return max(1, len(text) // 4)


def _extract_request(prompt: str) -> str:
    match = _REQUEST_RE.search(prompt or "")
    if match:
        return match.group(1).strip()
    return (prompt or "").strip()


def _clip(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "\u2026"


class MockLLMProvider(LLMProvider):
    """A zero-dependency provider that produces coherent, structured output."""

    def complete(self, prompt: str, *, system: Optional[str] = None) -> LLMResponse:
        system_l = (system or "").lower()

        # Test hook: agent calls whose prompt contains "force_fail" raise, so the
        # retry / dead-letter path can be exercised on demand. Planning is exempt.
        if "planning assistant" not in system_l and "force_fail" in (prompt or "").lower():
            raise RuntimeError("forced failure (mock provider saw 'force_fail')")

        if "planning assistant" in system_l:
            text = self._plan(prompt)
        elif "research agent" in system_l:
            text = self._research(prompt)
        elif "analysis agent" in system_l:
            text = self._analysis(prompt)
        elif "summarization agent" in system_l:
            text = self._summarize(prompt)
        else:
            text = self._generic(prompt)

        prompt_tokens = _estimate_tokens((system or "") + prompt)
        completion_tokens = _estimate_tokens(text)
        return LLMResponse(
            text=text,
            model=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            raw={"provider": "mock"},
        )

    # -- planning -----------------------------------------------------------
    def _plan(self, prompt: str) -> str:
        request = _clip(_extract_request(prompt), 200)
        subtasks = [
            {
                "agent_type": "research",
                "description": f"Gather relevant background information, facts and sources about: {request}",
            },
            {
                "agent_type": "analysis",
                "description": f"Analyze the gathered information and identify the key insights, patterns and trade-offs for: {request}",
            },
            {
                "agent_type": "summarization",
                "description": f"Synthesize the research and analysis into a clear, well-structured final answer for: {request}",
            },
        ]
        return json.dumps(subtasks, indent=2)

    # -- agents -------------------------------------------------------------
    def _task_line(self, prompt: str) -> str:
        # Agent prompts embed the subtask after "Task:".
        for line in (prompt or "").splitlines():
            if line.strip().lower().startswith("task:"):
                return _clip(line.split(":", 1)[1], 200)
        return _clip(prompt, 200)

    def _research(self, prompt: str) -> str:
        task = self._task_line(prompt)
        return (
            f"[mock:research] Findings for \u201c{task}\u201d:\n"
            "1. Established a working definition and the main entities involved.\n"
            "2. Collected representative facts, figures and example sources.\n"
            "3. Noted two competing perspectives worth analyzing further.\n\n"
            "(Simulated output from the mock LLM provider. Configure LLM_PROVIDER "
            "and an API key for real model responses.)"
        )

    def _analysis(self, prompt: str) -> str:
        task = self._task_line(prompt)
        return (
            f"[mock:analysis] Analysis of \u201c{task}\u201d:\n"
            "- Key insight: the strongest signal points to a clear, actionable pattern.\n"
            "- Trade-off: short-term cost versus long-term benefit.\n"
            "- Risk: results are sensitive to the quality of the input data.\n\n"
            "(Simulated output from the mock LLM provider.)"
        )

    def _summarize(self, prompt: str) -> str:
        task = self._task_line(prompt)
        return (
            f"[mock:summary] Final answer for \u201c{task}\u201d:\n"
            "Based on the research and analysis, the recommended conclusion balances "
            "the identified trade-offs and highlights the most important insight as the "
            "primary driver of the decision.\n\n"
            "(Simulated output from the mock LLM provider.)"
        )

    def _generic(self, prompt: str) -> str:
        return f"[mock] {_clip(prompt, 240)}"

    # -- tool-calling chat --------------------------------------------------
    def chat(self, messages, *, system=None, tools=None) -> LLMResponse:
        system_l = (system or "").lower()
        tool_names = {getattr(t, "name", None) for t in (tools or [])}
        user_text = next(
            (m.get("content", "") for m in messages if m.get("role") == "user"), ""
        )

        # Test hook (same as complete): agent calls containing "force_fail" raise.
        if "planning assistant" not in system_l and "force_fail" in (user_text or "").lower():
            raise RuntimeError("forced failure (mock provider saw 'force_fail')")

        tool_outputs = [m.get("content", "") for m in messages if m.get("role") == "tool"]

        # First turn: maybe request a tool call.
        if tools and not tool_outputs:
            call = self._decide_tool_call(system_l, user_text, tool_names)
            if call is not None:
                prompt_tokens = _estimate_tokens((system or "") + user_text)
                return LLMResponse(
                    model=self.model,
                    tool_calls=[call],
                    prompt_tokens=prompt_tokens,
                    completion_tokens=0,
                    total_tokens=prompt_tokens,
                    finish_reason="tool_calls",
                )

        # Otherwise: produce the final answer (using any tool observations).
        text = self._final_text(system_l, user_text, tool_outputs)
        prompt_tokens = _estimate_tokens((system or "") + user_text + "".join(tool_outputs))
        completion_tokens = _estimate_tokens(text)
        return LLMResponse(
            text=text,
            model=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            finish_reason="stop",
        )

    def _decide_tool_call(self, system_l: str, user_text: str, tool_names) -> Optional[ToolCall]:
        if "research agent" in system_l and "web_search" in tool_names:
            return ToolCall(
                id="call_ws", name="web_search", arguments={"query": _clip(self._task_line(user_text), 120)}
            )
        if "analysis agent" in system_l and "calculator" in tool_names:
            expr = _extract_expression(user_text)
            if expr:
                return ToolCall(id="call_calc", name="calculator", arguments={"expression": expr})
        return None

    def _final_text(self, system_l: str, user_text: str, tool_outputs) -> str:
        task = self._task_line(user_text)
        observations = ""
        if tool_outputs:
            observations = "\n\nTool observations:\n" + "\n".join(
                f"- {_clip(o, 160)}" for o in tool_outputs
            )
        if "research agent" in system_l:
            return (
                f"[mock:research] Findings for \u201c{task}\u201d, informed by tool results."
                + observations
                + "\n\n(Simulated mock output.)"
            )
        if "analysis agent" in system_l:
            return (
                f"[mock:analysis] Analysis of \u201c{task}\u201d: key insight, trade-off and risk."
                + observations
                + "\n\n(Simulated mock output.)"
            )
        if "summarization agent" in system_l:
            return (
                f"[mock:summary] Final answer for \u201c{task}\u201d: a clear, balanced conclusion "
                "drawn from the research and analysis.\n\n(Simulated mock output.)"
            )
        return f"[mock] {_clip(user_text, 240)}"
