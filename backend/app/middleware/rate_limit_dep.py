"""Per-user rate limiting as a FastAPI dependency.

Why a dependency, not middleware: ``BaseHTTPMiddleware`` interacts badly
with asyncpg (see ``main.py``), and a pure-ASGI rewrite would still need
per-route limits. Dependencies give us per-route limits for free and run
inside the request scope where the user is already resolved.

Storage:
- Redis (via ``REDIS_URL``) — fixed-window counter using ``INCR`` + ``EXPIRE``,
  shared across uvicorn workers. Required in prod (4 workers).
- In-memory dict — fallback used in dev when ``REDIS_URL`` is unset. Per-process,
  so under multiple workers the effective limit is N×; acceptable for dev.

admin and super_admin are exempt; both can search/browse without throttling.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Awaitable, Callable

from fastapi import Depends, HTTPException

from app.auth.dependencies import require_auth
from app.config import settings
from app.db.models import User

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- backends


class _InMemoryBackend:
    """Per-process fixed-window counter. Locked so concurrent reqs are correct."""

    def __init__(self) -> None:
        self._counts: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def incr(self, key: str, window_seconds: int) -> int:
        async with self._lock:
            now = time.monotonic()
            cutoff = now - window_seconds
            timestamps = [t for t in self._counts[key] if t > cutoff]
            timestamps.append(now)
            self._counts[key] = timestamps
            return len(timestamps)


class _RedisBackend:
    """Fixed-window using INCR. The first INCR creates the key; we EXPIRE it.

    Time bucket is included in the key so each window starts cleanly without
    needing GETSET / SCRIPT to reset the counter atomically.
    """

    def __init__(self, url: str) -> None:
        # redis-py's asyncio client is import-on-use to avoid a hard dep at
        # module import time when Redis isn't configured (dev).
        from redis.asyncio import Redis

        self._client: Redis = Redis.from_url(url, decode_responses=True)

    async def incr(self, key: str, window_seconds: int) -> int:
        bucket = int(time.time() // window_seconds)
        bucket_key = f"{key}:{bucket}"
        # Pipeline keeps both ops in one round-trip.
        async with self._client.pipeline(transaction=False) as pipe:
            pipe.incr(bucket_key, 1)
            pipe.expire(bucket_key, window_seconds + 1)
            count, _ = await pipe.execute()
        return int(count)


_backend: _InMemoryBackend | _RedisBackend | None = None


def _get_backend() -> _InMemoryBackend | _RedisBackend:
    global _backend
    if _backend is not None:
        return _backend
    if settings.redis_url:
        try:
            _backend = _RedisBackend(settings.redis_url)
            logger.info("Rate limiter: using Redis backend at %s", settings.redis_url)
        except Exception:
            logger.exception("Rate limiter: Redis init failed, falling back to in-memory")
            _backend = _InMemoryBackend()
    else:
        _backend = _InMemoryBackend()
        logger.info("Rate limiter: using in-memory backend (REDIS_URL unset)")
    return _backend


# ---------------------------------------------------------------- dependency


def rate_limit(scope: str, max_per_window: int, window_seconds: int = 60) -> Callable[[User], Awaitable[None]]:
    """Build a dependency enforcing ``max_per_window`` requests per ``window_seconds`` per user.

    admin and super_admin bypass the limit. Failures during counter access do not
    block the request — the counter is best-effort.
    """

    async def _dep(user: User = Depends(require_auth)) -> None:
        if user.role in {"admin", "super_admin"}:
            return
        key = f"rl:{scope}:{user.id}"
        try:
            count = await _get_backend().incr(key, window_seconds)
        except Exception:
            logger.exception("Rate limiter incr failed scope=%s user=%s", scope, user.id)
            return
        if count > max_per_window:
            raise HTTPException(
                status_code=429,
                detail="Przekroczono limit zapytań — spróbuj za chwilę.",
                headers={"Retry-After": str(window_seconds)},
            )

    return _dep


# Pre-built deps so routers can `Depends(rate_limit_search)` directly.
rate_limit_search = rate_limit("search", settings.rate_limit_user_search_per_min)
rate_limit_detail = rate_limit("detail", settings.rate_limit_user_detail_per_min)
