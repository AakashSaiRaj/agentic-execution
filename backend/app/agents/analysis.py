"""Analysis agent: interprets gathered information and extracts insights."""
from __future__ import annotations

from ..enums import AgentType
from .base import Agent


class AnalysisAgent(Agent):
    agent_type = AgentType.ANALYSIS
    tool_names = ["calculator", "fetch_url"]

    @property
    def system_prompt(self) -> str:
        return (
            "You are an analysis agent. Your job is to analyze the information "
            "provided in the context, identify key insights, patterns, trade-offs "
            "and risks, and reason about what matters most for the task. Be precise "
            "and structured."
        )
