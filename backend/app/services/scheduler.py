"""Distributed scheduler (Phase 2).

Contains the logic workers run for the two job types:

- ``plan_execution``: plan an execution into tasks (with dependencies), then
  enqueue the independent ones.
- ``execute_task``: claim and run a single task, then re-schedule the execution.

Concurrency safety is enforced with atomic, guarded UPDATEs (compare-and-set on
status / enqueued flags) rather than locks, so the same task can never be
executed or enqueued twice even with many workers running in parallel.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select, update

from ..config import get_settings
from ..database import SessionLocal
from ..enums import ExecutionStatus, TaskStatus
from ..agents.registry import get_agent
from ..llm.factory import get_llm_provider
from ..jobqueue import enqueue_task
from ..logging_config import get_logger
from ..models import Execution, Task, TaskResult
from ..models.base import utcnow
from .aggregator import Aggregator
from .executor import TaskOutcome
from .planner import Planner

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Job handlers
# ---------------------------------------------------------------------------
def plan_execution(execution_id: uuid.UUID) -> None:
    """Plan an execution into tasks and enqueue the independent ones."""
    settings = get_settings()
    db = SessionLocal()
    try:
        llm = get_llm_provider()
        execution = db.get(Execution, execution_id)
        if execution is None:
            logger.error("[execution_id=%s] not found; cannot plan", execution_id)
            return

        # Only one worker may plan: atomically move PENDING -> PLANNING.
        if not _guard_execution(db, execution_id, ExecutionStatus.PENDING, ExecutionStatus.PLANNING):
            logger.info("[execution_id=%s] already being planned; skipping", execution_id)
            return

        planner = Planner(
            llm,
            min_tasks=settings.planner_min_tasks,
            max_tasks=settings.planner_max_tasks,
        )
        subtasks = planner.plan(execution.user_request)
        for index, subtask in enumerate(subtasks):
            db.add(
                Task(
                    execution_id=execution_id,
                    agent_type=subtask.agent_type.value,
                    description=subtask.description,
                    order_index=index,
                    status=TaskStatus.PENDING.value,
                    depends_on=list(subtask.depends_on or []),
                    enqueued=False,
                )
            )
        db.commit()

        _guard_execution(db, execution_id, ExecutionStatus.PLANNING, ExecutionStatus.RUNNING)
        logger.info("[execution_id=%s] planned %d task(s); scheduling", execution_id, len(subtasks))

        schedule_execution(db, execution_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[execution_id=%s] planning failed: %s", execution_id, exc)
        _fail_execution(db, execution_id, f"Planning failed: {type(exc).__name__}: {exc}")
    finally:
        db.close()


def execute_task(task_id: uuid.UUID) -> None:
    """Claim and execute a single task, then re-schedule its execution."""
    db = SessionLocal()
    try:
        llm = get_llm_provider()
        task = db.get(Task, task_id)
        if task is None:
            logger.error("[task_id=%s] not found; cannot execute", task_id)
            return

        execution_id = task.execution_id

        # Concurrency-safe claim: only the worker that flips PENDING -> RUNNING
        # proceeds. Any duplicate delivery is a no-op.
        if not _claim_task(db, task_id):
            logger.info("[task_id=%s] already claimed; skipping", task_id)
            return

        logger.info(
            "[execution_id=%s task_id=%s] RUNNING agent=%s",
            execution_id, task_id, task.agent_type,
        )

        try:
            context = _dependency_context(db, task)
            agent = get_agent(task.agent_type, llm)
            output = agent.run(task.description, context)
            db.add(TaskResult(task_id=task_id, output=output.text))
            task.status = TaskStatus.COMPLETED.value
            task.updated_at = utcnow()
            db.commit()
            logger.info("[execution_id=%s task_id=%s] COMPLETED", execution_id, task_id)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            failed = db.get(Task, task_id)
            if failed is not None:
                failed.status = TaskStatus.FAILED.value
                failed.error = f"{type(exc).__name__}: {exc}"
                failed.updated_at = utcnow()
                db.commit()
            logger.exception("[execution_id=%s task_id=%s] FAILED", execution_id, task_id)

        # Enqueue newly-unblocked dependents and finalize if everything is done.
        schedule_execution(db, execution_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[task_id=%s] worker error: %s", task_id, exc)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Scheduling pass
# ---------------------------------------------------------------------------
def schedule_execution(db, execution_id: uuid.UUID) -> None:
    """Enqueue ready tasks, cascade dependency failures, and finalize.

    Idempotent and safe to run concurrently from multiple workers.
    """
    execution = db.get(Execution, execution_id)
    if execution is None:
        return

    # Resolve PENDING tasks to a fixpoint: enqueue those whose dependencies are
    # all COMPLETE; fail those whose dependencies have FAILED.
    changed = True
    while changed:
        changed = False
        db.expire_all()  # observe commits made by other workers
        tasks = db.scalars(select(Task).where(Task.execution_id == execution_id)).all()
        by_index = {t.order_index: t for t in tasks}

        for task in tasks:
            if task.status != TaskStatus.PENDING.value or task.enqueued:
                continue
            deps = [by_index[i] for i in (task.depends_on or []) if i in by_index]

            if any(d.status == TaskStatus.FAILED.value for d in deps):
                result = db.execute(
                    update(Task)
                    .where(Task.id == task.id, Task.status == TaskStatus.PENDING.value)
                    .values(
                        status=TaskStatus.FAILED.value,
                        enqueued=True,
                        error="Skipped: a dependency failed",
                        updated_at=utcnow(),
                    )
                )
                db.commit()
                if result.rowcount:
                    changed = True
            elif all(d.status == TaskStatus.COMPLETED.value for d in deps):
                if _mark_enqueued(db, task.id):
                    enqueue_task(task.id)
                    changed = True

    _finalize(db, execution)


def _finalize(db, execution: Execution) -> None:
    db.expire_all()
    tasks = db.scalars(select(Task).where(Task.execution_id == execution.id)).all()
    if not tasks:
        return
    # Not done while any task is still pending or running.
    if any(
        t.status in (TaskStatus.PENDING.value, TaskStatus.RUNNING.value) for t in tasks
    ):
        return

    completed = [t for t in tasks if t.status == TaskStatus.COMPLETED.value]

    if len(completed) == len(tasks):
        final_result = Aggregator().aggregate(execution.user_request, _outcomes(tasks))
        result = db.execute(
            update(Execution)
            .where(Execution.id == execution.id, Execution.status == ExecutionStatus.RUNNING.value)
            .values(
                status=ExecutionStatus.COMPLETED.value,
                final_result=final_result,
                updated_at=utcnow(),
            )
        )
        db.commit()
        if result.rowcount:
            logger.info("[execution_id=%s] COMPLETED", execution.id)
    else:
        failed = [t for t in tasks if t.status == TaskStatus.FAILED.value]
        summary = "; ".join(f"{t.agent_type}: {t.error or 'failed'}" for t in failed)
        result = db.execute(
            update(Execution)
            .where(Execution.id == execution.id, Execution.status == ExecutionStatus.RUNNING.value)
            .values(
                status=ExecutionStatus.FAILED.value,
                error=f"{len(failed)} task(s) failed: {summary}",
                updated_at=utcnow(),
            )
        )
        db.commit()
        if result.rowcount:
            logger.warning("[execution_id=%s] FAILED", execution.id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _dependency_context(db, task: Task) -> str:
    deps = task.depends_on or []
    if not deps:
        return ""
    tasks = db.scalars(select(Task).where(Task.execution_id == task.execution_id)).all()
    by_index = {t.order_index: t for t in tasks}
    parts = []
    for index in deps:
        dep = by_index.get(index)
        if dep is not None and dep.status == TaskStatus.COMPLETED.value and dep.result is not None:
            parts.append(f"[{dep.agent_type}] {dep.result.output}")
    return "\n\n".join(parts)


def _outcomes(tasks) -> list:
    outcomes = []
    for task in sorted(tasks, key=lambda t: t.order_index):
        output = task.result.output if task.result is not None else ""
        outcomes.append(
            TaskOutcome(
                agent_type=task.agent_type,
                description=task.description,
                status=TaskStatus(task.status),
                output=output,
            )
        )
    return outcomes


def _claim_task(db, task_id: uuid.UUID) -> bool:
    result = db.execute(
        update(Task)
        .where(Task.id == task_id, Task.status == TaskStatus.PENDING.value)
        .values(status=TaskStatus.RUNNING.value, updated_at=utcnow())
    )
    db.commit()
    return result.rowcount == 1


def _mark_enqueued(db, task_id: uuid.UUID) -> bool:
    result = db.execute(
        update(Task)
        .where(Task.id == task_id, Task.enqueued.is_(False))
        .values(enqueued=True)
    )
    db.commit()
    return result.rowcount == 1


def _guard_execution(
    db, execution_id: uuid.UUID, expected: ExecutionStatus, new: ExecutionStatus
) -> bool:
    result = db.execute(
        update(Execution)
        .where(Execution.id == execution_id, Execution.status == expected.value)
        .values(status=new.value, updated_at=utcnow())
    )
    db.commit()
    return result.rowcount == 1


def _fail_execution(db, execution_id: uuid.UUID, error: str) -> None:
    try:
        db.rollback()
        db.execute(
            update(Execution)
            .where(Execution.id == execution_id)
            .values(status=ExecutionStatus.FAILED.value, error=error, updated_at=utcnow())
        )
        db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("[execution_id=%s] failed to record failure", execution_id)
        db.rollback()
