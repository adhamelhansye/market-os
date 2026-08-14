"""RBAC tests: permissions gate access; the backend is the source of truth."""

import pytest
from conftest import (
    auth_headers,
    create_membership,
    create_organization,
    create_role,
    create_user,
)
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.rbac import ADMIN_PERMISSIONS, MEMBER_PERMISSIONS, VIEWER_PERMISSIONS
from src.db.models import Organization, Role, User


@pytest.fixture
async def rbac_world(session: AsyncSession):
    """One org with owner/admin/member/viewer users and one business."""
    org = await create_organization(session, type="agency")
    owner = await create_user(session, email="owner@example.com")
    admin = await create_user(session, email="admin@example.com")
    member = await create_user(session, email="member@example.com")
    viewer = await create_user(session, email="viewer@example.com")
    await create_user(session, email="outsider@example.com")
    await session.commit()

    roles = {}
    for name, permissions in (
        ("owner", set(ADMIN_PERMISSIONS) | {"org:manage", "members:manage"}),
        ("admin", ADMIN_PERMISSIONS),
        ("member", MEMBER_PERMISSIONS),
        ("viewer", VIEWER_PERMISSIONS),
    ):
        role = await create_role(
            session, name=name, organization_id=org.id, permissions=list(permissions)
        )
        await session.flush()
        roles[name] = role

    for user, role_name in (
        (owner, "owner"),
        (admin, "admin"),
        (member, "member"),
        (viewer, "viewer"),
    ):
        await create_membership(session, user=user, organization=org, role=roles[role_name])
    await session.commit()
    return {
        "org": org,
        "users": {"owner": owner, "admin": admin, "member": member, "viewer": viewer},
    }


async def test_owner_can_read_organization(
    session: AsyncSession, client: AsyncClient, rbac_world
) -> None:
    org: Organization = rbac_world["org"]
    owner: User = rbac_world["users"]["owner"]
    response = await client.get(
        f"/api/v1/organizations/{org.id}",
        headers=await auth_headers(session, owner, org.id),
    )
    assert response.status_code == 200
    assert response.json()["slug"] == org.slug


async def test_viewer_can_read_but_not_write(
    session: AsyncSession, client: AsyncClient, rbac_world
) -> None:
    org: Organization = rbac_world["org"]
    viewer: User = rbac_world["users"]["viewer"]

    org_response = await client.get(
        f"/api/v1/organizations/{org.id}",
        headers=await auth_headers(session, viewer, org.id),
    )
    assert org_response.status_code == 200

    # viewer lacks business:write — but there is no write endpoint yet;
    # prove the permission dependency denies with a direct check below.
    from src.core.tenancy import resolve_tenant

    tenant = await resolve_tenant(session, viewer.id, org.id)
    assert not tenant.has_permission("business:write")


async def test_member_can_list_businesses_without_business_write(
    session: AsyncSession, client: AsyncClient, rbac_world
) -> None:
    org: Organization = rbac_world["org"]
    member: User = rbac_world["users"]["member"]
    response = await client.get(
        "/api/v1/businesses",
        headers=await auth_headers(session, member, org.id),
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_missing_permission_denied_on_organization_detail(
    session: AsyncSession, client: AsyncClient, rbac_world
) -> None:
    """A role without org:read must be rejected by the backend even if the
    frontend hides the button."""
    org: Organization = rbac_world["org"]
    viewer: User = rbac_world["users"]["viewer"]

    # Temporarily strip org:read from the viewer role to simulate a
    # restrictive role configuration.

    role = await session.scalar(select(Role).where(Role.name == "viewer"))
    role.permissions_json = [p for p in role.permissions_json if p != "org:read"]
    await session.commit()

    response = await client.get(
        f"/api/v1/organizations/{org.id}",
        headers=await auth_headers(session, viewer, org.id),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


async def test_list_organizations_returns_all_memberships(
    session: AsyncSession, client: AsyncClient, rbac_world
) -> None:
    org: Organization = rbac_world["org"]
    owner: User = rbac_world["users"]["owner"]
    response = await client.get(
        "/api/v1/organizations",
        headers=await auth_headers(session, owner, org.id),
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["role_name"] == "owner"
    assert "org:manage" in body[0]["permissions"]