"""Execution REST endpoints."""
from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...database import get_db
from ...enums import ExecutionStatus
from ...jobqueue import enqueue_plan
from ...logging_config import get_logger
from ...models import Execution, Task
from ...schemas import ExecutionCreate, ExecutionRead, ExecutionSummary, TaskRead
from ...services.orchestrator import run_execution

logger = get_logger(__name__)

router = APIRouter(prefix="/executions", tags=["executions"])


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
