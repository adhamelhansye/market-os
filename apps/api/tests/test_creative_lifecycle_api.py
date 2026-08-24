"""Creative test lifecycle API tests (Phase 8H).

Covers: strict activation gate (only acknowledged + draft), single
activation, bounded transitions, role restriction (member/viewer 403),
cross-tenant 404s and immutable event history with provenance.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from src.core.rbac import DEFAULT_ROLES
from src.db.models.creative import CreativeTest
from src.db.models.creative_action import (
    CreativeActionDraft,
    CreativeTestActivation,
)
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
AP = BASE + "/businesses/{business_id}/strategy/creative/action-preparation"

pytestmark = pytest.mark.usefixtures("clean_tables")


def _ap(tenant, path=""):
    return AP.format(business_id=tenant["business"].id) + path


def _dp(tenant, path=""):
    return DP.format(business_id=tenant["business"].id) + path


async def _prepared_draft(client: AsyncClient, session, tenant) -> dict:
    """Drive 8C -> 8E -> 8F -> acknowledge -> 8G draft; return the row."""
    stack = await _seed_performance_data(session, tenant)
    concept = await _concept(session, tenant)
    await session.commit()

    assert (
        await client.post(
            BASE + f"/businesses/{tenant['business'].id}"
            + "/strategy/creative/performance/links",
            json={
                "creative_concept_id": str(concept.id),
                "ad_id": str(stack["ads"][0].id),
            },
            headers=tenant["headers"],
        )
    ).status_code == 201
    # Real chain: optimization generate -> decision plan generate ->
    # acknowledge first translatable item -> action drafts.
    opt_gen = await client.post(
        BASE + f"/businesses/{tenant['business'].id}"
        + "/strategy/creative/optimization/generate",
        headers=tenant["headers"],
    )
    assert opt_gen.status_code == 200
    dp_gen = await client.post(
        _dp(tenant, "/generate"), headers=tenant["headers"]
    )
    assert dp_gen.status_code == 200
    items = (
        await client.get(_dp(tenant, "/items"), headers=tenant["headers"])
    ).json()["items"]
    translatable = next(
        i for i in items if i.get("category") in ("expansion", "coverage_gap", "fatigue")
    )
    ack = await client.post(
        _dp(tenant, f"/items/{translatable['opportunity_id']}/review"),
        json={"review_state": "acknowledged"},
        headers=tenant["headers"],
    )
    assert ack.status_code == 200

    gen = await client.post(_ap(tenant, "/generate"), headers=tenant["headers"])
    assert gen.status_code == 200
    drafts = (
        await client.get(_ap(tenant, "/items"), headers=tenant["headers"])
    ).json()["drafts"]
    assert drafts

    # Human Review #2: the draft itself must be acknowledged before
    # activation (strict gate under test).
    ack2 = await client.post(
        _ap(tenant, f"/drafts/{drafts[0]['id']}/review"),
        json={"review_state": "acknowledged"},
        headers=tenant["headers"],
    )
    assert ack2.status_code == 200
    return drafts[0]


async def test_full_activation_flow(client: AsyncClient, session, tenant):
    draft = await _prepared_draft(client, session, tenant)

    activate_url = _ap(tenant, f"/drafts/{draft['id']}/activate")
    response = await client.post(activate_url, headers=tenant["headers"])
    if response.status_code != 200:
        print("ACT-FAIL:", response.status_code, response.text[:300])
    assert response.status_code == 200
    assert response.json()["review_state"] == "acknowledged"

    # Status moved to active.
    row = (
        await session.execute(
            select(CreativeTest).where(CreativeTest.test_id == draft["draft_test_id"])
        )
    ).scalar_one()
    assert row.status == "active"

    # Immutable event recorded with provenance fields.
    events = (
        await session.execute(select(CreativeTestActivation))
    ).scalars().all()
    assert len(events) == 1
    event = events[0]
    assert event.previous_status == "draft"
    assert event.new_status == "active"
    assert event.source_opportunity_id == draft["source_opportunity_id"]
    assert event.source_plan_fingerprint
    assert event.activated_by is not None

    # Lifecycle history endpoint reflects it.
    history = await client.get(
        _ap(tenant, f"/tests/{draft['draft_test_id']}/lifecycle"),
        headers=tenant["headers"],
    )
    assert history.status_code == 200
    entries = history.json()
    assert len(entries) == 1
    assert entries[0]["new_status"] == "active"


class TestActivationGates:
    async def test_double_activation_conflict(self, client, session, tenant):
        draft = await _prepared_draft(client, session, tenant)
        url = _ap(tenant, f"/drafts/{draft['id']}/activate")
        first = await client.post(url, headers=tenant["headers"])
        assert first.status_code == 200
        second = await client.post(url, headers=tenant["headers"])
        assert second.status_code == 409

    async def test_proposed_review_blocks_activation(self, client, session, tenant):
        # Drive the chain but leave the review in proposed state by
        # acknowledging a different item if one exists; otherwise skip.
        draft = await _prepared_draft(client, session, tenant)
        # Reset review to proposed is not an allowed transition; instead
        # verify the gate via a fresh draft whose review we dismiss then
        # re-acknowledge... Simplest deterministic check: activation of an
        # already-activated draft was covered above. For the strict-gate
        # matrix we manipulate the draft row directly.
        from sqlalchemy import update

        await session.execute(
            update(CreativeActionDraft)
            .where(CreativeActionDraft.id == uuid.UUID(draft["id"]))
            .values(review_state="proposed")
        )
        await session.commit()
        url = _ap(tenant, f"/drafts/{draft['id']}/activate")
        response = await client.post(url, headers=tenant["headers"])
        assert response.status_code == 409
        assert "acknowledged" in response.json()["error"]["message"]

    async def test_dismissed_review_blocks_activation(self, client, session, tenant):
        draft = await _prepared_draft(client, session, tenant)
        from sqlalchemy import update

        await session.execute(
            update(CreativeActionDraft)
            .where(CreativeActionDraft.id == uuid.UUID(draft["id"]))
            .values(review_state="dismissed")
        )
        await session.commit()
        response = await client.post(
            _ap(tenant, f"/drafts/{draft['id']}/activate"),
            headers=tenant["headers"],
        )
        assert response.status_code == 409

    async def test_deferred_review_blocks_activation(self, client, session, tenant):
        draft = await _prepared_draft(client, session, tenant)
        from sqlalchemy import update

        await session.execute(
            update(CreativeActionDraft)
            .where(CreativeActionDraft.id == uuid.UUID(draft["id"]))
            .values(review_state="deferred")
        )
        await session.commit()
        response = await client.post(
            _ap(tenant, f"/drafts/{draft['id']}/activate"),
            headers=tenant["headers"],
        )
        assert response.status_code == 409

    async def test_non_draft_status_blocks_reactivation(self, client, session, tenant):
        draft = await _prepared_draft(client, session, tenant)
        url = _ap(tenant, f"/drafts/{draft['id']}/activate")
        assert (
            await client.post(url, headers=tenant["headers"])
        ).status_code == 200
        # Force status back to draft to simulate out-of-band mutation;
        # the prior activation event must still block re-activation.
        from sqlalchemy import update

        await session.execute(
            update(CreativeTest)
            .where(CreativeTest.test_id == draft["draft_test_id"])
            .values(status="draft")
        )
        await session.commit()
        response = await client.post(url, headers=tenant["headers"])
        assert response.status_code == 409


class TestLifecycleTransitions:
    async def test_active_to_completed_and_cancelled_blocked_after(self, client, session, tenant):
        draft = await _prepared_draft(client, session, tenant)
        activate_url = _ap(tenant, f"/drafts/{draft['id']}/activate")
        lifecycle_url = _ap(tenant, f"/tests/{draft['draft_test_id']}/lifecycle")

        assert (
            await client.post(activate_url, headers=tenant["headers"])
        ).status_code == 200
        done = await client.post(
            lifecycle_url, json={"target_status": "completed"}, headers=tenant["headers"]
        )
        assert done.status_code == 200
        assert done.json()["previous_status"] == "active"
        assert done.json()["new_status"] == "completed"

        # Bounded machine rejects reactivation-style jumps.
        blocked = await client.post(
            lifecycle_url, json={"target_status": "cancelled"}, headers=tenant["headers"]
        )
        assert blocked.status_code == 409

    async def test_direct_draft_to_completed_rejected(self, client, session, tenant):
        draft = await _prepared_draft(client, session, tenant)
        response = await client.post(
            _ap(tenant, f"/tests/{draft['draft_test_id']}/lifecycle"),
            json={"target_status": "completed"},
            headers=tenant["headers"],
        )
        assert response.status_code == 409

    async def test_invalid_target_rejected(self, client, session, tenant):
        draft = await _prepared_draft(client, session, tenant)
        response = await client.post(
            _ap(tenant, f"/tests/{draft['draft_test_id']}/lifecycle"),
            json={"target_status": "active"},
            headers=tenant["headers"],
        )
        assert response.status_code == 409


class TestRolesAndTenancy:
    def _role_headers(self, **kwargs):
        return kwargs

    async def _make_role_user(self, session, tenant, permissions, role_name):
        user = await create_user(session)
        role = await create_role(
            session,
            name=role_name,
            organization_id=tenant["org"].id,
            permissions=sorted(permissions),
        )
        await create_membership(session, user=user, organization=tenant["org"], role=role)
        await session.commit()
        return await auth_headers(session, user, tenant["org"].id)

    async def test_member_cannot_activate_403(self, client, session, tenant):
        draft = await _prepared_draft(client, session, tenant)
        # Member has business:write but NOT creative:lifecycle.
        member_perms = set(DEFAULT_ROLES["member"])
        member_headers = await self._make_role_user(
            session, tenant, member_perms, "member-test"
        )
        response = await client.post(
            _ap(tenant, f"/drafts/{draft['id']}/activate"), headers=member_headers
        )
        assert response.status_code == 403

    async def test_viewer_cannot_activate_403(self, client, session, tenant):
        draft = await _prepared_draft(client, session, tenant)
        viewer_headers = await self._make_role_user(
            session, tenant, DEFAULT_ROLES["viewer"], "viewer-test"
        )
        response = await client.post(
            _ap(tenant, f"/drafts/{draft['id']}/activate"), headers=viewer_headers
        )
        assert response.status_code == 403

    async def test_admin_can_activate(self, client, session, tenant):
        draft = await _prepared_draft(client, session, tenant)
        admin_perms = set(DEFAULT_ROLES["admin"]) | {"creative:lifecycle"}
        admin_headers = await self._make_role_user(
            session, tenant, admin_perms, "admin-test"
        )
        response = await client.post(
            _ap(tenant, f"/drafts/{draft['id']}/activate"), headers=admin_headers
        )
        assert response.status_code == 200

    async def test_cross_tenant_activate_404(self, client, session, tenant):
        draft = await _prepared_draft(client, session, tenant)
        other = await create_tenant(session)
        response = await client.post(
            AP.format(business_id=tenant["business"].id)
            + f"/drafts/{draft['id']}/activate",
            headers=other["headers"],
        )
        assert response.status_code == 404

    async def test_cross_tenant_lifecycle_404(self, client, session, tenant):
        other = await create_tenant(session)
        response = await client.post(
            AP.format(business_id=tenant["business"].id)
            + f"/tests/{uuid.uuid4()}/lifecycle",
            json={"target_status": "completed"},
            headers=other["headers"],
        )
        assert response.status_code == 404
