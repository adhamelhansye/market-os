"""Forecasting endpoints: deterministic, read-only forecast snapshots.

Every route resolves `business_id` from the path via the central
`get_business_from_path` dependency (server-side tenancy validation, 404
on unknown businesses) and requires the `business:read` permission.
Campaign ids are resolved inside the authorized business — unknown or
cross-tenant ids return 404, never a leak.

Horizons: 7, 14, 30, 60 or 90 days, validated server-side. Anything
else yields 422 `invalid_forecast_request`. Training windows are sized
automatically (capped at 180 days) and may be overridden by the caller.

The endpoints are pure read-only when serving snapshots (`/summary`,
`/forecast`, `/campaigns/.../forecast`). `/forecast/generate` is the only
write endpoint: it persists the deterministic snapshot idempotently.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.core.dependencies import (
    CurrentBusinessId,
    DbSession,
    SettingsDep,
    require_permission,
)
from src.core.tenancy import TenantContext
from src.modules.forecasting import service as forecasting_service
from src.modules.forecasting.schemas import (
    CampaignForecastRead,
    ForecastGenerateRequest,
    ForecastSummaryRead,
    ForecastWithPointsRead,
)
from src.modules.metrics.errors import UnknownEntityError

router = APIRouter(tags=["forecasting"])


# ---------------------------------------------------------------------------
# Business forecast endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/businesses/{business_id}/forecast/summary",
    response_model=ForecastSummaryRead,
    summary="Deterministic business forecast snapshot",
)
async def forecast_summary(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    settings: SettingsDep,
    horizon_days: Annotated[
        int,
        Query(description="Forecast horizon (7, 14, 30, 60 or 90 days)."),
    ] = 30,
) -> ForecastSummaryRead:
    business = await forecasting_service.get_business(session, business_id)
    return await forecasting_service.summary(
        session,
        business,
        horizon_days=horizon_days,
        settings=settings,
    )


@router.get(
    "/businesses/{business_id}/forecast",
    response_model=list[ForecastWithPointsRead],
    summary="Latest persisted forecasts with daily points",
)
async def forecast_list(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    horizon_days: Annotated[
        int,
        Query(description="Forecast horizon (7, 14, 30, 60 or 90 days)."),
    ] = 30,
    metric_code: Annotated[
        str | None,
        Query(description="Restrict to one metric."),
    ] = None,
) -> list[ForecastWithPointsRead]:
    business = await forecasting_service.get_business(session, business_id)
    return await forecasting_service.get_business_forecasts(
        session,
        business,
        horizon_days=horizon_days,
        metric_code=metric_code,
    )


@router.post(
    "/businesses/{business_id}/forecast/generate",
    response_model=list[ForecastWithPointsRead],
    summary="Generate (or refresh) the deterministic forecast",
)
async def forecast_generate(
    payload: ForecastGenerateRequest,
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    settings: SettingsDep,
) -> list[ForecastWithPointsRead]:
    business = await forecasting_service.get_business(session, business_id)
    rows = await forecasting_service.generate(
        session,
        business,
        request=payload,
        settings=settings,
    )
    horizon = payload.horizon_days
    metric_code = payload.metric_code
    return await forecasting_service.get_business_forecasts(
        session,
        business,
        horizon_days=horizon,
        metric_code=metric_code,
    ) or [
        ForecastWithPointsRead(
            id=row.id,
            organization_id=row.organization_id,
            business_id=row.business_id,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            metric_code=row.metric_code,
            horizon_days=row.horizon_days,
            forecast_start=row.forecast_start,
            forecast_end=row.forecast_end,
            training_start=row.training_start,
            training_end=row.training_end,
            model=row.model,
            model_version=row.model_version,
            confidence_level=row.confidence_level,
            expected_value=row.expected_value,
            lower_value=row.lower_value,
            upper_value=row.upper_value,
            observations_used=row.observations_used,
            missing_observations=row.missing_observations,
            backtest_mae=row.backtest_mae,
            backtest_smape=row.backtest_smape,
            status=row.status,
            reason=row.reason,
            currency=row.currency,
            source=row.source,
            created_at=row.created_at,
            updated_at=row.updated_at,
            points=[],
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Campaign forecast endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/businesses/{business_id}/campaigns/{campaign_id}/forecast",
    response_model=CampaignForecastRead,
    summary="Per-campaign deterministic forecast",
)
async def campaign_forecast(
    business_id: CurrentBusinessId,
    campaign_id: str,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    settings: SettingsDep,
    horizon_days: Annotated[
        int, Query(description="Forecast horizon (7, 14, 30, 60 or 90 days).")
    ] = 30,
) -> CampaignForecastRead:
    try:
        parsed = uuid.UUID(campaign_id)
    except ValueError:
        raise UnknownEntityError(
            "campaign not found in this business", details={"id": campaign_id}
        ) from None
    business = await forecasting_service.get_business(session, business_id)
    return await forecasting_service.campaign_forecast(
        session,
        business,
        parsed,
        horizon_days=horizon_days,
        settings=settings,
    )


__all__ = ["router"]
