"""Creative performance orchestration service (Phase 8C).

Async layer between the canonical metrics view and the pure engine:

- loads REAL ad-grain facts per linked entity (never invents data),
- resolves explicit attribution links authored by users,
- runs the deterministic engine (signals / trend / fatigue /
  classification / readiness),
- assembles provenance chains back to metric sources and Phase 7
  strategy references.

No LLM, no predicted numbers, no autonomous actions, no campaign or
provider mutations. Commerce purchases/revenue stay business-level and
are never distributed across creatives.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError, NotFoundError
from src.db.models import Ad, Business
from src.db.models.creative import (
    CreativeConcept,
    CreativeConceptPortfolio,
    CreativeStrategy,
    CreativeTest,
    CreativeTestVariant,
)
from src.db.models.creative_performance import (
    CreativePerformanceLink,
    CreativePerformanceSnapshot,
)
from src.modules.creative.performance import engine
from src.modules.creative.performance.thresholds import CREATIVE_PERFORMANCE_RULES_VERSION
from src.modules.economics.service import summary_data as economics_summary
from src.modules.metrics.aggregation import Range
from src.modules.metrics.models import F, metric_facts

# Raw fact codes surfaced by the engine (subset of the ad-grain columns).
FACT_CODES = (
    "impressions",
    "reach",
    "clicks",
    "spend",
    "conversions",
    "conversion_value",
)

ENTITY_TYPE_CONCEPT = "creative_concept"
ENTITY_TYPE_VARIANT = "creative_test_variant"
_PROVIDER_KINDS = ("ad", "provider_creative")


def _fact_sums() -> list[Any]:
    return [sa.func.sum(F[code]).label(code) for code in FACT_CODES]


async def _daily_rows_for_ads(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    start: date,
    end: date,
    currency: str,
    ad_ids: list[uuid.UUID],
) -> list[dict[str, Any]]:
    """Daily ad-grain fact rows for specific ads (empty when none)."""
    if not ad_ids:
        return []
    stmt = (
        select(F["date"], *_fact_sums())
        .select_from(metric_facts)
        .where(
            F["business_id"] == business_id,
            F["grain"] == "ad",
            F["date"] >= start,
            F["date"] <= end,
            F["currency"] == currency,
            F["ad_id"].in_(ad_ids),
        )
        .group_by(F["date"])
        .order_by(F["date"])
    )
    return [dict(row._mapping) for row in await session.execute(stmt)]


async def _ad_ids_for_provider_creative(
    session: AsyncSession, business_id: uuid.UUID, provider_creative_id: uuid.UUID
) -> list[uuid.UUID]:
    rows = await session.execute(
        select(Ad.id).where(Ad.business_id == business_id, Ad.creative_id == provider_creative_id)
    )
    return [row[0] for row in rows]


def _totals_from_rows(rows: list[dict[str, Any]]) -> dict[str, Decimal | None]:
    totals: dict[str, Decimal | None] = {}
    for code in FACT_CODES:
        total = Decimal("0")
        seen = False
        for row in rows:
            value = row.get(code)
            if value is None:
                continue
            total += Decimal(value)
            seen = True
        totals[code] = total if seen else None
    return totals


def _days_covered(rows: list[dict[str, Any]], *, start: date, end: date) -> int:
    return len({row["date"] for row in rows if start <= row["date"] <= end})


# ---------------------------------------------------------------------------
# Attribution links (8C.2) — explicit user-authored mapping
# ---------------------------------------------------------------------------

ATTRIBUTION_LINKED = "linked"
ATTRIBUTION_UNAVAILABLE = "unavailable"


async def create_link(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    business_id: uuid.UUID,
    created_by: uuid.UUID,
    label: str | None,
    creative_concept_id: uuid.UUID | None,
    creative_test_variant_id: uuid.UUID | None,
    ad_id: uuid.UUID | None,
    provider_creative_id: uuid.UUID | None,
) -> CreativePerformanceLink:
    """Create an explicit attribution link after validating all references.

    Every reference must exist inside the same tenant/business. The
    database CHECK constraints guarantee exactly one internal target and
    exactly one provider target; duplicate identical mappings raise a
    conflict.
    """
    if (creative_concept_id is None) == (creative_test_variant_id is None):
        raise ConflictError(
            "exactly one of creative_concept_id or creative_test_variant_id is required"
        )
    if (ad_id is None) == (provider_creative_id is None):
        raise ConflictError("exactly one of ad_id or provider_creative_id is required")

    concept: CreativeConcept | None = None
    variant: CreativeTestVariant | None = None
    if creative_concept_id is not None:
        concept = (
            await session.execute(
                select(CreativeConcept).where(
                    CreativeConcept.id == creative_concept_id,
                    CreativeConcept.organization_id == organization_id,
                    CreativeConcept.business_id == business_id,
                )
            )
        ).scalar_one_or_none()
        if concept is None:
            raise NotFoundError("Creative concept not found")
    else:
        variant = (
            await session.execute(
                select(CreativeTestVariant).where(
                    CreativeTestVariant.id == creative_test_variant_id,
                    CreativeTestVariant.organization_id == organization_id,
                    CreativeTestVariant.business_id == business_id,
                )
            )
        ).scalar_one_or_none()
        if variant is None:
            raise NotFoundError("Creative test variant not found")

    if ad_id is not None:
        ad = (
            await session.execute(select(Ad).where(Ad.id == ad_id, Ad.business_id == business_id))
        ).scalar_one_or_none()
        if ad is None:
            raise NotFoundError("Ad not found")
    else:
        assert provider_creative_id is not None
        from src.modules.integrations.models import Creative as ProviderCreative

        creative = (
            await session.execute(
                select(ProviderCreative).where(
                    ProviderCreative.id == provider_creative_id,
                    ProviderCreative.business_id == business_id,
                )
            )
        ).scalar_one_or_none()
        if creative is None:
            raise NotFoundError("Provider creative not found")

    link = CreativePerformanceLink(
        organization_id=organization_id,
        business_id=business_id,
        creative_concept_id=creative_concept_id,
        creative_test_variant_id=creative_test_variant_id,
        ad_id=ad_id,
        provider_creative_id=provider_creative_id,
        label=label,
        status="active",
        created_by=created_by,
    )
    session.add(link)
    try:
        await session.flush()
    except sa.exc.IntegrityError as exc:
        raise ConflictError("identical performance link already exists") from exc
    await session.commit()
    return link


async def list_links(
    session: AsyncSession, *, organization_id: uuid.UUID, business_id: uuid.UUID
) -> list[CreativePerformanceLink]:
    rows = (
        (
            await session.execute(
                select(CreativePerformanceLink)
                .where(
                    CreativePerformanceLink.organization_id == organization_id,
                    CreativePerformanceLink.business_id == business_id,
                )
                .order_by(CreativePerformanceLink.created_at.desc(), CreativePerformanceLink.id)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def get_link(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    business_id: uuid.UUID,
    link_id: uuid.UUID,
) -> CreativePerformanceLink | None:
    return (
        await session.execute(
            select(CreativePerformanceLink).where(
                CreativePerformanceLink.id == link_id,
                CreativePerformanceLink.organization_id == organization_id,
                CreativePerformanceLink.business_id == business_id,
            )
        )
    ).scalar_one_or_none()


async def delete_link(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    business_id: uuid.UUID,
    link_id: uuid.UUID,
) -> None:
    link = await get_link(
        session, organization_id=organization_id, business_id=business_id, link_id=link_id
    )
    if link is None:
        raise NotFoundError("Performance link not found")
    await session.delete(link)
    await session.commit()


# ---------------------------------------------------------------------------
# Entity context + provenance (8C.2)
# ---------------------------------------------------------------------------


async def _concept_context(
    session: AsyncSession, concept: CreativeConcept
) -> dict[str, Any]:
    portfolio_rows = (
        await session.execute(
            select(CreativeConceptPortfolio.portfolio_id).where(
                CreativeConceptPortfolio.creative_concept_id == concept.id
            )
        )
    ).scalars().all()
    strategy = (
        await session.execute(
            select(CreativeStrategy).where(
                CreativeStrategy.creative_intelligence_reference == concept.id
            )
        )
    ).scalars().first()
    return {
        "funnel_stage": concept.funnel_stage,
        "angle": concept.angle,
        "creative_format": concept.creative_format,
        "hook_direction": concept.hook_direction,
        "audience": concept.audience,
        "portfolio_ids": [str(pid) for pid in portfolio_rows],
        "strategy_reference": str(strategy.id) if strategy is not None else None,
        "positioning_reference": (
            str(concept.positioning_reference) if concept.positioning_reference else None
        ),
        "offer_reference": str(concept.offer_reference) if concept.offer_reference else None,
        "messaging_reference": (
            str(concept.messaging_reference) if concept.messaging_reference else None
        ),
        "funnel_reference": str(concept.funnel_reference) if concept.funnel_reference else None,
    }


async def _entity_descriptor(
    session: AsyncSession, link: CreativePerformanceLink
) -> dict[str, Any] | None:
    """Resolve one link into an entity descriptor with context.

    Returns None when the referenced internal target no longer resolves
    (defensive; FK cascades should prevent it).
    """
    test: CreativeTest | None = None
    if link.creative_concept_id is not None:
        concept = await session.get(CreativeConcept, link.creative_concept_id)
        if concept is None:
            return None
        entity_type = ENTITY_TYPE_CONCEPT
        entity_id = concept.id
        context = await _concept_context(session, concept)
    else:
        variant = await session.get(CreativeTestVariant, link.creative_test_variant_id)
        if variant is None:
            return None
        entity_type = ENTITY_TYPE_VARIANT
        entity_id = variant.id
        test = (
            await session.execute(
                select(CreativeTest).where(
                    CreativeTest.test_id == variant.test_id,
                    CreativeTest.business_id == link.business_id,
                )
            )
        ).scalars().first()
        context = {
            "test_id": variant.test_id,
            "variant_value": variant.test_variable_value,
            "test_objective": test.objective if test else None,
            "test_variable": test.test_variable if test else None,
            "success_metric": test.success_metric if test else None,
        }

    if link.ad_id is not None:
        ad = await session.get(Ad, link.ad_id)
        if ad is None:
            return None
        provider = {"kind": "ad", "id": ad.id, "campaign_id": ad.campaign_id}
        ad_ids = [ad.id]
    else:
        ad_ids = await _ad_ids_for_provider_creative(
            session, link.business_id, link.provider_creative_id
        )
        provider = {
            "kind": "provider_creative",
            "id": link.provider_creative_id,
            "campaign_id": None,
        }

    chain: list[dict[str, Any]] = [
        {"step": "entity", "type": entity_type, "id": str(entity_id)},
        {"step": "provider_object", "kind": provider["kind"], "id": str(provider["id"])},
    ]
    if provider.get("campaign_id") is not None:
        chain.append({"step": "campaign", "id": str(provider["campaign_id"])})
    if test is not None:
        chain.append({"step": "creative_test", "id": str(test.id)})
    for step_key, step_name in (
        ("strategy_reference", "creative_strategy"),
        ("funnel_reference", "funnel_strategy"),
        ("messaging_reference", "messaging_strategy"),
        ("positioning_reference", "positioning_strategy"),
        ("offer_reference", "offer_candidate"),
    ):
        reference = context.get(step_key)
        if reference:
            chain.append({"step": step_name, "id": reference})

    return {
        "link_id": link.id,
        "entity": {"type": entity_type, "id": str(entity_id)},
        "context": context,
        "provider": provider,
        "ad_ids": ad_ids,
        "provenance_chain": chain,
        "metric_source": {
            "source_type": "ad_insight",
            "grain": "ad",
            "provider": "meta",
        },
    }


# ---------------------------------------------------------------------------
# Report building
# ---------------------------------------------------------------------------


def engine_thresholds_fatigue_window() -> int:
    from src.modules.creative.performance.thresholds import FATIGUE_WINDOW_DAYS
    from src.modules.creative.performance.thresholds import value as tv

    return int(tv(FATIGUE_WINDOW_DAYS))


async def _entity_performance(
    session: AsyncSession,
    descriptor: dict[str, Any],
    *,
    business: Business,
    range: Range,
    break_even_roas: Decimal | None,
) -> dict[str, Any]:
    currency = business.currency
    fatigue_span = timedelta(days=2 * engine_thresholds_fatigue_window() - 1)
    load_start = min(range.start, range.end - fatigue_span)
    rows = await _daily_rows_for_ads(
        session,
        business.id,
        start=load_start,
        end=range.end,
        currency=currency,
        ad_ids=descriptor["ad_ids"],
    )
    current_rows = [row for row in rows if range.start <= row["date"] <= range.end]
    totals = _totals_from_rows(current_rows)
    days = _days_covered(rows, start=range.start, end=range.end)

    signals = engine.extract_signals(totals)
    signals_map = engine.signals_by_code(signals)
    trend = engine.trend_from_daily(current_rows)
    fatigue = engine.detect_fatigue(range.end, rows)
    ctr_trend = trend.get("metrics", {}).get("ctr", {}).get("direction")
    classification = engine.classify(
        signals_map,
        days_covered=days,
        break_even_roas=break_even_roas,
        fatigue_status=fatigue["status"],
        ctr_trend_direction=ctr_trend,
    )
    readiness = engine.scaling_readiness(
        signals_map,
        days_covered=days,
        fatigue_status=fatigue["status"],
        classification_status=classification["status"],
        break_even_roas=break_even_roas,
    )

    observation = {
        "entity": descriptor["entity"],
        "range": {"kind": range.kind, "start": range.start, "end": range.end},
        "currency": currency,
        "days_covered": days,
        "totals": totals,
        "metric_source": descriptor["metric_source"],
    }

    return {
        "link_id": descriptor["link_id"],
        "entity": descriptor["entity"],
        "attribution": {"status": ATTRIBUTION_LINKED, "reason": None},
        "context": descriptor["context"],
        "observation": observation,
        "signals": signals,
        "trend": trend,
        "fatigue": fatigue,
        "classification": classification,
        "scaling_readiness": readiness,
        "provenance": {
            "metric_source": descriptor["metric_source"],
            "chain": descriptor["provenance_chain"],
        },
    }


def _dimension_of(entity_result: dict[str, Any], dimension: str) -> str | None:
    """Dimension key for one computed entity result (None when absent)."""
    context = entity_result.get("context") or {}
    if dimension == "campaign":
        campaign = None
        for step in entity_result["provenance"]["chain"]:
            if step["step"] == "campaign":
                campaign = step["id"]
        return campaign
    value = context.get(dimension)
    return str(value) if value not in (None, "") else None


COMPARISON_DIMENSIONS = (
    "campaign",
    "funnel_stage",
    "creative_format",
    "angle",
    "hook_direction",
    "audience",
)


async def build_report(
    session: AsyncSession,
    business: Business,
    *,
    range: Range,
) -> dict[str, Any]:
    """Full deterministic report over every actively linked entity."""
    links = [
        link
        for link in await list_links(
            session, organization_id=business.organization_id, business_id=business.id
        )
        if link.status == "active"
    ]
    economics = await economics_summary(session, business)
    break_even_roas = economics.get("break_even_roas")

    descriptors: list[dict[str, Any]] = []
    for link in links:
        descriptor = await _entity_descriptor(session, link)
        if descriptor is not None:
            descriptors.append(descriptor)
    descriptors.sort(key=lambda d: (d["entity"]["type"], d["entity"]["id"]))

    entity_results = [
        await _entity_performance(
            session, descriptor, business=business, range=range, break_even_roas=break_even_roas
        )
        for descriptor in descriptors
    ]

    comparisons: dict[str, Any] = {}
    for dimension in COMPARISON_DIMENSIONS:
        groups: dict[str, list[dict[str, Any]]] = {}
        for result in entity_results:
            key = _dimension_of(result, dimension)
            if key is None:
                continue
            groups.setdefault(key, []).append(result)
        dimension_output: dict[str, Any] = {}
        for key in sorted(groups):
            members = groups[key]
            if len(members) < 2:
                continue
            entries = [
                {"entity": member["entity"], "signals": engine.signals_by_code(member["signals"])}
                for member in members
            ]
            dimension_output[key] = engine.compare_entities(entries, primary_metric="ctr")
        if dimension_output:
            comparisons[dimension] = dimension_output

    attribution_summary = (
        {"status": ATTRIBUTION_LINKED, "linked_entities": len(entity_results)}
        if entity_results
        else {
            "status": ATTRIBUTION_UNAVAILABLE,
            "reason": "no_performance_links_recorded",
            "linked_entities": 0,
        }
    )

    report = {
        "business_id": str(business.id),
        "currency": business.currency,
        "range": {"kind": range.kind, "start": range.start, "end": range.end},
        "rules_versions": {
            "engine": CREATIVE_PERFORMANCE_RULES_VERSION,
            "fatigue": engine.FATIGUE_RULES_VERSION,
            "classification": engine.CLASSIFICATION_RULES_VERSION,
            "readiness": engine.READINESS_RULES_VERSION,
            "comparison": engine.COMPARISON_RULES_VERSION,
        },
        "break_even_roas_available": break_even_roas is not None,
        "attribution": attribution_summary,
        "entities": entity_results,
        "comparisons": comparisons,
    }
    report["fingerprint"] = engine.fingerprint(
        engine.to_jsonable(
            {
                "business_id": report["business_id"],
                "range": report["range"],
                "rules_versions": report["rules_versions"],
                "entities": [e["entity"] for e in report["entities"]],
            }
        )
    )
    return report


async def build_entity_report(
    session: AsyncSession,
    business: Business,
    *,
    range: Range,
    entity_type: str,
    entity_id: uuid.UUID,
) -> dict[str, Any]:
    """Deterministic performance for ONE entity; unavailable when unlinked."""
    if entity_type not in (ENTITY_TYPE_CONCEPT, ENTITY_TYPE_VARIANT):
        raise NotFoundError("Unknown entity type")
    column = (
        CreativePerformanceLink.creative_concept_id
        if entity_type == ENTITY_TYPE_CONCEPT
        else CreativePerformanceLink.creative_test_variant_id
    )
    link = (
        await session.execute(
            select(CreativePerformanceLink).where(
                column == entity_id,
                CreativePerformanceLink.status == "active",
                CreativePerformanceLink.organization_id == business.organization_id,
                CreativePerformanceLink.business_id == business.id,
            )
        )
    ).scalars().first()
    if link is None:
        return {
            "business_id": str(business.id),
            "entity": {"type": entity_type, "id": str(entity_id)},
            "attribution": {
                "status": ATTRIBUTION_UNAVAILABLE,
                "reason": "no_performance_link_recorded",
            },
            "range": {"kind": range.kind, "start": range.start, "end": range.end},
        }
    descriptor = await _entity_descriptor(session, link)
    if descriptor is None:
        raise NotFoundError("Linked entity no longer exists")
    economics = await economics_summary(session, business)
    result = await _entity_performance(
        session,
        descriptor,
        business=business,
        range=range,
        break_even_roas=economics.get("break_even_roas"),
    )
    return {
        "business_id": str(business.id),
        "range": {"kind": range.kind, "start": range.start, "end": range.end},
        "result": result,
    }


# ---------------------------------------------------------------------------
# Snapshots — immutable audit trail of computed reports
# ---------------------------------------------------------------------------


async def persist_snapshot(
    session: AsyncSession,
    business: Business,
    *,
    report: dict[str, Any],
    created_by: uuid.UUID,
) -> tuple[CreativePerformanceSnapshot, bool]:
    """Store a snapshot keyed by fingerprint. Idempotent on recompute.

    Returns (snapshot, created). Recomputing the same inputs returns the
    existing snapshot instead of duplicating it.
    """
    fingerprint = report["fingerprint"]
    existing = (
        await session.execute(
            select(CreativePerformanceSnapshot).where(
                CreativePerformanceSnapshot.business_id == business.id,
                CreativePerformanceSnapshot.fingerprint == fingerprint,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    snapshot = CreativePerformanceSnapshot(
        organization_id=business.organization_id,
        business_id=business.id,
        range_kind=str(report["range"]["kind"]),
        start_date=report["range"]["start"],
        end_date=report["range"]["end"],
        currency=report["currency"],
        entity_scope="all",
        rules_version=str(report["rules_versions"]["engine"]),
        fingerprint=fingerprint,
        payload=engine.to_jsonable(report),
        created_by=created_by,
    )
    session.add(snapshot)
    try:
        await session.flush()
    except sa.exc.IntegrityError as exc:
        raise ConflictError("snapshot fingerprint already exists") from exc
    await session.commit()
    return snapshot, True


async def list_snapshots(
    session: AsyncSession, *, organization_id: uuid.UUID, business_id: uuid.UUID
) -> list[CreativePerformanceSnapshot]:
    rows = (
        (
            await session.execute(
                select(CreativePerformanceSnapshot)
                .where(
                    CreativePerformanceSnapshot.organization_id == organization_id,
                    CreativePerformanceSnapshot.business_id == business_id,
                )
                .order_by(CreativePerformanceSnapshot.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def get_snapshot(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    business_id: uuid.UUID,
    snapshot_id: uuid.UUID,
) -> CreativePerformanceSnapshot | None:
    return (
        await session.execute(
            select(CreativePerformanceSnapshot).where(
                CreativePerformanceSnapshot.id == snapshot_id,
                CreativePerformanceSnapshot.organization_id == organization_id,
                CreativePerformanceSnapshot.business_id == business_id,
            )
        )
    ).scalar_one_or_none()


__all__ = [
    "ATTRIBUTION_LINKED",
    "ATTRIBUTION_UNAVAILABLE",
    "create_link",
    "list_links",
    "get_link",
    "delete_link",
    "build_report",
    "build_entity_report",
    "persist_snapshot",
    "list_snapshots",
    "get_snapshot",
]
