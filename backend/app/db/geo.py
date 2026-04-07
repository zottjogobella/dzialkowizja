from __future__ import annotations

import asyncpg

from app.config import settings

_pool: asyncpg.Pool | None = None


async def init_geo_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(
        host=settings.geo_db_host,
        port=settings.geo_db_port,
        database=settings.geo_db_name,
        user=settings.geo_db_user,
        password=settings.geo_db_password,
        min_size=2,
        max_size=10,
        command_timeout=30,
        statement_cache_size=100,
    )


async def close_geo_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
    _pool = None


def get_geo_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Geo DB pool not initialized")
    return _pool
