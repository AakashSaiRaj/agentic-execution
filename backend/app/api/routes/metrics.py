"""Metrics endpoints (Phase 4): JSON for the UI, Prometheus text for scrapers."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from ...database import get_db
from ...observability.metrics import collect_metrics, render_prometheus
from ..security import require_api_key

router = APIRouter(tags=["metrics"])


@router.get(
    "/api/metrics",
    summary="Execution / task / LLM / tool metrics (JSON)",
    dependencies=[Depends(require_api_key)],
)
def metrics_json(db: Session = Depends(get_db)) -> dict:
    return collect_metrics(db)


@router.get("/metrics", response_class=PlainTextResponse, summary="Prometheus metrics")
def metrics_prometheus(db: Session = Depends(get_db)) -> str:
    return render_prometheus(collect_metrics(db))
