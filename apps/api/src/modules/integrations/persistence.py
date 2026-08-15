"""Persistence of canonical provider data.

Every function here is IDEMPOTENT: re-running a sync or processing a webhook
twice converges to the same state. Unique database constraints
((business_id, external_id) for products/customers, (business_id, source,
external_id) for orders) are the integrity anchor; application logic just
picks the cheaper path.

No function commits: callers own the transaction boundary (one commit per
canonical record, with a single IntegrityError retry for races).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Customer,
    InventorySnapshot,
    Order,
    OrderItem,
    Product,
    ProductPrice,
)
from src.modules.economics.service import resolve_active_price
from src.modules.integrations.base.types import (
    CanonicalCustomer,
    CanonicalInventory,
    CanonicalOrder,
    CanonicalOrderItem,
    CanonicalProduct,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _normalize_currency(value: str | None, fallback: str | None) -> str:
    """Deterministic currency normalization: exactly three uppercase ASCII
    letters; anything else falls back (Shopify order currencies can be
    short/odd strings that the DB constraint would otherwise reject)."""
    for candidate in ((value or "").strip().upper(), (fallback or "").strip().upper()):
        if len(candidate) == 3 and candidate.isalpha() and candidate.isascii():
            return candidate
    return "USD"


def _product_status(status: str) -> str:
    """Provider status → internal status (active/inactive/archived)."""
    mapped = {"active": "active", "archived": "archived", "draft": "inactive"}
    return mapped.get(status, "inactive")


def _first_variant_sku(product: CanonicalProduct) -> str | None:
    for variant in product.variants:
        if variant.sku:
            return variant.sku
    return None


async def upsert_customer(
    session: AsyncSession, business_id, canonical: CanonicalCustomer
) -> uuid.UUID:
    customer = await session.scalar(
        select(Customer).where(
            Customer.business_id == business_id,
            Customer.external_id == canonical.external_id,
        )
    )
    if customer is None:
        customer = Customer(
            business_id=business_id,
            external_id=canonical.external_id,
            email=canonical.email,
        )
        session.add(customer)
    elif canonical.email and canonical.email != customer.email:
        customer.email = canonical.email
    await session.flush()
    return customer.id


async def upsert_product(
    session: AsyncSession,
    business_id,
    canonical: CanonicalProduct,
    *,
    currency_fallback: str | None,
) -> uuid.UUID:
    """Upserts a canonical product (match by external_id, then by SKU) and
    appends a new product_prices record when the anchor price changed.

    COGS (product_costs) are NEVER written here: manually configured costs
    must not be overwritten by sync.
    """
    sku = _first_variant_sku(canonical)
    product = await session.scalar(
        select(Product).where(
            Product.business_id == business_id,
            Product.external_id == canonical.external_id,
        )
    )
    if product is None and sku:
        # Manual product match: only attach the external mapping when the
        # candidate does not belong to a DIFFERENT provider record.
        candidate = await session.scalar(
            select(Product).where(
                Product.business_id == business_id, Product.sku == sku
            )
        )
        if candidate is not None and (
            candidate.external_id is None or candidate.external_id == canonical.external_id
        ):
            product = candidate
            sku = None  # already set on the existing row
    currency = _normalize_currency(canonical.currency, currency_fallback)

    if product is None:
        product = Product(
            business_id=business_id,
            sku=sku,
            name=canonical.title,
            status=_product_status(canonical.status),
            currency=currency,
            external_id=canonical.external_id,
            external_source="shopify",
        )
        session.add(product)
    else:
        product.name = canonical.title
        product.status = _product_status(canonical.status)
        if product.external_id is None:
            product.external_id = canonical.external_id
        if product.external_source is None:
            product.external_source = "shopify"
        if product.sku is None and sku:
            product.sku = sku
    await session.flush()

    prices = [v.price for v in canonical.variants if v.price is not None]
    if prices:
        anchor = min(prices)
        active = await resolve_active_price(session, product.id, _now())
        if active is None or active.price != anchor:
            session.add(
                ProductPrice(
                    product_id=product.id,
                    price=anchor,
                    currency=currency,
                    effective_from=_now(),
                    effective_to=None,
                )
            )
    return product.id


async def write_inventory_snapshot(
    session: AsyncSession, business_id, canonical: CanonicalInventory
) -> None:
    """Appends an inventory_snapshots(source='shopify') row ONLY when the
    quantity differs from the latest snapshot for the product (avoids
    noise rows on every sync)."""
    if canonical.product_external_id is None:
        return
    product_id = await session.scalar(
        select(Product.id).where(
            Product.business_id == business_id,
            Product.external_id == canonical.product_external_id,
        )
    )
    if product_id is None:
        return  # product not synced yet; the next sync run covers it
    latest = await session.scalar(
        select(InventorySnapshot)
        .where(InventorySnapshot.product_id == product_id)
        .order_by(InventorySnapshot.recorded_at.desc(), InventorySnapshot.id.desc())
        .limit(1)
    )
    if latest is not None and latest.quantity == canonical.quantity:
        return
    session.add(
        InventorySnapshot(
            product_id=product_id,
            quantity=canonical.quantity,
            source="shopify",
        )
    )


async def upsert_order(
    session: AsyncSession,
    business_id,
    source: str,
    canonical: CanonicalOrder,
    *,
    currency_fallback: str | None,
) -> uuid.UUID:
    customer_id: uuid.UUID | None = None
    if canonical.customer_external_id:
        customer_id = await upsert_customer(
            session,
            business_id,
            CanonicalCustomer(
                external_id=canonical.customer_external_id,
                email=canonical.customer_email,
                updated_at=canonical.updated_at,
            ),
        )

    order = await session.scalar(
        select(Order).where(
            Order.business_id == business_id,
            Order.source == source,
            Order.external_id == canonical.external_id,
        )
    )
    currency = _normalize_currency(canonical.currency, currency_fallback)
    if order is None:
        order = Order(
            business_id=business_id,
            external_id=canonical.external_id,
            source=source,
            customer_id=customer_id,
            currency=currency,
            subtotal=canonical.subtotal,
            discount_total=canonical.discount_total,
            shipping_revenue=canonical.shipping_revenue,
            tax_total=canonical.tax_total,
            total=canonical.total,
            financial_status=canonical.financial_status,
            fulfillment_status=canonical.fulfillment_status,
            ordered_at=canonical.ordered_at,
        )
        session.add(order)
    else:
        order.customer_id = customer_id
        order.currency = currency
        order.subtotal = canonical.subtotal
        order.discount_total = canonical.discount_total
        order.shipping_revenue = canonical.shipping_revenue
        order.tax_total = canonical.tax_total
        order.total = canonical.total
        order.financial_status = canonical.financial_status
        order.fulfillment_status = canonical.fulfillment_status
        order.ordered_at = canonical.ordered_at
    await session.flush()

    # Replace line items wholesale (the canonical record is authoritative).
    await session.execute(delete(OrderItem).where(OrderItem.order_id == order.id))
    await _insert_order_items(session, business_id, order.id, canonical.items)
    return order.id


async def _insert_order_items(
    session: AsyncSession,
    business_id,
    order_id: uuid.UUID,
    items: list[CanonicalOrderItem],
) -> None:
    if not items:
        return
    external_ids = [item.external_product_id for item in items]
    products = {
        row.external_id: row.id
        for row in await session.scalars(
            select(Product)
            .where(
                Product.business_id == business_id,
                Product.external_id.in_(external_ids),
            )
        )
    }
    for item in items:
        session.add(
            OrderItem(
                order_id=order_id,
                product_id=products.get(item.external_product_id),
                external_product_id=item.external_product_id,
                external_variant_id=item.external_variant_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
                discount_amount=item.discount_amount,
                line_total=item.line_total,
            )
        )