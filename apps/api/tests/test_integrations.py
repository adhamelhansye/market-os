"""Integration core + Shopify tests.

External HTTP is fully stubbed: we monkey-patch ShopifyAdapter.exchange_code
and validate_connection so the OAuth dance never hits the real Shopify API.
"""

import base64
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.dependencies import get_db_session, get_redis_client
from src.db.models import (
    Business,
    IntegrationConnection,
    IntegrationCredential,
    Order,
    OrderItem,
    Product,
    ProductPrice,
    WebhookEvent,
)
from src.main import app as app_under_test
from src.modules.integrations import service as service_module
from src.modules.integrations.base.errors import ProviderDataError
from src.modules.integrations.base.types import (
    CanonicalOrder,
    CanonicalProduct,
    ProviderExchangeResult,
    SyncPage,
)
from src.modules.integrations.shopify.adapter import ShopifyAdapter
from src.modules.integrations.shopify.mapper import (
    map_customer,
    map_inventory,
    map_order,
    map_product,
    map_variant_inventory,
)
from src.modules.integrations.shopify.schemas import (
    CustomerResponse,
    InventoryLevelResponse,
    LineItemResponse,
    OrderResponse,
    ProductResponse,
    ShippingLineResponse,
    VariantResponse,
)

SHOPIFY_SECRET = "test-shopify-secret"


def _hmac(body: bytes) -> str:
    return base64.b64encode(
        hmac.new(SHOPIFY_SECRET.encode("utf-8"), body, hashlib.sha256).digest()
    ).decode("ascii")


def _shop_product(product_id="111", title="Widget", price="9.99") -> ProductResponse:
    return ProductResponse(
        id=int(product_id),
        title=title,
        status="active",
        variants=[
            VariantResponse(
                id=int(product_id + "001"),
                sku=f"SKU-{product_id}",
                price=price,
                inventory_quantity=5,
                inventory_item_id=int(product_id + "001"),
            )
        ],
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _shop_order(order_id="9001", product_id="111", price="19.99", currency="USD") -> OrderResponse:
    return OrderResponse(
        id=int(order_id),
        currency=currency,
        subtotal_price=f"{Decimal(price) * 2:.2f}",
        total_discounts="0.00",
        total_tax="0.00",
        total_price=f"{Decimal(price) * 2:.2f}",
        financial_status="paid",
        fulfillment_status=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        customer=CustomerResponse(id=42, email="buyer@example.com"),
        line_items=[
            LineItemResponse(
                id=int(order_id + "10"),
                product_id=int(product_id),
                variant_id=int(product_id + "001"),
                quantity=2,
                price=price,
                total_discount="0.00",
            )
        ],
        shipping_lines=[ShippingLineResponse(price="5.00")],
    )


async def _stub_adapter(monkeypatch) -> None:
    async def _exchange(self, shop_domain, code):
        return ProviderExchangeResult(access_token="shpat_test", scope=["read_orders"])

    async def _validate(self, credentials):
        return {"name": "Test Shop", "myshopify_domain": "test.myshopify.com", "currency": "USD"}

    monkeypatch.setattr(ShopifyAdapter, "exchange_code", _exchange)
    monkeypatch.setattr(ShopifyAdapter, "validate_connection", _validate)


async def _find_connection(
    session: AsyncSession, business: Business, *, status: str
) -> IntegrationConnection | None:
    return await session.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.business_id == business.id,
            IntegrationConnection.status == status,
        )
    )


@pytest.fixture
async def integration_client(session, session_factory, redis_client):
    async def _db():
        async with session_factory() as db:
            yield db

    async def _redis():
        yield redis_client

    app_under_test.dependency_overrides[get_db_session] = _db
    app_under_test.dependency_overrides[get_redis_client] = _redis
    transport = ASGITransport(app=app_under_test)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app_under_test.dependency_overrides.clear()


# -- mapper -------------------------------------------------------------------


def test_map_product_creates_canonical() -> None:
    p = map_product(_shop_product(), "USD")
    assert isinstance(p, CanonicalProduct)
    assert p.external_id == "111" and p.title == "Widget" and p.currency == "USD"


def test_map_variant_inventory_sums_quantities() -> None:
    product = ProductResponse(
        id=1,
        title="T",
        status="active",
        variants=[
            VariantResponse(id=2, sku="A", price="1", inventory_quantity=3, inventory_item_id=99),
            VariantResponse(id=3, sku="B", price="1", inventory_quantity=7, inventory_item_id=99),
        ],
    )
    inv = map_variant_inventory(product)
    assert inv.quantity == 10 and inv.product_external_id == "1"


def test_map_order_math() -> None:
    canonical = map_order(_shop_order())
    assert isinstance(canonical, CanonicalOrder)
    # total_price from the provider = subtotal = 39.98 (shipping is captured
    # separately as shipping_revenue); line_total = unit * qty = 39.98.
    assert canonical.total == Decimal("39.98")
    assert canonical.shipping_revenue == Decimal("5.00")
    assert canonical.subtotal == Decimal("39.98")


def test_map_order_invalid_money_raises() -> None:
    order = _shop_order()
    order.subtotal_price = "not-money"
    with pytest.raises(ProviderDataError):
        map_order(order)


def test_map_customer_normalizes_email() -> None:
    p = map_customer(CustomerResponse(id=1, email="  Alice@Example.COM "))
    assert p.email == "alice@example.com"


def test_map_inventory_resolves_product() -> None:
    inv = map_inventory(
        InventoryLevelResponse(inventory_item_id=99, available=4, location_id=1),
        product_external_id="42",
    )
    assert inv.quantity == 4 and inv.product_external_id == "42"


# -- adapter webhook HMAC -----------------------------------------------------


def test_adapter_hmac_accepts_valid_signature() -> None:
    a = ShopifyAdapter()
    body = b'{"x":1}'
    assert a.verify_webhook(body, _hmac(body)) is True


def test_adapter_hmac_rejects_bad_or_missing_signature() -> None:
    a = ShopifyAdapter()
    assert a.verify_webhook(b"{}", "not-real") is False
    assert a.verify_webhook(b"{}", None) is False


# -- sync ---------------------------------------------------------------------


async def _seed_connection(session: AsyncSession, business: Business) -> IntegrationConnection:
    from src.modules.integrations.credentials import TokenCipher

    cipher = TokenCipher.from_settings(get_settings())
    connection = IntegrationConnection(
        business_id=business.id,
        provider="shopify",
        status="connected",
        external_account_id="seed.myshopify.com",
        external_account_name="Seed Shop",
        scopes=["read_orders"],
        provider_metadata={"currency": "USD"},
        connected_at=datetime.now(UTC),
    )
    session.add(connection)
    await session.flush()
    session.add(
        IntegrationCredential(
            connection_id=connection.id,
            access_token_encrypted=cipher.encrypt("shpat_seed"),
        )
    )
    await session.commit()
    return connection


def _stub_sync_page(monkeypatch, *, page_results: dict):
    async def _sync_page(self, creds, resource, cursor):
        return SyncPage(records=page_results.get(resource, []), next_cursor=None)

    monkeypatch.setattr(ShopifyAdapter, "sync_page", _sync_page)


async def test_run_sync_initial_creates_records(
    monkeypatch, session: AsyncSession, tenant: dict
) -> None:
    business = tenant["business"]
    connection = await _seed_connection(session, business)
    product = _shop_product()
    _stub_sync_page(monkeypatch, page_results={
        "products": [map_product(product, "USD"), map_variant_inventory(product)],
        "orders": [map_order(_shop_order(product_id="111"))],
        "customers": [map_customer(CustomerResponse(id=42, email="a@b.com"))],
        "inventory": [],
    })
    results = await service_module.run_sync(
        session, connection_id=str(connection.id),
        resources=service_module.INITIAL_RESOURCES, initial=True,
    )
    # products resource emits both a product and an inventory record
    assert results["products"] == 2
    assert results["orders"] == 1
    assert results["customers"] == 1
    assert results["inventory"] == 0
    product_row = await session.scalar(select(Product).where(Product.external_id == "111"))
    assert product_row is not None and product_row.external_source == "shopify"
    price = await session.scalar(
        select(ProductPrice).where(ProductPrice.product_id == product_row.id)
    )
    assert price is not None and price.price == Decimal("9.99")
    order_row = await session.scalar(select(Order).where(Order.external_id == "9001"))
    assert order_row is not None
    items = list(await session.scalars(select(OrderItem).where(OrderItem.order_id == order_row.id)))
    assert len(items) == 1 and items[0].product_id == product_row.id


async def test_run_sync_is_idempotent(
    monkeypatch, session: AsyncSession, tenant: dict
) -> None:
    business = tenant["business"]
    connection = await _seed_connection(session, business)
    _stub_sync_page(monkeypatch, page_results={
        "products": [map_product(_shop_product(), "USD")],
        "orders": [], "customers": [], "inventory": [],
    })
    for _ in range(2):
        await service_module.run_sync(
            session, connection_id=str(connection.id),
            resources=service_module.INITIAL_RESOURCES, initial=True,
        )
    products = list(await session.scalars(select(Product).where(Product.external_id == "111")))
    assert len(products) == 1
    prices = list(await session.scalars(select(ProductPrice)))
    assert len(prices) == 1


async def test_run_sync_incremental_uses_cursor(
    monkeypatch, session: AsyncSession, tenant: dict
) -> None:
    business = tenant["business"]
    connection = await _seed_connection(session, business)
    seen = {}

    async def _sync_page(self, creds, resource, cursor):
        seen.setdefault(resource, []).append(cursor)
        return SyncPage(
            records=[map_product(_shop_product(), "USD")] if resource == "products" else [],
            next_cursor=None,
        )

    monkeypatch.setattr(ShopifyAdapter, "sync_page", _sync_page)
    await service_module.run_sync(
        session, connection_id=str(connection.id),
        resources=("products",), initial=True,
    )
    assert seen["products"][0] is None
    await service_module.run_sync(
        session, connection_id=str(connection.id),
        resources=("products",), initial=False,
    )
    # Second run starts from a non-null cursor (the watermark from the first run).
    assert seen["products"][1] is not None


async def test_webhook_event_is_deduplicated(session: AsyncSession) -> None:
    body = b'{"id":1}'
    e1 = await service_module.record_webhook_event(
        session, provider="shopify", external_event_id="evt-1", raw_body=body
    )
    e2 = await service_module.record_webhook_event(
        session, provider="shopify", external_event_id="evt-1", raw_body=body
    )
    assert e1 is not None and e2 is None


# -- API endpoints ------------------------------------------------------------


async def _connect(client, tenant: dict) -> str:
    """Drives the connect endpoint; returns the callback cookie token."""
    r = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/integrations/shopify/connect",
        headers=tenant["headers"],
        json={"shop_domain": "demo.myshopify.com", "locale": "en"},
    )
    assert r.status_code == 200, r.text
    return r.cookies[get_settings().callback_session_cookie_name]


async def _state_for(tenant: dict) -> str | None:
    redis = AsyncRedis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        for key in await redis.keys("oauth:state:*"):
            payload = await redis.get(key)
            if payload is None:
                continue
            data = json.loads(payload)
            if uuid.UUID(data["user_id"]) == tenant["user"].id:
                return key.removeprefix("oauth:state:")
    finally:
        await redis.aclose()
    return None


async def _complete_callback(client, tenant: dict, cookie: str, state: str) -> None:
    r = await client.get(
        "/api/v1/integrations/shopify/callback",
        params={"code": "x", "state": state, "shop": "demo.myshopify.com"},
        cookies={get_settings().callback_session_cookie_name: cookie},
        follow_redirects=False,
    )
    assert r.status_code == 302, r.text


async def test_list_integrations_empty(integration_client, tenant: dict) -> None:
    client = integration_client
    r = await client.get(
        f"/api/v1/businesses/{tenant['business'].id}/integrations",
        headers=tenant["headers"],
    )
    assert r.status_code == 200 and r.json() == []


async def test_connect_callback_full_flow(
    monkeypatch, integration_client, session: AsyncSession, tenant: dict
) -> None:
    await _stub_adapter(monkeypatch)
    client = integration_client
    cookie = await _connect(client, tenant)
    state = await _state_for(tenant)
    assert state is not None
    await _complete_callback(client, tenant, cookie, state)
    conn = await _find_connection(session, tenant["business"], status="connected")
    assert conn is not None
    assert conn.provider_metadata == {"currency": "USD"}
    r = await client.get(
        f"/api/v1/businesses/{tenant['business'].id}/integrations",
        headers=tenant["headers"],
    )
    assert r.status_code == 200 and len(r.json()) == 1


async def test_connect_invalid_shop_domain(integration_client, tenant: dict) -> None:
    client = integration_client
    r = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/integrations/shopify/connect",
        headers=tenant["headers"],
        json={"shop_domain": "https://evil.com/admin"},
    )
    assert r.status_code == 400


async def test_callback_rejects_missing_cookie(
    monkeypatch, integration_client, tenant: dict
) -> None:
    await _stub_adapter(monkeypatch)
    client = integration_client
    await _connect(client, tenant)
    state = await _state_for(tenant)
    # Clear the auto-persisted cookie on the client to simulate a callback
    # that arrives in a browser that never received the connect response.
    client.cookies.clear()
    r = await client.get(
        "/api/v1/integrations/shopify/callback",
        params={"code": "x", "state": state, "shop": "demo.myshopify.com"},
        follow_redirects=False,
    )
    assert r.status_code == 302 and "error=connect_failed" in r.headers["location"]


async def test_callback_rejects_unknown_state(
    monkeypatch, integration_client, tenant: dict
) -> None:
    await _stub_adapter(monkeypatch)
    client = integration_client
    cookie = await _connect(client, tenant)
    r = await client.get(
        "/api/v1/integrations/shopify/callback",
        params={"code": "x", "state": "never-issued", "shop": "demo.myshopify.com"},
        cookies={get_settings().callback_session_cookie_name: cookie},
        follow_redirects=False,
    )
    assert r.status_code == 302 and "error=connect_failed" in r.headers["location"]


async def test_tenancy_other_organization_cannot_list(
    monkeypatch, integration_client, session: AsyncSession, tenant: dict
) -> None:
    from tests.conftest import create_tenant

    await _stub_adapter(monkeypatch)
    client = integration_client
    await _connect(client, tenant)
    other = await create_tenant(session)
    r = await client.get(
        f"/api/v1/businesses/{tenant['business'].id}/integrations",
        headers=other["headers"],
    )
    assert r.status_code == 404


async def test_webhook_invalid_signature(integration_client, tenant: dict) -> None:
    client = integration_client
    r = await client.post(
        "/api/v1/integrations/shopify/webhook",
        headers={
            "x-shopify-topic": "orders/create",
            "x-shopify-shop-domain": "demo.myshopify.com",
            "x-shopify-webhook-id": "evt-bad",
            "x-shopify-hmac-sha256": "bad",
        },
        content=b'{"id":1}',
    )
    assert r.status_code == 401


async def test_webhook_valid_records_event(
    integration_client, session: AsyncSession, tenant: dict
) -> None:
    client = integration_client
    body = json.dumps(_shop_order().model_dump(mode="json")).encode()
    r = await client.post(
        "/api/v1/integrations/shopify/webhook",
        headers={
            "x-shopify-topic": "orders/create",
            "x-shopify-shop-domain": "demo.myshopify.com",
            "x-shopify-webhook-id": "evt-ok",
            "x-shopify-hmac-sha256": _hmac(body),
        },
        content=body,
    )
    assert r.status_code == 200
    events = list(await session.scalars(select(WebhookEvent)))
    assert len(events) == 1


async def test_webhook_duplicate_is_idempotent(integration_client, tenant: dict) -> None:
    client = integration_client
    body = json.dumps(_shop_order().model_dump(mode="json")).encode()
    headers = {
        "x-shopify-topic": "orders/create",
        "x-shopify-shop-domain": "demo.myshopify.com",
        "x-shopify-webhook-id": "evt-dup",
        "x-shopify-hmac-sha256": _hmac(body),
    }
    r1 = await client.post("/api/v1/integrations/shopify/webhook", headers=headers, content=body)
    r2 = await client.post("/api/v1/integrations/shopify/webhook", headers=headers, content=body)
    assert r1.status_code == 200 and r2.status_code == 200


async def test_sync_endpoint_enqueues_job(
    monkeypatch, integration_client, session: AsyncSession, tenant: dict
) -> None:
    await _stub_adapter(monkeypatch)
    client = integration_client
    cookie = await _connect(client, tenant)
    state = await _state_for(tenant)
    await _complete_callback(client, tenant, cookie, state)
    conn = await _find_connection(session, tenant["business"], status="connected")
    captured = {}

    async def _enqueue(connection_id, resources):
        captured["connection_id"] = connection_id
        captured["resources"] = list(resources)

    # Patch where service.py binds the symbol (the service imports it by name).
    monkeypatch.setattr(service_module, "enqueue_incremental_sync", _enqueue)
    r = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/integrations/{conn.id}/sync",
        headers=tenant["headers"],
        json={"resources": ["orders", "products"]},
    )
    assert r.status_code == 200, r.text
    assert captured["resources"] == ["orders", "products"]


async def test_disconnect_clears_credentials(
    monkeypatch, integration_client, session: AsyncSession, tenant: dict
) -> None:
    await _stub_adapter(monkeypatch)
    client = integration_client
    cookie = await _connect(client, tenant)
    state = await _state_for(tenant)
    await _complete_callback(client, tenant, cookie, state)
    conn = await _find_connection(session, tenant["business"], status="connected")
    r = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/integrations/{conn.id}/disconnect",
        headers=tenant["headers"],
    )
    assert r.status_code == 200
    assert r.json()["status"] == "disconnected"
    creds = list(
        await session.scalars(
            select(IntegrationCredential).where(IntegrationCredential.connection_id == conn.id)
        )
    )
    assert creds == []


# -- revenue summary ----------------------------------------------------------


async def test_revenue_summary_empty(integration_client, tenant: dict) -> None:
    client = integration_client
    r = await client.get(
        f"/api/v1/businesses/{tenant['business'].id}/economics/revenue",
        headers=tenant["headers"],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["order_count"] == 0
    assert body["total_revenue"] == "0.00"
    assert body["refunded_revenue"] == "0.00"
    assert body["last_30d_orders"] == 0


async def test_revenue_summary_aggregates(
    integration_client, session: AsyncSession, tenant: dict
) -> None:
    business = tenant["business"]
    now = datetime.now(UTC)
    session.add_all([
        Order(
            business_id=business.id, external_id="o1", source="shopify", currency="USD",
            subtotal=Decimal("10.00"), discount_total=Decimal("0"), shipping_revenue=Decimal("0"),
            tax_total=None, total=Decimal("12.00"), financial_status="paid",
            fulfillment_status=None, ordered_at=now - timedelta(days=5),
        ),
        Order(
            business_id=business.id, external_id="o2", source="shopify", currency="USD",
            subtotal=Decimal("50.00"), discount_total=Decimal("0"), shipping_revenue=Decimal("0"),
            tax_total=None, total=Decimal("50.00"), financial_status="refunded",
            fulfillment_status=None, ordered_at=now - timedelta(days=40),
        ),
        Order(
            business_id=business.id, external_id="o3", source="shopify", currency="EUR",
            subtotal=Decimal("999.00"), discount_total=Decimal("0"), shipping_revenue=Decimal("0"),
            tax_total=None, total=Decimal("999.00"), financial_status="paid",
            fulfillment_status=None, ordered_at=now - timedelta(days=1),
        ),
    ])
    await session.commit()
    client = integration_client
    r = await client.get(
        f"/api/v1/businesses/{business.id}/economics/revenue",
        headers=tenant["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["order_count"] == 2
    assert body["total_revenue"] == "62.00"
    assert body["refunded_revenue"] == "50.00"
    assert body["last_30d_orders"] == 1
    assert body["last_30d_revenue"] == "12.00"


async def test_revenue_summary_tenancy(
    integration_client, session: AsyncSession, tenant: dict
) -> None:
    from tests.conftest import create_tenant

    business = tenant["business"]
    session.add(
        Order(
            business_id=business.id, external_id="o1", source="shopify", currency="USD",
            subtotal=Decimal("10.00"), discount_total=Decimal("0"), shipping_revenue=Decimal("0"),
            tax_total=None, total=Decimal("10.00"), financial_status="paid",
            fulfillment_status=None, ordered_at=datetime.now(UTC),
        )
    )
    await session.commit()
    other = await create_tenant(session)
    client = integration_client
    r = await client.get(
        f"/api/v1/businesses/{business.id}/economics/revenue",
        headers=other["headers"],
    )
    assert r.status_code == 404