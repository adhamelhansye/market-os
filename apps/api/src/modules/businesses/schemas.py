"""Pydantic schemas for business records and the business profile."""

import re
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.db.models.business import COUNTRY_CODE_PATTERN, ONBOARDING_STATUSES
from src.schemas.entities import BusinessRead as BaseBusinessRead

_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


class BusinessCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    currency: str = Field(min_length=3, max_length=3)
    timezone: str = Field(min_length=1, max_length=64)
    industry: str | None = Field(default=None, max_length=100)
    description: str | None = None
    country: str | None = Field(default=None, max_length=2)
    website_url: str | None = Field(default=None, max_length=500)
    onboarding_status: str = "not_started"

    @field_validator("currency")
    @classmethod
    def _currency_upper(cls, value: str) -> str:
        value = value.upper()
        if not _CURRENCY_PATTERN.match(value):
            raise ValueError("currency must be a 3-letter code (e.g. USD, EGP)")
        return value

    @field_validator("country")
    @classmethod
    def _country_upper(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        if not re.match(COUNTRY_CODE_PATTERN, value):
            raise ValueError("country must be a 2-letter ISO code (e.g. EG, SA, US)")
        return value

    @field_validator("onboarding_status")
    @classmethod
    def _status_valid(cls, value: str) -> str:
        if value not in ONBOARDING_STATUSES:
            raise ValueError(f"onboarding_status must be one of {ONBOARDING_STATUSES}")
        return value


class BusinessUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    industry: str | None = Field(default=None, max_length=100)
    description: str | None = None
    country: str | None = Field(default=None, max_length=2)
    website_url: str | None = Field(default=None, max_length=500)
    onboarding_status: str | None = None

    @field_validator("currency")
    @classmethod
    def _currency_upper(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.upper()
        if not _CURRENCY_PATTERN.match(value):
            raise ValueError("currency must be a 3-letter code (e.g. USD, EGP)")
        return value

    @field_validator("country")
    @classmethod
    def _country_upper(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        if not re.match(COUNTRY_CODE_PATTERN, value):
            raise ValueError("country must be a 2-letter ISO code (e.g. EG, SA, US)")
        return value

    @field_validator("onboarding_status")
    @classmethod
    def _status_valid(cls, value: str | None) -> str | None:
        if value is not None and value not in ONBOARDING_STATUSES:
            raise ValueError(f"onboarding_status must be one of {ONBOARDING_STATUSES}")
        return value


class BusinessRead(BaseBusinessRead):
    description: str | None
    country: str | None
    website_url: str | None


class BusinessProfileWrite(BaseModel):
    model_config = ConfigDict(extra="ignore")

    description: str | None = None
    industry: str | None = Field(default=None, max_length=100)
    business_model: str | None = Field(default=None, max_length=50)
    target_market: str | None = Field(default=None, max_length=255)
    brand_positioning: str | None = None
    average_order_value: Decimal | None = Field(default=None, ge=0)
    primary_customer_type: str | None = Field(default=None, max_length=50)
    brand_voice: str | None = Field(default=None, max_length=50)


class BusinessProfileRead(BusinessProfileWrite):
    business_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
