"""Metrics layer integration tests (Phase 3A).

Covers the canonical metric_facts view end-to-end: aggregation correctness
(weighted ratios never averaged), zero-vs-unavailable semantics, currency
isolation, funnel shapes, entity rollups, data quality, period comparisons,
tenancy isolation and the HTTP API contract (money serialized as strings).

Seed arithmetic contract (see _seed_standard_tenant):
  campaign 1: 1000 impressions, 10 clicks, spend 100, conversions 3, conv value 300
  campaign 2: 1000 impressions, 90 clicks, spend 900, conversions 5, conv value 900
  orders: 500.00 (2x Alpha), 300.00 (1x Beta), 400.00 (2x Beta), 50.00 refunded (1x Alpha)

Totals: impressions 2000, clicks 100, spend 1000.00, revenue 1250.00
(paid + refunded order totals), refunds 50.00, purchases 4.
Ratios (always from totals, never averaged):
  ctr 100/2000 = 0.05  cpc 10.00  cpm 500.00  cvr 4/100 = 0.04
  cpa 1000/4 = 250.00  aov 1250/4 = 312.50
  roas (Meta att) 1200/1000 = 1.2   mer 1250/1000 = 1.25
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from conftest import create_tenant
from httpx import AsyncClient

from src.core.config import get_settings
from src.db.models import (
    Ad,
    AdAccount,
    AdInsight,
    AdSet,
    Campaign,
    IntegrationConnection,
    IntegrationCredential,
    Order,
    OrderItem,
    Product,
)
from src.modules.integrations.credentials import TokenCipher
from src.modules.metrics.kpi_engine import STATUS_AVAILABLE, STATUS_UNAVAILABLE

PROVIDER_META = "meta"
PROVIDER_SHOPIFY = "shopify"


def _today() -> date:
    return datetime.now(UTC).date()


async def _connected(session, business, *, provider: str) -> IntegrationConnection:
    settings = get_settings()
    connection = IntegrationConnection(
        business_id=business.id,
        provider=provider,
        status="connected",
        external_account_id="act_111222333" if provider == "meta" else "shop.myshopify.com",
        external_account_name="Test Account",
        scopes=["ads_read"] if provider == "meta" else ["read_orders"],
        provider_metadata={},
        connected_at=datetime.now(UTC),
        last_sync_at=datetime.now(UTC),
    )
    session.add(connection)
    await session.flush()
    cipher = TokenCipher.from_settings(settings)
    session.add(
        IntegrationCredential(
            connection_id=connection.id,
            access_token_encrypted=cipher.encrypt("test-token"),
        )
    )
    await session.flush()
    return connection


async def _ad_stack(session, business, *, currency: str = "USD") -> dict:
    """One connected Meta account with two campaigns; returns entity refs."""
    connection = await _connected(session, business, provider="meta")
    account = AdAccount(
        business_id=business.id,
        integration_connection_id=connection.id,
        external_id="111222333",
        name="Test Account",
        currency=currency,
        timezone="UTC",
        status="ACTIVE",
    )
    session.add(account)
    await session.flush()

    campaigns = []
    ad_sets = []
    ads = []
    for index in (1, 2):
        campaign = Campaign(
            business_id=business.id,
            ad_account_id=account.id,
            external_id=f"camp{index}",
            name=f"Campaign {index}",
            status="ACTIVE",
        )
        session.add(campaign)
        await session.flush()
        campaigns.append(campaign)
        ad_set = AdSet(
            business_id=business.id,
            ad_account_id=account.id,
            campaign_id=campaign.id,
            external_id=f"set{index}",
            name=f"Ad Set {index}",
            status="ACTIVE",
        )
        session.add(ad_set)
        await session.flush()
        ad_sets.append(ad_set)
        ad = Ad(
            business_id=business.id,
            ad_account_id=account.id,
            campaign_id=campaign.id,
            ad_set_id=ad_set.id,
            external_id=f"ad{index}",
            name=f"Ad {index}",
            status="ACTIVE",
        )
        session.add(ad)
        await session.flush()
        ads.append(ad)
    return {"account": account, "campaigns": campaigns, "ad_sets": ad_sets, "ads": ads}


async def _insight(
    session,
    business,
    stack: dict,
    *,
    campaign_index: int,
    day: date,
    impressions: int = 1000,
    clicks: int = 10,
    spend: str = "10.00",
    conversions: int | None = None,
    conversion_value: str | None = None,
    reach: int = 900,
    link_clicks: int | None = 8,
    landing_page_views: int | None = 6,
) -> AdInsight:
    ad = stack["ads"][campaign_index - 1]
    insight = AdInsight(
        business_id=business.id,
        ad_account_id=stack["account"].id,
        campaign_id=ad.campaign_id,
        ad_set_id=ad.ad_set_id,
        ad_id=ad.id,
        provider=PROVIDER_META,
        date=day,
        grain="daily",
        currency=stack["account"].currency,
        impressions=impressions,
        reach=reach,
        clicks=clicks,
        link_clicks=link_clicks,
        landing_page_views=landing_page_views,
        spend=Decimal(spend),
        conversions=conversions,
        conversion_value=Decimal(conversion_value) if conversion_value else None,
    )
    session.add(insight)
    await session.flush()
    return insight


async def _product(session, business, *, name: str, sku: str) -> Product:
    product = Product(business_id=business.id, name=name, sku=sku, status="active")
    session.add(product)
    await session.flush()
    return product


async def _order(
    session,
    business,
    *,
    total: str,
    day: date,
    currency: str = "USD",
    financial_status: str = "paid",
    items: list[tuple[Product, int, str]] | None = None,
) -> Order:
    order = Order(
        business_id=business.id,
        external_id=f"o-{uuid.uuid4().hex[:10]}",
        source=PROVIDER_SHOPIFY,
        currency=currency,
        subtotal=Decimal(total),
        discount_total=Decimal("0"),
        shipping_revenue=Decimal("0"),
        tax_total=None,
        total=Decimal(total),
        financial_status=financial_status,
        fulfillment_status=None,
        ordered_at=datetime.combine(day, datetime.min.time(), tzinfo=UTC),
    )
    session.add(order)
    await session.flush()
    for product, quantity, line_total in items or []:
        session.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                external_product_id=f"p-{product.id}",
                quantity=quantity,
                unit_price=Decimal(line_total) / quantity,
                discount_amount=Decimal("0"),
                line_total=Decimal(line_total),
            )
        )
    await session.flush()
    return order


async def _seed_standard_tenant(session, tenant: dict) -> dict:
    """Seeds the documented arithmetic contract (module docstring)."""
    business = tenant["business"]
    stack = await _ad_stack(session, business)
    day = _today() - timedelta(days=3)
    await _insight(
        session, business, stack, campaign_index=1, day=day,
        impressions=1000, clicks=10, spend="100.00",
        conversions=3, conversion_value="300.00",
    )
    await _insight(
        session, business, stack, campaign_index=2, day=day,
        impressions=1000, clicks=90, spend="900.00",
        conversions=5, conversion_value="900.00",
    )
    p_alpha = await _product(session, business, name="Alpha", sku="A-1")
    p_beta = await _product(session, business, name="Beta", sku="B-1")
    await _order(session, business, total="500.00", day=day, items=[(p_alpha, 2, "500.00")])
    await _order(session, business, total="300.00", day=day, items=[(p_beta, 1, "300.00")])
    await _order(session, business, total="400.00", day=day, items=[(p_beta, 2, "400.00")])
    await _order(
        session, business, total="50.00", day=day,
        financial_status="refunded", items=[(p_alpha, 1, "50.00")],
    )
    await session.commit()
    return stack


def _days_ago(n: int) -> str:
    return str(_today() - timedelta(days=n))


# ---------------------------------------------------------------------------
# Summary: aggregation correctness
# ---------------------------------------------------------------------------


async def test_summary_weighted_kpis(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)
    business = tenant["business"]
    r = await client.get(
        f"/api/v1/businesses/{business.id}/metrics/summary",
        params={"range_kind": "custom", "start": _days_ago(5), "end": _days_ago(1)},
        headers=tenant["headers"],
    )
    assert r.status_code == 200
    body = r.json()

    # Weighted ratios from totals — never an average of per-campaign ratios.
    assert body["impressions"] == {"value": 2000, "status": STATUS_AVAILABLE, "reason": None}
    assert body["clicks"]["value"] == 100
    assert body["purchases"]["value"] == 4
    assert body["revenue"]["value"] == "1250.00"
    assert body["refunds"]["value"] == "50.00"
    assert Decimal(body["ctr"]["value"]) == Decimal("0.05")
    assert body["cpc"]["value"] == "10.00"
    assert body["cpm"]["value"] == "500.00"
    assert Decimal(body["cvr"]["value"]) == Decimal("0.04")
    assert body["cpa"]["value"] == "250.00"
    assert body["aov"]["value"] == "312.50"
    assert Decimal(body["roas"]["value"]) == Decimal("1.2")  # Meta-reported attributed value
    assert Decimal(body["mer"]["value"]) == Decimal("1.25")  # commerce revenue / spend
    # Source provenance labels stay apart.
    assert body["roas"]["status"] == STATUS_AVAILABLE
    assert body["revenue"]["source"] == "commerce"


async def test_summary_zero_vs_unavailable(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    business = tenant["business"]
    await session.commit()
    r = await client.get(
        f"/api/v1/businesses/{business.id}/metrics/summary",
        headers=tenant["headers"],
    )
    assert r.status_code == 200
    body = r.json()
    # No facts at all: measures are unavailable with reasons — never zeros.
    assert body["revenue"]["value"] is None
    assert body["revenue"]["status"] == STATUS_UNAVAILABLE
    assert body["revenue"]["reason"] == "no commerce data in period"
    assert body["spend"]["status"] == STATUS_UNAVAILABLE
    assert body["spend"]["reason"] == "no advertising data in period"
    assert body["ctr"]["status"] == STATUS_UNAVAILABLE
    assert body["roas"]["status"] == STATUS_UNAVAILABLE
    # Money measures still carry currency/source metadata.
    assert body["revenue"]["currency"] == "USD"
    assert body["revenue"]["source"] == "commerce"


async def test_summary_currency_isolation(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    business = tenant["business"]
    stack = await _ad_stack(session, business, currency="EUR")
    await _insight(
        session, business, stack, campaign_index=1, day=_today() - timedelta(days=2),
        impressions=5000, clicks=500, spend="500.00",
    )
    await _order(
        session, business, total="999.00", day=_today() - timedelta(days=2), currency="EUR"
    )
    await session.commit()
    r = await client.get(
        f"/api/v1/businesses/{business.id}/metrics/summary",
        params={"range_kind": "last_7_days"},
        headers=tenant["headers"],
    )
    assert r.status_code == 200
    body = r.json()
    # EUR rows are excluded from the USD business totals, never converted.
    assert body["impressions"]["value"] is None
    assert body["revenue"]["value"] is None
    assert body["revenue"]["reason"] == "no commerce data in period"


async def test_summary_refunds_counted_separately(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session)
    business = tenant["business"]
    day = _today() - timedelta(days=1)
    await _order(session, business, total="100.00", day=day)
    await _order(session, business, total="40.00", day=day, financial_status="refunded")
    await session.commit()
    r = await client.get(
        f"/api/v1/businesses/{business.id}/metrics/summary",
        params={"range_kind": "last_7_days"},
        headers=tenant["headers"],
    )
    body = r.json()
    # Revenue counts order totals (paid + refunded); refunds are reported
    # separately so net can be derived without ever fabricating numbers.
    assert body["revenue"]["value"] == "140.00"
    assert body["refunds"]["value"] == "40.00"
    assert body["purchases"]["value"] == 2


# ---------------------------------------------------------------------------
# Timeseries / funnel
# ---------------------------------------------------------------------------


async def test_timeseries_points_only_for_facts(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session)
    business = tenant["business"]
    stack = await _ad_stack(session, business)
    today = _today()
    day1 = today - timedelta(days=4)
    day2 = today - timedelta(days=3)
    await _insight(
        session, business, stack, campaign_index=1, day=day1,
        impressions=1000, clicks=10, spend="10.00",
    )
    await _order(session, business, total="77.00", day=day2)
    await session.commit()
    r = await client.get(
        f"/api/v1/businesses/{business.id}/metrics/timeseries",
        params={"range_kind": "custom", "start": _days_ago(6), "end": _days_ago(1)},
        headers=tenant["headers"],
    )
    assert r.status_code == 200
    points = r.json()["points"]
    assert [p["date"] for p in points] == [str(day1), str(day2)]
    assert points[0]["impressions"] == 1000
    assert points[0]["spend"] == "10.00"
    assert points[0]["revenue"] is None
    assert points[1]["revenue"] == "77.00"
    assert points[1]["impressions"] is None


async def test_funnel_stage_order_and_unobserved(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)
    business = tenant["business"]
    r = await client.get(
        f"/api/v1/businesses/{business.id}/metrics/funnel",
        params={"range_kind": "custom", "start": _days_ago(5), "end": _days_ago(1)},
        headers=tenant["headers"],
    )
    assert r.status_code == 200
    stages = r.json()["stages"]
    assert [s["metric"] for s in stages] == [
        "impressions", "clicks", "landing_page_views",
        "product_views", "add_to_cart", "checkout_started", "purchases",
    ]
    by_metric = {s["metric"]: s for s in stages}
    assert by_metric["impressions"]["value"] == 2000
    assert by_metric["clicks"]["value"] == 100
    # Unobserved intent metrics are unavailable, never zero.
    for metric in ("product_views", "add_to_cart", "checkout_started"):
        stage = by_metric[metric]
        assert stage["value"] is None
        assert stage["status"] == STATUS_UNAVAILABLE
        assert stage["reason"] == "no provider reports this metric"
        assert stage["conversion_rate"]["status"] == STATUS_UNAVAILABLE
    # Conversion rates relate a stage to the one BEFORE it.
    assert Decimal(by_metric["clicks"]["conversion_rate"]["value"]) == Decimal("0.05")  # 100/2000
    lpv_conversion = by_metric["landing_page_views"]["conversion_rate"]["value"]  # 12/100
    assert Decimal(lpv_conversion) == Decimal("0.12")
    # The last chain never fabricates a path through unobserved intent
    # stages: purchases conversion (vs checkout_started) is unavailable.
    assert by_metric["purchases"]["conversion_rate"]["status"] == STATUS_UNAVAILABLE


# ---------------------------------------------------------------------------
# Entity rollups
# ---------------------------------------------------------------------------


async def test_campaign_rollups_no_purchase_attribution(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)
    business = tenant["business"]
    r = await client.get(
        f"/api/v1/businesses/{business.id}/metrics/campaigns",
        params={"range_kind": "custom", "start": _days_ago(5), "end": _days_ago(1)},
        headers=tenant["headers"],
    )
    assert r.status_code == 200
    campaigns = {c["name"]: c for c in r.json()["campaigns"]}
    c1 = campaigns["Campaign 1"]
    c2 = campaigns["Campaign 2"]
    # Per-campaign facts (ad grain only; no commerce at this grain).
    assert c1["impressions"] == 1000
    assert c1["spend"] == "100.00"
    assert Decimal(c1["ctr"]["value"]) == Decimal("0.01")
    assert Decimal(c1["roas"]["value"]) == Decimal("3")  # Meta-reported conversion value
    assert Decimal(c2["roas"]["value"]) == Decimal("1")
    # Purchase attribution does not exist at this grain.
    for campaign in (c1, c2):
        assert campaign["cvr"]["status"] == STATUS_UNAVAILABLE
        assert campaign["cvr"]["reason"] == "no purchase attribution at this grain"
        assert campaign["aov"]["status"] == STATUS_UNAVAILABLE
        assert campaign["revenue_source"] == "meta_reported"


async def test_ad_sets_filtered_by_campaign(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    stack = await _seed_standard_tenant(session, tenant)
    business = tenant["business"]
    campaign_id = stack["campaigns"][0].id
    r = await client.get(
        f"/api/v1/businesses/{business.id}/metrics/adsets",
        params={
            "range_kind": "custom",
            "start": _days_ago(5),
            "end": _days_ago(1),
            "campaign_id": str(campaign_id),
        },
        headers=tenant["headers"],
    )
    assert r.status_code == 200
    ad_sets = r.json()["ad_sets"]
    assert len(ad_sets) == 1
    assert ad_sets[0]["name"] == "Ad Set 1"
    assert ad_sets[0]["campaign_id"] == str(campaign_id)


async def test_foreign_campaign_filter_is_404(client: AsyncClient, session) -> None:
    tenant_a = await create_tenant(session)
    tenant_b = await create_tenant(session)
    stack = await _ad_stack(session, tenant_a["business"])
    await session.commit()
    foreign_campaign = stack["campaigns"][0].id
    r = await client.get(
        f"/api/v1/businesses/{tenant_b['business'].id}/metrics/adsets",
        params={"campaign_id": str(foreign_campaign)},
        headers=tenant_b["headers"],
    )
    # Unknown entity within the authorized business -> 404, never data.
    assert r.status_code == 404


async def test_ads_rollup(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)
    business = tenant["business"]
    r = await client.get(
        f"/api/v1/businesses/{business.id}/metrics/ads",
        params={"range_kind": "custom", "start": _days_ago(5), "end": _days_ago(1)},
        headers=tenant["headers"],
    )
    assert r.status_code == 200
    ads = r.json()["ads"]
    assert len(ads) == 2
    by_name = {a["name"]: a for a in ads}
    assert by_name["Ad 1"]["spend"] == "100.00"
    assert by_name["Ad 1"]["cpc"]["value"] == "10.00"
    assert by_name["Ad 2"]["cpc"]["value"] == "10.00"


async def test_products_units_revenue_aov(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)
    business = tenant["business"]
    r = await client.get(
        f"/api/v1/businesses/{business.id}/metrics/products",
        params={"range_kind": "custom", "start": _days_ago(5), "end": _days_ago(1)},
        headers=tenant["headers"],
    )
    assert r.status_code == 200
    products = {p["name"]: p for p in r.json()["products"]}
    alpha = products["Alpha"]
    # Alpha sold qty 2 (@500) in a paid order + qty 1 (@50) in a refunded order.
    assert alpha["units"] == 3
    assert alpha["revenue"] == "550.00"
    assert alpha["aov"]["value"] == "183.33"
    assert alpha["contribution_margin"]["status"] == STATUS_UNAVAILABLE
    beta = products["Beta"]
    assert beta["units"] == 3
    assert beta["revenue"] == "700.00"
    assert beta["aov"]["value"] == "233.33"


# ---------------------------------------------------------------------------
# Data quality
# ---------------------------------------------------------------------------


async def test_data_quality_fresh(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    business = tenant["business"]
    stack = await _ad_stack(session, business)
    await _insight(
        session, business, stack, campaign_index=1, day=_today() - timedelta(days=1),
        impressions=100, clicks=1, spend="1.00",
    )
    await _order(session, business, total="10.00", day=_today() - timedelta(days=1))
    await session.commit()
    r = await client.get(
        f"/api/v1/businesses/{business.id}/metrics/data-quality",
        params={"range_kind": "last_7_days"},
        headers=tenant["headers"],
    )
    assert r.status_code == 200
    providers = {p["provider"]: p for p in r.json()["providers"]}
    assert providers[PROVIDER_META]["freshness_status"] == "fresh"
    assert providers[PROVIDER_META]["connected"] is True
    assert providers[PROVIDER_META]["covered_days"] == 1
    assert providers[PROVIDER_META]["missing_days"] == 6
    assert providers[PROVIDER_SHOPIFY]["freshness_status"] == "fresh"


async def test_data_quality_not_connected(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    business = tenant["business"]
    await session.commit()
    r = await client.get(
        f"/api/v1/businesses/{business.id}/metrics/data-quality",
        headers=tenant["headers"],
    )
    assert r.status_code == 200
    providers = {p["provider"]: p for p in r.json()["providers"]}
    for provider in (PROVIDER_META, PROVIDER_SHOPIFY):
        assert providers[provider]["freshness_status"] == "unavailable"
        assert providers[provider]["reason"] == "not connected"
        assert providers[provider]["connected"] is False


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


async def test_comparison_current_vs_previous(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    business = tenant["business"]
    today = _today()
    current_start, current_end = today - timedelta(days=4), today - timedelta(days=2)
    previous_end = today - timedelta(days=5)
    stack = await _ad_stack(session, business)
    await _insight(
        session, business, stack, campaign_index=1, day=current_end,
        impressions=1000, clicks=10, spend="100.00",
    )
    await _order(session, business, total="150.00", day=current_end)
    await _order(session, business, total="100.00", day=previous_end)
    await session.commit()
    r = await client.get(
        f"/api/v1/businesses/{business.id}/metrics/comparison",
        params={"range_kind": "custom", "start": current_start, "end": current_end},
        headers=tenant["headers"],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["revenue"]["current"] == "150.00"
    assert body["revenue"]["previous"] == "100.00"
    assert body["revenue"]["absolute_change"] == "50.00"
    assert body["revenue"]["percentage_change"]["status"] == STATUS_AVAILABLE
    assert body["revenue"]["percentage_change"]["value"] == "50.00"
    # Spend had no previous period -> percent unavailable.
    assert body["spend"]["current"] == "100.00"
    assert body["spend"]["previous"] is None
    assert body["spend"]["percentage_change"]["status"] == STATUS_UNAVAILABLE
    assert body["spend"]["percentage_change"]["reason"] == "no previous period data"


async def test_comparison_previous_zero_percent_unavailable(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session)
    business = tenant["business"]
    today = _today()
    current_start, current_end = today - timedelta(days=4), today - timedelta(days=2)
    previous_day = today - timedelta(days=6)
    await _order(session, business, total="0.00", day=previous_day)
    await _order(session, business, total="150.00", day=current_end)
    await session.commit()
    r = await client.get(
        f"/api/v1/businesses/{business.id}/metrics/comparison",
        params={"range_kind": "custom", "start": current_start, "end": current_end},
        headers=tenant["headers"],
    )
    body = r.json()
    # Previous-period revenue is a real zero: percent change is unavailable,
    # never a fabricated percentage.
    assert body["revenue"]["current"] == "150.00"
    assert body["revenue"]["previous"] == "0.00"
    assert body["revenue"]["percentage_change"]["status"] == STATUS_UNAVAILABLE
    assert body["revenue"]["percentage_change"]["reason"] == "previous period is zero"


# ---------------------------------------------------------------------------
# API contract: ranges, tenancy, permissions, money serialization
# ---------------------------------------------------------------------------


async def test_unknown_range_kind_422(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    business = tenant["business"]
    await session.commit()
    r = await client.get(
        f"/api/v1/businesses/{business.id}/metrics/summary",
        params={"range_kind": "last_decade"},
        headers=tenant["headers"],
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_metrics_range"


async def test_custom_range_requires_dates(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    business = tenant["business"]
    await session.commit()
    r = await client.get(
        f"/api/v1/businesses/{business.id}/metrics/summary",
        params={"range_kind": "custom"},
        headers=tenant["headers"],
    )
    assert r.status_code == 422


async def test_cross_tenant_business_404(client: AsyncClient, session) -> None:
    tenant_a = await create_tenant(session)
    tenant_b = await create_tenant(session)
    await session.commit()
    r = await client.get(
        f"/api/v1/businesses/{tenant_a['business'].id}/metrics/summary",
        headers=tenant_b["headers"],
    )
    assert r.status_code == 404


async def test_requires_business_read_permission(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session, permissions=["business:manage"])
    business = tenant["business"]
    await session.commit()
    r = await client.get(
        f"/api/v1/businesses/{business.id}/metrics/summary",
        headers=tenant["headers"],
    )
    assert r.status_code == 403


async def test_money_serialized_as_string(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    business = tenant["business"]
    await _order(session, business, total="12.30", day=_today() - timedelta(days=1))
    await session.commit()
    r = await client.get(
        f"/api/v1/businesses/{business.id}/metrics/summary",
        params={"range_kind": "last_7_days"},
        headers=tenant["headers"],
    )
    body = r.json()
    value = body["revenue"]["value"]
    assert isinstance(value, str)
    assert value == "12.30"
    # Counts stay numbers.
    assert body["purchases"]["value"] == 1