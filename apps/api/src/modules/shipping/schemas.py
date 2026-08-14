"""Pydantic schemas for shipping rules."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ShippingRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    country: str = Field(min_length=1, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    method: str = Field(min_length=1, max_length=50)
    cost: Decimal = Field(default=Decimal("0"), ge=0)
    customer_price: Decimal = Field(default=Decimal("0"), ge=0)
    free_shipping_threshold: Decimal | None = Field(default=None, ge=0)
    is_default: bool = False
    active: bool = True


class ShippingRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    country: str | None = Field(default=None, min_length=1, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    method: str | None = Field(default=None, min_length=1, max_length=50)
    cost: Decimal | None = Field(default=None, ge=0)
    customer_price: Decimal | None = Field(default=None, ge=0)
    free_shipping_threshold: Decimal | None = Field(default=None, ge=0)
    is_default: bool | None = None
    active: bool | None = None

    @model_validator(mode="after")
    def _coalesce_threshold(self) -> "ShippingRuleUpdate":
        # None means "not provided", so a threshold can only be cleared via
        # the dedicated API contract on the write path; keep as-is.
        return self


class ShippingRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    name: str
    country: str
    region: str | None
    method: str
    cost: Decimal
    customer_price: Decimal
    free_shipping_threshold: Decimal | None
    is_default: bool
    active: bool
    created_at: datetime
    updated_at: datetime