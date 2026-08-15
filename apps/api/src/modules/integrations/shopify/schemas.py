"""Shopify API response schemas (REST Admin API).

Only the fields needed by Phase 2A. Pydantic validation here is the defense
against malformed provider payloads: a payload that fails to parse becomes
a ProviderDataError instead of a crash. Money stays as strings (Shopify
serializes prices as strings); conversion to Decimal happens in the mapper.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ShopResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    myshopify_domain: str
    currency: str = "USD"


class VariantResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    sku: str | None = None
    price: str = "0"
    inventory_quantity: int | None = None
    inventory_item_id: int | None = None
    title: str | None = None


class ProductResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    title: str
    status: str = "active"
    variants: list[VariantResponse] = Field(default_factory=list)
    updated_at: datetime | None = None

    @field_validator("status")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.lower()


class CustomerResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    email: str | None = None
    updated_at: datetime | None = None


class LineItemResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    product_id: int | None = None
    variant_id: int | None = None
    quantity: int = 0
    price: str = "0"
    total_discount: str = "0"
    name: str | None = None


class ShippingLineResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    price: str = "0"


class OrderResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    currency: str = "USD"
    subtotal_price: str = "0"
    total_discounts: str = "0"
    total_shipping: str | None = None
    total_tax: str | None = None
    total_price: str = "0"
    financial_status: str = "pending"
    fulfillment_status: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    customer: CustomerResponse | None = None
    line_items: list[LineItemResponse] = Field(default_factory=list)
    shipping_lines: list[ShippingLineResponse] = Field(default_factory=list)


class InventoryLevelResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    inventory_item_id: int
    available: int = 0
    location_id: int | None = None


class TokenExchangeResponse(BaseModel):
    """POST /admin/oauth/access_token response."""

    model_config = ConfigDict(extra="allow")

    access_token: str = Field(min_length=1)
    scope: str = ""
