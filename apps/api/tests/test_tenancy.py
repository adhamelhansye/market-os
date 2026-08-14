"""Tenant isolation tests: users can never cross organization boundaries."""


import pytest
from conftest import (
    auth_headers,
    create_business,
    create_membership,
    create_organization,
    create_role,
    create_user,
)
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.security import create_access_token


@pytest.fixture
async def two_tenants(session: AsyncSession):
    """Two independent organizations with their own users."""
    org_a = await create_organization(session, name="Tenant A")
    org_b = await create_organization(session, name="Tenant B")
    user_a = await create_user(session, email="a@example.com")
    user_b = await create_user(session, email="b@example.com")
    role_a = await create_role(
        session, name="owner", organization_id=org_a.id, permissions=["org:read", "business:read"]
    )
    role_b = await create_role(
        session, name="owner", organization_id=org_b.id, permissions=["org:read", "business:read"]
    )
    await create_membership(session, user=user_a, organization=org_a, role=role_a)
    await create_membership(session, user=user_b, organization=org_b, role=role_b)
    await session.commit()
    return {"a": (org_a, user_a), "b": (org_b, user_b)}


async def test_cannot_list_other_tenants_organizations(
    session: AsyncSession, client: AsyncClient, two_tenants
) -> None:
    org_a, user_a = two_tenants["a"]
    response = await client.get(
        "/api/v1/organizations",
        headers=await auth_headers(session, user_a, org_a.id),
    )
    assert response.status_code == 200
    assert len(response.json()) == 1  # only tenant A


async def test_cannot_read_other_tenant_organization_detail(
    session: AsyncSession, client: AsyncClient, two_tenants
) -> None:
    org_a, user_a = two_tenants["a"]
    _, org_b = two_tenants["b"][0], two_tenants["b"][1]
    response = await client.get(
        f"/api/v1/organizations/{org_b.id}",
        headers=await auth_headers(session, user_a, org_a.id),
    )
    assert response.status_code == 403


async def test_cannot_use_foreign_organization_id_header(
    session: AsyncSession, client: AsyncClient, two_tenants
) -> None:
    """The X-Organization-Id header is never trusted."""
    org_a, user_a = two_tenants["a"]
    _, org_b = two_tenants["b"][0], two_tenants["b"][1]
    token = create_access_token(user_a.id, get_settings())
    response = await client.get(
        "/api/v1/businesses",
        headers={"Authorization": f"Bearer {token}", "X-Organization-Id": str(org_b.id)},
    )
    assert response.status_code == 403


async def test_suspended_membership_rejected(
    session: AsyncSession, client: AsyncClient, two_tenants
) -> None:
    org_a, user_a = two_tenants["a"]
    from src.db.models import Membership

    membership = await session.scalar(select(Membership).where(Membership.user_id == user_a.id))
    membership.status = "suspended"
    await session.commit()

    response = await client.get(
        "/api/v1/businesses",
        headers=await auth_headers(session, user_a, org_a.id),
    )
    assert response.status_code == 403


async def test_no_active_membership_rejected(session: AsyncSession, client: AsyncClient) -> None:
    org = await create_organization(session)
    user = await create_user(session, email="lonely@example.com")
    await session.commit()

    response = await client.get(
        "/api/v1/businesses",
        headers=await auth_headers(session, user, org.id),
    )
    assert response.status_code == 403


async def test_businesses_are_isolated_between_tenants(
    session: AsyncSession, client: AsyncClient, two_tenants
) -> None:
    org_a, user_a = two_tenants["a"]
    org_b, _ = two_tenants["b"]
    business_b = await create_business(session, organization=org_b)
    await session.commit()

    response = await client.get(
        "/api/v1/businesses",
        headers=await auth_headers(session, user_a, org_a.id),
    )
    assert response.status_code == 200
    assert response.json() == []

    detail = await client.get(
        f"/api/v1/businesses/{business_b.id}",
        headers=await auth_headers(session, user_a, org_a.id),
    )
    assert detail.status_code == 404


async def test_business_detail_within_tenant(
    session: AsyncSession, client: AsyncClient, two_tenants
) -> None:
    org_a, user_a = two_tenants["a"]
    business_a = await create_business(session, organization=org_a)
    await session.commit()

    response = await client.get(
        f"/api/v1/businesses/{business_a.id}",
        headers=await auth_headers(session, user_a, org_a.id),
    )
    assert response.status_code == 200
    assert response.json()["name"] == business_a.name


async def test_missing_organization_header_rejected(
    session: AsyncSession, client: AsyncClient, two_tenants
) -> None:
    _, user_a = two_tenants["a"]
    token = create_access_token(user_a.id, get_settings())
    response = await client.get(
        "/api/v1/businesses", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"