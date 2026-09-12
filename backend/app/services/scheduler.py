"""Distributed scheduler (Phase 2 + Phase 3 reliability).

Workers run two job types:
- ``plan_execution``: plan an execution into tasks (with dependencies), then
  enqueue the independent ones.
- ``execute_task``: claim and run a single task with a timeout, persist its
  result idempotently, retry with exponential backoff on failure, and send it to
  a dead-letter queue once retries are exhausted.

Concurrency safety comes from atomic, guarded UPDATEs (compare-and-set on
status / enqueued), not locks, so any number of workers is safe. Crashed workers
are recovered by ``recover_stale_tasks`` (a lease/heartbeat on RUNNING tasks).
"""
from __future__ import annotations

import random
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from ..agents.registry import get_agent
from ..config import Settings, get_settings
from ..database import SessionLocal
from ..enums import ExecutionStatus, TaskStatus
from ..jobqueue import enqueue_task, push_dead_letter, schedule_task
from ..llm.factory import get_llm_provider
from ..logging_config import bind_log_context, clear_log_context, get_logger
from ..models import Execution, Task, TaskResult
from ..models.base import utcnow
from .aggregator import Aggregator
from .executor import TaskOutcome
from .planner import Planner

logger = get_logger(__name__)

# A task can be picked up when freshly planned (PENDING) or scheduled for retry.
_CLAIMABLE = (TaskStatus.PENDING.value, TaskStatus.RETRYING.value)


class TaskTimeoutError(Exception):
    """Raised when a task exceeds its execution timeout."""


# ---------------------------------------------------------------------------
# Job handlers
# ---------------------------------------------------------------------------
def plan_execution(execution_id: uuid.UUID) -> None:
    """Plan an execution into tasks and enqueue the independent ones."""
    settings = get_settings()
    db = SessionLocal()
    bind_log_context(execution_id=execution_id)
    try:
        llm = get_llm_provider()
        execution = db.get(Execution, execution_id)
        if execution is None:
            logger.error("execution not found; cannot plan")
            return

        # Only one worker may plan: atomically move PENDING -> PLANNING.
        if not _guard_execution(db, execution_id, ExecutionStatus.PENDING, ExecutionStatus.PLANNING):
            logger.info("execution already being planned; skipping")
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
        logger.info("planned %d task(s); scheduling", len(subtasks))
        schedule_execution(db, execution_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("planning failed: %s", exc)
        _fail_execution(db, execution_id, f"Planning failed: {type(exc).__name__}: {exc}")
    finally:
        db.close()
        clear_log_context()


def execute_task(task_id: uuid.UUID) -> None:
    """Claim and execute a single task (with timeout + retry), then re-schedule."""
    settings = get_settings()
    db = SessionLocal()
    bind_log_context(task_id=task_id)
    try:
        llm = get_llm_provider()
        task = db.get(Task, task_id)
        if task is None:
            logger.error("task not found; cannot execute")
            return

        execution_id = task.execution_id
        bind_log_context(execution_id=execution_id, task_id=task_id)

        # Concurrency-safe claim: only the worker that flips PENDING/RETRYING ->
        # RUNNING proceeds. Duplicate deliveries are no-ops.
        if not _claim_task(db, task_id):
            logger.info("task not claimable; skipping (duplicate delivery)")
            return
        db.refresh(task)

        # Idempotency: if a result already exists (e.g. a prior attempt actually
        # succeeded), do not run the agent again.
        if db.scalar(select(TaskResult.id).where(TaskResult.task_id == task_id)) is not None:
            db.execute(
                update(Task)
                .where(Task.id == task_id, Task.status == TaskStatus.RUNNING.value)
                .values(status=TaskStatus.COMPLETED.value, updated_at=utcnow())
            )
            db.commit()
            logger.info("result already present; marked COMPLETED idempotently")
            schedule_execution(db, execution_id)
            return

        attempt = (task.attempts or 0) + 1
        logger.info("RUNNING agent=%s attempt=%d", task.agent_type, attempt)

        try:
            context = _dependency_context(db, task)
            agent = get_agent(task.agent_type, llm)
            output = _run_agent_with_timeout(
                agent, task.description, context, settings.task_timeout_seconds
            )
        except Exception as exc:  # noqa: BLE001 - agent failure or timeout
            db.rollback()
            fresh = db.get(Task, task_id)
            if fresh is not None:
                _retry_or_fail(db, fresh, f"{type(exc).__name__}: {exc}")
            schedule_execution(db, execution_id)
            return

        _persist_success(db, task_id, output.text)
        logger.info("COMPLETED")
        schedule_execution(db, execution_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("worker error: %s", exc)
    finally:
        db.close()
        clear_log_context()


# ---------------------------------------------------------------------------
# Execution helpers (timeout / idempotency / retry)
# ---------------------------------------------------------------------------
def _run_agent_with_timeout(agent, description: str, context: str, timeout: float):
    """Run an agent with a hard timeout.

    The agent runs in a dedicated thread; on timeout we stop waiting (the thread
    may linger, but idempotency guarantees at most one persisted result).
    """
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(agent.run, description, context)
    try:
        result = future.result(timeout=timeout)
        executor.shutdown(wait=False)
        return result
    except FuturesTimeout:
        executor.shutdown(wait=False)
        raise TaskTimeoutError(f"task exceeded timeout of {timeout}s")


def _persist_success(db, task_id: uuid.UUID, output_text: str) -> None:
    """Persist the result + mark COMPLETED idempotently.

    The UNIQUE constraint on task_results.task_id guarantees at most one result
    per task even if two executions race.
    """
    try:
        db.add(TaskResult(task_id=task_id, output=output_text))
        db.flush()
    except IntegrityError:
        db.rollback()  # a result already exists -> idempotent no-op
    db.execute(
        update(Task)
        .where(
            Task.id == task_id,
            Task.status.in_([TaskStatus.RUNNING.value, TaskStatus.RETRYING.value]),
        )
        .values(status=TaskStatus.COMPLETED.value, error=None, updated_at=utcnow())
    )
    db.commit()


def _retry_or_fail(db, task: Task, error_msg: str) -> str:
    """Schedule a backoff retry, or permanently FAIL + dead-letter."""
    settings = get_settings()
    attempts_new = (task.attempts or 0) + 1

    if attempts_new <= settings.task_max_retries:
        delay = _backoff(attempts_new, settings)
        next_at = utcnow() + timedelta(seconds=delay)
        result = db.execute(
            update(Task)
            .where(Task.id == task.id, Task.status == TaskStatus.RUNNING.value)
            .values(
                status=TaskStatus.RETRYING.value,
                attempts=attempts_new,
                next_attempt_at=next_at,
                error=error_msg,
                updated_at=utcnow(),
            )
        )
        db.commit()
        if result.rowcount:
            schedule_task(task.id, next_at.timestamp())
            logger.warning(
                "attempt %d failed (%s); retrying in %.1fs", attempts_new, error_msg, delay
            )
        return "retry"

    result = db.execute(
        update(Task)
        .where(Task.id == task.id, Task.status == TaskStatus.RUNNING.value)
        .values(
            status=TaskStatus.FAILED.value,
            attempts=attempts_new,
            error=error_msg,
            updated_at=utcnow(),
        )
    )
    db.commit()
    if result.rowcount:
        push_dead_letter(
            {
                "task_id": str(task.id),
                "execution_id": str(task.execution_id),
                "agent_type": task.agent_type,
                "attempts": attempts_new,
                "error": error_msg,
                "failed_at": utcnow().isoformat(),
            }
        )
        logger.error(
            "attempt %d failed (%s); retries exhausted -> FAILED + dead-letter",
            attempts_new, error_msg,
        )
    return "failed"


def _backoff(attempt: int, settings: Settings) -> float:
    delay = settings.retry_backoff_base_seconds * (2 ** (attempt - 1))
    delay = min(delay, settings.retry_backoff_max_seconds)
    if settings.retry_backoff_jitter:
        delay *= random.uniform(0.8, 1.2)
    return max(0.0, delay)


# ---------------------------------------------------------------------------
# Crash recovery
# ---------------------------------------------------------------------------
def recover_stale_tasks(db) -> int:
    """Recover tasks stuck in RUNNING past their lease (crashed/lost workers)."""
    settings = get_settings()
    cutoff = utcnow() - timedelta(seconds=settings.task_lease_seconds)
    db.expire_all()
    stale = db.scalars(
        select(Task).where(
            Task.status == TaskStatus.RUNNING.value, Task.updated_at < cutoff
        )
    ).all()

    recovered = 0
    affected = set()
    for task in stale:
        bind_log_context(execution_id=task.execution_id, task_id=task.id)
        _retry_or_fail(db, task, "worker lease expired (possible crash)")
        recovered += 1
        affected.add(task.execution_id)
    clear_log_context()

    for execution_id in affected:
        schedule_execution(db, execution_id)
    if recovered:
        logger.warning("recovered %d stale task(s)", recovered)
    return recovered


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
    # Not done while any task is still pending, running, or retrying.
    non_terminal = (
        TaskStatus.PENDING.value,
        TaskStatus.RUNNING.value,
        TaskStatus.RETRYING.value,
    )
    if any(t.status in non_terminal for t in tasks):
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
            logger.info("execution COMPLETED")
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
            logger.warning("execution FAILED")


# ---------------------------------------------------------------------------
# Small helpers
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
        .where(Task.id == task_id, Task.status.in_(_CLAIMABLE))
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
        logger.exception("failed to record execution failure")
        db.rollback()
