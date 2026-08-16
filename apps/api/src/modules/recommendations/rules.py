"""Decision rules for the deterministic decision engine.

Pure functions that evaluate evidence and return decisions.
All rules are deterministic: same inputs → same outputs.
Rules reference actual metric values, thresholds, and structured evidence.

Decision types must NOT be confused with actions — they are review
recommendations only. The system never executes anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from src.modules.recommendations.evidence import (
    DecisionEvidence,
    EvidenceItem,
    make_decision_evidence,
    make_evidence_item,
    make_fact_evidence,
    make_funnel_evidence,
    make_metric_evidence,
    make_threshold_evidence,
)
from src.modules.recommendations.severity import (
    DECISION_SEVERITY_MAP,
    EVIDENCE_INSUFFICIENT,
    EVIDENCE_MODERATE,
    EVIDENCE_STRONG,
    EVIDENCE_WEAK,
)
from src.modules.recommendations.thresholds import THRESHOLD_VERSION

# Rule codes for tracking which rule produced a decision
RULE_CODES = (
    "sample_size",
    "data_freshness",
    "tracking_quality",
    "learning_state",
    "kill_review",
    "scale_review",
    "optimize",
    "maintain",
    "economics",
    "forecast",
)

ALL_RULES = RULE_CODES


@dataclass(frozen=True)
class DecisionContext:
    """Input context for decision evaluation.

    All fields optional — the engine passes what's available.
    """
    business_id: Any = None
    entity_type: str = "campaign"
    entity_id: Any = None
    entity_name: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    previous_metrics: dict[str, Any] | None = None
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    performance_state: str | None = None
    scaling_readiness: dict[str, Any] | None = None
    forecast: dict[str, Any] | None = None  # CampaignForecastRead-like dict
    economics: dict[str, Any] | None = None  # summary_data-dict
    goal: dict[str, Any] | None = None  # current_goal dict
    rows: int = 0
    range_length_days: int = 0
    data_quality: dict[str, Any] | None = None
    data_stale: bool = False
    tracking_issue: bool = False
    currency: str = "USD"


@dataclass(frozen=True)
class Decision:
    """A structured decision with evidence."""
    decision: str
    entity_type: str
    business_id: Any = None
    entity_id: Any = None
    entity_name: str | None = None
    evidence_strength: str = ""
    primary_reason: str = ""
    evidence: DecisionEvidence | None = None
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    metrics_snapshot: dict[str, Any] = field(default_factory=dict)
    forecast_snapshot: dict[str, Any] | None = None
    severity: str = ""
    rules_version: str = THRESHOLD_VERSION
    review_suggestions: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Decision evaluation helpers
# ---------------------------------------------------------------------------


def _dec(value) -> Decimal | None:
    """Coerce serialized values (str/Decimal/int/None) to Decimal."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        return None


def _val(measure: dict | None) -> Decimal | None:
    """Extract value from a measure dict (status available only)."""
    if not measure or measure.get("status") != "available":
        return None
    return _dec(measure.get("value"))


def _raw(metrics: dict, code: str) -> Decimal | None:
    """Extract raw metric value from a metrics dict (serialized KPI view)."""
    return _dec(metrics.get(code))


# ---------------------------------------------------------------------------
# Sample-size gates (Phase 3B reuse)
# ---------------------------------------------------------------------------


def sample_gates_met(ctx: DecisionContext) -> tuple[bool, list[dict]]:
    """Check sample-size gates (reuse Phase 3B thresholds).

    Returns (met, gates) where gates lists which gates failed.
    """
    from src.modules.diagnostics.thresholds import (
        SAMPLE_MIN_CONVERSIONS,
        SAMPLE_MIN_IMPRESSIONS,
        SAMPLE_MIN_SPEND,
    )
    from src.modules.diagnostics.thresholds import (
        value as threshold_value,
    )

    spend = _raw(ctx.metrics, "spend")
    impressions = _raw(ctx.metrics, "impressions")
    conversions = _raw(ctx.metrics, "conversions")
    rows = max(ctx.rows, ctx.range_length_days)

    spend_d = _dec(spend)
    impressions_d = _dec(impressions)
    conversions_d = _dec(conversions)
    min_spend = _dec(threshold_value(SAMPLE_MIN_SPEND))
    min_impressions = _dec(threshold_value(SAMPLE_MIN_IMPRESSIONS))
    min_conversions = _dec(threshold_value(SAMPLE_MIN_CONVERSIONS))

    gates: list[dict] = [
        {
            "code": "minimum_spend",
            "value": spend,
            "threshold": min_spend,
            "unit": "money",
            "met": spend_d is not None and min_spend is not None
            and spend_d >= min_spend,
        },
        {
            "code": "minimum_impressions",
            "value": impressions,
            "threshold": min_impressions,
            "unit": "count",
            "met": impressions_d is not None and min_impressions is not None
            and impressions_d >= min_impressions,
        },
        {
            "code": "minimum_conversions",
            "value": conversions,
            "threshold": min_conversions,
            "unit": "count",
            "met": conversions_d is not None and min_conversions is not None
            and conversions_d >= min_conversions,
        },
        {
            "code": "minimum_days",
            "value": rows,
            "threshold": 7,
            "unit": "count",
            "met": rows >= 7,
        },
    ]
    return all(g["met"] for g in gates), gates


def sample_sufficient(ctx: DecisionContext) -> bool:
    """Sufficient sample for performance decisions."""
    met, _ = sample_gates_met(ctx)
    return met


# ---------------------------------------------------------------------------
# Data quality / tracking gates
# ---------------------------------------------------------------------------


def has_tracking_issue(ctx: DecisionContext) -> bool:
    """Tracking issue when diagnostics detect conversion/revenue mismatches."""
    if ctx.tracking_issue:
        return True
    return any(
        finding.get("category") in ("tracking",)
        and finding.get("severity") not in ("info",)
        for finding in ctx.diagnostics
    )


def has_data_quality_issue(ctx: DecisionContext) -> bool:
    """Data quality issue when data is stale or quality findings exist."""
    if ctx.data_stale:
        return True
    return any(
        finding.get("category") == "data_quality"
        and finding.get("severity") not in ("info",)
        for finding in ctx.diagnostics
    )


# ---------------------------------------------------------------------------
# Learning state
# ---------------------------------------------------------------------------


def is_learning(ctx: DecisionContext) -> bool:
    """Learning state from actual observed data maturity (not age).

    A campaign is learning when:
    - it has some data (rows > 0)
    - but does not yet meet minimum sample gates
    - and has more than zero impressions/spend (early signals)
    """
    spend = _raw(ctx.metrics, "spend")
    impressions = _raw(ctx.metrics, "impressions")
    rows = max(ctx.rows, ctx.range_length_days)
    has_any = (spend is not None and spend > 0) or (
        impressions is not None and impressions > 0
    ) or (spend is not None and spend > 0)
    if not has_any:
        return False
    if rows <= 0:
        return False
    # learning = has data but not yet sample-sufficient
    return not sample_sufficient(ctx)


# ---------------------------------------------------------------------------
# Economics helpers
# ---------------------------------------------------------------------------


def break_even_roas(ctx: DecisionContext) -> Decimal | None:
    """Break-even ROAS from Phase 1 economics."""
    if ctx.economics:
        value = ctx.economics.get("break_even_roas")
        return _dec(value)
    return None


def break_even_cpa_range(ctx: DecisionContext) -> tuple[Decimal | None, Decimal | None]:
    """Break-even CPA range from Phase 1 economics."""
    if not ctx.economics:
        return None, None
    value = ctx.economics.get("break_even_cpa_range")
    if not value or not isinstance(value, (list, tuple)):
        return None, None
    return _dec(value[0]), _dec(value[1])


def target_roas(ctx: DecisionContext) -> Decimal | None:
    """Target ROAS from business goals."""
    if ctx.goal:
        value = ctx.goal.get("target_roas")
        return _dec(value)
    return None


def target_cpa(ctx: DecisionContext) -> Decimal | None:
    """Target CPA from the business goal (`maximum_cpa`), else None.

    The decision engine never invents targets: without a goal or unit
    economics it simply has no CPA target to evaluate against.
    """
    if ctx.goal:
        value = ctx.goal.get("maximum_cpa")
        if value is not None:
            return _dec(value)
    return None


def viable_cpa(ctx: DecisionContext) -> Decimal | None:
    """Viable CPA = min of target CPA and break-even CPA upper."""
    target = target_cpa(ctx)
    low, high = break_even_cpa_range(ctx)
    candidates = [v for v in (target, low, high) if v is not None and v > 0]
    return min(candidates) if candidates else None


# ---------------------------------------------------------------------------
# Forecast helpers
# ---------------------------------------------------------------------------


def forecast_roas(ctx: DecisionContext) -> Decimal | None:
    """Forecast ROAS from Phase 4A campaign forecast."""
    if not ctx.forecast:
        return None
    roas = ctx.forecast.get("roas")
    if not roas:
        return None
    return _dec(roas.get("value"))


def current_roas(ctx: DecisionContext) -> Decimal | None:
    """Current ROAS from metrics."""
    return _val(ctx.metrics.get("roas"))


def current_cpa(ctx: DecisionContext) -> Decimal | None:
    """Current CPA from metrics."""
    return _val(ctx.metrics.get("cpa"))


def current_spend(ctx: DecisionContext) -> Decimal | None:
    """Current spend from metrics."""
    return _raw(ctx.metrics, "spend")


def current_purchases(ctx: DecisionContext) -> Decimal | None:
    """Current purchases from metrics (business grain) or conversions (campaign)."""
    purchases = _raw(ctx.metrics, "purchases")
    if purchases is not None:
        return purchases
    conversions = _raw(ctx.metrics, "conversions")
    return conversions


# ---------------------------------------------------------------------------
# Decision rules (pure functions)
# ---------------------------------------------------------------------------


def rule_tracking_issue(ctx: DecisionContext) -> bool:
    """Precedence 1: tracking_issue."""
    return has_tracking_issue(ctx)


def rule_data_quality_issue(ctx: DecisionContext) -> bool:
    """Precedence 2: data_quality_issue."""
    return has_data_quality_issue(ctx)


def rule_insufficient_data(ctx: DecisionContext) -> bool:
    """Precedence 3: insufficient_data.

    True when there is no meaningful evidence at all: no spend/impressions
    above the early-signal floor. Zero purchases with substantial spend is
    a real observation (handled by diagnostics findings), not "no data".
    """
    has_any_facts = False
    for code in ("spend", "impressions", "clicks", "purchases", "conversions"):
        value = _raw(ctx.metrics, code)
        if value is not None and value > 0:
            has_any_facts = True
            break
    if not has_any_facts:
        return True
    spend = _raw(ctx.metrics, "spend")
    impressions = _raw(ctx.metrics, "impressions")
    # No spend or no impressions at all → nothing to decide on yet.
    if spend is None or impressions is None:
        return True
    # Early-signal floors: below these, evidence is too thin for any
    # performance conclusion (a single well-spent day can be noise).
    return spend < Decimal("100") or impressions < Decimal("1000")


def rule_learning(ctx: DecisionContext) -> bool:
    """Precedence 4: learning."""
    if is_learning(ctx):
        # need at least early signals
        spend = _raw(ctx.metrics, "spend")
        impressions = _raw(ctx.metrics, "impressions")
        if (spend is not None and spend > 0) or (
            impressions is not None and impressions > 0
        ):
            return True
    return False


def rule_kill_review(ctx: DecisionContext) -> bool:
    """Precedence 5: kill_review.

    ONLY when persistent, sufficiently evidenced unprofitability:
    - enough historical duration
    - spend above kill threshold
    - ROAS below break-even OR CPA materially above viable CPA
    - no tracking/data issue explaining the result
    - forecast does not indicate recovery
    """
    from src.modules.recommendations.thresholds import (
        CPA_KILL_MULTIPLIER,
        MIN_DAYS_FOR_KILL_REVIEW,
        MIN_PURCHASES_FOR_KILL_REVIEW,
        MIN_SPEND_FOR_KILL_REVIEW,
        ROAS_KILL_BUFFER,
    )

    if has_tracking_issue(ctx) or has_data_quality_issue(ctx):
        return False
    spend = current_spend(ctx)
    if spend is None or spend < MIN_SPEND_FOR_KILL_REVIEW:
        return False
    rows = max(ctx.rows, ctx.range_length_days)
    if rows < MIN_DAYS_FOR_KILL_REVIEW:
        return False
    purchases = current_purchases(ctx)
    cpa = current_cpa(ctx)
    roas = current_roas(ctx)
    break_even = break_even_roas(ctx)

    roas_below = False
    if roas is not None and break_even is not None:
        roas_below = roas < (break_even - ROAS_KILL_BUFFER)
    cpa_above = False
    viable = viable_cpa(ctx)
    if cpa is not None and viable is not None:
        cpa_above = cpa > (viable * CPA_KILL_MULTIPLIER)

    # Need either enough purchases OR strong loss evidence
    sufficient_loss_evidence = (
        purchases is not None and purchases >= MIN_PURCHASES_FOR_KILL_REVIEW
    ) or cpa_above
    # Campaign grain has no purchase attribution: Meta conversions act as
    # the only loss evidence (never invented, never confused with purchases).
    if purchases is None:
        conversions = _raw(ctx.metrics, "conversions")
        sufficient_loss_evidence = (
            conversions is not None
            and conversions >= MIN_PURCHASES_FOR_KILL_REVIEW
        ) or cpa_above
    if not sufficient_loss_evidence:
        return False

    # Persistent underperformance: ROAS below break-even OR CPA above viable
    if not (roas_below or cpa_above):
        return False

    # Forecast does not indicate a reasonable recovery
    forecast_roas_value = forecast_roas(ctx)
    return not (
        forecast_roas_value is not None
        and break_even is not None
        and forecast_roas_value >= break_even
    )


def rule_scale_review(ctx: DecisionContext) -> bool:
    """Precedence 6: scale_review.

    Requires ALL conditions:
    - sufficient sample
    - data fresh
    - no critical tracking/data quality issue
    - CPA at/below target OR economics viable
    - ROAS above break-even
    - forecast does not indicate imminent deterioration
    - no major unresolved diagnostic
    """
    from src.modules.recommendations.thresholds import (
        CPA_BUFFER_BELOW_TARGET,
        ROAS_BUFFER_ABOVE_BREAKEVEN,
    )

    if has_tracking_issue(ctx) or has_data_quality_issue(ctx):
        return False
    if ctx.performance_state in ("unprofitable", "stale_data"):
        return False
    if not sample_sufficient(ctx):
        return False
    if ctx.data_stale:
        return False

    roas = current_roas(ctx)
    break_even = break_even_roas(ctx)
    if roas is None or break_even is None:
        return False
    if roas < (break_even + ROAS_BUFFER_ABOVE_BREAKEVEN):
        return False

    cpa = current_cpa(ctx)
    viable = viable_cpa(ctx)
    if (
        cpa is not None
        and viable is not None
        and cpa > (viable * CPA_BUFFER_BELOW_TARGET)
    ):
        return False

    # No major unresolved diagnostic
    for finding in ctx.diagnostics:
        if finding.get("severity") in ("high", "critical"):
            return False

    # Forecast does not indicate imminent deterioration
    f_roas = forecast_roas(ctx)
    if f_roas is not None and roas is not None:
        drop = (roas - f_roas) / roas if roas > 0 else Decimal("0")
        if drop > Decimal("0.15"):
            return False
    return True


# Categories that describe performance bottlenecks (as opposed to
# informational notes such as `unobserved_funnel_stages`). Only findings in
# these categories make a decision "optimize" vs "maintain".
PERFORMANCE_CATEGORIES = (
    "traffic",
    "creative",
    "conversion",
    "offer",
    "funnel",
    "economics",
    "performance",
)


def _performance_findings(ctx: DecisionContext) -> list[dict]:
    return [
        finding
        for finding in ctx.diagnostics
        if finding.get("category") in PERFORMANCE_CATEGORIES
        and finding.get("status") != "insufficient_data"
    ]


def rule_optimize(ctx: DecisionContext) -> bool:
    """Precedence 7: optimize.

    Enough data, not necessarily unprofitable, but one or more
    bottlenecks detected (low CTR, high CPC, low CVR, offer/funnel issue,
    creative fatigue) — referenced from actual diagnostics. Cost
    efficiency issues (CPA above viable CPA) also trigger optimize even
    without a diagnostic finding.
    """
    if has_tracking_issue(ctx) or has_data_quality_issue(ctx):
        return False
    if not sample_sufficient(ctx):
        return False
    if len(_performance_findings(ctx)) > 0:
        return True
    # Cost efficiency: CPA above viable CPA (deterministic, never invented)
    from src.modules.recommendations.thresholds import CPA_BUFFER_BELOW_TARGET

    cpa = current_cpa(ctx)
    viable = viable_cpa(ctx)
    return (
        cpa is not None
        and viable is not None
        and cpa > (viable * CPA_BUFFER_BELOW_TARGET)
    )


def rule_maintain(ctx: DecisionContext) -> bool:
    """Precedence 8: maintain.

    Data sufficient, performance healthy, economics positive,
    no performance bottleneck, forecast stable.
    """
    if has_tracking_issue(ctx) or has_data_quality_issue(ctx):
        return False
    if not sample_sufficient(ctx):
        return False
    # No performance findings → maintain
    return len(_performance_findings(ctx)) == 0


# ---------------------------------------------------------------------------
# Evidence strength computation
# ---------------------------------------------------------------------------


def compute_evidence_strength(ctx: DecisionContext, decision: str) -> str:
    """Deterministic evidence strength from available evidence sources.

    - insufficient: minimal evidence
    - weak: some evidence, missing key inputs
    - moderate: most inputs available
    - strong: all key inputs available
    """
    checks: list[bool] = []

    # Metrics availability
    checks.append(_raw(ctx.metrics, "spend") is not None)
    checks.append(_raw(ctx.metrics, "impressions") is not None)
    checks.append(
        _raw(ctx.metrics, "conversions") is not None
        or _raw(ctx.metrics, "purchases") is not None
    )

    # Economics availability
    checks.append(
        break_even_roas(ctx) is not None or break_even_cpa_range(ctx)[0] is not None
    )

    # Forecast availability (if decision depends on it)
    if decision in ("scale_review", "kill_review"):
        checks.append(forecast_roas(ctx) is not None)

    met = sum(1 for c in checks if c)
    total = len(checks)
    ratio = met / total if total > 0 else 0

    if ratio >= 0.9:
        return EVIDENCE_STRONG
    if ratio >= 0.7:
        return EVIDENCE_MODERATE
    if ratio >= 0.5:
        return EVIDENCE_WEAK
    return EVIDENCE_INSUFFICIENT


# ---------------------------------------------------------------------------
# Review suggestions (safe, human-review only)
# ---------------------------------------------------------------------------


def review_suggestions_for(decision: str, ctx: DecisionContext) -> list[str]:
    """Safe review suggestions for human review. Never executed."""

    def _bottleneck_codes():
        codes = {f.get("code") for f in ctx.diagnostics}
        return codes

    codes = _bottleneck_codes()

    if decision == "scale_review":
        suggestions = [
            "review_additional_budget_allocation",
            "review_incremental_testing",
        ]
    elif decision == "optimize":
        suggestions = []
        if "low_ctr" in codes or "ctr_decline" in codes:
            suggestions.append("review_creative_hooks")
        if "high_cpc" in codes or "high_cpm" in codes:
            suggestions.append("review_audience_targeting")
        if "low_cvr" in codes or "funnel_bottleneck" in codes:
            suggestions.append("review_landing_page_offer")
        if "creative_fatigue" in codes:
            suggestions.append("test_new_creative_angles")
        if "offer_issue" in codes:
            suggestions.append("review_offer_structure")
        if not suggestions:
            suggestions = ["review_campaign_performance"]
    elif decision == "kill_review":
        # Suggest review for potential shutdown — NOT execution
        suggestions = [
            "review_campaign_for_potential_shutdown",
            "review_spend_allocations",
        ]
    elif decision in ("tracking_issue", "data_quality_issue"):
        suggestions = [
            "review_tracking_integration",
            "review_data_freshness",
            "review_provider_connection",
        ]
    elif decision in ("insufficient_data", "learning"):
        suggestions = []
    else:  # maintain
        suggestions = []
    return suggestions


# ---------------------------------------------------------------------------
# Decision resolution (precedence)
# ---------------------------------------------------------------------------


def _diagnostic_refs(ctx: DecisionContext) -> list[dict[str, Any]]:
    """Compact references to the diagnostics that informed the decision."""
    refs: list[dict[str, Any]] = []
    for finding in ctx.diagnostics:
        refs.append(
            {
                "id": str(finding.get("id") or finding.get("code") or ""),
                "code": finding.get("code", ""),
                "category": finding.get("category", ""),
                "severity": finding.get("severity", "info"),
                "status": finding.get("status", "detected"),
            }
        )
    return refs


def resolve_decision(ctx: DecisionContext) -> Decision:
    """Resolve the decision for a context using explicit precedence.

    Precedence order (first match wins):
    tracking_issue → data_quality_issue → insufficient_data → learning
    → kill_review → scale_review → optimize → maintain
    """
    rule_checks = [
        (rule_tracking_issue, "tracking_issue", "data_quality_or_tracking_mismatch"),
        (rule_data_quality_issue, "data_quality_issue", "data_quality_issue_detected"),
        (rule_insufficient_data, "insufficient_data", "not_enough_evidence"),
        (rule_learning, "learning", "campaign_still_learning"),
        (rule_kill_review, "kill_review", "persistent_unprofitability"),
        (rule_scale_review, "scale_review", "profitable_performance"),
        (rule_optimize, "optimize", "performance_bottleneck"),
        (rule_maintain, "maintain", "healthy_performance"),
    ]

    evidence_items: list[EvidenceItem] = []

    # Build shared evidence items
    spend = current_spend(ctx)
    impressions = _raw(ctx.metrics, "impressions")
    roas = current_roas(ctx)
    cpa = current_cpa(ctx)
    break_even = break_even_roas(ctx)
    target = target_roas(ctx)
    viable = viable_cpa(ctx)

    if spend is not None:
        evidence_items.append(
            make_evidence_item(
                metric=make_metric_evidence("spend", spend, unit="money"),
                source="metrics",
                rule="sample_size",
            )
        )
    if impressions is not None:
        evidence_items.append(
            make_evidence_item(
                metric=make_metric_evidence("impressions", impressions, unit="count"),
                source="metrics",
                rule="sample_size",
            )
        )
    if roas is not None:
        evidence_items.append(
            make_evidence_item(
                metric=make_metric_evidence("roas", roas, unit="ratio"),
                source="metrics",
                rule="performance",
            )
        )
    if cpa is not None:
        evidence_items.append(
            make_evidence_item(
                metric=make_metric_evidence("cpa", cpa, unit="money"),
                source="metrics",
                rule="performance",
            )
        )
    if break_even is not None:
        evidence_items.append(
            make_evidence_item(
                threshold=make_threshold_evidence(
                    "break_even_roas", "gt", break_even, unit="ratio"
                ),
                source="economics",
                rule="economics",
            )
        )
    if viable is not None:
        evidence_items.append(
            make_evidence_item(
                threshold=make_threshold_evidence(
                    "viable_cpa", "lte", viable, unit="money"
                ),
                source="economics",
                rule="economics",
            )
        )
    if target is not None:
        evidence_items.append(
            make_evidence_item(
                threshold=make_threshold_evidence(
                    "target_roas", "gte", target, unit="ratio"
                ),
                source="goals",
                rule="goals",
            )
        )

    # Funnel bottleneck evidence (if available)
    for finding in ctx.diagnostics:
        funnel_view = (finding.get("evidence") or {}).get("funnel")
        if funnel_view and funnel_view.get("from_stage") and funnel_view.get("to_stage"):
            evidence_items.append(
                make_evidence_item(
                    funnel=make_funnel_evidence(
                        from_stage=funnel_view.get("from_stage", ""),
                        to_stage=funnel_view.get("to_stage", ""),
                        conversion_rate=_dec(funnel_view.get("conversion_rate")),
                        previous_rate=_dec(funnel_view.get("previous_rate")),
                    ),
                    source="diagnostics",
                    rule="funnel_bottleneck",
                )
            )
        elif finding.get("affected_stage"):
            evidence_items.append(
                make_evidence_item(
                    funnel=make_funnel_evidence(
                        from_stage=finding.get("affected_stage", ""),
                        to_stage=finding.get("affected_stage", ""),
                        conversion_rate=None,
                    ),
                    source="diagnostics",
                    rule="funnel_bottleneck",
                )
            )
        if finding.get("code"):
            evidence_items.append(
                make_evidence_item(
                    facts=[make_fact_evidence("finding_code", finding.get("code"))],
                    source="diagnostics",
                    rule="diagnostic_finding",
                )
            )

    for rule_fn, decision_type, reason in rule_checks:
        if rule_fn(ctx):
            # Build structured evidence for this decision
            strength = compute_evidence_strength(ctx, decision_type)
            suggestion_items = review_suggestions_for(decision_type, ctx)
            evidence = make_decision_evidence(
                primary_reason=reason,
                evidence_items=evidence_items,
                evidence_strength=strength,
                diagnostics_refs=[
                    str(f.get("id", f.get("code", ""))) for f in ctx.diagnostics
                ],
                forecast_refs=(
                    [ctx.forecast.get("metric_code", "spend")] if ctx.forecast else []
                ),
                goal_refs=[
                    g
                    for g in ("target_roas", "maximum_cpa")
                    if ctx.goal and ctx.goal.get(g) is not None
                ],
            )
            return Decision(
                decision=decision_type,
                business_id=ctx.business_id,
                entity_type=ctx.entity_type,
                entity_id=ctx.entity_id,
                entity_name=ctx.entity_name,
                evidence_strength=strength,
                primary_reason=reason,
                evidence=evidence,
                diagnostics=_diagnostic_refs(ctx),
                metrics_snapshot={
                    "spend": str(spend) if spend is not None else None,
                    "impressions": str(impressions) if impressions is not None else None,
                    "clicks": (
                        str(_raw(ctx.metrics, "clicks"))
                        if _raw(ctx.metrics, "clicks") is not None
                        else None
                    ),
                    "purchases": (
                        str(_raw(ctx.metrics, "purchases"))
                        if _raw(ctx.metrics, "purchases") is not None
                        else None
                    ),
                    "conversions": (
                        str(_raw(ctx.metrics, "conversions"))
                        if _raw(ctx.metrics, "conversions") is not None
                        else None
                    ),
                    "roas": str(roas) if roas is not None else None,
                    "cpa": str(cpa) if cpa is not None else None,
                },
                forecast_snapshot=ctx.forecast,
                severity=DECISION_SEVERITY_MAP.get(decision_type, "info"),
                rules_version=THRESHOLD_VERSION,
                review_suggestions=suggestion_items,
            )
    # Fallback (should never happen due to maintain)
    return Decision(
        decision="maintain",
        business_id=ctx.business_id,
        entity_type=ctx.entity_type,
        entity_id=ctx.entity_id,
        entity_name=ctx.entity_name,
        evidence_strength=EVIDENCE_WEAK,
        primary_reason="healthy_performance",
        evidence=make_decision_evidence(
            primary_reason="healthy_performance",
            evidence_items=evidence_items,
            evidence_strength=EVIDENCE_WEAK,
        ),
        diagnostics=_diagnostic_refs(ctx),
        metrics_snapshot={
            "spend": str(spend) if spend is not None else None,
            "impressions": str(impressions) if impressions is not None else None,
            "roas": str(roas) if roas is not None else None,
            "cpa": str(cpa) if cpa is not None else None,
        },
        forecast_snapshot=ctx.forecast,
        severity=DECISION_SEVERITY_MAP.get("maintain", "info"),
        rules_version=THRESHOLD_VERSION,
        review_suggestions=[],
    )


RULES = ALL_RULES


__all__ = [
    "DecisionContext",
    "Decision",
    "RULE_CODES",
    "RULES",
    "PERFORMANCE_CATEGORIES",
    "resolve_decision",
    "compute_evidence_strength",
    "sample_gates_met",
    "sample_sufficient",
    "has_tracking_issue",
    "has_data_quality_issue",
    "is_learning",
    "rule_tracking_issue",
    "rule_data_quality_issue",
    "rule_insufficient_data",
    "rule_learning",
    "rule_kill_review",
    "rule_scale_review",
    "rule_optimize",
    "rule_maintain",
    "break_even_roas",
    "break_even_cpa_range",
    "target_roas",
    "target_cpa",
    "viable_cpa",
    "forecast_roas",
    "current_roas",
    "current_cpa",
    "current_spend",
    "current_purchases",
    "review_suggestions_for",
    "ALL_RULES",
]