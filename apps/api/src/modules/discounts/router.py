"""Discount endpoints, scoped to a business."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from src.core.dependencies import (
    CurrentBusinessId,
    DbSession,
    require_permission,
)
from src.core.exceptions import NotFoundError
from src.core.tenancy import TenantContext
from src.db.models import Discount
from src.modules.discounts.schemas import DiscountCreate, DiscountRead, DiscountUpdate

router = APIRouter(tags=["discounts"])


async def get_discount_from_path(
    request: Request, business_id: CurrentBusinessId, session: DbSession
) -> Discount:
    raw = request.path_params.get("discount_id", "")
    try:
        discount_id = uuid.UUID(raw)
    except ValueError:
        raise NotFoundError("Discount not found") from None
    discount = await session.get(Discount, discount_id)
    if discount is None or discount.business_id != business_id:
        raise NotFoundError("Discount not found")
    return discount


CurrentDiscount = Annotated[Discount, Depends(get_discount_from_path)]


@router.get("/businesses/{business_id}/discounts", response_model=list[DiscountRead])
async def list_discounts(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> list[DiscountRead]:
    discounts = list(
        await session.scalars(
            select(Discount)
            .where(Discount.business_id == business_id)
            .order_by(Discount.starts_at.desc())
        )
    )
    return [DiscountRead.model_validate(d) for d in discounts]


@router.post(
    "/businesses/{business_id}/discounts",
    response_model=DiscountRead,
    status_code=201,
)
async def create_discount(
    payload: DiscountCreate,
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> DiscountRead:
    discount = Discount(
        business_id=business_id,
        name=payload.name,
        type=payload.type,
        value=payload.value,
        minimum_order_value=payload.minimum_order_value,
        maximum_discount=payload.maximum_discount,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        active=payload.active,
    )
    session.add(discount)
    await session.commit()
    await session.refresh(discount)
    return DiscountRead.model_validate(discount)


@router.patch(
    "/businesses/{business_id}/discounts/{discount_id}",
    response_model=DiscountRead,
)
async def update_discount(
    payload: DiscountUpdate,
    discount: CurrentDiscount,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> DiscountRead:
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(discount, field, value)
    await session.commit()
    await session.refresh(discount)
    return DiscountRead.model_validate(discount)