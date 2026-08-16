"""Recommendations API integration tests (Phase 4B).

End-to-end coverage of the deterministic decision endpoints: list + summary
counters, server-side filter validation (422), entity filters that resolve
inside the business (404 on foreign ids), per-campaign decision endpoint,
cross-tenant 404s, idempotent generation (recompute never duplicates rows),
money serialized as strings and the review-only contract (decisions only,
no action keys).

Seed: the standard tenant (see test_metrics module docstring for the exact
arithmetic contract). Conversions 8 vs purchases 4 → the metrics layer fires
provider_conversion_mismatch, so every decision in the seeded business is
`tracking_issue` (precedence 1) — deterministic and stable.
"""

import uuid

from conftest import create_tenant
from httpx import AsyncClient
from sqlalchemy import func, select
from test_metrics import _seed_standard_tenant

from src.db.models import Recommendation

RECOMMENDATIONS_URL = "/api/v1/businesses/{business_id}/recommendations"
SUMMARY_URL = "/api/v1/businesses/{business_id}/recommendations/summary"
GENERATE_URL = "/api/v1/businesses/{business_id}/recommendations/generate"
CAMPAIGN_URL = "/api/v1/businesses/{business_id}/campaigns/{campaign_id}/recommendation"


async def _fetch(client: AsyncClient, headers: dict, business_id, **params) -> dict:
    response = await client.get(
        RECOMMENDATIONS_URL.format(business_id=business_id),
        headers=headers,
        params=params,
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# List + summary
# ---------------------------------------------------------------------------


async def test_recommendations_list_returns_review_decisions(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)
    data = await _fetch(client, tenant["headers"], tenant["business"].id)

    assert data["business_id"] == str(tenant["business"].id)
    assert data["currency"] == "USD"
    assert data["range"]["kind"] == "last_30_days"
    assert data["summary"]["total"] == len(data["decisions"]) == 3  # business + 2 campaigns
    assert data["summary"]["by_entity_type"] == {"business": 1, "campaign": 2}

    for decision in data["decisions"]:
        assert decision["id"]
        assert decision["business_id"] == str(tenant["business"].id)
        # Seeded business has a conversion mismatch → tracking_issue always
        assert decision["decision"] == "tracking_issue"
        assert decision["evidence_strength"] in {"insufficient", "weak", "moderate", "strong"}
        assert decision["primary_reason"]
        assert decision["rules_version"] == "1.0"
        assert decision["range"]["kind"] == "last_30_days"
        assert decision["evidence"]["primary_reason"]
        assert isinstance(decision["review_suggestions"], list)
        for suggestion in decision["review_suggestions"]:
            assert suggestion.startswith(("review_", "test_"))
        # Review-only contract: decisions never contain action keys
        assert "action" not in decision
        assert "execute" not in decision

    business_ids = {d["entity_type"] for d in data["decisions"]}
    assert business_ids == {"business", "campaign"}


async def test_recommendations_summary_matches_list(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)
    data = await _fetch(client, tenant["headers"], tenant["business"].id)

    response = await client.get(
        SUMMARY_URL.format(business_id=tenant["business"].id),
        headers=tenant["headers"],
    )
    assert response.status_code == 200, response.text
    summary = response.json()

    assert summary["business_id"] == str(tenant["business"].id)
    assert summary["total"] == data["summary"]["total"] == 3
    assert summary["tracking_issue"] == 3
    assert summary["by_decision"]["tracking_issue"] == 3
    assert summary["by_entity_type"] == {"business": 1, "campaign": 2}
    for key in ("scale_review", "optimize", "maintain", "kill_review",
                "learning", "insufficient_data", "tracking_issue", "data_quality_issue"):
        assert summary[key] == summary["by_decision"][key]


# ---------------------------------------------------------------------------
# Filters (server-side validation)
# ---------------------------------------------------------------------------


async def test_filter_by_entity_type(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)
    data = await _fetch(
        client, tenant["headers"], tenant["business"].id, entity_type="business"
    )
    assert data["summary"]["total"] == 1
    assert {d["entity_type"] for d in data["decisions"]} == {"business"}


async def test_filter_by_decision_type(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)
    data = await _fetch(
        client, tenant["headers"], tenant["business"].id, decision="tracking_issue"
    )
    assert data["summary"]["total"] == 3
    assert {d["decision"] for d in data["decisions"]} == {"tracking_issue"}


async def test_filter_by_entity_id_resolves_inside_business(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session)
    stack = await _seed_standard_tenant(session, tenant)
    campaign_id = stack["campaigns"][0].id
    data = await _fetch(
        client, tenant["headers"], tenant["business"].id,
        entity_type="campaign", entity_id=str(campaign_id),
    )
    assert data["summary"]["total"] == 1
    assert data["decisions"][0]["entity_type"] == "campaign"
    assert data["decisions"][0]["entity_id"] == str(campaign_id)


async def test_filter_by_foreign_entity_id_is_404(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)
    other = await create_tenant(session)
    other_stack = await _seed_standard_tenant(session, other)
    foreign_id = other_stack["campaigns"][0].id

    response = await client.get(
        RECOMMENDATIONS_URL.format(business_id=tenant["business"].id),
        headers=tenant["headers"],
        params={
            "entity_type": "campaign",
            "entity_id": str(foreign_id),
        },
    )
    assert response.status_code == 404


async def test_invalid_filter_values_are_422(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)
    for params in (
        {"entity_type": "ad"},
        {"decision": "delete_campaign"},
        {"severity": "ultra"},
    ):
        response = await client.get(
            RECOMMENDATIONS_URL.format(business_id=tenant["business"].id),
            headers=tenant["headers"],
            params=params,
        )
        assert response.status_code == 422, (params, response.text)


# ---------------------------------------------------------------------------
# Per-campaign endpoint
# ---------------------------------------------------------------------------


async def test_campaign_recommendation_returns_campaign_decision(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session)
    stack = await _seed_standard_tenant(session, tenant)
    campaign_id = stack["campaigns"][0].id

    response = await client.get(
        CAMPAIGN_URL.format(
            business_id=tenant["business"].id, campaign_id=campaign_id
        ),
        headers=tenant["headers"],
    )
    assert response.status_code == 200, response.text
    decision = response.json()

    assert decision["entity_type"] == "campaign"
    assert decision["entity_id"] == str(campaign_id)
    assert decision["business_id"] == str(tenant["business"].id)
    assert decision["decision"] == "tracking_issue"
    # Campaign grain has no purchase attribution
    assert decision["metrics_snapshot"]["purchases"] is None
    assert decision["metrics_snapshot"]["cpa"] is None


async def test_campaign_recommendation_unknown_campaign_is_404(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)
    response = await client.get(
        CAMPAIGN_URL.format(
            business_id=tenant["business"].id, campaign_id=uuid.uuid4()
        ),
        headers=tenant["headers"],
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Generate (idempotent persistence)
# ---------------------------------------------------------------------------


async def test_generate_persists_idempotently(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)
    headers = tenant["headers"]
    business_id = tenant["business"].id

    first = await client.post(
        GENERATE_URL.format(business_id=business_id), headers=headers, json={}
    )
    assert first.status_code == 200, first.text
    first_data = first.json()
    assert first_data["summary"]["total"] == 3

    rows = (await session.execute(select(func.count(Recommendation.id)))).scalar_one()
    assert rows == 3

    # Recompute: same deterministic fingerprints → upsert, never duplicate
    second = await client.post(
        GENERATE_URL.format(business_id=business_id), headers=headers, json={}
    )
    assert second.status_code == 200, second.text
    second_data = second.json()
    assert second_data["summary"]["total"] == 3
    assert {d["id"] for d in first_data["decisions"]} == {
        d["id"] for d in second_data["decisions"]
    }
    rows = (await session.execute(select(func.count(Recommendation.id)))).scalar_one()
    assert rows == 3


async def test_generate_with_custom_range(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)
    from datetime import UTC, datetime, timedelta

    end = datetime.now(UTC).date()
    start = end - timedelta(days=7)
    response = await client.post(
        GENERATE_URL.format(business_id=tenant["business"].id),
        headers=tenant["headers"],
        json={"range_kind": "custom", "date_from": str(start), "date_to": str(end)},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["range"]["kind"] == "custom"
    assert data["range"]["start"] == str(start)


# ---------------------------------------------------------------------------
# Money + review-only contract on the wire
# ---------------------------------------------------------------------------


async def test_money_serialized_as_strings(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)
    data = await _fetch(client, tenant["headers"], tenant["business"].id)

    business_decision = next(
        d for d in data["decisions"] if d["entity_type"] == "business"
    )
    snapshot = business_decision["metrics_snapshot"]
    assert snapshot["spend"] == "1000.00"
    assert snapshot["impressions"] == "2000"
    assert snapshot["conversions"] == "8"
    assert isinstance(snapshot["spend"], str)
    assert isinstance(snapshot["conversions"], str)

    for item in business_decision["evidence"]["evidence_items"]:
        if item["metric"] and item["metric"]["current"] is not None:
            assert isinstance(item["metric"]["current"], str)
        if item["threshold"]:
            assert isinstance(item["threshold"]["value"], str)

    # Business KPIs from the seed contract, never invented by the engine
    assert snapshot["purchases"] == "4"
    assert snapshot["roas"] == "1.2000"
    assert snapshot["cpa"] == "250.00"