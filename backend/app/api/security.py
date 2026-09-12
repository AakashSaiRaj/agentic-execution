"""API key authentication (Phase 5).

If no API keys are configured, auth is disabled (dev-friendly). Otherwise a valid
key must be supplied via the ``X-API-Key`` header, a Bearer token, or an
``api_key`` query parameter (the last one lets browser EventSource/SSE connect,
since it cannot set custom headers).
"""
from __future__ import annotations

from fastapi import HTTPException, Request, status

from ..config import get_settings


def require_api_key(request: Request) -> None:
    keys = get_settings().configured_api_keys
    if not keys:
        return  # auth disabled

    provided = request.headers.get("x-api-key") or request.query_params.get("api_key")
    if not provided:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            provided = auth[7:].strip()

    if not provided or provided not in keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
