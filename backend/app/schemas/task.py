"""Pydantic schemas for tasks and task results."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

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
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    result: Optional[TaskResultRead] = None
