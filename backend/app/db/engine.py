from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_app_db() -> None:
    global _engine, _session_factory
    _engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_size=10,
        max_overflow=5,
        pool_timeout=30,
        pool_pre_ping=True,
        pool_recycle=300,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def close_app_db() -> None:
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    assert _session_factory is not None, "App DB not initialized"
    async with _session_factory() as session:
        yield session
