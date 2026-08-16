"""Deterministic trend model for the forecasting engine.

A simple ordinary-least-squares fit of `value = a + b*day_index` over the
training window. Slope and intercept are derived from full-Decimal
arithmetic (no floats, no numpy). The forecast is the fitted line
extrapolated forward over the horizon; the uncertainty interval is the
residual standard error scaled to the requested confidence level.

Constraints:

- requires `MIN_OBSERVATIONS_TREND` observations;
- refuses to fit when the residuals are degenerate (no variance left
  after the trend): the engine then falls back to the baseline;
- clamps negative predictions to zero (business reality: never negative
  revenue / spend / purchases);
- never reads future observations.

This is deliberately simple: it is the ceiling of our deterministic
stack. Anything more elaborate would belong to the Simulator phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.modules.forecasting.constants import (
    DEFAULT_CONFIDENCE_LEVEL,
    MIN_OBSERVATIONS_TREND,
    MODEL_TREND,
    TREND_RESIDUAL_EPSILON,
)
from src.modules.forecasting.validation import ValidatedSeries, observed_values

ZERO = Decimal("0")
ONE = Decimal("1")
TWO = Decimal("2")

# 80% two-sided z-score (normal approximation). Matches the baseline.
_Z80 = Decimal("1.2816")


@dataclass(frozen=True)
class TrendForecast:
    model: str = MODEL_TREND
    expected_per_step: Decimal = ZERO  # value at day_index=1 (one step ahead)
    intercept: Decimal = ZERO
    slope: Decimal = ZERO
    residual_stddev: Decimal = ZERO
    confidence_level: Decimal = DEFAULT_CONFIDENCE_LEVEL

    def forecast_for_day(self, day_index: int) -> Decimal:
        """Fit value at day_index = intercept + slope * day_index."""
        if day_index < 1:
            raise ValueError("day_index must be 1 or greater")
        value = self.intercept + self.slope * Decimal(day_index)
        return value if value > ZERO else ZERO

    @property
    def lower(self) -> Decimal:
        half = (self.residual_stddev * _Z80).quantize(Decimal("0.0001"))
        return (
            self.expected_per_step - half
            if self.expected_per_step - half > ZERO
            else ZERO
        )

    @property
    def upper(self) -> Decimal:
        half = (self.residual_stddev * _Z80).quantize(Decimal("0.0001"))
        return self.expected_per_step + half


def _decimal_sqrt(value: Decimal) -> Decimal:
    if value <= ZERO:
        return ZERO
    estimate = value
    for _ in range(50):
        next_estimate = (estimate + value / estimate) / TWO
        if next_estimate == estimate:
            break
        estimate = next_estimate
    return estimate.quantize(Decimal("0.0001"))


def fit_trend(
    series: ValidatedSeries, *, training_start: date
) -> TrendForecast | None:
    """Fit `value = a + b * t` (OLS) over the non-missing observations.

    Returns `None` when the trend cannot be fitted honestly: not enough
    observations, no variance, or degenerate residuals.
    """
    observed = observed_values(series)
    if len(observed) < MIN_OBSERVATIONS_TREND:
        return None

    # day_index = 1 for the first observation (training_start), increments
    # by 1 for every subsequent calendar day (gaps included — the model is
    # honest about how many days passed between observations).
    xs: list[Decimal] = []
    ys: list[Decimal] = []
    day_index = 1
    for point in series.points:
        if point.value is None:
            day_index += 1
            continue
        xs.append(Decimal(day_index))
        ys.append(point.value)
        day_index += 1

    n = Decimal(len(xs))
    if len(xs) < MIN_OBSERVATIONS_TREND:
        return None

    sum_x = sum(xs, ZERO)
    sum_y = sum(ys, ZERO)
    sum_x_sq = sum((x * x for x in xs), ZERO)
    sum_xy = sum((xs[i] * ys[i] for i in range(len(xs))), ZERO)

    denom = n * sum_x_sq - sum_x * sum_x
    if denom == ZERO:
        return None  # degenerate (all observations on the same day_index)

    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n

    # Residual sum of squares — not variance-bias corrected; we use the
    # raw residuals because the engine treats the residual stddev as an
    # honest bound, not a population statistic.
    residual_ss = ZERO
    for i in range(len(xs)):
        fitted = intercept + slope * xs[i]
        residual = ys[i] - fitted
        residual_ss += residual * residual
    if residual_ss <= TREND_RESIDUAL_EPSILON:
        return None

    residual_variance = residual_ss / (n - TWO)
    if residual_variance <= ZERO:
        return None
    residual_stddev = _decimal_sqrt(residual_variance)

    expected_per_step = intercept + slope * ONE
    if expected_per_step < ZERO:
        expected_per_step = ZERO

    return TrendForecast(
        intercept=intercept,
        slope=slope,
        residual_stddev=residual_stddev,
        expected_per_step=expected_per_step,
    )


__all__ = ["TrendForecast", "fit_trend"]
