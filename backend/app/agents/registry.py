"""Agent registry: maps an agent type to its implementation."""
from __future__ import annotations

from ..enums import AgentType
from ..llm.base import LLMProvider
from .analysis import AnalysisAgent
from .base import Agent
from .research import ResearchAgent
from .summarization import SummarizationAgent

_AGENT_CLASSES = {
    AgentType.RESEARCH: ResearchAgent,
    AgentType.ANALYSIS: AnalysisAgent,
    AgentType.SUMMARIZATION: SummarizationAgent,
}


def get_agent(agent_type: str, llm: LLMProvider) -> Agent:
    """Return an agent instance for the given (possibly free-form) type string."""
    resolved = AgentType.from_value(agent_type)
    agent_cls = _AGENT_CLASSES[resolved]
    return agent_cls(llm)


def available_agent_types() -> list[str]:
    return [member.value for member in AgentType]
