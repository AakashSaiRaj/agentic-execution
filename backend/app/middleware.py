"""ASGI middleware (Phase 5): request-size limit and rate limiting.

Implemented as pure ASGI middleware (not BaseHTTPMiddleware) so they only
inspect the request and pass through untouched — which keeps streaming responses
like SSE working correctly.
"""
from __future__ import annotations

import threading
import time

from starlette.responses import JSONResponse

from .config import get_settings
from .logging_config import get_logger

logger = get_logger(__name__)


def _header(scope, name: bytes):
    for key, value in scope.get("headers", []):
        if key == name:
            return value.decode("latin-1")
    return None


class RequestSizeLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            content_length = _header(scope, b"content-length")
            if content_length is not None:
                try:
                    if int(content_length) > get_settings().max_request_bytes:
                        response = JSONResponse(
                            status_code=413,
                            content={"detail": "Request body too large"},
                        )
                        await response(scope, receive, send)
                        return
                except ValueError:
                    pass
        await self.app(scope, receive, send)


class RateLimitMiddleware:
    """Fixed-window per-minute limiter keyed by API key or client IP.

    In-process (per worker). For multi-instance deployments back it with Redis;
    for a single backend this is sufficient and dependency-free.
    """

    def __init__(self, app):
        self.app = app
        self._lock = threading.Lock()
        self._counts: dict = {}

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        limit = settings.rate_limit_per_minute
        path = scope.get("path", "")
        if limit <= 0 or not path.startswith("/api"):
            await self.app(scope, receive, send)
            return

        key = _header(scope, b"x-api-key")
        if not key:
            client = scope.get("client")
            key = client[0] if client else "anon"

        now = time.time()
        window = int(now // 60)
        with self._lock:
            window_start, count = self._counts.get(key, (window, 0))
            if window_start != window:
                window_start, count = window, 0
            count += 1
            self._counts[key] = (window_start, count)
            if len(self._counts) > 10000:  # opportunistic cleanup
                self._counts = {
                    k: v for k, v in self._counts.items() if v[0] == window
                }

        if count > limit:
            retry_after = 60 - int(now % 60)
            response = JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(retry_after)},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
