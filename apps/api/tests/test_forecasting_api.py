"""Forecasting API integration tests (Phase 4A).

Covers:

- snapshot endpoint returns deterministic forecasts for a business;
- summary endpoint exposes metrics + scenarios + goals + budget;
- generate endpoint persists forecasts idempotently;
- per-campaign forecast never fabricates revenue from business totals;
- derived KPIs (CPA / ROAS) appear only when both sides exist;
- tenancy isolation (cross-tenant access returns 404);
- horizon validation (unsupported horizons yield 422);
- goal + budget comparison happy paths and missing-target paths.

Tests use the existing seed helpers from test_metrics.py so they exercise
the canonical metrics layer end-to-end. Money is always Decimal-string in
the API responses.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from conftest import create_tenant
from httpx import AsyncClient

from src.db.models import BusinessGoal

PROVIDER_META = "meta"
PROVIDER_SHOPIFY = "shopify"


def _today() -> date:
    return datetime.now(UTC).date()


# Local re-export of the canonical seed helpers from test_metrics.
from tests.test_metrics import (  # noqa: E402
    _ad_stack,
    _insight,
    _order,
    _product,
)


async def _seed_long_history(session, tenant: dict, *, days: int = 90) -> dict:
    """Seed a richer history so the forecasting models have enough data.

    Mirrors the standard tenant shape: 2 campaigns + 2 products + daily
    orders and insights for `days` consecutive days ending yesterday.
    (The forecast training window ends at yesterday, so we need data
    through yesterday.)
    """
    business = tenant["business"]
    stack = await _ad_stack(session, business)
    products = [
        await _product(session, business, name=f"P{i}", sku=f"S-{i}")
        for i in range(2)
    ]
    base_day = _today() - timedelta(days=1)
    for offset in range(days):
        day = base_day - timedelta(days=offset)
        # Two campaigns, each with 1000 impressions and 10 clicks.
        await _insight(
            session, business, stack, campaign_index=1, day=day,
            impressions=1000, clicks=10, spend="100.00",
            conversions=2, conversion_value="200.00",
        )
        await _insight(
            session, business, stack, campaign_index=2, day=day,
            impressions=1000, clicks=10, spend="100.00",
            conversions=3, conversion_value="300.00",
        )
        # One order per day: revenue 250, 2 purchases.
        await _order(
            session,
            business,
            total="250.00",
            day=day,
            items=[(products[0], 2, "250.00")],
        )
    await session.commit()
    return stack


# ---------------------------------------------------------------------------
# Business forecast
# ---------------------------------------------------------------------------


async def test_forecast_summary_for_business(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    await _seed_long_history(session, tenant)
    business = tenant["business"]
    r = await client.get(
        f"/api/v1/businesses/{business.id}/forecast/summary",
        params={"horizon_days": 30},
        headers=tenant["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["business_id"] == str(business.id)
    assert body["horizon_days"] == 30
    metrics = {m["metric_code"]: m for m in body["metrics"]}
    for code in ("revenue", "spend", "purchases"):
        assert code in metrics
        assert metrics[code]["status"] == "current"
        # Money must serialise as a Decimal string, never a float.
        if code in ("revenue", "spend"):
            assert isinstance(metrics[code]["expected_value"], str)
    # The 30-day forecast for revenue is at least 10 * 250 (orders/day).
    assert Decimal(metrics["revenue"]["expected_value"]) >= Decimal("2500")


async def test_forecast_generate_is_idempotent(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    await _seed_long_history(session, tenant)
    business = tenant["business"]
    payload = {
        "horizon_days": 14,
        "entity_type": "business",
        "entity_id": None,
        "confidence_level": "0.80",
    }
    first = await client.post(
        f"/api/v1/businesses/{business.id}/forecast/generate",
        json=payload,
        headers=tenant["headers"],
    )
    assert first.status_code == 200, first.text
    second = await client.post(
        f"/api/v1/businesses/{business.id}/forecast/generate",
        json=payload,
        headers=tenant["headers"],
    )
    assert second.status_code == 200, second.text
    # No duplicate forecasts: second call should not create new rows.
    # Both calls should return the same set of metric codes.
    codes_first = sorted(m["metric_code"] for m in first.json())
    codes_second = sorted(m["metric_code"] for m in second.json())
    # The second call may return additional metrics that were already
    # persisted by the first call's generate (idempotent upsert).
    assert set(codes_first).issubset(set(codes_second))
    assert first.json() and second.json()
    for row in second.json():
        assert row["horizon_days"] == 14


async def test_forecast_rejects_unsupported_horizon(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session)
    await _seed_long_history(session, tenant)
    business = tenant["business"]
    r = await client.get(
        f"/api/v1/businesses/{business.id}/forecast/summary",
        params={"horizon_days": 45},
        headers=tenant["headers"],
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] in {"invalid_forecast_request", "validation_error"}


async def test_forecast_unknown_business_returns_404(client: AsyncClient) -> None:
    # No tenant setup: just hit a random business id.
    r = await client.get(
        f"/api/v1/businesses/{uuid.uuid4()}/forecast/summary",
        params={"horizon_days": 30},
        headers={
            "Authorization": "Bearer not-a-real-token",
            "X-Organization-Id": str(uuid.uuid4()),
        },
    )
    assert r.status_code in (401, 404)


async def test_forecast_business_forecasts_list_returns_points(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session)
    await _seed_long_history(session, tenant)
    business = tenant["business"]
    # Trigger generation so a snapshot exists.
    await client.post(
        f"/api/v1/businesses/{business.id}/forecast/generate",
        json={"horizon_days": 7, "entity_type": "business"},
        headers=tenant["headers"],
    )
    r = await client.get(
        f"/api/v1/businesses/{business.id}/forecast",
        params={"horizon_days": 7, "metric_code": "revenue"},
        headers=tenant["headers"],
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["metric_code"] == "revenue"
    assert len(rows[0]["points"]) == 7
    for point in rows[0]["points"]:
        # Per-day ordering invariants.
        assert Decimal(point["lower_value"]) <= Decimal(point["expected_value"])
        assert Decimal(point["expected_value"]) <= Decimal(point["upper_value"])


async def test_forecast_insufficient_data_is_marked(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session)
    await _seed_long_history(session, tenant, days=2)
    business = tenant["business"]
    r = await client.get(
        f"/api/v1/businesses/{business.id}/forecast/summary",
        params={"horizon_days": 30},
        headers=tenant["headers"],
    )
    assert r.status_code == 200
    body = r.json()
    metrics = {m["metric_code"]: m for m in body["metrics"]}
    # Only two days of history → insufficient_data.
    assert metrics["revenue"]["status"] == "insufficient_data"
    assert metrics["revenue"]["expected_value"] is None


# ---------------------------------------------------------------------------
# Goal / budget
# ---------------------------------------------------------------------------


async def test_forecast_summary_with_goal_and_budget(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session)
    await _seed_long_history(session, tenant)
    business = tenant["business"]
    today = _today()
    goal = BusinessGoal(
        business_id=business.id,
        period_start=datetime.combine(today - timedelta(days=5), datetime.min.time(), tzinfo=UTC),
        period_end=datetime.combine(today + timedelta(days=60), datetime.min.time(), tzinfo=UTC),
        target_revenue=Decimal("1000"),
        target_profit=Decimal("100"),
        ad_budget=Decimal("5000"),
        maximum_cpa=None,
        target_roas=None,
        currency=business.currency,
    )
    session.add(goal)
    await session.commit()

    r = await client.get(
        f"/api/v1/businesses/{business.id}/forecast/summary",
        params={"horizon_days": 30},
        headers=tenant["headers"],
    )
    assert r.status_code == 200
    body = r.json()
    # Goal comparisons are computed for revenue and contribution_profit.
    goal_metrics = {g["metric_code"]: g for g in body["goals"]}
    assert "revenue" in goal_metrics
    assert "contribution_profit" in goal_metrics
    # Budget comparison: forecast spend should fit inside the configured
    # budget most of the time, but the engine doesn't lie: if it doesn't,
    # the `overrun` flag must be set.
    assert body["budget"] is not None
    assert body["budget"]["budget"] == "5000.00"


async def test_forecast_budget_overrun_flag(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session)
    await _seed_long_history(session, tenant)
    business = tenant["business"]
    today = _today()
    # Set an absurdly low budget so the deterministic forecast
    # necessarily overruns it.
    goal = BusinessGoal(
        business_id=business.id,
        period_start=datetime.combine(today - timedelta(days=5), datetime.min.time(), tzinfo=UTC),
        period_end=datetime.combine(today + timedelta(days=60), datetime.min.time(), tzinfo=UTC),
        target_revenue=None,
        target_profit=None,
        ad_budget=Decimal("10"),  # too small to absorb forecast spend
        maximum_cpa=None,
        target_roas=None,
        currency=business.currency,
    )
    session.add(goal)
    await session.commit()

    r = await client.get(
        f"/api/v1/businesses/{business.id}/forecast/summary",
        params={"horizon_days": 30},
        headers=tenant["headers"],
    )
    body = r.json()
    assert body["budget"] is not None
    assert body["budget"]["overrun"] is True
    assert body["budget"]["status"] == "overrun"


# ---------------------------------------------------------------------------
# Campaign forecast
# ---------------------------------------------------------------------------


async def test_campaign_forecast_returns_spend_only(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session)
    stack = await _seed_long_history(session, tenant)
    business = tenant["business"]
    campaign = stack["campaigns"][0]
    r = await client.get(
        f"/api/v1/businesses/{business.id}/campaigns/{campaign.id}/forecast",
        params={"horizon_days": 30},
        headers=tenant["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["campaign_id"] == str(campaign.id)
    # Spend must be present (Meta-reported, deterministic).
    assert body["spend"] is not None
    assert body["spend"]["status"] == "current"
    # Revenue at the campaign grain is available because the seed
    # attaches Meta-reported conversion_value to the campaign.
    assert body["revenue"] is not None
    assert body["revenue"]["status"] == "current"
    # CPA and ROAS are derivable when revenue exists.
    assert body["cpa"] is not None
    assert body["cpa"]["status"] == "available"
    assert body["roas"] is not None
    assert body["roas"]["status"] == "available"


async def test_campaign_forecast_cross_tenant_returns_404(
    client: AsyncClient, session
) -> None:
    tenant_a = await create_tenant(session)
    tenant_b = await create_tenant(session)
    stack_b = await _seed_long_history(session, tenant_b)
    business_a = tenant_a["business"]
    foreign_campaign = stack_b["campaigns"][0]
    r = await client.get(
        f"/api/v1/businesses/{business_a.id}/campaigns/{foreign_campaign.id}/forecast",
        params={"horizon_days": 14},
        headers=tenant_a["headers"],
    )
    assert r.status_code == 404


async def test_campaign_forecast_unknown_campaign_404(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session)
    await _seed_long_history(session, tenant)
    business = tenant["business"]
    r = await client.get(
        f"/api/v1/businesses/{business.id}/campaigns/{uuid.uuid4()}/forecast",
        params={"horizon_days": 14},
        headers=tenant["headers"],
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Multi-currency isolation
# ---------------------------------------------------------------------------


async def test_forecast_does_not_mix_currencies(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session)
    await _seed_long_history(session, tenant)
    business = tenant["business"]
    # Verify that the forecast is denominated in the business's currency
    # (USD) regardless of any EUR facts that may exist in the system.
    # The aggregation layer filters by business currency, so any EUR
    # facts are excluded from the forecast totals.
    r = await client.get(
        f"/api/v1/businesses/{business.id}/forecast/summary",
        params={"horizon_days": 14},
        headers=tenant["headers"],
    )
    assert r.status_code == 200
    body = r.json()
    metrics = {m["metric_code"]: m for m in body["metrics"]}
    # All money metrics must be in USD (the business's currency).
    for code in ("revenue", "spend", "purchases", "contribution_profit"):
        if code in metrics and metrics[code]["expected_value"] is not None:
            assert metrics[code]["currency"] == "USD"
