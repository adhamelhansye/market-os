"""Deterministic KPI engine unit tests (pure — no database).

Covers the zero-vs-unavailable contract, Decimal precision policy,
ratio safety (no division by zero, no Infinity), comparison semantics
and funnel transition/dropoff math.
"""

from decimal import Decimal

import pytest

from src.modules.metrics.kpi_engine import (
    STATUS_AVAILABLE,
    STATUS_UNAVAILABLE,
    Comparison,
    aov,
    contribution_margin,
    cpa,
    cpc,
    cpm,
    ctr,
    cvr,
    dropoff_rate,
    funnel_transition,
    mer,
    roas,
)

ZERO = Decimal("0")
RATE = Decimal("0.0001")


# -- zero vs unavailable ------------------------------------------------------


def test_real_zero_is_available():
    """0 clicks with 1000 impressions is a real zero, not unavailable."""
    m = ctr(0, 1000)
    assert m.status == STATUS_AVAILABLE
    assert m.value == ZERO.quantize(RATE)


def test_missing_denominator_is_unavailable_never_zero_or_infinity():
    m = ctr(5, 0)
    assert m.status == STATUS_UNAVAILABLE
    assert m.value is None
    assert m.reason == "no impressions"


def test_missing_numerator_is_unavailable():
    m = ctr(None, 100)
    assert m.status == STATUS_UNAVAILABLE
    assert m.value is None
    assert m.reason == "no clicks"


def test_none_denominator_is_unavailable():
    assert cpc(Decimal("10"), None).status == STATUS_UNAVAILABLE


# -- typical values with quantized precision ----------------------------------


def test_ctr_precision():
    assert ctr(13, 400).value == (Decimal("13") / Decimal("400")).quantize(RATE)


def test_cpc_precision():
    m = cpc(Decimal("12.345"), 3)
    assert m.status == STATUS_AVAILABLE
    assert m.value == Decimal("4.12")  # money quantized at 2dp at output


def test_cpm():
    m = cpm(Decimal("50"), 1000)
    assert m.value == Decimal("50.00")


def test_cvr_denominator_is_clicks():
    m = cvr(30, 1000)
    assert m.value == Decimal("0.03")


def test_cpa():
    m = cpa(Decimal("45.00"), 4)
    assert m.value == Decimal("11.25")


def test_cpa_zero_purchases_unavailable():
    assert cpa(Decimal("45.00"), 0).status == STATUS_UNAVAILABLE


def test_aov():
    m = aov(Decimal("250.00"), 2)
    assert m.value == Decimal("125.00")


def test_roas():
    m = roas(Decimal("1200"), Decimal("500"))
    assert m.status == STATUS_AVAILABLE
    assert m.value == Decimal("2.4").quantize(RATE)


def test_roas_zero_spend_unavailable():
    assert roas(Decimal("10"), 0).status == STATUS_UNAVAILABLE


def test_mer():
    assert mer(Decimal("3000"), Decimal("1000")).value == Decimal("3").quantize(RATE)


def test_contribution_margin():
    m = contribution_margin(Decimal("40"), Decimal("100"))
    assert m.value == Decimal("0.4").quantize(RATE)


def test_contribution_margin_no_revenue_unavailable():
    assert contribution_margin(Decimal("40"), None).status == STATUS_UNAVAILABLE


# -- negative input contract --------------------------------------------------


@pytest.mark.parametrize(
    "fn",
    [
        lambda: ctr(Decimal("-1"), 100),
        lambda: cpc(Decimal("-1"), 100),
        lambda: cpm(Decimal("10"), Decimal("-5")),
        lambda: cvr(Decimal("-1"), 100),
        lambda: cpa(Decimal("10"), Decimal("-1")),
        lambda: aov(Decimal("-1"), 1),
        lambda: roas(Decimal("-1"), 100),
        lambda: mer(Decimal("-1"), 100),
    ],
)
def test_negative_inputs_are_rejected(fn):
    with pytest.raises(ValueError):
        fn()


def test_non_numeric_input_rejected():
    with pytest.raises(ValueError):
        ctr("not-a-number", 100)


# -- comparison ---------------------------------------------------------------


def test_comparison_normal():
    c = Comparison.of(Decimal("150"), Decimal("100"))
    assert c.current == Decimal("150")
    assert c.previous == Decimal("100")
    assert c.absolute_change == Decimal("50")
    assert c.percentage_change.status == STATUS_AVAILABLE
    assert c.percentage_change.value == Decimal("50.00")


def test_comparison_no_current():
    c = Comparison.of(None, Decimal("100"))
    assert c.current is None
    assert c.absolute_change is None
    assert c.percentage_change.status == STATUS_UNAVAILABLE
    assert c.percentage_change.reason == "no current period data"


def test_comparison_no_previous():
    c = Comparison.of(Decimal("150"), None)
    assert c.percentage_change.status == STATUS_UNAVAILABLE
    assert c.percentage_change.reason == "no previous period data"


def test_comparison_previous_zero_never_percent():
    c = Comparison.of(Decimal("150"), ZERO)
    assert c.absolute_change == Decimal("150")
    assert c.percentage_change.status == STATUS_UNAVAILABLE
    assert c.percentage_change.reason == "previous period is zero"


# -- funnel math --------------------------------------------------------------


def test_funnel_transition():
    m = funnel_transition(Decimal("50"), Decimal("200"))
    assert m.value == Decimal("0.25").quantize(RATE)


def test_funnel_transition_no_previous():
    m = funnel_transition(Decimal("50"), None)
    assert m.status == STATUS_UNAVAILABLE


def test_dropoff_rate():
    m = dropoff_rate(Decimal("75"), Decimal("100"))
    assert m.value == Decimal("0.25").quantize(RATE)


def test_dropoff_rate_no_previous_unavailable():
    assert dropoff_rate(Decimal("75"), None).status == STATUS_UNAVAILABLE


# -- aggregation-vs-averaging guard (defensive sanity of the engine) ----------


def test_period_kpis_come_from_totals():
    """Engine ratios must reproduce total-numerator/total-denominator math.

    If anyone averages per-period ratios instead, blended CTR of a 1% day
    and a 9% day would be 5% — the totals math must stay exact.
    """
    blended = ctr(100, 2000)  # totals across two campaigns
    assert blended.value == Decimal("0.05").quantize(RATE)