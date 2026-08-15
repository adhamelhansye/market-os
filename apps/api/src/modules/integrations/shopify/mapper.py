"""Shopify payload → canonical data mapping.

Pure functions: validated Shopify API schemas in, canonical MarketingOS
types out. Money strings become Decimal here (never float). No other module
knows Shopify response formats; the mapper is the only translation layer.
"""

from decimal import Decimal, InvalidOperation

from src.modules.integrations.base.errors import ProviderDataError
from src.modules.integrations.base.types import (
    CanonicalCustomer,
    CanonicalInventory,
    CanonicalOrder,
    CanonicalOrderItem,
    CanonicalProduct,
    CanonicalVariant,
)
from src.modules.integrations.shopify.schemas import (
    CustomerResponse,
    InventoryLevelResponse,
    OrderResponse,
    ProductResponse,
)


def _money(value: str | None, field: str) -> Decimal:
    try:
        return Decimal(value or "0")
    except (InvalidOperation, TypeError, ValueError):
        raise ProviderDataError(f"Invalid money value in Shopify field {field}") from None


def _status(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip().lower() or None


def map_variant(variant) -> CanonicalVariant:
    return CanonicalVariant(
        external_id=str(variant.id),
        sku=(variant.sku or "").strip() or None,
        price=_money(variant.price, "variant.price"),
        inventory_quantity=variant.inventory_quantity,
        inventory_item_id=str(variant.inventory_item_id) if variant.inventory_item_id else None,
    )


def map_product(product: ProductResponse, currency: str) -> CanonicalProduct:
    return CanonicalProduct(
        external_id=str(product.id),
        title=product.title,
        status=_status(product.status) or "active",
        currency=currency,
        variants=[map_variant(v) for v in product.variants],
        updated_at=product.updated_at,
    )


def map_variant_inventory(product: ProductResponse) -> CanonicalInventory:
    """Per-product inventory total (sum of variant quantities).

    MarketingOS keeps one inventory quantity per product; Shopify's
    variant-level quantities are summed deterministically.
    """
    total = sum((v.inventory_quantity or 0) for v in product.variants)
    return CanonicalInventory(
        external_variant_id=None,
        inventory_item_id=None,
        quantity=total,
        product_external_id=str(product.id),
    )


def map_order(order: OrderResponse) -> CanonicalOrder:
    """Maps a Shopify order. Cancellations arrive with an updated
    financial_status; the mapper simply reflects whatever state the
    provider reports."""
    items: list[CanonicalOrderItem] = []
    for line in order.line_items:
        quantity = line.quantity or 0
        if quantity <= 0:
            continue
        unit_price = _money(line.price, "line.price")
        discount = _money(line.total_discount, "line.total_discount")
        items.append(
            CanonicalOrderItem(
                external_product_id=(
                    str(line.product_id)
                    if line.product_id
                    else f"custom:{line.variant_id or 'unknown'}"
                ),
                external_variant_id=str(line.variant_id) if line.variant_id else None,
                quantity=quantity,
                unit_price=unit_price,
                discount_amount=discount,
                line_total=(unit_price * quantity - discount).quantize(Decimal("0.01")),
            )
        )

    shipping_revenue = sum(
        (_money(line.price, "shipping.price") for line in order.shipping_lines), Decimal("0")
    )
    tax_total = _money(order.total_tax, "order.total_tax") if order.total_tax is not None else None

    return CanonicalOrder(
        external_id=str(order.id),
        currency=(order.currency or "USD").strip().upper()[:3],
        subtotal=_money(order.subtotal_price, "order.subtotal_price"),
        discount_total=_money(order.total_discounts, "order.total_discounts"),
        shipping_revenue=shipping_revenue.quantize(Decimal("0.01")),
        tax_total=tax_total,
        total=_money(order.total_price, "order.total_price"),
        financial_status=_status(order.financial_status) or "pending",
        fulfillment_status=_status(order.fulfillment_status),
        ordered_at=order.created_at,
        updated_at=order.updated_at,
        customer_external_id=str(order.customer.id) if order.customer else None,
        customer_email=order.customer.email if order.customer else None,
        items=items,
    )


def map_customer(customer: CustomerResponse) -> CanonicalCustomer:
    return CanonicalCustomer(
        external_id=str(customer.id),
        email=(customer.email or "").strip().lower() or None,
        updated_at=customer.updated_at,
    )


def map_inventory(
    level: InventoryLevelResponse, *, product_external_id: str | None = None
) -> CanonicalInventory:
    return CanonicalInventory(
        external_variant_id=None,
        inventory_item_id=str(level.inventory_item_id),
        quantity=level.available,
        product_external_id=product_external_id,
    )