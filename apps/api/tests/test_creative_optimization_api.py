"""Creative optimization API tests (Phase 8E).

Covers: generate/persist flow, explicit no-snapshot state, idempotent
recomputation, snapshot reads, blocked opportunities, tenancy 404s and
viewer-role 403.
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
OPT = BASE + "/businesses/{business_id}/strategy/creative/optimization"

pytestmark = pytest.mark.usefixtures("clean_tables")


def _url(tenant, path=""):
    return OPT.format(business_id=tenant["business"].id) + path


async def _seed_linked(client: AsyncClient, session, tenant: dict):
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


class TestGenerateFlow:
    async def test_generate_without_links_is_unavailable(self, client, tenant):
        response = await client.post(_url(tenant, "/generate"), headers=tenant["headers"])
        assert response.status_code == 200
        body = response.json()
        assert body["snapshot_id"] is None
        assert body["plan"]["optimization_status"] == "unavailable"
        assert body["plan"]["summary"]["reason"] == "no_performance_links_recorded"

    async def test_generate_persists_and_serves_projections(
        self, client, session, tenant
    ):
        await _seed_linked(client, session, tenant)
        first = await client.post(_url(tenant, "/generate"), headers=tenant["headers"])
        assert first.status_code == 200
        body = first.json()
        assert body["snapshot_id"] is not None
        plan = body["plan"]
        assert plan["rules_versions"]["engine"] == "copt-v1"
        for opportunity in plan["opportunities"]:
            assert opportunity["review_only"] is True

        summary = await client.get(_url(tenant, "/summary"), headers=tenant["headers"])
        assert summary.status_code == 200
        data = summary.json()
        assert data["status"] == "available"
        assert data["fingerprint"] == plan["fingerprint"]

        opps = await client.get(
            _url(tenant, "/opportunities"), headers=tenant["headers"]
        )
        assert opps.json()["status"] == "available"

        tests = await client.get(_url(tenant, "/tests"), headers=tenant["headers"])
        assert tests.status_code == 200

        refresh = await client.get(_url(tenant, "/refresh"), headers=tenant["headers"])
        assert refresh.status_code == 200

        coverage = await client.get(_url(tenant, "/coverage"), headers=tenant["headers"])
        assert coverage.status_code == 200
        assert coverage.json()["status"] == "available"

        portfolio = await client.get(
            _url(tenant, "/portfolio"), headers=tenant["headers"]
        )
        assert portfolio.json()["status"] == "available"

        conflicts = await client.get(
            _url(tenant, "/conflicts"), headers=tenant["headers"]
        )
        assert conflicts.status_code == 200

    async def test_recompute_idempotent_by_fingerprint(self, client, session, tenant):
        await _seed_linked(client, session, tenant)
        url = _url(tenant, "/generate")
        first = await client.post(url, headers=tenant["headers"])
        second = await client.post(url, headers=tenant["headers"])
        assert second.json()["created"] is False
        assert second.json()["snapshot_id"] == first.json()["snapshot_id"]
        assert (
            second.json()["plan"]["fingerprint"]
            == first.json()["plan"]["fingerprint"]
        )


class TestSnapshotReads:
    async def test_reads_before_generate_are_no_snapshot(self, client, tenant):
        for section in ("opportunities", "tests", "refresh", "portfolio", "conflicts"):
            response = await client.get(
                _url(tenant, f"/{section}"), headers=tenant["headers"]
            )
            assert response.status_code == 200
            assert response.json()["status"] == "no_snapshot"

    async def test_snapshot_list_detail_json_safe(self, client, session, tenant):
        await _seed_linked(client, session, tenant)
        await client.post(_url(tenant, "/generate"), headers=tenant["headers"])
        listing = await client.get(_url(tenant, "/snapshots"), headers=tenant["headers"])
        rows = listing.json()
        assert len(rows) >= 1
        detail = await client.get(
            _url(tenant, f"/snapshots/{rows[0]['id']}"), headers=tenant["headers"]
        )
        assert detail.status_code == 200
        assert "Decimal" not in detail.text

    async def test_unknown_snapshot_404(self, client, tenant):
        response = await client.get(
            _url(tenant, f"/snapshots/{uuid.uuid4()}"), headers=tenant["headers"]
        )
        assert response.status_code == 404


class TestTenancyAndRbac:
    async def test_cross_tenant_read_404(self, client, session, tenant):
        other = await create_tenant(session)
        response = await client.get(
            OPT.format(business_id=tenant["business"].id) + "/summary",
            headers=other["headers"],
        )
        assert response.status_code == 404

    async def test_cross_tenant_generate_404(self, client, session, tenant):
        other = await create_tenant(session)
        response = await client.post(
            OPT.format(business_id=tenant["business"].id) + "/generate",
            headers=other["headers"],
        )
        assert response.status_code == 404

    async def test_cross_tenant_snapshot_detail_404(self, client, session, tenant):
        await _seed_linked(client, session, tenant)
        await client.post(_url(tenant, "/generate"), headers=tenant["headers"])
        listing = await client.get(_url(tenant, "/snapshots"), headers=tenant["headers"])
        snapshot_id = listing.json()[0]["id"]
        other = await create_tenant(session)
        response = await client.get(
            OPT.format(business_id=tenant["business"].id) + f"/snapshots/{snapshot_id}",
            headers=other["headers"],
        )
        assert response.status_code == 404

    async def test_viewer_cannot_generate(self, client, session, tenant):
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
        response = await client.post(_url(tenant, "/generate"), headers=viewer_headers)
        assert response.status_code == 403

    async def test_owner_reads_own_snapshots(self, client, session, tenant):
        await _seed_linked(client, session, tenant)
        await client.post(_url(tenant, "/generate"), headers=tenant["headers"])
        listing = await client.get(_url(tenant, "/snapshots"), headers=tenant["headers"])
        assert listing.status_code == 200
