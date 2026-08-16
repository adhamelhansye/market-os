"""Deterministic forecasting engine (Phase 4A).

The engine is the single source of forecast math. It:

1. Loads canonical daily metrics for a business (and optionally an entity).
2. Materialises a dense training series (gaps are explicitly identified).
3. Gates on the minimum-history contract.
4. Backtests every available candidate model on the same holdout window.
5. Selects the best model by sMAPE (tie-break by MAE).
6. Builds Best / Expected / Worst scenarios for the horizon from the
   selected model's residual uncertainty.
7. Compares the forecast against goals and budget when configured.
8. Returns a serialisable forecast snapshot for the service layer.

The engine never queries provider APIs, never asks an LLM for numbers,
never performs an autonomous action. It only consumes canonical
metric_facts (Phase 3A) and the configured unit-economics profile
(Phase 1).

Multi-currency: the engine only aggregates metrics within the business's
configured currency; rows in other currencies are excluded by the
underlying aggregation layer (`metric_facts` already does this).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from src.db.models import Business
from src.modules.economics.service import summary_data
from src.modules.forecasting.backtesting import (
    BacktestResult,
    backtest,
    best,
)
from src.modules.forecasting.constants import (
    ALL_METRIC_CODES,
    ALLOWED_HORIZON_DAYS,
    DEFAULT_CONFIDENCE_LEVEL,
    ENTITY_TYPE_BUSINESS,
    ENTITY_TYPE_CAMPAIGN,
    FORECAST_STATUS_CURRENT,
    FORECAST_STATUS_INSUFFICIENT_DATA,
    METRIC_CONTRIBUTION_PROFIT,
    METRIC_PURCHASES,
    METRIC_REVENUE,
    METRIC_SPEND,
    MIN_OBSERVATIONS_BASELINE,
    MODEL_MOVING_AVERAGE,
    MODEL_NAIVE,
    MODEL_SEASONAL,
    MODEL_TREND,
    SOURCE_ADVERTISING,
    SOURCE_COMMERCE,
    SOURCE_ECONOMICS,
)
from src.modules.forecasting.errors import (
    ForecastingFilterError,
    ForecastingInputError,
)
from src.modules.forecasting.models.baseline import (
    BaselineForecast,
    moving_average,
    naive_last_value,
    weighted_moving_average,
)
from src.modules.forecasting.models.seasonality import fit_seasonal
from src.modules.forecasting.models.trend import fit_trend
from src.modules.forecasting.scenarios import (
    ScenarioSet,
    build_scenarios,
    build_trend_scenarios,
)
from src.modules.forecasting.validation import ValidatedSeries, dense_series
from src.modules.metrics.aggregation import (
    Range,
    ad_timeseries,
    campaign_timeseries,
    commerce_timeseries,
)

ZERO = Decimal("0")
ONE = Decimal("1")
TWO = Decimal("2")
TWO_HUNDRED = Decimal("200")
MAX_TRAINING_WINDOW_DAYS = 180


# ---------------------------------------------------------------------------
# Range helpers
# ---------------------------------------------------------------------------


def _resolve_horizon(horizon_days: int) -> int:
    if horizon_days not in ALLOWED_HORIZON_DAYS:
        raise ForecastingFilterError(
            f"Unsupported horizon_days: {horizon_days}. "
            f"Allowed: {sorted(ALLOWED_HORIZON_DAYS)}"
        )
    return horizon_days


def _resolve_training_window(
    timezone_now: date,
    *,
    horizon_days: int,
    training_window_days: int | None,
) -> Range:
    """Compute the training window (inclusive on both ends).

    The training window ends *the day before* the forecast start, so the
    engine never peeks at future data. The forecast starts at `today`
    (resolved in the business timezone) and runs for `horizon_days`.
    """
    forecast_start = timezone_now
    training_end = forecast_start - timedelta(days=1)
    if training_window_days is None:
        window = max(MIN_OBSERVATIONS_BASELINE * 4, horizon_days * 3, 60)
    else:
        if training_window_days <= 0:
            raise ForecastingInputError("training_window_days must be positive")
        window = min(training_window_days, MAX_TRAINING_WINDOW_DAYS)
    training_start = training_end - timedelta(days=window - 1)
    return Range(
        kind="custom",
        start=training_start,
        end=training_end,
        previous_start=None,
        previous_end=None,
    )


# ---------------------------------------------------------------------------
# Time-series loaders
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetricBundle:
    """The four metric series the engine needs for one forecast scope."""

    revenue: ValidatedSeries
    spend: ValidatedSeries
    purchases: ValidatedSeries

    @property
    def has_any(self) -> bool:
        return any(
            series.observations_used > 0
            for series in (self.revenue, self.spend, self.purchases)
        )

    def for_metric(self, metric_code: str) -> ValidatedSeries:
        if metric_code == METRIC_REVENUE:
            return self.revenue
        if metric_code == METRIC_SPEND:
            return self.spend
        if metric_code == METRIC_PURCHASES:
            return self.purchases
        raise ForecastingFilterError(f"Unsupported metric_code: {metric_code}")


async def load_metric_bundle(
    session,
    business: Business,
    *,
    training: Range,
    campaign_id: uuid.UUID | None = None,
) -> MetricBundle:
    """Pull canonical daily series for revenue / spend / purchases."""
    if campaign_id is not None:
        ad_series = await campaign_timeseries(
            session, business.id, training, currency=business.currency, campaign_id=campaign_id
        )
    else:
        ad_series = await ad_timeseries(
            session, business.id, training, currency=business.currency
        )
    commerce_series = await commerce_timeseries(
        session, business.id, training, currency=business.currency
    )

    return MetricBundle(
        revenue=dense_series(
            [(row["date"], row.get("revenue")) for row in commerce_series],
            start=training.start,
            end=training.end,
        ),
        spend=dense_series(
            [(row["date"], row.get("spend")) for row in ad_series],
            start=training.start,
            end=training.end,
        ),
        purchases=dense_series(
            [(row["date"], row.get("purchases")) for row in commerce_series],
            start=training.start,
            end=training.end,
        ),
    )


# ---------------------------------------------------------------------------
# Forecast result (engine-level)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EngineForecast:
    metric_code: str
    horizon_days: int
    forecast_start: date
    forecast_end: date
    training_start: date
    training_end: date
    model: str
    confidence_level: Decimal
    expected_value: Decimal | None
    lower_value: Decimal | None
    upper_value: Decimal | None
    observations_used: int
    missing_observations: int
    status: str
    reason: str | None
    scenarios: ScenarioSet | None = None
    backtest: BacktestResult | None = None
    currency: str = "USD"
    source: str = SOURCE_COMMERCE

    def to_transport(self) -> dict:
        """Plain-dict transport view (mirrors ForecastRead)."""
        return {
            "metric_code": self.metric_code,
            "horizon_days": self.horizon_days,
            "forecast_start": self.forecast_start,
            "forecast_end": self.forecast_end,
            "training_start": self.training_start,
            "training_end": self.training_end,
            "model": self.model,
            "model_version": "1.0.0",
            "confidence_level": self.confidence_level,
            "expected_value": self.expected_value,
            "lower_value": self.lower_value,
            "upper_value": self.upper_value,
            "observations_used": self.observations_used,
            "missing_observations": self.missing_observations,
            "backtest_mae": self.backtest.mae if self.backtest else None,
            "backtest_smape": self.backtest.smape if self.backtest else None,
            "status": self.status,
            "reason": self.reason,
            "currency": self.currency,
            "source": self.source,
        }


# ---------------------------------------------------------------------------
# Single-metric forecast pipeline
# ---------------------------------------------------------------------------


def _forecast_dates(today: date, horizon_days: int) -> list[date]:
    return [today + timedelta(days=offset) for offset in range(horizon_days)]


def _scenario_for_model(
    *,
    model: str,
    series: ValidatedSeries,
    training_start: date,
    dates: list[date],
    confidence_level: Decimal,
) -> tuple[ScenarioSet, BacktestResult | None]:
    """Run the backtest, pick the winner, then build scenarios for the horizon."""
    results = backtest(series, training_start=training_start)
    winner = best(results)
    if winner is None:
        # Insufficient data even for the backtest: refuse.
        raise ForecastingInputError("insufficient data for forecasting")

    if winner.model == MODEL_NAIVE:
        fit = naive_last_value(series)
    elif winner.model == MODEL_MOVING_AVERAGE:
        fit = moving_average(series)
    elif winner.model == "weighted_moving_average":
        fit = weighted_moving_average(series)
    elif winner.model == MODEL_TREND:
        fit = fit_trend(series, training_start=training_start)
        if fit is None:
            # Fallback to baseline when trend refuses to fit.
            fit = moving_average(series)
    elif winner.model == MODEL_SEASONAL:
        fit = fit_seasonal(series)
        if fit is None:
            fit = moving_average(series)
    else:
        fit = moving_average(series)

    if fit is None:
        raise ForecastingInputError("no model could be fitted on the series")

    if isinstance(fit, BaselineForecast):
        scenarios = build_scenarios(
            dates,
            expected_per_day=fit.expected,
            stddev=fit.stddev,
            confidence_level=confidence_level,
        )
    else:
        # Trend model: per-day forecast via slope/intercept.
        scenarios = build_trend_scenarios(
            dates,
            intercept=fit.intercept,
            slope=fit.slope,
            residual_stddev=fit.residual_stddev,
            confidence_level=confidence_level,
            training_start=training_start,
        )

    return scenarios, winner


def _forecast_metric(
    *,
    metric_code: str,
    series: ValidatedSeries,
    training_start: date,
    today: date,
    horizon_days: int,
    confidence_level: Decimal,
    currency: str,
    source: str,
) -> EngineForecast:
    forecast_end = today + timedelta(days=horizon_days - 1)
    training_end = series.points[-1].date if series.points else training_start

    if not series.is_sufficient:
        return EngineForecast(
            metric_code=metric_code,
            horizon_days=horizon_days,
            forecast_start=today,
            forecast_end=forecast_end,
            training_start=training_start,
            training_end=training_end,
            model=MODEL_NAIVE,
            confidence_level=confidence_level,
            expected_value=None,
            lower_value=None,
            upper_value=None,
            observations_used=series.observations_used,
            missing_observations=series.missing_observations,
            status=FORECAST_STATUS_INSUFFICIENT_DATA,
            reason="insufficient_history",
            scenarios=None,
            backtest=None,
            currency=currency,
            source=source,
        )

    try:
        scenarios, winner = _scenario_for_model(
            model="",
            series=series,
            training_start=training_start,
            dates=_forecast_dates(today, horizon_days),
            confidence_level=confidence_level,
        )
    except ForecastingInputError:
        return EngineForecast(
            metric_code=metric_code,
            horizon_days=horizon_days,
            forecast_start=today,
            forecast_end=forecast_end,
            training_start=training_start,
            training_end=training_end,
            model=MODEL_NAIVE,
            confidence_level=confidence_level,
            expected_value=None,
            lower_value=None,
            upper_value=None,
            observations_used=series.observations_used,
            missing_observations=series.missing_observations,
            status=FORECAST_STATUS_INSUFFICIENT_DATA,
            reason="no_model",
            scenarios=None,
            backtest=None,
            currency=currency,
            source=source,
        )

    return EngineForecast(
        metric_code=metric_code,
        horizon_days=horizon_days,
        forecast_start=today,
        forecast_end=forecast_end,
        training_start=training_start,
        training_end=training_end,
        model=winner.model,
        confidence_level=confidence_level,
        expected_value=scenarios.total_expected,
        lower_value=scenarios.total_lower,
        upper_value=scenarios.total_upper,
        observations_used=series.observations_used,
        missing_observations=series.missing_observations,
        status=FORECAST_STATUS_CURRENT,
        reason=None,
        scenarios=scenarios,
        backtest=winner,
        currency=currency,
        source=source,
    )


# ---------------------------------------------------------------------------
# Public forecast entry points
# ---------------------------------------------------------------------------


async def forecast_for_business(
    session,
    business: Business,
    *,
    today: date,
    horizon_days: int,
    confidence_level: Decimal = DEFAULT_CONFIDENCE_LEVEL,
    training_window_days: int | None = None,
) -> list[EngineForecast]:
    """Forecast the four business metrics in one pass."""
    horizon_days = _resolve_horizon(horizon_days)
    training = _resolve_training_window(
        today, horizon_days=horizon_days, training_window_days=training_window_days
    )
    bundle = await load_metric_bundle(session, business, training=training)
    metrics: list[EngineForecast] = [
        _forecast_metric(
            metric_code=METRIC_REVENUE,
            series=bundle.revenue,
            training_start=training.start,
            today=today,
            horizon_days=horizon_days,
            confidence_level=confidence_level,
            currency=business.currency,
            source=SOURCE_COMMERCE,
        ),
        _forecast_metric(
            metric_code=METRIC_SPEND,
            series=bundle.spend,
            training_start=training.start,
            today=today,
            horizon_days=horizon_days,
            confidence_level=confidence_level,
            currency=business.currency,
            source=SOURCE_ADVERTISING,
        ),
        _forecast_metric(
            metric_code=METRIC_PURCHASES,
            series=bundle.purchases,
            training_start=training.start,
            today=today,
            horizon_days=horizon_days,
            confidence_level=confidence_level,
            currency=business.currency,
            source=SOURCE_COMMERCE,
        ),
    ]
    metrics.append(
        await _forecast_profit(
            session,
            business,
            revenue_forecast=metrics[0],
            spend_forecast=metrics[1],
            purchases_forecast=metrics[2],
            today=today,
            horizon_days=horizon_days,
            confidence_level=confidence_level,
            training_window_days=training_window_days,
            training_start=training.start,
        )
    )
    return metrics


async def forecast_for_campaign(
    session,
    business: Business,
    campaign_id: uuid.UUID,
    *,
    today: date,
    horizon_days: int,
    confidence_level: Decimal = DEFAULT_CONFIDENCE_LEVEL,
    training_window_days: int | None = None,
) -> list[EngineForecast]:
    """Forecast spend + purchases + (optionally) revenue for one campaign."""
    horizon_days = _resolve_horizon(horizon_days)
    training = _resolve_training_window(
        today, horizon_days=horizon_days, training_window_days=training_window_days
    )
    bundle = await load_metric_bundle(
        session, business, training=training, campaign_id=campaign_id
    )

    metrics: list[EngineForecast] = []
    metrics.append(
        _forecast_metric(
            metric_code=METRIC_SPEND,
            series=bundle.spend,
            training_start=training.start,
            today=today,
            horizon_days=horizon_days,
            confidence_level=confidence_level,
            currency=business.currency,
            source=SOURCE_ADVERTISING,
        )
    )
    metrics.append(
        _forecast_metric(
            metric_code=METRIC_PURCHASES,
            series=bundle.purchases,
            training_start=training.start,
            today=today,
            horizon_days=horizon_days,
            confidence_level=confidence_level,
            currency=business.currency,
            source=SOURCE_COMMERCE,
        )
    )
    # Revenue at the campaign grain requires Meta-reported attributed
    # conversion_value: we surface it ONLY when the campaign has a
    # dedicated revenue column. In the canonical layer that's
    # conversion_value from Meta. We deliberately do NOT use commerce
    # revenue here (see forecasting.md §19).
    campaign_revenue_series = await _campaign_revenue_series(
        session, business, training=training, campaign_id=campaign_id
    )
    if campaign_revenue_series is not None:
        metrics.append(
            _forecast_metric(
                metric_code=METRIC_REVENUE,
                series=campaign_revenue_series,
                training_start=training.start,
                today=today,
                horizon_days=horizon_days,
                confidence_level=confidence_level,
                currency=business.currency,
                source=SOURCE_ADVERTISING,
            )
        )
    return metrics


async def _campaign_revenue_series(
    session,
    business: Business,
    *,
    training: Range,
    campaign_id: uuid.UUID,
) -> ValidatedSeries | None:
    """Return a Meta-attributed campaign revenue series when present.

    The Phase 3A view exposes `conversion_value` per ad insight. We
    sum it per day for the campaign; if every observation is None we
    return None so the campaign forecast surfaces
    `revenue.status=unavailable`.
    """
    from sqlalchemy import func, select

    from src.modules.metrics.aggregation import metric_facts
    from src.modules.metrics.models import F

    stmt = (
        select(
            F["date"].label("date"),
            func.coalesce(func.sum(F["conversion_value"]), ZERO).label("revenue"),
        )
        .select_from(metric_facts)
        .where(
            F["business_id"] == business.id,
            F["grain"] == "ad",
            F["campaign_id"] == campaign_id,
            F["date"] >= training.start,
            F["date"] <= training.end,
            F["currency"] == business.currency,
        )
        .group_by(F["date"])
        .order_by(F["date"])
    )
    rows = (await session.execute(stmt)).all()
    raw = [(row.date, row.revenue) for row in rows]
    series = dense_series(raw, start=training.start, end=training.end)
    if series.observations_used == 0:
        return None
    return series


async def _forecast_profit(
    session,
    business: Business,
    *,
    revenue_forecast: EngineForecast,
    spend_forecast: EngineForecast,
    purchases_forecast: EngineForecast,
    today: date,
    horizon_days: int,
    confidence_level: Decimal,
    training_window_days: int | None,
    training_start: date,
) -> EngineForecast:
    """Derive contribution profit forecast from revenue + economics.

    Phase 1 already owns the unit-economics calculator; the engine never
    recomputes per-unit profit. Profit is `avg_contribution_profit ×
    forecast_purchases`. If either input is unavailable we surface
    `status=unavailable` instead of inventing a number.
    """
    profile = await summary_data(session, business)
    avg_unit_profit = profile.get("average_contribution_profit")

    forecast_end = today + timedelta(days=horizon_days - 1)
    if (
        avg_unit_profit is None
        or revenue_forecast.expected_value is None
        or purchases_forecast.expected_value is None
    ):
        return EngineForecast(
            metric_code=METRIC_CONTRIBUTION_PROFIT,
            horizon_days=horizon_days,
            forecast_start=today,
            forecast_end=forecast_end,
            training_start=training_start,
            training_end=revenue_forecast.training_end,
            model=MODEL_NAIVE,
            confidence_level=confidence_level,
            expected_value=None,
            lower_value=None,
            upper_value=None,
            observations_used=purchases_forecast.observations_used,
            missing_observations=purchases_forecast.missing_observations,
            status="unavailable",
            reason=(
                "missing_economics"
                if avg_unit_profit is None
                else "missing_revenue_or_purchases"
            ),
            scenarios=None,
            backtest=None,
            currency=business.currency,
            source=SOURCE_ECONOMICS,
        )

    expected = (
        avg_unit_profit * Decimal(str(purchases_forecast.expected_value))
    ).quantize(Decimal("0.01"))
    # Symmetric uncertainty: scale the purchases uncertainty by the
    # per-unit profit.
    lower = (
        avg_unit_profit * Decimal(str(purchases_forecast.lower_value or ZERO))
    ).quantize(Decimal("0.01"))
    upper = (
        avg_unit_profit * Decimal(str(purchases_forecast.upper_value or ZERO))
    ).quantize(Decimal("0.01"))

    return EngineForecast(
        metric_code=METRIC_CONTRIBUTION_PROFIT,
        horizon_days=horizon_days,
        forecast_start=today,
        forecast_end=forecast_end,
        training_start=training_start,
        training_end=revenue_forecast.training_end,
        model="profit_derived",
        confidence_level=confidence_level,
        expected_value=expected,
        lower_value=lower,
        upper_value=upper,
        observations_used=purchases_forecast.observations_used,
        missing_observations=purchases_forecast.missing_observations,
        status=FORECAST_STATUS_CURRENT,
        reason=None,
        scenarios=None,
        backtest=None,
        currency=business.currency,
        source=SOURCE_ECONOMICS,
    )


# ---------------------------------------------------------------------------
# Derived KPIs
# ---------------------------------------------------------------------------


def derived_cpa(spend: EngineForecast, purchases: EngineForecast) -> dict | None:
    """Return forecast CPA when both spend and purchases are available."""
    if (
        spend.expected_value is None
        or purchases.expected_value is None
        or Decimal(str(purchases.expected_value)) == ZERO
    ):
        return None
    expected = (
        Decimal(str(spend.expected_value)) / Decimal(str(purchases.expected_value))
    ).quantize(Decimal("0.0001"))
    lower = (
        Decimal(str(spend.lower_value or ZERO))
        / Decimal(str(purchases.upper_value or ZERO))
        if (purchases.upper_value or ZERO) > ZERO
        else ZERO
    ).quantize(Decimal("0.0001"))
    upper = (
        Decimal(str(spend.upper_value or ZERO))
        / Decimal(str(purchases.lower_value or purchases.expected_value))
    ).quantize(Decimal("0.0001"))
    return {
        "value": expected,
        "lower": lower,
        "upper": upper,
        "status": "available",
        "reason": None,
        "currency": spend.currency,
    }


def derived_aov(revenue: EngineForecast, purchases: EngineForecast) -> dict | None:
    """Return forecast AOV at the business grain only."""
    if (
        revenue.expected_value is None
        or purchases.expected_value is None
        or Decimal(str(purchases.expected_value)) == ZERO
    ):
        return None
    expected = (
        Decimal(str(revenue.expected_value))
        / Decimal(str(purchases.expected_value))
    ).quantize(Decimal("0.0001"))
    return {
        "value": expected,
        "status": "available",
        "reason": None,
        "currency": revenue.currency,
    }


def derived_roas(revenue: EngineForecast, spend: EngineForecast) -> dict | None:
    """Return forecast ROAS only when both numerator and denominator exist."""
    if (
        revenue.expected_value is None
        or spend.expected_value is None
        or Decimal(str(spend.expected_value)) == ZERO
    ):
        return None
    expected = (
        Decimal(str(revenue.expected_value)) / Decimal(str(spend.expected_value))
    ).quantize(Decimal("0.0001"))
    return {
        "value": expected,
        "status": "available",
        "reason": None,
    }


def derived_mer(business_revenue: EngineForecast, business_spend: EngineForecast) -> dict | None:
    """MER at the business grain: commerce revenue / total advertising spend."""
    return derived_roas(business_revenue, business_spend)


def derived_contribution_margin(profit: EngineForecast, revenue: EngineForecast) -> dict | None:
    if (
        profit.expected_value is None
        or revenue.expected_value is None
        or Decimal(str(revenue.expected_value)) == ZERO
    ):
        return None
    expected = (
        Decimal(str(profit.expected_value)) / Decimal(str(revenue.expected_value))
    ).quantize(Decimal("0.0001"))
    return {"value": expected, "status": "available", "reason": None}


# ---------------------------------------------------------------------------
# Goal / budget comparisons
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GoalView:
    metric_code: str
    target_value: Decimal | None
    target_currency: str | None


@dataclass(frozen=True)
class BudgetView:
    budget: Decimal | None
    currency: str | None


def compare_to_goal(
    forecast: EngineForecast, goal: GoalView | None
) -> dict:
    """Compare a forecast against a goal. Stable shape, no fabrication."""
    if goal is None or goal.target_value is None:
        return {
            "metric_code": forecast.metric_code,
            "target_value": None,
            "forecast_value": forecast.expected_value,
            "gap": None,
            "gap_percent": None,
            "status": "unavailable",
            "reason": "no_target",
        }
    if forecast.expected_value is None:
        return {
            "metric_code": forecast.metric_code,
            "target_value": goal.target_value,
            "forecast_value": None,
            "gap": None,
            "gap_percent": None,
            "status": "unavailable",
            "reason": forecast.reason or "insufficient_forecast",
        }
    forecast_value = Decimal(str(forecast.expected_value))
    target_value = Decimal(str(goal.target_value))
    gap = forecast_value - target_value
    if target_value > ZERO:
        gap_percent = (
            (gap / target_value).quantize(Decimal("0.0001")) * TWO_HUNDRED
        )
    else:
        gap_percent = None
    status = "above_target" if forecast_value >= target_value else "below_target"
    return {
        "metric_code": forecast.metric_code,
        "target_value": target_value,
        "forecast_value": forecast_value,
        "gap": gap.quantize(Decimal("0.0001")),
        "gap_percent": gap_percent,
        "status": status,
        "reason": None,
    }


def compare_to_budget(
    spend_forecast: EngineForecast, budget: BudgetView | None
) -> dict:
    if budget is None or budget.budget is None:
        return {
            "budget": None,
            "forecast_spend": spend_forecast.expected_value,
            "utilization_percent": None,
            "remaining": None,
            "overrun": False,
            "status": "unavailable",
            "reason": "no_budget",
        }
    if spend_forecast.expected_value is None:
        return {
            "budget": budget.budget,
            "forecast_spend": None,
            "utilization_percent": None,
            "remaining": None,
            "overrun": False,
            "status": "unavailable",
            "reason": spend_forecast.reason or "insufficient_forecast",
        }
    forecast_value = Decimal(str(spend_forecast.expected_value))
    budget_value = Decimal(str(budget.budget))
    utilization = (
        (forecast_value / budget_value).quantize(Decimal("0.0001")) * TWO_HUNDRED
        if budget_value > ZERO
        else None
    )
    remaining = (budget_value - forecast_value).quantize(Decimal("0.0001"))
    return {
        "budget": budget_value,
        "forecast_spend": forecast_value,
        "utilization_percent": utilization,
        "remaining": remaining,
        "overrun": forecast_value > budget_value,
        "status": "overrun" if forecast_value > budget_value else "within_budget",
        "reason": None,
    }


__all__ = [
    "ALLOWED_HORIZON_DAYS",
    "ALL_METRIC_CODES",
    "BacktestResult",
    "BudgetView",
    "DEFAULT_CONFIDENCE_LEVEL",
    "EngineForecast",
    "ENTITY_TYPE_BUSINESS",
    "ENTITY_TYPE_CAMPAIGN",
    "GoalView",
    "METRIC_CONTRIBUTION_PROFIT",
    "METRIC_PURCHASES",
    "METRIC_REVENUE",
    "METRIC_SPEND",
    "MAX_TRAINING_WINDOW_DAYS",
    "MetricBundle",
    "ScenarioSet",
    "compare_to_budget",
    "compare_to_goal",
    "derived_aov",
    "derived_contribution_margin",
    "derived_cpa",
    "derived_mer",
    "derived_roas",
    "forecast_for_business",
    "forecast_for_campaign",
    "load_metric_bundle",
]
