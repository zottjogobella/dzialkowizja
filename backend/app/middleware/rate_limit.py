from __future__ import annotations

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory sliding window rate limiter. Replace with Redis for multi-process."""

    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _is_rate_limited(self, key: str, max_requests: int, window: int) -> bool:
        now = time.monotonic()
        timestamps = self._requests[key]

        # Remove expired entries
        cutoff = now - window
        self._requests[key] = [t for t in timestamps if t > cutoff]
        timestamps = self._requests[key]

        if len(timestamps) >= max_requests:
            return True

        timestamps.append(now)
        return False

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip rate limiting for health checks
        if request.url.path.startswith("/health"):
            return await call_next(request)

        ip = self._get_client_ip(request)

        # Stricter limits for auth endpoints
        if request.url.path.startswith("/auth"):
            max_req = 10
            window = 60
        else:
            max_req = settings.rate_limit_requests
            window = settings.rate_limit_window_seconds

        key = f"{ip}:{request.url.path.split('/')[1]}"

        if self._is_rate_limited(key, max_req, window):
            return JSONResponse(
                {"detail": "Too many requests"},
                status_code=429,
                headers={"Retry-After": str(window)},
            )

        return await call_next(request)
