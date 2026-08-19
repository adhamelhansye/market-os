"""Diagnostics engine: orchestration over the metrics layer.

Pipeline (spec §40):
    metrics service ─► KPI engine ─► diagnostic engine

The engine gathers the same canonical aggregates the metrics endpoints use
(current + previous period), builds a `RuleContext`, applies the pure rules
from rules.py and deduplicates by stable fingerprint. It never queries
providers directly and never recalculates KPI formulas.

Also computes, deterministically:

- campaign performance states (insufficient_data / learning / healthy /
  attention / inefficient / profitable / unprofitable / stale_data);
- campaign scaling-readiness (informational status — diagnostics only,
  never an action);
- per-finding summary counters.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.db.models import Business, IntegrationConnection, SyncRun
from src.modules.diagnostics import thresholds as th
from src.modules.diagnostics.evidence import (
    ENTITY_TYPE_AD,
    ENTITY_TYPE_AD_SET,
    ENTITY_TYPE_BUSINESS,
    ENTITY_TYPE_CAMPAIGN,
    ENTITY_TYPES,
    STATUS_INSUFFICIENT_DATA,
)
from src.modules.diagnostics.rules import (
    EntityContext,
    RuleContext,
    apply_business_rules,
    apply_entity_rules,
)
from src.modules.diagnostics.severity import (
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_INFO,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    max_severity,
    rank,
)
from src.modules.economics.service import summary_data
from src.modules.metrics import aggregation
from src.modules.metrics import service as metrics_service
from src.modules.metrics.aggregation import Range
from src.modules.metrics.errors import UnknownEntityError
from src.modules.metrics.kpi_engine import STATUS_AVAILABLE

# Campaign performance states (deterministic, see docs/architecture/diagnostics.md).
STATE_INSUFFICIENT_DATA = "insufficient_data"
STATE_LEARNING = "learning"
STATE_HEALTHY = "healthy"
STATE_ATTENTION = "attention"
STATE_INEFFICIENT = "inefficient"
STATE_PROFITABLE = "profitable"
STATE_UNPROFITABLE = "unprofitable"
STATE_STALE_DATA = "stale_data"

STATE_ORDER = (
    STATE_INSUFFICIENT_DATA,
    STATE_STALE_DATA,
    STATE_LEARNING,
    STATE_UNPROFITABLE,
    STATE_ATTENTION,
    STATE_PROFITABLE,
    STATE_INEFFICIENT,
    STATE_HEALTHY,
)

# Scaling readiness statuses (informational only).
SCALING_INSUFFICIENT_DATA = "insufficient_data"
SCALING_LEARNING = "learning"
SCALING_STABLE = "stable"
SCALING_PERFORMANCE_POSITIVE = "performance_positive"
SCALING_PERFORMANCE_NEGATIVE = "performance_negative"

_ENTITY_ROLLUPS = {
    ENTITY_TYPE_CAMPAIGN: (aggregation.campaign_rollups, "campaign_id", ("ad_account_id",)),
    ENTITY_TYPE_AD_SET: (aggregation.ad_set_rollups, "ad_set_id", ("campaign_id",)),
    ENTITY_TYPE_AD: (aggregation.ad_rollups, "ad_id", ("campaign_id", "ad_set_id")),
}


def previous_range(range: Range) -> Range:
    if range.previous_start is None or range.previous_end is None:
        return Range(kind=range.kind, start=range.end, end=range.end)
    return Range(
        kind=range.kind,
        start=range.previous_start,
        end=range.previous_end,
    )


def _dec(value) -> Decimal | None:
    """Coerce measure/raw serialized values (str/Decimal/int) to Decimal."""
    if value is None:
        return None
    return Decimal(str(value))


def _val(measure: dict | None) -> Decimal | None:
    if not measure or measure.get("status") != STATUS_AVAILABLE:
        return None
    return _dec(measure.get("value"))


def _raw(entity_metrics: dict, code: str):
    return _dec(entity_metrics.get(code))


async def _recent_sync_failures(session: AsyncSession, business_id: uuid.UUID) -> int:
    since = datetime.now(UTC) - timedelta(hours=24)
    return int(
        await session.scalar(
            select(func.count(SyncRun.id))
            .join(IntegrationConnection, IntegrationConnection.id == SyncRun.connection_id)
            .where(
                IntegrationConnection.business_id == business_id,
                SyncRun.status == "failed",
                SyncRun.started_at >= since,
            )
        )
        or 0
    )


def _meta_is_stale(ctx: RuleContext) -> bool:
    if ctx.quality is None:
        return False
    for item in ctx.quality.get("providers", []):
        if item.get("provider") == "meta" and item.get("freshness_status") == "stale":
            return True
    return False


def _traffic_creative_codes() -> frozenset[str]:
    return frozenset(
        (
            "low_ctr",
            "ctr_decline",
            "high_cpc",
            "high_cpm",
            "creative_low_ctr",
            "possible_creative_fatigue",
        )
    )


def _performance_state(ctx: RuleContext, entity: EntityContext, findings: list) -> str:
    """Deterministic campaign state from evidence (first match wins)."""
    has_facts = entity.rows > 0
    if not has_facts:
        return STATE_INSUFFICIENT_DATA
    if _meta_is_stale(ctx):
        return STATE_STALE_DATA
    spend = _raw(entity.metrics, "spend")
    impressions = _raw(entity.metrics, "impressions")
    if (
        spend is None
        or impressions is None
        or Decimal(spend) < th.value(th.SAMPLE_MIN_SPEND)
        or Decimal(impressions) < th.value(th.SAMPLE_MIN_IMPRESSIONS)
    ):
        return STATE_LEARNING
    roas = _val(entity.metrics.get("roas"))
    break_even = ctx.profile.get("break_even_roas")
    break_even_decimal = Decimal(break_even) if break_even is not None else None
    target = None
    if ctx.goal and ctx.goal.get("target_roas") is not None:
        target = Decimal(ctx.goal["target_roas"])
    if roas is not None and break_even_decimal is not None and roas < break_even_decimal:
        return STATE_UNPROFITABLE
    severities = [f.severity for f in findings if f.status != STATUS_INSUFFICIENT_DATA]
    highest = max_severity(severities)
    profitable = roas is not None and (
        break_even_decimal is None or roas >= break_even_decimal
    ) and (target is None or roas >= target)
    if highest in (SEVERITY_HIGH, SEVERITY_CRITICAL) and not profitable:
        return STATE_ATTENTION
    if profitable:
        return STATE_PROFITABLE
    cluster = _traffic_creative_codes()
    cluster_count = sum(1 for f in findings if f.code in cluster)
    if cluster_count >= 2:
        return STATE_INEFFICIENT
    if findings:
        return STATE_ATTENTION
    return STATE_HEALTHY


def _scaling_readiness(
    ctx: RuleContext, entity: EntityContext, findings: list
) -> dict[str, Any]:
    """Informational readiness: whether evidence exists to review scaling.

    This is a diagnostic status, never an action. Campaign grain has no
    purchase attribution, so conversion evidence uses Meta-reported
    conversions (labelled `meta_reported`, never claimed as purchases).
    """
    spend = _raw(entity.metrics, "spend")
    impressions = _raw(entity.metrics, "impressions")
    conversions = _raw(entity.metrics, "conversions")
    gates: dict[str, str] = {
        "spend": "money",
        "impressions": "count",
        "days": "count",
        "conversions": "count",
    }
    gate_values = {
        "spend": spend,
        "impressions": impressions,
        "days": entity.rows,
        "conversions": conversions,
    }
    gates_met = (
        spend is not None
        and Decimal(spend) >= th.value(th.SAMPLE_MIN_SPEND)
        and impressions is not None
        and Decimal(impressions) >= th.value(th.SAMPLE_MIN_IMPRESSIONS)
        and entity.rows >= int(th.value(th.SCALING_MIN_DAYS))
        and conversions is not None
        and Decimal(conversions) >= th.value(th.SAMPLE_MIN_CONVERSIONS)
        and not _meta_is_stale(ctx)
    )
    gates_read: list[dict] = [
        {"code": code, "value": gate_values[code], "unit": unit}
        for code, unit in gates.items()
    ]
    if not gates_met:
        return {
            "status": SCALING_INSUFFICIENT_DATA,
            "ready_for_review": False,
            "gates": gates_read,
        }
    roas = _val(entity.metrics.get("roas"))
    break_even = ctx.profile.get("break_even_roas")
    break_even_decimal = Decimal(break_even) if break_even is not None else None
    target = None
    if ctx.goal and ctx.goal.get("target_roas") is not None:
        target = Decimal(ctx.goal["target_roas"])
    if roas is not None and break_even_decimal is not None and roas < break_even_decimal:
        return {
            "status": SCALING_PERFORMANCE_NEGATIVE,
            "ready_for_review": False,
            "gates": gates_read,
        }
    if roas is not None and (target is None or roas >= target):
        blocking = any(
            f.status != STATUS_INSUFFICIENT_DATA
            and f.severity in (SEVERITY_HIGH, SEVERITY_CRITICAL)
            for f in findings
        )
        return {
            "status": SCALING_PERFORMANCE_POSITIVE,
            "ready_for_review": not blocking,
            "gates": gates_read,
        }
    return {"status": SCALING_STABLE, "ready_for_review": False, "gates": gates_read}


async def _entity_contexts(
    session: AsyncSession,
    business: Business,
    range: Range,
    entity_type: str,
) -> list[EntityContext]:
    rollup_fn, id_label, extra_labels = _ENTITY_ROLLUPS[entity_type]
    rows = await rollup_fn(session, business.id, range, currency=business.currency)
    previous = await rollup_fn(
        session, business.id, previous_range(range), currency=business.currency
    )
    previous_by_id = {str(row[id_label]): row for row in previous}

    contexts: list[EntityContext] = []
    for row in rows:
        view = metrics_service.entity_metrics_view(
            row, id_label=id_label, extra_labels=extra_labels, currency=business.currency
        )
        prev_row = previous_by_id.get(str(row[id_label]))
        prev_view = None
        if prev_row is not None:
            prev_view = metrics_service.entity_metrics_view(
                prev_row, id_label=id_label, extra_labels=extra_labels,
                currency=business.currency,
            )
        contexts.append(
            EntityContext(
                entity_type=entity_type,
                entity_id=row.get(id_label),
                entity_name=row.get(f"{id_label.replace('_id', '')}_name"),
                metrics=view,
                previous_metrics=prev_view,
                rows=int(row.get("rows") or 0),
                range_length_days=(range.end - range.start).days + 1,
            )
        )
    return contexts


def _sort_findings(findings: list) -> list:
    return sorted(
        findings,
        key=lambda f: (
            -rank(f.severity),
            f.code,
            f.entity_type,
            str(f.entity_id or ""),
        ),
    )


def finding_view(finding, range: Range) -> dict:
    """Plain-dict transport view of a finding (matches FindingRead)."""
    evidence = finding.evidence
    return {
        "id": finding.id,
        "business_id": finding.business_id,
        "business_name": finding.business_name,
        "entity_type": finding.entity_type,
        "entity_id": finding.entity_id,
        "entity_name": finding.entity_name,
        "category": finding.category,
        "code": finding.code,
        "severity": finding.severity,
        "status": finding.status,
        "title_key": finding.title_key,
        "description_key": finding.description_key,
        "reason": finding.reason,
        "evidence": {
            "metric": {
                "code": evidence.metric.code,
                "current": evidence.metric.current,
                "previous": evidence.metric.previous,
            }
            if evidence.metric is not None
            else None,
            "threshold": {
                "code": evidence.threshold.code,
                "operator": evidence.threshold.operator,
                "value": evidence.threshold.value,
                "unit": evidence.threshold.unit,
            }
            if evidence.threshold is not None
            else None,
            "comparison": {
                "change_percent": evidence.comparison.change_percent,
                "status": evidence.comparison.status,
                "reason": evidence.comparison.reason,
            }
            if evidence.comparison is not None
            else None,
            "funnel": {
                "from_stage": evidence.funnel.from_stage,
                "to_stage": evidence.funnel.to_stage,
                "conversion_rate": evidence.funnel.conversion_rate,
                "previous_rate": evidence.funnel.previous_rate,
            }
            if evidence.funnel is not None
            else None,
            "facts": [
                {"code": fact.code, "value": fact.value, "unit": fact.unit}
                for fact in evidence.facts
            ],
        },
        "affected_stage": finding.affected_stage,
        "range": _range_view(
            Range(kind=range.kind, start=finding.range_start, end=finding.range_end)
        ),
        "currency": finding.currency,
        "review_status": finding.review_status,
    }


def summary_of(findings: list) -> dict:
    counts = {severity: 0 for severity in (SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
                                           SEVERITY_LOW, SEVERITY_INFO)}
    insufficient = 0
    affected: set[tuple[str, str]] = set()
    for finding in findings:
        if finding.status == STATUS_INSUFFICIENT_DATA:
            insufficient += 1
        else:
            counts[finding.severity] = counts.get(finding.severity, 0) + 1
        affected.add((finding.entity_type, str(finding.entity_id or "")))
    return {
        "total_findings": len(findings),
        "critical": counts[SEVERITY_CRITICAL],
        "high": counts[SEVERITY_HIGH],
        "medium": counts[SEVERITY_MEDIUM],
        "low": counts[SEVERITY_LOW],
        "info": counts[SEVERITY_INFO],
        "insufficient_data": insufficient,
        "affected_entities": len(affected),
    }


async def diagnose_business(
    session: AsyncSession, business: Business, range: Range, settings: Settings
) -> dict:
    """Runs the full deterministic diagnostics for a business + range."""
    profile = await summary_data(session, business)
    current = await metrics_service.build_summary(session, business, range)
    previous = await metrics_service.build_summary(session, business, previous_range(range))
    funnel = await metrics_service.funnel(session, business, range)
    previous_funnel = await metrics_service.funnel(session, business, previous_range(range))
    quality = await metrics_service.data_quality(session, business, range, settings)
    sync_failures = await _recent_sync_failures(session, business.id)

    current_goal = profile.get("current_goal")
    goal_view = (
        {
            "target_revenue": current_goal.target_revenue,
            "target_profit": current_goal.target_profit,
            "maximum_cpa": current_goal.maximum_cpa,
            "target_roas": current_goal.target_roas,
            "ad_budget": current_goal.ad_budget,
        }
        if current_goal is not None
        else None
    )
    ctx = RuleContext(
        business_id=business.id,
        business_name=business.name,
        currency=business.currency,
        timezone=business.timezone,
        range=range,
        profile=profile,
        goal=goal_view,
        summary=current,
        previous_summary=previous,
        funnel=funnel,
        previous_funnel=previous_funnel,
        quality=quality,
        sync_failures=sync_failures,
    )

    findings = apply_business_rules(ctx)
    campaign_states: list[dict] = []
    for entity_type in (ENTITY_TYPE_CAMPAIGN, ENTITY_TYPE_AD_SET, ENTITY_TYPE_AD):
        for entity in await _entity_contexts(session, business, range, entity_type):
            entity_findings = apply_entity_rules(ctx, entity)
            findings.extend(entity_findings)
            if entity_type == ENTITY_TYPE_CAMPAIGN:
                campaign_states.append(
                    {
                        "campaign_id": entity.entity_id,
                        "name": entity.entity_name,
                        "performance_state": _performance_state(ctx, entity, entity_findings),
                        "scaling_readiness": _scaling_readiness(ctx, entity, entity_findings),
                        "finding_count": sum(
                            1 for f in entity_findings if f.status != STATUS_INSUFFICIENT_DATA
                        ),
                        "highest_severity": max_severity(
                            [f.severity for f in entity_findings]
                        ),
                    }
                )

    unique = {finding.id: finding for finding in findings}
    ordered = _sort_findings(list(unique.values()))
    campaign_states.sort(key=lambda s: (STATE_ORDER.index(s["performance_state"]), str(s["name"])))

    return {
        "business_id": business.id,
        "currency": business.currency,
        "timezone": business.timezone,
        "range": _range_view(range),
        "findings": ordered,
        "campaign_states": campaign_states,
        "summary": summary_of(ordered),
    }


async def diagnose_campaign(
    session: AsyncSession,
    business: Business,
    campaign_id: uuid.UUID,
    range: Range,
    settings: Settings,
) -> dict:
    """Deterministic diagnostics for one campaign (resolved inside the business)."""
    profile = await summary_data(session, business)
    current = await metrics_service.build_summary(session, business, range)
    previous = await metrics_service.build_summary(session, business, previous_range(range))
    funnel = await metrics_service.funnel(session, business, range)
    quality = await metrics_service.data_quality(session, business, range, settings)
    sync_failures = await _recent_sync_failures(session, business.id)

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
        previous_funnel=None,
        quality=quality,
        sync_failures=sync_failures,
    )

    rows = await aggregation.campaign_rollups(
        session, business.id, range, currency=business.currency
    )
    row = next((r for r in rows if str(r.get("campaign_id")) == str(campaign_id)), None)
    if row is None:
        raise UnknownEntityError(
            "campaign not found in this business", details={"id": str(campaign_id)}
        )
    metrics_view = metrics_service.entity_metrics_view(
        row, id_label="campaign_id", extra_labels=("ad_account_id",), currency=business.currency
    )
    previous_rows = await aggregation.campaign_rollups(
        session, business.id, previous_range(range), currency=business.currency
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
        entity_type=ENTITY_TYPE_CAMPAIGN,
        entity_id=campaign_id,
        entity_name=metrics_view.get("name"),
        metrics=metrics_view,
        previous_metrics=previous_view,
        rows=int(row.get("rows") or 0),
        range_length_days=(range.end - range.start).days + 1,
    )
    findings = _sort_findings(apply_entity_rules(ctx, entity))

    meta_quality = None
    for item in quality.get("providers", []):
        if item.get("provider") == "meta":
            meta_quality = item

    return {
        "business_id": business.id,
        "currency": business.currency,
        "timezone": business.timezone,
        "range": _range_view(range),
        "campaign": metrics_view,
        "performance_state": _performance_state(ctx, entity, findings),
        "scaling_readiness": _scaling_readiness(ctx, entity, findings),
        "findings": findings,
        "data_quality": meta_quality,
    }


def filter_findings(
    findings: list,
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    severity: str | None = None,
    category: str | None = None,
    status: str | None = None,
) -> list:
    """Deterministic client-side filtering after computation."""
    result = findings
    if entity_type:
        result = [f for f in result if f.entity_type == entity_type]
    if entity_id:
        result = [f for f in result if str(f.entity_id or "") == str(entity_id)]
    if severity:
        result = [f for f in result if f.severity == severity]
    if category:
        result = [f for f in result if f.category == category]
    if status:
        result = [f for f in result if f.status == status]
    return result


def _range_view(range: Range) -> dict:
    return {
        "kind": range.kind,
        "start": range.start,
        "end": range.end,
        "previous_start": range.previous_start,
        "previous_end": range.previous_end,
    }


async def validate_entity_filter(
    session: AsyncSession,
    business_id: uuid.UUID,
    entity_type: str | None,
    entity_id: uuid.UUID | None,
) -> None:
    """Filters never trust client ids: entity must resolve inside the business."""
    from src.modules.diagnostics.errors import DiagnosticsFilterError

    if entity_id is None or entity_type is None:
        return
    if entity_type not in ENTITY_TYPES:
        raise DiagnosticsFilterError(f"Unsupported entity_type: {entity_type}")
    if entity_type == ENTITY_TYPE_BUSINESS:
        if entity_id != business_id:
            raise UnknownEntityError(
                "business not found in this tenant", details={"id": str(entity_id)}
            )
        return
    if entity_type in (ENTITY_TYPE_CAMPAIGN, ENTITY_TYPE_AD_SET, ENTITY_TYPE_AD):
        await aggregation.resolve_entity(session, business_id, entity_type, entity_id)
        return
    raise DiagnosticsFilterError(
        f"entity_id filtering not supported for entity_type: {entity_type}"
    )


__all__ = [
    "STATE_INSUFFICIENT_DATA",
    "STATE_LEARNING",
    "STATE_HEALTHY",
    "STATE_ATTENTION",
    "STATE_INEFFICIENT",
    "STATE_PROFITABLE",
    "STATE_UNPROFITABLE",
    "STATE_STALE_DATA",
    "STATE_ORDER",
    "SCALING_INSUFFICIENT_DATA",
    "SCALING_LEARNING",
    "SCALING_STABLE",
    "SCALING_PERFORMANCE_POSITIVE",
    "SCALING_PERFORMANCE_NEGATIVE",
    "diagnose_business",
    "diagnose_campaign",
    "filter_findings",
    "validate_entity_filter",
    "previous_range",
    "finding_view",
]
