import uuid
from datetime import UTC, datetime
from decimal import Decimal

from conftest import create_tenant
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import InventorySnapshot, Product, ProductCost, ProductPrice


async def _product(session: AsyncSession, tenant: dict, *, cogs: str = "40.00") -> Product:
    product = Product(
        business_id=tenant["business"].id,
        name="Strategy product",
        currency="USD",
    )
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
            ProductCost(
                product_id=product.id,
                cogs=Decimal(cogs),
                effective_from=effective,
            ),
            InventorySnapshot(
                product_id=product.id,
                quantity=25,
                source="manual",
                recorded_at=effective,
            ),
        ]
    )
    await session.commit()
    return product


async def test_positioning_candidate_and_insufficient_recommendation(
    client: AsyncClient, tenant: dict
) -> None:
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    created = await client.post(
        f"{base}/positioning/candidates",
        headers=tenant["headers"],
        json={
            "name": "Problem-led",
            "target_customer": "Busy owners",
            "problem": "Too much manual work",
            "solution": "A structured operating system",
            "differentiator": "Evidence-backed workflows",
            "promise": "Make decisions with clarity",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["positioning_statement"].startswith("For Busy owners")
    recommendation = await client.post(f"{base}/positioning/recommend", headers=tenant["headers"])
    assert recommendation.status_code == 200
    assert recommendation.json()["status"] == "insufficient_data"


async def test_offer_uses_decimal_economics_and_provenance_is_tenant_scoped(
    session: AsyncSession, client: AsyncClient, tenant: dict
) -> None:
    product = await _product(session, tenant)
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    created = await client.post(
        f"{base}/offers/candidates",
        headers=tenant["headers"],
        json={"name": "Standard offer", "product_id": str(product.id)},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["economics"]["contribution_profit"] == "60.00"
    assert isinstance(body["economics"]["break_even_roas"], str)
    validated = await client.post(
        f"{base}/offers/validate",
        headers=tenant["headers"],
        json={"candidate_id": body["id"]},
    )
    assert validated.status_code == 200
    assert validated.json()["candidates"][0]["status"] == "validated"

    foreign = await create_tenant(session)
    denied = await client.get(
        f"/api/v1/businesses/{foreign['business'].id}/strategy/offers/candidates/{body['id']}",
        headers=foreign["headers"],
    )
    assert denied.status_code == 404


async def test_invalid_offer_is_explicitly_invalid(
    session: AsyncSession, client: AsyncClient, tenant: dict
) -> None:
    product = await _product(session, tenant, cogs="120.00")
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    created = await client.post(
        f"{base}/offers/candidates",
        headers=tenant["headers"],
        json={"name": "Loss-making offer", "product_id": str(product.id)},
    )
    assert created.status_code == 201
    validated = await client.post(
        f"{base}/offers/validate",
        headers=tenant["headers"],
        json={"candidate_id": created.json()["id"]},
    )
    assert validated.status_code == 200
    assert validated.json()["status"] == "invalid"
    assert any(r["code"] == "margin_risk" for r in validated.json()["candidates"][0]["risks"])


async def test_strategy_summary_and_snapshot_endpoints(client: AsyncClient, tenant: dict) -> None:
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    summary = await client.get(f"{base}/summary", headers=tenant["headers"])
    assert summary.status_code == 200
    assert summary.json()["positioning"]["status"] == "insufficient_data"
    snapshot = await client.get(f"{base}/snapshot", headers=tenant["headers"])
    assert snapshot.status_code == 404


async def test_strategy_decision_integrates_research_and_performance(
    client: AsyncClient, tenant: dict
) -> None:
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    candidate = await client.post(
        f"{base}/positioning/candidates",
        headers=tenant["headers"],
        json={
            "name": "Decision candidate",
            "solution": "A product solution",
            "promise": "A supported outcome",
        },
    )
    assert candidate.status_code == 201, candidate.text
    decision = await client.post(
        f"{base}/decisions/evaluate",
        headers=tenant["headers"],
        json={"candidate_type": "positioning", "candidate_id": candidate.json()["id"]},
    )
    assert decision.status_code == 201, decision.text
    body = decision.json()
    assert body["decision_rules_version"] == "strategy_decision_v1"
    assert body["status"] in {"not_recommended", "insufficient_data"}
    assert "metrics_range" in body["input_snapshot"]
    assert "metrics" in body["evaluation"]
    listed = await client.get(f"{base}/decisions", headers=tenant["headers"])
    assert listed.status_code == 200
    assert listed.json()["decisions"][0]["id"] == body["id"]
    provenance = await client.get(
        f"{base}/decisions/{body['id']}/provenance", headers=tenant["headers"]
    )
    assert provenance.status_code == 200


async def test_offer_decision_economic_gate_and_goal_reference(
    session: AsyncSession, client: AsyncClient, tenant: dict
) -> None:
    product = await _product(session, tenant, cogs="120.00")
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
    candidate = await client.post(
        f"{base}/offers/candidates",
        headers=tenant["headers"],
        json={"name": "Invalid decision offer", "product_id": str(product.id)},
    )
    assert candidate.status_code == 201, candidate.text
    decision = await client.post(
        f"{base}/decisions/evaluate",
        headers=tenant["headers"],
        json={"candidate_type": "offer", "candidate_id": candidate.json()["id"]},
    )
    assert decision.status_code == 201, decision.text
    body = decision.json()
    assert body["status"] == "economically_invalid"
    assert body["evaluation"]["goal"]["status"] == "available"
    assert any(reason["type"] == "economic" for reason in body["reasons"])


async def test_strategy_decision_cross_tenant_isolation(
    session: AsyncSession, client: AsyncClient, tenant: dict
) -> None:
    created = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/strategy/positioning/candidates",
        headers=tenant["headers"],
        json={"name": "Private candidate"},
    )
    assert created.status_code == 201
    foreign = await create_tenant(session)
    response = await client.post(
        f"/api/v1/businesses/{foreign['business'].id}/strategy/decisions/evaluate",
        headers=foreign["headers"],
        json={
            "candidate_type": "positioning",
            "candidate_id": created.json()["id"],
        },
    )
    assert response.status_code == 404


async def test_messaging_generation_is_structured_and_traceable(
    session: AsyncSession, client: AsyncClient, tenant: dict
) -> None:
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    positioning = await client.post(
        f"{base}/positioning/candidates",
        headers=tenant["headers"],
        json={
            "name": "Messaging positioning",
            "target_customer": "Busy owners",
            "problem": "Manual work",
            "solution": "Structured workflows",
            "differentiator": "Evidence-backed workflows",
            "promise": "Clarity",
        },
    )
    assert positioning.status_code == 201, positioning.text
    generated = await client.post(
        f"{base}/messaging/generate",
        headers=tenant["headers"],
        json={"positioning_candidate_id": positioning.json()["id"]},
    )
    assert generated.status_code == 201, generated.text
    body = generated.json()
    assert body["messaging_version"] == "messaging_v1"
    assert body["core_message"]["problem"] == "Manual work"
    assert any(component["component_type"] == "promise" for component in body["components"])
    assert body["quality"]["performance_attribution"] == "no_performance_attribution"
    assert all(angle["status"] == "no_performance_attribution" for angle in body["angles"])
    provenance = await client.get(
        f"{base}/messaging/{body['id']}/provenance", headers=tenant["headers"]
    )
    assert provenance.status_code == 200


async def test_messaging_input_and_tenant_isolation(
    session: AsyncSession, client: AsyncClient, tenant: dict
) -> None:
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    generated = await client.post(f"{base}/messaging/generate", headers=tenant["headers"], json={})
    assert generated.status_code == 201
    foreign = await create_tenant(session)
    response = await client.get(
        f"/api/v1/businesses/{foreign['business'].id}/strategy/messaging/{generated.json()['id']}",
        headers=foreign["headers"],
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Phase 7B messaging strategy
# ---------------------------------------------------------------------------


def _research_url(business_id, *parts) -> str:
    return f"/api/v1/businesses/{business_id}/research/" + "/".join(parts)


async def _credential(client: AsyncClient, headers: dict, business_id: uuid.UUID) -> dict:
    source = await client.post(
        _research_url(business_id, "sources"),
        headers=headers,
        json={
            "source_type": "review",
            "title": "Customer review",
            "url": "https://example.test/review",
            "content": "Original review text.",
        },
    )
    assert source.status_code == 201, source.text
    return {"source": source.json()}


async def _evidence(
    client: AsyncClient, headers: dict, business_id: uuid.UUID, source_id: str, **overrides
) -> dict:
    payload = {
        "source_id": source_id,
        "evidence_type": "pain_point",
        "statement": "Manual reports take hours every week.",
        "confidence": "observed",
        **overrides,
    }
    response = await client.post(
        _research_url(business_id, "evidence"), headers=headers, json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _competitor(
    client: AsyncClient, headers: dict, business_id: uuid.UUID, **overrides
) -> dict:
    payload = {
        "name": "Rival One",
        "domain": "rival-one.example",
        "description": "Free shipping and 30-day returns on every order.",
        **overrides,
    }
    response = await client.post(
        _research_url(business_id, "competitors"), headers=headers, json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()


def _positioning_payload() -> dict:
    return {
        "name": "Messaging positioning",
        "target_customer": "Busy owners",
        "problem": "Manual work",
        "solution": "Structured workflows",
        "differentiator": "Evidence-backed workflows",
        "promise": "Clarity",
        "classification": "observed",
    }


async def test_messaging_objections_carry_severity_and_proof_response(
    client: AsyncClient,
    tenant: dict,
) -> None:
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    research = await _credential(client, tenant["headers"], tenant["business"].id)
    source_id = research["source"]["id"]
    await _evidence(
        client,
        tenant["headers"],
        tenant["business"].id,
        source_id,
        evidence_type="objection",
        statement="Is this just another tool to learn?",
    )
    await _evidence(
        client,
        tenant["headers"],
        tenant["business"].id,
        source_id,
        evidence_type="review",
        statement="Setup took under ten minutes.",
    )
    positioning = await client.post(
        f"{base}/positioning/candidates", headers=tenant["headers"], json=_positioning_payload()
    )
    assert positioning.status_code == 201, positioning.text
    generated = await client.post(
        f"{base}/messaging/generate",
        headers=tenant["headers"],
        json={"positioning_candidate_id": positioning.json()["id"]},
    )
    assert generated.status_code == 201, generated.text
    body = generated.json()
    objections = [c for c in body["components"] if c["component_type"] == "objection"]
    assert objections, "objection component expected"
    objection = objections[0]
    assert objection["details"]["severity"] in {"high", "medium", "low"}
    assert objection["details"]["response_available"] is True
    assert objection["details"]["response"] == "Setup took under ten minutes."
    assert objection["details"]["response_provenance"]


async def test_messaging_unsupported_claims_are_flagged(
    client: AsyncClient,
    tenant: dict,
) -> None:
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    payload = _positioning_payload()
    payload["promise"] = "Guaranteed results for every customer"
    positioning = await client.post(
        f"{base}/positioning/candidates", headers=tenant["headers"], json=payload
    )
    assert positioning.status_code == 201, positioning.text
    generated = await client.post(
        f"{base}/messaging/generate",
        headers=tenant["headers"],
        json={"positioning_candidate_id": positioning.json()["id"]},
    )
    assert generated.status_code == 201, generated.text
    body = generated.json()
    flags = body["quality"]["unsupported_claims"]
    assert flags, "unsupported claims must not be silently approved"
    assert any("guaranteed" in claim for flag in flags for claim in flag["claims"])
    promise = next(c for c in body["components"] if c["component_type"] == "promise")
    assert "guaranteed" in promise["details"]["unsupported_claims"]


async def test_messaging_competitor_patterns_saturation_and_whitespace(
    client: AsyncClient,
    tenant: dict,
) -> None:
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    research = await _credential(client, tenant["headers"], tenant["business"].id)
    source_id = research["source"]["id"]
    await _competitor(client, tenant["headers"], tenant["business"].id, name="Rival A")
    await _competitor(client, tenant["headers"], tenant["business"].id, name="Rival B")
    await _competitor(client, tenant["headers"], tenant["business"].id, name="Rival C")
    competitor = await _competitor(
        client,
        tenant["headers"],
        tenant["business"].id,
        name="Rival D",
        description="Enterprise plans for teams.",
    )
    await _evidence(
        client,
        tenant["headers"],
        tenant["business"].id,
        source_id,
        evidence_type="pain_point",
        statement="It takes days to reconcile ad spend.",
    )
    positioning = await client.post(
        f"{base}/positioning/candidates", headers=tenant["headers"], json=_positioning_payload()
    )
    generated = await client.post(
        f"{base}/messaging/generate",
        headers=tenant["headers"],
        json={"positioning_candidate_id": positioning.json()["id"]},
    )
    body = generated.json()
    analysis = body["quality"]["competitor_messaging"]
    assert analysis["competitor_sample_size"] == 4
    patterns = {pattern["pattern"]: pattern for pattern in analysis["patterns"]}
    assert "shipping" in patterns
    assert patterns["shipping"]["saturation"] == "common"
    assert patterns["shipping"]["frequency"] == 3
    assert "price" not in patterns
    assert analysis["whitespace_claim"] == "no_performance_claim"
    competitor_id = competitor["id"]
    assert not any(competitor_id in p["competitor_ids"] for p in analysis["patterns"])


async def test_messaging_prioritization_is_deterministic_and_versioned(
    client: AsyncClient,
    tenant: dict,
) -> None:
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    research = await _credential(client, tenant["headers"], tenant["business"].id)
    source_id = research["source"]["id"]
    await _evidence(client, tenant["headers"], tenant["business"].id, source_id)
    await _evidence(
        client,
        tenant["headers"],
        tenant["business"].id,
        source_id,
        evidence_type="desire",
        statement="We want one source of truth.",
    )
    positioning = await client.post(
        f"{base}/positioning/candidates", headers=tenant["headers"], json=_positioning_payload()
    )
    first = await client.post(
        f"{base}/messaging/generate",
        headers=tenant["headers"],
        json={"positioning_candidate_id": positioning.json()["id"]},
    )
    second = await client.post(
        f"{base}/messaging/generate",
        headers=tenant["headers"],
        json={"positioning_candidate_id": positioning.json()["id"]},
    )
    assert first.status_code == 201 and second.status_code == 201
    first_body, second_body = first.json(), second.json()
    assert first_body["version"] == 1 and second_body["version"] == 2
    assert (
        first_body["input_snapshot"]["prioritization_rules_version"]
        == "messaging_prioritization_v1"
    )
    first_order = [row["statement"] for row in first_body["quality"]["prioritization"]]
    second_order = [row["statement"] for row in second_body["quality"]["prioritization"]]
    assert first_order == second_order
    ranks = [row["rank"] for row in first_body["quality"]["prioritization"]]
    assert ranks == sorted(ranks)
    scores = [row["score"] for row in first_body["quality"]["prioritization"]]
    assert scores == sorted(scores, reverse=True)


async def test_messaging_cta_requires_an_available_action(
    client: AsyncClient,
    tenant: dict,
    session: AsyncSession,
) -> None:
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    research = await _credential(client, tenant["headers"], tenant["business"].id)
    await _evidence(
        client,
        tenant["headers"],
        tenant["business"].id,
        research["source"]["id"],
        evidence_type="review",
        statement="It works as described.",
    )
    positioning = await client.post(
        f"{base}/positioning/candidates", headers=tenant["headers"], json=_positioning_payload()
    )
    positional = positioning.json()

    without_offer = await client.post(
        f"{base}/messaging/generate",
        headers=tenant["headers"],
        json={"positioning_candidate_id": positional["id"]},
    )
    no_offer_body = without_offer.json()
    assert no_offer_body["core_message"]["cta"] is None
    assert no_offer_body["quality"]["cta_validation"]["available"] is False

    product = await _product(session, tenant)
    offer = await client.post(
        f"{base}/offers/candidates",
        headers=tenant["headers"],
        json={"name": "Default offer", "product_id": str(product.id)},
    )
    assert offer.status_code == 201, offer.text
    with_offer = await client.post(
        f"{base}/messaging/generate",
        headers=tenant["headers"],
        json={
            "positioning_candidate_id": positional["id"],
            "offer_candidate_id": offer.json()["id"],
        },
    )
    offer_body = with_offer.json()
    assert offer_body["core_message"]["cta"] == "view_product"
    assert offer_body["quality"]["cta_validation"]["available"] is True
    cta = next(c for c in offer_body["components"] if c["component_type"] == "cta")
    assert cta["provenance"][0]["source"] == "offer_candidate"


async def test_messaging_snapshot_references_and_versioning(
    client: AsyncClient,
    tenant: dict,
) -> None:
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    research = await _credential(client, tenant["headers"], tenant["business"].id)
    await _evidence(client, tenant["headers"], tenant["business"].id, research["source"]["id"])
    positioning = await client.post(
        f"{base}/positioning/candidates", headers=tenant["headers"], json=_positioning_payload()
    )
    generated = await client.post(
        f"{base}/messaging/generate",
        headers=tenant["headers"],
        json={"positioning_candidate_id": positioning.json()["id"]},
    )
    assert generated.status_code == 201
    body = generated.json()
    snapshot = body["input_snapshot"]
    assert snapshot["messaging_rules_version"] == "messaging_rules_v1"
    assert snapshot["positioning_candidate_id"] == positioning.json()["id"]
    assert len(snapshot["evidence_ids"]) == 1

    versions = await client.get(f"{base}/messaging/versions", headers=tenant["headers"])
    assert versions.status_code == 200
    assert len(versions.json()["versions"]) == 1

    fetched = await client.get(f"{base}/messaging/{body['id']}", headers=tenant["headers"])
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]

    provenance = await client.get(
        f"{base}/messaging/{body['id']}/provenance", headers=tenant["headers"]
    )
    assert provenance.status_code == 200
    assert provenance.json()["messaging_strategy_id"] == body["id"]
    assert provenance.json()["provenance"]


async def test_messaging_insufficient_data_without_positioning(
    client: AsyncClient,
    tenant: dict,
) -> None:
    base = f"/api/v1/businesses/{tenant['business'].id}/strategy"
    generated = await client.post(f"{base}/messaging/generate", headers=tenant["headers"], json={})
    assert generated.status_code == 201
    body = generated.json()
    assert body["status"] == "insufficient_data"
    assert "problem" in body["quality"]["missing_components"]
    assert body["core_message"]["who"] is None


async def test_messaging_generate_requires_write_permission(
    client: AsyncClient,
    tenant: dict,
    session: AsyncSession,
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
    response = await client.post(f"{base}/messaging/generate", headers=headers, json={})
    assert response.status_code == 403
