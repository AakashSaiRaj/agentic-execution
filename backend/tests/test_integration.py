"""Integration test (Phase 5): the complete flow through the real Redis queue.

user request -> planning -> queued tasks -> worker execution -> aggregation ->
final result. Requires a running Redis (skipped otherwise); works locally
(against the isolated test DB) and in CI (with postgres + redis services).
"""
import time

import pytest

pytestmark = pytest.mark.integration


def _redis_ok() -> bool:
    try:
        from app.jobqueue import get_redis

        get_redis().ping()
        return True
    except Exception:
        return False


REDIS_AVAILABLE = _redis_ok()


@pytest.mark.skipif(not REDIS_AVAILABLE, reason="requires a running Redis")
def test_full_flow_through_queue():
    from fastapi.testclient import TestClient

    from app.jobqueue import DELAYED_KEY, QUEUE_KEY, dequeue, get_redis, promote_due
    from app.main import app
    from app.worker import _handle_job

    # Start from a clean (test) queue.
    r = get_redis()
    r.delete(QUEUE_KEY)
    r.delete(DELAYED_KEY)

    client = TestClient(app)
    resp = client.post(
        "/api/executions",
        json={"user_request": "Integration: research queues and compute 6 * 7"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "PENDING"
    execution_id = body["id"]

    # Act as the worker pool: drain jobs until the execution is terminal.
    deadline = time.time() + 30
    data = None
    while time.time() < deadline:
        job = dequeue(timeout=1)
        if job:
            _handle_job(job)
        promote_due(time.time() + 120)  # flush any scheduled retries
        data = client.get(f"/api/executions/{execution_id}").json()
        if data["status"] in ("COMPLETED", "FAILED"):
            break

    assert data is not None and data["status"] == "COMPLETED", f"final status: {data}"
    assert data["tasks"], "expected subtasks"
    assert all(t["status"] == "COMPLETED" for t in data["tasks"])
    assert data["final_result"]
    # Observability was recorded end to end.
    assert (data["total_tokens"] or 0) > 0
    assert data["duration_ms"] is not None
    assert sum(t["tool_calls"] for t in data["tasks"]) >= 1  # research used web_search
