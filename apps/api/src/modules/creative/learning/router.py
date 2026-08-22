"""Creative learning API endpoints (Phase 8D).

Read projections are served from the latest persisted snapshot; POST
generate recomputes and persists idempotently. Reads require
``business:read``; generation requires ``business:write``.

Recommendations are informational only: no action payloads exist.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.core.dependencies import CurrentBusinessId, DbSession, require_permission
from src.core.exceptions import NotFoundError
from src.core.tenancy import TenantContext
from src.modules.businesses.service import get_business
from src.modules.creative.learning import service
from src.modules.creative.learning.schemas import (
    LearningGenerateResponse,
    LearningProjectionResponse,
    LearningSnapshotRead,
    LearningSnapshotSummaryRead,
    LearningSummaryResponse,
)
from src.modules.metrics.service import resolve_range

router = APIRouter(tags=["creative-learning"])


class RangeParams(BaseModel):
    range_kind: str = "last_30_days"
    start: date | None = None
    end: date | None = None


def _range_params(
    range_kind: Annotated[str, Query()] = "last_30_days",
    start: Annotated[date | None, Query(description="Custom range start")] = None,
    end: Annotated[date | None, Query(description="Custom range end")] = None,
) -> RangeParams:
    return RangeParams(range_kind=range_kind, start=start, end=end)


async def _resolve(
    session: DbSession, business_id: uuid.UUID, params: RangeParams
):
    business = await get_business(session, business_id)
    resolved = resolve_range(
        business.timezone, params.range_kind, start=params.start, end=params.end
    )
    return business, resolved


@router.post(
    "/businesses/{business_id}/strategy/creative/learning/generate",
    response_model=LearningGenerateResponse,
    status_code=200,
)
async def generate_learning(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
    params: Annotated[RangeParams, Depends(_range_params)],
) -> LearningGenerateResponse:
    """Recompute the deterministic learning report (idempotent persist)."""
    business, resolved = await _resolve(session, business_id, params)
    result = await service.generate(
        session,
        business,
        range=resolved,
        created_by=tenant.user_id,
    )
    return LearningGenerateResponse(
        business_id=str(business.id),
        snapshot_id=result["snapshot_id"],
        created=result["created"],
        report=result["report"],
    )


@router.get(
    "/businesses/{business_id}/strategy/creative/learning/summary",
    response_model=LearningSummaryResponse,
)
async def learning_summary(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    params: Annotated[RangeParams, Depends(_range_params)],
) -> LearningSummaryResponse:
    business, _resolved = await _resolve(session, business_id, params)
    snapshot = await service.latest_snapshot(
        session, organization_id=tenant.organization_id, business_id=business.id
    )
    data = service.projection_from_snapshot(snapshot, "summary")
    return LearningSummaryResponse(**data)


@router.get(
    "/businesses/{business_id}/strategy/creative/learning/patterns",
    response_model=LearningProjectionResponse,
)
async def learning_patterns(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> LearningProjectionResponse:
    snapshot = await service.latest_snapshot(
        session, organization_id=tenant.organization_id, business_id=business_id
    )
    return LearningProjectionResponse(
        **service.projection_from_snapshot(snapshot, "patterns")
    )


@router.get(
    "/businesses/{business_id}/strategy/creative/learning/learnings",
    response_model=LearningProjectionResponse,
)
async def learning_learnings(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> LearningProjectionResponse:
    snapshot = await service.latest_snapshot(
        session, organization_id=tenant.organization_id, business_id=business_id
    )
    return LearningProjectionResponse(
        **service.projection_from_snapshot(snapshot, "learnings")
    )


@router.get(
    "/businesses/{business_id}/strategy/creative/learning/recommendations",
    response_model=LearningProjectionResponse,
)
async def learning_recommendations(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> LearningProjectionResponse:
    snapshot = await service.latest_snapshot(
        session, organization_id=tenant.organization_id, business_id=business_id
    )
    return LearningProjectionResponse(
        **service.projection_from_snapshot(snapshot, "recommendations")
    )


@router.get(
    "/businesses/{business_id}/strategy/creative/learning/profiles",
    response_model=LearningProjectionResponse,
)
async def learning_profiles(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> LearningProjectionResponse:
    snapshot = await service.latest_snapshot(
        session, organization_id=tenant.organization_id, business_id=business_id
    )
    return LearningProjectionResponse(
        **service.projection_from_snapshot(snapshot, "profiles")
    )


@router.get(
    "/businesses/{business_id}/strategy/creative/learning/snapshots",
    response_model=list[LearningSnapshotSummaryRead],
)
async def list_snapshots(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> list[LearningSnapshotSummaryRead]:
    rows = await service.list_snapshots(
        session, organization_id=tenant.organization_id, business_id=business_id
    )
    return [LearningSnapshotSummaryRead.model_validate(row) for row in rows]


@router.get(
    "/businesses/{business_id}/strategy/creative/learning/snapshots/{snapshot_id}",
    response_model=LearningSnapshotRead,
)
async def get_snapshot(
    business_id: CurrentBusinessId,
    snapshot_id: uuid.UUID,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> LearningSnapshotRead:
    snapshot = await service.get_snapshot(
        session,
        organization_id=tenant.organization_id,
        business_id=business_id,
        snapshot_id=snapshot_id,
    )
    if snapshot is None:
        raise NotFoundError("Learning snapshot not found")
    return LearningSnapshotRead.model_validate(snapshot)
