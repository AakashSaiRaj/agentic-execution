"""Health / readiness endpoint (Phase 5)."""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from ...config import get_settings
from ...database import SessionLocal

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
        "auth": "enabled" if settings.configured_api_keys else "disabled",
    }

    # Database connectivity.
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        payload["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        payload["database"] = f"unavailable: {exc}"
        payload["status"] = "degraded"
    finally:
        db.close()

    # Redis connectivity (queue mode).
    if settings.execution_mode.lower() == "queue":
        try:
            from ...jobqueue import get_redis, queue_depth

            get_redis().ping()
            payload["redis"] = "ok"
            payload["queue_depth"] = queue_depth()
        except Exception as exc:  # noqa: BLE001
            payload["redis"] = f"unavailable: {exc}"
            payload["status"] = "degraded"

    return payload
