"""Creative Intelligence API endpoints (Phases 8A/8B).

Follows project conventions:
- All endpoints under /api/v1/businesses/{business_id}/strategy/creative
- Tenant/business scoped via CurrentBusinessId (server-side membership check)
- RBAC: reads require business:read, writes require business:write
- Cross-tenant reads return 404; forbidden writes return 403
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.core.dependencies import CurrentBusinessId, DbSession, require_permission
from src.core.exceptions import NotFoundError
from src.core.tenancy import TenantContext
from src.db.models.creative import (
    CreativeConcept,
)
from src.modules.businesses.service import get_business
from src.modules.creative import service
from src.modules.creative.schemas import (
    CreativeConceptCreate,
    CreativeConceptPage,
    CreativeConceptRead,
    CreativePortfolioRead,
    CreativeStrategyRead,
    CreativeTestRead,
    CreativeTestVariantRead,
)

router = APIRouter(tags=["creative-intelligence"])


@router.post(
    "/businesses/{business_id}/strategy/creative/concepts",
    response_model=CreativeConceptRead,
    status_code=201,
)
async def create_concept(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
    payload: CreativeConceptCreate,
) -> CreativeConceptRead:
    """Create a creative concept anchored in Phase 7 strategy references."""
    await get_business(session, business_id)
    concept = await service.create_creative_concept(
        session,
        organization_id=tenant.organization_id,
        business_id=business_id,
        **payload.model_dump(),
    )
    return CreativeConceptRead.model_validate(concept)


@router.get(
    "/businesses/{business_id}/strategy/creative/concepts",
    response_model=CreativeConceptPage,
)
async def list_concepts(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: uuid.UUID | None = None,
    include_archived: bool = False,
) -> CreativeConceptPage:
    """List creative concepts (keyset pagination, newest first)."""
    cursor_row: CreativeConcept | None = None
    if cursor is not None:
        cursor_row = await service.get_concept(
            session,
            organization_id=tenant.organization_id,
            business_id=business_id,
            concept_id=cursor,
        )
        if cursor_row is None:
            raise NotFoundError("Cursor concept not found")
    items, next_cursor = await service.list_concepts(
        session,
        organization_id=tenant.organization_id,
        business_id=business_id,
        limit=limit,
        cursor=cursor_row.created_at if cursor_row else None,
        cursor_id=cursor_row.id if cursor_row else None,
        include_archived=include_archived,
    )
    return CreativeConceptPage(
        items=[CreativeConceptRead.model_validate(r) for r in items],
        next_cursor=next_cursor,
    )


@router.get(
    "/businesses/{business_id}/strategy/creative/concepts/{concept_id}",
    response_model=CreativeConceptRead,
)
async def get_concept(
    business_id: CurrentBusinessId,
    concept_id: uuid.UUID,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> CreativeConceptRead:
    concept = await service.get_concept(
        session,
        organization_id=tenant.organization_id,
        business_id=business_id,
        concept_id=concept_id,
    )
    if concept is None:
        raise NotFoundError("Creative concept not found")
    return CreativeConceptRead.model_validate(concept)


@router.get(
    "/businesses/{business_id}/strategy/creative/strategies",
    response_model=list[CreativeStrategyRead],
)
async def list_strategies(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> list[CreativeStrategyRead]:
    rows = await service.list_strategies(
        session, organization_id=tenant.organization_id, business_id=business_id
    )
    return [CreativeStrategyRead.model_validate(row) for row in rows]


@router.get(
    "/businesses/{business_id}/strategy/creative/tests",
    response_model=list[CreativeTestRead],
)
async def list_tests(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> list[CreativeTestRead]:
    rows = await service.list_tests(
        session, organization_id=tenant.organization_id, business_id=business_id
    )
    return [CreativeTestRead.model_validate(row) for row in rows]


@router.get(
    "/businesses/{business_id}/strategy/creative/tests/{test_id}/variants",
    response_model=list[CreativeTestVariantRead],
)
async def list_test_variants(
    business_id: CurrentBusinessId,
    test_id: str,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> list[CreativeTestVariantRead]:
    test = await service.get_test(
        session,
        organization_id=tenant.organization_id,
        business_id=business_id,
        test_id=test_id,
    )
    if test is None:
        raise NotFoundError("Creative test not found")
    rows = await service.list_test_variants(
        session,
        organization_id=tenant.organization_id,
        business_id=business_id,
        test_id=test_id,
    )
    return [CreativeTestVariantRead.model_validate(row) for row in rows]


@router.get(
    "/businesses/{business_id}/strategy/creative/portfolios",
    response_model=list[CreativePortfolioRead],
)
async def list_portfolios(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> list[CreativePortfolioRead]:
    rows = await service.list_portfolios(
        session, organization_id=tenant.organization_id, business_id=business_id
    )
    return [CreativePortfolioRead.model_validate(row) for row in rows]
