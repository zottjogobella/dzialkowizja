from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.engine import close_app_db, init_app_db
from app.db.geo import close_geo_pool, init_geo_pool
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_id import RequestIdMiddleware
from app.middleware.security import SecurityHeadersMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_app_db()
    if settings.geo_db_user:
        await init_geo_pool()
    yield
    await close_geo_pool()
    await close_app_db()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Dzialkowizja API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_prod else None,
        redoc_url=None,
    )

    # Middleware (outermost first)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["X-CSRF-Token", "Content-Type"],
    )

    # Routers
    from app.auth.router import router as auth_router
    from app.history.router import router as history_router
    from app.plots.router import router as plots_router
    from app.search.router import router as search_router

    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    app.include_router(search_router, prefix="/api/search", tags=["search"])
    app.include_router(plots_router, prefix="/api/plots", tags=["plots"])
    app.include_router(history_router, prefix="/api/history", tags=["history"])

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/health/ready")
    async def readiness():
        from app.db.engine import get_db
        from app.db.geo import get_geo_pool

        checks: dict[str, str] = {}

        # Check app DB
        try:
            async for db in get_db():
                await db.execute("SELECT 1")
            checks["app_db"] = "ok"
        except Exception:
            checks["app_db"] = "error"

        # Check geo DB
        try:
            pool = get_geo_pool()
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            checks["geo_db"] = "ok"
        except Exception:
            checks["geo_db"] = "unavailable"

        all_ok = checks.get("app_db") == "ok"
        status_code = 200 if all_ok else 503
        from fastapi.responses import JSONResponse

        return JSONResponse({"status": "ready" if all_ok else "degraded", "checks": checks}, status_code=status_code)

    return app
