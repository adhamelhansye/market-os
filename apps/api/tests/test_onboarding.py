"""Onboarding: profile upsert and server-side completion validation."""

import pytest
from conftest import create_tenant
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def tenant(session: AsyncSession) -> dict:
    return await create_tenant(session)


async def test_profile_upsert_and_read(client: AsyncClient, tenant) -> None:
    business_id = tenant["business"].id
    response = await client.put(
        f"/api/v1/businesses/{business_id}/profile",
        headers=tenant["headers"],
        json={
            "description": "Handmade goods",
            "business_model": "d2c",
            "target_market": "Egypt and GCC",
            "brand_positioning": "Premium handmade",
            "average_order_value": "150.50",
            "primary_customer_type": "consumer",
            "brand_voice": "warm",
        },
    )
    assert response.status_code == 200
    assert response.json()["average_order_value"] == "150.50"
    profile_id = response.json()["business_id"]

    again = await client.put(
        f"/api/v1/businesses/{business_id}/profile",
        headers=tenant["headers"],
        json={"industry": "fashion"},  # partial update
    )
    assert again.status_code == 200
    assert again.json()["industry"] == "fashion"
    assert again.json()["business_id"] == profile_id  # same record, not a duplicate

    read = await client.get(
        f"/api/v1/businesses/{business_id}/profile", headers=tenant["headers"]
    )
    assert read.status_code == 200
    assert read.json()["description"] == "Handmade goods"


async def test_profile_requires_business_access(
    session: AsyncSession, client: AsyncClient, tenant
) -> None:
    foreign = await create_tenant(session)
    response = await client.get(
        f"/api/v1/businesses/{tenant['business'].id}/profile",
        headers=foreign["headers"],
    )
    assert response.status_code == 404


async def test_complete_onboarding_requires_product_with_price_and_cogs(
    client: AsyncClient, tenant
) -> None:
    business_id = tenant["business"].id

    # No products yet: cannot complete.
    blocked = await client.patch(
        f"/api/v1/businesses/{business_id}",
        headers=tenant["headers"],
        json={"onboarding_status": "completed"},
    )
    assert blocked.status_code == 409

    # Product without price/cost: still blocked.
    product = await client.post(
        f"/api/v1/businesses/{business_id}/products",
        headers=tenant["headers"],
        json={"name": "Widget", "currency": "USD"},
    )
    assert product.status_code == 201
    product_id = product.json()["id"]

    still_blocked = await client.patch(
        f"/api/v1/businesses/{business_id}",
        headers=tenant["headers"],
        json={"onboarding_status": "completed"},
    )
    assert still_blocked.status_code == 409

    price = await client.post(
        f"/api/v1/businesses/{business_id}/products/{product_id}/prices",
        headers=tenant["headers"],
        json={
            "price": "100.00",
            "currency": "USD",
            "effective_from": "2026-01-01T00:00:00Z",
        },
    )
    assert price.status_code == 201

    cost = await client.post(
        f"/api/v1/businesses/{business_id}/products/{product_id}/costs",
        headers=tenant["headers"],
        json={
            "cogs": "30.00",
            "effective_from": "2026-01-01T00:00:00Z",
        },
    )
    assert cost.status_code == 201

    done = await client.patch(
        f"/api/v1/businesses/{business_id}",
        headers=tenant["headers"],
        json={"onboarding_status": "completed"},
    )
    assert done.status_code == 200
    assert done.json()["onboarding_status"] == "completed"


async def test_optional_marketing_fields_not_required_for_completion(
    client: AsyncClient, tenant
) -> None:
    """Onboarding completes without profile, website or shipping data."""
    business_id = tenant["business"].id
    product = await client.post(
        f"/api/v1/businesses/{business_id}/products",
        headers=tenant["headers"],
        json={"name": "Widget", "currency": "USD"},
    )
    product_id = product.json()["id"]
    await client.post(
        f"/api/v1/businesses/{business_id}/products/{product_id}/prices",
        headers=tenant["headers"],
        json={"price": "100.00", "currency": "USD", "effective_from": "2026-01-01T00:00:00Z"},
    )
    await client.post(
        f"/api/v1/businesses/{business_id}/products/{product_id}/costs",
        headers=tenant["headers"],
        json={"cogs": "30.00", "effective_from": "2026-01-01T00:00:00Z"},
    )
    response = await client.patch(
        f"/api/v1/businesses/{business_id}",
        headers=tenant["headers"],
        json={"onboarding_status": "completed"},
    )
    assert response.status_code == 200


async def test_archived_product_does_not_satisfy_completion(
    client: AsyncClient, tenant
) -> None:
    business_id = tenant["business"].id
    product = await client.post(
        f"/api/v1/businesses/{business_id}/products",
        headers=tenant["headers"],
        json={"name": "Widget", "currency": "USD"},
    )
    product_id = product.json()["id"]
    await client.post(
        f"/api/v1/businesses/{business_id}/products/{product_id}/prices",
        headers=tenant["headers"],
        json={"price": "100.00", "currency": "USD", "effective_from": "2026-01-01T00:00:00Z"},
    )
    await client.post(
        f"/api/v1/businesses/{business_id}/products/{product_id}/costs",
        headers=tenant["headers"],
        json={"cogs": "30.00", "effective_from": "2026-01-01T00:00:00Z"},
    )
    await client.delete(
        f"/api/v1/businesses/{business_id}/products/{product_id}",
        headers=tenant["headers"],
    )
    response = await client.patch(
        f"/api/v1/businesses/{business_id}",
        headers=tenant["headers"],
        json={"onboarding_status": "completed"},
    )
    assert response.status_code == 409