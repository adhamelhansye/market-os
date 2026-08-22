"""MarketingOS API entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import get_settings
from src.core.exceptions import register_exception_handlers
from src.core.logging import get_logger, setup_logging
from src.core.middleware import RequestContextMiddleware
from src.modules.auth.router import router as auth_router
from src.modules.bundles.router import router as bundles_router
from src.modules.businesses.router import router as businesses_router
from src.modules.creative.learning.router import router as creative_learning_router
from src.modules.creative.performance.router import router as creative_performance_router
from src.modules.creative.router import router as creative_router
from src.modules.diagnostics.router import router as diagnostics_router
from src.modules.discounts.router import router as discounts_router
from src.modules.economics.router import router as economics_router
from src.modules.forecasting.router import router as forecasting_router
from src.modules.goals.router import router as goals_router
from src.modules.health.router import router as health_router
from src.modules.integrations.router import router as integrations_router
from src.modules.metrics.router import router as metrics_router
from src.modules.organizations.router import router as organizations_router
from src.modules.products.router import router as products_router
from src.modules.recommendations.router import router as recommendations_router
from src.modules.research.router import router as research_router
from src.modules.shipping.router import router as shipping_router
from src.modules.simulator.router import router as simulator_router
from src.modules.strategy.router import router as strategy_router

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
        version="0.2.0",
        description="MarketingOS API — Phase 1: business intelligence core.",
        lifespan=lifespan,
        # Money never leaves the API as a float: Decimal fields serialize
        # as strings everywhere (deterministic, no precision loss).
        json_encoders={Decimal: str},
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
    app.include_router(products_router, prefix=API_PREFIX)
    app.include_router(shipping_router, prefix=API_PREFIX)
    app.include_router(discounts_router, prefix=API_PREFIX)
    app.include_router(bundles_router, prefix=API_PREFIX)
    app.include_router(goals_router, prefix=API_PREFIX)
    app.include_router(economics_router, prefix=API_PREFIX)
    app.include_router(integrations_router, prefix=API_PREFIX)
    app.include_router(metrics_router, prefix=API_PREFIX)
    app.include_router(diagnostics_router, prefix=API_PREFIX)
    app.include_router(forecasting_router, prefix=API_PREFIX)
    app.include_router(recommendations_router, prefix=API_PREFIX)
    app.include_router(simulator_router, prefix=API_PREFIX)
    app.include_router(research_router, prefix=API_PREFIX)
    app.include_router(strategy_router, prefix=API_PREFIX)
    app.include_router(creative_router, prefix=API_PREFIX)
    app.include_router(creative_performance_router, prefix=API_PREFIX)
    app.include_router(creative_learning_router, prefix=API_PREFIX)

    return app


app = create_app()
