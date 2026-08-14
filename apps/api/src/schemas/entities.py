"""Pydantic v2 responses for core entities. The API contract is explicit:
internal ORM models are never exposed directly."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserRead(OrmModel):
    id: uuid.UUID
    email: EmailStr
    name: str
    locale: str
    created_at: datetime


class OrganizationRead(OrmModel):
    id: uuid.UUID
    name: str
    slug: str
    type: str
    locale_default: str
    created_at: datetime


class BusinessRead(OrmModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    managed_by_organization_id: uuid.UUID | None
    name: str
    industry: str | None
    timezone: str
    currency: str
    onboarding_status: str
    created_at: datetime