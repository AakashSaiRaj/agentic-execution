"""System / operational endpoints (Phase 3): queue + dead-letter visibility."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ...config import get_settings
from ...logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["system"])


@router.get("/dead-letter", summary="List permanently-failed jobs (dead-letter queue)")
def dead_letter(limit: int = Query(default=50, ge=1, le=200)) -> dict:
    settings = get_settings()
    if settings.execution_mode.lower() != "queue":
        return {"enabled": False, "depth": 0, "entries": []}
    try:
        from ...jobqueue import (
            dead_letter_depth,
            dead_letter_entries,
            delayed_depth,
            queue_depth,
        )

        return {
            "enabled": True,
            "queue_depth": queue_depth(),
            "delayed_depth": delayed_depth(),
            "depth": dead_letter_depth(),
            "entries": dead_letter_entries(limit),
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("dead-letter lookup failed: %s", exc)
        return {"enabled": True, "error": str(exc), "entries": []}
