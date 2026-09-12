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

from .base import LLMProvider, LLMResponse

_REQUEST_RE = re.compile(r'"""(.*?)"""', re.DOTALL)


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
