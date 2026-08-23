"""Creative action preparation API endpoints (Phase 8G).

Translates acknowledged Phase 8F opportunities into Phase 8B creative
test DRAFTS. Review-only: the review endpoint records second-stage human
review and never executes, promotes, launches or modifies anything.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from src.core.dependencies import CurrentBusinessId, DbSession, require_permission
from src.core.tenancy import TenantContext
from src.modules.businesses.service import get_business
from src.modules.creative.action import service
from src.modules.creative.action.schemas import (
    ActionDraftRead,
    ActionGenerateResponse,
    ActionItemsResponse,
    ReviewStateUpdate,
)

router = APIRouter(tags=["creative-action-preparation"])


@router.post(
    "/businesses/{business_id}/strategy/creative/action-preparation/generate",
    response_model=ActionGenerateResponse,
    status_code=200,
)
async def generate_action_drafts(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> ActionGenerateResponse:
    """Assemble 8B test drafts from acknowledged decision items (idempotent)."""
    business = await get_business(session, business_id)
    result = await service.generate(
        session, business, created_by=tenant.user_id
    )
    return ActionGenerateResponse(
        business_id=str(business.id),
        created_count=result["created_count"],
        report=result["report"],
    )


@router.get(
    "/businesses/{business_id}/strategy/creative/action-preparation/items",
    response_model=ActionItemsResponse,
)
async def action_items(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> ActionItemsResponse:
    """Drafts with second-stage review state plus skip/exclusion detail."""
    rows = await service.list_drafts(
        session, organization_id=tenant.organization_id, business_id=business_id
    )
    drafts: list[dict[str, Any]] = []
    for row in rows:
        entry = {
            "id": str(row.id),
            "source_opportunity_id": row.source_opportunity_id,
            "draft_test_id": row.draft_test_id,
            "draft_kind": row.draft_kind,
            "review_state": row.review_state,
            "note": row.note,
            "payload": row.payload,
        }
        drafts.append(entry)
    return ActionItemsResponse(status="available", drafts=drafts)


@router.post(
    (
        "/businesses/{business_id}/strategy/creative/action-preparation"
        "/drafts/{draft_id}/review"
    ),
    response_model=ActionDraftRead,
    status_code=200,
)
async def review_action_draft(
    business_id: CurrentBusinessId,
    draft_id: uuid.UUID,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
    payload: ReviewStateUpdate,
) -> ActionDraftRead:
    """Record second-stage human review of a draft.

    Writes review state ONLY. The underlying CreativeTest remains a draft;
    nothing is executed, launched or modified.
    """
    await get_business(session, business_id)
    draft_row = await service.review_draft(
        session,
        organization_id=tenant.organization_id,
        business_id=business_id,
        draft_id=draft_id,
        review_state=payload.review_state,
        note=payload.note,
        decided_by=tenant.user_id,
    )
    return ActionDraftRead.model_validate(draft_row)


__all__ = ["router"]
