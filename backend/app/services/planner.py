"""Planner service.

Turns a free-form user request into 2-5 structured subtasks. The planner asks
the LLM for a JSON plan and parses it defensively, falling back to a sensible
default decomposition if the model returns something unusable.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List

from ..enums import AgentType
from ..llm.base import LLMProvider
from ..logging_config import get_logger

logger = get_logger(__name__)

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


@dataclass
class PlannedSubtask:
    agent_type: AgentType
    description: str
    # order_index values (within this plan) that must COMPLETE before this task
    # can run. Empty => independent (eligible to run immediately / concurrently).
    depends_on: List[int] = field(default_factory=list)


class Planner:
    def __init__(self, llm: LLMProvider, *, min_tasks: int = 2, max_tasks: int = 5) -> None:
        self.llm = llm
        self.min_tasks = max(1, min_tasks)
        self.max_tasks = max(self.min_tasks, max_tasks)

    def _system_prompt(self) -> str:
        return (
            "You are a task planning assistant. Decompose the user's request into "
            f"between {self.min_tasks} and {self.max_tasks} sequential subtasks. Each "
            "subtask must be a JSON object with two fields: 'agent_type' (one of: "
            "research, analysis, summarization) and 'description' (a clear instruction). "
            "Order them so later tasks can build on earlier ones. Respond with ONLY a "
            "JSON array, no surrounding prose."
        )

    def _user_prompt(self, user_request: str) -> str:
        return (
            f'User request:\n"""{user_request}"""\n\n'
            "Return the JSON array of subtasks now."
        )

    def plan(self, user_request: str) -> List[PlannedSubtask]:
        prompt = self._user_prompt(user_request)
        response = self.llm.complete(prompt, system=self._system_prompt())
        subtasks = self._parse(response.text)

        if not subtasks:
            logger.warning("Planner could not parse an LLM plan; using fallback plan.")
            subtasks = self._fallback(user_request)

        # Clamp to the configured maximum. (We keep at least what we have; the
        # fallback already guarantees a reasonable minimum.)
        subtasks = subtasks[: self.max_tasks]
        self._assign_dependencies(subtasks)
        logger.info("Planner produced %d subtask(s).", len(subtasks))
        return subtasks

    def _assign_dependencies(self, subtasks: List[PlannedSubtask]) -> None:
        """Assign a fan-out/fan-in dependency structure.

        Non-summarization tasks are left independent so they run concurrently.
        Each summarization task depends on all earlier tasks, so it only runs
        once the research/analysis it summarizes has completed (the join). Any
        dependencies the LLM supplied are validated (must reference an earlier
        task) and otherwise respected.
        """
        for index, subtask in enumerate(subtasks):
            if subtask.depends_on:
                subtask.depends_on = [
                    d for d in subtask.depends_on if isinstance(d, int) and 0 <= d < index
                ]
                continue
            if subtask.agent_type == AgentType.SUMMARIZATION:
                subtask.depends_on = list(range(index))
            else:
                subtask.depends_on = []

    def _parse(self, text: str) -> List[PlannedSubtask]:
        data = self._load_json(text)
        if not isinstance(data, list):
            return []

        result: List[PlannedSubtask] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            description = str(item.get("description", "")).strip()
            if not description:
                continue
            agent_type = AgentType.from_value(item.get("agent_type", "research"))
            raw_deps = item.get("depends_on")
            deps = [d for d in raw_deps if isinstance(d, int)] if isinstance(raw_deps, list) else []
            result.append(
                PlannedSubtask(agent_type=agent_type, description=description, depends_on=deps)
            )
        return result

    @staticmethod
    def _load_json(text: str):
        if not text:
            return None
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            pass
        # The model may have wrapped the array in prose or code fences.
        match = _JSON_ARRAY_RE.search(text)
        if match:
            try:
                return json.loads(match.group(0))
            except (ValueError, TypeError):
                return None
        return None

    def _fallback(self, user_request: str) -> List[PlannedSubtask]:
        snippet = " ".join(user_request.split())
        if len(snippet) > 160:
            snippet = snippet[:159].rstrip() + "\u2026"
        return [
            PlannedSubtask(
                AgentType.RESEARCH,
                f"Research and gather relevant information for: {snippet}",
            ),
            PlannedSubtask(
                AgentType.ANALYSIS,
                f"Analyze the gathered information and identify key insights for: {snippet}",
            ),
            PlannedSubtask(
                AgentType.SUMMARIZATION,
                f"Summarize the findings into a clear final answer for: {snippet}",
            ),
        ]
