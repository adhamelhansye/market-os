"""Business endpoints scoped to the current tenant (agency/business access)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select

from src.core.dependencies import (
    CurrentBusinessId,
    DbSession,
    require_permission,
)
from src.core.tenancy import TenantContext
from src.db.models import Business
from src.modules.businesses import service
from src.modules.businesses.schemas import (
    BusinessCreate,
    BusinessProfileRead,
    BusinessProfileWrite,
    BusinessRead,
    BusinessUpdate,
)

router = APIRouter(tags=["businesses"])


@router.get("/businesses", response_model=list[BusinessRead])
async def list_businesses(
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> list[BusinessRead]:
    rows = await session.scalars(
        select(Business).where(
            or_(
                Business.organization_id == tenant.organization_id,
                Business.managed_by_organization_id == tenant.organization_id,
            )
        )
    )
    return [BusinessRead.model_validate(business) for business in rows]


@router.post("/businesses", response_model=BusinessRead, status_code=201)
async def create_business(
    payload: BusinessCreate,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> BusinessRead:
    business = await service.create_business(session, tenant.organization_id, payload)
    return BusinessRead.model_validate(business)


@router.get("/businesses/{business_id}", response_model=BusinessRead)
async def get_business(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> BusinessRead:
    business = await service.get_business(session, business_id)
    return BusinessRead.model_validate(business)


@router.patch("/businesses/{business_id}", response_model=BusinessRead)
async def update_business(
    payload: BusinessUpdate,
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> BusinessRead:
    business = await service.get_business(session, business_id)
    business = await service.update_business(session, business, payload)
    return BusinessRead.model_validate(business)


@router.get(
    "/businesses/{business_id}/profile", response_model=BusinessProfileRead
)
async def get_profile(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> BusinessProfileRead:
    profile = await service.get_profile(session, business_id)
    return BusinessProfileRead(
        business_id=profile.business_id,
        description=profile.description,
        industry=profile.industry,
        business_model=profile.business_model,
        target_market=profile.target_market,
        brand_positioning=profile.brand_positioning,
        average_order_value=profile.average_order_value,
        primary_customer_type=profile.primary_customer_type,
        brand_voice=profile.brand_voice,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.put(
    "/businesses/{business_id}/profile", response_model=BusinessProfileRead
)
async def upsert_profile(
    payload: BusinessProfileWrite,
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> BusinessProfileRead:
    profile = await service.upsert_profile(session, business_id, payload)
    return BusinessProfileRead(
        business_id=profile.business_id,
        description=profile.description,
        industry=profile.industry,
        business_model=profile.business_model,
        target_market=profile.target_market,
        brand_positioning=profile.brand_positioning,
        average_order_value=profile.average_order_value,
        primary_customer_type=profile.primary_customer_type,
        brand_voice=profile.brand_voice,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )