"""Phase 3 reliability tests: state transitions, idempotency, retries, timeout."""
import time

from app.agents.base import AgentOutput
from app.enums import ExecutionStatus, TaskStatus
from app.models import Execution, Task, TaskResult
from app.services import scheduler
from tests.conftest import reload


class _OkAgent:
    def run(self, description, context=""):
        return AgentOutput(
            text="ok output",
            prompt_tokens=5,
            completion_tokens=5,
            total_tokens=10,
            tool_calls=0,
            model="mock-model",
        )


class _FailingAgent:
    def run(self, description, context=""):
        raise RuntimeError("boom")


class _SlowAgent:
    def run(self, description, context=""):
        time.sleep(0.6)  # exceeds TASK_TIMEOUT_SECONDS (0.3) in tests
        return AgentOutput(text="late", total_tokens=1, model="mock-model")


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------
def test_claim_is_exclusive(db, seed):
    _execution, task = seed()
    assert scheduler._claim_task(db, task.id) is True
    # Second claim must fail (already RUNNING).
    assert scheduler._claim_task(db, task.id) is False
    assert reload(db, Task, task.id).status == TaskStatus.RUNNING.value


def test_happy_path_completes(db, seed, queue_stub, monkeypatch):
    monkeypatch.setattr(scheduler, "get_agent", lambda *_: _OkAgent())
    execution, task = seed()

    scheduler.execute_task(task.id)

    t = reload(db, Task, task.id)
    e = reload(db, Execution, execution.id)
    assert t.status == TaskStatus.COMPLETED.value
    assert t.result is not None and t.result.output == "ok output"
    # Single task all-completed -> execution finalized.
    assert e.status == ExecutionStatus.COMPLETED.value
    assert e.final_result


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------
def test_existing_result_short_circuits(db, seed, queue_stub, monkeypatch):
    # If a result already exists, the agent must not run again.
    execution, task = seed()
    db.add(TaskResult(task_id=task.id, output="prior result"))
    db.commit()

    def _boom(*_):
        raise AssertionError("agent should not run when a result exists")

    monkeypatch.setattr(scheduler, "get_agent", _boom)
    scheduler.execute_task(task.id)

    t = reload(db, Task, task.id)
    assert t.status == TaskStatus.COMPLETED.value
    assert t.result.output == "prior result"


def test_result_is_unique_per_task(db, seed):
    _execution, task = seed()
    scheduler._persist_success(db, task.id, "first")
    scheduler._persist_success(db, task.id, "second")  # must not duplicate

    count = db.query(TaskResult).filter(TaskResult.task_id == task.id).count()
    assert count == 1


def test_duplicate_delivery_is_noop(db, seed, queue_stub, monkeypatch):
    monkeypatch.setattr(scheduler, "get_agent", lambda *_: _OkAgent())
    _execution, task = seed()

    scheduler.execute_task(task.id)  # completes
    scheduler.execute_task(task.id)  # duplicate delivery -> no-op

    assert db.query(TaskResult).filter(TaskResult.task_id == task.id).count() == 1
    assert reload(db, Task, task.id).status == TaskStatus.COMPLETED.value


# ---------------------------------------------------------------------------
# Retry behaviour + exponential backoff + dead-letter
# ---------------------------------------------------------------------------
def test_retries_then_dead_letters(db, seed, queue_stub, monkeypatch):
    monkeypatch.setattr(scheduler, "get_agent", lambda *_: _FailingAgent())
    execution, task = seed()  # TASK_MAX_RETRIES=2 -> tries at attempts 1,2,3

    # Attempt 1 fails -> RETRYING (attempts=1), scheduled for retry.
    scheduler.execute_task(task.id)
    t = reload(db, Task, task.id)
    assert t.status == TaskStatus.RETRYING.value
    assert t.attempts == 1
    assert len(queue_stub["schedule"]) == 1

    # Attempt 2 fails -> RETRYING (attempts=2).
    scheduler.execute_task(task.id)
    t = reload(db, Task, task.id)
    assert t.status == TaskStatus.RETRYING.value
    assert t.attempts == 2
    assert len(queue_stub["schedule"]) == 2

    # Attempt 3 fails -> exhausted -> FAILED + dead-letter.
    scheduler.execute_task(task.id)
    t = reload(db, Task, task.id)
    assert t.status == TaskStatus.FAILED.value
    assert t.attempts == 3
    assert len(queue_stub["dlq"]) == 1
    assert queue_stub["dlq"][0]["task_id"] == str(task.id)

    # Execution finalizes to FAILED once its only task failed.
    assert reload(db, Execution, execution.id).status == ExecutionStatus.FAILED.value


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------
def test_timeout_is_treated_as_failure(db, seed, queue_stub, monkeypatch):
    monkeypatch.setattr(scheduler, "get_agent", lambda *_: _SlowAgent())
    _execution, task = seed()

    scheduler.execute_task(task.id)

    t = reload(db, Task, task.id)
    assert t.status == TaskStatus.RETRYING.value  # first timeout -> retry
    assert t.attempts == 1
    assert "timeout" in (t.error or "").lower()


# ---------------------------------------------------------------------------
# Crash recovery (stale RUNNING lease)
# ---------------------------------------------------------------------------
def test_recover_stale_running_task(db, seed, queue_stub, monkeypatch):
    from datetime import timedelta

    from sqlalchemy import update

    from app.models.base import utcnow

    _execution, task = seed()
    # Simulate a crashed worker: task stuck RUNNING with an old updated_at.
    old = utcnow() - timedelta(seconds=999)
    db.execute(
        update(Task)
        .where(Task.id == task.id)
        .values(status=TaskStatus.RUNNING.value, updated_at=old)
    )
    db.commit()

    recovered = scheduler.recover_stale_tasks(db)
    assert recovered == 1

    t = reload(db, Task, task.id)
    # attempts=1 <= max_retries -> requeued for retry.
    assert t.status == TaskStatus.RETRYING.value
    assert t.attempts == 1
    assert len(queue_stub["schedule"]) == 1
