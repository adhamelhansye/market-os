"""Creative learning orchestration service (Phase 8D).

Async layer between Phase 8C performance artifacts and the pure learning
engine:

- consumes linked-entity observations via the Phase 8C service
  (no metric recomputation, no new formulas),
- computes observation freshness from canonical fact dates,
- runs the deterministic OBSERVATION → SIGNAL → PATTERN → LEARNING →
  RECOMMENDATION pipeline,
- persists immutable, fingerprint-idempotent snapshots,
- serves read projections from the latest persisted snapshot.

No LLM, no provider calls, no campaign/budget mutations. Recommendations
are informational only.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError
from src.db.models import Business
from src.db.models.creative_learning import CreativeLearningSnapshot
from src.modules.creative.learning import engine as learning_engine
from src.modules.creative.learning.thresholds import CREATIVE_LEARNING_RULES_VERSION
from src.modules.creative.performance.service import (
    _entity_descriptor,
    _entity_performance,
    list_links,
)
from src.modules.economics.service import summary_data as economics_summary
from src.modules.metrics.aggregation import Range

NO_SNAPSHOT_STATUS = "no_snapshot"


async def _last_fact_date(
    session: AsyncSession,
    *,
    business_id: uuid.UUID,
    currency: str,
    ad_ids: list[uuid.UUID],
    start: date,
    end: date,
) -> date | None:
    """Most recent canonical fact date for the entity's ads in range."""
    if not ad_ids:
        return None
    from src.modules.metrics.models import F, metric_facts

    row = (
        await session.execute(
            select(sa.func.max(F["date"]))
            .select_from(metric_facts)
            .where(
                F["business_id"] == business_id,
                F["grain"] == "ad",
                F["currency"] == currency,
                F["ad_id"].in_(ad_ids),
                F["date"] >= start,
                F["date"] <= end,
            )
        )
    ).scalar_one_or_none()
    return row


# ---------------------------------------------------------------------------
# Report generation (pure pipeline + canonical inputs)
# ---------------------------------------------------------------------------


async def build_learning_report(
    session: AsyncSession,
    business: Business,
    *,
    range: Range,
) -> dict[str, Any]:
    """Full deterministic learning report over every actively linked entity."""
    links = [
        link
        for link in await list_links(
            session, organization_id=business.organization_id, business_id=business.id
        )
        if link.status == "active"
    ]
    economics = await economics_summary(session, business)

    descriptors: list[dict[str, Any]] = []
    for link in links:
        descriptor = await _entity_descriptor(session, link)
        if descriptor is not None:
            descriptors.append(descriptor)
    descriptors.sort(key=lambda d: (d["entity"]["type"], d["entity"]["id"]))

    entries: list[dict[str, Any]] = []
    for descriptor in descriptors:
        result = await _entity_performance(
            session,
            descriptor,
            business=business,
            range=range,
            break_even_roas=economics.get("break_even_roas"),
        )
        last_date = await _last_fact_date(
            session,
            business_id=business.id,
            currency=business.currency,
            ad_ids=descriptor["ad_ids"],
            start=range.start,
            end=range.end,
        )
        freshness_days: int | None = None
        if last_date is not None:
            freshness_days = (range.end - last_date).days
        entries.append(
            {
                "entity": descriptor["entity"],
                "context": descriptor["context"],
                "signals": result["signals"],
                "classification_status": result["classification"]["status"],
                "fatigue_status": result["fatigue"]["status"],
                "days_covered": result["observation"]["days_covered"],
                "freshness_days": freshness_days,
                "provenance_chain": descriptor["provenance_chain"],
            }
        )

    profiles = learning_engine.build_profiles(entries)
    patterns = learning_engine.detect_patterns(profiles)

    from src.modules.creative.service import (
        _VALID_CREATIVE_FORMATS,
        _VALID_HOOK_DIRECTIONS,
    )

    portfolio = learning_engine.build_portfolio_intelligence(profiles)
    coverage = learning_engine.coverage_gaps(
        profiles,
        valid_hooks=sorted(_VALID_HOOK_DIRECTIONS),
        valid_formats=sorted(_VALID_CREATIVE_FORMATS),
    )

    report = learning_engine.build_report(profiles, patterns, portfolio, coverage)
    # Provenance chains per entity travel with their profiles so every
    # learning/recommendation can be traced back through 8C.
    provenance_by_entity = {
        entry["entity"]["id"]: entry["provenance_chain"] for entry in entries
    }
    report["provenance_index"] = [
        {"entity_id": entity_id, "chain": chain}
        for entity_id, chain in sorted(provenance_by_entity.items())
    ]
    report["fingerprint"] = learning_engine.fingerprint(
        learning_engine.to_jsonable_payload(
            {
                "business_id": str(business.id),
                "range": {"kind": range.kind, "start": range.start, "end": range.end},
                "rules_versions": report["rules_versions"],
                "entities": sorted(provenance_by_entity.keys()),
            }
        )
    )
    return report


def empty_report(business: Business, range: Range) -> dict[str, Any]:
    """Explicit empty state when no performance links exist."""
    return {
        "business_id": str(business.id),
        "range": {"kind": range.kind, "start": range.start, "end": range.end},
        "rules_versions": {"engine": CREATIVE_LEARNING_RULES_VERSION},
        "summary": {
            "entities_total": 0,
            "entities_sufficient": 0,
            "patterns_total": 0,
            "patterns_by_status": {},
            "learnings_total": 0,
            "recommendations_total": 0,
            "learning_status": "insufficient_data",
            "reason": "no_performance_links_recorded",
        },
        "profiles": [],
        "patterns": [],
        "learnings": [],
        "conflicting_evidence": [],
        "portfolio_intelligence": {
            "concept_count": 0,
            "angle_concentration": {"risk": False},
            "format_concentration": {"risk": False},
            "hook_distribution": {},
            "role_balance": None,
        },
        "coverage_gaps": [],
        "recommendations": [],
        "provenance_index": [],
        "fingerprint": "",
    }


# ---------------------------------------------------------------------------
# Persistence (immutable snapshots, idempotent by fingerprint)
# ---------------------------------------------------------------------------


async def persist_snapshot(
    session: AsyncSession,
    business: Business,
    *,
    report: dict[str, Any],
    range: Range,
    created_by: uuid.UUID | None,
) -> tuple[CreativeLearningSnapshot, bool]:
    """Store a snapshot keyed by fingerprint. Idempotent on recompute."""
    fingerprint = report["fingerprint"]
    existing = (
        await session.execute(
            select(CreativeLearningSnapshot).where(
                CreativeLearningSnapshot.business_id == business.id,
                CreativeLearningSnapshot.fingerprint == fingerprint,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    snapshot = CreativeLearningSnapshot(
        organization_id=business.organization_id,
        business_id=business.id,
        range_kind=range.kind,
        start_date=range.start,
        end_date=range.end,
        currency=business.currency,
        rules_version=CREATIVE_LEARNING_RULES_VERSION,
        fingerprint=fingerprint,
        payload=learning_engine.to_jsonable_payload(report),
        created_by=created_by,
    )
    session.add(snapshot)
    try:
        await session.flush()
    except sa.exc.IntegrityError as exc:
        raise ConflictError("learning snapshot fingerprint already exists") from exc
    await session.commit()
    return snapshot, True


async def generate(
    session: AsyncSession,
    business: Business,
    *,
    range: Range,
    created_by: uuid.UUID | None,
) -> dict[str, Any]:
    """Recompute and persist the learning report (idempotent)."""
    links_present = any(
        link.status == "active"
        for link in await list_links(
            session, organization_id=business.organization_id, business_id=business.id
        )
    )
    if not links_present:
        report = empty_report(business, range)
        snapshot, created = None, False
    else:
        report = await build_learning_report(session, business, range=range)
        snapshot, created = await persist_snapshot(
            session, business, report=report, range=range, created_by=created_by
        )
    return {
        "report": report,
        "snapshot_id": snapshot.id if snapshot else None,
        "created": created,
    }


# ---------------------------------------------------------------------------
# Read projections - served from the latest persisted snapshot
# ---------------------------------------------------------------------------


async def latest_snapshot(
    session: AsyncSession, *, organization_id: uuid.UUID, business_id: uuid.UUID
) -> CreativeLearningSnapshot | None:
    return (
        await session.execute(
            select(CreativeLearningSnapshot)
            .where(
                CreativeLearningSnapshot.organization_id == organization_id,
                CreativeLearningSnapshot.business_id == business_id,
            )
            .order_by(CreativeLearningSnapshot.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def get_snapshot(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    business_id: uuid.UUID,
    snapshot_id: uuid.UUID,
) -> CreativeLearningSnapshot | None:
    return (
        await session.execute(
            select(CreativeLearningSnapshot).where(
                CreativeLearningSnapshot.id == snapshot_id,
                CreativeLearningSnapshot.organization_id == organization_id,
                CreativeLearningSnapshot.business_id == business_id,
            )
        )
    ).scalar_one_or_none()


async def list_snapshots(
    session: AsyncSession, *, organization_id: uuid.UUID, business_id: uuid.UUID
) -> list[CreativeLearningSnapshot]:
    rows = (
        (
            await session.execute(
                select(CreativeLearningSnapshot)
                .where(
                    CreativeLearningSnapshot.organization_id == organization_id,
                    CreativeLearningSnapshot.business_id == business_id,
                )
                .order_by(CreativeLearningSnapshot.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


def _empty_section(section: str) -> dict[str, Any]:
    return {"status": NO_SNAPSHOT_STATUS, "reason": "generate a learning snapshot first"}


def projection_from_snapshot(
    snapshot: CreativeLearningSnapshot | None, section: str
) -> dict[str, Any]:
    """Extract one read projection; explicit state when nothing persisted."""
    if snapshot is None:
        return _empty_section(section)
    payload = snapshot.payload or {}
    if section == "summary":
        summary = dict(payload.get("summary") or {})
        summary["status"] = "available"
        summary["fingerprint"] = snapshot.fingerprint
        summary["rules_version"] = snapshot.rules_version
        summary["range"] = {
            "kind": snapshot.range_kind,
            "start": snapshot.start_date,
            "end": snapshot.end_date,
        }
        return summary
    items = payload.get(section)
    if items is None:
        return _empty_section(section)
    return {"status": "available", "items": items}


__all__ = [
    "NO_SNAPSHOT_STATUS",
    "build_learning_report",
    "empty_report",
    "generate",
    "persist_snapshot",
    "latest_snapshot",
    "get_snapshot",
    "list_snapshots",
    "projection_from_snapshot",
]
