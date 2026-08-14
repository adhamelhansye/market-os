"""Pydantic schemas for products, price history, cost history and inventory."""

import re
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")

PRODUCT_STATUSES = ("active", "inactive", "archived")
INVENTORY_SOURCES = ("manual", "system", "shopify")


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    sku: str | None = Field(default=None, max_length=100)
    description: str | None = None
    status: str = "active"
    currency: str = Field(default="USD", max_length=3)

    @field_validator("status")
    @classmethod
    def _status_valid(cls, value: str) -> str:
        if value not in PRODUCT_STATUSES:
            raise ValueError(f"status must be one of {PRODUCT_STATUSES}")
        return value

    @field_validator("currency")
    @classmethod
    def _currency_upper(cls, value: str) -> str:
        value = value.upper()
        if not _CURRENCY_PATTERN.match(value):
            raise ValueError("currency must be a 3-letter code (e.g. USD, EGP)")
        return value

    @field_validator("sku")
    @classmethod
    def _sku_trim(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    sku: str | None = Field(default=None, max_length=100)
    description: str | None = None
    status: str | None = None
    currency: str | None = Field(default=None, max_length=3)

    @field_validator("status")
    @classmethod
    def _status_valid(cls, value: str | None) -> str | None:
        if value is not None and value not in PRODUCT_STATUSES:
            raise ValueError(f"status must be one of {PRODUCT_STATUSES}")
        return value

    @field_validator("currency")
    @classmethod
    def _currency_upper(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.upper()
        if not _CURRENCY_PATTERN.match(value):
            raise ValueError("currency must be a 3-letter code (e.g. USD, EGP)")
        return value

    @field_validator("sku")
    @classmethod
    def _sku_trim(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    sku: str | None
    name: str
    description: str | None
    status: str
    currency: str
    created_at: datetime
    updated_at: datetime


class ProductDetailRead(ProductRead):
    """Product plus its current unit economics and inventory quantity."""

    inventory_quantity: int = 0
    active_price: Decimal | None = None
    contribution_profit: Decimal | None = None
    contribution_margin: Decimal | None = None


class ProductPriceCreate(BaseModel):
    price: Decimal = Field(ge=0)
    currency: str = Field(max_length=3)
    effective_from: datetime
    effective_to: datetime | None = None

    @field_validator("currency")
    @classmethod
    def _currency_upper(cls, value: str) -> str:
        value = value.upper()
        if not _CURRENCY_PATTERN.match(value):
            raise ValueError("currency must be a 3-letter code (e.g. USD, EGP)")
        return value

    @model_validator(mode="after")
    def _period_valid(self) -> "ProductPriceCreate":
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be after effective_from")
        return self


class ProductPriceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    price: Decimal
    currency: str
    effective_from: datetime
    effective_to: datetime | None
    created_at: datetime


class ProductCostCreate(BaseModel):
    cogs: Decimal = Field(default=Decimal("0"), ge=0)
    packaging_cost: Decimal = Field(default=Decimal("0"), ge=0)
    payment_fee_fixed: Decimal = Field(default=Decimal("0"), ge=0)
    payment_fee_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    effective_from: datetime
    effective_to: datetime | None = None

    @model_validator(mode="after")
    def _period_valid(self) -> "ProductCostCreate":
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be after effective_from")
        return self


class ProductCostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    cogs: Decimal
    packaging_cost: Decimal
    payment_fee_fixed: Decimal
    payment_fee_percent: Decimal
    effective_from: datetime
    effective_to: datetime | None
    created_at: datetime


class InventorySet(BaseModel):
    """Absolute quantity; replaces the current inventory."""

    quantity: int = Field(ge=0)


class InventoryAdjust(BaseModel):
    """Signed delta applied to the current quantity."""

    quantity_delta: int


class InventoryRead(BaseModel):
    product_id: uuid.UUID
    quantity: int
    source: str
    recorded_at: datetime