"""Pydantic responses for the economics endpoints.

Money fields are Decimal; the app serializes Decimals as strings
(json_encoders in main.py), so clients never receive floats for money.
"""

import uuid
from datetime import datetime
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


class RevenueSummaryRead(BaseModel):
    """Read-only revenue summary sourced from canonical orders.

    All values are deterministic (pure Decimal aggregation over the orders
    table); no provider numerics or LLM involvement. Returns zero values for
    a business with no synced orders rather than raising.
    """

    business_id: uuid.UUID
    currency: str
    order_count: int
    total_revenue: Decimal
    refunded_revenue: Decimal
    last_30d_revenue: Decimal
    last_30d_orders: int
    last_30d_window_start: datetime


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