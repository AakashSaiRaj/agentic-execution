"""TaskResult ORM model.

Stores the output produced by an agent for a given task. Separated from Task so
results can grow independently (e.g. multiple result artifacts in later phases)
and to keep a clean 1:1 record of produced output.
"""
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .task import Task


class TaskResult(Base, TimestampMixin):
    __tablename__ = "task_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    output: Mapped[str] = mapped_column(Text, nullable=False)

    task: Mapped["Task"] = relationship(back_populates="result")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<TaskResult id={self.id} task_id={self.task_id}>"
