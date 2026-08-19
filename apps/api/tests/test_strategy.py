from datetime import UTC, datetime
from decimal import Decimal

from conftest import create_tenant
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import InventorySnapshot, Product, ProductCost, ProductPrice


async def _product(session: AsyncSession, tenant: dict, *, cogs: str = "40.00") -> Product:
    product = Product(
        business_id=tenant["business"].id,
        name="Strategy product",
        currency="USD",
    )
    session.add(product)
    await session.flush()
    effective = datetime(2020, 1, 1, tzinfo=UTC)
    session.add_all(
        [
            ProductPrice(
                product_id=product.id,
                price=Decimal("100.00"),
                currency="USD",
                effective_from=effective,
            ),
            ProductCost(
                product_id=product.id,
                cogs=Decimal(cogs),
                effective_from=effective,
            ),
            InventorySnapshot(
                product_id=product.id,
                quantity=25,
                source="manual",
                recorded_at=effective,
            ),
        ]
    )
    await session.commit()
    return product


async def test_positioning_candidate_and_insufficient_recommendation(
    client: AsyncClient, tenant: dict
) -> None:
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    created = await client.post(
        f"{base}/positioning/candidates",
        headers=tenant["headers"],
        json={
            "name": "Problem-led",
            "target_customer": "Busy owners",
            "problem": "Too much manual work",
            "solution": "A structured operating system",
            "differentiator": "Evidence-backed workflows",
            "promise": "Make decisions with clarity",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["positioning_statement"].startswith("For Busy owners")
    recommendation = await client.post(f"{base}/positioning/recommend", headers=tenant["headers"])
    assert recommendation.status_code == 200
    assert recommendation.json()["status"] == "insufficient_data"


async def test_offer_uses_decimal_economics_and_provenance_is_tenant_scoped(
    session: AsyncSession, client: AsyncClient, tenant: dict
) -> None:
    product = await _product(session, tenant)
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    created = await client.post(
        f"{base}/offers/candidates",
        headers=tenant["headers"],
        json={"name": "Standard offer", "product_id": str(product.id)},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["economics"]["contribution_profit"] == "60.00"
    assert isinstance(body["economics"]["break_even_roas"], str)
    validated = await client.post(
        f"{base}/offers/validate",
        headers=tenant["headers"],
        json={"candidate_id": body["id"]},
    )
    assert validated.status_code == 200
    assert validated.json()["candidates"][0]["status"] == "validated"

    foreign = await create_tenant(session)
    denied = await client.get(
        f"/api/v1/businesses/{foreign['business'].id}/strategy/offers/candidates/{body['id']}",
        headers=foreign["headers"],
    )
    assert denied.status_code == 404


async def test_invalid_offer_is_explicitly_invalid(
    session: AsyncSession, client: AsyncClient, tenant: dict
) -> None:
    product = await _product(session, tenant, cogs="120.00")
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    created = await client.post(
        f"{base}/offers/candidates",
        headers=tenant["headers"],
        json={"name": "Loss-making offer", "product_id": str(product.id)},
    )
    assert created.status_code == 201
    validated = await client.post(
        f"{base}/offers/validate",
        headers=tenant["headers"],
        json={"candidate_id": created.json()["id"]},
    )
    assert validated.status_code == 200
    assert validated.json()["status"] == "invalid"
    assert any(r["code"] == "margin_risk" for r in validated.json()["candidates"][0]["risks"])


async def test_strategy_summary_and_snapshot_endpoints(client: AsyncClient, tenant: dict) -> None:
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    summary = await client.get(f"{base}/summary", headers=tenant["headers"])
    assert summary.status_code == 200
    assert summary.json()["positioning"]["status"] == "insufficient_data"
    snapshot = await client.get(f"{base}/snapshot", headers=tenant["headers"])
    assert snapshot.status_code == 404
