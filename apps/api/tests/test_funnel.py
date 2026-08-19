"""Phase 7C funnel strategy API tests (deterministic, evidence-backed)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from conftest import create_tenant
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Ad,
    AdAccount,
    AdInsight,
    AdSet,
    Campaign,
    IntegrationConnection,
    InventorySnapshot,
    Order,
    Product,
    ProductCost,
    ProductPrice,
)

PROVIDER_META = "meta"
PROVIDER_SHOPIFY = "shopify"


def _today() -> date:
    return datetime.now(UTC).date()


async def _product(session: AsyncSession, tenant: dict, *, cogs: str = "40.00") -> Product:
    product = Product(business_id=tenant["business"].id, name="Funnel product", currency="USD")
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
            ProductCost(product_id=product.id, cogs=Decimal(cogs), effective_from=effective),
            InventorySnapshot(
                product_id=product.id, quantity=25, source="manual", recorded_at=effective
            ),
        ]
    )
    await session.commit()
    return product


async def _connection(session, business, *, provider: str) -> IntegrationConnection:
    connection = IntegrationConnection(
        business_id=business.id,
        provider=provider,
        status="connected",
        external_account_id=f"act_{uuid.uuid4().hex[:10]}"
        if provider == "meta"
        else f"shop-{uuid.uuid4().hex[:10]}.myshopify.com",
        external_account_name="Test Account",
        scopes=[],
        provider_metadata={},
        connected_at=datetime.now(UTC),
        last_sync_at=datetime.now(UTC),
    )
    session.add(connection)
    await session.flush()
    return connection


async def _ad_facts(session, business, *, day: date, impressions: int, clicks: int) -> None:
    """Minimal Meta insight rows (grain 'ad') read by the metrics view."""
    connection = await _connection(session, business, provider=PROVIDER_META)
    account = AdAccount(
        business_id=business.id,
        integration_connection_id=connection.id,
        external_id=f"act-{uuid.uuid4().hex[:10]}",
        name="Meta Account",
        currency="USD",
        status="ACTIVE",
    )
    session.add(account)
    await session.flush()
    campaign = Campaign(
        business_id=business.id,
        ad_account_id=account.id,
        external_id=f"camp-{uuid.uuid4().hex[:8]}",
        name="Campaign",
        status="ACTIVE",
    )
    session.add(campaign)
    await session.flush()
    ad_set = AdSet(
        business_id=business.id,
        ad_account_id=account.id,
        campaign_id=campaign.id,
        external_id=f"set-{uuid.uuid4().hex[:8]}",
        name="Ad Set",
        status="ACTIVE",
    )
    session.add(ad_set)
    await session.flush()
    ad = Ad(
        business_id=business.id,
        ad_account_id=account.id,
        campaign_id=campaign.id,
        ad_set_id=ad_set.id,
        external_id=f"ad-{uuid.uuid4().hex[:8]}",
        name="Ad",
        status="ACTIVE",
    )
    session.add(ad)
    await session.flush()
    session.add(
        AdInsight(
            business_id=business.id,
            ad_account_id=account.id,
            campaign_id=campaign.id,
            ad_set_id=ad_set.id,
            ad_id=ad.id,
            provider=PROVIDER_META,
            date=day,
            grain="daily",
            currency="USD",
            impressions=impressions,
            reach=clicks * 20,
            clicks=clicks,
            link_clicks=clicks,
            landing_page_views=int(clicks * 0.6),
            spend=Decimal("50.00"),
            conversions=None,
            conversion_value=None,
        )
    )


async def _order(session, business, *, day: date, total: str = "50.00") -> None:
    session.add(
        Order(
            business_id=business.id,
            external_id=f"o-{uuid.uuid4().hex[:10]}",
            source=PROVIDER_SHOPIFY,
            currency="USD",
            subtotal=Decimal(total),
            discount_total=Decimal("0"),
            shipping_revenue=Decimal("0"),
            tax_total=None,
            total=Decimal(total),
            financial_status="paid",
            fulfillment_status=None,
            ordered_at=datetime.combine(day, datetime.min.time(), tzinfo=UTC),
        )
    )


async def _positioning(client: AsyncClient, tenant: dict, base: str) -> dict:
    created = await client.post(
        f"{base}/positioning/candidates",
        headers=tenant["headers"],
        json={
            "name": "Funnel positioning",
            "target_customer": "Busy owners",
            "problem": "Manual work",
            "solution": "Structured workflows",
            "differentiator": "Evidence-backed workflows",
            "promise": "Clarity",
        },
    )
    assert created.status_code == 201, created.text
    return created.json()


async def test_funnel_generate_with_matrics_drives_transitions_and_health(
    session: AsyncSession, client: AsyncClient, tenant: dict
) -> None:
    product = await _product(session, tenant)
    day = _today() - timedelta(days=2)
    await _ad_facts(session, tenant["business"], day=day, impressions=1000, clicks=30)
    await _ad_facts(
        session,
        tenant["business"],
        day=day - timedelta(days=1),
        impressions=1000,
        clicks=30,
    )
    await _order(session, tenant["business"], day=day)
    await _order(session, tenant["business"], day=day - timedelta(days=1))
    await session.commit()

    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    positioning = await _positioning(client, tenant, base)
    offer = await client.post(
        f"{base}/offers/candidates",
        headers=tenant["headers"],
        json={"name": "Standard offer", "product_id": str(product.id)},
    )
    assert offer.status_code == 201, offer.text
    generated = await client.post(
        f"{base}/funnel/generate",
        headers=tenant["headers"],
        json={
            "positioning_candidate_id": positioning["id"],
            "offer_candidate_id": offer.json()["id"],
        },
    )
    assert generated.status_code == 201, generated.text
    body = generated.json()
    assert body["funnel_version"] == "funnel_v1"
    assert body["variant"] == "ecommerce"
    assert body["version"] == 1
    stages = {stage["stage"]: stage for stage in body["stages"]}
    assert [stage["stage"] for stage in body["stages"]] == [
        "awareness",
        "interest",
        "consideration",
        "purchase",
        "retention",
    ]
    assert body["health"]["score"] == "1.0000"
    assert body["health"]["bucket"] == "healthy"
    assert body["health"]["performance_claims"] == "no_performance_claim"

    awareness = stages["awareness"]
    assert awareness["status"] == "healthy"
    assert awareness["exit_condition"]["status"] == "available"
    assert awareness["exit_condition"]["value"] == "0.0300"
    assert awareness["exit_condition"]["bottleneck"] == "likely"
    assert {channel["channel"] for channel in awareness["channels"]} == {"meta"}
    meta_channel = next(
        channel for channel in awareness["channels"] if channel["channel"] == "meta"
    )
    assert meta_channel["status"] == "connected"
    assert meta_channel["integration_connection_id"] is not None

    consideration = stages["consideration"]
    assert consideration["exit_condition"]["status"] == "available"

    purchase = stages["purchase"]
    assert purchase["status"] == "healthy"
    assert purchase["cta_type"] == "view_product"
    purchase_kpis = {kpi["kpi_code"]: kpi for kpi in purchase["kpis"]}
    assert purchase_kpis["purchases"]["status"] == "available"
    assert purchase_kpis["purchases"]["value_ref"]["value"] == "2"
    assert {kpi["kpi_code"] for kpi in purchase["kpis"]} == {
        "purchases",
        "revenue",
        "cpa",
        "roas",
        "aov",
    }

    retention = stages["retention"]
    assert retention["status"] == "not_configured"
    assert retention["kpis"][0]["kpi_code"] == "repeat_purchases"
    assert retention["kpis"][0]["status"] == "not_configured"

    transitions = [gap for gap in body["gaps"] if gap["gap_type"] == "transition"]
    assert transitions, "a likely bottleneck transition gap is expected"
    assert transitions[0]["stage_from"] == "awareness"
    assert transitions[0]["stage_to"] == "interest"
    assert transitions[0]["severity"] == "high"
    assert body["status"] == "viable"
    snapshot = body["input_snapshot"]
    assert snapshot["funnel_rules_version"] == "funnel_rules_v1"
    assert snapshot["metrics_range"]["kind"] == "last_30_days"
    assert snapshot["business_goal"]["status"] == "unavailable"


async def test_funnel_lead_generation_variant_is_invalid(client: AsyncClient, tenant: dict) -> None:
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    generated = await client.post(
        f"{base}/funnel/generate",
        headers=tenant["headers"],
        json={"variant": "lead_generation"},
    )
    assert generated.status_code == 201, generated.text
    body = generated.json()
    assert body["variant"] == "lead_generation"
    assert body["status"] == "invalid"
    assert body["input_snapshot"]["variant_signal"] == "unsupported"
    assert body["gaps"] == []


async def test_funnel_ecommerce_variant_requires_offer(client: AsyncClient, tenant: dict) -> None:
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    generated = await client.post(
        f"{base}/funnel/generate",
        headers=tenant["headers"],
        json={"variant": "ecommerce"},
    )
    assert generated.status_code == 201, generated.text
    body = generated.json()
    assert body["status"] == "insufficient_data"
    signals = [gap for gap in body["gaps"] if gap["gap_type"] == "variant_signal"]
    assert signals
    assert signals[0]["severity"] == "critical"


async def test_funnel_product_led_variant_requires_differentiator(
    session: AsyncSession, client: AsyncClient, tenant: dict
) -> None:
    product = await _product(session, tenant)
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    positioning = await client.post(
        f"{base}/positioning/candidates",
        headers=tenant["headers"],
        json={"name": "No differentiator", "solution": "A product", "promise": "Outcomes"},
    )
    assert positioning.status_code == 201, positioning.text
    offer = await client.post(
        f"{base}/offers/candidates",
        headers=tenant["headers"],
        json={"name": "Offer", "product_id": str(product.id)},
    )
    assert offer.status_code == 201, offer.text
    generated = await client.post(
        f"{base}/funnel/generate",
        headers=tenant["headers"],
        json={
            "variant": "product_led",
            "positioning_candidate_id": positioning.json()["id"],
            "offer_candidate_id": offer.json()["id"],
        },
    )
    assert generated.status_code == 201, generated.text
    body = generated.json()
    assert body["status"] == "insufficient_data"
    signals = [gap for gap in body["gaps"] if gap["gap_type"] == "variant_signal"]
    assert signals and signals[0]["severity"] == "critical"


async def test_funnel_direct_response_default_without_offer_reports_gaps(
    client: AsyncClient, tenant: dict
) -> None:
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    generated = await client.post(f"{base}/funnel/generate", headers=tenant["headers"], json={})
    assert generated.status_code == 201, generated.text
    body = generated.json()
    assert body["variant"] == "direct_response"
    assert body["status"] == "needs_evidence"
    gap_types = {gap["gap_type"] for gap in body["gaps"]}
    assert "evidence" in gap_types
    assert "decision" in gap_types
    assert "cta" in gap_types
    purchase = next(stage for stage in body["stages"] if stage["stage"] == "purchase")
    assert purchase["cta_type"] is None
    assert body["health"]["score"] is None


async def test_funnel_connected_channel_only_from_connected_connection(
    session: AsyncSession, client: AsyncClient, tenant: dict
) -> None:
    connected = await _connection(session, tenant["business"], provider=PROVIDER_META)
    stale = IntegrationConnection(
        business_id=tenant["business"].id,
        provider=PROVIDER_META,
        status="connected",
        external_account_id="act_old",
        external_account_name="Old Account",
        scopes=[],
        provider_metadata={},
        connected_at=datetime.now(UTC) - timedelta(days=30),
        last_sync_at=None,
    )
    disconnected = IntegrationConnection(
        business_id=tenant["business"].id,
        provider=PROVIDER_SHOPIFY,
        status="disconnected",
        external_account_id="old-shop.myshopify.com",
        external_account_name="Old Shop",
        scopes=[],
        provider_metadata={},
        connected_at=None,
        last_sync_at=None,
    )
    session.add_all([stale, disconnected])
    await session.commit()

    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    generated = await client.post(f"{base}/funnel/generate", headers=tenant["headers"], json={})
    assert generated.status_code == 201, generated.text
    body = generated.json()
    awareness = next(stage for stage in body["stages"] if stage["stage"] == "awareness")
    meta_channel = next(
        channel for channel in awareness["channels"] if channel["channel"] == "meta"
    )
    assert meta_channel["status"] == "connected"
    assert meta_channel["integration_connection_id"] == str(connected.id)
    purchase = next(stage for stage in body["stages"] if stage["stage"] == "purchase")
    shopify_channel = next(
        channel for channel in purchase["channels"] if channel["channel"] == "shopify"
    )
    assert shopify_channel["status"] == "recommended"
    assert shopify_channel["integration_connection_id"] is None
    channel_gaps = [gap for gap in body["gaps"] if gap["gap_type"] == "channel"]
    assert any(gap["stage_from"] == "purchase" for gap in channel_gaps)


async def test_funnel_goal_and_decision_insufficient_data_coupling(
    client: AsyncClient, tenant: dict
) -> None:
    goal = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/goals",
        headers=tenant["headers"],
        json={
            "period_start": "2020-01-01T00:00:00Z",
            "period_end": "2099-01-01T00:00:00Z",
            "maximum_cpa": "20.00",
            "target_roas": "2.00",
            "currency": "USD",
        },
    )
    assert goal.status_code == 201, goal.text
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    positioning = await _positioning(client, tenant, base)
    decision = await client.post(
        f"{base}/decisions/evaluate",
        headers=tenant["headers"],
        json={"candidate_type": "positioning", "candidate_id": positioning["id"]},
    )
    assert decision.status_code == 201, decision.text
    decision_status = decision.json()["status"]
    generated = await client.post(
        f"{base}/funnel/generate",
        headers=tenant["headers"],
        json={"strategy_decision_id": decision.json()["id"]},
    )
    assert generated.status_code == 201, generated.text
    body = generated.json()
    snapshot = body["input_snapshot"]
    assert snapshot["strategy_decision_id"] == decision.json()["id"]
    assert snapshot["strategy_decision_status"] == decision_status
    assert snapshot["business_goal"]["status"] == "available"
    assert snapshot["business_goal"]["maximum_cpa"] == "20.00"
    if decision_status == "insufficient_data":
        decision_gaps = [gap for gap in body["gaps"] if gap["gap_type"] == "decision"]
        assert any(gap["severity"] == "medium" for gap in decision_gaps)
        assert body["status"] != "recommended"


async def test_funnel_messaging_anchor_and_variant_support(
    client: AsyncClient, tenant: dict
) -> None:
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    positioning = await _positioning(client, tenant, base)
    messaging = await client.post(
        f"{base}/messaging/generate",
        headers=tenant["headers"],
        json={"positioning_candidate_id": positioning["id"]},
    )
    assert messaging.status_code == 201, messaging.text
    generated = await client.post(
        f"{base}/funnel/generate",
        headers=tenant["headers"],
        json={
            "variant": "content_led",
            "positioning_candidate_id": positioning["id"],
            "messaging_strategy_id": messaging.json()["id"],
        },
    )
    assert generated.status_code == 201, generated.text
    body = generated.json()
    assert body["variant"] == "content_led"
    snapshot = body["input_snapshot"]
    assert snapshot["messaging_strategy_id"] == messaging.json()["id"]
    assert snapshot["messaging_status"] == messaging.json()["status"]
    assert not any(gap["gap_type"] == "variant_signal" for gap in body["gaps"])
    awareness = next(stage for stage in body["stages"] if stage["stage"] == "awareness")
    assert awareness["cta_type"] is None
    assert stages_have_no_evidence(body)


def stages_have_no_evidence(body: dict) -> bool:
    return all(stage["evidence_refs"] == [] for stage in body["stages"])


async def test_funnel_versions_and_provenance(
    session: AsyncSession, client: AsyncClient, tenant: dict
) -> None:
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    research = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/research/sources",
        headers=tenant["headers"],
        json={
            "source_type": "review",
            "title": "Customer review",
            "url": "https://example.test/review",
            "content": "Original review text.",
        },
    )
    assert research.status_code == 201, research.text
    evidence = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/research/evidence",
        headers=tenant["headers"],
        json={
            "source_id": research.json()["id"],
            "evidence_type": "pain_point",
            "statement": "Manual reports take hours.",
            "confidence": "observed",
        },
    )
    assert evidence.status_code == 201, evidence.text
    positioning = await client.post(
        f"{base}/positioning/candidates",
        headers=tenant["headers"],
        json={
            "name": "Evidence positioning",
            "target_customer": "Busy owners",
            "problem": "Manual work",
            "solution": "Structured workflows",
            "promise": "Clarity",
            "classification": "observed",
            "evidence_ids": [evidence.json()["id"]],
        },
    )
    assert positioning.status_code == 201, positioning.text
    first = await client.post(
        f"{base}/funnel/generate",
        headers=tenant["headers"],
        json={"positioning_candidate_id": positioning.json()["id"]},
    )
    second = await client.post(
        f"{base}/funnel/generate",
        headers=tenant["headers"],
        json={"positioning_candidate_id": positioning.json()["id"]},
    )
    assert first.status_code == 201 and second.status_code == 201
    first_body, second_body = first.json(), second.json()
    assert first_body["version"] == 1 and second_body["version"] == 2
    assert first_body["input_snapshot"]["evidence_ids"]
    assert first_body["input_snapshot"]["positioning_candidate_id"] == positioning.json()["id"]

    versions = await client.get(f"{base}/funnel/versions", headers=tenant["headers"])
    assert versions.status_code == 200
    assert [row["version"] for row in versions.json()["versions"]] == [2, 1]

    fetched = await client.get(f"{base}/funnel/{first_body['id']}", headers=tenant["headers"])
    assert fetched.status_code == 200
    assert fetched.json()["id"] == first_body["id"]

    latest = await client.get(f"{base}/funnel", headers=tenant["headers"])
    assert latest.status_code == 200
    assert latest.json()["version"] == 2

    provenance = await client.get(
        f"{base}/funnel/{first_body['id']}/provenance", headers=tenant["headers"]
    )
    assert provenance.status_code == 200
    assert provenance.json()["funnel_strategy_id"] == first_body["id"]
    assert provenance.json()["provenance"]


async def test_funnel_not_found_and_cross_tenant_isolation(
    session: AsyncSession, client: AsyncClient, tenant: dict
) -> None:
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    missing = await client.get(f"{base}/funnel", headers=tenant["headers"])
    assert missing.status_code == 404

    product = await _product(session, tenant)
    offer = await client.post(
        f"{base}/offers/candidates",
        headers=tenant["headers"],
        json={"name": "Private offer", "product_id": str(product.id)},
    )
    assert offer.status_code == 201, offer.text
    generated = await client.post(f"{base}/funnel/generate", headers=tenant["headers"], json={})
    assert generated.status_code == 201, generated.text

    foreign = await create_tenant(session)
    stolen = await client.post(
        f"/api/v1/businesses/{foreign['business'].id}/strategy/funnel/generate",
        headers=foreign["headers"],
        json={"offer_candidate_id": offer.json()["id"]},
    )
    assert stolen.status_code == 404
    denied = await client.get(
        f"/api/v1/businesses/{foreign['business'].id}/strategy/funnel/{generated.json()['id']}",
        headers=foreign["headers"],
    )
    assert denied.status_code == 404


async def test_funnel_generate_requires_write_permission(
    client: AsyncClient, tenant: dict, session: AsyncSession
) -> None:
    from conftest import auth_headers, create_membership, create_role, create_user

    user = await create_user(session)
    org = tenant["org"]
    role = await create_role(
        session, name="viewer", organization_id=org.id, permissions=["business:read"]
    )
    await create_membership(session, user=user, organization=org, role=role)
    await session.commit()
    headers = await auth_headers(session, user, org.id)
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    response = await client.post(f"{base}/funnel/generate", headers=headers, json={})
    assert response.status_code == 403
