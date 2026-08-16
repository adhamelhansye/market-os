"""Recommendations service: read-only orchestration and idempotent persistence.

The service is the only place that talks to the database for decisions:

- computes deterministic decisions via the engine (which reuses the
  metrics / diagnostics / forecasting / economics / goals services);
- persists each decision idempotently using the deterministic fingerprint
  unique constraint, so recomputation never duplicates rows;
- validates filters server-side;
- never executes any action: no provider mutation, no budget change, no
  campaign edit, no notification beyond the read-only API response.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.db.models import Business, Recommendation
from src.modules.metrics import aggregation
from src.modules.metrics.aggregation import Range
from src.modules.metrics.errors import UnknownEntityError
from src.modules.recommendations import engine
from src.modules.recommendations.errors import RecommendationsFilterError
from src.modules.recommendations.rules import Decision
from src.modules.recommendations.severity import rank as decision_severity_rank
from src.modules.recommendations.thresholds import THRESHOLD_VERSION


@dataclass(frozen=True)
class ComputedDecision:
    """A decision with its persisted row (view source of truth)."""
    decision: Decision
    row: Recommendation


# ---------------------------------------------------------------------------
# Identity + persistence
# ---------------------------------------------------------------------------


def _fingerprint(
    *,
    organization_id: uuid.UUID,
    business_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID | None,
    range: Range,
) -> str:
    """Deterministic idempotency key for one decision computation."""
    parts = (
        str(organization_id),
        str(business_id),
        entity_type,
        str(entity_id or ""),
        str(range.start),
        str(range.end),
        THRESHOLD_VERSION,
    )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


async def _upsert_recommendation(
    session: AsyncSession,
    business: Business,
    decision: Decision,
    range: Range,
) -> Recommendation:
    stmt = (
        pg_insert(Recommendation)
        .values(
            organization_id=business.organization_id,
            business_id=business.id,
            entity_type=decision.entity_type,
            entity_id=decision.entity_id,
            entity_name=decision.entity_name,
            decision=decision.decision,
            evidence_strength=decision.evidence_strength,
            primary_reason=decision.primary_reason,
            diagnostics=decision.diagnostics,
            evidence=decision.evidence.to_dict(),
            review_suggestions=decision.review_suggestions,
            metrics_snapshot=decision.metrics_snapshot,
            forecast_snapshot=dict(decision.forecast_snapshot)
            if decision.forecast_snapshot
            else None,
            range_start=range.start,
            range_end=range.end,
            rules_version=decision.rules_version,
            fingerprint=_fingerprint(
                organization_id=business.organization_id,
                business_id=business.id,
                entity_type=decision.entity_type,
                entity_id=decision.entity_id,
                range=range,
            ),
        )
        .on_conflict_do_update(
            index_elements=["fingerprint"],
            set_={
                "decision": decision.decision,
                "evidence_strength": decision.evidence_strength,
                "primary_reason": decision.primary_reason,
                "diagnostics": decision.diagnostics,
                "evidence": decision.evidence.to_dict(),
                "review_suggestions": decision.review_suggestions,
                "metrics_snapshot": decision.metrics_snapshot,
                "forecast_snapshot": dict(decision.forecast_snapshot)
                if decision.forecast_snapshot
                else None,
                "updated_at": datetime.now(UTC),
            },
        )
        .returning(Recommendation)
    )
    result = await session.execute(stmt)
    row = result.scalar_one()
    await session.commit()
    return row


def _range_view(range: Range) -> dict:
    return {
        "kind": range.kind,
        "start": range.start,
        "end": range.end,
        "previous_start": range.previous_start,
        "previous_end": range.previous_end,
    }


def decision_view(computed: ComputedDecision, range: Range) -> dict:
    """Plain-dict transport view of a decision (matches DecisionRead)."""
    decision, row = computed.decision, computed.row
    return {
        "id": row.id,
        "business_id": row.business_id,
        "entity_type": decision.entity_type,
        "entity_id": decision.entity_id,
        "entity_name": decision.entity_name,
        "decision": decision.decision,
        "evidence_strength": decision.evidence_strength,
        "primary_reason": decision.primary_reason,
        "diagnostics": decision.diagnostics,
        "evidence": decision.evidence.to_dict(),
        "review_suggestions": decision.review_suggestions,
        "metrics_snapshot": decision.metrics_snapshot,
        "forecast_snapshot": dict(decision.forecast_snapshot)
        if decision.forecast_snapshot
        else None,
        "range": _range_view(range),
        "created_at": row.created_at,
        "rules_version": decision.rules_version,
    }


# ---------------------------------------------------------------------------
# Summary + filtering
# ---------------------------------------------------------------------------


def summary_of(computeds: list[ComputedDecision]) -> dict:
    counts = {decision_type: 0 for decision_type in engine.DECISION_TYPES}
    by_entity_type: dict[str, int] = {}
    for computed in computeds:
        decision_type = computed.decision.decision
        counts[decision_type] = counts.get(decision_type, 0) + 1
        entity_type = computed.decision.entity_type
        by_entity_type[entity_type] = by_entity_type.get(entity_type, 0) + 1
    return {
        "business_id": computeds[0].row.business_id if computeds else None,
        "total": len(computeds),
        "scale_review": counts.get("scale_review", 0),
        "optimize": counts.get("optimize", 0),
        "maintain": counts.get("maintain", 0),
        "kill_review": counts.get("kill_review", 0),
        "learning": counts.get("learning", 0),
        "insufficient_data": counts.get("insufficient_data", 0),
        "tracking_issue": counts.get("tracking_issue", 0),
        "data_quality_issue": counts.get("data_quality_issue", 0),
        "by_decision": counts,
        "by_entity_type": by_entity_type,
    }


_ALLOWED_ENTITY_TYPES = ("business", "campaign")


def _validate_filter(
    *, entity_type: str | None, decision: str | None, severity: str | None
) -> None:
    if entity_type is not None and entity_type not in _ALLOWED_ENTITY_TYPES:
        raise RecommendationsFilterError(f"Unsupported entity_type: {entity_type}")
    if decision is not None and decision not in engine.DECISION_TYPES:
        raise RecommendationsFilterError(f"Unknown decision: {decision}")
    if severity is not None:
        from src.modules.diagnostics.severity import is_valid as severity_is_valid

        if not severity_is_valid(severity):
            raise RecommendationsFilterError(f"Unknown severity: {severity}")


def filter_computed(
    computeds: list[ComputedDecision],
    *,
    entity_type: str | None,
    entity_id: str | None,
    decision: str | None,
    severity: str | None,
) -> list[ComputedDecision]:
    if entity_type:
        computeds = [c for c in computeds if c.decision.entity_type == entity_type]
    if entity_id:
        computeds = [
            c for c in computeds if str(c.decision.entity_id or "") == str(entity_id)
        ]
    if decision:
        computeds = [c for c in computeds if c.decision.decision == decision]
    if severity:
        computeds = [
            c for c in computeds if c.decision.severity == severity
        ]
    return computeds


async def _validate_entity_filter(
    session: AsyncSession,
    business: Business,
    entity_type: str | None,
    entity_id: uuid.UUID | None,
) -> None:
    """Filters never trust client ids: entity must resolve inside the business."""
    if entity_id is None or entity_type is None:
        return
    if entity_type == "business":
        if entity_id != business.id:
            raise UnknownEntityError(
                "business not found in this tenant", details={"id": str(entity_id)}
            )
        return
    if entity_type == "campaign":
        await aggregation.resolve_entity(session, business.id, "campaign", entity_id)
        return
    raise RecommendationsFilterError(
        f"entity_id filtering not supported for entity_type: {entity_type}"
    )


# ---------------------------------------------------------------------------
# Computation orchestration
# ---------------------------------------------------------------------------


async def _compute_all(
    session: AsyncSession,
    business: Business,
    range: Range,
    settings: Settings,
) -> list[ComputedDecision]:
    """Compute + persist the business decision and every campaign decision."""
    computed: list[ComputedDecision] = []

    business_decision = await engine.decide_business(session, business, range, settings)
    computed.append(
        ComputedDecision(
            decision=business_decision,
            row=await _upsert_recommendation(session, business, business_decision, range),
        )
    )

    rows = await aggregation.campaign_rollups(
        session, business.id, range, currency=business.currency
    )
    for row in rows:
        campaign_id = row.get("campaign_id")
        campaign_decision = await engine.decide_campaign(
            session, business, campaign_id, range, settings
        )
        computed.append(
            ComputedDecision(
                decision=campaign_decision,
                row=await _upsert_recommendation(
                    session, business, campaign_decision, range
                ),
            )
        )
    return computed


def _sort_computeds(computeds: list[ComputedDecision]) -> list[ComputedDecision]:
    return sorted(
        computeds,
        key=lambda c: (
            -decision_severity_rank(c.decision.severity or "info"),
            c.decision.decision,
            c.decision.entity_type,
            str(c.decision.entity_id or ""),
        ),
    )


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


async def recommendations_for_business(
    session: AsyncSession,
    business: Business,
    range: Range,
    settings: Settings,
    *,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    decision: str | None = None,
    severity: str | None = None,
) -> dict:
    _validate_filter(entity_type=entity_type, decision=decision, severity=severity)
    await _validate_entity_filter(session, business, entity_type, entity_id)
    computeds = _sort_computeds(
        filter_computed(
            await _compute_all(session, business, range, settings),
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None,
            decision=decision,
            severity=severity,
        )
    )
    return {
        "business_id": business.id,
        "currency": business.currency,
        "range": _range_view(range),
        "decisions": [decision_view(c, range) for c in computeds],
        "summary": summary_of(computeds),
    }


async def recommendations_summary(
    session: AsyncSession,
    business: Business,
    range: Range,
    settings: Settings,
    *,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    decision: str | None = None,
    severity: str | None = None,
) -> dict:
    data = await recommendations_for_business(
        session,
        business,
        range,
        settings,
        entity_type=entity_type,
        entity_id=entity_id,
        decision=decision,
        severity=severity,
    )
    return data["summary"]


async def campaign_recommendation(
    session: AsyncSession,
    business: Business,
    campaign_id: uuid.UUID,
    range: Range,
    settings: Settings,
) -> dict:
    campaign_decision = await engine.decide_campaign(
        session, business, campaign_id, range, settings
    )
    row = await _upsert_recommendation(session, business, campaign_decision, range)
    return decision_view(ComputedDecision(decision=campaign_decision, row=row), range)


async def generate(
    session: AsyncSession,
    business: Business,
    range: Range,
    settings: Settings,
) -> dict:
    """Recompute and persist all decisions for the range (idempotent)."""
    computeds = _sort_computeds(await _compute_all(session, business, range, settings))
    return {
        "business_id": business.id,
        "currency": business.currency,
        "range": _range_view(range),
        "decisions": [decision_view(c, range) for c in computeds],
        "summary": summary_of(computeds),
    }


__all__ = [
    "campaign_recommendation",
    "decision_view",
    "filter_computed",
    "generate",
    "recommendations_for_business",
    "recommendations_summary",
    "summary_of",
]