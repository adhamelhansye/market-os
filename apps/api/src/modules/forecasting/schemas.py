"""Typed API contracts for the deterministic forecasting engine.

All forecasts are read-only views of the deterministic statistical
pipeline:

- Money is Decimal (serialized as strings by the app encoder). The
  forecast engine never produces a float.
- Confidence intervals carry `(lower, expected, upper)` plus the
  confidence level, the model, the model version, the observations used
  and the backtest error. The interval is always ordered (lower ≤
  expected ≤ upper); if not, the value is marked unavailable.
- Forecasts may be `insufficient_data` or `failed` — the dashboard never
  shows an unavailable forecast as if it were current.
- Goal and budget comparisons are computed by the engine itself; they
  are deterministic and never mutate the goal / budget rows.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from src.modules.metrics.schemas import RangeRead

# -- Forecast measure shapes ------------------------------------------------


class ForecastValueRead(BaseModel):
    value: Decimal | None = None
    status: str = "unavailable"
    reason: str | None = None


class ForecastValueMoneyRead(ForecastValueRead):
    currency: str | None = None
    source: str | None = None


# -- Backtest metadata -----------------------------------------------------


class BacktestRead(BaseModel):
    model: str
    mae: Decimal | None = None
    smape: Decimal | None = None
    holdout_days: int = 0


# -- Forecast point (one day) ---------------------------------------------


class ForecastPointRead(BaseModel):
    date: date
    expected_value: Decimal
    lower_value: Decimal
    upper_value: Decimal


# -- Forecast --------------------------------------------------------------


class ForecastRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    business_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID | None = None
    metric_code: str
    horizon_days: int
    forecast_start: date
    forecast_end: date
    training_start: date
    training_end: date
    model: str
    model_version: str
    confidence_level: Decimal
    expected_value: Decimal | None = None
    lower_value: Decimal | None = None
    upper_value: Decimal | None = None
    observations_used: int
    missing_observations: int
    backtest_mae: Decimal | None = None
    backtest_smape: Decimal | None = None
    status: str
    reason: str | None = None
    currency: str
    source: str
    created_at: datetime
    updated_at: datetime


class ForecastWithPointsRead(ForecastRead):
    points: list[ForecastPointRead] = Field(default_factory=list)


# -- Business summary ------------------------------------------------------


class GoalComparisonRead(BaseModel):
    metric_code: str
    target_value: Decimal | None = None
    forecast_value: Decimal | None = None
    gap: Decimal | None = None
    gap_percent: Decimal | None = None
    status: str = "unavailable"
    reason: str | None = None


class BudgetComparisonRead(BaseModel):
    budget: Decimal | None = None
    forecast_spend: Decimal | None = None
    utilization_percent: Decimal | None = None
    remaining: Decimal | None = None
    overrun: bool = False
    status: str = "unavailable"
    reason: str | None = None


class ForecastSummaryRead(BaseModel):
    business_id: uuid.UUID
    currency: str
    timezone: str
    horizon_days: int
    forecast_start: date
    forecast_end: date
    training_start: date
    training_end: date
    confidence_level: Decimal
    metrics: list[ForecastRead]
    goals: list[GoalComparisonRead] = Field(default_factory=list)
    budget: BudgetComparisonRead | None = None
    scenario_totals: dict[str, ScenarioTotalsRead] = Field(default_factory=dict)


class ScenarioTotalsRead(BaseModel):
    metric_code: str
    expected: Decimal
    lower: Decimal
    upper: Decimal


# -- Campaign forecast -----------------------------------------------------


class CampaignForecastRead(BaseModel):
    business_id: uuid.UUID
    currency: str
    timezone: str
    campaign_id: uuid.UUID
    horizon_days: int
    forecast_start: date
    forecast_end: date
    training_start: date
    training_end: date
    confidence_level: Decimal
    spend: ForecastRead | None = None
    purchases: ForecastRead | None = None
    revenue: ForecastRead | None = None
    cpa: ForecastValueMoneyRead | None = None
    roas: ForecastValueRead | None = None
    data_sufficiency: str = "insufficient_data"
    break_even_roas: ForecastValueRead | None = None
    scenarios: dict[str, ScenarioTotalsRead] = Field(default_factory=dict)


# -- Generate request ------------------------------------------------------


class ForecastGenerateRequest(BaseModel):
    horizon_days: int = Field(
        default=30, description="One of 7, 14, 30, 60 or 90 days."
    )
    entity_type: str = Field(default="business")
    entity_id: uuid.UUID | None = None
    metric_code: str | None = None
    confidence_level: Decimal = Decimal("0.80")
    training_window_days: int | None = Field(
        default=None,
        description="Override the auto-sized training window. Capped at 180.",
    )


# -- Common ----------------------------------------------------------------


class RangeReadWithHorizon(RangeRead):
    horizon_days: int


__all__ = [
    "BacktestRead",
    "BudgetComparisonRead",
    "CampaignForecastRead",
    "ForecastGenerateRequest",
    "ForecastPointRead",
    "ForecastRead",
    "ForecastSummaryRead",
    "ForecastValueMoneyRead",
    "ForecastValueRead",
    "ForecastWithPointsRead",
    "GoalComparisonRead",
    "RangeReadWithHorizon",
    "ScenarioTotalsRead",
]
