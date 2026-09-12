"""Pytest fixtures for Phase 3 reliability tests.

Uses a temporary SQLite database and the mock LLM, and stubs the Redis-backed
queue functions so tests run with no external services. Environment is set
before importing the app so settings pick up the test configuration.
"""
import os
import tempfile

_TMPDIR = tempfile.mkdtemp(prefix="aep-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMPDIR}/test.db")
os.environ.setdefault("EXECUTION_MODE", "queue")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("TASK_MAX_RETRIES", "2")
os.environ.setdefault("TASK_TIMEOUT_SECONDS", "0.3")
os.environ.setdefault("RETRY_BACKOFF_BASE_SECONDS", "0")
os.environ.setdefault("RETRY_BACKOFF_JITTER", "false")
os.environ.setdefault("LOG_LEVEL", "WARNING")

import pytest  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402
from app.enums import ExecutionStatus, TaskStatus  # noqa: E402
from app.models import Base, Execution, Task, TaskResult  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _clean(db):
    # Isolate tests: clear all rows before each test.
    db.query(TaskResult).delete()
    db.query(Task).delete()
    db.query(Execution).delete()
    db.commit()
    yield


@pytest.fixture
def queue_stub(monkeypatch):
    """Replace the scheduler's queue calls with in-memory recorders."""
    from app.services import scheduler

    calls = {"enqueue": [], "schedule": [], "dlq": []}
    monkeypatch.setattr(scheduler, "enqueue_task", lambda tid: calls["enqueue"].append(str(tid)))
    monkeypatch.setattr(
        scheduler, "schedule_task", lambda tid, when: calls["schedule"].append((str(tid), when))
    )
    monkeypatch.setattr(scheduler, "push_dead_letter", lambda entry: calls["dlq"].append(entry))
    return calls


@pytest.fixture
def seed(db):
    """Factory: create a RUNNING execution with one PENDING (already-enqueued) task."""

    def _make(agent_type="research", depends_on=None):
        execution = Execution(user_request="test request", status=ExecutionStatus.RUNNING.value)
        db.add(execution)
        db.commit()
        db.refresh(execution)

        task = Task(
            execution_id=execution.id,
            agent_type=agent_type,
            description="do the thing",
            order_index=0,
            status=TaskStatus.PENDING.value,
            depends_on=depends_on or [],
            enqueued=True,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return execution, task

    return _make


def reload(db, model, obj_id):
    """Re-read an object from the DB (seeing other sessions' commits)."""
    db.expire_all()
    return db.get(model, obj_id)
