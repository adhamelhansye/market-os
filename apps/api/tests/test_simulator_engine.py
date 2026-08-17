"""Simulator engine unit tests (Phase 5A, spec §31-§36).

Pure arithmetic: no database, no API. Covers model selection priority,
funnel math with Decimal precision, unavailable-vs-zero semantics,
scenario derivation from daily percentiles, sensitivity tables,
break-even / profitability / target comparisons, and the deterministic
assumption hash.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.modules.simulator import engine, inputs, scenarios
from src.modules.simulator.constants import (
    DATA_QUALITY_STRONG,
    MODEL_CPA_AOV,
    MODEL_CPC_CVR_AOV,
    MODEL_CPM_CTR_CVR_AOV,
    PROFITABILITY_PROFITABLE,
    PROFITABILITY_UNAVAILABLE,
    PROFITABILITY_UNPROFITABLE,
)

ZERO = Decimal("0")


def _av(name: str, value: Decimal | None, unit: str = "ratio") -> inputs.AssumptionValue:
    return inputs.AssumptionValue(
        name=name,
        value=value,
        unit=unit,
        source="user_input",
        override=False,
        confidence=DATA_QUALITY_STRONG,
    )


def _assumption_set(**values) -> inputs.AssumptionSet:
    return inputs.AssumptionSet(
        budget=_av("budget", values.get("budget", Decimal("1000")), "money"),
        ctr=_av("ctr", values.get("ctr", Decimal("0.01"))),
        cpc=_av("cpc", values.get("cpc", Decimal("10")), "money"),
        cpm=_av("cpm", values.get("cpm", Decimal("100")), "money"),
        cvr=_av("cvr", values.get("cvr", Decimal("0.2"))),
        aov=_av("aov", values.get("aov", Decimal("50")), "money"),
        cpa=_av("cpa", values.get("cpa", Decimal("25")), "money"),
        refund_rate=_av("refund_rate", values.get("refund_rate", Decimal("0.1"))),
        contribution_profit_per_order=_av(
            "contribution_profit_per_order",
            values.get("contribution_profit_per_order", Decimal("20")),
            "money",
        ),
        break_even_cpa=_av("break_even_cpa", values.get("break_even_cpa"), "money"),
        break_even_roas=_av("break_even_roas", values.get("break_even_roas")),
        reference_window_start=None,
        reference_window_end=None,
    )


# ---------------------------------------------------------------------------
# Model selection
# ---------------------------------------------------------------------------


def test_select_model_priority_a_then_b_then_c_then_none() -> None:
    assert engine.select_model(_assumption_set()) == MODEL_CPM_CTR_CVR_AOV
    no_cpm = _assumption_set(cpm=None)
    assert engine.select_model(no_cpm) == MODEL_CPC_CVR_AOV
    no_cpc = _assumption_set(cpm=None, cpc=None)
    assert engine.select_model(no_cpc) == MODEL_CPA_AOV
    no_cpa = _assumption_set(cpm=None, cpc=None, cpa=None)
    assert engine.select_model(no_cpa) is None


# ---------------------------------------------------------------------------
# Funnel arithmetic (Model A)
# ---------------------------------------------------------------------------


def test_compute_funnel_model_a_expected_values() -> None:
    level = scenarios.LevelValues(
        ctr=Decimal("0.01"),
        cpc=Decimal("10"),
        cpm=Decimal("100"),
        cvr=Decimal("0.2"),
        aov=Decimal("50"),
        cpa=Decimal("25"),
    )
    metrics = engine.compute_funnel(
        model=MODEL_CPM_CTR_CVR_AOV,
        budget=Decimal("1000"),
        level=level,
        refund_rate=Decimal("0.1"),
        profit_per_order=Decimal("20"),
    )
    assert metrics is not None
    # budget 1000 / cpm 100 * 1000 → 10_000 impressions
    assert metrics.impressions == Decimal("10000.0000")
    # clicks = 10_000 * 0.01
    assert metrics.clicks == Decimal("100.0000")
    # purchases = 100 * 0.2
    assert metrics.purchases == Decimal("20.0000")
    assert metrics.cpa == Decimal("50.00")
    assert metrics.revenue == Decimal("1000.00")
    assert metrics.roas == Decimal("1.0000")
    # refunds = revenue * 0.1
    assert metrics.refund_amount == Decimal("100.00")
    assert metrics.net_revenue == Decimal("900.00")
    # profit = 20 orders * 20
    assert metrics.contribution_profit == Decimal("400.00")
    # margin quantified to 0.0001 (400 / 900)
    assert metrics.contribution_margin == Decimal("0.4444")
    assert metrics.cpm == Decimal("100.00")


def test_compute_funnel_missing_input_is_none_not_zero() -> None:
    level = scenarios.LevelValues(cpm=Decimal("100"), cvr=Decimal("0.2"))
    metrics = engine.compute_funnel(
        model=MODEL_CPM_CTR_CVR_AOV,
        budget=Decimal("1000"),
        level=level,
        refund_rate=None,
        profit_per_order=None,
    )
    assert metrics is None


def test_compute_funnel_division_safe() -> None:
    level = scenarios.LevelValues(
        ctr=Decimal("0.01"),
        cpm=Decimal("100"),
        cvr=Decimal("0.2"),
        aov=Decimal("50"),
    )
    metrics = engine.compute_funnel(
        model=MODEL_CPM_CTR_CVR_AOV,
        budget=Decimal("0"),
        level=level,
        refund_rate=None,
        profit_per_order=None,
    )
    # no crash, everything derived from the zero budget stays decimal-zero
    assert metrics is not None
    assert metrics.impressions == Decimal("0.0000")


# ---------------------------------------------------------------------------
# run_simulation end-to-end
# ---------------------------------------------------------------------------


def _profile_with(assumptions: inputs.AssumptionSet, ratios: scenarios.DailyRatios):
    return scenarios.build_scenario_profile(assumptions, ratios)


def test_run_simulation_tails_unavailable_without_enough_days() -> None:
    assumptions = _assumption_set()
    daily = scenarios.DailyRatios()  # empty — no historical evidence
    run = engine.run_simulation(
        assumptions=assumptions,
        profile=_profile_with(assumptions, daily),
        evidence_strength=DATA_QUALITY_STRONG,
    )
    assert run.model_used == MODEL_CPM_CTR_CVR_AOV
    assert set(run.scenarios) == {"expected"}
    assert run.reasons["downside"] == "insufficient_assumptions"
    assert run.reasons["upside"] == "insufficient_assumptions"
    assert run.reasons["expected"] is None
    expected = run.scenarios["expected"]
    assert expected.revenue == Decimal("1000.00")
    assert run.profitability.status == PROFITABILITY_PROFITABLE


def test_run_simulation_no_model_is_unavailable_not_fabricated() -> None:
    assumptions = _assumption_set(cpm=None, cpc=None, cpa=None)
    daily = scenarios.DailyRatios()
    run = engine.run_simulation(
        assumptions=assumptions,
        profile=_profile_with(assumptions, daily),
        evidence_strength=DATA_QUALITY_STRONG,
    )
    assert run.model_used == "unavailable"
    assert run.scenarios == {}
    assert run.profitability.status == PROFITABILITY_UNAVAILABLE
    assert run.profitability.reason == "no_calculation_model"


def test_run_simulation_with_percentile_tails() -> None:
    assumptions = _assumption_set()
    # 12 days of daily ratios → 25th/75th percentiles are well defined
    days = [date(2026, 7, 1 + i) for i in range(12)]
    daily = scenarios.DailyRatios(
        dates=tuple(days),
        ctr=tuple(Decimal(f"0.{i:02d}") for i in range(1, 13)),  # 0.01..0.12
        cpm=tuple(Decimal("10") for _ in days),
        cpc=tuple(Decimal("2") for _ in days),
        cvr=tuple(Decimal("0.2") for _ in days),
        aov=tuple(Decimal("50") for _ in days),
        cpa=tuple(Decimal("25") for _ in days),
    )
    run = engine.run_simulation(
        assumptions=assumptions,
        profile=_profile_with(assumptions, daily),
        evidence_strength=DATA_QUALITY_STRONG,
    )
    assert set(run.scenarios) == {"downside", "expected", "upside"}
    # 25th percentile of 0.01..0.12 → 0.03 ; 75th → 0.09
    assert run.scenarios["downside"].ctr == Decimal("0.0300")
    assert run.scenarios["upside"].ctr == Decimal("0.0900")
    assert run.scenarios["expected"].ctr == Decimal("0.0100")


def test_percentile_nearest_rank_deterministic() -> None:
    values = (Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"))
    assert scenarios.percentile(values, Decimal("25")) == Decimal("1")
    assert scenarios.percentile(values, Decimal("50")) == Decimal("2")
    assert scenarios.percentile(values, Decimal("75")) == Decimal("3")
    assert scenarios.percentile((), Decimal("25")) is None


# ---------------------------------------------------------------------------
# Break-even / profitability / targets
# ---------------------------------------------------------------------------


def test_build_break_even_uses_economics_values() -> None:
    level = scenarios.LevelValues(
        ctr=Decimal("0.01"),
        cpm=Decimal("100"),
        cvr=Decimal("0.2"),
        aov=Decimal("50"),
    )
    expected = engine.compute_funnel(
        model=MODEL_CPM_CTR_CVR_AOV,
        budget=Decimal("1000"),
        level=level,
        refund_rate=None,
        profit_per_order=Decimal("20"),
    )
    assert expected is not None
    be = engine.build_break_even(
        expected,
        break_even_cpa=Decimal("30"),
        break_even_roas=Decimal("2"),
    )
    assert be.break_even_cpa == Decimal("30.00")
    assert be.simulated_cpa == Decimal("50.00")
    # 1000 / (30 * 100 clicks) → 0.3333…
    assert be.minimum_cvr == Decimal("0.3333")
    assert be.maximum_cpc == Decimal("6.00")  # 30 * 0.2
    assert be.minimum_aov == Decimal("100.00")  # 2*1000 / 20
    assert be.maximum_cpa == Decimal("25.00")  # 50 / 2


def test_build_targets_statuses() -> None:
    level = scenarios.LevelValues(
        ctr=Decimal("0.01"),
        cpm=Decimal("100"),
        cvr=Decimal("0.2"),
        aov=Decimal("50"),
    )
    expected = engine.compute_funnel(
        model=MODEL_CPM_CTR_CVR_AOV,
        budget=Decimal("1000"),
        level=level,
        refund_rate=None,
        profit_per_order=Decimal("20"),
    )
    assert expected is not None
    targets = engine.build_targets(
        expected,
        target_cpa=Decimal("60"),
        target_roas=Decimal("3"),
        target_revenue=None,
        target_profit=Decimal("500"),
    )
    by_code = {t.metric_code: t for t in targets}
    assert by_code["cpa"].status == "met"  # 50 <= 60
    assert by_code["roas"].status == "not_met"  # 1 < 3
    assert by_code["revenue"].status == "unavailable"
    assert by_code["profit"].status == "not_met"  # 400 < 500


def test_build_profitability_unprofitable() -> None:
    level = scenarios.LevelValues(
        ctr=Decimal("0.01"),
        cpm=Decimal("100"),
        cvr=Decimal("0.2"),
        aov=Decimal("50"),
    )
    expected = engine.compute_funnel(
        model=MODEL_CPM_CTR_CVR_AOV,
        budget=Decimal("1000"),
        level=level,
        refund_rate=None,
        # unit tests may construct negative economics directly; the API
        # layer rejects them, so this only proves the engine's branch
        profit_per_order=Decimal("-5"),
    )
    assert expected is not None
    profitability = engine.build_profitability(expected, break_even_roas=Decimal("2"))
    assert profitability.status == PROFITABILITY_UNPROFITABLE
    assert profitability.contribution_profit == Decimal("-100.00")


# ---------------------------------------------------------------------------
# Sensitivity
# ---------------------------------------------------------------------------


def test_sensitivity_only_consumed_variables() -> None:
    level = scenarios.LevelValues(
        ctr=Decimal("0.01"),
        cpm=Decimal("100"),
        cvr=Decimal("0.2"),
        aov=Decimal("50"),
    )
    tables = engine.build_sensitivity(
        MODEL_CPM_CTR_CVR_AOV,
        budget=Decimal("1000"),
        level=level,
        refund_rate=None,
        profit_per_order=Decimal("20"),
    )
    variables = {t.variable for t in tables}
    assert variables == {"ctr", "cpm", "cvr", "aov", "budget"}
    ctr_table = next(t for t in tables if t.variable == "ctr")
    rows = {r.change_percent: r for r in ctr_table.rows}
    # +20% CTR → clicks up 20% → revenue up 20%
    assert rows[Decimal("0.20")].revenue == Decimal("1200.00")
    assert rows[Decimal("-0.20")].revenue == Decimal("800.00")
    assert rows[Decimal("0")].revenue == Decimal("1000.00")


def test_sensitivity_model_b_excludes_cpm() -> None:
    level = scenarios.LevelValues(
        ctr=Decimal("0.01"),
        cpc=Decimal("10"),
        cvr=Decimal("0.2"),
        aov=Decimal("50"),
    )
    tables = engine.build_sensitivity(
        MODEL_CPC_CVR_AOV,
        budget=Decimal("1000"),
        level=level,
        refund_rate=None,
        profit_per_order=Decimal("20"),
    )
    assert {t.variable for t in tables} == {"cpc", "cvr", "aov", "budget"}


# ---------------------------------------------------------------------------
# Funnel-derived metrics (Model C)
# ---------------------------------------------------------------------------


def test_compute_funnel_model_c() -> None:
    level = scenarios.LevelValues(
        ctr=Decimal("0.01"), cpc=Decimal("10"), cpa=Decimal("25"), aov=Decimal("50")
    )
    metrics = engine.compute_funnel(
        model=MODEL_CPA_AOV,
        budget=Decimal("100"),
        level=level,
        refund_rate=None,
        profit_per_order=None,
    )
    assert metrics is not None
    assert metrics.purchases == Decimal("4.0000")  # 100 / 25
    assert metrics.revenue == Decimal("200.00")
    assert metrics.cpa == Decimal("25.00")
    # clicks derived from purchases / cvr — cvr missing here → None
    assert metrics.clicks is None


# ---------------------------------------------------------------------------
# Hash determinism (assumptions_hash)
# ---------------------------------------------------------------------------


def test_assumptions_hash_deterministic_and_sensitive() -> None:
    from src.modules.simulator.service import assumptions_hash

    first = _assumption_set()
    second = _assumption_set()
    assert assumptions_hash(first) == assumptions_hash(second)
    changed = _assumption_set(budget=Decimal("999"))
    assert assumptions_hash(changed) != assumptions_hash(first)
    # scalar scale differences must not break identity
    scaled = _assumption_set(cvr=Decimal("0.2000"))
    assert assumptions_hash(scaled) == assumptions_hash(first)


def test_inputs_assumption_value_money_stays_decimal() -> None:
    value = inputs.AssumptionValue(
        name="cpc", value=Decimal("10.5"), unit="money", source="user_input"
    )
    dumped = value.to_dict()
    assert isinstance(dumped["value"], str)
    from decimal import Decimal as D

    assert D(dumped["value"]) == Decimal("10.5")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
