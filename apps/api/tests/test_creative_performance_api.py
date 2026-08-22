"""Creative performance API tests (Phase 8C).

Covers: report/attribution flow, link validation, tenancy isolation,
RBAC, snapshot reproducibility and JSON-safe payloads.
"""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from src.core.rbac import DEFAULT_ROLES
from src.db.models.creative import CreativeConcept, CreativeTest, CreativeTestVariant
from tests.conftest import auth_headers, create_membership, create_role, create_tenant, create_user
from tests.test_metrics import _ad_stack, _insight

pytestmark = pytest.mark.usefixtures("clean_tables")

BASE = "/api/v1"
REPORT_URL = BASE + "/businesses/{business_id}/strategy/creative/performance/report"


async def _concept(session, tenant: dict, **overrides) -> CreativeConcept:
    concept = CreativeConcept(
        organization_id=tenant["org"].id,
        business_id=tenant["business"].id,
        strategy_version="v1",
        creative_format="static",
        funnel_stage="awareness",
        angle="problem_agitation",
        hook_direction="problem_agitation",
        status="draft",
        **overrides,
    )
    session.add(concept)
    await session.flush()
    return concept


def _link_payload(*, concept_id=None, variant_id=None, ad_id=None, creative_id=None, label=None):
    payload = {}
    if label:
        payload["label"] = label
    if concept_id:
        payload["creative_concept_id"] = str(concept_id)
    if variant_id:
        payload["creative_test_variant_id"] = str(variant_id)
    if ad_id:
        payload["ad_id"] = str(ad_id)
    if creative_id:
        payload["provider_creative_id"] = str(creative_id)
    return payload


async def _seed_performance_data(session, tenant: dict) -> dict:
    """Ad stack plus three days of insights (enough for classification)."""
    stack = await _ad_stack(session, tenant["business"])
    today = date.today()
    for offset in range(3):
        day = today - timedelta(days=offset)
        for index in (1, 2):
            await _insight(
                session,
                tenant["business"],
                stack,
                campaign_index=index,
                day=day,
                impressions=1000,
                clicks=20 if index == 1 else 10,
                spend="120.00",
                conversions=4 if index == 1 else 2,
                conversion_value="300.00" if index == 1 else "150.00",
                reach=800,
            )
    return stack


# ---------------------------------------------------------------------------
# Report / attribution
# ---------------------------------------------------------------------------


class TestReportAttribution:
    async def test_report_without_links_is_unavailable(self, client: AsyncClient, tenant):
        response = await client.get(
            REPORT_URL.format(business_id=tenant["business"].id), headers=tenant["headers"]
        )
        assert response.status_code == 200
        body = response.json()
        assert body["attribution"]["status"] == "unavailable"
        assert body["attribution"]["reason"] == "no_performance_links_recorded"
        assert body["entities"] == []

    async def test_linked_concept_appears_with_provenance(
        self, client: AsyncClient, session, tenant
    ):
        stack = await _seed_performance_data(session, tenant)
        concept = await _concept(session, tenant)
        await session.commit()

        created = await client.post(
            BASE + f"/businesses/{tenant['business'].id}/strategy/creative/performance/links",
            json=_link_payload(concept_id=concept.id, ad_id=stack["ads"][0].id),
            headers=tenant["headers"],
        )
        assert created.status_code == 201

        report = await client.get(
            REPORT_URL.format(business_id=tenant["business"].id), headers=tenant["headers"]
        )
        assert report.status_code == 200
        body = report.json()
        assert body["attribution"]["status"] == "linked"
        entity = next(e for e in body["entities"] if e["entity"]["id"] == str(concept.id))
        assert entity["attribution"]["status"] == "linked"
        ctr_signal = next(s for s in entity["signals"] if s["code"] == "ctr")
        assert ctr_signal["status"] == "available"
        chain_steps = [step["step"] for step in entity["provenance"]["chain"]]
        assert chain_steps[0] == "entity" and "campaign" in chain_steps
        # money serialized as string, never float
        spend_signal = next(s for s in entity["signals"] if s["code"] == "spend")
        assert isinstance(spend_signal["value"], str)

    async def test_entity_unlinked_attribution_unavailable(
        self, client: AsyncClient, session, tenant
    ):
        concept = await _concept(session, tenant)
        await session.commit()
        url = (
            BASE
            + f"/businesses/{tenant['business'].id}"
            + f"/strategy/creative/performance/entities/creative_concept/{concept.id}"
        )
        response = await client.get(url, headers=tenant["headers"])
        assert response.status_code == 200
        body = response.json()
        assert body["attribution"]["status"] == "unavailable"
        assert body["attribution"]["reason"] == "no_performance_link_recorded"

    async def test_variant_link_carries_test_context(self, client: AsyncClient, session, tenant):
        stack = await _seed_performance_data(session, tenant)
        test = CreativeTest(
            organization_id=tenant["org"].id,
            business_id=tenant["business"].id,
            test_id=f"t-{uuid4hex()}",
            name="Hook test",
            objective="CTR",
            test_variable="hook_direction",
            hypothesis="H1",
            success_metric="ctr",
        )
        session.add(test)
        await session.flush()
        variant = CreativeTestVariant(
            organization_id=tenant["org"].id,
            business_id=tenant["business"].id,
            test_id=test.test_id,
            variant_id="v1",
            test_variable_value="problem_agitation",
        )
        session.add(variant)
        await session.flush()
        await session.commit()

        created = await client.post(
            BASE + f"/businesses/{tenant['business'].id}/strategy/creative/performance/links",
            json=_link_payload(variant_id=variant.id, ad_id=stack["ads"][1].id),
            headers=tenant["headers"],
        )
        assert created.status_code == 201
        report = await client.get(
            REPORT_URL.format(business_id=tenant["business"].id), headers=tenant["headers"]
        )
        entity = next(
            e
            for e in report.json()["entities"]
            if e["entity"]["type"] == "creative_test_variant"
        )
        assert entity["context"]["test_variable"] == "hook_direction"
        steps = [step["step"] for step in entity["provenance"]["chain"]]
        assert "creative_test" in steps


def uuid4hex() -> str:
    import uuid

    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# Link validation
# ---------------------------------------------------------------------------


class TestLinkValidation:
    async def _setup(self, session, tenant):
        stack = await _ad_stack(session, tenant["business"])
        concept = await _concept(session, tenant)
        await session.commit()
        return stack, concept

    async def test_both_provider_sides_rejected(self, client, session, tenant):
        stack, concept = await self._setup(session, tenant)
        response = await client.post(
            BASE + f"/businesses/{tenant['business'].id}/strategy/creative/performance/links",
            json=_link_payload(concept_id=concept.id, ad_id=stack["ads"][0].id,
                               creative_id=stack["ads"][0].id),
            headers=tenant["headers"],
        )
        assert response.status_code == 409

    async def test_neither_internal_side_rejected(self, client, session, tenant):
        stack, _concept = await self._setup(session, tenant)
        response = await client.post(
            BASE + f"/businesses/{tenant['business'].id}/strategy/creative/performance/links",
            json=_link_payload(ad_id=stack["ads"][0].id),
            headers=tenant["headers"],
        )
        assert response.status_code == 409

    async def test_unknown_concept_404(self, client, session, tenant):
        import uuid as uuid_mod

        stack, _concept = await self._setup(session, tenant)
        response = await client.post(
            BASE + f"/businesses/{tenant['business'].id}/strategy/creative/performance/links",
            json=_link_payload(concept_id=uuid_mod.uuid4(), ad_id=stack["ads"][0].id),
            headers=tenant["headers"],
        )
        assert response.status_code == 404

    async def test_unknown_ad_404(self, client, session, tenant):
        import uuid as uuid_mod

        stack, concept = await self._setup(session, tenant)
        response = await client.post(
            BASE + f"/businesses/{tenant['business'].id}/strategy/creative/performance/links",
            json=_link_payload(concept_id=concept.id, ad_id=uuid_mod.uuid4()),
            headers=tenant["headers"],
        )
        assert response.status_code == 404

    async def test_duplicate_mapping_409(self, client, session, tenant):
        stack, concept = await self._setup(session, tenant)
        url = BASE + f"/businesses/{tenant['business'].id}/strategy/creative/performance/links"
        first = await client.post(
            url, json=_link_payload(concept_id=concept.id, ad_id=stack["ads"][0].id),
            headers=tenant["headers"],
        )
        assert first.status_code == 201
        second = await client.post(
            url, json=_link_payload(concept_id=concept.id, ad_id=stack["ads"][0].id),
            headers=tenant["headers"],
        )
        assert second.status_code == 409

    async def test_delete_link_restores_unavailable(self, client, session, tenant):
        stack, concept = await self._setup(session, tenant)
        url = BASE + f"/businesses/{tenant['business'].id}/strategy/creative/performance/links"
        created = await client.post(
            url, json=_link_payload(concept_id=concept.id, ad_id=stack["ads"][0].id),
            headers=tenant["headers"],
        )
        deleted = await client.delete(f"{url}/{created.json()['id']}", headers=tenant["headers"])
        assert deleted.status_code == 204
        report = await client.get(
            REPORT_URL.format(business_id=tenant["business"].id), headers=tenant["headers"]
        )
        assert report.json()["attribution"]["status"] == "unavailable"


# ---------------------------------------------------------------------------
# Tenancy & RBAC
# ---------------------------------------------------------------------------


class TestTenancyAndRbac:
    async def _other_tenant(self, session):
        return await create_tenant(session)

    async def test_cross_tenant_business_read_404(self, client, session, tenant):
        other = await self._other_tenant(session)
        response = await client.get(
            REPORT_URL.format(business_id=tenant["business"].id), headers=other["headers"]
        )
        assert response.status_code == 404

    async def test_cross_tenant_write_404(self, client, session, tenant):
        other = await self._other_tenant(session)
        stack = await _ad_stack(session, tenant["business"])
        concept = await _concept(session, tenant)
        await session.commit()
        response = await client.post(
            BASE + f"/businesses/{other['business'].id}/strategy/creative/performance/links",
            json=_link_payload(concept_id=concept.id, ad_id=stack["ads"][0].id),
            headers=other["headers"],
        )
        assert response.status_code == 404

    async def test_viewer_cannot_create_links(self, client, session, tenant):
        # Build a viewer inside the SAME org.
        viewer = await create_user(session)
        role = await create_role(
            session,
            name="viewer",
            organization_id=tenant["org"].id,
            permissions=sorted(DEFAULT_ROLES["viewer"]),
        )
        await create_membership(session, user=viewer, organization=tenant["org"], role=role)
        await session.commit()
        stack = await _ad_stack(session, tenant["business"])
        concept = await _concept(session, tenant)
        await session.commit()
        response = await client.post(
            BASE + f"/businesses/{tenant['business'].id}/strategy/creative/performance/links",
            json=_link_payload(concept_id=concept.id, ad_id=stack["ads"][0].id),
            headers=await auth_headers(session, viewer, tenant["org"].id),
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


class TestSnapshots:
    def _url(self, tenant):
        return BASE + f"/businesses/{tenant['business'].id}/strategy/creative/performance/snapshots"

    async def test_snapshot_reproducible_and_json_safe(self, client, session, tenant):
        stack = await _seed_performance_data(session, tenant)
        concept = await _concept(session, tenant)
        await session.commit()
        links_url = (
            BASE
            + f"/businesses/{tenant['business'].id}"
            + "/strategy/creative/performance/links"
        )
        await client.post(
            links_url, json=_link_payload(concept_id=concept.id, ad_id=stack["ads"][0].id),
            headers=tenant["headers"],
        )

        first = await client.post(
            self._url(tenant) + "?range_kind=last_7_days", headers=tenant["headers"]
        )
        assert first.status_code == 201
        first_body = first.json()
        assert first_body["created"] is True

        second = await client.post(
            self._url(tenant) + "?range_kind=last_7_days", headers=tenant["headers"]
        )
        second_body = second.json()
        assert second_body["created"] is False
        assert second_body["snapshot_id"] == first_body["snapshot_id"]
        assert second_body["fingerprint"] == first_body["fingerprint"]

        listing = await client.get(self._url(tenant), headers=tenant["headers"])
        assert listing.status_code == 200
        assert len(listing.json()) >= 1

        detail = await client.get(
            f"{self._url(tenant)}/{first_body['snapshot_id']}", headers=tenant["headers"]
        )
        assert detail.status_code == 200
        payload_text = detail.text
        assert "Decimal" not in payload_text

    async def test_snapshot_requires_write(self, client, session, tenant):
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
        response = await client.post(self._url(tenant), headers=viewer_headers)
        assert response.status_code == 403
