"""Creative test measurement reporting (Phase 8I).

Read-only assembly of canonical outputs into one coherent report per
creative test:

    8H lifecycle events + current status
    8C per-entity observations/signals/fatigue/classification (verbatim)
    8D learning snapshot patterns touching the test's entities (verbatim)

Zero new intelligence logic: no KPI recomputation, no fatigue/classifier
re-derivation, no new thresholds, no scores, no lifecycle mutation.
Missing data is surfaced as unavailable / insufficient_data with reasons.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Business
from src.db.models.creative import CreativeTest
from src.db.models.creative_action import CreativeActionDraft
from src.modules.creative.learning.service import latest_snapshot as learning_latest
from src.modules.creative.performance.engine import to_jsonable
from src.modules.creative.performance.service import build_entity_report
from src.modules.diagnostics.thresholds import (
    SAMPLE_MIN_IMPRESSIONS,
    SAMPLE_MIN_SPEND,
    SCALING_MIN_DAYS,
)
from src.modules.diagnostics.thresholds import (
    value as diagnostics_threshold_value,
)


def _observation_sufficiency(
    *,
    impressions: Decimal | None,
    spend: Decimal | None,
    days_covered: int | None,
) -> tuple[str, bool, str | None]:
    """Apply the EXISTING 8C/8D sample gates - no new threshold registry.

    Returns (status, sufficiently_observed, reason).
    """
    """Apply the EXISTING 8C/8D sample gates - no new threshold registry.

    sufficient  : impressions/spend gate met (identical to the Phase 8D
                  ``sufficiently_observed`` computation) AND observed days
                  meet the same minimum used for classification runway.
    insufficient: gate unmet; reason names the failing requirement.
    """
    minimum_impressions = diagnostics_threshold_value(SAMPLE_MIN_IMPRESSIONS)
    minimum_spend = diagnostics_threshold_value(SAMPLE_MIN_SPEND)
    sufficiently_observed = bool(
        impressions is not None
        and impressions >= minimum_impressions
        and spend is not None
        and spend >= minimum_spend
    )
    if not sufficiently_observed:
        return (
            "insufficient_data",
            False,
            "impressions/spend below diagnostic sample minima",
        )
    minimum_days = int(diagnostics_threshold_value(SCALING_MIN_DAYS))
    if days_covered is None or days_covered < minimum_days:
        return (
            "insufficient_data",
            True,
            f"observed days {days_covered} below required {minimum_days}",
        )
    return "sufficient", True, None


async def _entities_for_test(
    session: AsyncSession,
    *,
    draft_row: CreativeActionDraft,
) -> list[dict[str, Any]]:
    """Supporting entity references stored on the action draft payload."""
    payload = draft_row.payload or {}
    ids = payload.get("supporting_entity_ids") or []
    return [{"id": str(e)} for e in ids]


async def _learning_context(
    session: AsyncSession,
    *,
    business: Business,
    entity_ids: set[str],
) -> dict[str, Any]:
    """Verbatim 8D artifacts whose supporting entities touch this test."""
    snapshot = await learning_latest(
        session, organization_id=business.organization_id, business_id=business.id
    )
    if snapshot is None:
        return {
            "status": "unavailable",
            "reason": "no_learning_snapshot",
            "patterns": [],
            "learnings": [],
        }
    payload = snapshot.payload or {}
    entity_set = {str(e) for e in entity_ids}

    def touches(record: dict[str, Any]) -> bool:
        involved = set(record.get("supporting_entity_ids") or []) | set(
            record.get("contradicting_entity_ids") or []
        )
        return bool(involved & entity_set)

    patterns = [p for p in payload.get("patterns") or [] if touches(p)]
    learnings = [x for x in payload.get("learnings") or [] if touches(x)]
    if not patterns and not learnings:
        return {
            "status": "unavailable",
            "reason": "no_learning_touching_this_test",
            "patterns": [],
            "learnings": [],
        }
    return {
        "status": "available",
        "snapshot_fingerprint": snapshot.fingerprint,
        "rules_version": snapshot.rules_version,
        "patterns": patterns,
        "learnings": learnings,
    }


async def build_test_report(
    session: AsyncSession,
    business: Business,
    *,
    test_external_ref: str,
    range_kind: str = "last_30_days",
) -> dict[str, Any]:
    """Assemble the full measurement report for one creative test."""
    test_row = (
        await session.execute(
            select(CreativeTest).where(
                CreativeTest.test_id == test_external_ref,
                CreativeTest.organization_id == business.organization_id,
                CreativeTest.business_id == business.id,
            )
        )
    ).scalar_one_or_none()
    if test_row is None:
        return {"status": "not_found"}

    draft_row = (
        await session.execute(
            select(CreativeActionDraft).where(
                CreativeActionDraft.business_id == business.id,
                CreativeActionDraft.draft_test_id == test_external_ref,
            )
        )
    ).scalar_one_or_none()

    # Lifecycle history (8H canonical service).
    from src.modules.creative.action import service as action_service

    events = await action_service.lifecycle_events(
        session,
        organization_id=business.organization_id,
        business_id=business.id,
        test_external_ref=test_external_ref,
    )

    entity_refs = await _entities_for_test(session, draft_row=draft_row) if draft_row else []

    entity_ids = [e["id"] for e in entity_refs]

    # Resolve observation window via the canonical metrics resolver so the
    # report uses exactly the windows every other layer uses.
    from src.modules.metrics.service import resolve_range

    resolved = resolve_range(business.timezone, range_kind)

    measurements: list[dict[str, Any]] = []
    statuses: list[str] = []
    days_list: list[int] = []
    for entity_id in sorted(entity_ids):
        result = await build_entity_report(
            session, business, range=resolved, entity_type="creative_concept",
            entity_id=uuid.UUID(entity_id),
        )
        inner = result.get("result")
        if inner is None:
            # No performance link recorded for this entity.
            measurements.append(
                {
                    "entity_id": entity_id,
                    "attribution": result.get("attribution"),
                    "observation_status": "insufficient_data",
                    "days_covered": 0,
                    "reason": "no_performance_link_recorded",
                }
            )
            statuses.append("insufficient_data")
            continue
        core = inner
        signals_map = {s["code"]: s for s in core["signals"]}
        impressions_raw = signals_map.get("impressions", {}).get("value")
        spend_raw = signals_map.get("spend", {}).get("value")
        obs_status, sufficiently_observed, obs_reason = _observation_sufficiency(
            impressions=None if impressions_raw is None else Decimal(str(impressions_raw)),
            spend=None if spend_raw is None else Decimal(str(spend_raw)),
            days_covered=core["observation"]["days_covered"],
        )
        statuses.append(obs_status)
        days_list.append(core["observation"]["days_covered"])
        measurements.append(
            {
                "entity_id": entity_id,
                "attribution": core["attribution"],
                "observation_status": obs_status,
                "observation_reason": obs_reason,
                "days_covered": core["observation"]["days_covered"],
                "range": core["observation"]["range"],
                "signals": core["signals"],
                "trend": core["trend"],
                "fatigue": core["fatigue"],
                "classification": core["classification"],
                "scaling_readiness": core["scaling_readiness"],
                "provenance": core["provenance"],
            }
        )

    if not entity_ids:
        overall_observation = "insufficient_data"
        overall_reason = "no_performance_link_recorded"
    elif all(s == "sufficient" for s in statuses):
        overall_observation = "sufficient"
        overall_reason = None
    else:
        overall_observation = "insufficient_data"
        overall_reason = (
            "one or more linked creatives do not yet satisfy the applicable "
            "diagnostic sample requirements"
        )

    learning_ctx = await _learning_context(
        session, business=business, entity_ids=set(entity_ids)
    )

    report = {
        "rules_versions": {
            "report": "creport-v1",
        },
        "test": {
            "test_id": test_row.test_id,
            "name": test_row.name,
            "objective": test_row.objective,
            "test_variable": test_row.test_variable,
            "status": test_row.status,
            "hypothesis": test_row.hypothesis,
        },
        "lifecycle": {
            "current_status": test_row.status,
            "events": [
                {
                    "previous_status": e.previous_status,
                    "new_status": e.new_status,
                    "activated_by": str(e.activated_by) if e.activated_by else None,
                    "created_at": e.created_at,
                    "source_opportunity_id": e.source_opportunity_id,
                    "source_plan_fingerprint": e.source_plan_fingerprint,
                }
                for e in events
            ],
        },
        "measurement": {
            "observation_status": overall_observation,
            "reason": overall_reason,
            "days_observed_max": max(days_list) if days_list else None,
            "entities": measurements,
        },
        "learning": learning_ctx,
        "completion_note": (
            "Completion is a human decision. The observation status above is "
            "informational only and never transitions lifecycle state."
        ),
    }
    return to_jsonable(report)


__all__ = ["build_test_report"]
