"""Pydantic responses for the economics endpoints.

Money fields are Decimal; the app serializes Decimals as strings
(json_encoders in main.py), so clients never receive floats for money.
"""

import uuid
from decimal import Decimal

from pydantic import BaseModel

from src.modules.goals.schemas import GoalRead


class ProductEconomicsRead(BaseModel):
    """Unit economics for one product plus its identity/inventory context."""

    product_id: uuid.UUID
    name: str
    sku: str | None
    status: str
    currency: str
    inventory_quantity: int
    product_revenue: Decimal | None
    shipping_revenue: Decimal | None
    total_customer_revenue: Decimal | None
    product_cost: Decimal
    shipping_cost: Decimal
    payment_fees: Decimal
    discount_amount: Decimal
    contribution_profit: Decimal | None
    contribution_margin: Decimal | None
    break_even_cpa: Decimal | None
    break_even_roas: Decimal | None
    target_cpa: Decimal | None
    target_cpa_reason: str | None


class BundleEconomicsRead(BaseModel):
    bundle_id: uuid.UUID
    name: str
    currency: str
    bundle_price: Decimal
    items_cost: Decimal
    contribution_profit: Decimal
    contribution_margin: Decimal | None


class EconomicsSummaryRead(BaseModel):
    business_id: uuid.UUID
    business_name: str
    currency: str
    active_products: int
    priced_products: int
    average_product_price: Decimal | None
    average_contribution_profit: Decimal | None
    average_contribution_margin: Decimal | None
    average_total_customer_revenue: Decimal | None
    break_even_cpa_range: list[Decimal] | None
    target_cpa: Decimal | None
    target_cpa_reason: str | None
    break_even_roas: Decimal | None
    inventory_value: Decimal | None
    current_goal: GoalRead | None