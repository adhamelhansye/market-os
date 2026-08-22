"""Creative optimization API endpoints (Phase 8E).

Review-only optimization plans. POST generate recomputes and persists
idempotently (business:write); all reads serve the latest persisted
snapshot (business:read). No execution endpoints exist.
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
from src.modules.creative.optimization import service
from src.modules.creative.optimization.schemas import (
    OptimizationGenerateResponse,
    OptimizationProjectionResponse,
    OptimizationSnapshotRead,
    OptimizationSnapshotSummaryRead,
    OptimizationSummaryResponse,
)
from src.modules.metrics.service import resolve_range

router = APIRouter(tags=["creative-optimization"])


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
    "/businesses/{business_id}/strategy/creative/optimization/generate",
    response_model=OptimizationGenerateResponse,
    status_code=200,
)
async def generate_optimization(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
    params: Annotated[RangeParams, Depends(_range_params)],
) -> OptimizationGenerateResponse:
    """Recompute the deterministic optimization plan (idempotent persist)."""
    business, resolved = await _resolve(session, business_id, params)
    result = await service.generate(
        session, business, range=resolved, created_by=tenant.user_id
    )
    return OptimizationGenerateResponse(
        business_id=str(business.id),
        snapshot_id=result["snapshot_id"],
        created=result["created"],
        plan=result["plan"],
    )


@router.get(
    "/businesses/{business_id}/strategy/creative/optimization/summary",
    response_model=OptimizationSummaryResponse,
)
async def optimization_summary(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> OptimizationSummaryResponse:
    snapshot = await service.latest_snapshot(
        session, organization_id=tenant.organization_id, business_id=business_id
    )
    if snapshot is None:
        return OptimizationSummaryResponse(status="no_snapshot")
    payload = snapshot.payload or {}
    summary = dict(payload.get("summary") or {})
    return OptimizationSummaryResponse(
        status="available",
        optimization_status=payload.get("optimization_status"),
        entities_total=summary.get("entities_total"),
        entities_sufficient=summary.get("entities_sufficient"),
        opportunities_total=summary.get("opportunities_total"),
        blocked_total=summary.get("blocked_total"),
        by_priority=summary.get("by_priority"),
        note=summary.get("note"),
        fingerprint=snapshot.fingerprint,
        rules_version=snapshot.rules_version,
    )


async def _projection(
    tenant: TenantContext, session: DbSession, business_id: uuid.UUID, section: str
) -> OptimizationProjectionResponse:
    snapshot = await service.latest_snapshot(
        session, organization_id=tenant.organization_id, business_id=business_id
    )
    return OptimizationProjectionResponse(
        **service.projection_from_snapshot(snapshot, section)
    )


@router.get(
    "/businesses/{business_id}/strategy/creative/optimization/opportunities",
    response_model=OptimizationProjectionResponse,
)
async def optimization_opportunities(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> OptimizationProjectionResponse:
    return await _projection(tenant, session, business_id, "opportunities")


@router.get(
    "/businesses/{business_id}/strategy/creative/optimization/blocked",
    response_model=OptimizationProjectionResponse,
)
async def optimization_blocked(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> OptimizationProjectionResponse:
    return await _projection(tenant, session, business_id, "blocked")


@router.get(
    "/businesses/{business_id}/strategy/creative/optimization/tests",
    response_model=OptimizationProjectionResponse,
)
async def optimization_tests(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> OptimizationProjectionResponse:
    return await _projection(tenant, session, business_id, "tests")


@router.get(
    "/businesses/{business_id}/strategy/creative/optimization/refresh",
    response_model=OptimizationProjectionResponse,
)
async def optimization_refresh(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> OptimizationProjectionResponse:
    return await _projection(tenant, session, business_id, "refresh")


@router.get(
    "/businesses/{business_id}/strategy/creative/optimization/conflicts",
    response_model=OptimizationProjectionResponse,
)
async def optimization_conflicts(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> OptimizationProjectionResponse:
    return await _projection(tenant, session, business_id, "conflicts")


@router.get(
    "/businesses/{business_id}/strategy/creative/optimization/coverage",
)
async def optimization_coverage(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> dict:
    snapshot = await service.latest_snapshot(
        session, organization_id=tenant.organization_id, business_id=business_id
    )
    if snapshot is None:
        return {"status": "no_snapshot", "reason": "generate an optimization plan first"}
    payload = snapshot.payload or {}
    item = dict(payload.get("coverage_analysis") or {})
    item["status"] = "available"
    return item


@router.get(
    "/businesses/{business_id}/strategy/creative/optimization/portfolio",
    response_model=OptimizationProjectionResponse,
)
async def optimization_portfolio(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> OptimizationProjectionResponse:
    snapshot = await service.latest_snapshot(
        session, organization_id=tenant.organization_id, business_id=business_id
    )
    if snapshot is None:
        return OptimizationProjectionResponse(status="no_snapshot")
    payload = snapshot.payload or {}
    item = dict(payload.get("concentration_analysis") or {})
    item["status"] = "available"
    return OptimizationProjectionResponse(status="available", items=[item])


@router.get(
    "/businesses/{business_id}/strategy/creative/optimization/snapshots",
    response_model=list[OptimizationSnapshotSummaryRead],
)
async def list_snapshots(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> list[OptimizationSnapshotSummaryRead]:
    rows = await service.list_snapshots(
        session, organization_id=tenant.organization_id, business_id=business_id
    )
    return [OptimizationSnapshotSummaryRead.model_validate(row) for row in rows]


@router.get(
    "/businesses/{business_id}/strategy/creative/optimization/snapshots/{snapshot_id}",
    response_model=OptimizationSnapshotRead,
)
async def get_snapshot(
    business_id: CurrentBusinessId,
    snapshot_id: uuid.UUID,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> OptimizationSnapshotRead:
    snapshot = await service.get_snapshot(
        session,
        organization_id=tenant.organization_id,
        business_id=business_id,
        snapshot_id=snapshot_id,
    )
    if snapshot is None:
        raise NotFoundError("Optimization snapshot not found")
    return OptimizationSnapshotRead.model_validate(snapshot)
