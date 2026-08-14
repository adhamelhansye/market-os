"""Pydantic schemas for business goals."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_CURRENCY_PATTERN = r"^[A-Z]{3}$"


class GoalCreate(BaseModel):
    period_start: datetime
    period_end: datetime
    target_revenue: Decimal | None = Field(default=None, ge=0)
    target_profit: Decimal | None = Field(default=None, ge=0)
    ad_budget: Decimal | None = Field(default=None, gt=0)
    maximum_cpa: Decimal | None = Field(default=None, gt=0)
    target_roas: Decimal | None = Field(default=None, gt=0)
    currency: str = Field(min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def _currency_upper(cls, value: str) -> str:
        value = value.upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("currency must be a 3-letter code (e.g. USD, EGP)")
        return value

    @model_validator(mode="after")
    def _period_valid(self) -> "GoalCreate":
        if self.period_end <= self.period_start:
            raise ValueError("period_end must be after period_start")
        return self


class GoalUpdate(BaseModel):
    period_start: datetime | None = None
    period_end: datetime | None = None
    target_revenue: Decimal | None = Field(default=None, ge=0)
    target_profit: Decimal | None = Field(default=None, ge=0)
    ad_budget: Decimal | None = Field(default=None, gt=0)
    maximum_cpa: Decimal | None = Field(default=None, gt=0)
    target_roas: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def _currency_upper(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("currency must be a 3-letter code (e.g. USD, EGP)")
        return value

    @model_validator(mode="after")
    def _period_valid(self) -> "GoalUpdate":
        if (
            self.period_start is not None
            and self.period_end is not None
            and self.period_end <= self.period_start
        ):
            raise ValueError("period_end must be after period_start")
        return self


class GoalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    period_start: datetime
    period_end: datetime
    target_revenue: Decimal | None
    target_profit: Decimal | None
    ad_budget: Decimal | None
    maximum_cpa: Decimal | None
    target_roas: Decimal | None
    currency: str
    created_at: datetime
    updated_at: datetime