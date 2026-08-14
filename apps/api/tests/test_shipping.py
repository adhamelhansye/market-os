"""Shipping rules: actual cost vs customer price, free shipping, default
rule uniqueness."""

import pytest
from conftest import create_tenant
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def tenant(session: AsyncSession) -> dict:
    return await create_tenant(session)


async def test_create_shipping_rule(client: AsyncClient, tenant) -> None:
    response = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/shipping-rules",
        headers=tenant["headers"],
        json={
            "name": "Egypt Standard",
            "country": "Egypt",
            "method": "standard",
            "cost": "50.00",
            "customer_price": "50.00",
            "is_default": True,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["cost"] == "50.00"
    assert body["customer_price"] == "50.00"
    assert body["is_default"] is True


async def test_free_shipping_rule(client: AsyncClient, tenant) -> None:
    response = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/shipping-rules",
        headers=tenant["headers"],
        json={
            "name": "KSA Free",
            "country": "Saudi Arabia",
            "method": "free",
            "cost": "20.00",
            "customer_price": "0.00",
            "free_shipping_threshold": "150.00",
        },
    )
    assert response.status_code == 201
    assert response.json()["customer_price"] == "0.00"


async def test_only_one_default_rule_per_business(
    client: AsyncClient, tenant
) -> None:
    first = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/shipping-rules",
        headers=tenant["headers"],
        json={
            "name": "Default One",
            "country": "Egypt",
            "method": "standard",
            "cost": "10.00",
            "customer_price": "10.00",
            "is_default": True,
        },
    )
    assert first.status_code == 201
    second = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/shipping-rules",
        headers=tenant["headers"],
        json={
            "name": "Default Two",
            "country": "Egypt",
            "method": "express",
            "cost": "20.00",
            "customer_price": "20.00",
            "is_default": True,
        },
    )
    assert second.status_code == 201

    rules = await client.get(
        f"/api/v1/businesses/{tenant['business'].id}/shipping-rules",
        headers=tenant["headers"],
    )
    defaults = [r for r in rules.json() if r["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["name"] == "Default Two"


async def test_update_rule_and_validation(client: AsyncClient, tenant) -> None:
    created = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/shipping-rules",
        headers=tenant["headers"],
        json={
            "name": "Egypt Standard",
            "country": "Egypt",
            "method": "standard",
            "cost": "50.00",
            "customer_price": "50.00",
        },
    )
    rule_id = created.json()["id"]

    updated = await client.patch(
        f"/api/v1/businesses/{tenant['business'].id}/shipping-rules/{rule_id}",
        headers=tenant["headers"],
        json={"customer_price": "0.00", "is_default": True},
    )
    assert updated.status_code == 200
    assert updated.json()["customer_price"] == "0.00"
    assert updated.json()["is_default"] is True

    negative = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/shipping-rules",
        headers=tenant["headers"],
        json={
            "name": "Bad",
            "country": "Egypt",
            "method": "standard",
            "cost": "-5.00",
            "customer_price": "0.00",
        },
    )
    assert negative.status_code == 422


async def test_delete_rule(client: AsyncClient, tenant) -> None:
    created = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/shipping-rules",
        headers=tenant["headers"],
        json={
            "name": "Temp",
            "country": "Egypt",
            "method": "standard",
            "cost": "10.00",
            "customer_price": "10.00",
        },
    )
    rule_id = created.json()["id"]
    deleted = await client.delete(
        f"/api/v1/businesses/{tenant['business'].id}/shipping-rules/{rule_id}",
        headers=tenant["headers"],
    )
    assert deleted.status_code == 204

    rules = await client.get(
        f"/api/v1/businesses/{tenant['business'].id}/shipping-rules",
        headers=tenant["headers"],
    )
    assert rules.json() == []


async def test_shipping_rule_cross_tenant_denied(
    session: AsyncSession, client: AsyncClient, tenant
) -> None:
    foreign = await create_tenant(session)
    response = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/shipping-rules",
        headers=foreign["headers"],
        json={
            "name": "Nope",
            "country": "Egypt",
            "method": "standard",
            "cost": "10.00",
            "customer_price": "10.00",
        },
    )
    assert response.status_code == 404