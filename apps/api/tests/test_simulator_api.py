"""Simulator API tests (Phase 5A).

End-to-end through the FastAPI app: deterministic numbers on a seeded
7-day history, idempotency via assumptions_hash, rerun semantics,
campaign scoping, and cross-tenant isolation (404, never a leak).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import delete

from src.db.models import AdInsight
from tests.conftest import create_tenant
from tests.test_metrics import (
    _ad_stack,
    _insight,
    _order,
    _product,
    _today,
)


def _days_ago(n: int) -> str:
    return str(_today() - timedelta(days=n))


async def _seed_constant_history(session, tenant: dict, *, days: int = 7) -> dict:
    """7+ days of constant funnel + one paid order per day.

    Totals: impressions 1000/day, clicks 10/day, spend 100/day,
    purchases 1/day, revenue 400/day. Ratios: CTR 0.01, CPC 10.00,
    CPM 100.00, CVR 0.1, CPA 100.00, AOV 400.00.
    """
    business = tenant["business"]
    stack = await _ad_stack(session, business)
    product = await _product(session, business, name="Widget", sku="W-1")
    for offset in range(days, 0, -1):
        day = _today() - timedelta(days=offset)
        await _insight(
            session,
            business,
            stack,
            campaign_index=1,
            day=day,
            impressions=1000,
            clicks=10,
            spend="100.00",
        )
        await _order(session, business, total="400.00", day=day, items=[(product, 1, "400.00")])
    await session.commit()
    return stack


async def _create_simulation(client: AsyncClient, tenant: dict, **overrides) -> dict:
    payload = {
        "budget": "1000",
        "duration_days": 30,
        "historical_window_days": 7,
        "target_cpa": "120.00",
        **overrides,
    }
    r = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/simulations",
        headers=tenant["headers"],
        json=payload,
    )
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Auth / validation
# ---------------------------------------------------------------------------


async def test_simulations_require_auth(client: AsyncClient, tenant) -> None:
    r = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/simulations", json={"budget": "1000"}
    )
    assert r.status_code == 401


async def test_create_rejects_invalid_inputs(client: AsyncClient, tenant) -> None:
    url = f"/api/v1/businesses/{tenant['business'].id}/simulations"
    assert (
        await client.post(url, headers=tenant["headers"], json={"budget": "0"})
    ).status_code == 422
    assert (
        await client.post(
            url,
            headers=tenant["headers"],
            json={"budget": "1000", "historical_window_days": 31},
        )
    ).status_code == 422
    assert (
        await client.post(
            url,
            headers=tenant["headers"],
            json={"budget": "1000", "overrides": {"ctr": "1.5"}},
        )
    ).status_code == 422


# ---------------------------------------------------------------------------
# Deterministic arithmetic
# ---------------------------------------------------------------------------


async def test_create_deterministic_numbers(client: AsyncClient, session, tenant) -> None:
    await _seed_constant_history(session, tenant)
    body = await _create_simulation(client, tenant)

    assert body["model_used"] == "cpm_ctr_cvr_aov"
    assert body["calculation_path"] == (
        "budget → impressions → clicks → purchases → revenue → contribution_profit"
    )
    assert body["model_version"]
    assert body["assumptions_hash"]
    assert body["currency"] == "USD"
    assert body["entity_type"] == "business"
    assert body["entity_id"] is None

    expected = body["scenarios"]["expected"]
    assert expected["available"] is True
    m = expected["metrics"]
    assert m["impressions"] == 10000.0
    assert m["clicks"] == 100.0
    assert m["purchases"] == 10.0
    assert m["ctr"] == "0.0100"
    assert m["cpc"] == "10.00"
    assert m["cpm"] == "100.00"
    assert m["cvr"] == "0.1000"
    assert m["cpa"] == "100.00"
    assert m["aov"] == "400.00"
    assert m["revenue"] == "4000.00"
    assert Decimal(m["roas"]) == Decimal("4.0")
    assert m["net_revenue"] == "4000.00"

    # 7 observation days → identical daily constants → all tails equal
    assert set(body["scenarios"]) == {"downside", "expected", "upside"}
    for level in ("downside", "upside"):
        assert body["scenarios"][level]["available"] is True
        assert body["scenarios"][level]["metrics"]["revenue"] == "4000.00"

    # no unit economics → profitability unavailable, never fabricated
    assert body["profitability"]["status"] == "unavailable"
    assert body["profitability"]["reason"] == "no_contribution_profit"

    assert body["data_quality"] == "weak"
    assert body["evidence_strength"] == "weak"

    assumptions = {a["name"]: a for a in body["assumptions"]}
    assert assumptions["budget"]["value"] == "1000.00"
    assert assumptions["budget"]["source"] == "user_input"
    assert assumptions["ctr"]["source"] == "business_history"
    assert assumptions["ctr"]["historical_value"] == "0.0100"
    assert assumptions["contribution_profit_per_order"]["value"] is None
    assert assumptions["contribution_profit_per_order"]["source"] == "system_default"

    targets = {t["metric_code"]: t for t in body["targets"]}
    assert targets["cpa"]["status"] == "met"
    assert targets["cpa"]["target_value"] == "120.00"
    assert targets["roas"]["status"] == "unavailable"
    assert targets["roas"]["reason"] == "missing_target_or_simulation"

    variables = [t["variable"] for t in body["sensitivity"]]
    assert variables == ["ctr", "cpm", "cvr", "aov", "budget"]


async def test_create_idempotent_and_hash_sensitive(client: AsyncClient, session, tenant) -> None:
    await _seed_constant_history(session, tenant)
    first = await _create_simulation(client, tenant)
    second = await _create_simulation(client, tenant)
    assert first["id"] == second["id"]
    assert first["assumptions_hash"] == second["assumptions_hash"]

    changed = await _create_simulation(client, tenant, budget="2000")
    assert changed["id"] != first["id"]
    assert changed["scenarios"]["expected"]["metrics"]["revenue"] == "8000.00"


# ---------------------------------------------------------------------------
# Read paths
# ---------------------------------------------------------------------------


async def test_list_and_get(client: AsyncClient, session, tenant) -> None:
    await _seed_constant_history(session, tenant)
    body = await _create_simulation(client, tenant)

    listing = await client.get(
        f"/api/v1/businesses/{tenant['business'].id}/simulations",
        headers=tenant["headers"],
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["simulations"][0]["id"] == body["id"]

    detail = await client.get(
        f"/api/v1/businesses/{tenant['business'].id}/simulations/{body['id']}",
        headers=tenant["headers"],
    )
    assert detail.status_code == 200
    assert detail.json()["id"] == body["id"]
    assert detail.json()["scenarios"]["expected"]["metrics"]["revenue"] == "4000.00"
    # snapshots are persisted alongside the response
    assert set(detail.json()["results_snapshot"]) >= {
        "model_used",
        "scenarios",
        "reasons",
    }
    assert len(detail.json()["assumptions_snapshot"]) == len(body["assumptions"])


async def test_get_unknown_simulation_404(client: AsyncClient, tenant) -> None:
    r = await client.get(
        f"/api/v1/businesses/{tenant['business'].id}/simulations/"
        "00000000-0000-0000-0000-000000000000",
        headers=tenant["headers"],
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Rerun
# ---------------------------------------------------------------------------


async def test_rerun_returns_same_row_when_history_unchanged(
    client: AsyncClient, session, tenant
) -> None:
    await _seed_constant_history(session, tenant)
    body = await _create_simulation(client, tenant)
    refreshed = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/simulations/{body['id']}/rerun",
        headers=tenant["headers"],
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["id"] == body["id"]
    assert refreshed.json()["assumptions_hash"] == body["assumptions_hash"]


async def test_rerun_reflects_new_history(client: AsyncClient, session, tenant) -> None:
    stack = await _seed_constant_history(session, tenant)
    body = await _create_simulation(client, tenant)

    # strengthen one day inside the window: replace yesterday's insight
    # with a much better one (10x clicks) and add a large order so
    # totals now reflect 8 ad rows / 9 purchases
    day = _today() - timedelta(days=1)
    ad_id = stack["ads"][0].id
    await session.execute(
        delete(AdInsight).where(
            AdInsight.ad_id == ad_id,
            AdInsight.date == day,
        )
    )
    await _insight(
        session,
        tenant["business"],
        stack,
        campaign_index=1,
        day=day,
        impressions=1000,
        clicks=100,
        spend="100.00",
    )
    product = await _product(session, tenant["business"], name="Bulk", sku="B-1")
    await _order(
        session,
        tenant["business"],
        total="4000.00",
        day=day,
        items=[(product, 10, "4000.00")],
    )
    await session.commit()

    refreshed = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/simulations/{body['id']}/rerun",
        headers=tenant["headers"],
    )
    assert refreshed.status_code == 200
    refreshed_body = refreshed.json()
    # history changed → new assumptions_hash → fresh row (upsert probe)
    assert refreshed_body["id"] != body["id"]
    assert refreshed_body["assumptions_hash"] != body["assumptions_hash"]
    # total clicks went from 70 to 160 → expected clicks must rise
    assert refreshed_body["scenarios"]["expected"]["metrics"]["clicks"] > 100.0


# ---------------------------------------------------------------------------
# Campaign scope
# ---------------------------------------------------------------------------


async def test_campaign_simulation_scopes_entity(client: AsyncClient, session, tenant) -> None:
    stack = await _seed_constant_history(session, tenant)
    campaign = stack["campaigns"][0]
    payload = {
        "budget": "500",
        "duration_days": 30,
        "historical_window_days": 7,
    }
    r = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/campaigns/{campaign.id}/simulate",
        headers=tenant["headers"],
        json=payload,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["entity_type"] == "campaign"
    assert body["entity_id"] == str(campaign.id)
    m = body["scenarios"]["expected"]["metrics"]
    # campaign series: same 7 days at half the budget
    assert m["revenue"] == "2000.00"
    assert m["cpa"] == "100.00"


# ---------------------------------------------------------------------------
# Tenancy isolation
# ---------------------------------------------------------------------------


async def test_foreign_business_is_404(client: AsyncClient, session, tenant) -> None:
    other = await create_tenant(session)
    await session.commit()
    url = f"/api/v1/businesses/{tenant['business'].id}/simulations"
    r = await client.post(url, headers=other["headers"], json={"budget": "1000"})
    assert r.status_code == 404
    r = await client.get(url, headers=other["headers"])
    assert r.status_code == 404


async def test_foreign_simulation_get_is_404(client: AsyncClient, session, tenant) -> None:
    await _seed_constant_history(session, tenant)
    body = await _create_simulation(client, tenant)
    other = await create_tenant(session)
    await session.commit()
    r = await client.get(
        f"/api/v1/businesses/{tenant['business'].id}/simulations/{body['id']}",
        headers=other["headers"],
    )
    assert r.status_code == 404


async def test_foreign_rerun_and_campaign_are_404(client: AsyncClient, session, tenant) -> None:
    stack = await _seed_constant_history(session, tenant)
    body = await _create_simulation(client, tenant)
    other = await create_tenant(session)
    await session.commit()
    rerun = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/simulations/{body['id']}/rerun",
        headers=other["headers"],
    )
    assert rerun.status_code == 404
    campaign = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/campaigns/{stack['campaigns'][0].id}/simulate",
        headers=other["headers"],
        json={"budget": "500"},
    )
    assert campaign.status_code == 404


async def test_foreign_business_does_not_leak_simulations(
    client: AsyncClient, session, tenant
) -> None:
    """A simulation created under A must never be visible under B's
    access to A's business id via a different organization header."""
    await _seed_constant_history(session, tenant)
    body = await _create_simulation(client, tenant)
    other = await create_tenant(session)
    await session.commit()
    listing = await client.get(
        f"/api/v1/businesses/{tenant['business'].id}/simulations",
        headers=other["headers"],
    )
    assert listing.status_code == 404
    detail = await client.get(
        f"/api/v1/businesses/{tenant['business'].id}/simulations/{body['id']}",
        headers=other["headers"],
    )
    assert detail.status_code == 404


async def test_agency_can_read_managed_business_simulations(
    client: AsyncClient, session, tenant
) -> None:
    agency = await create_tenant(session, org_type="agency", business_name="Agency")
    await session.commit()
    managed = await create_tenant(session, managed_by=agency["org"])
    await session.commit()
    await _seed_constant_history(session, managed)
    r = await client.get(
        f"/api/v1/businesses/{managed['business'].id}/simulations",
        headers=agency["headers"],
    )
    assert r.status_code == 200
    assert r.json()["total"] == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
