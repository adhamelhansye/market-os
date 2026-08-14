"""Price/cost history: active period resolution, overlap rejection and
Decimal precision."""

from decimal import Decimal

import pytest
from conftest import create_tenant
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def tenant(session: AsyncSession) -> dict:
    return await create_tenant(session)


def _iso(day: int, month: int = 1) -> str:
    return f"2026-{month:02d}-{day:02d}T00:00:00Z"


async def _product(client, tenant):
    response = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/products",
        headers=tenant["headers"],
        json={"name": "Widget", "currency": "USD"},
    )
    return response.json()["id"]


async def test_create_price_and_list_history(client: AsyncClient, tenant) -> None:
    product_id = await _product(client, tenant)
    url = f"/api/v1/businesses/{tenant['business'].id}/products/{product_id}/prices"

    first = await client.post(
        url, headers=tenant["headers"],
        json={"price": "100.00", "currency": "USD", "effective_from": _iso(1)},
    )
    assert first.status_code == 201
    assert first.json()["price"] == "100.00"

    second = await client.post(
        url, headers=tenant["headers"],
        json={"price": "120.00", "currency": "USD", "effective_from": _iso(1, 7)},
    )
    assert second.status_code == 201

    history = await client.get(url, headers=tenant["headers"])
    assert history.status_code == 200
    prices = history.json()
    assert len(prices) == 2
    assert [p["price"] for p in reversed(prices)] == ["100.00", "120.00"]


async def test_overlapping_price_period_rejected(client: AsyncClient, tenant) -> None:
    product_id = await _product(client, tenant)
    url = f"/api/v1/businesses/{tenant['business'].id}/products/{product_id}/prices"
    await client.post(
        url, headers=tenant["headers"],
        json={
            "price": "100.00", "currency": "USD",
            "effective_from": _iso(1), "effective_to": _iso(30, 6),
        },
    )
    overlap = await client.post(
        url, headers=tenant["headers"],
        json={
            "price": "200.00", "currency": "USD",
            "effective_from": _iso(1, 6), "effective_to": None,
        },
    )
    assert overlap.status_code == 409
    assert overlap.json()["error"]["code"] == "conflict"

    # Adjacent (half-open) periods are allowed.
    adjacent = await client.post(
        url, headers=tenant["headers"],
        json={
            "price": "200.00", "currency": "USD",
            "effective_from": _iso(30, 6), "effective_to": None,
        },
    )
    assert adjacent.status_code == 201


async def test_price_validation(client: AsyncClient, tenant) -> None:
    product_id = await _product(client, tenant)
    url = f"/api/v1/businesses/{tenant['business'].id}/products/{product_id}/prices"
    negative = await client.post(
        url, headers=tenant["headers"],
        json={"price": "-5.00", "currency": "USD", "effective_from": _iso(1)},
    )
    assert negative.status_code == 422

    inverted = await client.post(
        url, headers=tenant["headers"],
        json={
            "price": "10.00", "currency": "USD",
            "effective_from": _iso(10), "effective_to": _iso(1),
        },
    )
    assert inverted.status_code == 422


async def test_cost_decimal_precision_and_history(
    client: AsyncClient, tenant
) -> None:
    product_id = await _product(client, tenant)
    url = f"/api/v1/businesses/{tenant['business'].id}/products/{product_id}/costs"

    created = await client.post(
        url, headers=tenant["headers"],
        json={
            "cogs": "0.10",
            "packaging_cost": "0.20",
            "payment_fee_fixed": "0.30",
            "payment_fee_percent": "2.50",
            "effective_from": _iso(1),
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["cogs"] == "0.10"
    assert body["packaging_cost"] == "0.20"
    assert Decimal(body["cogs"]) + Decimal(body["packaging_cost"]) == Decimal("0.30")

    second = await client.post(
        url, headers=tenant["headers"],
        json={"cogs": "15.00", "effective_from": _iso(1, 9)},
    )
    assert second.status_code == 201

    history = await client.get(url, headers=tenant["headers"])
    assert len(history.json()) == 2


async def test_overlapping_cost_period_rejected(client: AsyncClient, tenant) -> None:
    product_id = await _product(client, tenant)
    url = f"/api/v1/businesses/{tenant['business'].id}/products/{product_id}/costs"
    await client.post(
        url, headers=tenant["headers"],
        json={"cogs": "10.00", "effective_from": _iso(1), "effective_to": _iso(30, 6)},
    )
    overlap = await client.post(
        url, headers=tenant["headers"],
        json={"cogs": "12.00", "effective_from": _iso(15, 4)},
    )
    assert overlap.status_code == 409


async def test_cost_validation(client: AsyncClient, tenant) -> None:
    product_id = await _product(client, tenant)
    url = f"/api/v1/businesses/{tenant['business'].id}/products/{product_id}/costs"
    bad_percent = await client.post(
        url, headers=tenant["headers"],
        json={"cogs": "10.00", "payment_fee_percent": "150", "effective_from": _iso(1)},
    )
    assert bad_percent.status_code == 422
    bad_fee = await client.post(
        url, headers=tenant["headers"],
        json={"cogs": "10.00", "payment_fee_fixed": "-1", "effective_from": _iso(1)},
    )
    assert bad_fee.status_code == 422


async def test_price_cost_endpoints_require_business_access(
    session: AsyncSession, client: AsyncClient, tenant
) -> None:
    product_id = await _product(client, tenant)
    foreign = await create_tenant(session)
    response = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/products/{product_id}/prices",
        headers=foreign["headers"],
        json={"price": "10.00", "currency": "USD", "effective_from": _iso(1)},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Inventory: snapshots, set vs adjust, history preserved
# ---------------------------------------------------------------------------


async def test_inventory_set_adjust_and_current(client: AsyncClient, tenant) -> None:
    product_id = await _product(client, tenant)
    url = f"/api/v1/businesses/{tenant['business'].id}/products/{product_id}/inventory"

    set_resp = await client.put(url, headers=tenant["headers"], json={"quantity": 50})
    assert set_resp.status_code == 200
    assert set_resp.json()["quantity"] == 50
    assert set_resp.json()["source"] == "manual"

    adjust = await client.patch(url, headers=tenant["headers"], json={"quantity_delta": -10})
    assert adjust.status_code == 200
    assert adjust.json()["quantity"] == 40

    current = await client.get(url, headers=tenant["headers"])
    assert current.json()["quantity"] == 40

    # Below zero is rejected.
    below = await client.patch(url, headers=tenant["headers"], json={"quantity_delta": -100})
    assert below.status_code == 409


async def test_inventory_negative_quantity_rejected(client: AsyncClient, tenant) -> None:
    product_id = await _product(client, tenant)
    url = f"/api/v1/businesses/{tenant['business'].id}/products/{product_id}/inventory"
    response = await client.put(url, headers=tenant["headers"], json={"quantity": -1})
    assert response.status_code == 422


async def test_inventory_defaults_to_zero(client: AsyncClient, tenant) -> None:
    product_id = await _product(client, tenant)
    url = f"/api/v1/businesses/{tenant['business'].id}/products/{product_id}/inventory"
    current = await client.get(url, headers=tenant["headers"])
    assert current.json()["quantity"] == 0