"""Research module API tests (Phase 6A).

Covers project creation, tenancy isolation, RBAC, competitor creation,
source creation + content-hash dedup, evidence creation, finding
creation, provenance, deterministic classification, filters, search,
status transitions, cross-tenant access, malformed input and duplicate
records.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import (
    create_tenant,
)


def _url(business_id, *parts) -> str:
    return f"/api/v1/businesses/{business_id}/research/" + "/".join(parts)


async def _create_project(client: AsyncClient, headers: dict, business_id: uuid.UUID, **overrides):
    payload = {"name": "Competitor teardown", "type": "competitor", **overrides}
    return await client.post(_url(business_id, "projects"), json=payload, headers=headers)


async def _create_competitor(
    client: AsyncClient, headers: dict, business_id: uuid.UUID, **overrides
):
    payload = {"name": "Acme Inc", "domain": "acme.example", **overrides}
    return await client.post(_url(business_id, "competitors"), json=payload, headers=headers)


async def _create_source(client: AsyncClient, headers: dict, business_id: uuid.UUID, **overrides):
    payload = {
        "source_type": "website",
        "title": "Acme homepage",
        "url": "https://acme.example",
        "content": "Fast shipping, 30-day returns.",
        **overrides,
    }
    return await client.post(_url(business_id, "sources"), json=payload, headers=headers)


async def _create_evidence(
    client: AsyncClient, headers: dict, business_id: uuid.UUID, source_id: uuid.UUID, **overrides
):
    payload = {
        "source_id": str(source_id),
        "evidence_type": "trust_signal",
        "statement": "30-day returns offered",
        **overrides,
    }
    return await client.post(_url(business_id, "evidence"), json=payload, headers=headers)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------
async def test_create_project_returns_draft(tenant, client: AsyncClient):
    response = await _create_project(client, tenant["headers"], tenant["business"].id)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Competitor teardown"
    assert body["type"] == "competitor"
    assert body["status"] == "draft"
    assert uuid.UUID(body["id"])


async def test_create_project_rejects_unknown_type(tenant, client: AsyncClient):
    response = await _create_project(client, tenant["headers"], tenant["business"].id, type="spy")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_classification"


async def test_list_projects(tenant, client: AsyncClient):
    await _create_project(client, tenant["headers"], tenant["business"].id)
    await _create_project(
        client, tenant["headers"], tenant["business"].id, name="Market scan", type="market"
    )
    response = await client.get(_url(tenant["business"].id, "projects"), headers=tenant["headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {p["name"] for p in body["projects"]} == {"Competitor teardown", "Market scan"}


async def test_project_status_transitions(tenant, client: AsyncClient):
    created = (await _create_project(client, tenant["headers"], tenant["business"].id)).json()
    pid = created["id"]
    for status in ("collecting", "processing", "completed", "archived"):
        response = await client.patch(
            _url(tenant["business"].id, "projects", pid, "status"),
            json={"status": status},
            headers=tenant["headers"],
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == status


async def test_project_invalid_status_transition(tenant, client: AsyncClient):
    created = (await _create_project(client, tenant["headers"], tenant["business"].id)).json()
    pid = created["id"]
    await client.patch(
        _url(tenant["business"].id, "projects", pid, "status"),
        json={"status": "completed"},
        headers=tenant["headers"],
    )
    response = await client.patch(
        _url(tenant["business"].id, "projects", pid, "status"),
        json={"status": "collecting"},
        headers=tenant["headers"],
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_state"
    assert response.json()["error"]["details"]["current"] == "completed"


async def test_project_detail_includes_data_quality(tenant, client: AsyncClient):
    created = (await _create_project(client, tenant["headers"], tenant["business"].id)).json()
    pid = created["id"]
    response = await client.get(
        _url(tenant["business"].id, "projects", pid), headers=tenant["headers"]
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source_count"] == 0
    assert body["evidence_count"] == 0
    assert body["finding_count"] == 0
    assert body["data_quality"]["coverage"] == 0.0
    assert body["data_quality"]["missing_areas"]


# ---------------------------------------------------------------------------
# Tenancy & authorization
# ---------------------------------------------------------------------------
async def test_cross_tenant_project_is_404(tenant, client: AsyncClient, session):
    created = (await _create_project(client, tenant["headers"], tenant["business"].id)).json()
    other = await create_tenant(session)
    response = await client.get(
        _url(tenant["business"].id, "projects", created["id"]), headers=other["headers"]
    )
    assert response.status_code == 404


async def test_read_requires_business_read_permission(client: AsyncClient, session):
    tenant = await create_tenant(session, permissions=["business:write"])
    response = await client.get(
        _url(tenant["business"].id, "projects"), headers=tenant["headers"]
    )
    assert response.status_code == 403


async def test_write_requires_business_write_permission(client: AsyncClient, session):
    tenant = await create_tenant(session, permissions=["business:read"])
    response = await _create_project(client, tenant["headers"], tenant["business"].id)
    assert response.status_code == 403


async def test_unknown_business_is_404(tenant, client: AsyncClient):
    response = await client.get(
        _url(uuid.uuid4(), "projects"), headers=tenant["headers"]
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Competitors
# ---------------------------------------------------------------------------
async def test_create_competitor_without_domain(tenant, client: AsyncClient):
    response = await _create_competitor(
        client, tenant["headers"], tenant["business"].id, domain=None
    )
    assert response.status_code == 201
    assert response.json()["domain"] is None


async def test_duplicate_competitor_conflict(tenant, client: AsyncClient):
    await _create_competitor(client, tenant["headers"], tenant["business"].id)
    response = await _create_competitor(client, tenant["headers"], tenant["business"].id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "resource_conflict"


async def test_get_competitor_cross_tenant_404(tenant, client: AsyncClient, session):
    created = (await _create_competitor(client, tenant["headers"], tenant["business"].id)).json()
    other = await create_tenant(session)
    response = await client.get(
        _url(tenant["business"].id, "competitors", created["id"]), headers=other["headers"]
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
async def test_create_source_and_snapshot(tenant, client: AsyncClient):
    response = await _create_source(client, tenant["headers"], tenant["business"].id)
    assert response.status_code == 201
    body = response.json()
    assert body["content_hash"] and len(body["content_hash"]) == 64
    assert body["domain"] == "acme.example"
    detail = await client.get(
        _url(tenant["business"].id, "sources", body["id"]), headers=tenant["headers"]
    )
    assert detail.status_code == 200
    assert len(detail.json()["snapshots"]) == 1
    assert detail.json()["snapshots"][0]["content"] == "Fast shipping, 30-day returns."


async def test_source_content_hash_dedup(tenant, client: AsyncClient):
    first = (await _create_source(client, tenant["headers"], tenant["business"].id)).json()
    second = (await _create_source(client, tenant["headers"], tenant["business"].id)).json()
    assert first["id"] == second["id"]
    detail = await client.get(
        _url(tenant["business"].id, "sources", first["id"]), headers=tenant["headers"]
    )
    assert len(detail.json()["snapshots"]) == 1  # snapshot deduped too


async def test_source_without_content_no_hash(tenant, client: AsyncClient):
    response = await _create_source(
        client, tenant["headers"], tenant["business"].id, content=None
    )
    assert response.status_code == 201
    assert response.json()["content_hash"] is None


async def test_source_links_competitor(tenant, client: AsyncClient):
    competitor = (await _create_competitor(client, tenant["headers"], tenant["business"].id)).json()
    response = await _create_source(
        client,
        tenant["headers"],
        tenant["business"].id,
        competitor_id=competitor["id"],
    )
    assert response.status_code == 201
    assert response.json()["competitor_id"] == competitor["id"]


async def test_source_cross_tenant_competitor_404(tenant, client: AsyncClient):
    response = await _create_source(
        client, tenant["headers"], tenant["business"].id, competitor_id=str(uuid.uuid4())
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "research_not_found"


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------
async def test_create_evidence_defaults_observed(tenant, client: AsyncClient):
    source = (await _create_source(client, tenant["headers"], tenant["business"].id)).json()
    response = await _create_evidence(
        client, tenant["headers"], tenant["business"].id, uuid.UUID(source["id"])
    )
    assert response.status_code == 201
    body = response.json()
    assert body["confidence"] == "observed"
    assert body["provenance"] == "collected"


async def test_evidence_excerpt_plus_structured_requires_confirmation(tenant, client: AsyncClient):
    source = (await _create_source(client, tenant["headers"], tenant["business"].id)).json()
    response = await _create_evidence(
        client,
        tenant["headers"],
        tenant["business"].id,
        uuid.UUID(source["id"]),
        raw_excerpt='"30-day returns"',
        structured_value={"return_days": 30},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "requires_confirmation"
    assert error["details"]["reasons"] == ["excerpt_and_structured_value"]
    # explicit inferred is accepted
    response = await _create_evidence(
        client,
        tenant["headers"],
        tenant["business"].id,
        uuid.UUID(source["id"]),
        raw_excerpt='"30-day returns"',
        structured_value={"return_days": 30},
        confidence="inferred",
    )
    assert response.status_code == 201
    assert response.json()["confidence"] == "inferred"


async def test_evidence_money_never_float(tenant, client: AsyncClient):
    source = (await _create_source(client, tenant["headers"], tenant["business"].id)).json()
    response = await _create_evidence(
        client,
        tenant["headers"],
        tenant["business"].id,
        uuid.UUID(source["id"]),
        evidence_type="pricing",
        statement="99.99",
        structured_value={"price": 99.99},
    )
    assert response.status_code == 201
    assert response.json()["structured_value"]["price"] == "99.99"


async def test_evidence_unknown_source_404(tenant, client: AsyncClient):
    response = await _create_evidence(
        client, tenant["headers"], tenant["business"].id, uuid.uuid4()
    )
    assert response.status_code == 404


async def test_evidence_invalid_confidence(tenant, client: AsyncClient):
    source = (await _create_source(client, tenant["headers"], tenant["business"].id)).json()
    response = await _create_evidence(
        client,
        tenant["headers"],
        tenant["business"].id,
        uuid.UUID(source["id"]),
        confidence="certain",
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_classification"


async def test_evidence_cross_tenant_source_404(tenant, client: AsyncClient, session):
    other = await create_tenant(session)
    response = await _create_evidence(
        client, other["headers"], tenant["business"].id, uuid.uuid4()
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------
async def test_finding_defaults_inferred_with_evidence(tenant, client: AsyncClient):
    project = (await _create_project(client, tenant["headers"], tenant["business"].id)).json()
    source = (await _create_source(client, tenant["headers"], tenant["business"].id)).json()
    evidence = (
        await _create_evidence(
            client, tenant["headers"], tenant["business"].id, uuid.UUID(source["id"])
        )
    ).json()
    response = await client.post(
        _url(tenant["business"].id, "findings"),
        json={
            "research_project_id": project["id"],
            "category": "messaging",
            "title": "30-day returns",
            "statement": "Acme offers 30-day returns",
            "evidence_ids": [evidence["id"]],
        },
        headers=tenant["headers"],
    )
    assert response.status_code == 201
    body = response.json()
    assert body["classification"] == "inferred"
    assert body["evidence_strength"] == "weak"  # 1 evidence


async def test_finding_defaults_hypothesis_without_evidence(tenant, client: AsyncClient):
    project = (await _create_project(client, tenant["headers"], tenant["business"].id)).json()
    response = await client.post(
        _url(tenant["business"].id, "findings"),
        json={
            "research_project_id": project["id"],
            "category": "customer",
            "title": "Shoppers prefer weekend delivery",
            "statement": "Weekend delivery may lift conversion.",
        },
        headers=tenant["headers"],
    )
    assert response.status_code == 201
    assert response.json()["classification"] == "hypothesis"
    assert response.json()["evidence_strength"] == "insufficient"


async def test_hypothesis_with_evidence_rejected(tenant, client: AsyncClient):
    project = (await _create_project(client, tenant["headers"], tenant["business"].id)).json()
    source = (await _create_source(client, tenant["headers"], tenant["business"].id)).json()
    evidence = (
        await _create_evidence(
            client, tenant["headers"], tenant["business"].id, uuid.UUID(source["id"])
        )
    ).json()
    response = await client.post(
        _url(tenant["business"].id, "findings"),
        json={
            "research_project_id": project["id"],
            "category": "customer",
            "title": "Guess",
            "statement": "A guess with evidence is not a hypothesis.",
            "classification": "hypothesis",
            "evidence_ids": [evidence["id"]],
        },
        headers=tenant["headers"],
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "requires_confirmation"


async def test_observed_without_evidence_rejected(tenant, client: AsyncClient):
    project = (await _create_project(client, tenant["headers"], tenant["business"].id)).json()
    response = await client.post(
        _url(tenant["business"].id, "findings"),
        json={
            "research_project_id": project["id"],
            "category": "customer",
            "title": "Claim",
            "statement": "Claimed as observed but no evidence attached.",
            "classification": "observed",
        },
        headers=tenant["headers"],
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "requires_confirmation"


async def test_finding_evidence_strength_ladder(tenant, client: AsyncClient):
    project = (await _create_project(client, tenant["headers"], tenant["business"].id)).json()
    source = (await _create_source(client, tenant["headers"], tenant["business"].id)).json()
    evidence_ids = []
    for i in range(5):
        row = (
            await _create_evidence(
                client,
                tenant["headers"],
                tenant["business"].id,
                uuid.UUID(source["id"]),
                statement=f"Claim {i}",
                confidence="observed",
            )
        ).json()
        evidence_ids.append(row["id"])
    response = await client.post(
        _url(tenant["business"].id, "findings"),
        json={
            "research_project_id": project["id"],
            "category": "customer",
            "title": "Strong claim",
            "statement": "Backed by five observations.",
            "evidence_ids": evidence_ids,
        },
        headers=tenant["headers"],
    )
    assert response.status_code == 201
    assert response.json()["evidence_strength"] == "strong"


async def test_finding_detail_includes_evidence_chain(tenant, client: AsyncClient):
    project = (await _create_project(client, tenant["headers"], tenant["business"].id)).json()
    source = (await _create_source(client, tenant["headers"], tenant["business"].id)).json()
    evidence = (
        await _create_evidence(
            client, tenant["headers"], tenant["business"].id, uuid.UUID(source["id"])
        )
    ).json()
    finding = (
        await client.post(
            _url(tenant["business"].id, "findings"),
            json={
                "research_project_id": project["id"],
                "category": "customer",
                "title": "Finding",
                "statement": "Statement",
                "evidence_ids": [evidence["id"]],
            },
            headers=tenant["headers"],
        )
    ).json()
    detail = await client.get(
        _url(tenant["business"].id, "findings", finding["id"]), headers=tenant["headers"]
    )
    assert detail.status_code == 200
    assert len(detail.json()["evidence"]) == 1
    assert detail.json()["evidence"][0]["provenance"] == "collected"


async def test_finding_cross_tenant_evidence_404(tenant, client: AsyncClient):
    project = (await _create_project(client, tenant["headers"], tenant["business"].id)).json()
    response = await client.post(
        _url(tenant["business"].id, "findings"),
        json={
            "research_project_id": project["id"],
            "category": "customer",
            "title": "Bad evidence",
            "statement": "References evidence from another tenant.",
            "evidence_ids": [str(uuid.uuid4())],
        },
        headers=tenant["headers"],
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Filters & search
# ---------------------------------------------------------------------------
async def test_evidence_filters(tenant, client: AsyncClient):
    source = (await _create_source(client, tenant["headers"], tenant["business"].id)).json()
    await _create_evidence(
        client, tenant["headers"], tenant["business"].id, uuid.UUID(source["id"])
    )
    await _create_evidence(
        client,
        tenant["headers"],
        tenant["business"].id,
        uuid.UUID(source["id"]),
        evidence_type="pricing",
        statement="Priced at 99",
        confidence="inferred",
    )
    response = await client.get(
        _url(tenant["business"].id, "evidence"),
        params={"evidence_type": "pricing"},
        headers=tenant["headers"],
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    response = await client.get(
        _url(tenant["business"].id, "evidence"),
        params={"confidence": "observed"},
        headers=tenant["headers"],
    )
    assert response.json()["total"] == 1


async def test_finding_filters(tenant, client: AsyncClient):
    project = (await _create_project(client, tenant["headers"], tenant["business"].id)).json()
    await client.post(
        _url(tenant["business"].id, "findings"),
        json={
            "research_project_id": project["id"],
            "category": "customer",
            "title": "One",
            "statement": "S",
        },
        headers=tenant["headers"],
    )
    await client.post(
        _url(tenant["business"].id, "findings"),
        json={
            "research_project_id": project["id"],
            "category": "pricing",
            "title": "Two",
            "statement": "S",
        },
        headers=tenant["headers"],
    )
    response = await client.get(
        _url(tenant["business"].id, "findings"),
        params={"category": "pricing", "classification": "hypothesis"},
        headers=tenant["headers"],
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["findings"][0]["title"] == "Two"


async def test_source_filters(tenant, client: AsyncClient):
    await _create_source(client, tenant["headers"], tenant["business"].id)
    await _create_source(
        client, tenant["headers"], tenant["business"].id, source_type="review", content="Good."
    )
    response = await client.get(
        _url(tenant["business"].id, "sources"),
        params={"source_type": "review"},
        headers=tenant["headers"],
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1


async def test_search_evidence_by_statement(tenant, client: AsyncClient):
    source = (await _create_source(client, tenant["headers"], tenant["business"].id)).json()
    await _create_evidence(
        client,
        tenant["headers"],
        tenant["business"].id,
        uuid.UUID(source["id"]),
        statement="Customers mention free shipping often",
    )
    response = await client.get(
        _url(tenant["business"].id, "evidence"),
        params={"q": "free shipping"},
        headers=tenant["headers"],
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1


async def test_search_evidence_by_source_title(tenant, client: AsyncClient):
    source = (
        await _create_source(
            client,
            tenant["headers"],
            tenant["business"].id,
            title="Deep Review of Acme",
            content="Review body.",
        )
    ).json()
    await _create_evidence(
        client,
        tenant["headers"],
        tenant["business"].id,
        uuid.UUID(source["id"]),
        statement="Neutral claim",
    )
    response = await client.get(
        _url(tenant["business"].id, "evidence"),
        params={"q": "deep review"},
        headers=tenant["headers"],
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1


# ---------------------------------------------------------------------------
# Malformed input
# ---------------------------------------------------------------------------
async def test_malformed_payloads(tenant, client: AsyncClient):
    response = await client.post(
        _url(tenant["business"].id, "projects"),
        json={"name": "", "type": "customer"},
        headers=tenant["headers"],
    )
    assert response.status_code == 422
    response = await client.post(
        _url(tenant["business"].id, "sources"),
        json={"source_type": "bogus", "title": "X"},
        headers=tenant["headers"],
    )
    assert response.status_code == 422
    response = await client.post(
        _url(tenant["business"].id, "evidence"),
        json={"source_id": str(uuid.uuid4()), "evidence_type": "x", "statement": ""},
        headers=tenant["headers"],
    )
    assert response.status_code == 422


async def test_duplicate_evidence_rows_are_independent(tenant, client: AsyncClient):
    source = (await _create_source(client, tenant["headers"], tenant["business"].id)).json()
    first = (
        await _create_evidence(
            client, tenant["headers"], tenant["business"].id, uuid.UUID(source["id"])
        )
    ).json()
    second = (
        await _create_evidence(
            client, tenant["headers"], tenant["business"].id, uuid.UUID(source["id"])
        )
    ).json()
    assert first["id"] != second["id"]  # evidence is not deduplicated by statement