"""Recommendations tenancy isolation tests (Phase 4B, spec §41).

Every recommendations endpoint resolves business_id server-side from the
authenticated tenant context: cross-tenant business paths return 404 (never
403 which would leak existence), cross-tenant campaign ids return 404, and
generate/persist operations are scoped to the owning business only.
"""


from conftest import create_tenant
from httpx import AsyncClient
from test_metrics import _seed_standard_tenant

RECOMMENDATIONS_URL = "/api/v1/businesses/{business_id}/recommendations"
SUMMARY_URL = "/api/v1/businesses/{business_id}/recommendations/summary"
GENERATE_URL = "/api/v1/businesses/{business_id}/recommendations/generate"
CAMPAIGN_URL = "/api/v1/businesses/{business_id}/campaigns/{campaign_id}/recommendation"


async def test_cross_tenant_business_is_404(client: AsyncClient, session) -> None:
    first = await create_tenant(session)
    await _seed_standard_tenant(session, first)
    second = await create_tenant(session)

    for url in (RECOMMENDATIONS_URL, SUMMARY_URL, GENERATE_URL):
        response = await client.request(
            "POST" if url == GENERATE_URL else "GET",
            url.format(business_id=first["business"].id),
            headers=second["headers"],
            json={} if url == GENERATE_URL else None,
        )
        assert response.status_code == 404, (url, response.text)


async def test_cross_tenant_campaign_is_404(client: AsyncClient, session) -> None:
    first = await create_tenant(session)
    await _seed_standard_tenant(session, first)
    second = await create_tenant(session)
    second_stack = await _seed_standard_tenant(session, second)

    response = await client.get(
        CAMPAIGN_URL.format(
            business_id=first["business"].id,
            campaign_id=second_stack["campaigns"][0].id,
        ),
        headers=first["headers"],
    )
    assert response.status_code == 404


async def test_foreign_entity_filter_is_404(client: AsyncClient, session) -> None:
    first = await create_tenant(session)
    await _seed_standard_tenant(session, first)
    second = await create_tenant(session)
    second_stack = await _seed_standard_tenant(session, second)

    response = await client.get(
        RECOMMENDATIONS_URL.format(business_id=first["business"].id),
        headers=first["headers"],
        params={
            "entity_type": "campaign",
            "entity_id": str(second_stack["campaigns"][0].id),
        },
    )
    assert response.status_code == 404


async def test_own_data_visible_after_other_tenant_generates(
    client: AsyncClient, session
) -> None:
    """Persisted decisions of one tenant never leak into another's API."""
    first = await create_tenant(session)
    first_stack = await _seed_standard_tenant(session, first)
    second = await create_tenant(session)
    await _seed_standard_tenant(session, second)

    # Only tenant B calls generate — tenant A's business must be unaffected
    response = await client.post(
        GENERATE_URL.format(business_id=second["business"].id),
        headers=second["headers"],
        json={},
    )
    assert response.status_code == 200, response.text

    response = await client.get(
        RECOMMENDATIONS_URL.format(business_id=first["business"].id),
        headers=first["headers"],
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["business_id"] == str(first["business"].id)
    # Tenant A's decisions are computed against its own campaigns only
    assert data["summary"]["by_entity_type"] == {"business": 1, "campaign": 2}
    entity_ids = {d["entity_id"] for d in data["decisions"] if d["entity_type"] == "campaign"}
    assert entity_ids == {str(c.id) for c in first_stack["campaigns"]}


async def test_unauthenticated_request_is_401(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)
    for url in (RECOMMENDATIONS_URL, SUMMARY_URL, GENERATE_URL):
        response = await client.request(
            "POST" if url == GENERATE_URL else "GET",
            url.format(business_id=tenant["business"].id),
            json={} if url == GENERATE_URL else None,
        )
        assert response.status_code == 401, (url, response.text)