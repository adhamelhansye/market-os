"""Organization endpoints: list user organizations, view a specific one."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.core.dependencies import (
    CurrentUser,
    DbSession,
    require_org_permission,
)
from src.core.exceptions import NotFoundError
from src.core.tenancy import TenantContext
from src.db.models import Organization
from src.modules.auth.service import list_memberships
from src.schemas.entities import OrganizationRead

router = APIRouter(tags=["organizations"])


class OrganizationSummaryRead(OrganizationRead):
    role_name: str
    permissions: list[str]


@router.get("/organizations", response_model=list[OrganizationSummaryRead])
async def list_organizations(
    user: CurrentUser,
    session: DbSession,
) -> list[OrganizationSummaryRead]:
    memberships = await list_memberships(session, user.id)
    return [
        OrganizationSummaryRead(
            **OrganizationRead.model_validate(org).model_dump(),
            role_name=role.name,
            permissions=role.permissions_json or [],
        )
        for org, role in memberships
    ]


@router.get("/organizations/{organization_id}", response_model=OrganizationRead)
async def get_organization(
    tenant: Annotated[TenantContext, Depends(require_org_permission("org:read"))],
    session: DbSession,
) -> OrganizationRead:
    organization = await session.get(Organization, tenant.organization_id)
    if organization is None:
        raise NotFoundError("Organization not found")
    return OrganizationRead.model_validate(organization)