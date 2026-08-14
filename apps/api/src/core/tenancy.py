"""Application-level tenant isolation.

Every authenticated request resolves a TenantContext describing the current
organization and the user's role permissions within it. Business resources
are additionally validated against the agency/business access rules.

Frontend-supplied organization/business ids are never trusted; membership
and access are always re-validated against the database.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError, PermissionDeniedError
from src.db.models import Business, Membership, Organization, Role


@dataclass(frozen=True)
class TenantContext:
    user_id: uuid.UUID
    organization_id: uuid.UUID
    organization_slug: str
    organization_type: str
    organization_name: str
    role_name: str
    permissions: frozenset[str]

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions


async def resolve_tenant(
    session: AsyncSession,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> TenantContext:
    """Loads the active membership for (user, organization) and its role.

    Raises PermissionDeniedError when the user has no active membership.
    """
    membership = await session.scalar(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
        )
    )
    if membership is None or membership.status != "active":
        raise PermissionDeniedError("You do not have access to this organization")

    organization = await session.get(Organization, organization_id)
    role = await session.get(Role, membership.role_id)
    if organization is None or role is None:
        raise PermissionDeniedError("You do not have access to this organization")

    permissions = frozenset(role.permissions_json or [])
    return TenantContext(
        user_id=user_id,
        organization_id=organization_id,
        organization_slug=organization.slug,
        organization_type=organization.type,
        organization_name=organization.name,
        role_name=role.name,
        permissions=permissions,
    )


async def can_access_business(
    session: AsyncSession,
    organization_id: uuid.UUID,
    business_id: uuid.UUID,
) -> Business | None:
    """Returns the business only when the current organization may access it.

    Access rules:
      - the current organization owns the business (business.organization_id), or
      - the current organization manages it (business.managed_by_organization_id).
    """
    business = await session.get(Business, business_id)
    if business is None:
        return None
    if business.organization_id == organization_id:
        return business
    if business.managed_by_organization_id == organization_id:
        return business
    return None


async def require_business_access(
    session: AsyncSession,
    organization_id: uuid.UUID,
    business_id: uuid.UUID,
) -> Business:
    business = await can_access_business(session, organization_id, business_id)
    if business is None:
        raise NotFoundError("Business not found")
    return business