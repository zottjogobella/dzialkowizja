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
    await init_geo_pool()
    yield
    await close_geo_pool()
    await close_app_db()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Dzialkowizja API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    # Middleware
    # NOTE: BaseHTTPMiddleware disabled - causes asyncpg timeouts
    # TODO: rewrite as pure ASGI middleware
    # app.add_middleware(RequestIdMiddleware)
    # app.add_middleware(SecurityHeadersMiddleware)
    # app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "PUT"],
        allow_headers=["X-CSRF-Token", "Content-Type"],
    )

    # Routers
    from app.admin.router import router as admin_router
    from app.auth.router import router as auth_router
    from app.gesut.router import router as gesut_router
    from app.history.router import router as history_router
    from app.investments.router import router as investments_router
    from app.mpzp.router import router as mpzp_router
    from app.plots.router import router as plots_router
    from app.powerlines.router import router as powerlines_router
    from app.argumentacja.router import router as argumentacja_router
    from app.roszczenia.router import router as roszczenia_router
    from app.search.router import router as search_router
    from app.super_admin.router import router as super_admin_router

    app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
    app.include_router(search_router, prefix="/api/search", tags=["search"])
    app.include_router(plots_router, prefix="/api/plots", tags=["plots"])
    app.include_router(gesut_router, prefix="/api/gesut", tags=["gesut"])
    app.include_router(history_router, prefix="/api/history", tags=["history"])
    app.include_router(powerlines_router, prefix="/api/powerlines", tags=["powerlines"])
    app.include_router(investments_router, prefix="/api/investments", tags=["investments"])
    app.include_router(mpzp_router, prefix="/api/mpzp", tags=["mpzp"])
    app.include_router(roszczenia_router, prefix="/api/roszczenia", tags=["roszczenia"])
    app.include_router(argumentacja_router, prefix="/api/argumentacja", tags=["argumentacja"])
    app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
    app.include_router(super_admin_router, prefix="/api/super-admin", tags=["super-admin"])

    @app.get("/health")
    async def health():
        """Liveness check. No internal details exposed."""
        return {"status": "ok"}

    @app.get("/health/ready")
    async def readiness():
        """Readiness check. Returns only ok/error, no service names or details."""
        from app.db.engine import get_db

        from fastapi.responses import JSONResponse

        try:
            from sqlalchemy import text

            async for db in get_db():
                await db.execute(text("SELECT 1"))
            return {"status": "ok"}
        except Exception:
            return JSONResponse({"status": "error"}, status_code=503)

    return app
