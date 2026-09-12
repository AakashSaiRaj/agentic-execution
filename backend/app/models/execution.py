"""Execution ORM model.

An Execution represents a single user request that gets planned into subtasks
and executed end to end.
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..enums import ExecutionStatus
from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .task import Task


class Execution(Base, TimestampMixin):
    __tablename__ = "executions"
    # Speeds up the "recent executions" listing (ORDER BY created_at DESC).
    __table_args__ = (Index("ix_executions_created_at", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_request: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ExecutionStatus.PENDING.value, index=True
    )
    final_result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Phase 4: observability -------------------------------------------
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    tasks: Mapped[List["Task"]] = relationship(
        back_populates="execution",
        cascade="all, delete-orphan",
        order_by="Task.order_index",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Execution id={self.id} status={self.status}>"
