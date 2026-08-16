"""Time-series validation utilities for the forecasting engine.

The engine distinguishes *observed zeros* from *missing observations*: a day
with no facts in the underlying canonical layer must never be silently
treated as zero, because that would manufacture a false trend. We materialise
every day in the requested training window and explicitly flag any
day that did not appear in the source data.

All arithmetic is `Decimal`. No floats.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from src.modules.forecasting.constants import MIN_OBSERVATIONS_INSUFFICIENT

ZERO = Decimal("0")


@dataclass(frozen=True)
class TimeSeriesPoint:
    date: date
    value: Decimal | None  # None ⇒ missing observation


@dataclass(frozen=True)
class ValidatedSeries:
    """A dense time series with the gaps explicitly identified.

    - `observations_used` = number of non-missing points
    - `missing_observations` = number of explicit gaps
    - `observed_total` = sum over the non-missing observations only;
      gaps are never added as zero.
    - `mean` is the simple arithmetic mean over non-missing observations.
    """

    points: tuple[TimeSeriesPoint, ...]
    observations_used: int
    missing_observations: int
    observed_total: Decimal

    @property
    def length(self) -> int:
        return len(self.points)

    @property
    def mean(self) -> Decimal | None:
        if self.observations_used == 0:
            return None
        return (self.observed_total / Decimal(self.observations_used)).quantize(
            Decimal("0.0001")
        )

    @property
    def is_sufficient(self) -> bool:
        return self.observations_used >= MIN_OBSERVATIONS_INSUFFICIENT


def _to_decimal(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def dense_series(
    raw: list[tuple[date, object]],
    *,
    start: date,
    end: date,
) -> ValidatedSeries:
    """Materialise a dense daily series between `start` and `end` inclusive.

    Days that appear in `raw` carry their observed value (coerced to
    Decimal). Days that do not appear are inserted with `value=None` and
    counted as missing observations. The function never treats missing data
    as zero.
    """
    if end < start:
        raise ValueError("series end must be on or after start")

    observed = {d: _to_decimal(v) for d, v in raw}

    points: list[TimeSeriesPoint] = []
    used = 0
    missing = 0
    total = ZERO
    cursor = start
    while cursor <= end:
        value = observed.get(cursor)
        if value is None:
            missing += 1
        else:
            used += 1
            total += value
        points.append(TimeSeriesPoint(date=cursor, value=value))
        cursor += timedelta(days=1)

    return ValidatedSeries(
        points=tuple(points),
        observations_used=used,
        missing_observations=missing,
        observed_total=total,
    )


def observed_values(series: ValidatedSeries) -> list[Decimal]:
    """Return only the observed values (gaps excluded)."""
    return [point.value for point in series.points if point.value is not None]


__all__ = [
    "TimeSeriesPoint",
    "ValidatedSeries",
    "dense_series",
    "observed_values",
]
