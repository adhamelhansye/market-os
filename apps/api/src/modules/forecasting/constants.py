"""Constants for the deterministic forecasting engine (Phase 4A).

All numbers are deliberately conservative: the engine prefers to admit
insufficient_data over producing a misleading forecast. Thresholds live here
so they are easy to audit and easy to tune without touching rule code.
"""

from __future__ import annotations

from decimal import Decimal

# -- Model registry ---------------------------------------------------------

MODEL_NAIVE = "naive"
MODEL_MOVING_AVERAGE = "moving_average"
MODEL_TREND = "trend"
MODEL_SEASONAL = "seasonal"

MODEL_VERSIONS: dict[str, str] = {
    MODEL_NAIVE: "1.0.0",
    MODEL_MOVING_AVERAGE: "1.0.0",
    MODEL_TREND: "1.0.0",
    MODEL_SEASONAL: "1.0.0",
}

ALL_MODELS: tuple[str, ...] = (
    MODEL_NAIVE,
    MODEL_MOVING_AVERAGE,
    MODEL_TREND,
    MODEL_SEASONAL,
)

# -- Minimum history requirements -------------------------------------------
#
# Below MIN_OBSERVATIONS_INSUFFICIENT the engine emits insufficient_data: there
# is no honest forecast we can compute. The bracketed bands drive model
# selection: as history grows we may graduate to richer models; the engine
# always backtests the candidates it considers and keeps the best, never
# silently picks the most complex.

MIN_OBSERVATIONS_INSUFFICIENT = 7
MIN_OBSERVATIONS_BASELINE = 7
MIN_OBSERVATIONS_TREND = 14
MIN_OBSERVATIONS_SEASONAL = 28

# 7-day moving average window for the moving-average / weighted-moving-average
# baseline. Linear weights favour the recent week.
MOVING_AVERAGE_WINDOW = 7

# Weight given to the most recent observation in the weighted moving average.
# Total weight is normalised over a 7-day window: weight_i = W**i.
WEIGHTED_MOVING_AVERAGE_RECENT_WEIGHT = Decimal("1.5")

# Linear-regression trend model uses two-sided residuals to derive the
# uncertainty interval. We refuse to fit when residuals are degenerate
# (no variance): the engine then falls back to the baseline.
TREND_RESIDUAL_EPSILON = Decimal("0.0001")

# -- Confidence ------------------------------------------------------------

DEFAULT_CONFIDENCE_LEVEL = Decimal("0.80")

# -- Horizon / freshness ---------------------------------------------------

ALLOWED_HORIZON_DAYS: tuple[int, ...] = (7, 14, 30, 60, 90)

# A persisted forecast is considered stale when its training window ends
# before the freshness cutoff. The default is a single business day, which
# matches the daily granularity of canonical metric_facts.
DEFAULT_STALE_AFTER_DAYS = 1

# -- Backtesting -----------------------------------------------------------

BACKTEST_MIN_OBSERVATIONS = 14
BACKTEST_WINDOW_FRACTION = Decimal("0.30")  # hold out the last 30% of history
BACKTEST_MIN_HOLDOUT = 7
BACKTEST_MAX_HOLDOUT = 30

# -- Forecast status (lifecycle) ------------------------------------------

FORECAST_STATUS_CURRENT = "current"
FORECAST_STATUS_STALE = "stale"
FORECAST_STATUS_INSUFFICIENT_DATA = "insufficient_data"
FORECAST_STATUS_FAILED = "failed"


# -- Metric codes ----------------------------------------------------------

METRIC_REVENUE = "revenue"
METRIC_SPEND = "spend"
METRIC_PURCHASES = "purchases"
METRIC_CONTRIBUTION_PROFIT = "contribution_profit"

ALL_METRIC_CODES: tuple[str, ...] = (
    METRIC_REVENUE,
    METRIC_SPEND,
    METRIC_PURCHASES,
    METRIC_CONTRIBUTION_PROFIT,
)

# -- Entity types ----------------------------------------------------------

ENTITY_TYPE_BUSINESS = "business"
ENTITY_TYPE_CAMPAIGN = "campaign"

ALL_ENTITY_TYPES: tuple[str, ...] = (ENTITY_TYPE_BUSINESS, ENTITY_TYPE_CAMPAIGN)

# -- Sources (revenue label, mirrors Phase 3A) -----------------------------

SOURCE_COMMERCE = "commerce"
SOURCE_ADVERTISING = "advertising"
SOURCE_ECONOMICS = "economics"


__all__ = [
    "ALLOWED_HORIZON_DAYS",
    "ALL_ENTITY_TYPES",
    "ALL_METRIC_CODES",
    "ALL_MODELS",
    "BACKTEST_MAX_HOLDOUT",
    "BACKTEST_MIN_HOLDOUT",
    "BACKTEST_MIN_OBSERVATIONS",
    "BACKTEST_WINDOW_FRACTION",
    "DEFAULT_CONFIDENCE_LEVEL",
    "DEFAULT_STALE_AFTER_DAYS",
    "ENTITY_TYPE_BUSINESS",
    "ENTITY_TYPE_CAMPAIGN",
    "FORECAST_STATUS_CURRENT",
    "FORECAST_STATUS_FAILED",
    "FORECAST_STATUS_INSUFFICIENT_DATA",
    "FORECAST_STATUS_STALE",
    "METRIC_CONTRIBUTION_PROFIT",
    "METRIC_PURCHASES",
    "METRIC_REVENUE",
    "METRIC_SPEND",
    "MIN_OBSERVATIONS_BASELINE",
    "MIN_OBSERVATIONS_INSUFFICIENT",
    "MIN_OBSERVATIONS_SEASONAL",
    "MIN_OBSERVATIONS_TREND",
    "MODEL_MOVING_AVERAGE",
    "MODEL_NAIVE",
    "MODEL_SEASONAL",
    "MODEL_TREND",
    "MODEL_VERSIONS",
    "MOVING_AVERAGE_WINDOW",
    "SOURCE_ADVERTISING",
    "SOURCE_COMMERCE",
    "SOURCE_ECONOMICS",
    "TREND_RESIDUAL_EPSILON",
    "WEIGHTED_MOVING_AVERAGE_RECENT_WEIGHT",
]
