"""Product service: CRUD, price/cost history, inventory.

Overlapping active periods for prices/costs are rejected here (service
level, half-open intervals [effective_from, effective_to)).
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError, NotFoundError
from src.db.models import (
    InventorySnapshot,
    Product,
    ProductCost,
    ProductPrice,
    ShippingRule,
)
from src.modules.economics.calculator import calculate_product_economics
from src.modules.products.schemas import (
    InventoryAdjust,
    InventorySet,
    ProductCostCreate,
    ProductCreate,
    ProductPriceCreate,
    ProductUpdate,
)


def _now() -> datetime:
    return datetime.now(UTC)


def periods_overlap(
    a_from: datetime, a_to: datetime | None, b_from: datetime, b_to: datetime | None
) -> bool:
    """Half-open intervals [from, to): overlap iff each starts before the
    other ends.

    An existing OPEN period (a_to is None) only conflicts with a new period
    that starts BEFORE it. Appending a later period over an open one is
    allowed: the resolver picks the latest effective_from, so the newest
    period deterministically wins from its start date.
    """
    if a_to is None:
        return b_from < a_from
    if b_to is None:
        return b_from < a_to
    return a_from < b_to and b_from < a_to


async def get_product(session: AsyncSession, business_id, product_id) -> Product:
    if isinstance(product_id, str):
        product_id = uuid.UUID(product_id)
    product = await session.get(Product, product_id)
    if product is None or product.business_id != business_id:
        raise NotFoundError("Product not found")
    return product


async def create_product(
    session: AsyncSession, business, payload: ProductCreate
) -> Product:
    product = Product(
        business_id=business.id,
        sku=payload.sku,
        name=payload.name,
        description=payload.description,
        status=payload.status,
        currency=payload.currency,
    )
    session.add(product)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("Product SKU already exists in this business") from exc
    await session.refresh(product)
    return product


async def update_product(
    session: AsyncSession, product: Product, payload: ProductUpdate
) -> Product:
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(product, field, value)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("Product SKU already exists in this business") from exc
    await session.refresh(product)
    return product


async def archive_product(session: AsyncSession, product: Product) -> Product:
    """Soft delete: archives the product so history stays consistent."""
    product.status = "archived"
    await session.commit()
    await session.refresh(product)
    return product


async def create_price(
    session: AsyncSession, product: Product, payload: ProductPriceCreate
) -> ProductPrice:
    existing = list(
        await session.scalars(
            select(ProductPrice).where(ProductPrice.product_id == product.id)
        )
    )
    for period in existing:
        if periods_overlap(
            period.effective_from,
            period.effective_to,
            payload.effective_from,
            payload.effective_to,
        ):
            raise ConflictError("Price period overlaps an existing price period")

    price = ProductPrice(
        product_id=product.id,
        price=payload.price,
        currency=payload.currency,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
    )
    session.add(price)
    await session.commit()
    await session.refresh(price)
    return price


async def create_cost(
    session: AsyncSession, product: Product, payload: ProductCostCreate
) -> ProductCost:
    existing = list(
        await session.scalars(
            select(ProductCost).where(ProductCost.product_id == product.id)
        )
    )
    for period in existing:
        if periods_overlap(
            period.effective_from,
            period.effective_to,
            payload.effective_from,
            payload.effective_to,
        ):
            raise ConflictError("Cost period overlaps an existing cost period")

    cost = ProductCost(
        product_id=product.id,
        cogs=payload.cogs,
        packaging_cost=payload.packaging_cost,
        payment_fee_fixed=payload.payment_fee_fixed,
        payment_fee_percent=payload.payment_fee_percent,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
    )
    session.add(cost)
    await session.commit()
    await session.refresh(cost)
    return cost


async def current_inventory(session: AsyncSession, product_id) -> int:
    """Latest inventory snapshot quantity for the product (0 if never recorded)."""
    snapshot = await session.scalar(
        select(InventorySnapshot)
        .where(InventorySnapshot.product_id == product_id)
        .order_by(InventorySnapshot.recorded_at.desc(), InventorySnapshot.id.desc())
        .limit(1)
    )
    return snapshot.quantity if snapshot is not None else 0


async def set_inventory(
    session: AsyncSession, product: Product, payload: InventorySet
) -> InventorySnapshot:
    snapshot = InventorySnapshot(
        product_id=product.id, quantity=payload.quantity, source="manual"
    )
    session.add(snapshot)
    await session.commit()
    await session.refresh(snapshot)
    return snapshot


async def adjust_inventory(
    session: AsyncSession, product: Product, payload: InventoryAdjust
) -> InventorySnapshot:
    from src.modules.economics.service import current_inventory_quantity

    current = await current_inventory_quantity(session, product.id)
    new_quantity = current + payload.quantity_delta
    if new_quantity < 0:
        raise ConflictError("Inventory cannot go below zero")
    snapshot = InventorySnapshot(
        product_id=product.id, quantity=new_quantity, source="manual"
    )
    session.add(snapshot)
    await session.commit()
    await session.refresh(snapshot)
    return snapshot


async def default_shipping_rule(
    session: AsyncSession, business_id
) -> ShippingRule | None:
    return await session.scalar(
        select(ShippingRule)
        .where(
            ShippingRule.business_id == business_id,
            ShippingRule.active.is_(True),
            ShippingRule.is_default.is_(True),
        )
        .order_by(ShippingRule.created_at.desc())
        .limit(1)
    )


async def product_detail(
    session: AsyncSession, product: Product
) -> dict:
    """Product list row: identity + active price + unit economics + stock."""
    from src.modules.economics.service import (
        current_inventory_quantity,
        resolve_active_cost,
        resolve_active_price,
    )

    as_of = _now()
    price = await resolve_active_price(session, product.id, as_of)
    cost = await resolve_active_cost(session, product.id, as_of)

    if price is not None:
        shipping = await default_shipping_rule(session, product.business_id)
        economics = calculate_product_economics(
            price=price.price,
            cogs=cost.cogs if cost else Decimal("0"),
            packaging_cost=cost.packaging_cost if cost else Decimal("0"),
            payment_fee_fixed=cost.payment_fee_fixed if cost else Decimal("0"),
            payment_fee_percent=cost.payment_fee_percent if cost else Decimal("0"),
            shipping_cost=shipping.cost if shipping else Decimal("0"),
            shipping_customer_price=shipping.customer_price if shipping else Decimal("0"),
        )
        contribution_profit = economics.contribution_profit
        contribution_margin = economics.contribution_margin
    else:
        contribution_profit = None
        contribution_margin = None

    return {
        "id": product.id,
        "business_id": product.business_id,
        "sku": product.sku,
        "name": product.name,
        "description": product.description,
        "status": product.status,
        "currency": product.currency,
        "created_at": product.created_at,
        "updated_at": product.updated_at,
        "inventory_quantity": await current_inventory_quantity(session, product.id),
        "active_price": price.price if price else None,
        "contribution_profit": contribution_profit,
        "contribution_margin": contribution_margin,
    }