"""Diagnostics rule unit tests (Phase 3B).

Every rule is tested with: positive case, negative case, insufficient-data
case and threshold boundary case, per the Phase 3B contract. Additional
coverage: tiny samples never produce performance findings, zero vs
unavailable is respected, multiple findings coexist, fingerprints dedupe.
"""

import uuid
from datetime import date
from decimal import Decimal

from src.modules.diagnostics import engine
from src.modules.diagnostics import thresholds as th
from src.modules.diagnostics.evidence import (
    CATEGORY_CREATIVE,
    CATEGORY_TRAFFIC,
    ENTITY_TYPE_AD,
    ENTITY_TYPE_CAMPAIGN,
    REVIEW_REQUIRED,
    STATUS_DETECTED,
    STATUS_INSUFFICIENT_DATA,
)
from src.modules.diagnostics.rules import (
    EntityContext,
    RuleContext,
    apply_business_rules,
    apply_entity_rules,
)
from src.modules.metrics.aggregation import Range
from src.modules.metrics.kpi_engine import STATUS_AVAILABLE, STATUS_UNAVAILABLE

BUSINESS_ID = uuid.uuid4()
CAMPAIGN_ID = uuid.uuid4()
AD_ID = uuid.uuid4()


def _measure(value=None, status=STATUS_AVAILABLE, reason=None) -> dict:
    return {"value": value, "status": status, "reason": reason}


def _u(reason: str) -> dict:
    return _measure(None, STATUS_UNAVAILABLE, reason)


def _money(value: str) -> Decimal:
    return Decimal(value)


def _range() -> Range:
    return Range(
        kind="last_7_days",
        start=date(2026, 8, 1),
        end=date(2026, 8, 7),
        previous_start=date(2026, 7, 25),
        previous_end=date(2026, 7, 31),
    )


def _summary(**overrides) -> dict:
    base = {
        "revenue": _measure("1250.00"),
        "spend": _measure("1000.00"),
        "purchases": _measure("4"),
        "refunds": _measure("50.00"),
        "impressions": _measure("2000"),
        "reach": _measure("1500"),
        "clicks": _measure("100"),
        "link_clicks": _measure("80"),
        "landing_page_views": _measure("60"),
        "conversions": _measure("8"),
        "ctr": _measure("0.05"),
        "cpc": _measure("10.00"),
        "cpm": _measure("500.00"),
        "cvr": _measure("0.04"),
        "cpa": _measure("250.00"),
        "aov": _measure("312.50"),
        "roas": _measure("1.5"),
        "mer": _measure("1.25"),
        "contribution_profit": _measure("320.00"),
        "contribution_margin": _measure("0.256"),
        "break_even_cpa": _measure("80.00"),
        "break_even_roas": _measure("1.5"),
    }
    base.update(overrides)
    return base


def _ctx(
    summary=None,
    previous=None,
    profile=None,
    goal=None,
    funnel=None,
    previous_funnel=None,
    quality=None,
    sync_failures=0,
) -> RuleContext:
    return RuleContext(
        business_id=BUSINESS_ID,
        business_name="Test Business",
        currency="USD",
        timezone="UTC",
        range=_range(),
        profile=profile or {},
        goal=goal,
        summary=summary if summary is not None else _summary(),
        previous_summary=previous,
        funnel=funnel,
        previous_funnel=previous_funnel,
        quality=quality,
        sync_failures=sync_failures,
    )


def _entity_metrics(defaults: dict | None = None, **overrides) -> dict:
    base = {
        "impressions": 2000,
        "reach": 1500,
        "clicks": 100,
        "spend": _money("500.00"),
        "conversions": 10,
        "conversion_value": _money("400.00"),
        "ctr": _measure("0.01"),
        "cpc": _measure("5.00"),
        "cpm": _measure("250.00"),
        "roas": _measure("0.8"),
        "cvr": _u("no purchase attribution at this grain"),
        "cpa": _u("no purchase attribution at this grain"),
        "aov": _u("no purchase attribution at this grain"),
    }
    if defaults:
        base.update(defaults)
    base.update(overrides)
    return base


def _campaign_entity(metrics=None, previous=None, rows=10) -> EntityContext:
    return EntityContext(
        entity_type=ENTITY_TYPE_CAMPAIGN,
        entity_id=CAMPAIGN_ID,
        entity_name="Campaign A",
        metrics=metrics if metrics is not None else _entity_metrics(),
        previous_metrics=previous,
        rows=rows,
        range_length_days=7,
    )


def _ad_entity(metrics=None, previous=None, rows=10) -> EntityContext:
    return EntityContext(
        entity_type=ENTITY_TYPE_AD,
        entity_id=AD_ID,
        entity_name="Ad 1",
        metrics=metrics if metrics is not None else _entity_metrics(),
        previous_metrics=previous,
        rows=rows,
        range_length_days=7,
    )


def _funnel(stages: list[dict]) -> dict:
    return {"business_id": BUSINESS_ID, "range": {}, "stages": stages}


def _stage(metric: str, value, status=STATUS_AVAILABLE) -> dict:
    return {"metric": metric, "value": value, "status": status,
            "reason": None, "conversion_rate": None, "dropoff_rate": None}


def _observed_funnel(impressions=2000, clicks=100, lpv=60, purchases=4) -> dict:
    stages = [
        _stage("impressions", impressions),
        _stage("clicks", clicks),
        _stage("landing_page_views", lpv),
        _stage("product_views", None, STATUS_UNAVAILABLE),
        _stage("add_to_cart", None, STATUS_UNAVAILABLE),
        _stage("checkout_started", None, STATUS_UNAVAILABLE),
        _stage("purchases", purchases),
    ]
    return _funnel(stages)


def _find(findings, code: str):
    return [f for f in findings if f.code == code]


def _only(findings, code: str):
    matches = _find(findings, code)
    assert len(matches) >= 1, f"expected at least one {code} finding"
    return matches[0]


# ---------------------------------------------------------------------------
# low_ctr
# ---------------------------------------------------------------------------


def test_low_ctr_positive() -> None:
    ctx = _ctx(summary=_summary(ctr=_measure("0.005")))
    finding = _only(apply_business_rules(ctx), "low_ctr")
    assert finding.status == STATUS_DETECTED
    assert finding.severity == "low"
    assert finding.category == CATEGORY_TRAFFIC
    assert finding.evidence.metric.code == "ctr"
    assert finding.evidence.threshold.value == th.value(th.CTR_LOW)


def test_low_ctr_negative() -> None:
    ctx = _ctx(summary=_summary(ctr=_measure("0.01")))
    assert _find(apply_business_rules(ctx), "low_ctr") == []


def test_low_ctr_insufficient_sample() -> None:
    # 12 impressions, 0 clicks: never a performance finding.
    ctx = _ctx(summary=_summary(impressions=_measure("12"), clicks=_measure("0"),
                                ctr=_measure("0")))
    finding = _only(apply_business_rules(ctx), "low_ctr")
    assert finding.status == STATUS_INSUFFICIENT_DATA
    assert finding.severity == "info"


def test_low_ctr_at_threshold_is_not_low() -> None:
    ctr_low = th.value(th.CTR_LOW)
    for value in (ctr_low, ctr_low + Decimal("0.0001")):
        ctx = _ctx(summary=_summary(ctr=_measure(str(value))))
        assert _find(apply_business_rules(ctx), "low_ctr") == []


def test_low_ctr_just_below_threshold_is_low() -> None:
    ctx = _ctx(summary=_summary(ctr=_measure(str(th.value(th.CTR_LOW) - Decimal("0.0001")))))
    finding = _only(apply_business_rules(ctx), "low_ctr")
    assert finding.status == STATUS_DETECTED


def test_low_ctr_critical_escalation() -> None:
    ctx = _ctx(summary=_summary(ctr=_measure("0.002")))
    assert _only(apply_business_rules(ctx), "low_ctr").severity == "high"


def test_low_ctr_zero_ctr_is_real_zero_and_low() -> None:
    # impressions=1000, clicks=0 → CTR=0 available → low_ctr fires.
    ctx = _ctx(summary=_summary(impressions=_measure("1000"), clicks=_measure("0"),
                                ctr=_measure("0")))
    finding = _only(apply_business_rules(ctx), "low_ctr")
    assert finding.status == STATUS_DETECTED


def test_low_ctr_unavailable_ctr_is_not_diagnosed() -> None:
    # impressions=0 → CTR unavailable → insufficient_data, never low_ctr.
    ctx = _ctx(summary=_summary(impressions=_measure(None, STATUS_UNAVAILABLE),
                                clicks=_measure(None, STATUS_UNAVAILABLE),
                                ctr=_u("no impressions")))
    findings = apply_business_rules(ctx)
    for finding in _find(findings, "low_ctr"):
        assert finding.status != STATUS_DETECTED


# ---------------------------------------------------------------------------
# ctr_decline
# ---------------------------------------------------------------------------


def test_ctr_decline_positive() -> None:
    ctx = _ctx(summary=_summary(ctr=_measure("0.004")),
               previous=_summary(ctr=_measure("0.011")))
    finding = _only(apply_business_rules(ctx), "ctr_decline")
    assert finding.status == STATUS_DETECTED
    assert finding.evidence.metric.previous == _money("0.011")
    # decline = 63.64% ≥ 30%
    assert finding.evidence.comparison.change_percent < Decimal("0")


def test_ctr_decline_negative() -> None:
    ctx = _ctx(summary=_summary(ctr=_measure("0.0128")),
               previous=_summary(ctr=_measure("0.011")))
    assert _find(apply_business_rules(ctx), "ctr_decline") == []


def test_ctr_decline_boundary() -> None:
    minimum = th.value(th.DECLINE_PERCENT)
    # exactly at threshold (gte): fires.
    prev = Decimal("100")
    current = prev * (Decimal("100") - minimum) / Decimal("100")
    ctx = _ctx(summary=_summary(ctr=_measure(str(current))),
               previous=_summary(ctr=_measure(str(prev))))
    assert _find(apply_business_rules(ctx), "ctr_decline") != []
    # just under threshold: does not fire.
    current_under = current + Decimal("0.0001")
    ctx2 = _ctx(summary=_summary(ctr=_measure(str(current_under))),
                previous=_summary(ctr=_measure(str(prev))))
    assert _find(apply_business_rules(ctx2), "ctr_decline") == []


def test_ctr_decline_no_previous_is_not_diagnosed() -> None:
    ctx = _ctx(summary=_summary(ctr=_measure("0.004")))
    assert _find(apply_business_rules(ctx), "ctr_decline") == []


# ---------------------------------------------------------------------------
# high_cpc / high_cpm
# ---------------------------------------------------------------------------


def test_high_cpc_positive() -> None:
    ctx = _ctx(summary=_summary(cpc=_measure("12.00")))
    finding = _only(apply_business_rules(ctx), "high_cpc")
    assert finding.status == STATUS_DETECTED
    assert finding.severity == "low"


def test_high_cpc_negative_and_boundary() -> None:
    ctx = _ctx(summary=_summary(cpc=_measure("10.00")))
    assert _find(apply_business_rules(ctx), "high_cpc") == []
    ctx2 = _ctx(summary=_summary(cpc=_measure("9.99")))
    assert _find(apply_business_rules(ctx2), "high_cpc") == []


def test_high_cpc_insufficient_clicks() -> None:
    ctx = _ctx(summary=_summary(clicks=_measure("10"), cpc=_measure("12.00")))
    finding = _only(apply_business_rules(ctx), "high_cpc")
    assert finding.status == STATUS_INSUFFICIENT_DATA


def test_high_cpm_positive() -> None:
    ctx = _ctx(summary=_summary(cpm=_measure("900.00")))
    finding = _only(apply_business_rules(ctx), "high_cpm")
    assert finding.status == STATUS_DETECTED


def test_high_cpm_negative_and_boundary() -> None:
    ctx = _ctx(summary=_summary(cpm=_measure("800.00")))
    assert _find(apply_business_rules(ctx), "high_cpm") == []


def test_high_cpm_insufficient_impressions() -> None:
    ctx = _ctx(summary=_summary(impressions=_measure("100"), cpm=_measure("900.00")))
    finding = _only(apply_business_rules(ctx), "high_cpm")
    assert finding.status == STATUS_INSUFFICIENT_DATA


# ---------------------------------------------------------------------------
# low_cvr / cvr_decline
# ---------------------------------------------------------------------------


def test_low_cvr_positive() -> None:
    ctx = _ctx(summary=_summary(cvr=_measure("0.02")))
    finding = _only(apply_business_rules(ctx), "low_cvr")
    assert finding.status == STATUS_DETECTED
    assert finding.severity == "medium"
    assert finding.category == "conversion"


def test_low_cvr_negative_and_boundary() -> None:
    ctx = _ctx(summary=_summary(cvr=_measure("0.03")))
    assert _find(apply_business_rules(ctx), "low_cvr") == []
    ctx2 = _ctx(summary=_summary(cvr=_measure("0.04")))
    assert _find(apply_business_rules(ctx2), "low_cvr") == []


def test_low_cvr_insufficient_clicks() -> None:
    ctx = _ctx(summary=_summary(clicks=_measure("10"), cvr=_measure("0.02")))
    finding = _only(apply_business_rules(ctx), "low_cvr")
    assert finding.status == STATUS_INSUFFICIENT_DATA


def test_low_cvr_very_low_escalates() -> None:
    ctx = _ctx(summary=_summary(cvr=_measure("0.01")))
    assert _only(apply_business_rules(ctx), "low_cvr").severity == "high"


def test_cvr_decline_positive() -> None:
    ctx = _ctx(summary=_summary(cvr=_measure("0.01")),
               previous=_summary(cvr=_measure("0.02")))
    finding = _only(apply_business_rules(ctx), "cvr_decline")
    assert finding.status == STATUS_DETECTED


def test_cvr_decline_negative() -> None:
    ctx = _ctx(summary=_summary(cvr=_measure("0.019")),
               previous=_summary(cvr=_measure("0.02")))
    assert _find(apply_business_rules(ctx), "cvr_decline") == []


# ---------------------------------------------------------------------------
# high_cpa
# ---------------------------------------------------------------------------


def test_high_cpa_positive_using_goal_target() -> None:
    ctx = _ctx(summary=_summary(cpa=_measure("184.00"), purchases=_measure("14")),
               goal={"maximum_cpa": _money("120.00"), "target_roas": None})
    finding = _only(apply_business_rules(ctx), "high_cpa")
    assert finding.status == STATUS_DETECTED
    assert finding.severity == "high"
    assert finding.evidence.threshold.value == _money("120.00")


def test_high_cpa_critical() -> None:
    ctx = _ctx(summary=_summary(cpa=_measure("241.00"), purchases=_measure("14")),
               goal={"maximum_cpa": _money("120.00"), "target_roas": None})
    assert _only(apply_business_rules(ctx), "high_cpa").severity == "critical"


def test_high_cpa_medium() -> None:
    ctx = _ctx(summary=_summary(cpa=_measure("121.00"), purchases=_measure("14")),
               goal={"maximum_cpa": _money("120.00"), "target_roas": None})
    assert _only(apply_business_rules(ctx), "high_cpa").severity == "medium"


def test_high_cpa_negative_and_boundary() -> None:
    ctx = _ctx(summary=_summary(cpa=_measure("120.00"), purchases=_measure("14")),
               goal={"maximum_cpa": _money("120.00"), "target_roas": None})
    assert _find(apply_business_rules(ctx), "high_cpa") == []


def test_high_cpa_insufficient_purchases() -> None:
    ctx = _ctx(summary=_summary(cpa=_measure("184.00"), purchases=_measure("2")),
               goal={"maximum_cpa": _money("120.00"), "target_roas": None})
    finding = _only(apply_business_rules(ctx), "high_cpa")
    assert finding.status == STATUS_INSUFFICIENT_DATA


def test_high_cpa_never_invents_target() -> None:
    # No goal, no economics: no target → no finding.
    ctx = _ctx(summary=_summary(cpa=_measure("1000.00"), purchases=_measure("14")))
    assert _find(apply_business_rules(ctx), "high_cpa") == []


def test_high_cpa_falls_back_to_break_even() -> None:
    ctx = _ctx(summary=_summary(cpa=_measure("100.00"), purchases=_measure("14")),
               profile={"break_even_cpa_range": [_money("70.00"), _money("80.00")]})
    finding = _only(apply_business_rules(ctx), "high_cpa")
    assert finding.evidence.threshold.value == _money("80.00")


# ---------------------------------------------------------------------------
# roas diagnostics
# ---------------------------------------------------------------------------


def test_below_break_even_roas_positive() -> None:
    ctx = _ctx(summary=_summary(roas=_measure("1.2")),
               profile={"break_even_roas": _money("1.5")})
    finding = _only(apply_business_rules(ctx), "below_break_even_roas")
    assert finding.status == STATUS_DETECTED
    assert finding.severity == "high"
    assert finding.category == "economics"


def test_below_break_even_roas_negative_and_boundary() -> None:
    ctx = _ctx(summary=_summary(roas=_measure("1.5")),
               profile={"break_even_roas": _money("1.5")})
    assert _find(apply_business_rules(ctx), "below_break_even_roas") == []


def test_below_break_even_roas_missing_break_even() -> None:
    ctx = _ctx(summary=_summary(roas=_measure("0.5")))
    assert _find(apply_business_rules(ctx), "below_break_even_roas") == []


def test_below_target_roas_positive() -> None:
    ctx = _ctx(summary=_summary(roas=_measure("1.8")),
               goal={"maximum_cpa": None, "target_roas": _money("2.0")})
    finding = _only(apply_business_rules(ctx), "below_target_roas")
    assert finding.status == STATUS_DETECTED
    assert finding.severity == "medium"


def test_below_target_roas_negative_and_boundary() -> None:
    ctx = _ctx(summary=_summary(roas=_measure("2.0")),
               goal={"maximum_cpa": None, "target_roas": _money("2.0")})
    assert _find(apply_business_rules(ctx), "below_target_roas") == []


def test_below_target_roas_without_goal() -> None:
    ctx = _ctx(summary=_summary(roas=_measure("1.0")))
    assert _find(apply_business_rules(ctx), "below_target_roas") == []


# ---------------------------------------------------------------------------
# profitability diagnostics
# ---------------------------------------------------------------------------


def test_negative_contribution_profit_positive() -> None:
    ctx = _ctx(summary=_summary(contribution_profit=_measure("0.00")))
    finding = _only(apply_business_rules(ctx), "negative_contribution_profit")
    assert finding.status == STATUS_DETECTED
    assert finding.severity == "high"
    ctx2 = _ctx(summary=_summary(contribution_profit=_measure("-50.00")))
    assert _find(apply_business_rules(ctx2), "negative_contribution_profit") != []


def test_negative_contribution_profit_negative() -> None:
    ctx = _ctx(summary=_summary(contribution_profit=_measure("10.00")))
    assert _find(apply_business_rules(ctx), "negative_contribution_profit") == []


def test_negative_unit_margin() -> None:
    ctx = _ctx(profile={"average_contribution_profit": _money("-2.00")})
    finding = _only(apply_business_rules(ctx), "negative_unit_margin")
    assert finding.status == STATUS_DETECTED
    assert finding.severity == "high"
    ctx2 = _ctx(profile={"average_contribution_profit": _money("9.00")})
    assert _find(apply_business_rules(ctx2), "negative_unit_margin") == []


def test_declining_contribution_margin() -> None:
    current = _measure("0.20")
    previous = _summary(contribution_margin=_measure("0.40"))
    ctx = _ctx(summary=_summary(contribution_margin=current), previous=previous)
    finding = _only(apply_business_rules(ctx), "declining_contribution_margin")
    assert finding.status == STATUS_DETECTED
    # margin increased: no decline.
    ctx2 = _ctx(summary=_summary(contribution_margin=_measure("0.45")), previous=previous)
    assert _find(apply_business_rules(ctx2), "declining_contribution_margin") == []


def test_revenue_profit_divergence_positive() -> None:
    ctx = _ctx(
        summary=_summary(revenue=_measure("1200.00"), contribution_profit=_measure("170.00")),
        previous=_summary(revenue=_measure("1000.00"), contribution_profit=_measure("200.00")),
    )
    finding = _only(apply_business_rules(ctx), "revenue_profit_divergence")
    assert finding.status == STATUS_DETECTED
    assert finding.severity == "high"
    assert finding.evidence.metric.code == "revenue"
    assert finding.evidence.metric.previous == _money("1000.00")


def test_revenue_profit_divergence_negative() -> None:
    # Revenue +10% only: below the divergence threshold.
    ctx = _ctx(
        summary=_summary(revenue=_measure("1100.00"), contribution_profit=_measure("170.00")),
        previous=_summary(revenue=_measure("1000.00"), contribution_profit=_measure("200.00")),
    )
    assert _find(apply_business_rules(ctx), "revenue_profit_divergence") == []
    # Profit decline -10% only.
    ctx2 = _ctx(
        summary=_summary(revenue=_measure("1200.00"), contribution_profit=_measure("180.00")),
        previous=_summary(revenue=_measure("1000.00"), contribution_profit=_measure("200.00")),
    )
    assert _find(apply_business_rules(ctx2), "revenue_profit_divergence") == []


def test_break_even_unavailable_and_target_above_viable() -> None:
    ctx = _ctx(summary=_summary(cpa=_measure("100.00")))
    assert _find(apply_business_rules(ctx), "break_even_unavailable") != []
    ctx2 = _ctx(
        summary=_summary(cpa=_measure("100.00")),
        goal={"maximum_cpa": _money("150.00"), "target_roas": None},
        profile={"break_even_cpa_range": [_money("70.00"), _money("80.00")]},
    )
    finding = _only(apply_business_rules(ctx2), "target_cpa_above_viable")
    assert finding.status == STATUS_DETECTED
    assert finding.evidence.threshold.value == _money("80.00")


# ---------------------------------------------------------------------------
# funnel diagnostics
# ---------------------------------------------------------------------------


def test_funnel_bottleneck_positive() -> None:
    ctx = _ctx(funnel=_observed_funnel(impressions=2000, clicks=100, lpv=60, purchases=1))
    finding = _only(apply_business_rules(ctx), "funnel_bottleneck")
    assert finding.status == STATUS_DETECTED
    assert finding.evidence.funnel.from_stage == "landing_page_views"
    assert finding.evidence.funnel.to_stage == "purchases"
    assert finding.affected_stage == "purchase"
    assert finding.evidence.funnel.conversion_rate < th.value(th.FUNNEL_LOW_TRANSITION)


def test_funnel_bottleneck_negative() -> None:
    ctx = _ctx(funnel=_observed_funnel(impressions=2000, clicks=100, lpv=60, purchases=5))
    assert _find(apply_business_rules(ctx), "funnel_bottleneck") == []


def test_funnel_bottleneck_boundary() -> None:
    # rate exactly at the threshold: no bottleneck.
    ctx = _ctx(funnel=_observed_funnel(impressions=2000, clicks=100, lpv=60, purchases=3))
    assert _find(apply_business_rules(ctx), "funnel_bottleneck") == []


def test_funnel_bottleneck_insufficient_volume() -> None:
    ctx = _ctx(funnel=_observed_funnel(impressions=2000, clicks=40, lpv=30, purchases=1))
    assert _find(apply_business_rules(ctx), "funnel_bottleneck") == []


def test_low_click_to_purchase_rate_positive() -> None:
    ctx = _ctx(funnel=_observed_funnel(impressions=2000, clicks=100, lpv=60, purchases=1))
    finding = _only(apply_business_rules(ctx), "low_click_to_purchase_rate")
    assert finding.status == STATUS_DETECTED
    assert finding.reason == "intermediate funnel stages are unavailable"
    assert finding.affected_stage == "purchase"


def test_low_click_to_purchase_rate_negative() -> None:
    ctx = _ctx(funnel=_observed_funnel(impressions=2000, clicks=100, lpv=60, purchases=5))
    assert _find(apply_business_rules(ctx), "low_click_to_purchase_rate") == []


def test_low_click_to_purchase_rate_insufficient_clicks() -> None:
    ctx = _ctx(funnel=_observed_funnel(impressions=2000, clicks=10, lpv=6, purchases=1))
    assert _find(apply_business_rules(ctx), "low_click_to_purchase_rate") == []


# ---------------------------------------------------------------------------
# spend / tracking
# ---------------------------------------------------------------------------


def test_spend_without_purchase_positive() -> None:
    ctx = _ctx(summary=_summary(spend=_measure("500.00"), purchases=_measure("0")))
    finding = _only(apply_business_rules(ctx), "spend_without_purchase")
    assert finding.status == STATUS_DETECTED
    assert finding.severity == "medium"


def test_spend_without_purchase_high_when_above_economics() -> None:
    ctx = _ctx(
        summary=_summary(spend=_measure("400.00"), purchases=_measure("0")),
        profile={"break_even_cpa_range": [_money("100.00"), _money("120.00")]},
    )
    finding = _only(apply_business_rules(ctx), "spend_without_purchase")
    # 400 ≥ 120 × 3 → high.
    assert finding.severity == "high"


def test_spend_without_purchase_high_when_previous_had_purchases() -> None:
    ctx = _ctx(
        summary=_summary(spend=_measure("500.00"), purchases=_measure("0")),
        previous=_summary(spend=_measure("400.00"), purchases=_measure("6")),
    )
    finding = _only(apply_business_rules(ctx), "spend_without_purchase")
    assert finding.severity == "high"


def test_spend_without_purchase_negative_and_boundary() -> None:
    ctx = _ctx(summary=_summary(spend=_measure("100.00"), purchases=_measure("0")))
    assert _find(apply_business_rules(ctx), "spend_without_purchase") == []
    ctx2 = _ctx(summary=_summary(spend=_measure("500.00"), purchases=_measure("1")))
    assert _find(apply_business_rules(ctx2), "spend_without_purchase") == []


def test_purchase_revenue_mismatch_positive() -> None:
    ctx = _ctx(summary=_summary(purchases=_measure("4"), revenue=_measure("0.00")))
    finding = _only(apply_business_rules(ctx), "purchase_revenue_mismatch")
    assert finding.status == STATUS_DETECTED


def test_purchase_revenue_mismatch_negative() -> None:
    ctx = _ctx(summary=_summary(purchases=_measure("4"), revenue=_measure("50.00")))
    assert _find(apply_business_rules(ctx), "purchase_revenue_mismatch") == []
    ctx2 = _ctx(summary=_summary(purchases=_measure("0"), revenue=_measure("0.00")))
    assert _find(apply_business_rules(ctx2), "purchase_revenue_mismatch") == []


def test_revenue_purchase_mismatch_positive() -> None:
    ctx = _ctx(summary=_summary(revenue=_measure("100.00"), purchases=_measure("0")))
    finding = _only(apply_business_rules(ctx), "revenue_purchase_mismatch")
    assert finding.status == STATUS_DETECTED


def test_revenue_purchase_mismatch_negative() -> None:
    ctx = _ctx(summary=_summary(revenue=_measure("100.00"), purchases=_measure("3")))
    assert _find(apply_business_rules(ctx), "revenue_purchase_mismatch") == []


def test_provider_conversion_mismatch_positive() -> None:
    ctx = _ctx(summary=_summary(conversions=_measure("12"), purchases=_measure("4")))
    finding = _only(apply_business_rules(ctx), "provider_conversion_mismatch")
    assert finding.status == STATUS_DETECTED
    assert finding.category == "tracking"


def test_provider_conversion_mismatch_boundary() -> None:
    # exactly 50% = 50% → fires (gte).
    ctx = _ctx(summary=_summary(conversions=_measure("6"), purchases=_measure("4")))
    assert _find(apply_business_rules(ctx), "provider_conversion_mismatch") != []
    # 25% → does not fire.
    ctx2 = _ctx(summary=_summary(conversions=_measure("5"), purchases=_measure("4")))
    assert _find(apply_business_rules(ctx2), "provider_conversion_mismatch") == []


def test_provider_conversion_mismatch_missing_sides() -> None:
    ctx = _ctx(summary=_summary(conversions=_measure(None, STATUS_UNAVAILABLE)))
    assert _find(apply_business_rules(ctx), "provider_conversion_mismatch") == []


# ---------------------------------------------------------------------------
# data quality
# ---------------------------------------------------------------------------


def _quality(meta_status: str, shopify_status: str, **overrides) -> dict:
    providers = [
        {
            "provider": "meta",
            "freshness_status": meta_status,
            "reason": None,
            "connected": True,
            "coverage_start": date(2026, 8, 1),
            "coverage_end": date(2026, 8, 6),
            "covered_days": 6,
            "missing_days": 1,
        },
        {
            "provider": "shopify",
            "freshness_status": shopify_status,
            "reason": None,
            "connected": True,
            "coverage_start": date(2026, 8, 1),
            "coverage_end": date(2026, 8, 7),
            "covered_days": 7,
            "missing_days": 0,
        },
    ]
    return {"providers": providers}


def test_stale_data_positive() -> None:
    ctx = _ctx(quality=_quality("stale", "fresh"))
    findings = apply_business_rules(ctx)
    stale = _only(findings, "stale_meta_data")
    assert stale.status == STATUS_DETECTED
    assert stale.severity == "medium"
    assert _find(findings, "stale_shopify_data") == []


def test_stale_data_negative() -> None:
    ctx = _ctx(quality=_quality("fresh", "fresh"))
    findings = apply_business_rules(ctx)
    assert _find(findings, "stale_meta_data") == []
    assert _find(findings, "stale_shopify_data") == []


def test_delayed_data() -> None:
    ctx = _ctx(quality=_quality("delayed", "fresh"))
    findings = apply_business_rules(ctx)
    assert _only(findings, "delayed_meta_data").severity == "low"


def test_incomplete_reporting_period() -> None:
    quality = _quality("fresh", "fresh")
    quality["providers"][0]["missing_days"] = 3
    ctx = _ctx(quality=quality)
    finding = _only(apply_business_rules(ctx), "incomplete_reporting_period")
    assert finding.status == STATUS_DETECTED
    # boundary: 2 missing days is the minimum → fires; 1 does not.
    quality2 = _quality("fresh", "fresh")
    quality2["providers"][0]["missing_days"] = 2
    ctx2 = _ctx(quality=quality2)
    assert _find(apply_business_rules(ctx2), "incomplete_reporting_period") != []
    assert _find(apply_business_rules(ctx), "incomplete_reporting_period") != []


def test_provider_not_connected() -> None:
    quality = {"providers": [
        {"provider": "meta", "freshness_status": "unavailable", "reason": "not connected",
         "connected": False, "covered_days": None, "missing_days": None},
        {"provider": "shopify", "freshness_status": "fresh", "reason": None,
         "connected": True, "covered_days": 7, "missing_days": 0},
    ]}
    finding = _only(apply_business_rules(_ctx(quality=quality)), "meta_not_connected")
    assert finding.severity == "info"


def test_unobserved_funnel_stages() -> None:
    ctx = _ctx(funnel=_observed_funnel())
    finding = _only(apply_business_rules(ctx), "unobserved_funnel_stages")
    assert finding.severity == "info"
    assert finding.affected_stage == "intent"


def test_recent_sync_failures() -> None:
    ctx = _ctx(sync_failures=2)
    finding = _only(apply_business_rules(ctx), "recent_sync_failures")
    assert finding.status == STATUS_DETECTED
    ctx2 = _ctx(sync_failures=0)
    assert _find(apply_business_rules(ctx2), "recent_sync_failures") == []


# ---------------------------------------------------------------------------
# persistent unprofitable performance (no kill/scale action — review only)
# ---------------------------------------------------------------------------


def test_persistent_unprofitable_business_roas_path() -> None:
    ctx = _ctx(
        summary=_summary(roas=_measure("0.8"), spend=_measure("500.00"), purchases=_measure("10")),
        previous=_summary(roas=_measure("0.9"), spend=_measure("400.00"), purchases=_measure("9")),
        profile={"break_even_roas": _money("1.5")},
    )
    finding = _only(apply_business_rules(ctx), "persistent_unprofitable_performance")
    assert finding.status == STATUS_DETECTED
    assert finding.severity == "high"
    assert finding.review_status == REVIEW_REQUIRED


def test_persistent_unprofitable_business_cpa_path() -> None:
    ctx = _ctx(
        summary=_summary(
            cpa=_measure("200.00"), spend=_measure("500.00"), purchases=_measure("10")
        ),
        previous=_summary(
            cpa=_measure("180.00"), spend=_measure("400.00"), purchases=_measure("9")
        ),
        goal={"maximum_cpa": _money("120.00"), "target_roas": None},
    )
    finding = _only(apply_business_rules(ctx), "persistent_unprofitable_performance")
    assert finding.review_status == REVIEW_REQUIRED
    assert finding.evidence.metric.code == "cpa"


def test_persistent_unprofitable_negative() -> None:
    ctx = _ctx(
        summary=_summary(roas=_measure("1.6"), spend=_measure("500.00"), purchases=_measure("10")),
        previous=_summary(roas=_measure("1.7"), spend=_measure("400.00"), purchases=_measure("9")),
        profile={"break_even_roas": _money("1.5")},
    )
    assert _find(apply_business_rules(ctx), "persistent_unprofitable_performance") == []


def test_persistent_unprofitable_boundary_and_sample() -> None:
    # roas exactly at break-even → not persistent (strict <).
    ctx = _ctx(
        summary=_summary(roas=_measure("1.5"), spend=_measure("500.00"), purchases=_measure("10")),
        previous=_summary(roas=_measure("1.4"), spend=_measure("400.00"), purchases=_measure("9")),
        profile={"break_even_roas": _money("1.5")},
    )
    assert _find(apply_business_rules(ctx), "persistent_unprofitable_performance") == []
    # tiny spend: sample gate blocks the finding entirely.
    ctx2 = _ctx(
        summary=_summary(roas=_measure("0.8"), spend=_measure("50.00"), purchases=_measure("10")),
        previous=_summary(roas=_measure("0.9"), spend=_measure("40.00"), purchases=_measure("9")),
        profile={"break_even_roas": _money("1.5")},
    )
    assert _find(apply_business_rules(ctx2), "persistent_unprofitable_performance") == []


# ---------------------------------------------------------------------------
# entity-level rules
# ---------------------------------------------------------------------------


def test_entity_low_ctr_and_sample_protection() -> None:
    entity = _campaign_entity(metrics=_entity_metrics(ctr=_measure("0.005")))
    findings = apply_entity_rules(_ctx(), entity)
    finding = _only(findings, "low_ctr")
    assert finding.entity_type == ENTITY_TYPE_CAMPAIGN
    assert finding.entity_id == CAMPAIGN_ID
    assert finding.entity_name == "Campaign A"
    # tiny sample on the entity: insufficient_data, never a performance finding.
    tiny = _campaign_entity(
        metrics=_entity_metrics(impressions=12, clicks=0, ctr=_measure("0.005"))
    )
    tiny_finding = _only(apply_entity_rules(_ctx(), tiny), "low_ctr")
    assert tiny_finding.status == STATUS_INSUFFICIENT_DATA


def test_entity_below_break_even_roas() -> None:
    entity = _campaign_entity(metrics=_entity_metrics(roas=_measure("0.8")))
    ctx = _ctx(profile={"break_even_roas": _money("1.5")})
    finding = _only(apply_entity_rules(ctx, entity), "below_break_even_roas")
    assert finding.entity_type == ENTITY_TYPE_CAMPAIGN
    assert finding.severity == "high"


def test_entity_ctr_decline() -> None:
    entity = _campaign_entity(
        metrics=_entity_metrics(ctr=_measure("0.004")),
        previous=_entity_metrics(ctr=_measure("0.011")),
    )
    finding = _only(apply_entity_rules(_ctx(), entity), "ctr_decline")
    assert finding.status == STATUS_DETECTED


def test_creative_rules_apply_only_to_ads() -> None:
    ad = _ad_entity(metrics=_entity_metrics(ctr=_measure("0.005")))
    findings = apply_entity_rules(_ctx(), ad)
    creative = _only(findings, "creative_low_ctr")
    assert creative.category == CATEGORY_CREATIVE
    assert creative.entity_type == ENTITY_TYPE_AD
    assert creative.affected_stage == "awareness"
    # Possible fatigue: high frequency + CTR decline + active spend.
    fatigued = _ad_entity(
        metrics=_entity_metrics(impressions=10000, reach=2000, spend=_money("300.00"),
                                ctr=_measure("0.004")),
        previous=_entity_metrics(reach=4000, ctr=_measure("0.011")),
    )
    fatigue = _only(apply_entity_rules(_ctx(), fatigued), "possible_creative_fatigue")
    assert fatigue.status == STATUS_DETECTED
    assert fatigue.severity == "medium"


def test_creative_fatigue_negative_without_frequency() -> None:
    calm = _ad_entity(
        metrics=_entity_metrics(impressions=10000, reach=8000, spend=_money("300.00"),
                                ctr=_measure("0.004")),
        previous=_entity_metrics(reach=8000, ctr=_measure("0.011")),
    )
    assert _find(apply_entity_rules(_ctx(), calm), "possible_creative_fatigue") == []


def test_entity_persistent_unprofitable() -> None:
    entity = _campaign_entity(
        metrics=_entity_metrics(roas=_measure("0.8"), spend=_money("500.00")),
        previous=_entity_metrics(roas=_measure("0.9")),
        rows=14,
    )
    ctx = _ctx(profile={"break_even_roas": _money("1.5")})
    finding = _only(apply_entity_rules(ctx, entity), "persistent_unprofitable_performance")
    assert finding.review_status == REVIEW_REQUIRED
    # single-day entity: not persistent.
    single_day = _campaign_entity(
        metrics=_entity_metrics(roas=_measure("0.8"), spend=_money("500.00")),
        previous=_entity_metrics(roas=_measure("0.9")),
        rows=1,
    )
    assert _find(apply_entity_rules(ctx, single_day), "persistent_unprofitable_performance") == []


# ---------------------------------------------------------------------------
# multiple findings, deduplication, separation of concerns
# ---------------------------------------------------------------------------


def test_multiple_findings_are_not_overwritten() -> None:
    ctx = _ctx(
        summary=_summary(ctr=_measure("0.004"), cpc=_measure("15.00"),
                         cpa=_measure("184.00"), purchases=_measure("14")),
        goal={"maximum_cpa": _money("120.00"), "target_roas": None},
    )
    findings = apply_business_rules(ctx)
    codes = {f.code for f in findings}
    assert {"low_ctr", "high_cpc", "high_cpa"} <= codes


def test_fingerprints_are_stable_and_unique() -> None:
    ctx = _ctx(summary=_summary(ctr=_measure("0.004")))
    first = _only(apply_business_rules(ctx), "low_ctr")
    second = _only(apply_business_rules(ctx), "low_ctr")
    assert first.id == second.id
    # Entity-level low_ctr has a distinct fingerprint from the business one.
    entity = _campaign_entity(metrics=_entity_metrics(ctr=_measure("0.004")))
    entity_finding = _only(apply_entity_rules(ctx, entity), "low_ctr")
    assert entity_finding.id != first.id


def test_low_ctr_entity_variants_have_distinct_ids() -> None:
    ctx = _ctx(summary=_summary(ctr=_measure("0.004")))
    campaign = _campaign_entity(metrics=_entity_metrics(ctr=_measure("0.004")))
    ad = _ad_entity(metrics=_entity_metrics(ctr=_measure("0.004")))
    campaign_finding = _only(apply_entity_rules(ctx, campaign), "low_ctr")
    ad_finding = _only(apply_entity_rules(ctx, ad), "low_ctr")
    assert campaign_finding.id != ad_finding.id


# ---------------------------------------------------------------------------
# performance states (campaign)
# ---------------------------------------------------------------------------


def _state_ctx(**overrides) -> RuleContext:
    return _ctx(profile={"break_even_roas": _money("1.5")}, **overrides)


def test_performance_state_order() -> None:
    ctx = _state_ctx()
    # No facts.
    no_facts = _campaign_entity(rows=0)
    assert engine._performance_state(ctx, no_facts, []) == "insufficient_data"
    # Below sample: learning.
    learning = _campaign_entity(metrics=_entity_metrics(spend=_money("50.00")))
    assert engine._performance_state(ctx, learning, []) == "learning"
    # Unprofitable: roas below break-even.
    unprofitable = _campaign_entity(metrics=_entity_metrics(roas=_measure("0.8")))
    assert engine._performance_state(ctx, unprofitable, []) == "unprofitable"
    # Profitable: roas at/above break-even.
    profitable = _campaign_entity(metrics=_entity_metrics(roas=_measure("2.0")))
    assert engine._performance_state(ctx, profitable, []) == "profitable"


def test_performance_state_attention_and_inefficient() -> None:
    ctx = _state_ctx(goal={"maximum_cpa": None, "target_roas": _money("2.5")})
    below_target = _campaign_entity(metrics=_entity_metrics(roas=_measure("2.0")))
    findings = apply_entity_rules(ctx, below_target)
    state = engine._performance_state(ctx, below_target, findings)
    # below_target_roas is a medium finding → attention (not unprofitable).
    assert state == "attention"

    inefficient = _campaign_entity(metrics=_entity_metrics(roas=_measure("2.0"),
                                                           ctr=_measure("0.004"),
                                                           cpc=_measure("15.00")))
    ine_findings = apply_entity_rules(ctx, inefficient)
    # two traffic findings (low_ctr + high_cpc) not profitable-needing →
    # state: inefficient requires ≥2 traffic/creative findings.
    assert sum(1 for f in ine_findings if f.code in ("low_ctr", "high_cpc")) >= 2
    assert engine._performance_state(ctx, inefficient, ine_findings) == "inefficient"


def test_performance_state_healthy() -> None:
    ctx = _state_ctx()
    healthy = _campaign_entity(metrics=_entity_metrics(roas=_measure(None, STATUS_UNAVAILABLE),
                                                       spend=_money("500.00")))
    assert engine._performance_state(ctx, healthy, []) == "healthy"


def test_performance_state_stale_data() -> None:
    ctx = _state_ctx(quality=_quality("stale", "fresh"))
    entity = _campaign_entity(metrics=_entity_metrics(roas=_measure("2.0")))
    assert engine._performance_state(ctx, entity, []) == "stale_data"


# ---------------------------------------------------------------------------
# scaling readiness (informational only)
# ---------------------------------------------------------------------------


def _scaling_gates_entity() -> EntityContext:
    return _campaign_entity(
        metrics=_entity_metrics(impressions=20000, spend=_money("1000.00"), conversions=10,
                                roas=_measure("2.0")),
        rows=10,
    )


def test_scaling_readiness_insufficient_evidence() -> None:
    ctx = _state_ctx()
    low_spend = _campaign_entity(metrics=_entity_metrics(impressions=20000,
                                                         spend=_money("50.00"), conversions=10))
    readiness = engine._scaling_readiness(ctx, low_spend, [])
    assert readiness["status"] == "insufficient_data"
    assert readiness["ready_for_review"] is False


def test_scaling_readiness_positive_review() -> None:
    ctx = _state_ctx()
    readiness = engine._scaling_readiness(ctx, _scaling_gates_entity(), [])
    assert readiness["status"] == "performance_positive"
    assert readiness["ready_for_review"] is True


def test_scaling_readiness_negative() -> None:
    ctx = _state_ctx()
    entity = _campaign_entity(
        metrics=_entity_metrics(impressions=20000, spend=_money("1000.00"), conversions=10,
                                roas=_measure("1.0")),
        rows=10,
    )
    readiness = engine._scaling_readiness(ctx, entity, [])
    assert readiness["status"] == "performance_negative"
    assert readiness["ready_for_review"] is False


def test_scaling_readiness_blocked_by_high_findings() -> None:
    ctx = _state_ctx()
    entity = _scaling_gates_entity()
    from src.modules.diagnostics.evidence import (
        CATEGORY_TRAFFIC,
        Evidence,
        Finding,
        MetricEvidence,
    )

    blocking = Finding(
        id="x", business_id=BUSINESS_ID, business_name="Test", entity_type=ENTITY_TYPE_CAMPAIGN,
        entity_id=CAMPAIGN_ID, entity_name="Campaign A", category=CATEGORY_TRAFFIC,
        code="low_ctr", severity="high", status=STATUS_DETECTED,
        title_key="diagnostics.low_ctr.title", description_key="diagnostics.low_ctr.description",
        reason=None, evidence=Evidence(metric=MetricEvidence("ctr", Decimal("0.001"))),
        affected_stage="awareness", range_start=_range().start, range_end=_range().end,
        currency="USD",
    )
    readiness = engine._scaling_readiness(ctx, entity, [blocking])
    assert readiness["status"] == "performance_positive"
    assert readiness["ready_for_review"] is False