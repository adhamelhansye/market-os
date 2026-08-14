"""Shipping rule service. At most one default rule per business:
setting is_default on a rule clears the flag on the previous default."""

import uuid

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ShippingRule
from src.modules.shipping.schemas import ShippingRuleCreate, ShippingRuleUpdate


async def create_rule(
    session: AsyncSession, business_id: uuid.UUID, payload: ShippingRuleCreate
) -> ShippingRule:
    if payload.is_default:
        await _clear_defaults(session, business_id)
    rule = ShippingRule(
        business_id=business_id,
        name=payload.name,
        country=payload.country,
        region=payload.region,
        method=payload.method,
        cost=payload.cost,
        customer_price=payload.customer_price,
        free_shipping_threshold=payload.free_shipping_threshold,
        is_default=payload.is_default,
        active=payload.active,
    )
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return rule


async def update_rule(
    session: AsyncSession, rule: ShippingRule, payload: ShippingRuleUpdate
) -> ShippingRule:
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("is_default") is True:
        await _clear_defaults(session, rule.business_id, exclude=rule.id)
    for field, value in changes.items():
        setattr(rule, field, value)
    await session.commit()
    await session.refresh(rule)
    return rule


async def delete_rule(session: AsyncSession, rule: ShippingRule) -> None:
    await session.delete(rule)
    await session.commit()


async def _clear_defaults(
    session: AsyncSession, business_id: uuid.UUID, exclude: uuid.UUID | None = None
) -> None:
    stmt = (
        update(ShippingRule)
        .where(
            ShippingRule.business_id == business_id,
            ShippingRule.is_default.is_(True),
        )
        .values(is_default=False)
    )
    if exclude is not None:
        stmt = stmt.where(ShippingRule.id != exclude)
    await session.execute(stmt)