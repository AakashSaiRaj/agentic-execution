"""Base agent definition.

An Agent turns a subtask description (plus accumulated context from earlier
tasks) into an output string, using the configured LLM provider. Concrete
agents only need to declare their type and a role-specific system prompt.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from ..enums import AgentType
from ..llm.base import LLMProvider


@dataclass
class AgentOutput:
    text: str
    total_tokens: Optional[int] = None


class Agent(ABC):
    #: The agent type this class handles. Set by subclasses.
    agent_type: AgentType

    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Role-specific system prompt for this agent."""
        raise NotImplementedError

    def build_user_prompt(self, task_description: str, context: str) -> str:
        context_block = context.strip() or "(no prior context)"
        return (
            f"Task: {task_description}\n\n"
            f"Context from previous steps:\n{context_block}\n\n"
            "Produce your output for this task."
        )

    def run(self, task_description: str, context: str = "") -> AgentOutput:
        prompt = self.build_user_prompt(task_description, context)
        response = self.llm.complete(prompt, system=self.system_prompt)
        return AgentOutput(text=response.text, total_tokens=response.total_tokens)
