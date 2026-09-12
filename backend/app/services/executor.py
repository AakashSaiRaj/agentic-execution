"""Sequential executor.

Phase 1 runs an execution's tasks one after another, in order, in-process. Each
task's output is accumulated into a shared context so later agents (e.g.
analysis, summarization) can build on earlier ones. Phase 2 will replace this
with Redis-backed workers running tasks concurrently.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from sqlalchemy.orm import Session

from ..agents.registry import get_agent
from ..enums import TaskStatus
from ..llm.base import LLMProvider
from ..logging_config import get_logger
from ..models import Task, TaskResult
from ..models.base import utcnow

logger = get_logger(__name__)


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
            log_prefix = f"[execution_id={execution_id} task_id={task.id}]"
            self._set_status(task, TaskStatus.RUNNING)
            logger.info("%s RUNNING agent=%s", log_prefix, task.agent_type)

            try:
                agent = get_agent(task.agent_type, self.llm)
                context = "\n\n".join(context_parts)
                output = agent.run(task.description, context)

                # Persist the result (1:1 with the task).
                self.db.add(TaskResult(task_id=task.id, output=output.text))
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
                logger.info("%s COMPLETED", log_prefix)
            except Exception as exc:  # noqa: BLE001 - we record and stop the run
                all_completed = False
                message = f"{type(exc).__name__}: {exc}"
                self._set_status(task, TaskStatus.FAILED, error=message)
                outcomes.append(
                    TaskOutcome(
                        agent_type=task.agent_type,
                        description=task.description,
                        status=TaskStatus.FAILED,
                        error=message,
                    )
                )
                logger.exception("%s FAILED: %s", log_prefix, message)
                # Sequential dependency: stop at the first failure.
                break

        return ExecutionRunResult(all_completed=all_completed, outcomes=outcomes)

    def _set_status(self, task: Task, status: TaskStatus, *, error: str = "") -> None:
        task.status = status.value
        task.updated_at = utcnow()
        if error:
            task.error = error
        self.db.commit()
