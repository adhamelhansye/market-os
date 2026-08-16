"""Forecasting service: read-only orchestration and persistence.

The service is the only place that talks to the database for forecasts:

- resolves the business timezone (`today` in business-local time, never
  the server timezone);
- delegates the math to `engine.py`;
- persists the deterministic snapshot to the `forecasts` table so the
  same `(business, entity, metric, horizon, training_end, model_version)`
  never produces duplicates (idempotency is enforced by the unique
  constraint on the table);
- never updates or deletes an existing goal / budget row (forecasts are
  observational, not authoritative).

The service does not perform any autonomous action: no budget change, no
campaign edit, no notification beyond the read-only API response.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.db.models import Business, BusinessGoal, Forecast, ForecastPoint
from src.modules.businesses.service import get_business
from src.modules.forecasting import engine
from src.modules.forecasting.constants import (
    ALL_ENTITY_TYPES,
    ALLOWED_HORIZON_DAYS,
    DEFAULT_STALE_AFTER_DAYS,
    ENTITY_TYPE_BUSINESS,
    ENTITY_TYPE_CAMPAIGN,
    FORECAST_STATUS_CURRENT,
    FORECAST_STATUS_STALE,
    METRIC_CONTRIBUTION_PROFIT,
    METRIC_PURCHASES,
    METRIC_REVENUE,
    METRIC_SPEND,
    MODEL_VERSIONS,
)
from src.modules.forecasting.errors import ForecastingFilterError, ForecastingInputError
from src.modules.forecasting.schemas import (
    BudgetComparisonRead,
    CampaignForecastRead,
    ForecastGenerateRequest,
    ForecastPointRead,
    ForecastRead,
    ForecastSummaryRead,
    ForecastValueMoneyRead,
    ForecastValueRead,
    ForecastWithPointsRead,
    GoalComparisonRead,
    ScenarioTotalsRead,
)

ZERO = Decimal("0")


# ---------------------------------------------------------------------------
# Timezone helpers
# ---------------------------------------------------------------------------


def business_today(business: Business) -> datetime.date:
    try:
        tz = ZoneInfo(business.timezone)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")
    return datetime.now(tz).date()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_request(
    *,
    entity_type: str,
    metric_code: str | None,
    horizon_days: int,
    confidence_level: Decimal,
) -> None:
    if entity_type not in ALL_ENTITY_TYPES:
        raise ForecastingFilterError(
            f"Unsupported entity_type: {entity_type}. "
            f"Allowed: {sorted(ALL_ENTITY_TYPES)}"
        )
    if horizon_days not in ALLOWED_HORIZON_DAYS:
        raise ForecastingFilterError(
            f"Unsupported horizon_days: {horizon_days}. "
            f"Allowed: {sorted(ALLOWED_HORIZON_DAYS)}"
        )
    if confidence_level <= ZERO or confidence_level >= Decimal("1"):
        raise ForecastingInputError("confidence_level must be between 0 and 1")
    if metric_code is not None and metric_code not in (
        METRIC_REVENUE,
        METRIC_SPEND,
        METRIC_PURCHASES,
        METRIC_CONTRIBUTION_PROFIT,
    ):
        raise ForecastingFilterError(f"Unsupported metric_code: {metric_code}")


def _validate_campaign_ownership(
    session: AsyncSession, business_id, campaign_id: uuid.UUID
) -> None:
    """Raise UnknownEntityError-equivalent on cross-tenant / unknown ids."""
    from src.modules.metrics.aggregation import resolve_entity

    # Re-raise as-is; the dependency layer turns `UnknownEntityError` into
    # 404 with code `not_found`. We use the same tenant-aware resolver the
    # metrics router uses so cross-tenant access always lands in 404.
    return resolve_entity(session, business_id, "campaign", campaign_id)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


async def _upsert_forecast(
    session: AsyncSession,
    *,
    business: Business,
    forecast: engine.EngineForecast,
    entity_id: uuid.UUID | None,
    entity_type: str,
    organization_id: uuid.UUID,
) -> Forecast:
    """Idempotent insert. The unique constraint collapses duplicates."""
    stmt = (
        pg_insert(Forecast)
        .values(
            organization_id=organization_id,
            business_id=business.id,
            entity_type=entity_type,
            entity_id=entity_id,
            metric_code=forecast.metric_code,
            horizon_days=forecast.horizon_days,
            forecast_start=forecast.forecast_start,
            forecast_end=forecast.forecast_end,
            training_start=forecast.training_start,
            training_end=forecast.training_end,
            model=forecast.model,
            model_version=MODEL_VERSIONS.get(forecast.model, "1.0.0"),
            confidence_level=forecast.confidence_level,
            expected_value=forecast.expected_value,
            lower_value=forecast.lower_value,
            upper_value=forecast.upper_value,
            observations_used=forecast.observations_used,
            missing_observations=forecast.missing_observations,
            backtest_mae=forecast.backtest.mae if forecast.backtest else None,
            backtest_smape=forecast.backtest.smape if forecast.backtest else None,
            status=forecast.status,
            reason=forecast.reason,
            currency=forecast.currency,
            source=forecast.source,
        )
        .on_conflict_do_update(
            index_elements=[
                "organization_id",
                "business_id",
                "entity_type",
                "entity_id",
                "metric_code",
                "horizon_days",
                "training_end",
                "model_version",
            ],
            set_={
                "expected_value": forecast.expected_value,
                "lower_value": forecast.lower_value,
                "upper_value": forecast.upper_value,
                "observations_used": forecast.observations_used,
                "missing_observations": forecast.missing_observations,
                "backtest_mae": forecast.backtest.mae if forecast.backtest else None,
                "backtest_smape": forecast.backtest.smape if forecast.backtest else None,
                "status": forecast.status,
                "reason": forecast.reason,
                "updated_at": datetime.now(UTC),
            },
        )
        .returning(Forecast)
    )
    result = await session.execute(stmt)
    row = result.scalar_one()
    await session.commit()
    return row


async def _replace_points(
    session: AsyncSession,
    forecast_row: Forecast,
    *,
    scenarios: engine.ScenarioSet | None,
) -> list[ForecastPoint]:
    if scenarios is None:
        return []
    # Wipe and rewrite; the unique (forecast_id, date) makes this safe.
    existing = list(
        await session.scalars(
            select(ForecastPoint).where(ForecastPoint.forecast_id == forecast_row.id)
        )
    )
    for point in existing:
        await session.delete(point)
    points: list[ForecastPoint] = []
    for scenario in scenarios.points:
        point = ForecastPoint(
            forecast_id=forecast_row.id,
            date=scenario.date,
            expected_value=scenario.expected,
            lower_value=scenario.lower,
            upper_value=scenario.upper,
        )
        session.add(point)
        points.append(point)
    await session.commit()
    return points


# ---------------------------------------------------------------------------
# Read-side helpers
# ---------------------------------------------------------------------------


async def _list_latest_forecasts(
    session: AsyncSession,
    *,
    business_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID | None,
    horizon_days: int,
) -> list[Forecast]:
    stmt = (
        select(Forecast)
        .where(
            Forecast.business_id == business_id,
            Forecast.entity_type == entity_type,
            (
                Forecast.entity_id.is_(None)
                if entity_id is None
                else Forecast.entity_id == entity_id
            ),
            Forecast.horizon_days == horizon_days,
        )
        .order_by(Forecast.training_end.desc(), Forecast.created_at.desc())
    )
    return list(await session.scalars(stmt))


def _freshness(forecast: Forecast, *, today) -> str:
    if forecast.status == "unavailable":
        return "unavailable"
    cutoff = today - timedelta(days=DEFAULT_STALE_AFTER_DAYS)
    if forecast.training_end < cutoff:
        return FORECAST_STATUS_STALE
    return FORECAST_STATUS_CURRENT


def _to_forecast_read(forecast: Forecast) -> ForecastRead:
    return ForecastRead(
        id=forecast.id,
        organization_id=forecast.organization_id,
        business_id=forecast.business_id,
        entity_type=forecast.entity_type,
        entity_id=forecast.entity_id,
        metric_code=forecast.metric_code,
        horizon_days=forecast.horizon_days,
        forecast_start=forecast.forecast_start,
        forecast_end=forecast.forecast_end,
        training_start=forecast.training_start,
        training_end=forecast.training_end,
        model=forecast.model,
        model_version=forecast.model_version,
        confidence_level=forecast.confidence_level,
        expected_value=forecast.expected_value,
        lower_value=forecast.lower_value,
        upper_value=forecast.upper_value,
        observations_used=forecast.observations_used,
        missing_observations=forecast.missing_observations,
        backtest_mae=forecast.backtest_mae,
        backtest_smape=forecast.backtest_smape,
        status=forecast.status,
        reason=forecast.reason,
        currency=forecast.currency,
        source=forecast.source,
        created_at=forecast.created_at,
        updated_at=forecast.updated_at,
    )


def _to_value_money(forecast: Forecast) -> ForecastValueMoneyRead:
    return ForecastValueMoneyRead(
        value=forecast.expected_value,
        status=forecast.status,
        reason=forecast.reason,
        currency=forecast.currency,
        source=forecast.source,
    )


def _to_value_ratio(forecast: Forecast | None) -> ForecastValueRead:
    if forecast is None:
        return ForecastValueRead(value=None, status="unavailable", reason="not_forecasted")
    return ForecastValueRead(
        value=forecast.expected_value,
        status=forecast.status,
        reason=forecast.reason,
    )


def _scenario_totals(forecasts: list[Forecast]) -> dict[str, ScenarioTotalsRead]:
    totals: dict[str, ScenarioTotalsRead] = {}
    for forecast in forecasts:
        if forecast.expected_value is None:
            continue
        totals[forecast.metric_code] = ScenarioTotalsRead(
            metric_code=forecast.metric_code,
            expected=forecast.expected_value,
            lower=forecast.lower_value or ZERO,
            upper=forecast.upper_value or forecast.expected_value,
        )
    return totals


async def _resolve_goal(session: AsyncSession, business: Business, today) -> BusinessGoal | None:

    target_day = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
    return await session.scalar(
        select(BusinessGoal).where(
            BusinessGoal.business_id == business.id,
            BusinessGoal.period_start <= target_day,
            BusinessGoal.period_end > target_day,
        )
    )


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


async def list_business_forecasts(
    session: AsyncSession,
    business: Business,
    *,
    horizon_days: int,
) -> list[Forecast]:
    return await _list_latest_forecasts(
        session,
        business_id=business.id,
        entity_type=ENTITY_TYPE_BUSINESS,
        entity_id=None,
        horizon_days=horizon_days,
    )


async def summary(
    session: AsyncSession,
    business: Business,
    *,
    horizon_days: int,
    settings: Settings,
) -> ForecastSummaryRead:
    today = business_today(business)
    persisted = await list_business_forecasts(session, business, horizon_days=horizon_days)
    if not persisted:
        # Cold start: generate once on demand.
        await generate(
            session,
            business,
            request=ForecastGenerateRequest(
                horizon_days=horizon_days,
                entity_type=ENTITY_TYPE_BUSINESS,
                entity_id=None,
            ),
            settings=settings,
        )
        persisted = await list_business_forecasts(
            session, business, horizon_days=horizon_days
        )

    goal = await _resolve_goal(session, business, today)
    forecasts = [_to_forecast_read(f) for f in persisted]

    scenario_totals = _scenario_totals(persisted)
    goals_view = []
    for forecast in persisted:
        if forecast.metric_code == METRIC_CONTRIBUTION_PROFIT:
            target = goal.target_profit if goal else None
        elif forecast.metric_code == METRIC_REVENUE:
            target = goal.target_revenue if goal else None
        else:
            target = None
        goals_view.append(
            GoalComparisonRead(
                metric_code=forecast.metric_code,
                target_value=target,
                forecast_value=forecast.expected_value,
                gap=(
                    (forecast.expected_value - target).quantize(Decimal("0.01"))
                    if (target is not None and forecast.expected_value is not None)
                    else None
                ),
                gap_percent=None,
                status=(
                    "available"
                    if (target is not None and forecast.expected_value is not None)
                    else "unavailable"
                ),
                reason=(
                    None
                    if (target is not None and forecast.expected_value is not None)
                    else "no_target_or_forecast"
                ),
            )
        )

    budget_comparison: BudgetComparisonRead | None = None
    spend_forecast = next(
        (f for f in persisted if f.metric_code == METRIC_SPEND), None
    )
    if goal is not None and goal.ad_budget is not None:
        from src.modules.forecasting.engine import compare_to_budget
        result = compare_to_budget(
            engine.EngineForecast(
                metric_code=METRIC_SPEND,
                horizon_days=horizon_days,
                forecast_start=persisted[0].forecast_start if persisted else today,
                forecast_end=persisted[0].forecast_end if persisted else today,
                training_start=persisted[0].training_start if persisted else today,
                training_end=persisted[0].training_end if persisted else today,
                model=spend_forecast.model if spend_forecast else "naive",
                confidence_level=Decimal("0.80"),
                expected_value=spend_forecast.expected_value if spend_forecast else None,
                lower_value=spend_forecast.lower_value if spend_forecast else None,
                upper_value=spend_forecast.upper_value if spend_forecast else None,
                observations_used=spend_forecast.observations_used if spend_forecast else 0,
                missing_observations=spend_forecast.missing_observations if spend_forecast else 0,
                status=spend_forecast.status if spend_forecast else "unavailable",
                reason=spend_forecast.reason if spend_forecast else "no_forecast",
                currency=business.currency,
                source="advertising",
            )
            if spend_forecast is not None
            else None,
            engine.BudgetView(budget=goal.ad_budget, currency=business.currency),
        )
        budget_comparison = BudgetComparisonRead(**result)

    return ForecastSummaryRead(
        business_id=business.id,
        currency=business.currency,
        timezone=business.timezone,
        horizon_days=horizon_days,
        forecast_start=persisted[0].forecast_start if persisted else today,
        forecast_end=persisted[0].forecast_end if persisted else today,
        training_start=persisted[0].training_start if persisted else today,
        training_end=persisted[0].training_end if persisted else today,
        confidence_level=Decimal("0.80"),
        metrics=forecasts,
        goals=goals_view,
        budget=budget_comparison,
        scenario_totals=scenario_totals,
    )


async def generate(
    session: AsyncSession,
    business: Business,
    *,
    request: ForecastGenerateRequest,
    settings: Settings,
) -> list[Forecast]:
    """Generate forecasts synchronously and persist them (idempotent)."""
    _validate_request(
        entity_type=request.entity_type,
        metric_code=request.metric_code,
        horizon_days=request.horizon_days,
        confidence_level=request.confidence_level,
    )

    if request.entity_type == ENTITY_TYPE_CAMPAIGN and request.entity_id is not None:
        await _validate_campaign_ownership(session, business.id, request.entity_id)

    today = business_today(business)

    if request.entity_type == ENTITY_TYPE_CAMPAIGN:
        forecasts = await engine.forecast_for_campaign(
            session,
            business,
            request.entity_id,
            today=today,
            horizon_days=request.horizon_days,
            confidence_level=request.confidence_level,
            training_window_days=request.training_window_days,
        )
        org_id = business.organization_id
    else:
        forecasts = await engine.forecast_for_business(
            session,
            business,
            today=today,
            horizon_days=request.horizon_days,
            confidence_level=request.confidence_level,
            training_window_days=request.training_window_days,
        )
        org_id = business.organization_id

    persisted: list[Forecast] = []
    for forecast in forecasts:
        if request.metric_code is not None and forecast.metric_code != request.metric_code:
            continue
        row = await _upsert_forecast(
            session,
            business=business,
            forecast=forecast,
            entity_id=request.entity_id,
            entity_type=request.entity_type,
            organization_id=org_id,
        )
        await _replace_points(
            session, row, scenarios=forecast.scenarios
        )
        persisted.append(row)
    return persisted


async def campaign_forecast(
    session: AsyncSession,
    business: Business,
    campaign_id: uuid.UUID,
    *,
    horizon_days: int,
    settings: Settings,
) -> CampaignForecastRead:
    today = business_today(business)
    persisted = await _list_latest_forecasts(
        session,
        business_id=business.id,
        entity_type=ENTITY_TYPE_CAMPAIGN,
        entity_id=campaign_id,
        horizon_days=horizon_days,
    )
    if not persisted:
        # Auto-generate if no snapshot exists.
        await generate(
            session,
            business,
            request=ForecastGenerateRequest(
                horizon_days=horizon_days,
                entity_type=ENTITY_TYPE_CAMPAIGN,
                entity_id=campaign_id,
            ),
            settings=settings,
        )
        persisted = await _list_latest_forecasts(
            session,
            business_id=business.id,
            entity_type=ENTITY_TYPE_CAMPAIGN,
            entity_id=campaign_id,
            horizon_days=horizon_days,
        )
    by_metric = {f.metric_code: f for f in persisted}

    spend = by_metric.get(METRIC_SPEND)
    purchases = by_metric.get(METRIC_PURCHASES)
    revenue = by_metric.get(METRIC_REVENUE)

    # Derived KPIs (CPA, ROAS) only when both sides exist.
    cpa_value: ForecastValueMoneyRead | None = None
    roas_value: ForecastValueRead | None = None
    if spend is not None and purchases is not None:
        cpa = engine.derived_cpa(
            engine.EngineForecast(
                metric_code=METRIC_SPEND,
                horizon_days=horizon_days,
                forecast_start=spend.forecast_start,
                forecast_end=spend.forecast_end,
                training_start=spend.training_start,
                training_end=spend.training_end,
                model=spend.model,
                confidence_level=spend.confidence_level,
                expected_value=spend.expected_value,
                lower_value=spend.lower_value,
                upper_value=spend.upper_value,
                observations_used=spend.observations_used,
                missing_observations=spend.missing_observations,
                status=spend.status,
                reason=spend.reason,
                currency=spend.currency,
                source=spend.source,
            ),
            engine.EngineForecast(
                metric_code=METRIC_PURCHASES,
                horizon_days=horizon_days,
                forecast_start=purchases.forecast_start,
                forecast_end=purchases.forecast_end,
                training_start=purchases.training_start,
                training_end=purchases.training_end,
                model=purchases.model,
                confidence_level=purchases.confidence_level,
                expected_value=purchases.expected_value,
                lower_value=purchases.lower_value,
                upper_value=purchases.upper_value,
                observations_used=purchases.observations_used,
                missing_observations=purchases.missing_observations,
                status=purchases.status,
                reason=purchases.reason,
                currency=purchases.currency,
                source=purchases.source,
            ),
        )
        if cpa is not None:
            cpa_value = ForecastValueMoneyRead(
                value=cpa.get("value"),
                status="available",
                reason=None,
                currency=business.currency,
                source=spend.source,
            )
    if revenue is not None and spend is not None:
        roas = engine.derived_roas(
            engine.EngineForecast(
                metric_code=METRIC_REVENUE,
                horizon_days=horizon_days,
                forecast_start=revenue.forecast_start,
                forecast_end=revenue.forecast_end,
                training_start=revenue.training_start,
                training_end=revenue.training_end,
                model=revenue.model,
                confidence_level=revenue.confidence_level,
                expected_value=revenue.expected_value,
                lower_value=revenue.lower_value,
                upper_value=revenue.upper_value,
                observations_used=revenue.observations_used,
                missing_observations=revenue.missing_observations,
                status=revenue.status,
                reason=revenue.reason,
                currency=revenue.currency,
                source=revenue.source,
            ),
            engine.EngineForecast(
                metric_code=METRIC_SPEND,
                horizon_days=horizon_days,
                forecast_start=spend.forecast_start,
                forecast_end=spend.forecast_end,
                training_start=spend.training_start,
                training_end=spend.training_end,
                model=spend.model,
                confidence_level=spend.confidence_level,
                expected_value=spend.expected_value,
                lower_value=spend.lower_value,
                upper_value=spend.upper_value,
                observations_used=spend.observations_used,
                missing_observations=spend.missing_observations,
                status=spend.status,
                reason=spend.reason,
                currency=spend.currency,
                source=spend.source,
            ),
        )
        if roas is not None:
            roas_value = ForecastValueRead(
                value=roas.get("value"), status="available", reason=None
            )

    scenarios = _scenario_totals(
        [f for f in (spend, purchases, revenue) if f is not None]
    )

    data_sufficiency = (
        "available"
        if spend and spend.status == FORECAST_STATUS_CURRENT
        else "insufficient_data"
    )
    anchor = spend or purchases or revenue
    return CampaignForecastRead(
        business_id=business.id,
        currency=business.currency,
        timezone=business.timezone,
        campaign_id=campaign_id,
        horizon_days=horizon_days,
        forecast_start=anchor.forecast_start if anchor else today,
        forecast_end=anchor.forecast_end if anchor else today,
        training_start=anchor.training_start if anchor else today,
        training_end=anchor.training_end if anchor else today,
        confidence_level=Decimal("0.80"),
        spend=_to_forecast_read(spend) if spend else None,
        purchases=_to_forecast_read(purchases) if purchases else None,
        revenue=_to_forecast_read(revenue) if revenue else None,
        cpa=cpa_value,
        roas=roas_value,
        data_sufficiency=data_sufficiency,
        break_even_roas=None,
        scenarios=scenarios,
    )


async def get_business_forecasts(
    session: AsyncSession,
    business: Business,
    *,
    horizon_days: int,
    metric_code: str | None = None,
) -> list[ForecastWithPointsRead]:
    rows = await list_business_forecasts(
        session, business, horizon_days=horizon_days
    )
    if metric_code is not None:
        rows = [row for row in rows if row.metric_code == metric_code]
    out: list[ForecastWithPointsRead] = []
    for row in rows:
        point_rows = list(
            await session.scalars(
                select(ForecastPoint)
                .where(ForecastPoint.forecast_id == row.id)
                .order_by(ForecastPoint.date)
            )
        )
        out.append(
            ForecastWithPointsRead(
                **_to_forecast_read(row).model_dump(),
                points=[
                    ForecastPointRead(
                        date=p.date,
                        expected_value=p.expected_value,
                        lower_value=p.lower_value,
                        upper_value=p.upper_value,
                    )
                    for p in point_rows
                ],
            )
        )
    return out


async def get_campaign_forecast_with_points(
    session: AsyncSession,
    business: Business,
    campaign_id: uuid.UUID,
    *,
    horizon_days: int,
) -> list[ForecastWithPointsRead]:
    rows = await _list_latest_forecasts(
        session,
        business_id=business.id,
        entity_type=ENTITY_TYPE_CAMPAIGN,
        entity_id=campaign_id,
        horizon_days=horizon_days,
    )
    out: list[ForecastWithPointsRead] = []
    for row in rows:
        point_rows = list(
            await session.scalars(
                select(ForecastPoint)
                .where(ForecastPoint.forecast_id == row.id)
                .order_by(ForecastPoint.date)
            )
        )
        out.append(
            ForecastWithPointsRead(
                **_to_forecast_read(row).model_dump(),
                points=[
                    ForecastPointRead(
                        date=p.date,
                        expected_value=p.expected_value,
                        lower_value=p.lower_value,
                        upper_value=p.upper_value,
                    )
                    for p in point_rows
                ],
            )
        )
    return out


__all__ = [
    "business_today",
    "campaign_forecast",
    "generate",
    "get_business",
    "get_business_forecasts",
    "get_campaign_forecast_with_points",
    "list_business_forecasts",
    "summary",
]
