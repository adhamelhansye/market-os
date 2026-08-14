"""Deterministic unit economics.

This layer contains NO LLM logic and NO database access: it is pure
Decimal arithmetic. All inputs are explicit so that callers (services)
control exactly which price/cost/shipping/discount records are used.

Formulas (single order, quantity 1):

    product_revenue           = product price charged to the customer
    shipping_revenue          = shipping price charged to the customer
    total_customer_revenue    = product_revenue + shipping_revenue
    product_cost              = cogs + packaging_cost
    payment_fees              = payment_fee_fixed
                                + product_revenue * payment_fee_percent / 100
    discount_amount           = percentage: min(price * value/100, maximum_discount)
                                fixed:      min(value, maximum_discount)
                                always capped at product_revenue (never below zero)
    contribution_profit       = product_revenue - product_cost - payment_fees
                                - shipping_cost + shipping_revenue - discount_amount
    contribution_margin       = contribution_profit / total_customer_revenue
    break_even_cpa            = contribution_profit   (max ad spend before negative)
    break_even_roas           = total_customer_revenue / contribution_profit
                                (only when contribution_profit > 0)
    target_cpa                = break_even_cpa - desired_profit_per_order
                                (only when a desired profit assumption is provided)

See docs/architecture/unit-economics.md for the full metric glossary.
"""

from dataclasses import dataclass
from decimal import Decimal

ZERO = Decimal("0")
HUNDRED = Decimal("100")


@dataclass(frozen=True)
class ProductEconomics:
    product_revenue: Decimal
    shipping_revenue: Decimal
    total_customer_revenue: Decimal
    product_cost: Decimal
    shipping_cost: Decimal
    payment_fees: Decimal
    discount_amount: Decimal
    contribution_profit: Decimal
    contribution_margin: Decimal | None
    break_even_cpa: Decimal
    break_even_roas: Decimal | None
    target_cpa: Decimal | None
    target_cpa_reason: str | None


@dataclass(frozen=True)
class BundleEconomics:
    bundle_price: Decimal
    items_cost: Decimal
    contribution_profit: Decimal
    contribution_margin: Decimal | None


def _quantize(value: Decimal) -> Decimal:
    """All money output is quantized to 2 decimal places."""
    return value.quantize(Decimal("0.01"))


def _divide(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    """Safe division: never raises, never silently divides by zero."""
    if denominator == ZERO:
        return None
    return numerator / denominator


def calculate_discount_amount(
    *,
    product_revenue: Decimal,
    discount_type: str,
    discount_value: Decimal,
    minimum_order_value: Decimal | None,
    maximum_discount: Decimal | None,
    order_value: Decimal | None = None,
) -> Decimal:
    """The monetary discount impact of a single discount on a single order.

    - percentage discounts apply to the product revenue
    - fixed discounts are a flat amount
    - minimum_order_value gates the discount (against the full order value)
    - maximum_discount caps the discount amount
    - the discount can never exceed the product revenue
    """
    if minimum_order_value is not None:
        effective_order = order_value if order_value is not None else product_revenue
        if effective_order < minimum_order_value:
            return ZERO

    if discount_type == "percentage":
        amount = product_revenue * discount_value / HUNDRED
    elif discount_type == "fixed_amount":
        amount = discount_value
    else:  # pragma: no cover - schema/DB constrain the type
        amount = ZERO

    if maximum_discount is not None:
        amount = min(amount, maximum_discount)
    return _quantize(min(amount, product_revenue))


def calculate_product_economics(
    *,
    price: Decimal,
    cogs: Decimal = ZERO,
    packaging_cost: Decimal = ZERO,
    payment_fee_fixed: Decimal = ZERO,
    payment_fee_percent: Decimal = ZERO,
    shipping_cost: Decimal = ZERO,
    shipping_customer_price: Decimal = ZERO,
    discount_type: str | None = None,
    discount_value: Decimal = ZERO,
    discount_minimum_order_value: Decimal | None = None,
    discount_maximum_discount: Decimal | None = None,
    desired_profit_per_order: Decimal | None = None,
) -> ProductEconomics:
    """Unit economics for one order of one product at the given price/costs."""
    product_revenue = price
    shipping_revenue = shipping_customer_price
    total_customer_revenue = product_revenue + shipping_revenue
    product_cost = cogs + packaging_cost
    payment_fees = payment_fee_fixed + product_revenue * payment_fee_percent / HUNDRED

    if discount_type is not None:
        discount_amount = calculate_discount_amount(
            product_revenue=product_revenue,
            discount_type=discount_type,
            discount_value=discount_value,
            minimum_order_value=discount_minimum_order_value,
            maximum_discount=discount_maximum_discount,
            order_value=total_customer_revenue,
        )
    else:
        discount_amount = ZERO

    contribution_profit = (
        product_revenue
        - product_cost
        - payment_fees
        - shipping_cost
        + shipping_revenue
        - discount_amount
    )

    contribution_profit = _quantize(contribution_profit)
    contribution_margin = _divide(contribution_profit, total_customer_revenue)
    contribution_margin = (
        contribution_margin.quantize(Decimal("0.0001")) if contribution_margin is not None else None
    )

    break_even_cpa = contribution_profit
    break_even_roas = (
        _divide(total_customer_revenue, contribution_profit)
        if contribution_profit > ZERO
        else None
    )
    if break_even_roas is not None:
        break_even_roas = break_even_roas.quantize(Decimal("0.0001"))

    if desired_profit_per_order is not None:
        target_cpa = break_even_cpa - desired_profit_per_order
        target_cpa_reason = None
    else:
        target_cpa = None
        target_cpa_reason = "target_profit_per_order_not_provided"

    return ProductEconomics(
        product_revenue=_quantize(product_revenue),
        shipping_revenue=_quantize(shipping_revenue),
        total_customer_revenue=_quantize(total_customer_revenue),
        product_cost=_quantize(product_cost),
        shipping_cost=_quantize(shipping_cost),
        payment_fees=_quantize(payment_fees),
        discount_amount=discount_amount,
        contribution_profit=contribution_profit,
        contribution_margin=contribution_margin,
        break_even_cpa=_quantize(break_even_cpa),
        break_even_roas=break_even_roas,
        target_cpa=_quantize(target_cpa) if target_cpa is not None else None,
        target_cpa_reason=target_cpa_reason,
    )


def calculate_bundle_economics(
    *,
    bundle_price: Decimal,
    item_costs: list[Decimal],
    quantities: list[int],
) -> BundleEconomics:
    """Bundle economics from its underlying product costs.

    items_cost = sum(quantity * unit_product_cost) across bundle items.
    contribution_profit = bundle_price - items_cost.
    """
    if len(item_costs) != len(quantities):
        raise ValueError("item_costs and quantities must have the same length")

    items_cost = sum(
        (qty * cost for qty, cost in zip(quantities, item_costs, strict=True)), ZERO
    )
    items_cost = _quantize(items_cost)
    contribution_profit = _quantize(bundle_price - items_cost)
    contribution_margin = _divide(contribution_profit, bundle_price)
    contribution_margin = (
        contribution_margin.quantize(Decimal("0.0001")) if contribution_margin is not None else None
    )

    return BundleEconomics(
        bundle_price=_quantize(bundle_price),
        items_cost=items_cost,
        contribution_profit=contribution_profit,
        contribution_margin=contribution_margin,
    )