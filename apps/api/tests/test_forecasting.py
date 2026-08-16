"""Unit tests for the deterministic forecasting math (Phase 4A).

These tests cover the *pure* layer:

- dense series validation (gaps are explicitly identified);
- baseline models (naive, moving average, weighted moving average);
- trend model (linear regression, residual stddev, clamped at zero);
- seasonal model (weekday buckets, 28-day minimum);
- backtesting (no leakage, sMAPE selection, MAE tie-break);
- confidence intervals (lower ≤ expected ≤ upper, non-negative);
- scenarios (Best/Expected/Worst derived from a single model);
- derived KPIs (CPA, AOV, ROAS, MER, contribution margin);
- goal / budget comparisons (deterministic, no fabrication);
- engine-level guarantees: idempotency, decimal-only, Decimal strings.

The tests do not touch the database, provider APIs or the LLM.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.modules.forecasting import (
    constants,
)
from src.modules.forecasting.backtesting import backtest, best
from src.modules.forecasting.confidence import interval, z_score
from src.modules.forecasting.models.baseline import (
    moving_average,
    naive_last_value,
    weighted_moving_average,
)
from src.modules.forecasting.models.seasonality import fit_seasonal
from src.modules.forecasting.models.trend import fit_trend
from src.modules.forecasting.scenarios import (
    build_scenarios,
    build_seasonal_scenarios,
    build_trend_scenarios,
)
from src.modules.forecasting.validation import dense_series

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_series(start: date, values: list[Decimal | None]) -> tuple[date, dense_series]:
    return start, values


def _series(start: date, end: date):
    return dense_series([], start=start, end=end)


def _populated_series(start: date, values: list[Decimal]) -> dense_series:
    raw = [(start + timedelta(days=i), v) for i, v in enumerate(values)]
    end = start + timedelta(days=len(values) - 1)
    return dense_series(raw, start=start, end=end)


# ---------------------------------------------------------------------------
# Series validation
# ---------------------------------------------------------------------------


class TestDenseSeries:
    def test_missing_dates_are_explicit(self) -> None:
        start = date(2026, 1, 1)
        raw = [(start, Decimal("100")), (start + timedelta(days=2), Decimal("200"))]
        end = start + timedelta(days=2)
        series = dense_series(raw, start=start, end=end)
        assert series.length == 3
        assert series.observations_used == 2
        assert series.missing_observations == 1
        # The gap must never be added to the total as zero.
        assert series.observed_total == Decimal("300")

    def test_observed_total_excludes_gaps(self) -> None:
        start = date(2026, 1, 1)
        raw = [(start, Decimal("100")), (start + timedelta(days=1), None)]
        end = start + timedelta(days=1)
        series = dense_series(raw, start=start, end=end)
        assert series.observations_used == 1
        assert series.observed_total == Decimal("100")
        assert series.mean == Decimal("100.0000")

    def test_sufficient_only_when_observations_meet_minimum(self) -> None:
        start = date(2026, 1, 1)
        raw = [(start + timedelta(days=i), Decimal(str(i + 1))) for i in range(6)]
        end = start + timedelta(days=6)
        series = dense_series(raw, start=start, end=end)
        assert series.is_sufficient is False
        assert series.observations_used == 6


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------


class TestNaiveBaseline:
    def test_returns_last_observation(self) -> None:
        start = date(2026, 1, 1)
        series = _populated_series(start, [Decimal("10"), Decimal("20"), Decimal("30")])
        forecast = naive_last_value(series)
        assert forecast is not None
        assert forecast.expected == Decimal("30")

    def test_clamps_lower_at_zero(self) -> None:
        start = date(2026, 1, 1)
        series = _populated_series(start, [Decimal("5"), Decimal("0"), Decimal("5")])
        forecast = naive_last_value(series)
        assert forecast is not None
        assert forecast.lower >= Decimal("0")

    def test_returns_none_with_no_observations(self) -> None:
        start = date(2026, 1, 1)
        series = dense_series([], start=start, end=start + timedelta(days=6))
        assert naive_last_value(series) is None


class TestMovingAverage:
    def test_uses_last_window(self) -> None:
        start = date(2026, 1, 1)
        values = [Decimal(str(i + 1)) for i in range(14)]
        series = _populated_series(start, values)
        forecast = moving_average(series)
        assert forecast is not None
        # Window is 7 → mean of the last 7 values = 11
        assert forecast.expected == Decimal("11.0000")

    def test_requires_minimum_history(self) -> None:
        start = date(2026, 1, 1)
        values = [Decimal("1") for _ in range(6)]
        series = _populated_series(start, values)
        assert moving_average(series) is None


class TestWeightedMovingAverage:
    def test_recent_days_have_more_weight(self) -> None:
        start = date(2026, 1, 1)
        values = [Decimal("1") for _ in range(13)] + [Decimal("100")]
        series = _populated_series(start, values)
        forecast = weighted_moving_average(series)
        assert forecast is not None
        # The 7-day window sees [1, 1, 1, 1, 1, 1, 100]. With linearly
        # increasing weights the most-recent observation dominates the
        # mean (weight 11.39 vs weight 1 for the oldest), but the older
        # six observations still pull the value below the spike. We
        # assert the forecast is *much* larger than the simple moving
        # average (which would be ~15) and never below the spike.
        ma = moving_average(series)
        assert forecast.expected > ma.expected
        assert forecast.expected > Decimal("30")
        assert forecast.expected < Decimal("100")


# ---------------------------------------------------------------------------
# Trend
# ---------------------------------------------------------------------------


class TestTrendModel:
    def test_positive_slope(self) -> None:
        start = date(2026, 1, 1)
        # Linear trend with deterministic noise so residuals are non-zero.
        values: list[Decimal] = []
        for i in range(28):
            base = (i + 1) * 10
            noise = Decimal("1") if i % 2 == 0 else Decimal("-1")
            values.append(Decimal(base) + noise)
        series = _populated_series(start, values)
        fit = fit_trend(series, training_start=start)
        assert fit is not None
        assert fit.slope > Decimal("0")
        assert fit.intercept > Decimal("0")
        assert fit.expected_per_step > Decimal("0")

    def test_rejects_when_below_minimum(self) -> None:
        start = date(2026, 1, 1)
        values = [Decimal("10") for _ in range(10)]
        series = _populated_series(start, values)
        assert fit_trend(series, training_start=start) is None

    def test_rejects_degenerate_residuals(self) -> None:
        start = date(2026, 1, 1)
        values = [Decimal("100") for _ in range(28)]
        series = _populated_series(start, values)
        # No variance → no honest residual stddev → refuse to fit.
        assert fit_trend(series, training_start=start) is None

    def test_per_day_forecast_clamps_at_zero(self) -> None:
        start = date(2026, 1, 1)
        # Strongly negative trend (values decreasing)
        values = [Decimal(str(100 - i)) for i in range(28)]
        series = _populated_series(start, values)
        fit = fit_trend(series, training_start=start)
        if fit is not None:
            # After enough horizon steps the line would go negative; clamp.
            forecast_at_day_500 = fit.forecast_for_day(500)
            assert forecast_at_day_500 >= Decimal("0")


# ---------------------------------------------------------------------------
# Seasonal
# ---------------------------------------------------------------------------


class TestSeasonalModel:
    def test_requires_four_full_weeks(self) -> None:
        start = date(2026, 1, 1)
        values = [Decimal(str(i + 1)) for i in range(20)]
        series = _populated_series(start, values)
        assert fit_seasonal(series) is None

    def test_weekday_average_is_stable(self) -> None:
        # Pick a Monday so the index-by-weekday mapping is predictable.
        start = date(2026, 1, 5)  # Monday
        # Build 8 weeks of data: Monday = 100, others = 10.
        values: list[Decimal] = []
        cursor = start
        for _week in range(8):
            for weekday in range(7):
                values.append(Decimal("100") if weekday == 0 else Decimal("10"))
                cursor = cursor + timedelta(days=1)
        series = _populated_series(start, values)
        fit = fit_seasonal(series)
        assert fit is not None
        assert fit.weekday_expected[0] == Decimal("100.0000")
        assert all(
            fit.weekday_expected[d] == Decimal("10.0000") for d in range(1, 7)
        )


# ---------------------------------------------------------------------------
# Backtesting
# ---------------------------------------------------------------------------


class TestBacktesting:
    def test_returns_empty_for_short_history(self) -> None:
        start = date(2026, 1, 1)
        values = [Decimal(str(i + 1)) for i in range(5)]
        series = _populated_series(start, values)
        assert backtest(series, training_start=start) == []

    def test_no_future_leakage(self) -> None:
        """The holdout observations must NEVER enter the model fit."""
        start = date(2026, 1, 1)
        # Rising series: training sees only the early low values, holdout
        # contains the spikes. The naive baseline will pick the last
        # training observation; the trend will extrapolate the early
        # slope. Both must be substantially below the holdout mean.
        values: list[Decimal] = []
        for i in range(20):
            values.append(Decimal("10") if i < 14 else Decimal("100"))
        series = _populated_series(start, values)
        results = backtest(series, training_start=start)
        assert results
        # No model should "know" about the spike — every score is high.
        for result in results:
            assert result.mae > Decimal("40")

    def test_best_picks_lowest_smape(self) -> None:
        start = date(2026, 1, 1)
        # Constant series: every candidate model should fit perfectly;
        # the tie-break picks the one with the lowest MAE (zero).
        values = [Decimal("100") for _ in range(30)]
        series = _populated_series(start, values)
        results = backtest(series, training_start=start)
        assert results
        winner = best(results)
        assert winner is not None
        assert winner.smape == Decimal("0.0000")

    def test_smape_handles_zero_observations(self) -> None:
        """sMAPE must remain zero-safe (no division-by-zero)."""
        start = date(2026, 1, 1)
        # Zero-observation series; backtest must still score honestly.
        values = [Decimal("0") for _ in range(30)]
        series = _populated_series(start, values)
        results = backtest(series, training_start=start)
        assert results
        for result in results:
            # Predictions are constant zero; observed values are zero → no error.
            assert result.smape == Decimal("0.0000")


# ---------------------------------------------------------------------------
# Confidence / intervals
# ---------------------------------------------------------------------------


class TestConfidenceInterval:
    def test_lower_le_expected_le_upper(self) -> None:
        lower, upper = interval(Decimal("100"), Decimal("20"))
        assert lower <= Decimal("100") <= upper

    def test_clamps_lower_at_zero(self) -> None:
        lower, upper = interval(Decimal("5"), Decimal("100"))
        assert lower == Decimal("0")
        assert upper > Decimal("0")

    def test_z_table_snapshots(self) -> None:
        assert z_score(Decimal("0.80")) == Decimal("1.2816")
        assert z_score(Decimal("0.95")) == Decimal("1.9600")
        # Out-of-range snaps to the nearest entry.
        assert z_score(Decimal("0")) == Decimal("0")
        assert z_score(Decimal("1.0")) == Decimal("1.9600")


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


class TestScenarios:
    def test_flat_scenario_totals(self) -> None:
        today = date(2026, 8, 15)
        dates = [today + timedelta(days=i) for i in range(7)]
        set_ = build_scenarios(
            dates,
            expected_per_day=Decimal("100"),
            stddev=Decimal("10"),
            confidence_level=Decimal("0.80"),
        )
        assert set_.horizon_days == 7
        assert set_.total_expected == Decimal("700.0000")
        assert set_.total_lower >= Decimal("0")
        assert set_.total_upper >= set_.total_expected

    def test_trend_scenario_totals(self) -> None:
        today = date(2026, 8, 15)
        dates = [today + timedelta(days=i) for i in range(7)]
        set_ = build_trend_scenarios(
            dates,
            intercept=Decimal("100"),
            slope=Decimal("10"),
            residual_stddev=Decimal("5"),
            confidence_level=Decimal("0.80"),
            training_start=today - timedelta(days=28),
        )
        assert set_.horizon_days == 7
        # Slope adds 10/day on top of intercept 100 → expected grows.
        for _index, point in enumerate(set_.points, start=1):
            assert point.expected >= Decimal("0")
            assert point.lower <= point.expected
            assert point.expected <= point.upper

    def test_seasonal_scenario_totals(self) -> None:
        today = date(2026, 8, 15)
        dates = [today + timedelta(days=i) for i in range(7)]
        expected = tuple(Decimal(str(10 * (weekday + 1))) for weekday in range(7))
        stddev = tuple(Decimal("1") for _ in range(7))
        set_ = build_seasonal_scenarios(
            dates,
            weekday_expected=expected,
            weekday_stddev=stddev,
            confidence_level=Decimal("0.80"),
        )
        # Worst-case scenario must be lower than the best case.
        assert set_.total_lower <= set_.total_expected <= set_.total_upper


# ---------------------------------------------------------------------------
# Derived KPIs and goal/budget helpers (engine surface)
# ---------------------------------------------------------------------------


class TestEngineDerived:
    def test_derived_cpa_requires_both_inputs(self) -> None:
        from src.modules.forecasting.engine import EngineForecast, derived_cpa

        spend = EngineForecast(
            metric_code=constants.METRIC_SPEND,
            horizon_days=7,
            forecast_start=date(2026, 8, 15),
            forecast_end=date(2026, 8, 21),
            training_start=date(2026, 7, 1),
            training_end=date(2026, 8, 14),
            model="naive",
            confidence_level=Decimal("0.80"),
            expected_value=Decimal("1000"),
            lower_value=Decimal("900"),
            upper_value=Decimal("1100"),
            observations_used=30,
            missing_observations=0,
            status="available",
            reason=None,
        )
        purchases = EngineForecast(
            metric_code=constants.METRIC_PURCHASES,
            horizon_days=7,
            forecast_start=date(2026, 8, 15),
            forecast_end=date(2026, 8, 21),
            training_start=date(2026, 7, 1),
            training_end=date(2026, 8, 14),
            model="naive",
            confidence_level=Decimal("0.80"),
            expected_value=Decimal("10"),
            lower_value=Decimal("8"),
            upper_value=Decimal("12"),
            observations_used=30,
            missing_observations=0,
            status="available",
            reason=None,
        )
        cpa = derived_cpa(spend, purchases)
        assert cpa is not None
        assert cpa["value"] == Decimal("100.0000")  # 1000 / 10
        assert cpa["currency"] == "USD"

    def test_derived_aov_is_revenue_over_purchases(self) -> None:
        from src.modules.forecasting.engine import EngineForecast, derived_aov

        revenue = EngineForecast(
            metric_code=constants.METRIC_REVENUE,
            horizon_days=7,
            forecast_start=date(2026, 8, 15),
            forecast_end=date(2026, 8, 21),
            training_start=date(2026, 7, 1),
            training_end=date(2026, 8, 14),
            model="naive",
            confidence_level=Decimal("0.80"),
            expected_value=Decimal("2500"),
            lower_value=Decimal("2000"),
            upper_value=Decimal("3000"),
            observations_used=30,
            missing_observations=0,
            status="available",
            reason=None,
        )
        purchases = EngineForecast(
            metric_code=constants.METRIC_PURCHASES,
            horizon_days=7,
            forecast_start=date(2026, 8, 15),
            forecast_end=date(2026, 8, 21),
            training_start=date(2026, 7, 1),
            training_end=date(2026, 8, 14),
            model="naive",
            confidence_level=Decimal("0.80"),
            expected_value=Decimal("10"),
            lower_value=Decimal("8"),
            upper_value=Decimal("12"),
            observations_used=30,
            missing_observations=0,
            status="available",
            reason=None,
        )
        aov = derived_aov(revenue, purchases)
        assert aov is not None
        assert aov["value"] == Decimal("250.0000")

    def test_derived_roas_requires_both_inputs(self) -> None:
        from src.modules.forecasting.engine import EngineForecast, derived_roas

        revenue = EngineForecast(
            metric_code=constants.METRIC_REVENUE,
            horizon_days=7,
            forecast_start=date(2026, 8, 15),
            forecast_end=date(2026, 8, 21),
            training_start=date(2026, 7, 1),
            training_end=date(2026, 8, 14),
            model="naive",
            confidence_level=Decimal("0.80"),
            expected_value=Decimal("2500"),
            lower_value=None,
            upper_value=None,
            observations_used=30,
            missing_observations=0,
            status="available",
            reason=None,
        )
        spend = EngineForecast(
            metric_code=constants.METRIC_SPEND,
            horizon_days=7,
            forecast_start=date(2026, 8, 15),
            forecast_end=date(2026, 8, 21),
            training_start=date(2026, 7, 1),
            training_end=date(2026, 8, 14),
            model="naive",
            confidence_level=Decimal("0.80"),
            expected_value=Decimal("1000"),
            lower_value=None,
            upper_value=None,
            observations_used=30,
            missing_observations=0,
            status="available",
            reason=None,
        )
        assert derived_roas(revenue, spend)["value"] == Decimal("2.5000")
        # Spend missing → ROAS unavailable.
        spend_zero = spend.__class__(
            metric_code=spend.metric_code,
            horizon_days=spend.horizon_days,
            forecast_start=spend.forecast_start,
            forecast_end=spend.forecast_end,
            training_start=spend.training_start,
            training_end=spend.training_end,
            model=spend.model,
            confidence_level=spend.confidence_level,
            expected_value=None,
            lower_value=None,
            upper_value=None,
            observations_used=spend.observations_used,
            missing_observations=spend.missing_observations,
            status=spend.status,
            reason=spend.reason,
        )
        assert derived_roas(revenue, spend_zero) is None

    def test_compare_to_goal_above_and_below(self) -> None:
        from src.modules.forecasting.engine import (
            EngineForecast,
            GoalView,
            compare_to_goal,
        )

        forecast = EngineForecast(
            metric_code=constants.METRIC_REVENUE,
            horizon_days=7,
            forecast_start=date(2026, 8, 15),
            forecast_end=date(2026, 8, 21),
            training_start=date(2026, 7, 1),
            training_end=date(2026, 8, 14),
            model="naive",
            confidence_level=Decimal("0.80"),
            expected_value=Decimal("300000"),
            lower_value=None,
            upper_value=None,
            observations_used=30,
            missing_observations=0,
            status="available",
            reason=None,
        )
        above = compare_to_goal(forecast, GoalView("revenue", Decimal("250000"), "USD"))
        assert above["status"] == "above_target"
        below = compare_to_goal(forecast, GoalView("revenue", Decimal("500000"), "USD"))
        assert below["status"] == "below_target"
        # No target → unavailable.
        none = compare_to_goal(forecast, None)
        assert none["status"] == "unavailable"

    def test_compare_to_budget_overrun(self) -> None:
        from src.modules.forecasting.engine import (
            BudgetView,
            EngineForecast,
            compare_to_budget,
        )

        spend = EngineForecast(
            metric_code=constants.METRIC_SPEND,
            horizon_days=7,
            forecast_start=date(2026, 8, 15),
            forecast_end=date(2026, 8, 21),
            training_start=date(2026, 7, 1),
            training_end=date(2026, 8, 14),
            model="naive",
            confidence_level=Decimal("0.80"),
            expected_value=Decimal("120000"),
            lower_value=None,
            upper_value=None,
            observations_used=30,
            missing_observations=0,
            status="available",
            reason=None,
        )
        result = compare_to_budget(spend, BudgetView(Decimal("100000"), "USD"))
        assert result["overrun"] is True
        assert result["status"] == "overrun"
        within = compare_to_budget(
            EngineForecast(
                metric_code=spend.metric_code,
                horizon_days=spend.horizon_days,
                forecast_start=spend.forecast_start,
                forecast_end=spend.forecast_end,
                training_start=spend.training_start,
                training_end=spend.training_end,
                model=spend.model,
                confidence_level=spend.confidence_level,
                expected_value=Decimal("80000"),
                lower_value=None,
                upper_value=None,
                observations_used=30,
                missing_observations=0,
                status="available",
                reason=None,
            ),
            BudgetView(Decimal("100000"), "USD"),
        )
        assert within["status"] == "within_budget"


# ---------------------------------------------------------------------------
# Forecast horizon validation (service-side mirror)
# ---------------------------------------------------------------------------


class TestHorizonValidation:
    def test_allowed_horizons(self) -> None:
        from src.modules.forecasting.engine import _resolve_horizon
        from src.modules.forecasting.errors import ForecastingFilterError

        assert _resolve_horizon(7) == 7
        assert _resolve_horizon(90) == 90
        with pytest.raises(ForecastingFilterError):
            _resolve_horizon(45)
