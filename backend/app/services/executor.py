"""Sequential executor (inline mode).

Runs an execution's tasks one after another, in order, in-process. Each task's
output is accumulated into a shared context so later agents build on earlier
ones. The distributed (queue) path lives in scheduler.py; this remains the
zero-dependency fallback. Records per-task observability metrics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from sqlalchemy.orm import Session

from ..agents.registry import get_agent
from ..enums import TaskStatus
from ..llm.base import LLMProvider
from ..llm.pricing import estimate_cost
from ..logging_config import bind_log_context, clear_log_context, get_logger
from ..models import Task, TaskResult
from ..models.base import utcnow

logger = get_logger(__name__)


def _ms_between(start, end) -> Optional[int]:
    if start is None or end is None:
        return None
    if start.tzinfo is not None:
        start = start.replace(tzinfo=None)
    if end.tzinfo is not None:
        end = end.replace(tzinfo=None)
    return max(0, int((end - start).total_seconds() * 1000))


@dataclass
class TaskOutcome:
    agent_type: str
    description: str
    status: TaskStatus
    output: str = ""
    error: str = ""


@dataclass
class ExecutionRunResult:
    all_completed: bool
    outcomes: List[TaskOutcome] = field(default_factory=list)


class SequentialExecutor:
    def __init__(self, db: Session, llm: LLMProvider) -> None:
        self.db = db
        self.llm = llm

    def execute(self, execution_id, tasks: List[Task]) -> ExecutionRunResult:
        outcomes: List[TaskOutcome] = []
        context_parts: List[str] = []
        all_completed = True

        for task in tasks:
            bind_log_context(
                execution_id=execution_id, task_id=task.id, agent_type=task.agent_type
            )
            started = utcnow()
            task.started_at = started
            self._set_status(task, TaskStatus.RUNNING)
            logger.info("RUNNING agent=%s", task.agent_type)

            try:
                agent = get_agent(task.agent_type, self.llm)
                context = "\n\n".join(context_parts)
                output = agent.run(task.description, context)

                now = utcnow()
                self.db.add(TaskResult(task_id=task.id, output=output.text))
                task.completed_at = now
                task.duration_ms = _ms_between(started, now)
                task.total_tokens = output.total_tokens
                task.cost_usd = estimate_cost(
                    output.model, output.prompt_tokens, output.completion_tokens
                )
                task.tool_calls = output.tool_calls
                self._set_status(task, TaskStatus.COMPLETED)

                context_parts.append(f"[{task.agent_type}] {output.text}")
                outcomes.append(
                    TaskOutcome(
                        agent_type=task.agent_type,
                        description=task.description,
                        status=TaskStatus.COMPLETED,
                        output=output.text,
                    )
                )
                logger.info(
                    "COMPLETED tokens=%s cost_usd=%.6f tool_calls=%d",
                    output.total_tokens, task.cost_usd, output.tool_calls,
                )
            except Exception as exc:  # noqa: BLE001 - record and stop the run
                all_completed = False
                message = f"{type(exc).__name__}: {exc}"
                task.completed_at = utcnow()
                self._set_status(task, TaskStatus.FAILED, error=message)
                outcomes.append(
                    TaskOutcome(
                        agent_type=task.agent_type,
                        description=task.description,
                        status=TaskStatus.FAILED,
                        error=message,
                    )
                )
                logger.exception("FAILED: %s", message)
                break

        clear_log_context()
        return ExecutionRunResult(all_completed=all_completed, outcomes=outcomes)

    def _set_status(self, task: Task, status: TaskStatus, *, error: str = "") -> None:
        task.status = status.value
        task.updated_at = utcnow()
        if error:
            task.error = error
        self.db.commit()
