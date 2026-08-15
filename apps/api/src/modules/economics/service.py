"""Economics service: resolves active price/cost/shipping/discount records
for a date and feeds them into the deterministic calculator.

The service only decides WHICH records apply; the calculator owns all
arithmetic (pure Decimal, no LLM).
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from statistics import mean

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Bundle,
    BundleItem,
    Business,
    BusinessGoal,
    Discount,
    InventorySnapshot,
    Product,
    ProductCost,
    ProductPrice,
    ShippingRule,
)
from src.modules.economics.calculator import (
    ZERO,
    BundleEconomics,
    ProductEconomics,
    calculate_bundle_economics,
    calculate_product_economics,
)
from src.modules.economics.constants import (
    TARGET_CPA_REASON_NEGATIVE_CONTRIBUTION,
    TARGET_CPA_REASON_NO_PRICE,
    TARGET_CPA_REASON_NOT_PROVIDED,
)


async def resolve_active_price(
    session: AsyncSession, product_id, as_of: datetime
) -> ProductPrice | None:
    """The price record covering `as_of` (latest effective_from wins)."""
    return await session.scalar(
        select(ProductPrice)
        .where(
            ProductPrice.product_id == product_id,
            ProductPrice.effective_from <= as_of,
            or_(
                ProductPrice.effective_to.is_(None),
                ProductPrice.effective_to > as_of,
            ),
        )
        .order_by(ProductPrice.effective_from.desc())
        .limit(1)
    )


async def resolve_active_cost(
    session: AsyncSession, product_id, as_of: datetime
) -> ProductCost | None:
    """The cost record covering `as_of` (latest effective_from wins)."""
    return await session.scalar(
        select(ProductCost)
        .where(
            ProductCost.product_id == product_id,
            ProductCost.effective_from <= as_of,
            or_(
                ProductCost.effective_to.is_(None),
                ProductCost.effective_to > as_of,
            ),
        )
        .order_by(ProductCost.effective_from.desc())
        .limit(1)
    )


async def resolve_shipping_rule(
    session: AsyncSession, business_id, as_of: datetime
) -> ShippingRule | None:
    """The default active shipping rule for the business, if any.

    If the business has no default rule, no shipping is assumed in unit
    economics (cost 0, customer price 0).
    """
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


async def best_active_discount(
    session: AsyncSession, business_id, as_of: datetime
) -> Discount | None:
    """The most favorable active discount for a single order.

    Approximation documented in unit-economics.md: percentage discounts are
    compared against the highest active product price in the business.
    """
    stmt = select(Discount).where(
        Discount.business_id == business_id,
        Discount.active.is_(True),
        Discount.starts_at <= as_of,
        Discount.ends_at > as_of,
    )
    discounts = list(await session.scalars(stmt))
    if not discounts:
        return None

    highest_price = await session.scalar(
        select(ProductPrice.price)
        .join(Product, Product.id == ProductPrice.product_id)
        .where(
            Product.business_id == business_id,
            Product.status == "active",
            ProductPrice.effective_from <= as_of,
            or_(ProductPrice.effective_to.is_(None), ProductPrice.effective_to > as_of),
        )
        .order_by(ProductPrice.price.desc())
        .limit(1)
    )
    if highest_price is None:
        return None

    def _amount(d: Discount) -> Decimal:
        if d.type == "percentage":
            return highest_price * d.value / Decimal("100")
        return d.value

    return max(discounts, key=lambda d: _amount(d))


async def current_inventory_quantity(
    session: AsyncSession, product_id
) -> int:
    """Latest inventory snapshot for the product (0 when never recorded)."""
    snapshot = await session.scalar(
        select(InventorySnapshot)
        .where(InventorySnapshot.product_id == product_id)
        .order_by(InventorySnapshot.recorded_at.desc(), InventorySnapshot.id.desc())
        .limit(1)
    )
    return snapshot.quantity if snapshot is not None else 0


def _as_of() -> datetime:
    return datetime.now(UTC)


async def product_economics(
    session: AsyncSession, product: Product
) -> ProductEconomics | None:
    """Unit economics for a product at its current active records.

    Returns None when the product has no active price (nothing to compute).
    Missing cost records default to zero; missing shipping means no shipping.
    """
    as_of = _as_of()
    price = await resolve_active_price(session, product.id, as_of)
    if price is None:
        return None

    cost = await resolve_active_cost(session, product.id, as_of)
    shipping = await resolve_shipping_rule(session, product.business_id, as_of)
    discount = await best_active_discount(session, product.business_id, as_of)

    return calculate_product_economics(
        price=price.price,
        cogs=cost.cogs if cost else ZERO,
        packaging_cost=cost.packaging_cost if cost else ZERO,
        payment_fee_fixed=cost.payment_fee_fixed if cost else ZERO,
        payment_fee_percent=cost.payment_fee_percent if cost else ZERO,
        shipping_cost=shipping.cost if shipping else ZERO,
        shipping_customer_price=shipping.customer_price if shipping else ZERO,
        discount_type=discount.type if discount else None,
        discount_value=discount.value if discount else ZERO,
        discount_minimum_order_value=discount.minimum_order_value if discount else None,
        discount_maximum_discount=discount.maximum_discount if discount else None,
    )


async def bundle_economics(
    session: AsyncSession, bundle: Bundle
) -> BundleEconomics:
    """Bundle economics from its underlying product costs (active cost records)."""
    as_of = _as_of()
    quantities: list[int] = []
    item_costs: list[Decimal] = []
    items = list(await session.scalars(select(BundleItem).where(BundleItem.bundle_id == bundle.id)))
    for item in items:
        cost = await resolve_active_cost(session, item.product_id, as_of)
        item_costs.append(cost.cogs + cost.packaging_cost if cost else ZERO)
        quantities.append(item.quantity)
    return calculate_bundle_economics(
        bundle_price=bundle.price, item_costs=item_costs, quantities=quantities
    )


async def current_goal(
    session: AsyncSession, business_id, as_of: datetime
) -> BusinessGoal | None:
    """The goal whose period contains `as_of` (periods are non-overlapping)."""
    return await session.scalar(
        select(BusinessGoal).where(
            BusinessGoal.business_id == business_id,
            BusinessGoal.period_start <= as_of,
            BusinessGoal.period_end > as_of,
        )
    )


async def summary_data(
    session: AsyncSession, business: Business, as_of: datetime | None = None
) -> dict:
    """Aggregates per-product economics into the summary metrics.

    All aggregates are computed over active products that have an active
    price ("priced products"). Averages are of the per-unit economics.
    """
    if as_of is None:
        as_of = _as_of()
    products = list(
        await session.scalars(
            select(Product).where(
                Product.business_id == business.id, Product.status == "active"
            )
        )
    )

    priced: list[tuple[Product, ProductEconomics]] = []
    for product in products:
        economics = await product_economics(session, product)
        if economics is not None:
            priced.append((product, economics))

    active_products = len(products)

    if priced:
        average_product_price = mean(
            e.product_revenue for _, e in priced
        ).quantize(Decimal("0.01"))
        average_contribution_profit = mean(
            e.contribution_profit for _, e in priced
        ).quantize(Decimal("0.01"))
        average_total_customer_revenue = mean(
            e.total_customer_revenue for _, e in priced
        ).quantize(Decimal("0.01"))
        margins = [e.contribution_margin for _, e in priced if e.contribution_margin is not None]
        average_contribution_margin = (
            mean(margins).quantize(Decimal("0.0001")) if margins else None
        )
        break_even_cpas = [e.break_even_cpa for _, e in priced]
        break_even_cpa_range = [
            min(break_even_cpas).quantize(Decimal("0.01")),
            max(break_even_cpas).quantize(Decimal("0.01")),
        ]
        break_even_roas = (
            (average_total_customer_revenue / average_contribution_profit).quantize(
                Decimal("0.0001")
            )
            if average_contribution_profit > ZERO
            else None
        )
        if average_contribution_profit > ZERO:
            target_cpa_reason = TARGET_CPA_REASON_NOT_PROVIDED
        else:
            target_cpa_reason = TARGET_CPA_REASON_NEGATIVE_CONTRIBUTION
    else:
        average_product_price = None
        average_contribution_profit = None
        average_total_customer_revenue = None
        average_contribution_margin = None
        break_even_cpa_range = None
        break_even_roas = None
        target_cpa_reason = TARGET_CPA_REASON_NO_PRICE

    inventory_value = ZERO
    for product in products:
        quantity = await current_inventory_quantity(session, product.id)
        if quantity <= 0:
            continue
        price = await resolve_active_price(session, product.id, as_of)
        if price is not None:
            inventory_value += quantity * price.price

    return {
        "business_id": business.id,
        "business_name": business.name,
        "currency": business.currency,
        "active_products": active_products,
        "priced_products": len(priced),
        "average_product_price": average_product_price,
        "average_contribution_profit": average_contribution_profit,
        "average_contribution_margin": average_contribution_margin,
        "average_total_customer_revenue": average_total_customer_revenue,
        "break_even_cpa_range": break_even_cpa_range,
        "target_cpa": None,
        "target_cpa_reason": target_cpa_reason,
        "break_even_roas": break_even_roas,
        "inventory_value": inventory_value.quantize(Decimal("0.01")),
        "current_goal": await current_goal(session, business.id, as_of),
    }


async def revenue_summary(session: AsyncSession, business: Business) -> dict:
    """Read-only revenue summary sourced from canonical orders.

    Deterministic aggregation: pure Decimal sums over the orders table
    filtered by (business_id). Multi-currency orders are converted to the
    business's currency only when the order currency matches; otherwise
    they are excluded from totals to keep the arithmetic honest (an order
    in EUR is not silently summed into a USD business total).

    Refunded revenue counts orders whose financial_status is in
    {'refunded', 'partially_refunded'}.
    """
    from src.db.models import Order

    as_of = _as_of()
    window_start = as_of - timedelta(days=30)

    rows = list(
        await session.scalars(
            select(Order)
            .where(Order.business_id == business.id)
            .order_by(Order.ordered_at)
        )
    )
    total_revenue = ZERO
    refunded_revenue = ZERO
    last_30d_revenue = ZERO
    last_30d_orders = 0
    order_count = 0
    for order in rows:
        if order.currency != business.currency:
            continue
        order_count += 1
        total_revenue += order.total
        if order.financial_status in {"refunded", "partially_refunded"}:
            refunded_revenue += order.total
        if order.ordered_at >= window_start:
            last_30d_revenue += order.total
            last_30d_orders += 1

    return {
        "business_id": business.id,
        "currency": business.currency,
        "order_count": order_count,
        "total_revenue": total_revenue.quantize(Decimal("0.01")),
        "refunded_revenue": refunded_revenue.quantize(Decimal("0.01")),
        "last_30d_revenue": last_30d_revenue.quantize(Decimal("0.01")),
        "last_30d_orders": last_30d_orders,
        "last_30d_window_start": window_start,
    }