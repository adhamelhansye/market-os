"""Deterministic backtesting for the forecasting engine.

The backtest harness validates that a model honestly fits the training
history. For each candidate model the harness:

1. Splits the series into a training portion and a holdout portion. The
   split is the last `BACKTEST_WINDOW_FRACTION` of observations
   (clipped to `BACKTEST_MIN_HOLDOUT` / `BACKTEST_MAX_HOLDOUT`).
2. Refits the model on the training portion (using the same code path
   the engine will use in production).
3. Generates point forecasts for each day in the holdout and compares
   them to the actual observations.
4. Reports the symmetric Mean Absolute Percentage Error (sMAPE) and the
   Mean Absolute Error (MAE) on the holdout.

sMAPE is the primary metric because it is zero-safe (the denominator
never explodes when an observation is zero). MAE is reported alongside
because it has a money/count meaning the dashboard can show directly.

Leakage prevention:

- The holdout portion is never visible to the model fit.
- The model always sees the prefix of the series before the holdout.
- We do not tune a model on the same data we evaluate it on.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.modules.forecasting.constants import (
    BACKTEST_MAX_HOLDOUT,
    BACKTEST_MIN_HOLDOUT,
    BACKTEST_MIN_OBSERVATIONS,
    BACKTEST_WINDOW_FRACTION,
    MODEL_MOVING_AVERAGE,
    MODEL_NAIVE,
    MODEL_SEASONAL,
    MODEL_TREND,
)
from src.modules.forecasting.models.baseline import (
    BaselineForecast,
    moving_average,
    naive_last_value,
    weighted_moving_average,
)
from src.modules.forecasting.models.seasonality import fit_seasonal
from src.modules.forecasting.models.trend import fit_trend
from src.modules.forecasting.validation import (
    TimeSeriesPoint,
    ValidatedSeries,
)

ZERO = Decimal("0")
ONE = Decimal("1")
TWO = Decimal("2")
TWO_HUNDRED = Decimal("200")


@dataclass(frozen=True)
class BacktestResult:
    """The score a single candidate model earned on the holdout window."""

    model: str
    mae: Decimal
    smape: Decimal
    holdout_days: int

    @property
    def is_reliable(self) -> bool:
        return self.holdout_days >= BACKTEST_MIN_HOLDOUT


def _holdout_window(series: ValidatedSeries) -> tuple[int, int]:
    """Return (training_count, holdout_length) for the series.

    `training_count` is the number of observations reserved for training;
    `holdout_length` is the number of observations kept out for scoring.
    """
    used = series.observations_used
    if used < BACKTEST_MIN_OBSERVATIONS:
        return used, 0

    desired_holdout = max(
        BACKTEST_MIN_HOLDOUT,
        min(BACKTEST_MAX_HOLDOUT, int(used * BACKTEST_WINDOW_FRACTION)),
    )
    holdout_length = min(desired_holdout, used - 1)
    training_count = used - holdout_length
    return training_count, holdout_length


def _split_training(
    series: ValidatedSeries, holdout_start: date
) -> ValidatedSeries:
    """Return a validated series that ends on the day before holdout_start."""
    training_points: list[TimeSeriesPoint] = []
    observed_total = ZERO
    used = 0
    missing = 0
    for point in series.points:
        if point.date >= holdout_start:
            break
        training_points.append(point)
        if point.value is None:
            missing += 1
        else:
            used += 1
            observed_total += point.value
    return ValidatedSeries(
        points=tuple(training_points),
        observations_used=used,
        missing_observations=missing,
        observed_total=observed_total,
    )


def _smape(actual: Decimal, predicted: Decimal) -> Decimal:
    """Symmetric Mean Absolute Percentage Error, scaled to 0-200.

    Zero-safe: when both inputs are zero we return zero.
    """
    numerator = abs(actual - predicted)
    denominator = abs(actual) + abs(predicted)
    if denominator == ZERO:
        return ZERO
    return (
        (numerator / denominator).quantize(Decimal("0.0001")) * TWO_HUNDRED
    )


def _score_constant(
    forecast: BaselineForecast, holdout: list[TimeSeriesPoint]
) -> BacktestResult:
    smape_total = ZERO
    mae_total = ZERO
    evaluated = 0
    for point in holdout:
        if point.value is None:
            continue
        smape_total += _smape(point.value, forecast.expected)
        mae_total += abs(point.value - forecast.expected)
        evaluated += 1
    mae = (mae_total / Decimal(evaluated)).quantize(Decimal("0.0001"))
    smape = (smape_total / Decimal(evaluated)).quantize(Decimal("0.0001"))
    return BacktestResult(
        model=forecast.model, mae=mae, smape=smape, holdout_days=evaluated
    )


def _score_trend(
    training: ValidatedSeries,
    training_start: date,
    holdout: list[TimeSeriesPoint],
) -> BacktestResult | None:
    fit = fit_trend(training, training_start=training_start)
    if fit is None:
        return None
    smape_total = ZERO
    mae_total = ZERO
    evaluated = 0
    # Use the one-step-ahead prediction (fit.expected_per_step) for every
    # holdout day. The residual stddev tracks historical noise.
    for point in holdout:
        if point.value is None:
            continue
        smape_total += _smape(point.value, fit.expected_per_step)
        mae_total += abs(point.value - fit.expected_per_step)
        evaluated += 1
    if evaluated == 0:
        return None
    mae = (mae_total / Decimal(evaluated)).quantize(Decimal("0.0001"))
    smape = (smape_total / Decimal(evaluated)).quantize(Decimal("0.0001"))
    return BacktestResult(
        model=MODEL_TREND, mae=mae, smape=smape, holdout_days=evaluated
    )


def _score_seasonal(
    training: ValidatedSeries,
    holdout: list[TimeSeriesPoint],
) -> BacktestResult | None:
    fit = fit_seasonal(training)
    if fit is None:
        return None
    smape_total = ZERO
    mae_total = ZERO
    evaluated = 0
    for point in holdout:
        if point.value is None:
            continue
        expected = fit.expected_for(point.date)
        smape_total += _smape(point.value, expected)
        mae_total += abs(point.value - expected)
        evaluated += 1
    if evaluated == 0:
        return None
    mae = (mae_total / Decimal(evaluated)).quantize(Decimal("0.0001"))
    smape = (smape_total / Decimal(evaluated)).quantize(Decimal("0.0001"))
    return BacktestResult(
        model=MODEL_SEASONAL, mae=mae, smape=smape, holdout_days=evaluated
    )


def backtest(
    series: ValidatedSeries, *, training_start: date
) -> list[BacktestResult]:
    """Score every available candidate model on the same holdout window."""
    training_count, holdout_length = _holdout_window(series)
    if holdout_length == 0:
        return []

    used_dates = [
        point.date for point in series.points if point.value is not None
    ]
    if len(used_dates) < training_count + holdout_length:
        return []

    holdout_start = used_dates[training_count]
    training = _split_training(series, holdout_start)
    holdout = [point for point in series.points if point.date >= holdout_start]

    candidates: list[BacktestResult | None] = []

    naive = naive_last_value(training)
    if naive is not None:
        candidates.append(_score_constant(naive, holdout))

    ma = moving_average(training)
    if ma is not None:
        candidates.append(_score_constant(ma, holdout))

    wma = weighted_moving_average(training)
    if wma is not None:
        candidates.append(_score_constant(wma, holdout))

    candidates.append(_score_trend(training, training_start, holdout))
    candidates.append(_score_seasonal(training, holdout))

    return [result for result in candidates if result is not None]


def best(results: list[BacktestResult]) -> BacktestResult | None:
    """Pick the most reliable candidate. Lower sMAPE wins; ties broken by MAE.

    Candidates with too few holdout days (below `BACKTEST_MIN_HOLDOUT`) are
    only returned when there is no reliable candidate at all — in that
    case the engine falls back to the best-insufficient one and reports
    it as such.
    """
    if not results:
        return None
    eligible = [r for r in results if r.is_reliable]
    pool = eligible if eligible else results
    return min(pool, key=lambda r: (r.smape, r.mae))


__all__ = [
    "BacktestResult",
    "MODEL_MOVING_AVERAGE",
    "MODEL_NAIVE",
    "MODEL_SEASONAL",
    "MODEL_TREND",
    "backtest",
    "best",
]


# Re-export types used by callers / typing.
_ = (Callable, BaselineForecast)  # type-check only
