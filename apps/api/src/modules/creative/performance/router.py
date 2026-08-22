"""Creative performance API endpoints (Phase 8C).

Read-only intelligence plus explicit link/snapshot management. All
endpoints are tenant/business scoped with RBAC:

- reads require ``business:read``
- writes (links, snapshots) require ``business:write``

No endpoint mutates campaigns, budgets or provider objects.
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
from src.modules.creative.performance import service
from src.modules.creative.performance.schemas import (
    EntityPerformanceResponse,
    PerformanceLinkCreate,
    PerformanceLinkRead,
    PerformanceReportResponse,
    SnapshotCreatedResponse,
    SnapshotRead,
    SnapshotSummaryRead,
)
from src.modules.metrics.service import resolve_range

router = APIRouter(tags=["creative-performance"])


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


@router.get(
    "/businesses/{business_id}/strategy/creative/performance/report",
    response_model=PerformanceReportResponse,
)
async def get_report(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    params: Annotated[RangeParams, Depends(_range_params)],
) -> PerformanceReportResponse:
    """Deterministic performance report over every linked creative entity."""
    business, resolved = await _resolve(session, business_id, params)
    report = await service.build_report(session, business, range=resolved)
    return PerformanceReportResponse.model_validate(report)


@router.get(
    "/businesses/{business_id}/strategy/creative/performance/entities/{entity_type}/{entity_id}",
    response_model=EntityPerformanceResponse,
)
async def get_entity_performance(
    business_id: CurrentBusinessId,
    entity_type: str,
    entity_id: uuid.UUID,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    params: Annotated[RangeParams, Depends(_range_params)],
) -> EntityPerformanceResponse:
    """Observed performance for one concept/variant; unavailable when unlinked."""
    business, resolved = await _resolve(session, business_id, params)
    payload = await service.build_entity_report(
        session, business, range=resolved, entity_type=entity_type, entity_id=entity_id
    )
    return EntityPerformanceResponse.model_validate(payload)


@router.post(
    "/businesses/{business_id}/strategy/creative/performance/links",
    response_model=PerformanceLinkRead,
    status_code=201,
)
async def create_link(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
    payload: PerformanceLinkCreate,
) -> PerformanceLinkRead:
    """Declare an explicit attribution mapping (never inferred)."""
    await get_business(session, business_id)
    link = await service.create_link(
        session,
        organization_id=tenant.organization_id,
        business_id=business_id,
        created_by=tenant.user_id,
        **payload.model_dump(),
    )
    return PerformanceLinkRead.model_validate(link)


@router.get(
    "/businesses/{business_id}/strategy/creative/performance/links",
    response_model=list[PerformanceLinkRead],
)
async def list_links(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> list[PerformanceLinkRead]:
    rows = await service.list_links(
        session, organization_id=tenant.organization_id, business_id=business_id
    )
    return [PerformanceLinkRead.model_validate(row) for row in rows]


@router.delete(
    "/businesses/{business_id}/strategy/creative/performance/links/{link_id}",
    status_code=204,
)
async def delete_link(
    business_id: CurrentBusinessId,
    link_id: uuid.UUID,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> None:
    await get_business(session, business_id)
    await service.delete_link(
        session, organization_id=tenant.organization_id, business_id=business_id, link_id=link_id
    )


@router.post(
    "/businesses/{business_id}/strategy/creative/performance/snapshots",
    response_model=SnapshotCreatedResponse,
    status_code=201,
)
async def create_snapshot(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
    params: Annotated[RangeParams, Depends(_range_params)],
) -> SnapshotCreatedResponse:
    """Persist the current deterministic report as an immutable snapshot.

    Idempotent on recompute: the same inputs return the existing snapshot
    with ``created=false``.
    """
    business, resolved = await _resolve(session, business_id, params)
    report = await service.build_report(session, business, range=resolved)
    snapshot, created = await service.persist_snapshot(
        session, business, report=report, created_by=tenant.user_id
    )
    return SnapshotCreatedResponse(
        snapshot_id=snapshot.id, fingerprint=snapshot.fingerprint, created=created
    )


@router.get(
    "/businesses/{business_id}/strategy/creative/performance/snapshots",
    response_model=list[SnapshotSummaryRead],
)
async def list_snapshots(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> list[SnapshotSummaryRead]:
    rows = await service.list_snapshots(
        session, organization_id=tenant.organization_id, business_id=business_id
    )
    return [SnapshotSummaryRead.model_validate(row) for row in rows]


@router.get(
    "/businesses/{business_id}/strategy/creative/performance/snapshots/{snapshot_id}",
    response_model=SnapshotRead,
)
async def get_snapshot(
    business_id: CurrentBusinessId,
    snapshot_id: uuid.UUID,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> SnapshotRead:
    snapshot = await service.get_snapshot(
        session,
        organization_id=tenant.organization_id,
        business_id=business_id,
        snapshot_id=snapshot_id,
    )
    if snapshot is None:
        raise NotFoundError("Snapshot not found")
    return SnapshotRead.model_validate(snapshot)
