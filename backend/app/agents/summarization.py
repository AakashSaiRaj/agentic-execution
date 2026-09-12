"""Summarization agent: synthesizes prior work into a final answer."""
from __future__ import annotations

from ..enums import AgentType
from .base import Agent


class SummarizationAgent(Agent):
    agent_type = AgentType.SUMMARIZATION

    @property
    def system_prompt(self) -> str:
        return (
            "You are a summarization agent. Your job is to synthesize the research "
            "and analysis from the context into a clear, well-structured final answer "
            "for the original request. Lead with the conclusion, then support it "
            "briefly. Avoid repetition."
        )
