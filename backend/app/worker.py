"""Worker process (Phase 2).

Run with:  python -m app.worker

Starts ``WORKER_CONCURRENCY`` consumer threads that block-pop jobs from Redis
and dispatch them to the scheduler. Run several of these processes/containers
for more parallelism. Concurrency safety lives in the scheduler's atomic DB
claims, so any number of workers/threads is safe.
"""
from __future__ import annotations

import signal
import threading
import time
import uuid

from sqlalchemy import text

from .config import get_settings
from .database import SessionLocal
from .jobqueue import JobType, dequeue, get_redis, promote_due
from .logging_config import configure_logging, get_logger
from .services.scheduler import execute_task, plan_execution, recover_stale_tasks

logger = get_logger(__name__)

_stop = threading.Event()


def _handle_job(job: dict) -> None:
    job_type = job.get("type")
    raw_id = job.get("id")
    if not raw_id:
        logger.error("Job missing id: %r", job)
        return
    try:
        job_id = uuid.UUID(str(raw_id))
    except (ValueError, TypeError):
        logger.error("Invalid job id: %r", raw_id)
        return

    if job_type == JobType.PLAN:
        plan_execution(job_id)
    elif job_type == JobType.TASK:
        execute_task(job_id)
    else:
        logger.error("Unknown job type: %r", job_type)


def _consumer_loop(worker_id: int, poll_timeout: int) -> None:
    logger.info("consumer thread %d started", worker_id)
    while not _stop.is_set():
        try:
            job = dequeue(timeout=poll_timeout)
        except Exception as exc:  # noqa: BLE001 - transient redis errors
            logger.error("dequeue error: %s; retrying shortly", exc)
            time.sleep(1)
            continue
        if job is None:
            continue
        try:
            _handle_job(job)
        except Exception:  # noqa: BLE001 - never let one bad job kill the loop
            logger.exception("error handling job %r", job)
    logger.info("consumer thread %d stopped", worker_id)


def _promoter_loop(interval: float) -> None:
    """Move due delayed (retry) tasks back onto the main queue."""
    logger.info("promoter thread started")
    while not _stop.is_set():
        try:
            moved = promote_due(time.time())
            if moved:
                logger.info("promoted %d delayed task(s) to the queue", moved)
        except Exception as exc:  # noqa: BLE001
            logger.error("promoter error: %s", exc)
        _stop.wait(interval)
    logger.info("promoter thread stopped")


def _reaper_loop(interval: float) -> None:
    """Recover tasks stuck in RUNNING past their lease (crashed workers)."""
    logger.info("reaper thread started")
    while not _stop.is_set():
        db = SessionLocal()
        try:
            recover_stale_tasks(db)
        except Exception as exc:  # noqa: BLE001
            logger.error("reaper error: %s", exc)
        finally:
            db.close()
        _stop.wait(interval)
    logger.info("reaper thread stopped")


def _wait_for_dependencies(max_attempts: int = 60) -> None:
    """Wait for Redis and for the DB schema (migrated by the backend) to exist."""
    for attempt in range(1, max_attempts + 1):
        try:
            get_redis().ping()
            break
        except Exception as exc:  # noqa: BLE001
            logger.info("waiting for redis (%d/%d): %s", attempt, max_attempts, exc)
            time.sleep(2)
    else:
        raise RuntimeError("Redis not reachable")

    for attempt in range(1, max_attempts + 1):
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1 FROM executions LIMIT 1"))
            logger.info("database schema is ready")
            return
        except Exception as exc:  # noqa: BLE001
            logger.info("waiting for database schema (%d/%d): %s", attempt, max_attempts, exc)
            time.sleep(2)
        finally:
            db.close()
    raise RuntimeError("Database schema not ready")


def _install_signal_handlers() -> None:
    def _handler(signum, _frame):
        logger.info("received signal %s; shutting down gracefully", signum)
        _stop.set()

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


def main() -> None:
    configure_logging()
    settings = get_settings()
    logger.info(
        "Worker starting (concurrency=%d, db=%s, llm=%s)",
        settings.worker_concurrency,
        settings.database_url.split("://", 1)[0],
        settings.llm_provider,
    )

    _wait_for_dependencies()
    _install_signal_handlers()

    threads = []
    for i in range(max(1, settings.worker_concurrency)):
        thread = threading.Thread(
            target=_consumer_loop,
            args=(i, settings.worker_poll_timeout),
            daemon=True,
        )
        thread.start()
        threads.append(thread)

    # Maintenance threads: promote due retries, and recover crashed-worker tasks.
    promoter = threading.Thread(
        target=_promoter_loop, args=(settings.delayed_poll_interval_seconds,), daemon=True
    )
    promoter.start()
    threads.append(promoter)

    reaper = threading.Thread(
        target=_reaper_loop, args=(settings.recovery_interval_seconds,), daemon=True
    )
    reaper.start()
    threads.append(reaper)

    logger.info(
        "Worker ready with %d consumer thread(s) + promoter + reaper",
        len(threads) - 2,
    )

    try:
        while not _stop.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        _stop.set()

    # Graceful shutdown: let in-flight jobs finish within a bounded window.
    deadline = time.time() + settings.worker_poll_timeout + 10
    for thread in threads:
        thread.join(timeout=max(0.1, deadline - time.time()))
    logger.info("Worker stopped")


if __name__ == "__main__":
    main()
