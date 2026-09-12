"""Base agent definition (Phase 4: tool-calling).

An Agent turns a subtask description (plus accumulated context) into an output
string. It runs a tool-calling loop: the LLM may request tools (advertised from
the registry), which are executed and fed back, until the model returns a final
answer. Token usage and tool-call counts are collected for observability.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List

from ..config import get_settings
from ..llm.base import LLMProvider
from ..logging_config import get_logger
from ..tools.executor import execute_tool
from ..tools.registry import get_tools

logger = get_logger(__name__)


@dataclass
class AgentOutput:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    tool_calls: int = 0
    model: str = ""


class Agent(ABC):
    #: Tools this agent may use (resolved from the registry by name).
    tool_names: List[str] = []

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
            "Use tools if helpful, then produce your output for this task."
        )

    def run(self, task_description: str, context: str = "") -> AgentOutput:
        settings = get_settings()
        tools = get_tools(self.tool_names) if settings.tools_enabled else []
        tool_specs = [t.spec() for t in tools]
        tool_by_name = {t.name: t for t in tools}

        messages = [{"role": "user", "content": self.build_user_prompt(task_description, context)}]
        prompt_tokens = 0
        completion_tokens = 0
        tool_calls_made = 0
        response = None

        for _ in range(max(1, settings.agent_max_tool_iterations)):
            response = self.llm.chat(
                messages, system=self.system_prompt, tools=tool_specs or None
            )
            prompt_tokens += response.prompt_tokens or 0
            completion_tokens += response.completion_tokens or 0

            if not response.tool_calls:
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": response.text or "",
                    "tool_calls": [
                        {"id": c.id, "name": c.name, "arguments": c.arguments}
                        for c in response.tool_calls
                    ],
                }
            )
            for call in response.tool_calls:
                tool = tool_by_name.get(call.name)
                if tool is None:
                    content = f"ERROR: unknown tool '{call.name}'"
                else:
                    result = execute_tool(tool, call.arguments)
                    content = result.output if result.ok else f"ERROR: {result.error}"
                tool_calls_made += 1
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.name,
                        "content": content,
                    }
                )

        text = (response.text if response else "") or "(no answer produced)"
        return AgentOutput(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            tool_calls=tool_calls_made,
            model=getattr(response, "model", "") or self.llm.model,
        )
