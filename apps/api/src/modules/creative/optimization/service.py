"""Creative optimization orchestration service (Phase 8E).

Consumes Phase 8D learning artifacts, Phase 8C performance evidence and
Phase 7 strategy context to produce a versioned optimization plan.

- reads the LATEST persisted Phase 8D snapshot when available (learning
  artifacts are canonical once generated),
- otherwise computes the learning report fresh via the Phase 8D service,
- extracts per-entity strategy-context availability from concept
  descriptors (positioning/offer/messaging/funnel references),
- runs the pure optimization engine,
- persists immutable fingerprint-idempotent snapshots.

No LLM, no provider calls, no execution paths. Recommendations are
review-only.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError
from src.db.models import Business
from src.db.models.creative import (
    CreativeConcept,
    CreativeConceptPortfolio,
)
from src.db.models.creative_optimization import CreativeOptimizationSnapshot
from src.modules.creative.learning.service import build_learning_report, empty_report
from src.modules.creative.optimization import engine as optimization_engine
from src.modules.creative.optimization.thresholds import OPTIMIZATION_RULES_VERSION
from src.modules.creative.performance.engine import to_jsonable
from src.modules.economics.service import summary_data as economics_summary
from src.modules.metrics.aggregation import Range

NO_SNAPSHOT_STATUS = "no_snapshot"


async def _concept_strategy_context(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    business_id: uuid.UUID,
) -> dict[str, dict[str, Any]]:
    """Per-concept strategy context availability (Phase 7 chain refs)."""
    concepts = (
        await session.execute(
            select(CreativeConcept).where(
                CreativeConcept.organization_id == organization_id,
                CreativeConcept.business_id == business_id,
            )
        )
    ).scalars().all()
    assignments = (
        await session.execute(
            select(
                CreativeConceptPortfolio.creative_concept_id,
                CreativeConceptPortfolio.portfolio_id,
                CreativeConceptPortfolio.role,
            ).where(
                CreativeConceptPortfolio.organization_id == organization_id,
                CreativeConceptPortfolio.business_id == business_id,
            )
        )
    ).all()
    roles_by_concept: dict[str, list[dict[str, Any]]] = {}
    for concept_id, portfolio_id, role in assignments:
        roles_by_concept.setdefault(str(concept_id), []).append(
            {"portfolio_id": str(portfolio_id), "role": role}
        )

    context: dict[str, dict[str, Any]] = {}
    for concept in concepts:
        context[str(concept.id)] = {
            "positioning_reference": (
                str(concept.positioning_reference) if concept.positioning_reference else None
            ),
            "offer_reference": str(concept.offer_reference) if concept.offer_reference else None,
            "messaging_reference": (
                str(concept.messaging_reference) if concept.messaging_reference else None
            ),
            "funnel_reference": str(concept.funnel_reference) if concept.funnel_reference else None,
            "funnel_stage": concept.funnel_stage,
            "reason_to_believe": concept.reason_to_believe,
            "objection": concept.objection,
            "provenance_chain": None,  # filled by caller from 8C descriptors
        }
    return context


def _merge_provenance(
    strategy_context: dict[str, dict[str, Any]],
    provenance_index: list[dict[str, Any]],
    portfolio_roles: dict[str, list[dict[str, Any]]] | None,
) -> dict[str, dict[str, Any]]:
    """Attach 8C provenance chains into the strategy-context map."""
    chain_by_entity = {
        row["entity_id"]: row.get("chain") for row in provenance_index or []
    }
    merged: dict[str, dict[str, Any]] = {}
    for entity_id, ctx in strategy_context.items():
        merged[entity_id] = {**ctx, "provenance_chain": chain_by_entity.get(entity_id)}
        if portfolio_roles and entity_id in portfolio_roles:
            merged[entity_id]["portfolios"] = portfolio_roles[entity_id]
    return merged


async def _latest_learning_artifacts(
    session: AsyncSession,
    business: Business,
    *,
    range: Range,
) -> tuple[dict[str, Any], str | None]:
    """Learning artifacts: prefer the latest persisted 8D snapshot."""
    from src.modules.creative.learning.service import latest_snapshot

    snapshot = await latest_snapshot(
        session, organization_id=business.organization_id, business_id=business.id
    )
    if snapshot is not None:
        payload = snapshot.payload or {}
        return payload, snapshot.fingerprint
    report = await build_learning_report(session, business, range=range)
    if report.get("summary", {}).get("entities_total") == 0:
        return empty_report(business, range), None
    return report, report.get("fingerprint")


# ---------------------------------------------------------------------------
# Plan generation + persistence
# ---------------------------------------------------------------------------


async def generate(
    session: AsyncSession,
    business: Business,
    *,
    range: Range,
    created_by: uuid.UUID | None,
) -> dict[str, Any]:
    """Recompute the deterministic optimization plan (idempotent persist)."""
    learning_payload, learning_fingerprint = await _latest_learning_artifacts(
        session, business, range=range
    )
    economics = await economics_summary(session, business)

    entities_total = int((learning_payload.get("summary") or {}).get("entities_total") or 0)
    if entities_total == 0:
        plan = optimization_engine.empty_plan()
        plan["fingerprint"] = optimization_engine.fingerprint_payload(plan)
        return {"plan": plan, "snapshot_id": None, "created": False}

    profiles = list(learning_payload.get("profiles") or [])
    patterns = list(learning_payload.get("patterns") or [])
    portfolio_intelligence = dict(learning_payload.get("portfolio_intelligence") or {})
    coverage_gaps = list(learning_payload.get("coverage_gaps") or [])
    learning_summary = dict(learning_payload.get("summary") or {})

    strategy_context = await _concept_strategy_context(
        session,
        organization_id=business.organization_id,
        business_id=business.id,
    )
    portfolio_roles = {
        entity_id: ctx.pop("portfolios")
        for entity_id, ctx in strategy_context.items()
        if "portfolios" in ctx
    } or None
    strategy_context = _merge_provenance(
        strategy_context,
        learning_payload.get("provenance_index") or [],
        portfolio_roles,
    )

    # Portfolio intelligence recomputed with role balance when assignments exist.
    if portfolio_roles:
        portfolio_intelligence["role_balance"] = _role_balance(portfolio_roles)

    proof_present = any((ctx or {}).get("reason_to_believe") for ctx in strategy_context.values())
    objection_present = any((ctx or {}).get("objection") for ctx in strategy_context.values())

    plan = optimization_engine.build_plan(
        profiles=profiles,
        patterns=patterns,
        portfolio_intelligence=portfolio_intelligence,
        coverage_gaps=coverage_gaps,
        strategy_context_by_entity=strategy_context,
        learning_summary={
            **learning_summary,
            "break_even_roas_available": economics.get("break_even_roas") is not None,
            "source": "phase_8d_snapshot" if learning_fingerprint else "phase_8d_computed",
        },
        learning_fingerprint=learning_fingerprint,
        proof_coverage_present=proof_present,
        objection_coverage_present=objection_present,
    )
    snapshot, created = await persist_snapshot(
        session, business, plan=plan, range=range, created_by=created_by
    )
    return {"plan": plan, "snapshot_id": snapshot.id, "created": created}


def _role_balance(
    portfolio_roles: dict[str, list[dict[str, Any]]],
) -> dict[str, int]:
    balance = {"core": 0, "exploration": 0}
    for assignments in portfolio_roles.values():
        for assignment in assignments:
            role = str(assignment.get("role") or "").lower()
            if role in balance:
                balance[role] += 1
    return balance


async def persist_snapshot(
    session: AsyncSession,
    business: Business,
    *,
    plan: dict[str, Any],
    range: Range,
    created_by: uuid.UUID | None,
) -> tuple[CreativeOptimizationSnapshot, bool]:
    """Store a plan snapshot keyed by fingerprint. Idempotent on recompute."""
    existing = (
        await session.execute(
            select(CreativeOptimizationSnapshot).where(
                CreativeOptimizationSnapshot.business_id == business.id,
                CreativeOptimizationSnapshot.fingerprint == plan["fingerprint"],
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    snapshot = CreativeOptimizationSnapshot(
        organization_id=business.organization_id,
        business_id=business.id,
        range_kind=range.kind,
        start_date=range.start,
        end_date=range.end,
        currency=business.currency,
        rules_version=OPTIMIZATION_RULES_VERSION,
        fingerprint=plan["fingerprint"],
        payload=to_jsonable(plan),
        created_by=created_by,
    )
    session.add(snapshot)
    try:
        await session.flush()
    except sa.exc.IntegrityError as exc:
        raise ConflictError("optimization snapshot fingerprint already exists") from exc
    await session.commit()
    return snapshot, True


# ---------------------------------------------------------------------------
# Read projections from the latest persisted snapshot
# ---------------------------------------------------------------------------


async def latest_snapshot(
    session: AsyncSession, *, organization_id: uuid.UUID, business_id: uuid.UUID
) -> CreativeOptimizationSnapshot | None:
    return (
        await session.execute(
            select(CreativeOptimizationSnapshot)
            .where(
                CreativeOptimizationSnapshot.organization_id == organization_id,
                CreativeOptimizationSnapshot.business_id == business_id,
            )
            .order_by(CreativeOptimizationSnapshot.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def get_snapshot(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    business_id: uuid.UUID,
    snapshot_id: uuid.UUID,
) -> CreativeOptimizationSnapshot | None:
    return (
        await session.execute(
            select(CreativeOptimizationSnapshot).where(
                CreativeOptimizationSnapshot.id == snapshot_id,
                CreativeOptimizationSnapshot.organization_id == organization_id,
                CreativeOptimizationSnapshot.business_id == business_id,
            )
        )
    ).scalar_one_or_none()


async def list_snapshots(
    session: AsyncSession, *, organization_id: uuid.UUID, business_id: uuid.UUID
) -> list[CreativeOptimizationSnapshot]:
    rows = (
        (
            await session.execute(
                select(CreativeOptimizationSnapshot)
                .where(
                    CreativeOptimizationSnapshot.organization_id == organization_id,
                    CreativeOptimizationSnapshot.business_id == business_id,
                )
                .order_by(CreativeOptimizationSnapshot.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


def projection_from_snapshot(
    snapshot: CreativeOptimizationSnapshot | None, section: str
) -> dict[str, Any]:
    """Extract one read projection; explicit state when nothing persisted."""
    if snapshot is None:
        return {
            "status": NO_SNAPSHOT_STATUS,
            "reason": "generate an optimization plan first",
        }
    payload = snapshot.payload or {}
    key_map = {
        "opportunities": "opportunities",
        "tests": "recommended_tests",
        "refresh": "refresh_investigations",
        "coverage": "coverage_analysis",
        "portfolio": "concentration_analysis",
        "conflicts": "conflicting_evidence_summary",
        "blocked": "blocked_opportunities",
    }
    key = key_map.get(section, section)
    value = payload.get(key)
    if value is None:
        return {"status": NO_SNAPSHOT_STATUS, "reason": f"section missing: {section}"}
    if isinstance(value, list):
        return {"status": "available", "items": value}
    item = dict(value)
    item["status"] = "available"
    return item


__all__ = [
    "NO_SNAPSHOT_STATUS",
    "generate",
    "persist_snapshot",
    "latest_snapshot",
    "get_snapshot",
    "list_snapshots",
    "projection_from_snapshot",
]
