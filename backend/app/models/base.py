"""Declarative base and shared mixins for ORM models."""
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Shared declarative base; holds the metadata used by Alembic."""


class TimestampMixin:
    """Adds created_at / updated_at columns with application-side defaults.

    Application-side defaults (rather than DB server defaults) keep behaviour
    identical across SQLite and Postgres and keep migrations simple.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
