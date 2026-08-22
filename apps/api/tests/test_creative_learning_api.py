"""Creative learning API tests (Phase 8D).

Covers: generate/persist flow, explicit insufficient-data state,
idempotent recomputation (fingerprint stability), snapshot reads,
cross-tenant isolation and RBAC.
"""

import uuid

import pytest
from httpx import AsyncClient

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
LEARNING = BASE + "/businesses/{business_id}/strategy/creative/learning"

pytestmark = pytest.mark.usefixtures("clean_tables")


def _url(tenant, path=""):
    return LEARNING.format(business_id=tenant["business"].id) + path


async def _seed_linked_concept(client: AsyncClient, session, tenant: dict) -> dict:
    stack = await _seed_performance_data(session, tenant)
    concept = await _concept(session, tenant)
    await session.commit()
    links_url = (
        BASE
        + f"/businesses/{tenant['business'].id}"
        + "/strategy/creative/performance/links"
    )
    created = await client.post(
        links_url,
        json={
            "creative_concept_id": str(concept.id),
            "ad_id": str(stack["ads"][0].id),
        },
        headers=tenant["headers"],
    )
    assert created.status_code == 201
    return {"stack": stack, "concept": concept}


class TestGenerateFlow:
    async def test_generate_without_links_is_explicit_insufficient(
        self, client: AsyncClient, tenant
    ):
        response = await client.post(_url(tenant, "/generate"), headers=tenant["headers"])
        assert response.status_code == 200
        body = response.json()
        assert body["created"] is False
        assert body["snapshot_id"] is None
        assert body["report"]["summary"]["learning_status"] == "insufficient_data"
        assert body["report"]["summary"]["reason"] == "no_performance_links_recorded"
        assert body["report"]["recommendations"] == []

    async def test_generate_with_linked_entity_persists_snapshot(
        self, client: AsyncClient, session, tenant
    ):
        await _seed_linked_concept(client, session, tenant)

        first = await client.post(
            _url(tenant, "/generate?range_kind=last_7_days"),
            headers=tenant["headers"],
        )
        assert first.status_code == 200
        body = first.json()
        assert body["snapshot_id"] is not None
        assert body["report"]["summary"]["entities_total"] >= 1
        assert body["report"]["fingerprint"]

        summary = await client.get(_url(tenant, "/summary"), headers=tenant["headers"])
        assert summary.status_code == 200
        assert summary.json()["status"] == "available"
        assert summary.json()["fingerprint"] == body["report"]["fingerprint"]

        patterns = await client.get(_url(tenant, "/patterns"), headers=tenant["headers"])
        assert patterns.json()["status"] == "available"

        recs = await client.get(
            _url(tenant, "/recommendations"), headers=tenant["headers"]
        )
        assert all(item["review_only"] for item in recs.json()["items"])

        profiles = await client.get(_url(tenant, "/profiles"), headers=tenant["headers"])
        assert len(profiles.json()["items"]) >= 1

        learnings = await client.get(
            _url(tenant, "/learnings"), headers=tenant["headers"]
        )
        assert learnings.status_code == 200

    async def test_recompute_is_idempotent_by_fingerprint(
        self, client: AsyncClient, session, tenant
    ):
        await _seed_linked_concept(client, session, tenant)
        url = _url(tenant, "/generate?range_kind=last_7_days")
        first = await client.post(url, headers=tenant["headers"])
        second = await client.post(url, headers=tenant["headers"])
        assert second.json()["created"] is False
        assert second.json()["snapshot_id"] == first.json()["snapshot_id"]
        assert (
            second.json()["report"]["fingerprint"]
            == first.json()["report"]["fingerprint"]
        )

    async def test_different_ranges_produce_distinct_snapshots(
        self, client: AsyncClient, session, tenant
    ):
        await _seed_linked_concept(client, session, tenant)
        seven = await client.post(
            _url(tenant, "/generate?range_kind=last_7_days"),
            headers=tenant["headers"],
        )
        fourteen = await client.post(
            _url(tenant, "/generate?range_kind=last_14_days"),
            headers=tenant["headers"],
        )
        assert (
            seven.json()["report"]["fingerprint"]
            != fourteen.json()["report"]["fingerprint"]
        )


class TestSnapshotReads:
    async def test_reads_before_generate_are_explicit_no_snapshot(
        self, client: AsyncClient, tenant
    ):
        for section in ("summary", "patterns", "learnings", "recommendations", "profiles"):
            response = await client.get(
                _url(tenant, f"/{section}"), headers=tenant["headers"]
            )
            assert response.status_code == 200
            assert response.json()["status"] == "no_snapshot"

    async def test_snapshot_list_and_detail(self, client: AsyncClient, session, tenant):
        await _seed_linked_concept(client, session, tenant)
        await client.post(_url(tenant, "/generate"), headers=tenant["headers"])

        listing = await client.get(_url(tenant, "/snapshots"), headers=tenant["headers"])
        assert listing.status_code == 200
        rows = listing.json()
        assert len(rows) >= 1
        assert rows[0]["fingerprint"]

        detail = await client.get(
            _url(tenant, f"/snapshots/{rows[0]['id']}"), headers=tenant["headers"]
        )
        assert detail.status_code == 200
        assert "Decimal" not in detail.text  # JSON-safe persisted payload

    async def test_unknown_snapshot_404(self, client: AsyncClient, tenant):
        response = await client.get(
            _url(tenant, f"/snapshots/{uuid.uuid4()}"), headers=tenant["headers"]
        )
        assert response.status_code == 404


class TestTenancyAndRbac:
    async def test_cross_tenant_business_read_404(self, client: AsyncClient, session, tenant):
        other = await create_tenant(session)
        response = await client.get(
            LEARNING.format(business_id=tenant["business"].id) + "/summary",
            headers=other["headers"],
        )
        assert response.status_code == 404

    async def test_cross_tenant_generate_404(self, client: AsyncClient, session, tenant):
        other = await create_tenant(session)
        response = await client.post(
            LEARNING.format(business_id=tenant["business"].id) + "/generate",
            headers=other["headers"],
        )
        assert response.status_code == 404

    async def test_cross_tenant_snapshot_detail_404(
        self, client: AsyncClient, session, tenant
    ):
        await _seed_linked_concept(client, session, tenant)
        await client.post(_url(tenant, "/generate"), headers=tenant["headers"])
        listing = await client.get(_url(tenant, "/snapshots"), headers=tenant["headers"])
        snapshot_id = listing.json()[0]["id"]

        other = await create_tenant(session)
        response = await client.get(
            LEARNING.format(business_id=tenant["business"].id)
            + f"/snapshots/{snapshot_id}",
            headers=other["headers"],
        )
        assert response.status_code == 404

    async def _viewer_headers(self, session, tenant):
        viewer = await create_user(session)
        role = await create_role(
            session,
            name="viewer",
            organization_id=tenant["org"].id,
            permissions=sorted(DEFAULT_ROLES["viewer"]),
        )
        await create_membership(session, user=viewer, organization=tenant["org"], role=role)
        await session.commit()
        return await auth_headers(session, viewer, tenant["org"].id)

    async def test_viewer_cannot_generate(self, client: AsyncClient, session, tenant):
        viewer_headers = await self._viewer_headers(session, tenant)
        response = await client.post(
            _url(tenant, "/generate"), headers=viewer_headers
        )
        assert response.status_code == 403

    async def test_owner_can_read_own_snapshots(self, client: AsyncClient, session, tenant):
        await _seed_linked_concept(client, session, tenant)
        await client.post(_url(tenant, "/generate"), headers=tenant["headers"])
        listing = await client.get(_url(tenant, "/snapshots"), headers=tenant["headers"])
        assert listing.status_code == 200
