"""Research agent: gathers information relevant to the task."""
from __future__ import annotations

from ..enums import AgentType
from .base import Agent


class ResearchAgent(Agent):
    agent_type = AgentType.RESEARCH

    @property
    def system_prompt(self) -> str:
        return (
            "You are a research agent. Your job is to gather accurate, relevant "
            "information and facts about the given task. Be concise, cite the kinds "
            "of sources you would use, and surface the most important points. Do not "
            "draw final conclusions; that is a later step."
        )
