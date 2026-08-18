"""Phase 6C deterministic intelligence API tests."""

from __future__ import annotations

import uuid

from conftest import create_tenant
from httpx import AsyncClient
from sqlalchemy import select

from src.db.models import ResearchEvidence


def _url(business_id: uuid.UUID, path: str) -> str:
    return f"/api/v1/businesses/{business_id}/research/intelligence/{path}"


async def _seed_project_source_evidence(
    client: AsyncClient,
    session,
    tenant: dict,
    *,
    source_type: str = "website",
    evidence_type: str = "pricing",
    statement: str = "Product price is SAR 100.",
    structured_value: dict | None = None,
    competitor_id: str | None = None,
) -> tuple[dict, dict, dict]:
    project = (
        await client.post(
            f"/api/v1/businesses/{tenant['business'].id}/research/projects",
            json={"name": f"Project {uuid.uuid4()}", "type": "mixed"},
            headers=tenant["headers"],
        )
    ).json()
    source = (
        await client.post(
            f"/api/v1/businesses/{tenant['business'].id}/research/sources",
            json={
                "source_type": source_type,
                "title": f"Source {uuid.uuid4()}",
                "url": f"https://example-{uuid.uuid4().hex}.test",
                "content": statement,
                "competitor_id": competitor_id,
            },
            headers=tenant["headers"],
        )
    ).json()
    evidence = (
        await client.post(
            f"/api/v1/businesses/{tenant['business'].id}/research/evidence",
            json={
                "source_id": source["id"],
                "evidence_type": evidence_type,
                "statement": statement,
                "structured_value": structured_value,
            },
            headers=tenant["headers"],
        )
    ).json()
    snapshot_id = await session.scalar(
        select(ResearchEvidence.snapshot_id).where(ResearchEvidence.id == uuid.UUID(evidence["id"]))
    )
    # Manual evidence is intentionally backward-compatible with Phase 6A;
    # this test associates it with the project and exact source snapshot as
    # collection-generated evidence does.
    row = await session.get(ResearchEvidence, uuid.UUID(evidence["id"]))
    row.research_project_id = uuid.UUID(project["id"])
    row.snapshot_id = snapshot_id or uuid.UUID(
        source["id"]
    )  # replaced below when a snapshot exists
    source_detail = await client.get(
        f"/api/v1/businesses/{tenant['business'].id}/research/sources/{source['id']}",
        headers=tenant["headers"],
    )
    row.snapshot_id = uuid.UUID(source_detail.json()["snapshots"][0]["id"])
    await session.commit()
    return project, source, evidence


async def test_market_pricing_currency_isolation_and_provenance(tenant, client, session):
    first = await _seed_project_source_evidence(
        client,
        session,
        tenant,
        structured_value={"price": "100", "currency": "SAR"},
    )
    project_id = first[0]["id"]
    await _seed_project_source_evidence(
        client,
        session,
        tenant,
        structured_value={"price": "200", "currency": "SAR"},
    )
    response = await client.get(_url(tenant["business"].id, "pricing"), headers=tenant["headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pricing"]["currencies"]["SAR"]["observation_count"] == 2
    assert body["pricing"]["currencies"]["SAR"]["median"] is None
    assert body["items"]
    assert body["items"][0]["provenance"][0]["snapshot_id"]
    project_response = await client.get(
        _url(tenant["business"].id, f"market?research_project_id={project_id}"),
        headers=tenant["headers"],
    )
    assert project_response.status_code == 200


async def test_customer_repeated_reviews_are_strong_and_competitor_copy_is_not_customer(
    tenant, client, session
):
    for _ in range(3):
        await _seed_project_source_evidence(
            client,
            session,
            tenant,
            source_type="review",
            evidence_type="pain_point",
            statement="Shipping took too long.",
        )
    competitor = (
        await client.post(
            f"/api/v1/businesses/{tenant['business'].id}/research/competitors",
            json={"name": "Competitor", "domain": "competitor.example"},
            headers=tenant["headers"],
        )
    ).json()
    await _seed_project_source_evidence(
        client,
        session,
        tenant,
        source_type="website",
        evidence_type="pain_point",
        statement="Customers love fast shipping.",
        competitor_id=competitor["id"],
    )
    response = await client.get(_url(tenant["business"].id, "customer"), headers=tenant["headers"])
    assert response.status_code == 200
    items = response.json()["items"]
    pain = next(item for item in items if item["statement"] == "Shipping took too long.")
    assert pain["strength"] == "strong"
    assert all(item["statement"] != "Customers love fast shipping." for item in items)


async def test_competitor_intelligence_and_cross_tenant_isolation(tenant, client, session):
    competitor = (
        await client.post(
            f"/api/v1/businesses/{tenant['business'].id}/research/competitors",
            json={"name": "Acme", "domain": "acme.example"},
            headers=tenant["headers"],
        )
    ).json()
    await _seed_project_source_evidence(
        client,
        session,
        tenant,
        evidence_type="positioning",
        statement="We make delivery simple.",
        competitor_id=competitor["id"],
    )
    response = await client.get(
        _url(tenant["business"].id, f"competitors/{competitor['id']}"),
        headers=tenant["headers"],
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["category"] == "positioning"
    other = await create_tenant(session)
    denied = await client.get(
        _url(tenant["business"].id, f"competitors/{competitor['id']}"),
        headers=other["headers"],
    )
    assert denied.status_code == 404


async def test_summary_reports_missing_research_areas(tenant, client, session):
    response = await client.get(_url(tenant["business"].id, "summary"), headers=tenant["headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["missing_research_areas"]
    assert body["coverage"]["total"] == 9
    assert body["intelligence_version"] == "research_intelligence_v1"
