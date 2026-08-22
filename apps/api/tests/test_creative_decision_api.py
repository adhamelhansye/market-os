"""Creative decision plan API tests (Phase 8F).

Covers: unavailable state, generate flow consuming the latest 8E
snapshot, idempotent regeneration, review lifecycle (proposed default,
acknowledge/dismiss/defer, invalid state rejected), review survival
across regeneration with source fingerprint preservation, tenancy 404s
and viewer 403.
"""

import uuid

import pytest

from src.core.rbac import DEFAULT_ROLES
from tests.conftest import (
    auth_headers,
    create_membership,
    create_role,
    create_tenant,
    create_user,
)
from tests.test_creative_performance_api import _concept, _seed_performance_data

BASE = "/api/v1"
DP = BASE + "/businesses/{business_id}/strategy/creative/decision-plan"

pytestmark = pytest.mark.usefixtures("clean_tables")


def _url(tenant, path=""):
    return DP.format(business_id=tenant["business"].id) + path


async def _seed_optimization_snapshot(client, session, tenant) -> str:
    """Drive the real 8C->8E chain: seed data, link, generate optimization."""
    stack = await _seed_performance_data(session, tenant)
    concept = await _concept(session, tenant)
    await session.commit()
    links_url = (
        BASE + f"/businesses/{tenant['business'].id}"
        + "/strategy/creative/performance/links"
    )
    created = await client.post(
        links_url,
        json={"creative_concept_id": str(concept.id), "ad_id": str(stack["ads"][0].id)},
        headers=tenant["headers"],
    )
    assert created.status_code == 201
    opt_generate = await client.post(
        BASE + f"/businesses/{tenant['business'].id}"
        + "/strategy/creative/optimization/generate",
        headers=tenant["headers"],
    )
    assert opt_generate.status_code == 200
    return opt_generate.json()["plan"]["fingerprint"]


async def test_no_8e_snapshot_returns_unavailable(client, tenant):
    response = await client.post(_url(tenant, "/generate"), headers=tenant["headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["snapshot_id"] is None and body["created"] is False
    assert body["plan"]["plan_status"] == "unavailable"
    assert body["plan"]["summary"]["reason"] == "no_optimization_snapshot"

    reads = await client.get(_url(tenant, "/summary"), headers=tenant["headers"])
    assert reads.status_code == 404


class TestGenerateAndReviewFlow:
    async def _generate(self, client, session, tenant):
        await _seed_optimization_snapshot(client, session, tenant)
        response = await client.post(_url(tenant, "/generate"), headers=tenant["headers"])
        assert response.status_code == 200
        return response.json()

    async def test_generate_consumes_latest_8e_snapshot(self, client, session, tenant):
        body = await self._generate(client, session, tenant)
        plan = body["plan"]
        assert plan["source_optimization_fingerprint"]
        assert plan["rules_versions"]["engine"] == "cdecision-v1"
        assert plan["summary"]["total_items"] >= 1
        for item in plan["items"]:
            assert item["review_only"] is True
            assert item["execution_status"] == "not_executed"
            assert item["review_state"] == "proposed"
            assert item["suggested_review_focus"]

    async def test_reads_after_generate(self, client, session, tenant):
        await self._generate(client, session, tenant)
        summary = await client.get(_url(tenant, "/summary"), headers=tenant["headers"])
        assert summary.status_code == 200
        data = summary.json()
        assert data["status"] == "available" and data["fingerprint"]
        assert data["review_progress"]["remaining_items"] >= 1

        items = await client.get(_url(tenant, "/items"), headers=tenant["headers"])
        assert items.json()["status"] == "available"
        blocked = await client.get(_url(tenant, "/blocked"), headers=tenant["headers"])
        assert blocked.json()["actionable"] is False

    async def test_regenerate_idempotent_same_fingerprint(self, client, session, tenant):
        await self._generate(client, session, tenant)
        first = await client.get(_url(tenant, "/summary"), headers=tenant["headers"])
        second_gen = await client.post(_url(tenant, "/generate"), headers=tenant["headers"])
        assert second_gen.json()["created"] is False
        second = await client.get(_url(tenant, "/summary"), headers=tenant["headers"])
        assert second.json()["fingerprint"] == first.json()["fingerprint"]

    async def test_review_lifecycle_and_survival(self, client, session, tenant):
        body = await self._generate(client, session, tenant)
        opportunity_id = body["plan"]["items"][0]["opportunity_id"]

        ack = await client.post(
            _url(tenant, f"/items/{opportunity_id}/review"),
            json={"review_state": "acknowledged", "note": "looked at it"},
            headers=tenant["headers"],
        )
        assert ack.status_code == 200
        assert ack.json()["review_state"] == "acknowledged"
        source_fp = ack.json()["source_plan_fingerprint"]
        assert source_fp

        items = await client.get(_url(tenant, "/items"), headers=tenant["headers"])
        merged = next(
            i for i in items.json()["items"] if i["opportunity_id"] == opportunity_id
        )
        assert merged["review_state"] == "acknowledged"
        assert merged["review_note"] == "looked at it"

        # Regenerate the SAME plan: review survives, source fp preserved.
        regen = await client.post(_url(tenant, "/generate"), headers=tenant["headers"])
        assert regen.json()["created"] is False
        items2 = await client.get(_url(tenant, "/items"), headers=tenant["headers"])
        merged2 = next(
            i for i in items2.json()["items"] if i["opportunity_id"] == opportunity_id
        )
        assert merged2["review_state"] == "acknowledged"
        assert merged2["review_source_plan_fingerprint"] == source_fp

        summary = await client.get(_url(tenant, "/summary"), headers=tenant["headers"])
        progress = summary.json()["review_progress"]
        assert progress["acknowledged"] == 1 and progress["reviewed_items"] == 1

    async def test_dismiss_and_defer_states(self, client, session, tenant):
        body = await self._generate(client, session, tenant)
        items = body["plan"]["items"]
        assert items, "expected at least one decision-plan item"
        # Single-item plans exercise dismiss; multi-item plans also defer.
        pairs = list(zip(items, ("dismissed", "deferred"), strict=False))
        for item, state in pairs:
            response = await client.post(
                _url(tenant, f"/items/{item['opportunity_id']}/review"),
                json={"review_state": state},
                headers=tenant["headers"],
            )
            assert response.status_code == 200
            assert response.json()["review_state"] == state

    async def test_invalid_review_state_rejected(self, client, session, tenant):
        body = await self._generate(client, session, tenant)
        opportunity_id = body["plan"]["items"][0]["opportunity_id"]
        for banned in ("approved", "implemented", "executed", "launched", "scaled"):
            response = await client.post(
                _url(tenant, f"/items/{opportunity_id}/review"),
                json={"review_state": banned},
                headers=tenant["headers"],
            )
            assert response.status_code == 409, banned

    async def test_unknown_opportunity_review_404(self, client, session, tenant):
        await self._generate(client, session, tenant)
        response = await client.post(
            _url(tenant, f"/items/{uuid.uuid4()}:angle:x/review"),
            json={"review_state": "acknowledged"},
            headers=tenant["headers"],
        )
        assert response.status_code == 404


class TestSnapshots:
    async def test_list_and_detail_json_safe(self, client, session, tenant):
        await self._generate_impl(client, session, tenant)
        listing = await client.get(_url(tenant, "/snapshots"), headers=tenant["headers"])
        rows = listing.json()
        assert len(rows) >= 1
        detail = await client.get(
            _url(tenant, f"/snapshots/{rows[0]['id']}"), headers=tenant["headers"]
        )
        assert detail.status_code == 200
        assert "Decimal" not in detail.text

    async def _generate_impl(self, client, session, tenant):
        await _seed_optimization_snapshot(client, session, tenant)
        response = await client.post(_url(tenant, "/generate"), headers=tenant["headers"])
        assert response.status_code == 200


class TestTenancyAndRbac:
    async def _other_tenant(self, session):
        return await create_tenant(session)

    async def test_cross_tenant_read_404(self, client, session, tenant):
        other = await self._other_tenant(session)
        response = await client.get(
            DP.format(business_id=tenant["business"].id) + "/summary",
            headers=other["headers"],
        )
        assert response.status_code == 404

    async def test_cross_tenant_review_write_404(self, client, session, tenant):
        await self._generate_for_tenancy(client, session, tenant)
        other = await self._other_tenant(session)
        response = await client.post(
            DP.format(business_id=tenant["business"].id)
            + "/items/whatever:angle:x/review",
            json={"review_state": "dismissed"},
            headers=other["headers"],
        )
        assert response.status_code == 404

    async def _generate_for_tenancy(self, client, session, tenant):
        await _seed_optimization_snapshot(client, session, tenant)
        response = await client.post(_url(tenant, "/generate"), headers=tenant["headers"])
        assert response.status_code == 200

    async def test_viewer_review_write_403(self, client, session, tenant):
        viewer = await create_user(session)
        role = await create_role(
            session,
            name="viewer",
            organization_id=tenant["org"].id,
            permissions=sorted(DEFAULT_ROLES["viewer"]),
        )
        await create_membership(session, user=viewer, organization=tenant["org"], role=role)
        await session.commit()
        viewer_headers = await auth_headers(session, viewer, tenant["org"].id)
        response = await client.post(
            _url(tenant, "/items/any:angle:x/review"),
            json={"review_state": "dismissed"},
            headers=viewer_headers,
        )
        assert response.status_code == 403
