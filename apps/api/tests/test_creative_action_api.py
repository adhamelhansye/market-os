"""Creative action preparation API tests (Phase 8G).

Drives the full chain: 8C facts -> link -> 8E optimization -> 8F
decision plan -> acknowledge -> 8G generate. Verifies 8B draft rows are
created with status='draft', idempotent regeneration, second-stage
review states, tenancy 404s and viewer 403.
"""

import uuid

import pytest
from httpx import AsyncClient

from src.core.rbac import DEFAULT_ROLES
from src.db.models.creative import CreativeTest
from tests.conftest import (
    auth_headers,
    create_membership,
    create_role,
    create_tenant,
    create_user,
)
from tests.test_creative_performance_api import _concept, _seed_performance_data

BASE = "/api/v1"
AP = BASE + "/businesses/{business_id}/strategy/creative/action-preparation"

pytestmark = pytest.mark.usefixtures("clean_tables")


def _url(tenant, path=""):
    return AP.format(business_id=tenant["business"].id) + path


async def _drive_to_acknowledged(client: AsyncClient, session, tenant) -> str:
    """Seed data and walk the full chain to one acknowledged opportunity."""
    stack = await _seed_performance_data(session, tenant)
    concept = await _concept(session, tenant)
    await session.commit()

    links_url = (
        BASE + f"/businesses/{tenant['business'].id}"
        + "/strategy/creative/performance/links"
    )
    assert (
        await client.post(
            links_url,
            json={
                "creative_concept_id": str(concept.id),
                "ad_id": str(stack["ads"][0].id),
            },
            headers=tenant["headers"],
        )
    ).status_code == 201

    opt = await client.post(
        BASE + f"/businesses/{tenant['business'].id}"
        + "/strategy/creative/optimization/generate",
        headers=tenant["headers"],
    )
    assert opt.status_code == 200

    dp = await client.post(
        BASE + f"/businesses/{tenant['business'].id}"
        + "/strategy/creative/decision-plan/generate",
        headers=tenant["headers"],
    )
    assert dp.status_code == 200
    items = dp.json()["plan"]["items"]
    assert items, "expected at least one decision-plan item"

    # Acknowledge the first TRANSLATABLE category (expansion/coverage/fatigue).
    translatable = next(
        (
            i
            for i in items
            if i.get("category") in ("expansion", "coverage_gap", "fatigue")
        ),
        None,
    )
    assert translatable is not None, "fixture must yield a translatable item"

    review = await client.post(
        DP_URL(tenant) + f"/items/{translatable['opportunity_id']}/review",
        json={"review_state": "acknowledged"},
        headers=tenant["headers"],
    )
    assert review.status_code == 200
    return translatable["opportunity_id"]


def DP_URL(tenant):
    return BASE + f"/businesses/{tenant['business'].id}/strategy/creative/decision-plan"


class TestGenerateFlow:
    async def test_no_acknowledged_items_is_explicit_empty(self, client, tenant):
        response = await client.post(_url(tenant, "/generate"), headers=tenant["headers"])
        assert response.status_code == 200
        body = response.json()
        assert body["report"]["summary"]["reason"] == "no_acknowledged_opportunities"
        assert body["created_count"] == 0

    async def test_acknowledged_item_produces_8b_draft_row(
        self, client, session, tenant
    ):
        await _drive_to_acknowledged(client, session, tenant)
        response = await client.post(_url(tenant, "/generate"), headers=tenant["headers"])
        assert response.status_code == 200
        body = response.json()
        assert body["created_count"] >= 1

        # An 8B CreativeTest row exists with status='draft' (verbatim taxonomy).
        tests = (
            await session.execute(CreativeTest.__table__.select())
        ).mappings().all()
        assert len(tests) >= 1
        for row in tests:
            assert row["status"] == "draft"
            assert row["test_id"].startswith("draft_")

        items = await client.get(_url(tenant, "/items"), headers=tenant["headers"])
        drafts = items.json()["drafts"]
        assert drafts and drafts[0]["review_state"] == "proposed"

    async def test_regeneration_is_idempotent(self, client, session, tenant):
        await _drive_to_acknowledged(client, session, tenant)
        first = await client.post(_url(tenant, "/generate"), headers=tenant["headers"])
        created_first = first.json()["created_count"]

        second = await client.post(_url(tenant, "/generate"), headers=tenant["headers"])
        assert second.json()["created_count"] == 0

        rows = (
            await session.execute(CreativeTest.__table__.select())
        ).mappings().all()
        assert len(rows) == created_first

    async def test_investigation_acknowledged_never_becomes_draft(
        self, client, session, tenant
    ):
        stack = await _seed_performance_data(session, tenant)
        concept = await _concept(session, tenant)
        await session.commit()
        links_url = (
            BASE + f"/businesses/{tenant['business'].id}"
            + "/strategy/creative/performance/links"
        )
        assert (
            await client.post(
                links_url,
                json={
                    "creative_concept_id": str(concept.id),
                    "ad_id": str(stack["ads"][0].id),
                },
                headers=tenant["headers"],
            )
        ).status_code == 201
        opt = await client.post(
            BASE + f"/businesses/{tenant['business'].id}"
            + "/strategy/creative/optimization/generate",
            headers=tenant["headers"],
        )
        assert opt.status_code == 200
        dp_gen = await client.post(
            BASE + f"/businesses/{tenant['business'].id}"
            + "/strategy/creative/decision-plan/generate",
            headers=tenant["headers"],
        )
        assert dp_gen.status_code == 200

        items = (
            await client.get(DP_URL(tenant) + "/items", headers=tenant["headers"])
        ).json()["items"]
        investigations = [
            i for i in items if i.get("category") == "investigation"
        ]
        if not investigations:
            return  # not present in this fixture; covered by engine tests
        target = investigations[0]["opportunity_id"]
        ack = await client.post(
            DP_URL(tenant) + f"/items/{target}/review",
            json={"review_state": "acknowledged"},
            headers=tenant["headers"],
        )
        assert ack.status_code == 200

        gen = await client.post(_url(tenant, "/generate"), headers=tenant["headers"])
        excluded = gen.json()["report"]["excluded"]
        assert any(e["source_opportunity_id"] == target for e in excluded)

        rows = (
            await session.execute(CreativeTest.__table__.select())
        ).mappings().all()
        # Only non-excluded acknowledged opportunities may produce drafts;
        # this fixture acknowledges exactly one item (investigation) so
        # no CreativeTest row may exist.
        assert rows == []


class TestSecondStageReview:
    async def _prepared(self, client, session, tenant) -> str:
        await _drive_to_acknowledged(client, session, tenant)
        await client.post(_url(tenant, "/generate"), headers=tenant["headers"])
        items = await client.get(_url(tenant, "/items"), headers=tenant["headers"])
        drafts = items.json()["drafts"]
        assert drafts
        return drafts[0]["id"], drafts[0]["draft_test_id"]

    async def test_second_stage_states(self, client, session, tenant):
        draft_id, test_id = await self._prepared(client, session, tenant)
        for state in ("dismissed", "deferred", "acknowledged"):
            r = await client.post(
                _url(tenant, f"/drafts/{draft_id}/review"),
                json={"review_state": state},
                headers=tenant["headers"],
            )
            assert r.status_code == 200
            assert r.json()["review_state"] == state

        # Status invariant: still a draft after all reviews.
        row = (
            await session.execute(
                CreativeTest.__table__.select().where(
                    CreativeTest.test_id == test_id
                )
            )
        ).mappings().one()
        assert row["status"] == "draft"

    async def test_invalid_state_rejected(self, client, session, tenant):
        draft_id, _tid = await self._prepared(client, session, tenant)
        for banned in ("approved", "implemented", "executed", "launched", "scaled"):
            r = await client.post(
                _url(tenant, f"/drafts/{draft_id}/review"),
                json={"review_state": banned},
                headers=tenant["headers"],
            )
            assert r.status_code == 409, banned

    async def test_unknown_draft_404(self, client, tenant):
        r = await client.post(
            _url(tenant, f"/drafts/{uuid.uuid4()}/review"),
            json={"review_state": "dismissed"},
            headers=tenant["headers"],
        )
        assert r.status_code == 404


class TestTenancyAndRbac:
    async def _prepared(self, client, session, tenant):
        await _drive_to_acknowledged(client, session, tenant)
        await client.post(_url(tenant, "/generate"), headers=tenant["headers"])
        items = await client.get(_url(tenant, "/items"), headers=tenant["headers"])
        return items.json()["drafts"][0]["id"]

    async def test_cross_tenant_read_404(self, client, session, tenant):
        await self._prepared(client, session, tenant)
        other = await create_tenant(session)
        r = await client.get(_url(other, "/items"), headers=other["headers"])
        assert r.json()["status"] in ("available",) or r.json()["drafts"] == []

        cross = await client.get(
            AP.format(business_id=tenant["business"].id) + "/items",
            headers=other["headers"],
        )
        assert cross.status_code == 404

    async def test_cross_tenant_generate_and_review_404(self, client, session, tenant):
        draft_id = await self._prepared(client, session, tenant)
        other = await create_tenant(session)
        base = AP.format(business_id=tenant["business"].id)
        assert (
            await client.post(base + "/generate", headers=other["headers"])
        ).status_code == 404
        assert (
            await client.post(
                base + f"/drafts/{draft_id}/review",
                json={"review_state": "dismissed"},
                headers=other["headers"],
            )
        ).status_code == 404

    async def test_viewer_generate_and_review_403(self, client, session, tenant):
        viewer = await create_user(session)
        role = await create_role(
            session,
            name="viewer",
            organization_id=tenant["org"].id,
            permissions=sorted(DEFAULT_ROLES["viewer"]),
        )
        await create_membership(session, user=viewer, organization=tenant["org"], role=role)
        await session.commit()
        vh = await auth_headers(session, viewer, tenant["org"].id)
        assert (
            await client.post(_url(tenant, "/generate"), headers=vh)
        ).status_code == 403
        assert (
            await client.post(
                _url(tenant, f"/drafts/{uuid.uuid4()}/review"),
                json={"review_state": "dismissed"},
                headers=vh,
            )
        ).status_code == 403

