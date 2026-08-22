"""Creative decision plan orchestration service (Phase 8F).

Assembles decision plans from the LATEST persisted Phase 8E snapshot
(never recomputing opportunities) and manages the repository's only
mutable human-review state.

- generate: assemble + persist idempotently by fingerprint
- review: upsert bounded human-review state per opportunity
- reads: projections merge live review state onto immutable items

No LLM, no provider calls, no execution paths of any kind.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy.exc as sa_exc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError, NotFoundError
from src.db.models import Business
from src.db.models.creative_decision import (
    CreativeDecisionItemReview,
    CreativeDecisionPlan,
)
from src.modules.creative.decision import engine as decision_engine
from src.modules.creative.decision.engine import ALLOWED_REVIEW_STATES
from src.modules.creative.optimization.service import (
    latest_snapshot as optimization_latest_snapshot,
)
from src.modules.creative.performance.engine import to_jsonable

NO_SNAPSHOT_STATUS = "no_snapshot"


async def reviews_by_opportunity(
    session: AsyncSession, *, business_id: uuid.UUID
) -> dict[str, dict[str, Any]]:
    rows = (
        await session.execute(
            select(CreativeDecisionItemReview).where(
                CreativeDecisionItemReview.business_id == business_id
            )
        )
    ).scalars().all()
    return {
        row.opportunity_id: {
            "review_state": row.review_state,
            "note": row.note,
            "source_plan_fingerprint": row.source_plan_fingerprint,
            "updated_at": row.updated_at,
        }
        for row in rows
    }


# ---------------------------------------------------------------------------
# Generate (assemble + persist, idempotent)
# ---------------------------------------------------------------------------


async def generate(
    session: AsyncSession,
    business: Business,
    *,
    created_by: uuid.UUID | None,
) -> dict[str, Any]:
    """Assemble the plan from the latest 8E snapshot; persist idempotently."""
    optimization_snapshot = await optimization_latest_snapshot(
        session, organization_id=business.organization_id, business_id=business.id
    )
    if optimization_snapshot is None:
        # Explicit unavailable state; nothing persisted.
        plan = decision_engine.empty_plan()
        return {"plan": plan, "snapshot_id": None, "created": False}

    plan = decision_engine.build_plan(
        optimization_payload=optimization_snapshot.payload or {},
        source_optimization_fingerprint=optimization_snapshot.fingerprint,
    )

    existing = (
        await session.execute(
            select(CreativeDecisionPlan).where(
                CreativeDecisionPlan.business_id == business.id,
                CreativeDecisionPlan.fingerprint == plan["fingerprint"],
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {"plan": plan, "snapshot_id": existing.id, "created": False}

    snapshot = CreativeDecisionPlan(
        organization_id=business.organization_id,
        business_id=business.id,
        rules_version=decision_engine.DECISION_PLAN_RULES_VERSION,
        fingerprint=plan["fingerprint"],
        source_optimization_fingerprint=optimization_snapshot.fingerprint,
        payload=to_jsonable(plan),
        created_by=created_by,
    )
    session.add(snapshot)
    try:
        await session.flush()
    except sa_exc.IntegrityError as exc:
        raise ConflictError("decision plan fingerprint already exists") from exc
    await session.commit()
    return {"plan": plan, "snapshot_id": snapshot.id, "created": True}


# ---------------------------------------------------------------------------
# Human review state (the only mutable state in Phase 8F)
# ---------------------------------------------------------------------------


async def upsert_review(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    business_id: uuid.UUID,
    opportunity_id: str,
    review_state: str,
    note: str | None,
    decided_by: uuid.UUID | None,
) -> CreativeDecisionItemReview:
    """Record human review state for one opportunity.

    The opportunity must exist in the latest persisted plan. This writes
    ONLY review state - nothing is executed, modified or triggered.
    """
    if review_state not in ALLOWED_REVIEW_STATES:
        raise ConflictError(
            f"review_state must be one of {', '.join(ALLOWED_REVIEW_STATES)}"
        )

    plan = await latest_plan_payload(
        session, organization_id=organization_id, business_id=business_id
    )
    if plan is None:
        raise NotFoundError("No decision plan has been generated")
    item_ids = {item["opportunity_id"] for item in plan.get("items") or []}
    if opportunity_id not in item_ids:
        raise NotFoundError("Opportunity not found in the current decision plan")

    source_fingerprint = plan["fingerprint"]
    existing = (
        await session.execute(
            select(CreativeDecisionItemReview).where(
                CreativeDecisionItemReview.business_id == business_id,
                CreativeDecisionItemReview.opportunity_id == opportunity_id,
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        # Latest review wins; historical metadata is never silently
        # rewritten - updated_at moves and the source fingerprint records
        # which plan this review was last made under.
        existing.review_state = review_state
        existing.note = note
        existing.decided_by = decided_by
        existing.source_plan_fingerprint = source_fingerprint
        await session.commit()
        return existing

    review = CreativeDecisionItemReview(
        organization_id=organization_id,
        business_id=business_id,
        opportunity_id=opportunity_id,
        source_plan_fingerprint=source_fingerprint,
        review_state=review_state,
        note=note,
        decided_by=decided_by,
    )
    session.add(review)
    try:
        await session.flush()
    except sa_exc.IntegrityError as exc:
        raise ConflictError("review already exists for this opportunity") from exc
    await session.commit()
    return review


# ---------------------------------------------------------------------------
# Reads - projections merge live review state onto immutable items
# ---------------------------------------------------------------------------


async def latest_plan(
    session: AsyncSession, *, organization_id: uuid.UUID, business_id: uuid.UUID
) -> CreativeDecisionPlan | None:
    return (
        await session.execute(
            select(CreativeDecisionPlan)
            .where(
                CreativeDecisionPlan.organization_id == organization_id,
                CreativeDecisionPlan.business_id == business_id,
            )
            .order_by(CreativeDecisionPlan.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def get_plan(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    business_id: uuid.UUID,
    snapshot_id: uuid.UUID,
) -> CreativeDecisionPlan | None:
    return (
        await session.execute(
            select(CreativeDecisionPlan).where(
                CreativeDecisionPlan.id == snapshot_id,
                CreativeDecisionPlan.organization_id == organization_id,
                CreativeDecisionPlan.business_id == business_id,
            )
        )
    ).scalar_one_or_none()


async def list_plans(
    session: AsyncSession, *, organization_id: uuid.UUID, business_id: uuid.UUID
) -> list[CreativeDecisionPlan]:
    rows = (
        (
            await session.execute(
                select(CreativeDecisionPlan)
                .where(
                    CreativeDecisionPlan.organization_id == organization_id,
                    CreativeDecisionPlan.business_id == business_id,
                )
                .order_by(CreativeDecisionPlan.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def latest_plan_payload(
    session: AsyncSession, *, organization_id: uuid.UUID, business_id: uuid.UUID
) -> dict[str, Any] | None:
    plan_row = await latest_plan(
        session, organization_id=organization_id, business_id=business_id
    )
    if plan_row is None:
        return None
    return plan_row.payload or {}


def summary_projection(
    plan_row: CreativeDecisionPlan | None,
    reviews_by_opportunity: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Summary with review progress merged from mutable review state."""
    if plan_row is None:
        return {"status": NO_SNAPSHOT_STATUS}
    payload = plan_row.payload or {}
    summary = dict(payload.get("summary") or {})
    items = list(payload.get("items") or [])
    progress = decision_engine.review_progress(items, reviews_by_opportunity)
    summary.update(
        {
            "status": "available",
            "plan_status": payload.get("plan_status"),
            "fingerprint": plan_row.fingerprint,
            "rules_version": plan_row.rules_version,
            "source_optimization_fingerprint": (
                plan_row.source_optimization_fingerprint
            ),
            "review_progress": progress,
        }
    )
    return summary


def items_projection(
    plan_row: CreativeDecisionPlan | None,
    reviews_by_opportunity: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Actionable items with live review state merged."""
    if plan_row is None:
        return {"status": NO_SNAPSHOT_STATUS}
    payload = plan_row.payload or {}
    items = [
        decision_engine.merge_review_state(item, reviews_by_opportunity)
        for item in payload.get("items") or []
    ]
    return {"status": "available", "items": items}


def blocked_projection(plan_row: CreativeDecisionPlan | None) -> dict[str, Any]:
    """Blocked appendix - informational only, never actionable."""
    if plan_row is None:
        return {"status": NO_SNAPSHOT_STATUS}
    payload = plan_row.payload or {}
    return {
        "status": "available",
        "actionable": False,
        "items": list(payload.get("blocked_appendix") or []),
    }


__all__ = [
    "NO_SNAPSHOT_STATUS",
    "reviews_by_opportunity",
    "generate",
    "upsert_review",
    "latest_plan",
    "get_plan",
    "list_plans",
    "summary_projection",
    "items_projection",
    "blocked_projection",
]
