"""Business CRUD, authorization and cross-tenant isolation tests."""

import pytest
from conftest import create_tenant
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def tenant(session: AsyncSession) -> dict:
    return await create_tenant(session)


async def test_create_business(client: AsyncClient, tenant) -> None:
    response = await client.post(
        "/api/v1/businesses",
        headers=tenant["headers"],
        json={
            "name": "Acme Store",
            "currency": "egp",
            "timezone": "Africa/Cairo",
            "industry": "ecommerce",
            "country": "eg",
            "description": "A store",
            "onboarding_status": "in_progress",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Acme Store"
    assert body["currency"] == "EGP"  # normalized to upper
    assert body["country"] == "EG"
    assert body["onboarding_status"] == "in_progress"
    assert body["organization_id"] == str(tenant["org"].id)


async def test_create_business_validates_required_fields(
    client: AsyncClient, tenant
) -> None:
    response = await client.post(
        "/api/v1/businesses",
        headers=tenant["headers"],
        json={"name": "Acme", "currency": "US", "timezone": ""},
    )
    assert response.status_code == 422  # invalid currency + empty timezone


async def test_update_business(client: AsyncClient, tenant) -> None:
    business_id = tenant["business"].id
    response = await client.patch(
        f"/api/v1/businesses/{business_id}",
        headers=tenant["headers"],
        json={"name": "Renamed Store", "website_url": "https://example.com"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed Store"
    assert response.json()["website_url"] == "https://example.com"


async def test_update_business_foreign_tenant_not_found(
    session: AsyncSession, client: AsyncClient, tenant
) -> None:
    foreign = await create_tenant(session)
    response = await client.patch(
        f"/api/v1/businesses/{tenant['business'].id}",
        headers=foreign["headers"],
        json={"name": "Hacked"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_business_detail_foreign_tenant_not_found(
    session: AsyncSession, client: AsyncClient, tenant
) -> None:
    foreign = await create_tenant(session)
    response = await client.get(
        f"/api/v1/businesses/{tenant['business'].id}", headers=foreign["headers"]
    )
    assert response.status_code == 404


async def test_agency_can_read_and_update_managed_business(
    session: AsyncSession, client: AsyncClient, tenant
) -> None:
    agency = await create_tenant(
        session, org_type="agency", managed_by=tenant["org"]
    )
    # agency["business"] is a business owned by the agency itself; the
    # managed business is tenant's. Reuse tenant's business as managed.
    managed = await create_tenant(
        session,
        managed_by=agency["org"],
        business_name="Managed Biz",
    )
    response = await client.get(
        f"/api/v1/businesses/{managed['business'].id}", headers=agency["headers"]
    )
    assert response.status_code == 200

    update = await client.patch(
        f"/api/v1/businesses/{managed['business'].id}",
        headers=agency["headers"],
        json={"name": "Managed Renamed"},
    )
    assert update.status_code == 200
    assert update.json()["name"] == "Managed Renamed"


async def test_business_list_requires_auth(client: AsyncClient, tenant) -> None:
    response = await client.get("/api/v1/businesses")
    assert response.status_code == 401


async def test_business_write_requires_permission(
    session: AsyncSession, client: AsyncClient, tenant
) -> None:
    """A viewer (business:read only) cannot create businesses."""
    viewer = await create_tenant(
        session, permissions=["org:read", "business:read"]
    )
    response = await client.post(
        "/api/v1/businesses",
        headers=viewer["headers"],
        json={"name": "X", "currency": "USD", "timezone": "UTC"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"