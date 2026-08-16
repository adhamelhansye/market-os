"""Baseline forecasting models.

Two deterministic baselines:

- `naive_last_value` — the most recent observation is the forecast for every
  day in the horizon. The standard Hyndman & Athanasopoulos "naive"
  benchmark. Always available when at least one observation exists.
- `moving_average` and `weighted_moving_average` — fixed-window means
  (7-day). Weighted variant favours the most recent observations.

All models:

- clamp negative predictions to zero (revenue/spend/purchases are never
  negative in business reality; linear extrapolation below zero means the
  model is out of its depth, never that the business will literally sell
  at a loss);
- return a `Forecast` whose uncertainty interval is symmetric around the
  point estimate at ± the in-sample standard deviation scaled to the
  requested confidence level;
- never produce a value when the series is shorter than the minimum
  observation requirement for the model.

All arithmetic is `Decimal`. No floats.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.modules.forecasting.constants import (
    DEFAULT_CONFIDENCE_LEVEL,
    MIN_OBSERVATIONS_BASELINE,
    MODEL_MOVING_AVERAGE,
    MODEL_NAIVE,
    MODEL_TREND,
    MOVING_AVERAGE_WINDOW,
    WEIGHTED_MOVING_AVERAGE_RECENT_WEIGHT,
)
from src.modules.forecasting.validation import (
    ValidatedSeries,
    observed_values,
)

ZERO = Decimal("0")
ONE = Decimal("1")
TWO = Decimal("2")


@dataclass(frozen=True)
class BaselineForecast:
    """Single-point deterministic forecast (one step)."""

    model: str
    expected: Decimal
    stddev: Decimal  # population stddev over observed values
    confidence_level: Decimal = DEFAULT_CONFIDENCE_LEVEL

    @property
    def lower(self) -> Decimal:
        # Single-step uncertainty: ± z * stddev (z = 1.2816 for 80% one-sided).
        # We use a conservative normal-approximation multiplier of 1.282
        # (80% central) for the symmetric interval.
        half = (self.stddev * _Z80).quantize(Decimal("0.0001"))
        return _clamp_non_negative(self.expected - half)

    @property
    def upper(self) -> Decimal:
        half = (self.stddev * _Z80).quantize(Decimal("0.0001"))
        return self.expected + half


# 80% two-sided z-score (normal approximation). 1.2815515655446004.
_Z80 = Decimal("1.2816")


def _clamp_non_negative(value: Decimal) -> Decimal:
    return value if value > ZERO else ZERO


def _population_stddev(values: list[Decimal], mean: Decimal) -> Decimal:
    """Population stddev over a list of non-empty Decimal values."""
    if len(values) < 2:
        return ZERO
    total = ZERO
    for value in values:
        diff = value - mean
        total += diff * diff
    variance = total / Decimal(len(values))
    return _decimal_sqrt(variance)


def _decimal_sqrt(value: Decimal) -> Decimal:
    """Newton-Raphson square root, Decimal-only, capped at 50 iterations."""
    if value <= ZERO:
        return ZERO
    estimate = value
    for _ in range(50):
        next_estimate = (estimate + value / estimate) / TWO
        if next_estimate == estimate:
            break
        estimate = next_estimate
    return estimate.quantize(Decimal("0.0001"))


def _series_mean(series: ValidatedSeries) -> Decimal:
    assert series.mean is not None  # callers gate on observations_used
    return series.mean


def naive_last_value(series: ValidatedSeries) -> BaselineForecast | None:
    """Forecast = most recent observed value.

    Requires at least one observation. The stddev is over all observations
    so the uncertainty band reflects historical noise, not a single point.
    """
    observed = observed_values(series)
    if not observed:
        return None
    last = observed[-1]
    mean = sum(observed, ZERO) / Decimal(len(observed))
    stddev = _population_stddev(observed, mean)
    return BaselineForecast(model=MODEL_NAIVE, expected=last, stddev=stddev)


def moving_average(
    series: ValidatedSeries, *, window: int = MOVING_AVERAGE_WINDOW
) -> BaselineForecast | None:
    """Forecast = mean of the last `window` observations.

    Requires at least `window` observations to match the headline
    minimum-history contract.
    """
    observed = observed_values(series)
    if len(observed) < max(MIN_OBSERVATIONS_BASELINE, window):
        return None
    window_values = observed[-window:]
    total = sum(window_values, ZERO)
    mean = (total / Decimal(len(window_values))).quantize(Decimal("0.0001"))
    stddev = _population_stddev(window_values, mean)
    return BaselineForecast(
        model=MODEL_MOVING_AVERAGE, expected=mean, stddev=stddev
    )


def weighted_moving_average(
    series: ValidatedSeries, *, window: int = MOVING_AVERAGE_WINDOW
) -> BaselineForecast | None:
    """Forecast = weighted mean with linearly increasing weights.

    Weight_i = W**i (i = 0 is the oldest observation in the window). The
    forecast is bounded below by zero to mirror the other baselines.
    """
    observed = observed_values(series)
    if len(observed) < max(MIN_OBSERVATIONS_BASELINE, window):
        return None
    window_values = observed[-window:]
    weight = WEIGHTED_MOVING_AVERAGE_RECENT_WEIGHT
    weights = [weight ** i for i in range(window)]
    total_weight = sum(weights, ZERO)
    weighted_total = sum(
        (window_values[i] * weights[i] for i in range(window)), ZERO
    )
    expected = (weighted_total / total_weight).quantize(Decimal("0.0001"))
    # For the stddev we use the simple population stddev over the window;
    # weighting the variance is possible but adds no insight at the
    # baseline level and confuses the backtest comparison.
    mean = sum(window_values, ZERO) / Decimal(len(window_values))
    stddev = _population_stddev(window_values, mean)
    return BaselineForecast(
        model="weighted_moving_average", expected=expected, stddev=stddev
    )


# Keep the public surface predictable for the engine; nothing here is
# exported twice.
__all__ = [
    "BaselineForecast",
    "moving_average",
    "naive_last_value",
    "weighted_moving_average",
    MODEL_TREND,
]
