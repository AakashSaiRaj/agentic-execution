"""Execution REST endpoints."""
from __future__ import annotations

import json
import time
import uuid
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...database import SessionLocal, get_db
from ...enums import ExecutionStatus
from ...jobqueue import enqueue_plan
from ...logging_config import get_logger
from ...models import Execution, Task
from ...schemas import ExecutionCreate, ExecutionRead, ExecutionSummary, TaskRead
from ...services.orchestrator import run_execution

logger = get_logger(__name__)

router = APIRouter(prefix="/executions", tags=["executions"])

_TERMINAL = (ExecutionStatus.COMPLETED.value, ExecutionStatus.FAILED.value)


@router.post(
    "",
    response_model=ExecutionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create and start a new execution",
)
def create_execution(
    payload: ExecutionCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Execution:
    execution = Execution(
        user_request=payload.user_request.strip(),
        status=ExecutionStatus.PENDING.value,
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)

    # The request returns immediately; the UI polls GET /executions/{id} to
    # observe status transitions.
    settings = get_settings()
    if settings.execution_mode.lower() == "queue":
        # Phase 2: hand off to Redis; distributed workers plan and execute.
        enqueue_plan(execution.id)
    else:
        # Phase 1 fallback: plan + execute in-process, sequentially.
        background_tasks.add_task(run_execution, execution.id)
    return execution


@router.get(
    "",
    response_model=List[ExecutionSummary],
    summary="List recent executions",
)
def list_executions(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> List[Execution]:
    stmt = select(Execution).order_by(Execution.created_at.desc()).limit(limit)
    return list(db.scalars(stmt).all())


@router.get(
    "/{execution_id}",
    response_model=ExecutionRead,
    summary="Get an execution and its subtasks",
)
def get_execution(
    execution_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> Execution:
    execution = db.get(Execution, execution_id)
    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found"
        )
    return execution


@router.get(
    "/{execution_id}/tasks",
    response_model=List[TaskRead],
    summary="List the subtasks for an execution",
)
def get_execution_tasks(
    execution_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> List[Task]:
    execution = db.get(Execution, execution_id)
    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found"
        )
    stmt = (
        select(Task)
        .where(Task.execution_id == execution_id)
        .order_by(Task.order_index)
    )
    return list(db.scalars(stmt).all())


@router.get(
    "/{execution_id}/events",
    summary="Stream execution + task updates via Server-Sent Events",
)
def stream_execution_events(execution_id: uuid.UUID) -> StreamingResponse:
    """SSE stream: pushes the full execution state whenever it changes, so the
    frontend does not have to poll. Emits an ``update`` event on each change and
    a ``done`` event when the execution reaches a terminal state.
    """
    settings = get_settings()

    def event_stream():
        db = SessionLocal()
        last_payload = None
        deadline = time.time() + settings.sse_max_seconds
        try:
            while time.time() < deadline:
                db.expire_all()
                execution = db.get(Execution, execution_id)
                if execution is None:
                    yield f"event: error\ndata: {json.dumps({'detail': 'not found'})}\n\n"
                    return

                payload = ExecutionRead.model_validate(execution).model_dump(mode="json")
                data = json.dumps(payload)
                if data != last_payload:
                    yield f"event: update\ndata: {data}\n\n"
                    last_payload = data
                    if execution.status in _TERMINAL:
                        yield "event: done\ndata: {}\n\n"
                        return
                else:
                    yield ": keepalive\n\n"
                time.sleep(settings.sse_poll_interval_seconds)
        finally:
            db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
