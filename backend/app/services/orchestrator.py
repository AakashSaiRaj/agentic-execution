"""Orchestrator.

Coordinates the full lifecycle of an execution: PLANNING -> RUNNING ->
COMPLETED/FAILED. Runs in a FastAPI background task, so it manages its own
database session (independent of the request that created the execution).
"""
from __future__ import annotations

import uuid

from ..config import get_settings
from ..database import SessionLocal
from ..enums import ExecutionStatus, TaskStatus
from ..llm.factory import get_llm_provider
from ..logging_config import get_logger
from ..models import Execution, Task
from ..models.base import utcnow
from .aggregator import Aggregator
from .executor import SequentialExecutor
from .planner import Planner

logger = get_logger(__name__)


def run_execution(execution_id: uuid.UUID) -> None:
    """Plan and execute an execution end to end. Never raises."""
    settings = get_settings()
    db = SessionLocal()
    try:
        llm = get_llm_provider()
        execution = db.get(Execution, execution_id)
        if execution is None:
            logger.error("[execution_id=%s] not found; aborting", execution_id)
            return

        # --- Planning ------------------------------------------------------
        _set_execution_status(db, execution, ExecutionStatus.PLANNING)
        planner = Planner(
            llm,
            min_tasks=settings.planner_min_tasks,
            max_tasks=settings.planner_max_tasks,
        )
        subtasks = planner.plan(execution.user_request)

        tasks = []
        for index, subtask in enumerate(subtasks):
            task = Task(
                execution_id=execution.id,
                agent_type=subtask.agent_type.value,
                description=subtask.description,
                order_index=index,
                status=TaskStatus.PENDING.value,
                depends_on=list(subtask.depends_on or []),
            )
            db.add(task)
            tasks.append(task)
        db.commit()
        for task in tasks:
            db.refresh(task)
        logger.info("[execution_id=%s] planned %d task(s)", execution.id, len(tasks))

        # --- Execution -----------------------------------------------------
        _set_execution_status(db, execution, ExecutionStatus.RUNNING)
        executor = SequentialExecutor(db, llm)
        result = executor.execute(execution.id, tasks)

        # --- Aggregation ---------------------------------------------------
        if result.all_completed:
            final_result = Aggregator().aggregate(execution.user_request, result.outcomes)
            execution.final_result = final_result
            _set_execution_status(db, execution, ExecutionStatus.COMPLETED)
            logger.info("[execution_id=%s] COMPLETED", execution.id)
        else:
            failed = next(
                (o for o in result.outcomes if o.status == TaskStatus.FAILED), None
            )
            execution.error = failed.error if failed else "One or more tasks failed."
            _set_execution_status(db, execution, ExecutionStatus.FAILED)
            logger.warning("[execution_id=%s] FAILED: %s", execution.id, execution.error)

    except Exception as exc:  # noqa: BLE001 - background task must not propagate
        logger.exception("[execution_id=%s] pipeline crashed: %s", execution_id, exc)
        _fail_execution(db, execution_id, f"{type(exc).__name__}: {exc}")
    finally:
        db.close()


def _set_execution_status(db, execution: Execution, status: ExecutionStatus) -> None:
    execution.status = status.value
    execution.updated_at = utcnow()
    db.commit()


def _fail_execution(db, execution_id: uuid.UUID, error: str) -> None:
    try:
        db.rollback()
        execution = db.get(Execution, execution_id)
        if execution is not None:
            execution.status = ExecutionStatus.FAILED.value
            execution.error = error
            execution.updated_at = utcnow()
            db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("[execution_id=%s] failed to record failure state", execution_id)
        db.rollback()
