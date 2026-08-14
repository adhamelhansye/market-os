"""Shipping rule endpoints, scoped to a business."""

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
from src.db.models import ShippingRule
from src.modules.shipping import service
from src.modules.shipping.schemas import (
    ShippingRuleCreate,
    ShippingRuleRead,
    ShippingRuleUpdate,
)

router = APIRouter(tags=["shipping"])


async def get_rule_from_path(
    request: Request, business_id: CurrentBusinessId, session: DbSession
) -> ShippingRule:
    raw = request.path_params.get("rule_id", "")
    try:
        rule_id = uuid.UUID(raw)
    except ValueError:
        raise NotFoundError("Shipping rule not found") from None
    rule = await session.get(ShippingRule, rule_id)
    if rule is None or rule.business_id != business_id:
        raise NotFoundError("Shipping rule not found")
    return rule


CurrentShippingRule = Annotated[ShippingRule, Depends(get_rule_from_path)]


@router.get(
    "/businesses/{business_id}/shipping-rules", response_model=list[ShippingRuleRead]
)
async def list_shipping_rules(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> list[ShippingRuleRead]:
    rules = list(
        await session.scalars(
            select(ShippingRule)
            .where(ShippingRule.business_id == business_id)
            .order_by(ShippingRule.country, ShippingRule.name)
        )
    )
    return [ShippingRuleRead.model_validate(r) for r in rules]


@router.post(
    "/businesses/{business_id}/shipping-rules",
    response_model=ShippingRuleRead,
    status_code=201,
)
async def create_shipping_rule(
    payload: ShippingRuleCreate,
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> ShippingRuleRead:
    rule = await service.create_rule(session, business_id, payload)
    return ShippingRuleRead.model_validate(rule)


@router.patch(
    "/businesses/{business_id}/shipping-rules/{rule_id}",
    response_model=ShippingRuleRead,
)
async def update_shipping_rule(
    payload: ShippingRuleUpdate,
    rule: CurrentShippingRule,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> ShippingRuleRead:
    rule = await service.update_rule(session, rule, payload)
    return ShippingRuleRead.model_validate(rule)


@router.delete(
    "/businesses/{business_id}/shipping-rules/{rule_id}", status_code=204
)
async def delete_shipping_rule(
    rule: CurrentShippingRule,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> None:
    await service.delete_rule(session, rule)