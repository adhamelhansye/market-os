"""Forecast scenario construction.

The engine returns three deterministic scenarios — Best / Expected /
Worst — derived from the model's confidence interval. They are not
arbitrary percentages: they share the model's own uncertainty estimate
and only differ in the multiplier applied to the residual stddev.

- Best  = expected + (upper - expected)
- Expected = expected
- Worst = expected - (expected - lower)

All three values are clamped at zero for non-negative business metrics
(money, counts). Scenario totals are sums of daily points (per-day
forecast × horizon), not arbitrary heuristics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

ZERO = Decimal("0")


@dataclass(frozen=True)
class ScenarioPoint:
    """One day of a forecast scenario."""

    date: date
    expected: Decimal
    lower: Decimal
    upper: Decimal


@dataclass(frozen=True)
class ScenarioSet:
    """The full scenario breakdown for one forecast window."""

    points: tuple[ScenarioPoint, ...]
    total_expected: Decimal
    total_lower: Decimal
    total_upper: Decimal

    @property
    def horizon_days(self) -> int:
        return len(self.points)


def _clamp(value: Decimal) -> Decimal:
    return value if value > ZERO else ZERO


def build_scenarios(
    dates: list[date],
    *,
    expected_per_day: Decimal,
    stddev: Decimal,
    confidence_level: Decimal,
    non_negative: bool = True,
) -> ScenarioSet:
    """Construct daily scenarios using a flat (constant) per-day forecast.

    The flat case covers naive / moving-average / trend-when-expected-is-flat
    models. The trend model with a non-zero slope builds scenarios via
    `build_trend_scenarios` below.
    """
    from src.modules.forecasting.confidence import interval

    lower_per_day, upper_per_day = interval(
        expected_per_day,
        stddev,
        confidence_level=confidence_level,
        non_negative=non_negative,
    )

    points = tuple(
        ScenarioPoint(
            date=day,
            expected=_clamp(expected_per_day) if non_negative else expected_per_day,
            lower=_clamp(lower_per_day) if non_negative else lower_per_day,
            upper=upper_per_day,
        )
        for day in dates
    )
    return ScenarioSet(
        points=points,
        total_expected=sum((p.expected for p in points), ZERO),
        total_lower=sum((p.lower for p in points), ZERO),
        total_upper=sum((p.upper for p in points), ZERO),
    )


def build_trend_scenarios(
    dates: list[date],
    *,
    intercept: Decimal,
    slope: Decimal,
    residual_stddev: Decimal,
    confidence_level: Decimal,
    training_start: date,
    non_negative: bool = True,
) -> ScenarioSet:
    """Build per-day scenarios when the fitted trend has a non-zero slope.

    `day_index` is 1 for the first forecast day after the training
    window; subsequent days step forward by one.
    """
    from src.modules.forecasting.confidence import interval

    points: list[ScenarioPoint] = []
    total_expected = ZERO
    total_lower = ZERO
    total_upper = ZERO
    for index, day in enumerate(dates, start=1):
        raw_expected = intercept + slope * Decimal(index)
        if non_negative and raw_expected < ZERO:
            raw_expected = ZERO
        lower, upper = interval(
            raw_expected,
            residual_stddev,
            confidence_level=confidence_level,
            non_negative=non_negative,
        )
        points.append(ScenarioPoint(date=day, expected=raw_expected, lower=lower, upper=upper))
        total_expected += raw_expected
        total_lower += lower
        total_upper += upper
    return ScenarioSet(
        points=tuple(points),
        total_expected=total_expected.quantize(Decimal("0.0001")),
        total_lower=total_lower.quantize(Decimal("0.0001")),
        total_upper=total_upper.quantize(Decimal("0.0001")),
    )


def build_seasonal_scenarios(
    dates: list[date],
    *,
    weekday_expected: tuple[Decimal, ...],
    weekday_stddev: tuple[Decimal, ...],
    confidence_level: Decimal,
    non_negative: bool = True,
) -> ScenarioSet:
    """Build per-day scenarios for the seasonal model using weekday buckets."""
    from src.modules.forecasting.confidence import interval

    points: list[ScenarioPoint] = []
    total_expected = ZERO
    total_lower = ZERO
    total_upper = ZERO
    for day in dates:
        weekday = day.weekday()
        raw_expected = weekday_expected[weekday]
        raw_stddev = weekday_stddev[weekday]
        if non_negative and raw_expected < ZERO:
            raw_expected = ZERO
        lower, upper = interval(
            raw_expected,
            raw_stddev,
            confidence_level=confidence_level,
            non_negative=non_negative,
        )
        points.append(ScenarioPoint(date=day, expected=raw_expected, lower=lower, upper=upper))
        total_expected += raw_expected
        total_lower += lower
        total_upper += upper
    return ScenarioSet(
        points=tuple(points),
        total_expected=total_expected.quantize(Decimal("0.0001")),
        total_lower=total_lower.quantize(Decimal("0.0001")),
        total_upper=total_upper.quantize(Decimal("0.0001")),
    )


__all__ = [
    "ScenarioPoint",
    "ScenarioSet",
    "build_scenarios",
    "build_seasonal_scenarios",
    "build_trend_scenarios",
]
