"""Calculators must be verified against both the unit-level API and the
HTTP API: the router may pass Decimals correctly but serialization could
silently coerce to floats. We assert raw JSON types (money must be
strings, never numbers) plus exact Decimal math.

For HTTP tests we always use UTC `datetime` and January 2026 dates so the
"current date" of the service (datetime.now) never interferes.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from conftest import create_tenant
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.economics.calculator import (
    calculate_bundle_economics,
    calculate_discount_amount,
    calculate_product_economics,
)
from src.modules.economics.service import (
    resolve_active_cost,
    resolve_active_price,
)

NOW = datetime(2026, 1, 15, tzinfo=UTC)


@pytest.fixture
async def econ_tenant(session: AsyncSession) -> dict:
    return await create_tenant(session)


# ---------------------------------------------------------------------------
# Calculator: exact Decimal arithmetic
# ---------------------------------------------------------------------------


def test_calculator_exact_contribution_profit() -> None:
    result = calculate_product_economics(
        price=Decimal("100.00"),
        cogs=Decimal("30.00"),
        packaging_cost=Decimal("5.00"),
        payment_fee_fixed=Decimal("0.50"),
        payment_fee_percent=Decimal("2.5"),
        shipping_cost=Decimal("20.00"),
        shipping_customer_price=Decimal("20.00"),
    )
    assert result.product_revenue == Decimal("100.00")
    assert result.shipping_revenue == Decimal("20.00")
    assert result.total_customer_revenue == Decimal("120.00")
    assert result.product_cost == Decimal("35.00")
    assert result.shipping_cost == Decimal("20.00")
    assert result.payment_fees == Decimal("3.00")
    assert result.discount_amount == Decimal("0.00")
    assert result.contribution_profit == Decimal("62.00")
    assert result.contribution_margin == Decimal("0.5167")
    assert result.break_even_cpa == Decimal("62.00")
    assert result.break_even_roas == Decimal("1.9355")
    assert result.target_cpa is None
    assert result.target_cpa_reason == "target_profit_per_order_not_provided"


def test_calculator_discount_percentage_and_caps() -> None:
    # 10% on 100 = 10.00
    result = calculate_product_economics(
        price=Decimal("100.00"),
        cogs=Decimal("30.00"),
        discount_type="percentage",
        discount_value=Decimal("10"),
    )
    assert result.discount_amount == Decimal("10.00")
    assert result.contribution_profit == Decimal("60.00")  # 100 - 30 - 0 - 10

    # capped by maximum_discount
    capped = calculate_product_economics(
        price=Decimal("100.00"),
        cogs=Decimal("30.00"),
        discount_type="percentage",
        discount_value=Decimal("10"),
        discount_maximum_discount=Decimal("8.00"),
    )
    assert capped.discount_amount == Decimal("8.00")


def test_calculator_discount_minimum_order_value() -> None:
    result = calculate_product_economics(
        price=Decimal("100.00"),
        shipping_customer_price=Decimal("20.00"),
        discount_type="percentage",
        discount_value=Decimal("10"),
        discount_minimum_order_value=Decimal("150.00"),
    )
    assert result.discount_amount == Decimal("0.00")

    applied = calculate_product_economics(
        price=Decimal("100.00"),
        shipping_customer_price=Decimal("20.00"),
        discount_type="percentage",
        discount_value=Decimal("10"),
        discount_minimum_order_value=Decimal("100.00"),
    )
    assert applied.discount_amount == Decimal("10.00")


def test_calculator_discount_fixed_and_100_percent() -> None:
    fixed = calculate_product_economics(
        price=Decimal("100.00"),
        cogs=Decimal("30.00"),
        discount_type="fixed_amount",
        discount_value=Decimal("15.00"),
    )
    assert fixed.discount_amount == Decimal("15.00")

    full = calculate_product_economics(
        price=Decimal("100.00"),
        cogs=Decimal("30.00"),
        discount_type="percentage",
        discount_value=Decimal("100"),
    )
    assert full.discount_amount == Decimal("100.00")  # capped at price
    assert full.contribution_profit == Decimal("-30.00")  # -30 cogs, no fees


def test_calculator_zero_price_and_zero_costs() -> None:
    zero = calculate_product_economics(price=Decimal("0.00"))
    assert zero.contribution_profit == Decimal("0.00")
    assert zero.contribution_margin is None  # no silent division by zero
    assert zero.break_even_roas is None

    no_cost = calculate_product_economics(price=Decimal("50.00"))
    assert no_cost.contribution_profit == Decimal("50.00")
    assert no_cost.contribution_margin == Decimal("1.0000")


def test_calculator_zero_shipping_and_negative_contribution() -> None:
    result = calculate_product_economics(
        price=Decimal("10.00"),
        cogs=Decimal("20.00"),
        shipping_cost=Decimal("5.00"),
    )
    assert result.contribution_profit == Decimal("-15.00")
    assert result.contribution_margin == Decimal("-1.5000")
    assert result.break_even_cpa == Decimal("-15.00")
    assert result.break_even_roas is None  # only positive contributions


def test_calculator_fee_precision_and_target_cpa() -> None:
    fee = calculate_product_economics(
        price=Decimal("100.00"),
        payment_fee_fixed=Decimal("0.10"),
        payment_fee_percent=Decimal("2.9"),
    )
    assert fee.payment_fees == Decimal("3.00")  # 0.10 + 2.90

    target = calculate_product_economics(
        price=Decimal("100.00"),
        cogs=Decimal("30.00"),
        desired_profit_per_order=Decimal("10.00"),
    )
    assert target.target_cpa == Decimal("60.00")  # 100 - 30 - 10


def test_calculate_discount_amount_never_negative() -> None:
    amount = calculate_discount_amount(
        product_revenue=Decimal("0.00"),
        discount_type="percentage",
        discount_value=Decimal("10"),
        minimum_order_value=None,
        maximum_discount=None,
    )
    assert amount == Decimal("0.00")


def test_calculator_bundle_economics() -> None:
    result = calculate_bundle_economics(
        bundle_price=Decimal("200.00"),
        item_costs=[Decimal("35.00"), Decimal("60.00")],
        quantities=[1, 2],
    )
    assert result.items_cost == Decimal("155.00")
    assert result.contribution_profit == Decimal("45.00")
    assert result.contribution_margin == Decimal("0.2250")

    free = calculate_bundle_economics(
        bundle_price=Decimal("0.00"),
        item_costs=[Decimal("10.00")],
        quantities=[1],
    )
    assert free.contribution_margin is None


# ---------------------------------------------------------------------------
# Service: active price/cost resolution with history
# ---------------------------------------------------------------------------


async def test_resolve_active_price_history(
    session: AsyncSession, econ_tenant
) -> None:
    from src.db.models import Product, ProductPrice

    product = Product(business_id=econ_tenant["business"].id, name="Widget", currency="USD")
    session.add(product)
    await session.flush()
    session.add_all(
        [
            ProductPrice(
                product_id=product.id,
                price=Decimal("100.00"),
                currency="USD",
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
                effective_to=datetime(2026, 6, 30, tzinfo=UTC),
            ),
            ProductPrice(
                product_id=product.id,
                price=Decimal("120.00"),
                currency="USD",
                effective_from=datetime(2026, 7, 1, tzinfo=UTC),
                effective_to=None,
            ),
        ]
    )
    await session.commit()

    earlier = await resolve_active_price(
        session, product.id, datetime(2026, 3, 1, tzinfo=UTC)
    )
    later = await resolve_active_price(
        session, product.id, datetime(2026, 9, 1, tzinfo=UTC)
    )
    assert earlier.price == Decimal("100.00")
    assert later.price == Decimal("120.00")


async def test_resolve_active_cost_defaults_zero(
    session: AsyncSession, econ_tenant
) -> None:
    from src.db.models import Product

    product = Product(business_id=econ_tenant["business"].id, name="Widget", currency="USD")
    session.add(product)
    await session.commit()
    cost = await resolve_active_cost(session, product.id, datetime.now(UTC))
    assert cost is None


# ---------------------------------------------------------------------------
# HTTP: summary endpoint, money serialization, empty states
# ---------------------------------------------------------------------------


from src.db.models import Product as _Product  # noqa: E402
from src.db.models import ProductCost as _Cost  # noqa: E402
from src.db.models import ProductPrice as _Price  # noqa: E402


async def _add_priced_product(
    session: AsyncSession,
    business_id,
    name: str,
    price: str,
    cogs: str,
    quantity: int = 0,
):
    product = _Product(business_id=business_id, name=name, currency="USD")
    session.add(product)
    await session.flush()
    session.add(
        _Price(
            product_id=product.id,
            price=Decimal(price),
            currency="USD",
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    session.add(
        _Cost(
            product_id=product.id,
            cogs=Decimal(cogs),
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    if quantity:
        from src.db.models import InventorySnapshot

        session.add(
            InventorySnapshot(
                product_id=product.id, quantity=quantity, source="manual"
            )
        )
    return product


async def test_summary_empty_state(client: AsyncClient, econ_tenant) -> None:
    response = await client.get(
        f"/api/v1/businesses/{econ_tenant['business'].id}/economics/summary",
        headers=econ_tenant["headers"],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["active_products"] == 0
    assert body["average_product_price"] is None
    assert body["break_even_cpa_range"] is None
    assert body["inventory_value"] == "0.00"
    assert body["current_goal"] is None


async def test_summary_aggregates(
    session: AsyncSession, client: AsyncClient, econ_tenant
) -> None:
    await _add_priced_product(
        session, econ_tenant["business"].id, "Alpha", "100.00", "30.00", quantity=10
    )
    await _add_priced_product(
        session, econ_tenant["business"].id, "Beta", "200.00", "50.00"
    )
    await session.commit()

    response = await client.get(
        f"/api/v1/businesses/{econ_tenant['business'].id}/economics/summary",
        headers=econ_tenant["headers"],
    )
    assert response.status_code == 200
    body = response.json()

    # Money must never serialize as a JSON number.
    assert isinstance(body["average_product_price"], str)
    assert isinstance(body["average_contribution_profit"], str)
    assert isinstance(body["inventory_value"], str)
    assert isinstance(body["break_even_cpa_range"][0], str)

    assert Decimal(body["average_product_price"]) == Decimal("150.00")
    assert Decimal(body["average_contribution_profit"]) == Decimal("110.00")
    assert Decimal(body["average_contribution_margin"]) == Decimal("0.7250")
    assert [Decimal(v) for v in body["break_even_cpa_range"]] == [
        Decimal("70.00"),
        Decimal("150.00"),
    ]
    assert Decimal(body["break_even_roas"]) == Decimal("1.3636")
    assert Decimal(body["inventory_value"]) == Decimal("1000.00")
    assert body["target_cpa"] is None


async def test_economics_products_list(
    session: AsyncSession, client: AsyncClient, econ_tenant
) -> None:
    await _add_priced_product(
        session, econ_tenant["business"].id, "Alpha", "100.00", "30.00"
    )
    await session.commit()

    response = await client.get(
        f"/api/v1/businesses/{econ_tenant['business'].id}/economics/products",
        headers=econ_tenant["headers"],
    )
    assert response.status_code == 200
    [row] = response.json()
    assert Decimal(row["product_revenue"]) == Decimal("100.00")
    assert Decimal(row["contribution_profit"]) == Decimal("70.00")
    assert Decimal(row["product_cost"]) == Decimal("30.00")
    assert Decimal(row["payment_fees"]) == Decimal("0.00")
    assert Decimal(row["contribution_margin"]) == Decimal("0.7000")
    assert Decimal(row["break_even_cpa"]) == Decimal("70.00")
    assert Decimal(row["break_even_roas"]) == Decimal("1.4286")


async def test_economics_goals(client: AsyncClient, econ_tenant) -> None:
    response = await client.post(
        f"/api/v1/businesses/{econ_tenant['business'].id}/goals",
        headers=econ_tenant["headers"],
        json={
            "period_start": "2026-01-01T00:00:00Z",
            "period_end": "2026-12-31T00:00:00Z",
            "target_revenue": "100000.00",
            "currency": "USD",
        },
    )
    assert response.status_code == 201

    goals = await client.get(
        f"/api/v1/businesses/{econ_tenant['business'].id}/economics/goals",
        headers=econ_tenant["headers"],
    )
    assert goals.status_code == 200
    [goal] = goals.json()
    assert Decimal(goal["target_revenue"]) == Decimal("100000.00")

    summary = await client.get(
        f"/api/v1/businesses/{econ_tenant['business'].id}/economics/summary",
        headers=econ_tenant["headers"],
    )
    assert summary.status_code == 200
    assert summary.json()["current_goal"]["id"] == goal["id"]


async def test_cross_tenant_economics_denied(
    session: AsyncSession, client: AsyncClient, econ_tenant
) -> None:
    foreign = await create_tenant(session)
    await _add_priced_product(
        session, econ_tenant["business"].id, "Alpha", "100.00", "30.00"
    )
    await session.commit()

    response = await client.get(
        f"/api/v1/businesses/{econ_tenant['business'].id}/economics/summary",
        headers=foreign["headers"],
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"