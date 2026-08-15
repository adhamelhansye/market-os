"""Diagnostics endpoints integration tests (Phase 3B).

Covers the deterministic analytics diagnostics API end-to-end: structured
findings with evidence and translation keys, stable fingerprints, filter
semantics (severity/category/entity_type/entity_id/status), summary
counters, per-campaign diagnostics with performance state + scaling
readiness, cross-tenant 404s, unknown-entity 404s, filter validation 422s
and money serialized as strings.

Seed contract (shared with metrics tests): a connected Meta account with
two campaigns; business totals impressions 2000, clicks 100, spend 1000.00,
conversions 8, revenue 1250.00, purchases 4 — conversions vs purchases
mismatch (8 vs 4 → 100% ≥ 50%) so provider_conversion_mismatch fires.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from conftest import create_tenant
from httpx import AsyncClient
from test_metrics import (
    _days_ago,
    _insight,
    _seed_standard_tenant,
    _today,
)

from src.db.models import IntegrationConnection, SyncRun

DIAGNOSTICS_URL = "/api/v1/businesses/{business_id}/diagnostics"
CAMPAIGN_DIAGNOSTICS_URL = "/api/v1/businesses/{business_id}/campaigns/{campaign_id}/diagnostics"


async def _fetch(client: AsyncClient, headers: dict, business_id, **params) -> dict:
    response = await client.get(
        DIAGNOSTICS_URL.format(business_id=business_id), headers=headers, params=params
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _seed_tiny_campaign(session, business, stack, day: date) -> None:
    """Adds a tiny campaign (below sample minima) for insufficient_data."""
    await _insight(
        session, business, stack, campaign_index=1, day=day,
        impressions=12, clicks=2, spend="5.00", reach=10,
        link_clicks=2, landing_page_views=1,
    )


async def _seed_sync_failure(session, business, connection: IntegrationConnection) -> None:
    session.add(
        SyncRun(
            connection_id=connection.id,
            resource_type="insights",
            status="failed",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            records_processed=0,
            error_summary="provider timeout",
            cursor=None,
        )
    )
    await session.commit()


# ---------------------------------------------------------------------------
# Main endpoint
# ---------------------------------------------------------------------------


async def test_diagnostics_returns_findings_with_evidence(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)
    data = await _fetch(client, tenant["headers"], tenant["business"].id)

    assert data["business_id"] == str(tenant["business"].id)
    assert data["currency"] == "USD"
    assert data["range"]["kind"] == "last_30_days"
    assert data["summary"]["total_findings"] == len(data["findings"])
    assert data["summary"]["affected_entities"] >= 1

    codes = {f["code"] for f in data["findings"]}
    assert "provider_conversion_mismatch" in codes
    assert "break_even_unavailable" in codes

    mismatch = next(f for f in data["findings"] if f["code"] == "provider_conversion_mismatch")
    assert mismatch["entity_type"] == "business"
    assert mismatch["severity"] == "low"
    assert mismatch["status"] == "detected"
    assert mismatch["title_key"] == "diagnostics.provider_conversion_mismatch.title"
    assert mismatch["description_key"] == "diagnostics.provider_conversion_mismatch.description"
    assert mismatch["evidence"]["threshold"]["code"] == "conversion_mismatch_percent"
    assert mismatch["evidence"]["threshold"]["value"] == "50"
    assert mismatch["evidence"]["metric"]["code"] == "conversions"
    assert mismatch["evidence"]["metric"]["current"] == "8"
    assert mismatch["range"]["kind"] == "last_30_days"

    for finding in data["findings"]:
        assert finding["id"]
        assert finding["business_id"] == str(tenant["business"].id)
        assert finding["code"]
        assert finding["category"]
        assert finding["severity"] in {"info", "low", "medium", "high", "critical"}
        assert finding["status"] in {"detected", "resolved", "insufficient_data"}
        assert finding["title_key"].startswith("diagnostics.")
        assert finding["description_key"].startswith("diagnostics.")


async def test_diagnostics_fingerprints_stable_within_range(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)
    first = await _fetch(client, tenant["headers"], tenant["business"].id)
    second = await _fetch(client, tenant["headers"], tenant["business"].id)
    assert sorted(f["id"] for f in first["findings"]) == sorted(f["id"] for f in second["findings"])


async def test_diagnostics_custom_range(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)
    data = await _fetch(
        client, tenant["headers"], tenant["business"].id,
        date_from=_days_ago(7), date_to=_today().isoformat(),
    )
    assert data["range"]["kind"] == "custom"
    assert data["range"]["start"].startswith(_days_ago(7))


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


async def test_diagnostics_filter_by_severity_category_entity(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session)
    stack = await _seed_standard_tenant(session, tenant)

    info_only = await _fetch(
        client, tenant["headers"], tenant["business"].id, severity="info"
    )
    assert all(f["severity"] == "info" for f in info_only["findings"])
    assert info_only["summary"]["total_findings"] == len(info_only["findings"])

    tracking = await _fetch(
        client, tenant["headers"], tenant["business"].id, category="tracking"
    )
    assert all(f["category"] == "tracking" for f in tracking["findings"])
    assert {f["code"] for f in tracking["findings"]} == {"provider_conversion_mismatch"}

    campaign_id = stack["campaigns"][0].id
    campaign_only = await _fetch(
        client, tenant["headers"], tenant["business"].id,
        entity_type="campaign", entity_id=str(campaign_id),
    )
    assert all(f["entity_type"] == "campaign" for f in campaign_only["findings"])
    assert all(str(f["entity_id"]) == str(campaign_id) for f in campaign_only["findings"])
    assert len(campaign_only["campaign_states"]) == 1
    assert str(campaign_only["campaign_states"][0]["campaign_id"]) == str(campaign_id)


async def test_diagnostics_unknown_filter_values_422(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)
    response = await client.get(
        DIAGNOSTICS_URL.format(business_id=tenant["business"].id),
        headers=tenant["headers"],
        params={"severity": "catastrophic"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_diagnostics_filter"

    response = await client.get(
        DIAGNOSTICS_URL.format(business_id=tenant["business"].id),
        headers=tenant["headers"],
        params={"entity_type": "organization"},
    )
    assert response.status_code == 422


async def test_diagnostics_filter_foreign_campaign_404(client: AsyncClient, session) -> None:
    tenant_a = await create_tenant(session)
    await _seed_standard_tenant(session, tenant_a)
    tenant_b = await create_tenant(session)
    stack_b = await _seed_standard_tenant(session, tenant_b)

    response = await client.get(
        DIAGNOSTICS_URL.format(business_id=tenant_a["business"].id),
        headers=tenant_a["headers"],
        params={
            "entity_type": "campaign",
            "entity_id": str(stack_b["campaigns"][0].id),
        },
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"

    response = await client.get(
        DIAGNOSTICS_URL.format(business_id=tenant_a["business"].id),
        headers=tenant_a["headers"],
        params={"entity_type": "campaign", "entity_id": "not-a-uuid"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Insufficient-data semantics
# ---------------------------------------------------------------------------


async def test_diagnostics_insufficient_data_visible(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    stack = await _seed_standard_tenant(session, tenant)
    await _seed_tiny_campaign(session, tenant["business"], stack, _today() - timedelta(days=2))
    await session.commit()

    data = await _fetch(
        client, tenant["headers"], tenant["business"].id, status="insufficient_data"
    )
    assert data["findings"], "tiny campaign must produce insufficient_data findings"
    assert all(f["status"] == "insufficient_data" for f in data["findings"])
    codes = {f["code"] for f in data["findings"]}
    assert codes & {"low_ctr", "high_cpc", "high_cpa"}

    detected = await _fetch(
        client, tenant["headers"], tenant["business"].id, status="detected"
    )
    assert all(f["status"] == "detected" for f in detected["findings"])
    assert all(f["code"] != "high_cpc" or f["severity"] != "info" for f in detected["findings"])


# ---------------------------------------------------------------------------
# Sync-failure and data-quality findings
# ---------------------------------------------------------------------------


async def test_diagnostics_recent_sync_failure_finding(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)
    business = tenant["business"]
    connection = IntegrationConnection(
        business_id=business.id,
        provider="meta",
        status="connected",
        external_account_id="act_999888777",
        external_account_name="Sync Test Account",
        scopes=["ads_read"],
        provider_metadata={},
        connected_at=datetime.now(UTC),
        last_sync_at=datetime.now(UTC),
    )
    session.add(connection)
    await session.flush()
    await _seed_sync_failure(session, business, connection)

    data = await _fetch(client, tenant["headers"], business.id)
    codes = {f["code"] for f in data["findings"]}
    assert "recent_sync_failures" in codes
    failure = next(f for f in data["findings"] if f["code"] == "recent_sync_failures")
    assert failure["severity"] == "low"


# ---------------------------------------------------------------------------
# Summary endpoint
# ---------------------------------------------------------------------------


async def test_diagnostics_summary_endpoint(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)
    data = await _fetch(client, tenant["headers"], tenant["business"].id)
    response = await client.get(
        f"{DIAGNOSTICS_URL.format(business_id=tenant['business'].id)}/summary",
        headers=tenant["headers"],
    )
    assert response.status_code == 200
    summary = response.json()
    assert summary == data["summary"]
    for key in ("total_findings", "critical", "high", "medium", "low", "info",
                "insufficient_data", "affected_entities"):
        assert key in summary


# ---------------------------------------------------------------------------
# Per-campaign diagnostics
# ---------------------------------------------------------------------------


async def test_campaign_diagnostics_endpoint(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    stack = await _seed_standard_tenant(session, tenant)
    campaign = stack["campaigns"][0]
    response = await client.get(
        CAMPAIGN_DIAGNOSTICS_URL.format(
            business_id=tenant["business"].id, campaign_id=campaign.id
        ),
        headers=tenant["headers"],
    )
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["business_id"] == str(tenant["business"].id)
    assert data["campaign"]["id"] == str(campaign.id)
    assert data["campaign"]["name"] == "Campaign 1"
    assert data["campaign"]["spend"] == "100.00"
    assert data["performance_state"] in {
        "insufficient_data", "learning", "healthy", "attention",
        "inefficient", "profitable", "unprofitable", "stale_data",
    }
    readiness = data["scaling_readiness"]
    assert readiness["status"] in {
        "insufficient_data", "learning", "stable",
        "performance_positive", "performance_negative",
    }
    assert isinstance(readiness["ready_for_review"], bool)
    assert isinstance(readiness["gates"], list)
    assert data["data_quality"]["provider"] == "meta"
    for finding in data["findings"]:
        assert finding["entity_type"] == "campaign"
        assert str(finding["entity_id"]) == str(campaign.id)


async def test_campaign_diagnostics_healthier_campaign(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    stack = await _seed_standard_tenant(session, tenant)
    campaign = stack["campaigns"][0]
    data = await _tenant_campaign(client, tenant, campaign.id)
    assert data["performance_state"] in {"learning", "profitable", "healthy", "attention"}


async def _tenant_campaign(client, tenant, campaign_id) -> dict:
    response = await client.get(
        CAMPAIGN_DIAGNOSTICS_URL.format(
            business_id=tenant["business"].id, campaign_id=campaign_id
        ),
        headers=tenant["headers"],
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_campaign_diagnostics_unknown_campaign_404(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)
    for campaign_id in (uuid.uuid4(), "not-a-uuid"):
        response = await client.get(
            CAMPAIGN_DIAGNOSTICS_URL.format(
                business_id=tenant["business"].id, campaign_id=campaign_id
            ),
            headers=tenant["headers"],
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


async def test_campaign_diagnostics_foreign_campaign_404(client: AsyncClient, session) -> None:
    tenant_a = await create_tenant(session)
    await _seed_standard_tenant(session, tenant_a)
    tenant_b = await create_tenant(session)
    stack_b = await _seed_standard_tenant(session, tenant_b)
    response = await client.get(
        CAMPAIGN_DIAGNOSTICS_URL.format(
            business_id=tenant_a["business"].id, campaign_id=stack_b["campaigns"][0].id
        ),
        headers=tenant_a["headers"],
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


# ---------------------------------------------------------------------------
# Tenancy and authorization
# ---------------------------------------------------------------------------


async def test_diagnostics_cross_tenant_404(client: AsyncClient, session) -> None:
    tenant_a = await create_tenant(session)
    await _seed_standard_tenant(session, tenant_a)
    tenant_b = await create_tenant(session)
    response = await client.get(
        DIAGNOSTICS_URL.format(business_id=tenant_a["business"].id),
        headers=tenant_b["headers"],
    )
    assert response.status_code == 404


async def test_diagnostics_requires_business_read_permission(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session, permissions=["business:write"])
    await _seed_standard_tenant(session, tenant)
    response = await client.get(
        DIAGNOSTICS_URL.format(business_id=tenant["business"].id),
        headers=tenant["headers"],
    )
    assert response.status_code == 403