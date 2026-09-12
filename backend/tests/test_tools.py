"""Phase 4 tests: tool correctness/safety, executor timeout + safe errors, registry,
and the agent tool-calling loop (mock)."""
import time

import pytest

from app.agents.analysis import AnalysisAgent
from app.agents.research import ResearchAgent
from app.agents.summarization import SummarizationAgent
from app.llm.mock import MockLLMProvider
from app.tools.base import Tool, ToolError
from app.tools.calculator import CalculatorTool
from app.tools.executor import execute_tool
from app.tools.registry import all_specs, get_tool, get_tools


# --- Calculator correctness + safety ---------------------------------------
def test_calculator_evaluates_expressions():
    calc = CalculatorTool()
    assert calc.run(expression="12 * (3 + 4)") == "84"
    assert calc.run(expression="sqrt(144)") == "12"
    assert calc.run(expression="2 ** 10") == "1024"


def test_calculator_rejects_unsafe_input():
    calc = CalculatorTool()
    with pytest.raises(ToolError):
        calc.run(expression="__import__('os').system('echo hi')")
    with pytest.raises(ToolError):
        calc.run(expression="1 +")  # syntax error
    with pytest.raises(ToolError):
        calc.run(expression="2 ** 99999")  # exponent guard


# --- Registry ---------------------------------------------------------------
def test_registry_resolves_tools():
    assert get_tool("calculator") is not None
    assert get_tool("does_not_exist") is None
    assert len(get_tools(["calculator", "web_search", "nope"])) == 2
    assert {s.name for s in all_specs()} == {"calculator", "web_search", "fetch_url"}


# --- Executor: safe errors + timeout ---------------------------------------
def test_executor_returns_safe_error_on_failure():
    result = execute_tool(CalculatorTool(), {"expression": "1 / 0"})
    assert result.ok is False
    assert "ZeroDivision" in (result.error or "")


def test_executor_handles_bad_arguments():
    result = execute_tool(CalculatorTool(), {"wrong_arg": "x"})
    assert result.ok is False  # missing required 'expression' -> TypeError, caught


class _SlowTool(Tool):
    name = "slow"
    description = "sleeps"
    parameters = {"type": "object", "properties": {}}

    def run(self, **_):
        time.sleep(1.0)
        return "done"


def test_executor_enforces_timeout():
    result = execute_tool(_SlowTool(), {}, timeout=0.2)
    assert result.ok is False
    assert "timed out" in (result.error or "")


# --- Agent tool-calling loop (mock) ----------------------------------------
def test_research_agent_uses_web_search():
    agent = ResearchAgent(MockLLMProvider("mock-model"))
    out = agent.run("Investigate distributed job queues", "")
    assert out.tool_calls >= 1  # web_search invoked
    assert out.text
    assert out.total_tokens > 0


def test_analysis_agent_uses_calculator_when_math_present():
    agent = AnalysisAgent(MockLLMProvider("mock-model"))
    out = agent.run("Compute 12 * (3 + 4) and analyse the result", "")
    assert out.tool_calls >= 1  # calculator invoked


def test_summarization_agent_uses_no_tools():
    agent = SummarizationAgent(MockLLMProvider("mock-model"))
    out = agent.run("Summarize the findings", "some context")
    assert out.tool_calls == 0
    assert out.text
