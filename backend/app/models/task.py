"""Task ORM model.

A Task is a single subtask produced by the planner and executed by one agent.
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..enums import TaskStatus
from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .execution import Execution
    from .task_result import TaskResult


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"
    # Speeds up the stale-task reaper (WHERE status='RUNNING' AND updated_at < cutoff).
    __table_args__ = (Index("ix_tasks_status_updated_at", "status", "updated_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=TaskStatus.PENDING.value, index=True
    )
    # Execution order within the parent execution (0-based). Named order_index
    # to avoid the SQL reserved word "order".
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Phase 2: distributed scheduling -----------------------------------
    # order_index values of the tasks this task depends on (within the same
    # execution). A task is only enqueued once all its dependencies COMPLETE.
    depends_on: Mapped[Optional[List[int]]] = mapped_column(
        JSON, nullable=True, default=list
    )
    # Set atomically to true when this task has been pushed to the queue, so it
    # is never enqueued twice by concurrent scheduler passes.
    enqueued: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- Phase 3: reliability ---------------------------------------------
    # Number of execution attempts made so far (incremented on each failure).
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # When a RETRYING task becomes eligible to run again.
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Phase 4: observability -------------------------------------------
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tool_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    execution: Mapped["Execution"] = relationship(back_populates="tasks")
    result: Mapped[Optional["TaskResult"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        uselist=False,
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Task id={self.id} type={self.agent_type} status={self.status}>"
