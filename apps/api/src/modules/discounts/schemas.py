"""Pydantic schemas for discounts."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DISCOUNT_TYPES = ("percentage", "fixed_amount")


class DiscountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: str
    value: Decimal = Field(gt=0)
    minimum_order_value: Decimal | None = Field(default=None, ge=0)
    maximum_discount: Decimal | None = Field(default=None, gt=0)
    starts_at: datetime
    ends_at: datetime
    active: bool = True

    @model_validator(mode="after")
    def _valid(self) -> "DiscountCreate":
        if self.type not in DISCOUNT_TYPES:
            raise ValueError(f"type must be one of {DISCOUNT_TYPES}")
        if self.type == "percentage" and self.value > Decimal("100"):
            raise ValueError("a percentage discount cannot exceed 100%")
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class DiscountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    type: str | None = None
    value: Decimal | None = Field(default=None, gt=0)
    minimum_order_value: Decimal | None = Field(default=None, ge=0)
    maximum_discount: Decimal | None = Field(default=None, gt=0)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    active: bool | None = None

    @model_validator(mode="after")
    def _valid(self) -> "DiscountUpdate":
        if self.type is not None and self.type not in DISCOUNT_TYPES:
            raise ValueError(f"type must be one of {DISCOUNT_TYPES}")
        if (
            self.type == "percentage"
            and self.value is not None
            and self.value > Decimal("100")
        ):
            raise ValueError("a percentage discount cannot exceed 100%")
        if (
            self.starts_at is not None
            and self.ends_at is not None
            and self.ends_at <= self.starts_at
        ):
            raise ValueError("ends_at must be after starts_at")
        return self


class DiscountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    name: str
    type: str
    value: Decimal
    minimum_order_value: Decimal | None
    maximum_discount: Decimal | None
    starts_at: datetime
    ends_at: datetime
    active: bool
    created_at: datetime
    updated_at: datetime