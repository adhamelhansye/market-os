"""Creative decision plan API endpoints (Phase 8F).

Decision plans are assembled from the latest Phase 8E snapshot and are
review-only. The review endpoint writes human-review state ONLY - it
never executes, modifies campaigns/ads/budgets or calls providers.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from src.core.dependencies import CurrentBusinessId, DbSession, require_permission
from src.core.exceptions import NotFoundError
from src.core.tenancy import TenantContext
from src.modules.businesses.service import get_business
from src.modules.creative.decision import service
from src.modules.creative.decision.schemas import (
    BlockedAppendixResponse,
    DecisionItemsResponse,
    DecisionPlanGenerateResponse,
    DecisionPlanSummaryResponse,
    DecisionSnapshotRead,
    DecisionSnapshotSummaryRead,
    ReviewStateRead,
    ReviewStateUpdate,
)

router = APIRouter(tags=["creative-decision-plan"])


@router.post(
    "/businesses/{business_id}/strategy/creative/decision-plan/generate",
    response_model=DecisionPlanGenerateResponse,
    status_code=200,
)
async def generate_decision_plan(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> DecisionPlanGenerateResponse:
    """Assemble the deterministic decision plan (idempotent persist)."""
    business = await get_business(session, business_id)
    result = await service.generate(session, business, created_by=tenant.user_id)
    return DecisionPlanGenerateResponse(
        business_id=str(business.id),
        snapshot_id=result["snapshot_id"],
        created=result["created"],
        plan=result["plan"],
    )


def _plan_or_404(plan_row):
    if plan_row is None:
        raise NotFoundError("No decision plan has been generated")
    return plan_row


@router.get(
    "/businesses/{business_id}/strategy/creative/decision-plan/summary",
    response_model=DecisionPlanSummaryResponse,
)
async def decision_plan_summary(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> DecisionPlanSummaryResponse:
    plan_row = await service.latest_plan(
        session, organization_id=tenant.organization_id, business_id=business_id
    )
    reviews = await service.reviews_by_opportunity(session, business_id=business_id)
    data = service.summary_projection(_plan_or_404(plan_row), reviews)
    return DecisionPlanSummaryResponse(**data)


@router.get(
    "/businesses/{business_id}/strategy/creative/decision-plan/items",
    response_model=DecisionItemsResponse,
)
async def decision_plan_items(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> DecisionItemsResponse:
    plan_row = await service.latest_plan(
        session, organization_id=tenant.organization_id, business_id=business_id
    )
    reviews = await service.reviews_by_opportunity(session, business_id=business_id)
    return DecisionItemsResponse(
        **service.items_projection(_plan_or_404(plan_row), reviews)
    )


@router.get(
    "/businesses/{business_id}/strategy/creative/decision-plan/blocked",
    response_model=BlockedAppendixResponse,
)
async def decision_plan_blocked(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> BlockedAppendixResponse:
    plan_row = await service.latest_plan(
        session, organization_id=tenant.organization_id, business_id=business_id
    )
    _plan_or_404(plan_row)
    return BlockedAppendixResponse(**service.blocked_projection(plan_row))


@router.post(
    "/businesses/{business_id}/strategy/creative/decision-plan/items/{opportunity_id}/review",
    response_model=ReviewStateRead,
    status_code=200,
)
async def review_decision_item(
    business_id: CurrentBusinessId,
    opportunity_id: str,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
    payload: ReviewStateUpdate,
) -> ReviewStateRead:
    """Record human review state for one opportunity.

    Writes review state ONLY. Nothing is executed, modified or triggered.
    """
    await get_business(session, business_id)
    review = await service.upsert_review(
        session,
        organization_id=tenant.organization_id,
        business_id=business_id,
        opportunity_id=opportunity_id,
        review_state=payload.review_state,
        note=payload.note,
        decided_by=tenant.user_id,
    )
    return ReviewStateRead.model_validate(review)


@router.get(
    "/businesses/{business_id}/strategy/creative/decision-plan/snapshots",
    response_model=list[DecisionSnapshotSummaryRead],
)
async def list_snapshots(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> list[DecisionSnapshotSummaryRead]:
    rows = await service.list_plans(
        session, organization_id=tenant.organization_id, business_id=business_id
    )
    return [DecisionSnapshotSummaryRead.model_validate(row) for row in rows]


@router.get(
    "/businesses/{business_id}/strategy/creative/decision-plan/snapshots/{snapshot_id}",
    response_model=DecisionSnapshotRead,
)
async def get_snapshot(
    business_id: CurrentBusinessId,
    snapshot_id: uuid.UUID,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> DecisionSnapshotRead:
    snapshot = await service.get_plan(
        session,
        organization_id=tenant.organization_id,
        business_id=business_id,
        snapshot_id=snapshot_id,
    )
    if snapshot is None:
        raise NotFoundError("Decision plan snapshot not found")
    return DecisionSnapshotRead.model_validate(snapshot)
