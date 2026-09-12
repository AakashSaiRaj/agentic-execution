"""Logging configuration.

Phase 1 keeps logging simple but includes a consistent format. Phase 3 will
extend this with structured logging that always carries execution_id and
task_id.
"""
from __future__ import annotations

import logging

from .config import get_settings

_CONFIGURED = False

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def configure_logging() -> None:
    """Configure root logging once, based on settings."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(level=level, format=_LOG_FORMAT)
    # Quiet noisy libraries a little.
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
