"""Authentication request/response schemas."""

import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from src.schemas.entities import OrganizationRead, UserRead


class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    organization_name: str = Field(min_length=1, max_length=255)
    organization_type: Literal["agency", "business"] = "business"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AuthResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserRead


class RefreshResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class MembershipRead(BaseModel):
    organization: OrganizationRead
    role_name: str
    permissions: list[str]


class MeResponse(BaseModel):
    user: UserRead
    active_organization_id: uuid.UUID | None = None
    memberships: list[MembershipRead]