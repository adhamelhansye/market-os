"""Bundles: CRUD, underlying product cost calculation and margin."""

from decimal import Decimal

import pytest
from conftest import create_tenant
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def tenant(session: AsyncSession) -> dict:
    return await create_tenant(session)


async def _product_with_cost(client, tenant, name: str, price: str, cogs: str) -> str:
    created = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/products",
        headers=tenant["headers"],
        json={"name": name, "currency": "USD"},
    )
    product_id = created.json()["id"]
    await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/products/{product_id}/prices",
        headers=tenant["headers"],
        json={"price": price, "currency": "USD", "effective_from": "2026-01-01T00:00:00Z"},
    )
    await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/products/{product_id}/costs",
        headers=tenant["headers"],
        json={"cogs": cogs, "packaging_cost": "5.00", "effective_from": "2026-01-01T00:00:00Z"},
    )
    return product_id


async def _create_bundle(
    client, tenant, product_ids: list[str], price: str = "200.00", **overrides
) -> dict:
    response = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/bundles",
        headers=tenant["headers"],
        json={
            "name": "Starter Bundle",
            "price": price,
            "currency": "USD",
            "items": [
                {"product_id": product_ids[0], "quantity": 1},
                {"product_id": product_ids[1], "quantity": 2},
            ],
            **overrides,
        },
    )
    return response


async def test_create_and_read_bundle(client: AsyncClient, tenant) -> None:
    alpha = await _product_with_cost(client, tenant, "Alpha", "100.00", "30.00")
    beta = await _product_with_cost(client, tenant, "Beta", "200.00", "50.00")

    response = await _create_bundle(client, tenant, [alpha, beta])
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Starter Bundle"
    assert body["price"] == "200.00"
    assert len(body["items"]) == 2
    assert {i["product_id"] for i in body["items"]} == {alpha, beta}
    assert {i["quantity"] for i in body["items"]} == {1, 2}


async def test_bundle_requires_products_from_same_business(
    session: AsyncSession, client: AsyncClient, tenant
) -> None:
    other = await create_tenant(session)
    foreign_product = await _product_with_cost(
        client, other, "Foreign", "10.00", "1.00"
    )
    own = await _product_with_cost(client, tenant, "Own", "10.00", "1.00")

    response = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/bundles",
        headers=tenant["headers"],
        json={
            "name": "Bad Bundle",
            "price": "50.00",
            "currency": "USD",
            "items": [
                {"product_id": own, "quantity": 1},
                {"product_id": foreign_product, "quantity": 1},
            ],
        },
    )
    assert response.status_code == 404


async def test_bundle_economics_cost_and_margin(client: AsyncClient, tenant) -> None:
    alpha = await _product_with_cost(client, tenant, "Alpha", "100.00", "30.00")
    beta = await _product_with_cost(client, tenant, "Beta", "200.00", "50.00")

    created = await _create_bundle(client, tenant, [alpha, beta])
    bundle_id = created.json()["id"]

    economics = await client.get(
        f"/api/v1/businesses/{tenant['business'].id}/bundles/{bundle_id}/economics",
        headers=tenant["headers"],
    )
    assert economics.status_code == 200
    body = economics.json()
    # Alpha: 30 + 5 packaging = 35; Beta: 50 + 5 = 55 x2 = 110; total 145
    assert Decimal(body["items_cost"]) == Decimal("145.00")
    assert Decimal(body["bundle_price"]) == Decimal("200.00")
    assert Decimal(body["contribution_profit"]) == Decimal("55.00")
    assert Decimal(body["contribution_margin"]) == Decimal("0.2750")


async def test_update_bundle_items(client: AsyncClient, tenant) -> None:
    alpha = await _product_with_cost(client, tenant, "Alpha", "100.00", "30.00")
    beta = await _product_with_cost(client, tenant, "Beta", "200.00", "50.00")

    created = await _create_bundle(client, tenant, [alpha, beta])
    bundle_id = created.json()["id"]

    updated = await client.patch(
        f"/api/v1/businesses/{tenant['business'].id}/bundles/{bundle_id}",
        headers=tenant["headers"],
        json={
            "name": "Expanded Bundle",
            "items": [{"product_id": alpha, "quantity": 3}],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Expanded Bundle"
    assert len(updated.json()["items"]) == 1
    assert updated.json()["items"][0]["quantity"] == 3


async def test_delete_bundle(client: AsyncClient, tenant) -> None:
    alpha = await _product_with_cost(client, tenant, "Alpha", "100.00", "30.00")
    beta = await _product_with_cost(client, tenant, "Beta", "200.00", "50.00")
    created = await _create_bundle(client, tenant, [alpha, beta])
    bundle_id = created.json()["id"]

    deleted = await client.delete(
        f"/api/v1/businesses/{tenant['business'].id}/bundles/{bundle_id}",
        headers=tenant["headers"],
    )
    assert deleted.status_code == 204

    gone = await client.get(
        f"/api/v1/businesses/{tenant['business'].id}/bundles/{bundle_id}",
        headers=tenant["headers"],
    )
    assert gone.status_code == 404


async def test_bundle_cross_tenant_denied(
    session: AsyncSession, client: AsyncClient, tenant
) -> None:
    alpha = await _product_with_cost(client, tenant, "Alpha", "100.00", "30.00")
    beta = await _product_with_cost(client, tenant, "Beta", "200.00", "50.00")
    created = await _create_bundle(client, tenant, [alpha, beta])
    bundle_id = created.json()["id"]

    foreign = await create_tenant(session)
    response = await client.get(
        f"/api/v1/businesses/{tenant['business'].id}/bundles/{bundle_id}",
        headers=foreign["headers"],
    )
    assert response.status_code == 404