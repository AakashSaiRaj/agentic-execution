"""Pydantic schemas for tasks and task results."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..enums import AgentType, TaskStatus


class TaskResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    output: str
    created_at: datetime


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    execution_id: uuid.UUID
    agent_type: AgentType
    description: str
    status: TaskStatus
    order_index: int
    depends_on: List[int] = Field(default_factory=list)
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    result: Optional[TaskResultRead] = None

    @field_validator("depends_on", mode="before")
    @classmethod
    def _coerce_depends_on(cls, value):
        return value or []
