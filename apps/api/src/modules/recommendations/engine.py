"""Deterministic decision engine: orchestration over deterministic sources.

Pipeline (Phase 4B):
    Metrics → Diagnostics → Forecast → Economics → Goals → Decision Engine
    → Structured Decision (review recommendation only)

The engine gathers the same canonical aggregates the metrics/diagnostics
endpoints use, builds a `DecisionContext` from them, and delegates the
decision to the pure rules in `rules.py` (explicit precedence). It never
queries providers directly, never recomputes KPI formulas, never invokes an
LLM and never executes any action — decisions are review recommendations
only.

Scope:

- `decide_business`  — business-grain decision. Purchases/revenue/cpa are
  attributed; tracking and data-quality findings are business-level.
- `decide_campaign`  — campaign-grain decision. Campaigns have no purchase
  attribution (Phase 3B rule), so CPA is unavailable and ROAS uses
  Meta-reported conversion value. Business-level tracking/data-quality
  findings still gate the decision because they affect every campaign's
  truthfulness.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.db.models import Business
from src.modules.diagnostics import engine as diagnostics_engine
from src.modules.diagnostics.rules import (
    EntityContext,
    RuleContext,
    apply_business_rules,
    apply_entity_rules,
)
from src.modules.economics.service import summary_data
from src.modules.forecasting.service import campaign_forecast
from src.modules.forecasting.service import summary as forecast_summary
from src.modules.metrics import aggregation
from src.modules.metrics import service as metrics_service
from src.modules.metrics.aggregation import Range
from src.modules.metrics.errors import UnknownEntityError
from src.modules.recommendations.evidence import DecisionEvidence
from src.modules.recommendations.rules import Decision, DecisionContext, resolve_decision
from src.modules.recommendations.severity import (
    DECISION_PRECEDENCE,
    DECISION_TYPES,
    EVIDENCE_STRENGTHS,
)

HORIZON_DAYS = 30


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------


def _measure_raw(measure: dict | None):
    """Plain value from a KPI measure dict (available only)."""
    if not measure or measure.get("status") != "available":
        return None
    return measure.get("value")


def _measure_view(measure: dict | None) -> dict:
    """Pass-through KPI measure view (value + status + reason)."""
    if measure is None:
        return {"value": None, "status": "unavailable", "reason": "unavailable"}
    return dict(measure)


def _summary_metrics(summary: dict) -> dict:
    """Canonical decision metric map from the business summary."""
    return {
        "spend": _measure_raw(summary.get("spend")),
        "impressions": _measure_raw(summary.get("impressions")),
        "clicks": _measure_raw(summary.get("clicks")),
        "purchases": _measure_raw(summary.get("purchases")),
        "conversions": _measure_raw(summary.get("conversions")),
        "revenue": _measure_raw(summary.get("revenue")),
        "ctr": _measure_view(summary.get("ctr")),
        "cpa": _measure_view(summary.get("cpa")),
        "roas": _measure_view(summary.get("roas")),
        "cvr": _measure_view(summary.get("cvr")),
        "contribution_profit": _measure_raw(summary.get("contribution_profit")),
        "break_even_roas": _measure_raw(summary.get("break_even_roas")),
        "break_even_cpa": _measure_raw(summary.get("break_even_cpa")),
    }


def _campaign_metrics(entity_view: dict) -> dict:
    """Canonical decision metric map from a campaign entity view.

    Campaigns have no purchase attribution (Phase 3B): purchases/revenue/
    cpa/cvr are explicitly unavailable — never invented.
    """
    return {
        "spend": entity_view.get("spend"),
        "impressions": entity_view.get("impressions"),
        "clicks": entity_view.get("clicks"),
        "purchases": None,
        "conversions": entity_view.get("conversions"),
        "revenue": None,
        "ctr": _measure_view(entity_view.get("ctr")),
        "cpa": {
            "value": None,
            "status": "unavailable",
            "reason": "no purchase attribution at this grain",
        },
        "roas": _measure_view(entity_view.get("roas")),
        "cvr": {
            "value": None,
            "status": "unavailable",
            "reason": "no purchase attribution at this grain",
        },
        "contribution_profit": None,
        "break_even_roas": None,
        "break_even_cpa": None,
    }


def _goal_view(goal) -> dict | None:
    """BusinessGoal ORM → plain dict for the decision rules.

    Only decision-relevant fields are carried; the engine never trusts
    client-supplied goals.
    """
    if goal is None:
        return None
    return {
        "target_revenue": goal.target_revenue,
        "target_profit": goal.target_profit,
        "ad_budget": goal.ad_budget,
        "maximum_cpa": goal.maximum_cpa,
        "target_roas": goal.target_roas,
        "currency": goal.currency,
    }


def _profit_value(profile: dict) -> Decimal | None:
    value = profile.get("average_contribution_profit")
    return Decimal(str(value)) if value is not None else None


def _meta_is_stale(quality: dict | None) -> bool:
    if not quality:
        return False
    for item in quality.get("providers", []):
        if item.get("provider") == "meta" and item.get("freshness_status") == "stale":
            return True
    return False


def _range_days(range: Range) -> int:
    return (range.end - range.start).days + 1


def _business_context(
    *,
    profile: dict,
    ctx: RuleContext,
    summary: dict,
    diagnostics: list,
    range: Range,
    range_days: int,
    forecast: dict | None,
    business: Business,
) -> DecisionContext:
    return DecisionContext(
        business_id=business.id,
        entity_type="business",
        entity_id=None,
        entity_name=business.name,
        metrics=_summary_metrics(summary),
        previous_metrics=None,
        diagnostics=diagnostics,
        performance_state=None,
        scaling_readiness=None,
        forecast=forecast,
        economics=profile,
        goal=_goal_view(profile.get("current_goal")),
        rows=range_days,
        range_length_days=range_days,
        data_quality=ctx.quality,
        data_stale=_meta_is_stale(ctx.quality),
        tracking_issue=False,
        currency=business.currency,
    )


# ---------------------------------------------------------------------------
# Shared diagnostics context (mirrors the Phase 3B diagnostics engine)
# ---------------------------------------------------------------------------


async def _rule_context(
    session: AsyncSession,
    business: Business,
    range: Range,
    settings: Settings,
    *,
    with_previous_funnel: bool,
) -> tuple[RuleContext, dict, dict]:
    profile = await summary_data(session, business)
    current = await metrics_service.build_summary(session, business, range)
    previous = await metrics_service.build_summary(
        session, business, diagnostics_engine.previous_range(range)
    )
    funnel = await metrics_service.funnel(session, business, range)
    previous_funnel = (
        await metrics_service.funnel(session, business, diagnostics_engine.previous_range(range))
        if with_previous_funnel
        else None
    )
    quality = await metrics_service.data_quality(session, business, range, settings)
    sync_failures = await diagnostics_engine._recent_sync_failures(session, business.id)

    ctx = RuleContext(
        business_id=business.id,
        business_name=business.name,
        currency=business.currency,
        timezone=business.timezone,
        range=range,
        profile=profile,
        goal=profile.get("current_goal"),
        summary=current,
        previous_summary=previous,
        funnel=funnel,
        previous_funnel=previous_funnel,
        quality=quality,
        sync_failures=sync_failures,
    )
    return ctx, profile, current


def _finding_views(findings: list, range: Range) -> list[dict]:
    return [diagnostics_engine.finding_view(finding, range) for finding in findings]


# ---------------------------------------------------------------------------
# Business-grain decision
# ---------------------------------------------------------------------------


async def decide_business(
    session: AsyncSession,
    business: Business,
    range: Range,
    settings: Settings,
) -> Decision:
    """Deterministic business-grain decision (review recommendation)."""
    ctx, profile, summary = await _rule_context(
        session, business, range, settings, with_previous_funnel=True
    )
    findings = apply_business_rules(ctx)
    range_days = _range_days(range)

    forecast = None
    try:
        forecast = (
            await forecast_summary(
                session, business, horizon_days=HORIZON_DAYS, settings=settings
            )
        ).model_dump(mode="json")
    except Exception:
        # Forecasts are evidence, never a blocker: unavailable forecasts
        # degrade the decision gracefully instead of failing it.
        forecast = None

    decision_ctx = _business_context(
        profile=profile,
        ctx=ctx,
        summary=summary,
        diagnostics=_finding_views(findings, range),
        range=range,
        range_days=range_days,
        forecast=forecast,
        business=business,
    )
    return resolve_decision(decision_ctx)


# ---------------------------------------------------------------------------
# Campaign-grain decision
# ---------------------------------------------------------------------------


async def decide_campaign(
    session: AsyncSession,
    business: Business,
    campaign_id: uuid.UUID,
    range: Range,
    settings: Settings,
) -> Decision:
    """Deterministic campaign-grain decision (review recommendation)."""
    ctx, profile, _summary = await _rule_context(
        session, business, range, settings, with_previous_funnel=False
    )

    rows = await aggregation.campaign_rollups(
        session, business.id, range, currency=business.currency
    )
    row = next((r for r in rows if str(r.get("campaign_id")) == str(campaign_id)), None)
    if row is None:
        raise UnknownEntityError(
            "campaign not found in this business", details={"id": str(campaign_id)}
        )
    entity_view = metrics_service.entity_metrics_view(
        row, id_label="campaign_id", extra_labels=("ad_account_id",), currency=business.currency
    )
    previous_rows = await aggregation.campaign_rollups(
        session, business.id, diagnostics_engine.previous_range(range),
        currency=business.currency,
    )
    previous_row = next(
        (r for r in previous_rows if str(r.get("campaign_id")) == str(campaign_id)), None
    )
    previous_view = None
    if previous_row is not None:
        previous_view = metrics_service.entity_metrics_view(
            previous_row, id_label="campaign_id", extra_labels=("ad_account_id",),
            currency=business.currency,
        )
    entity = EntityContext(
        entity_type="campaign",
        entity_id=campaign_id,
        entity_name=entity_view.get("name"),
        metrics=entity_view,
        previous_metrics=previous_view,
        rows=int(row.get("rows") or 0),
        range_length_days=_range_days(range),
    )

    entity_findings = apply_entity_rules(ctx, entity)
    business_findings = apply_business_rules(ctx)
    # Business-level tracking/data-quality findings gate campaign decisions
    # too: they affect the truthfulness of every campaign.
    diagnostics = [
        *business_findings,
        *entity_findings,
    ]
    diagnostics = _finding_views(diagnostics, range)

    performance_state = diagnostics_engine._performance_state(ctx, entity, entity_findings)
    scaling_readiness = diagnostics_engine._scaling_readiness(ctx, entity, entity_findings)

    forecast = None
    try:
        forecast = (
            await campaign_forecast(
                session, business, campaign_id, horizon_days=HORIZON_DAYS, settings=settings
            )
        ).model_dump(mode="json")
    except Exception:
        forecast = None

    decision_ctx = DecisionContext(
        business_id=business.id,
        entity_type="campaign",
        entity_id=campaign_id,
        entity_name=entity.entity_name or entity_view.get("name"),
        metrics=_campaign_metrics(entity_view),
        previous_metrics=None,
        diagnostics=diagnostics,
        performance_state=performance_state,
        scaling_readiness=scaling_readiness,
        forecast=forecast,
        economics=profile,
        goal=_goal_view(profile.get("current_goal")),
        rows=int(row.get("rows") or 0),
        range_length_days=_range_days(range),
        data_quality=ctx.quality,
        data_stale=_meta_is_stale(ctx.quality),
        tracking_issue=False,
        currency=business.currency,
    )
    return resolve_decision(decision_ctx)


__all__ = [
    "DECISION_TYPES",
    "DECISION_PRECEDENCE",
    "EVIDENCE_STRENGTHS",
    "decide_business",
    "decide_campaign",
    "resolve_decision",
    "Decision",
    "DecisionContext",
    "DecisionEvidence",
]