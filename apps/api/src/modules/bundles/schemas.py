"""Pydantic schemas for bundles."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_CURRENCY_PATTERN = r"^[A-Z]{3}$"


class BundleItemIn(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(ge=1)


class BundleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    price: Decimal = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    active: bool = True
    items: list[BundleItemIn] = Field(min_length=1)

    @field_validator("currency")
    @classmethod
    def _currency_upper(cls, value: str) -> str:
        value = value.upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("currency must be a 3-letter code (e.g. USD, EGP)")
        return value


class BundleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    active: bool | None = None
    items: list[BundleItemIn] | None = None

    @field_validator("currency")
    @classmethod
    def _currency_upper(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("currency must be a 3-letter code (e.g. USD, EGP)")
        return value


class BundleItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bundle_id: uuid.UUID
    product_id: uuid.UUID
    quantity: int


class BundleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    name: str
    description: str | None
    price: Decimal
    currency: str
    active: bool
    created_at: datetime
    updated_at: datetime
    items: list[BundleItemRead]