"""MarketingOS API entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import get_settings
from src.core.exceptions import register_exception_handlers
from src.core.logging import get_logger, setup_logging
from src.core.middleware import RequestContextMiddleware
from src.modules.auth.router import router as auth_router
from src.modules.businesses.router import router as businesses_router
from src.modules.health.router import router as health_router
from src.modules.organizations.router import router as organizations_router

logger = get_logger(__name__)

API_VERSION = "v1"
API_PREFIX = f"/api/{API_VERSION}"


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("MarketingOS API starting (env=%s)", settings.app_env)
        yield
        logger.info("MarketingOS API shutting down")

    app = FastAPI(
        title="MarketingOS API",
        version="0.1.0",
        description="Multi-tenant AI marketing operating system — Phase 0 foundation.",
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware, settings=settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(health_router, prefix=API_PREFIX)
    app.include_router(auth_router, prefix=f"{API_PREFIX}/auth")
    app.include_router(organizations_router, prefix=API_PREFIX)
    app.include_router(businesses_router, prefix=API_PREFIX)

    return app


app = create_app()