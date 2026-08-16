"""Seasonality-aware model stub.

The deterministic engine in Phase 4A does not run a full seasonal
decomposition: weekly/monthly seasonality requires far more than
`MIN_OBSERVATIONS_SEASONAL` observations to be statistically honest, and
the Phase 3B diagnostics already gate findings on similar sample sizes.

This module exists so the engine can graduate to the seasonal model as
soon as enough history is available, and so the backtest harness can
select it when appropriate. The implementation is a 7-day weekday
average when at least 4 full weeks are observed:

    forecast[d] = average of observed values whose weekday == d.weekday()

If the average is missing or unstable (zero variance), the engine falls
back to the moving average.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.modules.forecasting.constants import (
    DEFAULT_CONFIDENCE_LEVEL,
    MIN_OBSERVATIONS_SEASONAL,
    MODEL_MOVING_AVERAGE,
    MODEL_SEASONAL,
)
from src.modules.forecasting.validation import ValidatedSeries, observed_values

ZERO = Decimal("0")
ONE = Decimal("1")
SEVEN = 7
FOUR_WEEKS = 28

_Z80 = Decimal("1.2816")  # 80% two-sided normal z-score (matches baselines)


@dataclass(frozen=True)
class SeasonalForecast:
    weekday_expected: tuple[Decimal, ...]  # 7 entries, one per weekday
    weekday_stddev: tuple[Decimal, ...]  # 7 entries, one per weekday
    model: str = MODEL_SEASONAL
    confidence_level: Decimal = DEFAULT_CONFIDENCE_LEVEL

    def expected_for(self, target: date) -> Decimal:
        value = self.weekday_expected[target.weekday()]
        return value if value > ZERO else ZERO

    def lower_for(self, target: date) -> Decimal:
        stddev = self.weekday_stddev[target.weekday()]
        half = (stddev * _Z80).quantize(Decimal("0.0001"))
        expected = self.expected_for(target)
        return expected - half if expected - half > ZERO else ZERO

    def upper_for(self, target: date) -> Decimal:
        stddev = self.weekday_stddev[target.weekday()]
        half = (stddev * _Z80).quantize(Decimal("0.0001"))
        return self.expected_for(target) + half


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


TWO = Decimal("2")


def fit_seasonal(series: ValidatedSeries) -> SeasonalForecast | None:
    """Fit a 7-day weekday profile when ≥4 full weeks are observed.

    Returns `None` when there isn't enough history for a stable weekday
    estimate. The engine then falls back to the moving average.
    """
    observed = observed_values(series)
    if len(observed) < MIN_OBSERVATIONS_SEASONAL:
        return None
    if series.length < FOUR_WEEKS:
        return None

    # Group observed values by weekday.
    buckets: list[list[Decimal]] = [[] for _ in range(SEVEN)]
    for point in series.points:
        if point.value is None:
            continue
        buckets[point.date.weekday()].append(point.value)

    weekday_expected = []
    weekday_stddev = []
    for bucket in buckets:
        if not bucket:
            weekday_expected.append(ZERO)
            weekday_stddev.append(ZERO)
            continue
        total = sum(bucket, ZERO)
        mean = (total / Decimal(len(bucket))).quantize(Decimal("0.0001"))
        # Population stddev over the bucket; degenerate buckets stay zero.
        ss = ZERO
        for value in bucket:
            diff = value - mean
            ss += diff * diff
        stddev = (
            _decimal_sqrt(ss / Decimal(len(bucket)))
            if len(bucket) >= TWO
            else ZERO
        )
        weekday_expected.append(mean)
        weekday_stddev.append(stddev)

    return SeasonalForecast(
        weekday_expected=tuple(weekday_expected),
        weekday_stddev=tuple(weekday_stddev),
    )


__all__ = ["MODEL_MOVING_AVERAGE", "SeasonalForecast", "fit_seasonal"]
