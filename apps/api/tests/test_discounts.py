"""Discounts: percentage/fixed, limits, active dates."""

import pytest
from conftest import create_tenant
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def tenant(session: AsyncSession) -> dict:
    return await create_tenant(session)


def _iso(month: int, day: int) -> str:
    return f"2026-{month:02d}-{day:02d}T00:00:00Z"


async def _create_discount(client, tenant, **overrides):
    payload = {
        "name": "Launch 10%",
        "type": "percentage",
        "value": "10",
        "starts_at": _iso(1, 1),
        "ends_at": _iso(12, 31),
        **overrides,
    }
    return await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/discounts",
        headers=tenant["headers"],
        json=payload,
    )


async def test_create_percentage_discount(client: AsyncClient, tenant) -> None:
    response = await _create_discount(client, tenant)
    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "percentage"
    assert body["value"] == "10.00"
    assert body["active"] is True


async def test_create_fixed_discount(client: AsyncClient, tenant) -> None:
    response = await _create_discount(
        client, tenant,
        name="Fixed 15",
        type="fixed_amount",
        value="15.00",
        minimum_order_value="100.00",
        maximum_discount="25.00",
    )
    assert response.status_code == 201
    assert response.json()["value"] == "15.00"
    assert response.json()["minimum_order_value"] == "100.00"


async def test_discount_validation(client: AsyncClient, tenant) -> None:
    over_100 = await _create_discount(client, tenant, value="101")
    assert over_100.status_code == 422

    inverted = await _create_discount(
        client, tenant, starts_at=_iso(12, 1), ends_at=_iso(1, 1)
    )
    assert inverted.status_code == 422

    bad_type = await _create_discount(client, tenant, type="percent")
    assert bad_type.status_code == 422

    zero_value = await _create_discount(client, tenant, value="0")
    assert zero_value.status_code == 422


async def test_update_discount(client: AsyncClient, tenant) -> None:
    created = await _create_discount(client, tenant)
    discount_id = created.json()["id"]
    updated = await client.patch(
        f"/api/v1/businesses/{tenant['business'].id}/discounts/{discount_id}",
        headers=tenant["headers"],
        json={"active": False, "value": "15"},
    )
    assert updated.status_code == 200
    assert updated.json()["active"] is False
    assert updated.json()["value"] == "15.00"


async def test_discounts_list(client: AsyncClient, tenant) -> None:
    await _create_discount(client, tenant)
    await _create_discount(
        client, tenant, name="Summer", type="fixed_amount", value="20.00"
    )
    response = await client.get(
        f"/api/v1/businesses/{tenant['business'].id}/discounts",
        headers=tenant["headers"],
    )
    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_discount_cross_tenant_denied(
    session: AsyncSession, client: AsyncClient, tenant
) -> None:
    foreign = await create_tenant(session)
    response = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/discounts",
        headers=foreign["headers"],
        json={
            "name": "Nope",
            "type": "percentage",
            "value": "10",
            "starts_at": _iso(1, 1),
            "ends_at": _iso(12, 31),
        },
    )
    assert response.status_code == 404