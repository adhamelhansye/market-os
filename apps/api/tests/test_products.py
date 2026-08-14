"""Product CRUD, SKU uniqueness, archiving, cross-business and cross-tenant
access tests."""


import pytest
from conftest import create_tenant
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def tenant(session: AsyncSession) -> dict:
    return await create_tenant(session)


async def _create_product(client, tenant, **overrides):
    payload = {"name": "Widget", "currency": "USD", **overrides}
    return await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/products",
        headers=tenant["headers"],
        json=payload,
    )


async def test_create_and_get_product(client: AsyncClient, tenant) -> None:
    created = await _create_product(client, tenant, sku="WID-1", description="A widget")
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Widget"
    assert body["sku"] == "WID-1"
    assert body["status"] == "active"
    assert body["currency"] == "USD"
    assert body["business_id"] == str(tenant["business"].id)

    fetched = await client.get(
        f"/api/v1/businesses/{tenant['business'].id}/products/{body['id']}",
        headers=tenant["headers"],
    )
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


async def test_update_product(client: AsyncClient, tenant) -> None:
    created = await _create_product(client, tenant)
    product_id = created.json()["id"]
    updated = await client.patch(
        f"/api/v1/businesses/{tenant['business'].id}/products/{product_id}",
        headers=tenant["headers"],
        json={"name": "Renamed", "status": "inactive"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed"
    assert updated.json()["status"] == "inactive"


async def test_archive_product(client: AsyncClient, tenant) -> None:
    created = await _create_product(client, tenant)
    product_id = created.json()["id"]
    response = await client.delete(
        f"/api/v1/businesses/{tenant['business'].id}/products/{product_id}",
        headers=tenant["headers"],
    )
    assert response.status_code == 204

    fetched = await client.get(
        f"/api/v1/businesses/{tenant['business'].id}/products/{product_id}",
        headers=tenant["headers"],
    )
    assert fetched.json()["status"] == "archived"


async def test_duplicate_sku_rejected(
    session: AsyncSession, client: AsyncClient, tenant
) -> None:
    await _create_product(client, tenant, sku="DUP-1")
    duplicate = await _create_product(client, tenant, sku="DUP-1")
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "conflict"

    # Same SKU in a different business is allowed.
    other = await create_tenant(session)
    other_product = await client.post(
        f"/api/v1/businesses/{other['business'].id}/products",
        headers=other["headers"],
        json={"name": "Other", "sku": "DUP-1", "currency": "USD"},
    )
    assert other_product.status_code == 201


async def test_duplicate_sku_across_businesses_allowed(
    session: AsyncSession, client: AsyncClient, tenant
) -> None:
    await _create_product(client, tenant, sku="DUP-2")
    other = await create_tenant(session)
    other_product = await client.post(
        f"/api/v1/businesses/{other['business'].id}/products",
        headers=other["headers"],
        json={"name": "Other", "sku": "DUP-2", "currency": "USD"},
    )
    assert other_product.status_code == 201


async def test_cross_business_product_access_denied(
    session: AsyncSession, client: AsyncClient, tenant
) -> None:
    other = await create_tenant(session)
    created = await _create_product(client, tenant)
    product_id = created.json()["id"]

    # The other tenant's business id + our product id: product belongs to a
    # different business -> 404.
    response = await client.get(
        f"/api/v1/businesses/{other['business'].id}/products/{product_id}",
        headers=other["headers"],
    )
    assert response.status_code == 404


async def test_cross_tenant_product_access_denied(
    session: AsyncSession, client: AsyncClient, tenant
) -> None:
    foreign = await create_tenant(session)
    created = await _create_product(client, tenant)
    product_id = created.json()["id"]

    response = await client.get(
        f"/api/v1/businesses/{tenant['business'].id}/products/{product_id}",
        headers=foreign["headers"],
    )
    assert response.status_code == 404


async def test_agency_access_to_client_products(
    session: AsyncSession, client: AsyncClient, tenant
) -> None:
    agency = await create_tenant(session, org_type="agency")
    client_biz = await create_tenant(session, managed_by=agency["org"])
    await client.post(
        f"/api/v1/businesses/{client_biz['business'].id}/products",
        headers=client_biz["headers"],
        json={"name": "Client Widget", "currency": "USD"},
    )

    products = await client.get(
        f"/api/v1/businesses/{client_biz['business'].id}/products",
        headers=agency["headers"],
    )
    assert products.status_code == 200
    assert len(products.json()) == 1


async def test_product_list_includes_economics(
    client: AsyncClient, tenant
) -> None:
    created = await _create_product(client, tenant)
    product_id = created.json()["id"]
    await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/products/{product_id}/prices",
        headers=tenant["headers"],
        json={"price": "100.00", "currency": "USD", "effective_from": "2026-01-01T00:00:00Z"},
    )
    await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/products/{product_id}/costs",
        headers=tenant["headers"],
        json={"cogs": "40.00", "effective_from": "2026-01-01T00:00:00Z"},
    )
    await client.put(
        f"/api/v1/businesses/{tenant['business'].id}/products/{product_id}/inventory",
        headers=tenant["headers"],
        json={"quantity": 25},
    )

    products = await client.get(
        f"/api/v1/businesses/{tenant['business'].id}/products",
        headers=tenant["headers"],
    )
    [row] = products.json()
    assert row["active_price"] == "100.00"
    assert row["contribution_profit"] == "60.00"
    assert row["inventory_quantity"] == 25


async def test_invalid_product_status_rejected(client: AsyncClient, tenant) -> None:
    response = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/products",
        headers=tenant["headers"],
        json={"name": "Widget", "status": "bogus", "currency": "USD"},
    )
    assert response.status_code == 422