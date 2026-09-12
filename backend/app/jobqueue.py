"""Redis-backed job queue (Phase 2).

A deliberately small, understandable queue built on a single Redis list:
producers ``RPUSH`` JSON jobs; workers ``BLPOP`` them. Two job types exist:

- ``plan``: plan an execution into subtasks and enqueue the independent ones.
- ``task``: execute a single task with the appropriate agent.

Delivery is at-least-once; correctness under concurrency comes from
concurrency-safe database claims in the scheduler, not from the queue itself.
"""
from __future__ import annotations

import json
import uuid
from functools import lru_cache
from typing import Optional

import redis

from .config import get_settings
from .logging_config import get_logger

logger = get_logger(__name__)

# Redis keys
QUEUE_KEY = "aep:jobs"
DELAYED_KEY = "aep:delayed"  # ZSET: task_id -> run-at epoch (retry backoff)
DLQ_KEY = "aep:dlq"  # LIST: permanently-failed jobs


class JobType:
    PLAN = "plan"
    TASK = "task"


@lru_cache
def get_redis() -> "redis.Redis":
    settings = get_settings()
    # decode_responses=True so we work with str, not bytes.
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _enqueue(job: dict) -> None:
    get_redis().rpush(QUEUE_KEY, json.dumps(job))


def enqueue_plan(execution_id: uuid.UUID) -> None:
    _enqueue({"type": JobType.PLAN, "id": str(execution_id)})
    logger.info("[execution_id=%s] enqueued PLAN job", execution_id)


def enqueue_task(task_id: uuid.UUID) -> None:
    _enqueue({"type": JobType.TASK, "id": str(task_id)})
    logger.info("[task_id=%s] enqueued TASK job", task_id)


def dequeue(timeout: int = 5) -> Optional[dict]:
    """Blocking pop of a single job. Returns None if the timeout elapses."""
    result = get_redis().blpop(QUEUE_KEY, timeout=timeout)
    if not result:
        return None
    _key, payload = result
    try:
        return json.loads(payload)
    except (ValueError, TypeError):
        logger.error("Dropping malformed job payload: %r", payload)
        return None


def queue_depth() -> int:
    return int(get_redis().llen(QUEUE_KEY))


# ---------------------------------------------------------------------------
# Delayed / retry queue (ZSET scored by run-at epoch)
# ---------------------------------------------------------------------------
def schedule_task(task_id: uuid.UUID, run_at_epoch: float) -> None:
    """Schedule a task to be (re)enqueued at ``run_at_epoch`` (retry backoff)."""
    get_redis().zadd(DELAYED_KEY, {str(task_id): run_at_epoch})
    logger.info("scheduled retry at epoch=%.0f", run_at_epoch)


def promote_due(now_epoch: float) -> int:
    """Move all due delayed tasks into the main queue. Returns the count moved.

    Uses a conditional ZREM so that with multiple workers promoting, each due
    task is moved exactly once.
    """
    r = get_redis()
    due = r.zrangebyscore(DELAYED_KEY, "-inf", now_epoch)
    moved = 0
    for member in due:
        if r.zrem(DELAYED_KEY, member) == 1:
            r.rpush(QUEUE_KEY, json.dumps({"type": JobType.TASK, "id": member}))
            moved += 1
    return moved


def delayed_depth() -> int:
    return int(get_redis().zcard(DELAYED_KEY))


# ---------------------------------------------------------------------------
# Dead-letter queue (permanently-failed jobs)
# ---------------------------------------------------------------------------
def push_dead_letter(entry: dict) -> None:
    get_redis().rpush(DLQ_KEY, json.dumps(entry))
    logger.warning("pushed task to dead-letter queue")


def dead_letter_entries(limit: int = 50) -> list:
    raw = get_redis().lrange(DLQ_KEY, -limit, -1)
    entries = []
    for item in raw:
        try:
            entries.append(json.loads(item))
        except (ValueError, TypeError):
            continue
    return list(reversed(entries))  # most recent first


def dead_letter_depth() -> int:
    return int(get_redis().llen(DLQ_KEY))
