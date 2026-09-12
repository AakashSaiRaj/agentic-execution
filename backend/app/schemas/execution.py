"""Pydantic schemas for executions."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..enums import ExecutionStatus
from .task import TaskRead


class ExecutionCreate(BaseModel):
    """Request body for creating a new execution."""

    user_request: str = Field(
        ...,
        min_length=3,
        max_length=8000,
        description="The complex task the platform should plan and execute.",
        examples=["Research the impact of remote work on software team productivity."],
    )


class ExecutionSummary(BaseModel):
    """Lightweight execution view for list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_request: str
    status: ExecutionStatus
    created_at: datetime
    updated_at: datetime


class ExecutionRead(BaseModel):
    """Full execution view including its subtasks."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_request: str
    status: ExecutionStatus
    final_result: Optional[str] = None
    error: Optional[str] = None
    # Observability (Phase 4)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    total_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    created_at: datetime
    updated_at: datetime
    tasks: List[TaskRead] = Field(default_factory=list)
