"""Aggregator.

Combines the completed task outcomes into a single final result for the
execution. If a summarization step ran, its output is treated as the primary
final answer; otherwise the outputs are concatenated. Phase 2 will make the
aggregator explicitly wait for all required tasks before producing the result.
"""
from __future__ import annotations

from typing import List

from ..enums import AgentType, TaskStatus
from .executor import TaskOutcome


class Aggregator:
    def aggregate(self, user_request: str, outcomes: List[TaskOutcome]) -> str:
        completed = [o for o in outcomes if o.status == TaskStatus.COMPLETED and o.output]

        if not completed:
            return "No results were produced."

        # Prefer the summarization agent's output as the headline answer.
        summary = next(
            (o for o in completed if o.agent_type == AgentType.SUMMARIZATION.value),
            None,
        )

        lines: List[str] = []
        if summary is not None:
            lines.append(summary.output.strip())
            supporting = [o for o in completed if o is not summary]
        else:
            supporting = completed

        if supporting:
            lines.append("")
            lines.append("---")
            lines.append("Supporting work:")
            for outcome in supporting:
                lines.append("")
                lines.append(f"### {outcome.agent_type}")
                lines.append(outcome.output.strip())

        return "\n".join(lines).strip()
