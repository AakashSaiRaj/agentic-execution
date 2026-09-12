"""Health check endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from ...config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness/readiness check")
def health() -> dict:
    settings = get_settings()
    payload = {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
        "llm_provider": settings.llm_provider,
        "execution_mode": settings.execution_mode,
    }
    # In queue mode, report Redis connectivity (best-effort; never 500 on it).
    if settings.execution_mode.lower() == "queue":
        try:
            from ...jobqueue import get_redis, queue_depth

            get_redis().ping()
            payload["redis"] = "ok"
            payload["queue_depth"] = queue_depth()
        except Exception as exc:  # noqa: BLE001
            payload["redis"] = f"unavailable: {exc}"
    return payload
