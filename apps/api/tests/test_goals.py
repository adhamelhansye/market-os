"""Business goals: create/update, historical goals, overlapping periods."""

from decimal import Decimal

import pytest
from conftest import create_tenant
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def tenant(session: AsyncSession) -> dict:
    return await create_tenant(session)


def _iso(start_day: int, start_month: int = 1, end_day: int = 31, end_month: int = 12) -> dict:
    return {
        "period_start": f"2026-{start_month:02d}-{start_day:02d}T00:00:00Z",
        "period_end": f"2026-{end_month:02d}-{end_day:02d}T00:00:00Z",
    }


async def test_create_goal(client: AsyncClient, tenant) -> None:
    response = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/goals",
        headers=tenant["headers"],
        json={
            **_iso(1, 1, 30, 6),
            "target_revenue": "50000.00",
            "target_profit": "8000.00",
            "ad_budget": "12000.00",
            "maximum_cpa": "10.00",
            "target_roas": "4",
            "currency": "USD",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert Decimal(body["target_revenue"]) == Decimal("50000.00")
    assert Decimal(body["maximum_cpa"]) == Decimal("10.00")
    assert body["currency"] == "USD"


async def test_goal_validation(client: AsyncClient, tenant) -> None:
    response = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/goals",
        headers=tenant["headers"],
        json={**_iso(30, 6, 1, 1), "target_revenue": "100", "currency": "USD"},
    )
    assert response.status_code == 422  # period_end before period_start

    negative = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/goals",
        headers=tenant["headers"],
        json={**_iso(1, 1, 30, 6), "target_revenue": "-5", "currency": "USD"},
    )
    assert negative.status_code == 422


async def test_historical_goals_and_current(client: AsyncClient, tenant) -> None:
    url = f"/api/v1/businesses/{tenant['business'].id}/goals"

    past = await client.post(
        url, headers=tenant["headers"],
        json={**_iso(1, 1, 30, 6), "target_revenue": "30000", "currency": "USD"},
    )
    assert past.status_code == 201

    current = await client.post(
        url, headers=tenant["headers"],
        json={**_iso(1, 7, 31, 12), "target_revenue": "60000", "currency": "USD"},
    )
    assert current.status_code == 201

    goals = await client.get(url, headers=tenant["headers"])
    assert goals.status_code == 200
    assert len(goals.json()) == 2

    summary = await client.get(
        f"/api/v1/businesses/{tenant['business'].id}/economics/summary",
        headers=tenant["headers"],
    )
    current_goal = summary.json()["current_goal"]
    assert current_goal["id"] == current.json()["id"]  # the active period


async def test_overlapping_goal_periods_rejected(client: AsyncClient, tenant) -> None:
    url = f"/api/v1/businesses/{tenant['business'].id}/goals"
    await client.post(
        url, headers=tenant["headers"],
        json={**_iso(1, 1, 30, 6), "target_revenue": "30000", "currency": "USD"},
    )
    overlap = await client.post(
        url, headers=tenant["headers"],
        json={**_iso(1, 5, 31, 8), "target_revenue": "40000", "currency": "USD"},
    )
    assert overlap.status_code == 409
    assert overlap.json()["error"]["code"] == "conflict"

    # Adjacent periods (half-open) are allowed.
    adjacent = await client.post(
        url, headers=tenant["headers"],
        json={**_iso(30, 6, 31, 12), "target_revenue": "40000", "currency": "USD"},
    )
    assert adjacent.status_code == 201


async def test_update_goal(client: AsyncClient, tenant) -> None:
    created = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/goals",
        headers=tenant["headers"],
        json={**_iso(1, 1, 30, 6), "target_revenue": "30000", "currency": "USD"},
    )
    goal_id = created.json()["id"]

    updated = await client.patch(
        f"/api/v1/businesses/{tenant['business'].id}/goals/{goal_id}",
        headers=tenant["headers"],
        json={"target_revenue": "45000.50", "ad_budget": "9000"},
    )
    assert updated.status_code == 200
    assert Decimal(updated.json()["target_revenue"]) == Decimal("45000.50")


async def test_delete_goal(client: AsyncClient, tenant) -> None:
    created = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/goals",
        headers=tenant["headers"],
        json={**_iso(1, 1, 30, 6), "target_revenue": "30000", "currency": "USD"},
    )
    goal_id = created.json()["id"]

    deleted = await client.delete(
        f"/api/v1/businesses/{tenant['business'].id}/goals/{goal_id}",
        headers=tenant["headers"],
    )
    assert deleted.status_code == 204


async def test_goal_cross_tenant_denied(
    session: AsyncSession, client: AsyncClient, tenant
) -> None:
    foreign = await create_tenant(session)
    response = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/goals",
        headers=foreign["headers"],
        json={**_iso(1, 1, 30, 6), "target_revenue": "30000", "currency": "USD"},
    )
    assert response.status_code == 404