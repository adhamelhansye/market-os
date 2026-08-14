"""Business endpoints scoped to the current tenant (agency/business access)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select

from src.core.dependencies import (
    CurrentBusinessId,
    DbSession,
    require_permission,
)
from src.core.exceptions import NotFoundError
from src.core.tenancy import TenantContext
from src.db.models import Business
from src.schemas.entities import BusinessRead

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


@router.get("/businesses/{business_id}", response_model=BusinessRead)
async def get_business(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> BusinessRead:
    business = await session.get(Business, business_id)
    if business is None:
        raise NotFoundError("Business not found")
    return BusinessRead.model_validate(business)