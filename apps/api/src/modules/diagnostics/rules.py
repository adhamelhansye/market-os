"""Deterministic diagnostic rules (Phase 3B).

Every rule is PURE: it receives a `RuleContext` (measures already computed
by the metrics/KPI layer) and an optional `EntityContext`, evaluates
thresholds from the centralized registry (thresholds.py) and returns either
a structured `Finding` or None. No database access, no provider API calls,
no LLM.

Rule discipline:

- A finding only fires when its sample-size gate passes: below the
  registry minima the same code is returned with status
  `insufficient_data` — tiny samples never produce performance findings.
- Zero and unavailable stay distinct (impressions=1000/clicks=0 → CTR is a
  real 0 and may legitimately fire low-CTR; impressions=0 → CTR unavailable
  and nothing is invented).
- Relative rules compare against the previous period only when both values
  are available; percentage changes are never fabricated.
- The engine never claims causality: findings state observed conditions
  (e.g. "possible creative fatigue signal", never "creative is fatigued").
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from src.modules.diagnostics import thresholds as th
from src.modules.diagnostics.evidence import (
    CATEGORY_CONVERSION,
    CATEGORY_CREATIVE,
    CATEGORY_DATA_QUALITY,
    CATEGORY_ECONOMICS,
    CATEGORY_FUNNEL,
    CATEGORY_PERFORMANCE,
    CATEGORY_TRACKING,
    CATEGORY_TRAFFIC,
    ENTITY_TYPE_AD,
    ENTITY_TYPE_AD_SET,
    ENTITY_TYPE_BUSINESS,
    ENTITY_TYPE_CAMPAIGN,
    REVIEW_REQUIRED,
    STATUS_DETECTED,
    STATUS_INSUFFICIENT_DATA,
    ComparisonEvidence,
    Evidence,
    Fact,
    Finding,
    FunnelEvidence,
    MetricEvidence,
    ThresholdEvidence,
    finding_fingerprint,
)
from src.modules.diagnostics.severity import (
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_INFO,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
)
from src.modules.metrics.aggregation import Range
from src.modules.metrics.definitions import (
    FUNNEL_AWARENESS,
    FUNNEL_INTENT,
    FUNNEL_PURCHASE,
    FUNNEL_TRAFFIC,
)
from src.modules.metrics.kpi_engine import STATUS_AVAILABLE, STATUS_UNAVAILABLE

PROVIDER_META = "meta"
PROVIDER_SHOPIFY = "shopify"

# Funnel stage -> funnel group (mirrors metrics.definitions.FUNNEL_*).
FUNNEL_GROUPS = {
    "impressions": FUNNEL_AWARENESS,
    "clicks": FUNNEL_TRAFFIC,
    "landing_page_views": FUNNEL_TRAFFIC,
    "product_views": FUNNEL_INTENT,
    "add_to_cart": FUNNEL_INTENT,
    "checkout_started": FUNNEL_INTENT,
    "purchases": FUNNEL_PURCHASE,
}

_UNOBSERVED_FUNNEL_STAGES = ("product_views", "add_to_cart", "checkout_started")


@dataclass
class RuleContext:
    """Everything a rule may read — all values come from the metrics layer."""

    business_id: uuid.UUID
    business_name: str
    currency: str
    timezone: str
    range: Range
    profile: dict
    goal: dict | None
    summary: dict
    previous_summary: dict | None
    funnel: dict | None
    previous_funnel: dict | None
    quality: dict | None
    sync_failures: int


@dataclass
class EntityContext:
    """An entity rollup (campaign/ad_set/ad) with its previous-period view."""

    entity_type: str
    entity_id: uuid.UUID | None
    entity_name: str | None
    metrics: dict
    previous_metrics: dict | None
    rows: int
    range_length_days: int


def _dec(value) -> Decimal | None:
    """Coerce measure/raw serialized values (str/Decimal/int) to Decimal."""
    if value is None:
        return None
    return Decimal(str(value))


def _val(measure: dict | None) -> Decimal | None:
    if not measure or measure.get("status") != STATUS_AVAILABLE:
        return None
    return _dec(measure.get("value"))


def _raw(ctx: RuleContext, entity: EntityContext | None, code: str):
    """Raw fact (count/money) for entity or business scope."""
    if entity is not None:
        return _dec(entity.metrics.get(code))
    return _val(ctx.summary.get(code))


def _kpi_measure(ctx: RuleContext, entity: EntityContext | None, code: str) -> dict | None:
    if entity is not None:
        return entity.metrics.get(code)
    return ctx.summary.get(code)


def _prev_summary(ctx: RuleContext) -> dict | None:
    return ctx.previous_summary


def _prev_raw_entity(entity: EntityContext | None, code: str):
    if entity is None or entity.previous_metrics is None:
        return None
    return _dec(entity.previous_metrics.get(code))


def _prev_kpi_entity(ctx: RuleContext, entity: EntityContext | None, code: str) -> dict | None:
    if entity is None or entity.previous_metrics is None:
        return None
    return entity.previous_metrics.get(code)


def _prev_measure(ctx: RuleContext, entity: EntityContext | None, code: str) -> dict | None:
    """Previous-period KPI measure for business or entity scope."""
    if entity is not None:
        return _prev_kpi_entity(ctx, entity, code)
    previous = _prev_summary(ctx)
    if previous is None:
        return None
    return previous.get(code)


def _finding(
    ctx: RuleContext,
    *,
    code: str,
    category: str,
    severity: str,
    entity: EntityContext | None = None,
    evidence: Evidence | None = None,
    reason: str | None = None,
    affected_stage: str | None = None,
    review_status: str | None = None,
    status: str = STATUS_DETECTED,
) -> Finding:
    entity_type = entity.entity_type if entity else ENTITY_TYPE_BUSINESS
    entity_id = entity.entity_id if entity else None
    entity_name = entity.entity_name if entity else None
    return Finding(
        id=finding_fingerprint(
            business_id=ctx.business_id,
            entity_type=entity_type,
            entity_id=entity_id,
            code=code,
            range_start=ctx.range.start,
            range_end=ctx.range.end,
        ),
        business_id=ctx.business_id,
        business_name=ctx.business_name,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name,
        category=category,
        code=code,
        severity=severity,
        status=status,
        title_key=f"diagnostics.{code}.title",
        description_key=f"diagnostics.{code}.description",
        reason=reason,
        evidence=evidence or Evidence(),
        affected_stage=affected_stage,
        range_start=ctx.range.start,
        range_end=ctx.range.end,
        currency=ctx.currency,
        review_status=review_status,
    )


def _insufficient(
    ctx: RuleContext,
    *,
    code: str,
    category: str,
    entity: EntityContext | None,
    metric_code: str,
    observed,
    minimum: Decimal,
    threshold_code: str,
    unit: str = "count",
) -> Finding:
    reason = f"insufficient {metric_code} sample: {observed} < {minimum}"
    observed_decimal = Decimal(observed) if observed is not None else None
    return _finding(
        ctx,
        code=code,
        category=category,
        entity=entity,
        severity=SEVERITY_INFO,
        status=STATUS_INSUFFICIENT_DATA,
        reason=reason,
        evidence=Evidence(
            metric=MetricEvidence(metric_code, observed_decimal),
            threshold=ThresholdEvidence(
                code=threshold_code, operator="lt", value=minimum, unit=unit
            ),
        ),
    )


def _declined_percent(current: Decimal | None, previous: Decimal | None) -> Decimal | None:
    """Relative decline (negative = growth). None when not computable."""
    if current is None or previous is None or previous == Decimal("0"):
        return None
    return (previous - current) / abs(previous) * Decimal("100")


def _trend_threshold(
    code: str, threshold_operator: str, unit: str = "percent"
) -> ThresholdEvidence:
    return ThresholdEvidence(
        code=code, operator=threshold_operator, value=th.value(code), unit=unit
    )


def _measure_evidence(code: str, current: Decimal | None, previous: Decimal | None) -> Evidence:
    return Evidence(
        metric=MetricEvidence(code, current, previous),
        comparison=ComparisonEvidence.of(current, previous),
    )


# ---------------------------------------------------------------------------
# Traffic
# ---------------------------------------------------------------------------


def low_ctr(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    impressions = _raw(ctx, entity, "impressions")
    minimum = th.value(th.SAMPLE_MIN_IMPRESSIONS)
    if impressions is None:
        return _insufficient(
            ctx, code="low_ctr", category=CATEGORY_TRAFFIC, entity=entity,
            metric_code="impressions", observed=None, minimum=minimum,
            threshold_code=th.SAMPLE_MIN_IMPRESSIONS,
        )
    if Decimal(impressions) < minimum:
        return _insufficient(
            ctx, code="low_ctr", category=CATEGORY_TRAFFIC, entity=entity,
            metric_code="impressions", observed=impressions, minimum=minimum,
            threshold_code=th.SAMPLE_MIN_IMPRESSIONS,
        )
    ctr_measure = _kpi_measure(ctx, entity, "ctr")
    ctr_value = _val(ctr_measure)
    if ctr_measure is None or ctr_measure.get("status") != STATUS_AVAILABLE:
        return None
    ctr_low = th.value(th.CTR_LOW)
    ctr_critical = th.value(th.CTR_CRITICAL)
    if ctr_value is None or ctr_value >= ctr_low:
        return None
    severity = SEVERITY_HIGH if ctr_value < ctr_critical else SEVERITY_LOW
    return _finding(
        ctx,
        code="low_ctr",
        category=CATEGORY_TRAFFIC,
        entity=entity,
        severity=severity,
        affected_stage=FUNNEL_AWARENESS,
        evidence=Evidence(
            metric=MetricEvidence("ctr", ctr_value),
            threshold=ThresholdEvidence(code=th.CTR_LOW, operator="lt", value=ctr_low),
            facts=(Fact("impressions", Decimal(impressions)),),
        ),
    )


def ctr_decline(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    impressions = _raw(ctx, entity, "impressions")
    current = _val(_kpi_measure(ctx, entity, "ctr"))
    previous = _val(_prev_measure(ctx, entity, "ctr"))
    if current is None or previous is None or previous == Decimal("0"):
        return None
    if impressions is not None and Decimal(impressions) < th.value(th.SAMPLE_MIN_IMPRESSIONS):
        return None
    decline = _declined_percent(current, previous)
    minimum = th.value(th.DECLINE_PERCENT)
    if decline is None or decline < minimum:
        return None
    return _finding(
        ctx,
        code="ctr_decline",
        category=CATEGORY_TRAFFIC,
        entity=entity,
        severity=SEVERITY_MEDIUM,
        affected_stage=FUNNEL_AWARENESS,
        evidence=Evidence(
            metric=MetricEvidence("ctr", current, previous),
            comparison=ComparisonEvidence.of(current, previous),
            threshold=_trend_threshold(th.DECLINE_PERCENT, "gte"),
        ),
    )


def high_cpc(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    clicks = _raw(ctx, entity, "clicks")
    minimum = th.value(th.SAMPLE_MIN_CLICKS)
    if clicks is None or Decimal(clicks) < minimum:
        return _insufficient(
            ctx, code="high_cpc", category=CATEGORY_TRAFFIC, entity=entity,
            metric_code="clicks", observed=clicks, minimum=minimum,
            threshold_code=th.SAMPLE_MIN_CLICKS,
        )
    cpc_measure = _kpi_measure(ctx, entity, "cpc")
    cpc_value = _val(cpc_measure)
    if cpc_measure is None or cpc_measure.get("status") != STATUS_AVAILABLE:
        return None
    cpc_high = th.value(th.CPC_HIGH)
    if cpc_value is None or cpc_value <= cpc_high:
        return None
    return _finding(
        ctx,
        code="high_cpc",
        category=CATEGORY_TRAFFIC,
        entity=entity,
        severity=SEVERITY_LOW,
        evidence=Evidence(
            metric=MetricEvidence("cpc", cpc_value),
            threshold=ThresholdEvidence(
                code=th.CPC_HIGH, operator="gt", value=cpc_high, unit=th.UNIT_MONEY
            ),
            facts=(Fact("clicks", Decimal(clicks)),),
        ),
    )


def high_cpm(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    impressions = _raw(ctx, entity, "impressions")
    minimum = th.value(th.SAMPLE_MIN_IMPRESSIONS)
    if impressions is None or Decimal(impressions) < minimum:
        return _insufficient(
            ctx, code="high_cpm", category=CATEGORY_TRAFFIC, entity=entity,
            metric_code="impressions", observed=impressions, minimum=minimum,
            threshold_code=th.SAMPLE_MIN_IMPRESSIONS,
        )
    cpm_measure = _kpi_measure(ctx, entity, "cpm")
    cpm_value = _val(cpm_measure)
    if cpm_measure is None or cpm_measure.get("status") != STATUS_AVAILABLE:
        return None
    cpm_high = th.value(th.CPM_HIGH)
    if cpm_value is None or cpm_value <= cpm_high:
        return None
    return _finding(
        ctx,
        code="high_cpm",
        category=CATEGORY_TRAFFIC,
        entity=entity,
        severity=SEVERITY_LOW,
        evidence=Evidence(
            metric=MetricEvidence("cpm", cpm_value),
            threshold=ThresholdEvidence(
                code=th.CPM_HIGH, operator="gt", value=cpm_high, unit=th.UNIT_MONEY
            ),
            facts=(Fact("impressions", Decimal(impressions)),),
        ),
    )


# ---------------------------------------------------------------------------
# Creative (objective performance indicators only — never "bad creative")
# ---------------------------------------------------------------------------


def creative_low_ctr(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    if entity is None or entity.entity_type != ENTITY_TYPE_AD:
        return None
    impressions = _raw(ctx, entity, "impressions")
    minimum = th.value(th.SAMPLE_MIN_IMPRESSIONS)
    if impressions is None or Decimal(impressions) < minimum:
        return _insufficient(
            ctx, code="creative_low_ctr", category=CATEGORY_CREATIVE, entity=entity,
            metric_code="impressions", observed=impressions, minimum=minimum,
            threshold_code=th.SAMPLE_MIN_IMPRESSIONS,
        )
    ctr_value = _val(_kpi_measure(ctx, entity, "ctr"))
    ctr_low = th.value(th.CTR_LOW)
    if ctr_value is None or ctr_value >= ctr_low:
        return None
    return _finding(
        ctx,
        code="creative_low_ctr",
        category=CATEGORY_CREATIVE,
        entity=entity,
        severity=SEVERITY_MEDIUM,
        affected_stage=FUNNEL_AWARENESS,
        evidence=Evidence(
            metric=MetricEvidence("ctr", ctr_value),
            threshold=ThresholdEvidence(code=th.CTR_LOW, operator="lt", value=ctr_low),
            facts=(Fact("impressions", Decimal(impressions)),),
        ),
    )


def possible_creative_fatigue(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    """Signal, not certainty: high frequency + CTR decline + active spend."""
    if entity is None or entity.entity_type != ENTITY_TYPE_AD:
        return None
    spend = _raw(ctx, entity, "spend")
    impressions = _raw(ctx, entity, "impressions")
    reach = _raw(ctx, entity, "reach")
    current_ctr = _val(_kpi_measure(ctx, entity, "ctr"))
    previous_ctr = _val(_prev_kpi_entity(ctx, entity, "ctr"))
    past = entity.previous_metrics
    previous_reach = past.get("reach") if past else None

    minimum = th.value(th.SAMPLE_MIN_IMPRESSIONS)
    if impressions is None or reach is None or Decimal(impressions) < minimum:
        return None
    if Decimal(reach) == Decimal("0"):
        return None
    frequency = Decimal(impressions) / Decimal(reach)
    frequency_high = th.value(th.FREQUENCY_HIGH)
    if frequency < frequency_high:
        return None
    if Decimal(spend if spend is not None else 0) == Decimal("0"):
        return None
    if previous_ctr is None or previous_reach is None:
        return None
    if Decimal(previous_reach) == Decimal("0"):
        return None
    previous_frequency = Decimal(impressions) / Decimal(previous_reach)
    decline = _declined_percent(current_ctr, previous_ctr)
    minimum_decline = th.value(th.DECLINE_PERCENT)
    if previous_frequency >= frequency or decline is None or decline < minimum_decline:
        return None
    return _finding(
        ctx,
        code="possible_creative_fatigue",
        category=CATEGORY_CREATIVE,
        entity=entity,
        severity=SEVERITY_MEDIUM,
        affected_stage=FUNNEL_AWARENESS,
        evidence=Evidence(
            metric=MetricEvidence("ctr", current_ctr, previous_ctr),
            comparison=ComparisonEvidence.of(current_ctr, previous_ctr),
            threshold=ThresholdEvidence(
                code=th.FREQUENCY_HIGH, operator="gte", value=frequency_high,
                unit=th.UNIT_MULTIPLIER,
            ),
            facts=(
                Fact("frequency", frequency, th.UNIT_MULTIPLIER),
                Fact("spend", Decimal(spend or 0), "money"),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Conversion (business-level: purchases are not attributed at ad grain)
# ---------------------------------------------------------------------------


def low_cvr(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    if entity is not None:
        return None
    clicks = _raw(ctx, entity, "clicks")
    minimum = th.value(th.SAMPLE_MIN_CLICKS)
    if clicks is None or Decimal(clicks) < minimum:
        return _insufficient(
            ctx, code="low_cvr", category=CATEGORY_CONVERSION, entity=entity,
            metric_code="clicks", observed=clicks, minimum=minimum,
            threshold_code=th.SAMPLE_MIN_CLICKS,
        )
    cvr_measure = _kpi_measure(ctx, entity, "cvr")
    cvr_value = _val(cvr_measure)
    if cvr_measure is None or cvr_measure.get("status") != STATUS_AVAILABLE:
        return None
    cvr_low = th.value(th.CVR_LOW)
    if cvr_value is None or cvr_value >= cvr_low:
        return None
    severity = SEVERITY_HIGH if cvr_value * Decimal("2") < cvr_low else SEVERITY_MEDIUM
    return _finding(
        ctx,
        code="low_cvr",
        category=CATEGORY_CONVERSION,
        entity=entity,
        severity=severity,
        affected_stage=FUNNEL_PURCHASE,
        evidence=Evidence(
            metric=MetricEvidence("cvr", cvr_value),
            threshold=ThresholdEvidence(code=th.CVR_LOW, operator="lt", value=cvr_low),
            facts=(Fact("clicks", Decimal(clicks)),),
        ),
    )


def cvr_decline(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    if entity is not None:
        return None
    current = _val(_kpi_measure(ctx, entity, "cvr"))
    previous = _val(_prev_summary(ctx).get("cvr")) if _prev_summary(ctx) else None
    if current is None or previous is None or previous == Decimal("0"):
        return None
    decline = _declined_percent(current, previous)
    minimum = th.value(th.DECLINE_PERCENT)
    if decline is None or decline < minimum:
        return None
    return _finding(
        ctx,
        code="cvr_decline",
        category=CATEGORY_CONVERSION,
        entity=entity,
        severity=SEVERITY_MEDIUM,
        affected_stage=FUNNEL_PURCHASE,
        evidence=Evidence(
            metric=MetricEvidence("cvr", current, previous),
            comparison=ComparisonEvidence.of(current, previous),
            threshold=_trend_threshold(th.DECLINE_PERCENT, "gte"),
        ),
    )


def _cpa_target(ctx: RuleContext) -> tuple[Decimal | None, str | None]:
    """Target CPA: business goal when set, else break-even CPA (never invented)."""
    if ctx.goal and ctx.goal.get("maximum_cpa") is not None:
        return ctx.goal["maximum_cpa"], "business goal"
    break_even = ctx.profile.get("break_even_cpa_range")
    if break_even:
        return Decimal(break_even[1]), "break-even CPA (upper bound of range)"
    return None, None


def high_cpa(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    if entity is not None:
        return None
    purchases = _raw(ctx, entity, "purchases")
    minimum = th.value(th.SAMPLE_MIN_PURCHASES)
    if purchases is None or Decimal(purchases) < minimum:
        return _insufficient(
            ctx, code="high_cpa", category=CATEGORY_CONVERSION, entity=entity,
            metric_code="purchases", observed=purchases, minimum=minimum,
            threshold_code=th.SAMPLE_MIN_PURCHASES,
        )
    cpa_value = _val(_kpi_measure(ctx, entity, "cpa"))
    if cpa_value is None:
        return None
    target, _source = _cpa_target(ctx)
    if target is None or target == Decimal("0"):
        return None  # no goal, no economics: never invent a target
    if cpa_value <= target:
        return None
    high_multiplier = th.value(th.CPA_OVER_TARGET_HIGH)
    critical_multiplier = th.value(th.CPA_OVER_TARGET_CRITICAL)
    if cpa_value >= target * critical_multiplier:
        severity = SEVERITY_CRITICAL
    elif cpa_value >= target * high_multiplier:
        severity = SEVERITY_HIGH
    else:
        severity = SEVERITY_MEDIUM
    return _finding(
        ctx,
        code="high_cpa",
        category=CATEGORY_CONVERSION,
        entity=entity,
        severity=severity,
        affected_stage=FUNNEL_PURCHASE,
        evidence=Evidence(
            metric=MetricEvidence("cpa", cpa_value),
            threshold=ThresholdEvidence(
                code="target_cpa", operator="gt", value=target, unit=th.UNIT_MONEY
            ),
            facts=(Fact("purchases", Decimal(purchases)),),
        ),
    )


# ---------------------------------------------------------------------------
# Economics
# ---------------------------------------------------------------------------


def _break_even_roas(ctx: RuleContext) -> Decimal | None:
    value = ctx.profile.get("break_even_roas")
    return Decimal(value) if value is not None else None


def below_break_even_roas(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    roas_value = _val(_kpi_measure(ctx, entity, "roas"))
    break_even = _break_even_roas(ctx)
    if roas_value is None or break_even is None:
        return None
    if roas_value >= break_even:
        return None
    return _finding(
        ctx,
        code="below_break_even_roas",
        category=CATEGORY_ECONOMICS,
        entity=entity,
        severity=SEVERITY_HIGH,
        affected_stage=FUNNEL_PURCHASE,
        evidence=Evidence(
            metric=MetricEvidence("roas", roas_value),
            threshold=ThresholdEvidence(
                code="break_even_roas", operator="lt", value=break_even,
                unit=th.UNIT_MULTIPLIER,
            ),
        ),
    )


def below_target_roas(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    if not ctx.goal or ctx.goal.get("target_roas") is None:
        return None
    roas_value = _val(_kpi_measure(ctx, entity, "roas"))
    if roas_value is None:
        return None
    target = Decimal(ctx.goal["target_roas"])
    if target == Decimal("0") or roas_value >= target:
        return None
    return _finding(
        ctx,
        code="below_target_roas",
        category=CATEGORY_ECONOMICS,
        entity=entity,
        severity=SEVERITY_MEDIUM,
        affected_stage=FUNNEL_PURCHASE,
        evidence=Evidence(
            metric=MetricEvidence("roas", roas_value),
            threshold=ThresholdEvidence(
                code="target_roas", operator="lt", value=target, unit=th.UNIT_MULTIPLIER
            ),
        ),
    )


def negative_contribution_profit(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    if entity is not None:
        return None
    profit = _val(ctx.summary.get("contribution_profit"))
    if profit is None:
        return None
    if profit > Decimal("0"):
        return None
    return _finding(
        ctx,
        code="negative_contribution_profit",
        category=CATEGORY_ECONOMICS,
        entity=entity,
        severity=SEVERITY_HIGH,
        affected_stage=FUNNEL_PURCHASE,
        evidence=Evidence(metric=MetricEvidence("contribution_profit", profit)),
    )


def declining_contribution_margin(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    if entity is not None:
        return None
    current = _val(ctx.summary.get("contribution_margin"))
    previous = _val(_prev_summary(ctx).get("contribution_margin")) if _prev_summary(ctx) else None
    if current is None or previous is None or previous == Decimal("0"):
        return None
    decline = _declined_percent(current, previous)
    minimum = th.value(th.DECLINE_PERCENT)
    if decline is None or decline < minimum:
        return None
    return _finding(
        ctx,
        code="declining_contribution_margin",
        category=CATEGORY_ECONOMICS,
        entity=entity,
        severity=SEVERITY_MEDIUM,
        affected_stage=FUNNEL_PURCHASE,
        evidence=Evidence(
            metric=MetricEvidence("contribution_margin", current, previous),
            comparison=ComparisonEvidence.of(current, previous),
            threshold=_trend_threshold(th.DECLINE_PERCENT, "gte"),
        ),
    )


def revenue_profit_divergence(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    """Revenue growth alongside profit decline (observed, no causality claimed)."""
    if entity is not None or _prev_summary(ctx) is None:
        return None
    previous = _prev_summary(ctx)
    revenue = _val(ctx.summary.get("revenue"))
    prev_revenue = _val(previous.get("revenue"))
    profit = _val(ctx.summary.get("contribution_profit"))
    prev_profit = _val(previous.get("contribution_profit"))
    if _any_none(revenue, prev_revenue, profit, prev_profit):
        return None
    if prev_revenue == Decimal("0") or prev_profit == Decimal("0"):
        return None
    revenue_change = (revenue - prev_revenue) / abs(prev_revenue) * Decimal("100")
    profit_change = (profit - prev_profit) / abs(prev_profit) * Decimal("100")
    growth_min = th.value(th.REVENUE_GROWTH_DIVERGENCE)
    decline_max = th.value(th.PROFIT_DECLINE_DIVERGENCE)
    if revenue_change < growth_min or profit_change > -decline_max:
        return None
    return _finding(
        ctx,
        code="revenue_profit_divergence",
        category=CATEGORY_ECONOMICS,
        entity=entity,
        severity=SEVERITY_HIGH,
        affected_stage=FUNNEL_PURCHASE,
        evidence=Evidence(
            metric=MetricEvidence("revenue", revenue, prev_revenue),
            comparison=ComparisonEvidence.of(revenue, prev_revenue),
            threshold=ThresholdEvidence(
                code=th.REVENUE_GROWTH_DIVERGENCE, operator="gte",
                value=growth_min, unit=th.UNIT_PERCENT,
            ),
            facts=(
                Fact("contribution_profit", profit, "money"),
                Fact("previous_contribution_profit", prev_profit, "money"),
            ),
        ),
    )


def _any_none(*values) -> bool:
    return any(value is None for value in values)


def negative_unit_margin(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    """Average contribution profit below zero: unit economics sell below cost."""
    if entity is not None:
        return None
    average = ctx.profile.get("average_contribution_profit")
    if average is None:
        return None
    if Decimal(average) >= Decimal("0"):
        return None
    return _finding(
        ctx,
        code="negative_unit_margin",
        category=CATEGORY_ECONOMICS,
        entity=entity,
        severity=SEVERITY_HIGH,
        affected_stage=FUNNEL_PURCHASE,
        evidence=Evidence(
            metric=MetricEvidence("average_contribution_profit", Decimal(average)),
            threshold=ThresholdEvidence(code="zero", operator="lt", value=Decimal("0"),
                                        unit=th.UNIT_MONEY),
        ),
    )


def break_even_unavailable(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    """CPA exists but no unit economics: break-even cannot be assessed."""
    if entity is not None:
        return None
    cpa_value = _val(ctx.summary.get("cpa"))
    if cpa_value is None:
        return None
    if ctx.profile.get("break_even_cpa_range"):
        return None
    return _finding(
        ctx,
        code="break_even_unavailable",
        category=CATEGORY_ECONOMICS,
        entity=entity,
        severity=SEVERITY_INFO,
        affected_stage=FUNNEL_PURCHASE,
        evidence=Evidence(metric=MetricEvidence("cpa", cpa_value)),
    )


def target_cpa_above_viable(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    if entity is not None or not ctx.goal or ctx.goal.get("maximum_cpa") is None:
        return None
    break_even_range = ctx.profile.get("break_even_cpa_range")
    if not break_even_range or not ctx.goal["maximum_cpa"]:
        return None
    target = Decimal(ctx.goal["maximum_cpa"])
    viable = Decimal(break_even_range[1])
    if target <= viable:
        return None
    return _finding(
        ctx,
        code="target_cpa_above_viable",
        category=CATEGORY_ECONOMICS,
        entity=entity,
        severity=SEVERITY_MEDIUM,
        affected_stage=FUNNEL_PURCHASE,
        evidence=Evidence(
            metric=MetricEvidence("maximum_cpa", target),
            threshold=ThresholdEvidence(
                code="break_even_cpa", operator="gt", value=viable, unit=th.UNIT_MONEY
            ),
            facts=(Fact("break_even_cpa", viable, th.UNIT_MONEY),),
        ),
    )


# ---------------------------------------------------------------------------
# Funnel
# ---------------------------------------------------------------------------

_FUNNEL_STAGE_ORDER = ("impressions", "clicks", "landing_page_views", "purchases")


def _stage_value(funnel: dict | None, metric: str) -> Decimal | None:
    if funnel is None:
        return None
    for stage in funnel.get("stages", []):
        if stage.get("metric") == metric:
            if stage.get("status") != STATUS_AVAILABLE:
                return None
            return Decimal(stage["value"]) if stage.get("value") is not None else None
    return None


def _stage_unavailable(funnel: dict | None, metric: str) -> bool:
    if funnel is None:
        return True
    for stage in funnel.get("stages", []):
        if stage.get("metric") == metric:
            return stage.get("status") != STATUS_AVAILABLE
    return True


def funnel_bottleneck(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    """Largest observable drop-off among transitions with sufficient data."""
    if entity is not None:
        return None
    if ctx.funnel is None:
        return None
    best: tuple[Decimal | None, str, str] | None = None
    stages = ctx.funnel.get("stages", [])
    available = {s["metric"] for s in stages if s.get("status") == STATUS_AVAILABLE
                 and s.get("value") is not None}
    for index, metric in enumerate(_FUNNEL_STAGE_ORDER):
        if index == 0 or metric not in available:
            continue
        previous_metric = _FUNNEL_STAGE_ORDER[index - 1]
        if previous_metric not in available:
            continue
        from_value = _stage_value(ctx.funnel, previous_metric)
        to_value = _stage_value(ctx.funnel, metric)
        if from_value is None or to_value is None or from_value == Decimal("0"):
            continue
        sample_floor = (
            th.value(th.SAMPLE_MIN_IMPRESSIONS)
            if previous_metric == "impressions"
            else th.value(th.SAMPLE_MIN_CLICKS)
        )
        if from_value < sample_floor:
            continue
        if previous_metric == "impressions" and to_value < th.value(th.SAMPLE_MIN_CLICKS):
            continue
        rate = to_value / from_value
        if best is None or rate < best[0]:
            best = (rate, previous_metric, metric)
    if best is None or best[0] is None:
        return None
    rate, from_stage, to_stage = best
    minimum = th.value(th.FUNNEL_LOW_TRANSITION)
    if rate >= minimum:
        return None
    previous_rate = None
    if ctx.previous_funnel is not None:
        from_prev = _stage_value(ctx.previous_funnel, from_stage)
        to_prev = _stage_value(ctx.previous_funnel, to_stage)
        if from_prev and from_prev > Decimal("0") and to_prev is not None:
            previous_rate = to_prev / from_prev
    return _finding(
        ctx,
        code="funnel_bottleneck",
        category=CATEGORY_FUNNEL,
        entity=entity,
        severity=SEVERITY_MEDIUM,
        affected_stage=FUNNEL_GROUPS.get(to_stage),
        evidence=Evidence(
            funnel=FunnelEvidence(
                from_stage=from_stage, to_stage=to_stage,
                conversion_rate=rate, previous_rate=previous_rate,
            ),
            threshold=ThresholdEvidence(
                code=th.FUNNEL_LOW_TRANSITION, operator="lt", value=minimum,
                unit=th.UNIT_RATIO,
            ),
        ),
    )


def low_click_to_purchase_rate(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    """Observable purchases/clicks when intermediate funnel stages are missing."""
    if entity is not None or ctx.funnel is None:
        return None
    if not all(_stage_unavailable(ctx.funnel, stage) for stage in _UNOBSERVED_FUNNEL_STAGES):
        return None
    clicks = _stage_value(ctx.funnel, "clicks")
    purchases = _stage_value(ctx.funnel, "purchases")
    minimum_clicks = th.value(th.SAMPLE_MIN_CLICKS)
    if clicks is None or purchases is None or clicks < minimum_clicks:
        return None
    if purchases < Decimal("1"):
        return None
    rate = purchases / clicks
    cvr_low = th.value(th.CVR_LOW)
    if rate >= cvr_low:
        return None
    return _finding(
        ctx,
        code="low_click_to_purchase_rate",
        category=CATEGORY_CONVERSION,
        entity=entity,
        severity=SEVERITY_MEDIUM,
        affected_stage=FUNNEL_PURCHASE,
        reason="intermediate funnel stages are unavailable",
        evidence=Evidence(
            metric=MetricEvidence("click_to_purchase_rate", rate),
            threshold=ThresholdEvidence(code=th.CVR_LOW, operator="lt", value=cvr_low),
            facts=(Fact("clicks", clicks), Fact("purchases", purchases)),
        ),
    )


# ---------------------------------------------------------------------------
# Spend / tracking
# ---------------------------------------------------------------------------


def spend_without_purchase(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    if entity is not None:
        return None
    spend = _val(ctx.summary.get("spend"))
    purchases = _val(ctx.summary.get("purchases"))
    minimum_spend = th.value(th.SAMPLE_MIN_SPEND)
    if spend is None or purchases is None or spend <= minimum_spend:
        return None
    if purchases != Decimal("0"):
        return None
    severity = SEVERITY_MEDIUM
    break_even = ctx.profile.get("break_even_cpa_range")
    if break_even and spend >= Decimal(break_even[1]) * th.value(
        th.SPEND_WITHOUT_PURCHASE_HIGH
    ):
        severity = SEVERITY_HIGH
    prev = _prev_summary(ctx)
    if prev is not None:
        prev_purchases = _val(prev.get("purchases"))
        prev_spend = _val(prev.get("spend"))
        if prev_purchases is not None and prev_purchases > Decimal("0") and (
            prev_spend is None or spend >= prev_spend
        ):
            severity = SEVERITY_HIGH
    facts = [Fact("spend", spend, th.UNIT_MONEY), Fact("purchases", purchases)]
    if break_even:
        facts.append(Fact("break_even_cpa", Decimal(break_even[1]), th.UNIT_MONEY))
    return _finding(
        ctx,
        code="spend_without_purchase",
        category=CATEGORY_PERFORMANCE,
        entity=entity,
        severity=severity,
        affected_stage=FUNNEL_PURCHASE,
        evidence=Evidence(
            metric=MetricEvidence("purchases", purchases),
            threshold=ThresholdEvidence(
                code=th.SAMPLE_MIN_SPEND, operator="gt", value=minimum_spend,
                unit=th.UNIT_MONEY,
            ),
            facts=tuple(facts),
        ),
    )


def purchase_revenue_mismatch(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    if entity is not None:
        return None
    purchases = _val(ctx.summary.get("purchases"))
    revenue = _val(ctx.summary.get("revenue"))
    if purchases is None or revenue is None or purchases <= Decimal("0"):
        return None
    if revenue != Decimal("0"):
        return None
    return _finding(
        ctx,
        code="purchase_revenue_mismatch",
        category=CATEGORY_TRACKING,
        entity=entity,
        severity=SEVERITY_MEDIUM,
        affected_stage=FUNNEL_PURCHASE,
        evidence=Evidence(
            metric=MetricEvidence("revenue", revenue),
            facts=(Fact("purchases", purchases),),
        ),
    )


def revenue_purchase_mismatch(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    if entity is not None:
        return None
    revenue = _val(ctx.summary.get("revenue"))
    purchases = _val(ctx.summary.get("purchases"))
    if revenue is None or purchases is None or revenue <= Decimal("0"):
        return None
    if purchases != Decimal("0"):
        return None
    return _finding(
        ctx,
        code="revenue_purchase_mismatch",
        category=CATEGORY_TRACKING,
        entity=entity,
        severity=SEVERITY_MEDIUM,
        affected_stage=FUNNEL_PURCHASE,
        evidence=Evidence(
            metric=MetricEvidence("purchases", purchases),
            facts=(Fact("revenue", revenue, th.UNIT_MONEY),),
        ),
    )


def provider_conversion_mismatch(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    """Meta-reported conversions vs commerce purchases (no reconciliation claim)."""
    if entity is not None:
        return None
    conversions = _val(ctx.summary.get("conversions"))
    purchases = _val(ctx.summary.get("purchases"))
    if conversions is None or purchases is None:
        return None
    if conversions <= Decimal("0") or purchases <= Decimal("0"):
        return None
    mismatch = abs(conversions - purchases) / purchases * Decimal("100")
    minimum = th.value(th.CONVERSION_MISMATCH_PERCENT)
    if mismatch < minimum:
        return None
    return _finding(
        ctx,
        code="provider_conversion_mismatch",
        category=CATEGORY_TRACKING,
        entity=entity,
        severity=SEVERITY_LOW,
        affected_stage=FUNNEL_PURCHASE,
        evidence=Evidence(
            metric=MetricEvidence("conversions", conversions, purchases),
            threshold=ThresholdEvidence(
                code=th.CONVERSION_MISMATCH_PERCENT, operator="gte", value=minimum,
                unit=th.UNIT_PERCENT,
            ),
            facts=(
                Fact("conversions", conversions),
                Fact("purchases", purchases),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Data quality
# ---------------------------------------------------------------------------

_PROVIDER_LABELS = (PROVIDER_META, PROVIDER_SHOPIFY)


def _provider_quality(ctx: RuleContext, provider: str) -> dict | None:
    if ctx.quality is None:
        return None
    for item in ctx.quality.get("providers", []):
        if item.get("provider") == provider:
            return item
    return None


def stale_provider_data(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    if entity is not None:
        return None
    for provider in _PROVIDER_LABELS:
        item = _provider_quality(ctx, provider)
        if item and item.get("freshness_status") in ("stale",):
            yield _finding(
                ctx,
                code=f"stale_{provider}_data",
                category=CATEGORY_DATA_QUALITY,
                entity=entity,
                severity=SEVERITY_MEDIUM,
                evidence=Evidence(
                    metric=MetricEvidence(f"{provider}_freshness", None),
                    facts=(Fact("last_synced_at", None),),
                ),
            )


def delayed_provider_data(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    if entity is not None:
        return None
    for provider in _PROVIDER_LABELS:
        item = _provider_quality(ctx, provider)
        if item and item.get("freshness_status") == "delayed":
            yield _finding(
                ctx,
                code=f"delayed_{provider}_data",
                category=CATEGORY_DATA_QUALITY,
                entity=entity,
                severity=SEVERITY_LOW,
                evidence=Evidence(metric=MetricEvidence(f"{provider}_freshness", None)),
            )


def provider_not_connected(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    if entity is not None:
        return None
    for provider in _PROVIDER_LABELS:
        item = _provider_quality(ctx, provider)
        if item and item.get("freshness_status") == STATUS_UNAVAILABLE and item.get(
            "reason"
        ) == "not connected":
            yield _finding(
                ctx,
                code=f"{provider}_not_connected",
                category=CATEGORY_DATA_QUALITY,
                entity=entity,
                severity=SEVERITY_INFO,
                evidence=Evidence(metric=MetricEvidence(f"{provider}_freshness", None)),
            )


def missing_reporting_period(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    if entity is not None:
        return None
    for provider in _PROVIDER_LABELS:
        item = _provider_quality(ctx, provider)
        if item and item.get("freshness_status") == STATUS_UNAVAILABLE and item.get(
            "reason"
        ) == "no synced facts in period":
            yield _finding(
                ctx,
                code=f"missing_{provider}_reporting_period",
                category=CATEGORY_DATA_QUALITY,
                entity=entity,
                severity=SEVERITY_INFO,
                evidence=Evidence(metric=MetricEvidence(f"{provider}_freshness", None)),
            )


def incomplete_reporting_period(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    if entity is not None:
        return None
    minimum = th.value(th.MISSING_DAYS_INCOMPLETE)
    for provider in _PROVIDER_LABELS:
        item = _provider_quality(ctx, provider)
        if not item or item.get("freshness_status") == STATUS_UNAVAILABLE:
            continue
        missing = item.get("missing_days")
        if missing is None or int(missing) < minimum:
            continue
        yield _finding(
            ctx,
            code="incomplete_reporting_period",
            category=CATEGORY_DATA_QUALITY,
            entity=entity,
            severity=SEVERITY_LOW,
            evidence=Evidence(
                metric=MetricEvidence(f"{provider}_coverage", None),
                threshold=ThresholdEvidence(
                    code=th.MISSING_DAYS_INCOMPLETE, operator="gte", value=minimum,
                    unit=th.UNIT_COUNT,
                ),
                facts=(Fact("missing_days", Decimal(int(missing))),),
            ),
        )


def unobserved_funnel_stages(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    if entity is not None or ctx.funnel is None:
        return None
    stages = ctx.funnel.get("stages", [])
    if not stages:
        return None
    any_observed = any(s.get("status") == STATUS_AVAILABLE for s in stages)
    all_unobserved = all(
        _stage_unavailable(ctx.funnel, stage) for stage in _UNOBSERVED_FUNNEL_STAGES
    )
    if not any_observed or not all_unobserved:
        return None
    return _finding(
        ctx,
        code="unobserved_funnel_stages",
        category=CATEGORY_DATA_QUALITY,
        entity=entity,
        severity=SEVERITY_INFO,
        affected_stage=FUNNEL_INTENT,
        evidence=Evidence(
            metric=MetricEvidence("product_views", None),
            facts=tuple(Fact(stage, None) for stage in _UNOBSERVED_FUNNEL_STAGES),
        ),
    )


def recent_sync_failures(ctx: RuleContext, entity: EntityContext | None) -> Finding | None:
    if entity is not None or ctx.sync_failures <= 0:
        return None
    return _finding(
        ctx,
        code="recent_sync_failures",
        category=CATEGORY_DATA_QUALITY,
        entity=entity,
        severity=SEVERITY_LOW,
        evidence=Evidence(
            metric=MetricEvidence("sync_failures", Decimal(ctx.sync_failures)),
            facts=(Fact("sync_failures", Decimal(ctx.sync_failures)),),
        ),
    )


# ---------------------------------------------------------------------------
# Persistent underperformance (diagnosis only — never an action)
# ---------------------------------------------------------------------------


def persistent_unprofitable_performance(
    ctx: RuleContext, entity: EntityContext | None
) -> Finding | None:
    """Sufficient sample + multiple periods below break-even → review_required."""
    spend = _raw(ctx, entity, "spend")
    minimum_spend = th.value(th.SAMPLE_MIN_SPEND)
    if spend is None or Decimal(spend) < minimum_spend:
        return None
    if entity is not None:
        if entity.rows < 2:
            return None
        current_roas = _val(_kpi_measure(ctx, entity, "roas"))
        previous_roas = _val(_prev_kpi_entity(ctx, entity, "roas"))
        break_even = _break_even_roas(ctx)
        if _any_none(current_roas, previous_roas, break_even):
            return None
        if current_roas >= break_even or previous_roas >= break_even:
            return None
        return _finding(
            ctx,
            code="persistent_unprofitable_performance",
            category=CATEGORY_PERFORMANCE,
            entity=entity,
            severity=SEVERITY_HIGH,
            affected_stage=FUNNEL_PURCHASE,
            review_status=REVIEW_REQUIRED,
            evidence=Evidence(
                metric=MetricEvidence("roas", current_roas, previous_roas),
                threshold=ThresholdEvidence(
                    code="break_even_roas", operator="lt", value=break_even,
                    unit=th.UNIT_MULTIPLIER,
                ),
                facts=(Fact("spend", Decimal(spend), th.UNIT_MONEY),),
            ),
        )

    purchases = _raw(ctx, entity, "purchases")
    minimum_purchases = th.value(th.SAMPLE_MIN_PURCHASES)
    if purchases is None or Decimal(purchases) < minimum_purchases:
        return None
    previous = _prev_summary(ctx)
    if previous is None:
        return None
    current_roas = _val(ctx.summary.get("roas"))
    previous_roas = _val(previous.get("roas"))
    break_even = _break_even_roas(ctx)
    current_cpa = _val(ctx.summary.get("cpa"))
    previous_cpa = _val(previous.get("cpa"))
    target, _source = _cpa_target(ctx)
    roas_path = not _any_none(current_roas, previous_roas, break_even) and (
        current_roas < break_even and previous_roas < break_even
    )
    cpa_path = (
        target is not None
        and not _any_none(current_cpa, previous_cpa)
        and current_cpa > target
        and previous_cpa > target
    )
    if not roas_path and not cpa_path:
        return None
    metric = (
        MetricEvidence("roas", current_roas, previous_roas)
        if roas_path
        else MetricEvidence("cpa", current_cpa, previous_cpa)
    )
    return _finding(
        ctx,
        code="persistent_unprofitable_performance",
        category=CATEGORY_PERFORMANCE,
        entity=entity,
        severity=SEVERITY_HIGH,
        affected_stage=FUNNEL_PURCHASE,
        review_status=REVIEW_REQUIRED,
        evidence=Evidence(
            metric=metric,
            threshold=ThresholdEvidence(
                code="break_even_roas", operator="lt",
                value=break_even if roas_path else target,
                unit=th.UNIT_MULTIPLIER if roas_path else th.UNIT_MONEY,
            ),
            facts=(Fact("spend", Decimal(spend), th.UNIT_MONEY),),
        ),
    )


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

_BUSINESS_ONLY: tuple[str, ...] = ()


@dataclass(frozen=True)
class Rule:
    code: str
    category: str
    level: str  # "business" | "entity"
    entity_types: tuple[str, ...]
    evaluate: Callable[[RuleContext, EntityContext | None], object]


def _evaluate_single(rule: Rule, ctx: RuleContext, entity: EntityContext | None) -> list[Finding]:
    result = rule.evaluate(ctx, entity)
    if result is None:
        return []
    if isinstance(result, Finding):
        return [result]
    return list(result)


RULES: tuple[Rule, ...] = (
    Rule("low_ctr", CATEGORY_TRAFFIC, "entity",
         (ENTITY_TYPE_CAMPAIGN, ENTITY_TYPE_AD_SET, ENTITY_TYPE_AD), low_ctr),
    Rule("low_ctr", CATEGORY_TRAFFIC, "business", _BUSINESS_ONLY, low_ctr),
    Rule("ctr_decline", CATEGORY_TRAFFIC, "entity",
         (ENTITY_TYPE_CAMPAIGN, ENTITY_TYPE_AD_SET, ENTITY_TYPE_AD), ctr_decline),
    Rule("ctr_decline", CATEGORY_TRAFFIC, "business", _BUSINESS_ONLY, ctr_decline),
    Rule("high_cpc", CATEGORY_TRAFFIC, "entity",
         (ENTITY_TYPE_CAMPAIGN, ENTITY_TYPE_AD_SET, ENTITY_TYPE_AD), high_cpc),
    Rule("high_cpc", CATEGORY_TRAFFIC, "business", _BUSINESS_ONLY, high_cpc),
    Rule("high_cpm", CATEGORY_TRAFFIC, "entity",
         (ENTITY_TYPE_CAMPAIGN, ENTITY_TYPE_AD_SET, ENTITY_TYPE_AD), high_cpm),
    Rule("high_cpm", CATEGORY_TRAFFIC, "business", _BUSINESS_ONLY, high_cpm),
    Rule("creative_low_ctr", CATEGORY_CREATIVE, "entity", (ENTITY_TYPE_AD,), creative_low_ctr),
    Rule("possible_creative_fatigue", CATEGORY_CREATIVE, "entity",
         (ENTITY_TYPE_AD,), possible_creative_fatigue),
    Rule("low_cvr", CATEGORY_CONVERSION, "business", _BUSINESS_ONLY, low_cvr),
    Rule("cvr_decline", CATEGORY_CONVERSION, "business", _BUSINESS_ONLY, cvr_decline),
    Rule("high_cpa", CATEGORY_CONVERSION, "business", _BUSINESS_ONLY, high_cpa),
    Rule("below_break_even_roas", CATEGORY_ECONOMICS, "entity",
         (ENTITY_TYPE_CAMPAIGN, ENTITY_TYPE_AD_SET, ENTITY_TYPE_AD), below_break_even_roas),
    Rule("below_break_even_roas", CATEGORY_ECONOMICS, "business", _BUSINESS_ONLY,
         below_break_even_roas),
    Rule("below_target_roas", CATEGORY_ECONOMICS, "entity",
         (ENTITY_TYPE_CAMPAIGN, ENTITY_TYPE_AD_SET, ENTITY_TYPE_AD), below_target_roas),
    Rule("below_target_roas", CATEGORY_ECONOMICS, "business", _BUSINESS_ONLY, below_target_roas),
    Rule("negative_contribution_profit", CATEGORY_ECONOMICS, "business", _BUSINESS_ONLY,
         negative_contribution_profit),
    Rule("declining_contribution_margin", CATEGORY_ECONOMICS, "business", _BUSINESS_ONLY,
         declining_contribution_margin),
    Rule("revenue_profit_divergence", CATEGORY_ECONOMICS, "business", _BUSINESS_ONLY,
         revenue_profit_divergence),
    Rule("negative_unit_margin", CATEGORY_ECONOMICS, "business", _BUSINESS_ONLY,
         negative_unit_margin),
    Rule("break_even_unavailable", CATEGORY_ECONOMICS, "business", _BUSINESS_ONLY,
         break_even_unavailable),
    Rule("target_cpa_above_viable", CATEGORY_ECONOMICS, "business", _BUSINESS_ONLY,
         target_cpa_above_viable),
    Rule("funnel_bottleneck", CATEGORY_FUNNEL, "business", _BUSINESS_ONLY, funnel_bottleneck),
    Rule("low_click_to_purchase_rate", CATEGORY_CONVERSION, "business", _BUSINESS_ONLY,
         low_click_to_purchase_rate),
    Rule("spend_without_purchase", CATEGORY_PERFORMANCE, "business", _BUSINESS_ONLY,
         spend_without_purchase),
    Rule("purchase_revenue_mismatch", CATEGORY_TRACKING, "business", _BUSINESS_ONLY,
         purchase_revenue_mismatch),
    Rule("revenue_purchase_mismatch", CATEGORY_TRACKING, "business", _BUSINESS_ONLY,
         revenue_purchase_mismatch),
    Rule("provider_conversion_mismatch", CATEGORY_TRACKING, "business", _BUSINESS_ONLY,
         provider_conversion_mismatch),
    Rule("stale_provider_data", CATEGORY_DATA_QUALITY, "business", _BUSINESS_ONLY,
         stale_provider_data),
    Rule("delayed_provider_data", CATEGORY_DATA_QUALITY, "business", _BUSINESS_ONLY,
         delayed_provider_data),
    Rule("provider_not_connected", CATEGORY_DATA_QUALITY, "business", _BUSINESS_ONLY,
         provider_not_connected),
    Rule("missing_reporting_period", CATEGORY_DATA_QUALITY, "business", _BUSINESS_ONLY,
         missing_reporting_period),
    Rule("incomplete_reporting_period", CATEGORY_DATA_QUALITY, "business", _BUSINESS_ONLY,
         incomplete_reporting_period),
    Rule("unobserved_funnel_stages", CATEGORY_DATA_QUALITY, "business", _BUSINESS_ONLY,
         unobserved_funnel_stages),
    Rule("recent_sync_failures", CATEGORY_DATA_QUALITY, "business", _BUSINESS_ONLY,
         recent_sync_failures),
    Rule("persistent_unprofitable_performance", CATEGORY_PERFORMANCE, "entity",
         (ENTITY_TYPE_CAMPAIGN,), persistent_unprofitable_performance),
    Rule("persistent_unprofitable_performance", CATEGORY_PERFORMANCE, "business",
         _BUSINESS_ONLY, persistent_unprofitable_performance),
)

_BUSINESS_CODES = {rule.code for rule in RULES if rule.level == "business"}
_ENTITY_CODES_BY_TYPE: dict[str, set[str]] = {}
for rule in RULES:
    if rule.level != "entity":
        continue
    for entity_type in rule.entity_types:
        _ENTITY_CODES_BY_TYPE.setdefault(entity_type, set()).add(rule.code)

RULE_CODES: tuple[str, ...] = tuple(
    sorted({rule.code for rule in RULES})
)


def apply_business_rules(ctx: RuleContext) -> list[Finding]:
    findings: list[Finding] = []
    for rule in RULES:
        if rule.level != "business":
            continue
        findings.extend(_evaluate_single(rule, ctx, None))
    return findings


def apply_entity_rules(ctx: RuleContext, entity: EntityContext) -> list[Finding]:
    findings: list[Finding] = []
    for rule in RULES:
        if rule.level != "entity" or entity.entity_type not in rule.entity_types:
            continue
        findings.extend(_evaluate_single(rule, ctx, entity))
    return findings


def entity_rule_codes(entity_type: str) -> set[str]:
    return _ENTITY_CODES_BY_TYPE.get(entity_type, set())


__all__ = [
    "RuleContext",
    "EntityContext",
    "Rule",
    "RULES",
    "RULE_CODES",
    "apply_business_rules",
    "apply_entity_rules",
    "entity_rule_codes",
    "FUNNEL_GROUPS",
]