"""Structured logging (Phase 3).

Every log record automatically carries ``execution_id`` and ``task_id`` taken
from context variables, so all logs emitted while handling a job are correlated
without threading the ids through every call. Text and JSON formats are
supported (LOG_FORMAT).
"""
from __future__ import annotations

import contextvars
import json
import logging
from typing import Optional

from .config import get_settings

_CONFIGURED = False

# Context variables populated by workers / request handlers.
execution_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "execution_id", default="-"
)
task_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("task_id", default="-")
agent_type_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "agent_type", default="-"
)

_TEXT_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | "
    "execution_id=%(execution_id)s task_id=%(task_id)s agent=%(agent_type)s | %(message)s"
)


class _ContextFilter(logging.Filter):
    """Inject execution_id / task_id / agent_type from context vars onto records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.execution_id = execution_id_var.get()
        record.task_id = task_id_var.get()
        record.agent_type = agent_type_var.get()
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "execution_id": getattr(record, "execution_id", "-"),
            "task_id": getattr(record, "task_id", "-"),
            "agent_type": getattr(record, "agent_type", "-"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    handler = logging.StreamHandler()
    handler.addFilter(_ContextFilter())
    if settings.log_format.lower() == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(_TEXT_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)


def bind_log_context(
    execution_id: Optional[object] = None,
    task_id: Optional[object] = None,
    agent_type: Optional[object] = None,
) -> None:
    """Set correlation ids for subsequent log records in this context/thread."""
    if execution_id is not None:
        execution_id_var.set(str(execution_id))
    if task_id is not None:
        task_id_var.set(str(task_id))
    if agent_type is not None:
        agent_type_var.set(str(agent_type))


def clear_log_context() -> None:
    execution_id_var.set("-")
    task_id_var.set("-")
    agent_type_var.set("-")
