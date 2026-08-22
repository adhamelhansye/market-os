"""Pure deterministic decision-plan engine (Phase 8F).

Consumes the latest Phase 8E optimization snapshot payload VERBATIM and
assembles a reviewable decision plan. This module is PURE: no database
access, no API calls, no LLM, no timestamps in output.

Hard boundaries:

- 8E opportunity fields are copied unchanged: priority, priority_score,
  evidence_strength, learning_value, gates and status are NEVER
  recomputed. There is no second scoring system here.
- Blocked opportunities are never actionable: they appear only in an
  informational appendix.
- Every item carries review_only=true and
  execution_status="not_executed".
- Review state is NOT part of the immutable payload semantics: items
  carry the default "proposed"; live state is merged at projection time
  by the service from the mutable review table.
- Ordering is deterministic (priority_score desc, then dimension,
  target, type, opportunity_id). No timestamps anywhere.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from src.modules.creative.performance.engine import fingerprint, to_jsonable

DECISION_PLAN_RULES_VERSION = "cdecision-v1"

EXECUTION_STATUS_NOT_EXECUTED = "not_executed"
REVIEW_STATE_PROPOSED = "proposed"
REVIEW_STATE_ACKNOWLEDGED = "acknowledged"
REVIEW_STATE_DISMISSED = "dismissed"
REVIEW_STATE_DEFERRED = "deferred"

ALLOWED_REVIEW_STATES: tuple[str, ...] = (
    REVIEW_STATE_PROPOSED,
    REVIEW_STATE_ACKNOWLEDGED,
    REVIEW_STATE_DISMISSED,
    REVIEW_STATE_DEFERRED,
)

PLAN_STATUS_UNAVAILABLE = "unavailable"
PLAN_STATUS_READY_FOR_REVIEW = "ready_for_review"

# Deterministic review-focus mapping, centralized as named constants.
# Category values come verbatim from Phase 8E opportunities.
REVIEW_FOCUS_EXPANSION = "draft creative test per 8B taxonomy"
REVIEW_FOCUS_FATIGUE = "schedule refresh investigation"
REVIEW_FOCUS_INVESTIGATION = "attach diagnostics review"
REVIEW_FOCUS_ALIGNMENT = "strategy alignment check"
REVIEW_FOCUS_CONCENTRATION = "improve strategic coverage"
REVIEW_FOCUS_COVERAGE = "improve strategic coverage"
REVIEW_FOCUS_DEFAULT = "gather supporting evidence"

REVIEW_FOCUS_BY_CATEGORY: dict[str, str] = {
    "expansion": REVIEW_FOCUS_EXPANSION,
    "fatigue": REVIEW_FOCUS_FATIGUE,
    "investigation": REVIEW_FOCUS_INVESTIGATION,
    "alignment": REVIEW_FOCUS_ALIGNMENT,
    "concentration": REVIEW_FOCUS_CONCENTRATION,
    "coverage": REVIEW_FOCUS_COVERAGE,
}


def suggested_review_focus(category: str | None) -> str:
    """Deterministic focus text for one opportunity category."""
    return REVIEW_FOCUS_BY_CATEGORY.get(category or "", REVIEW_FOCUS_DEFAULT)


def _normalize_item(opportunity: Mapping[str, Any]) -> dict[str, Any]:
    """Copy an 8E opportunity into a plan item - verbatim, no recomputation."""
    return {
        "opportunity_id": str(opportunity["opportunity_id"]),
        "type": str(opportunity.get("type", "")),
        "dimension": str(opportunity.get("dimension", "")),
        "target_reference": str(opportunity.get("target_reference", "")),
        "status": str(opportunity.get("status", "")),
        "evidence_strength": str(opportunity.get("evidence_strength", "")),
        "learning_value": str(opportunity.get("learning_value", "")),
        "priority": str(opportunity.get("priority", "")),
        # Decimal preserved; JSON-safe conversion happens at persistence.
        "priority_score": opportunity.get("priority_score"),
        "rationale": str(opportunity.get("rationale", "")),
        "supporting_entity_ids": sorted(
            str(x) for x in opportunity.get("supporting_entity_ids", [])
        ),
        "contradicting_entity_ids": sorted(
            str(x) for x in opportunity.get("contradicting_entity_ids", [])
        ),
        "data_sufficiency": str(opportunity.get("data_sufficiency", "")),
        "freshness_days": opportunity.get("freshness_days"),
        "provenance": list(opportunity.get("provenance") or []),
        "category": str(opportunity.get("category", "")),
        "review_only": True,
        "execution_status": EXECUTION_STATUS_NOT_EXECUTED,
        "review_state": REVIEW_STATE_PROPOSED,
        "suggested_review_focus": suggested_review_focus(
            opportunity.get("category")
        ),
        "source_rules_version": str(
            opportunity.get("rules_version", "")
        ),
    }


def _blocked_appendix(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Blocked opportunities are informational-only appendix entries."""
    return {
        "type": str(entry.get("type", "")),
        "dimension": str(entry.get("dimension", "")),
        "target_reference": str(entry.get("target_reference", "")),
        "blocked_by_gate": str(entry.get("blocked_by_gate", "")),
        "reason_code": str(entry.get("reason_code", "")),
        "statement": str(entry.get("statement", "")),
        "actionable": False,
    }


def build_plan(
    *,
    optimization_payload: Mapping[str, Any],
    source_optimization_fingerprint: str | None,
) -> dict[str, Any]:
    """Assemble the immutable decision-plan payload from 8E output.

    `optimization_payload` is the persisted Phase 8E snapshot payload.
    """
    raw_opportunities = list(optimization_payload.get("opportunities") or [])
    raw_blocked = list(optimization_payload.get("blocked_opportunities") or [])

    items = [_normalize_item(o) for o in raw_opportunities]
    items.sort(
        key=lambda item: (
            -Decimal(str(item["priority_score"]))
            if item["priority_score"] is not None
            else Decimal("-1"),
            item["dimension"],
            item["target_reference"],
            item["type"],
            item["opportunity_id"],
        )
    )

    blocked_appendix = sorted(
        (_blocked_appendix(b) for b in raw_blocked),
        key=lambda b: (b["blocked_by_gate"], b["type"], b["target_reference"]),
    )

    summary = {
        "total_items": len(items),
        "blocked_count": len(blocked_appendix),
        "by_priority": {
            priority: sum(1 for i in items if i["priority"] == priority)
            for priority in ("high", "medium", "low")
        },
        "note": (
            "decision plan is review-only; acknowledging an item records "
            "human review and executes nothing"
        ),
    }

    plan = {
        "rules_versions": {
            "engine": DECISION_PLAN_RULES_VERSION,
            "source_optimization": str(
                (optimization_payload.get("rules_versions") or {}).get(
                    "engine", ""
                )
            ),
        },
        "plan_status": (
            PLAN_STATUS_READY_FOR_REVIEW if items else PLAN_STATUS_UNAVAILABLE
        ),
        "summary": summary,
        "items": items,
        "blocked_appendix": blocked_appendix,
        "provenance_index": list(
            optimization_payload.get("provenance_index") or []
        ),
        "source_optimization_fingerprint": source_optimization_fingerprint,
        "learning_snapshot_reference": optimization_payload.get(
            "learning_snapshot_reference"
        ),
    }
    normalized_fingerprint_input = {
        "rules_version": DECISION_PLAN_RULES_VERSION,
        "source_optimization_fingerprint": source_optimization_fingerprint,
        "opportunity_ids": sorted(item["opportunity_id"] for item in items),
        "item_signatures": [
            {
                "id": item["opportunity_id"],
                "type": item["type"],
                "priority": item["priority"],
                "score": str(item["priority_score"]),
            }
            for item in sorted(items, key=lambda x: x["opportunity_id"])
        ],
    }
    plan["fingerprint"] = fingerprint(to_jsonable(normalized_fingerprint_input))
    return plan


def empty_plan() -> dict[str, Any]:
    """Explicit unavailable state when no Phase 8E snapshot exists."""
    return {
        "rules_versions": {"engine": DECISION_PLAN_RULES_VERSION},
        "plan_status": PLAN_STATUS_UNAVAILABLE,
        "summary": {
            "total_items": 0,
            "blocked_count": 0,
            "by_priority": {"high": 0, "medium": 0, "low": 0},
            "reason": "no_optimization_snapshot",
            "note": (
                "decision plan is review-only; acknowledging an item records "
                "human review and executes nothing"
            ),
        },
        "items": [],
        "blocked_appendix": [],
        "provenance_index": [],
        "source_optimization_fingerprint": None,
        "learning_snapshot_reference": None,
        "fingerprint": "",
    }


def merge_review_state(
    item: Mapping[str, Any],
    reviews_by_opportunity: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Overlay live human-review state onto an immutable plan item.

    The immutable payload is never modified; this produces a projection.
    Missing reviews keep the default proposed state.
    """
    review = reviews_by_opportunity.get(item["opportunity_id"])
    merged = dict(item)
    if review is None:
        merged["review_state"] = REVIEW_STATE_PROPOSED
        merged["review_note"] = None
        merged["review_source_plan_fingerprint"] = None
        merged["review_updated_at"] = None
    else:
        merged["review_state"] = review["review_state"]
        merged["review_note"] = review.get("note")
        merged["review_source_plan_fingerprint"] = review.get(
            "source_plan_fingerprint"
        )
        merged["review_updated_at"] = review.get("updated_at")
    return merged


def review_progress(
    items: Sequence[Mapping[str, Any]],
    reviews_by_opportunity: Mapping[str, Mapping[str, Any]],
) -> dict[str, int]:
    """Review progress counts derived from persisted review state."""
    states = [
        reviews_by_opportunity.get(
            item["opportunity_id"], {}
        ).get("review_state", REVIEW_STATE_PROPOSED)
        for item in items
    ]
    total = len(items)
    reviewed = sum(1 for s in states if s != REVIEW_STATE_PROPOSED)
    progress: dict[str, int] = {state: 0 for state in ALLOWED_REVIEW_STATES}
    for state in states:
        progress[state] += 1
    progress.update(
        {
            "total_items": total,
            "reviewed_items": reviewed,
            "remaining_items": total - reviewed,
        }
    )
    return progress


__all__ = [
    "DECISION_PLAN_RULES_VERSION",
    "ALLOWED_REVIEW_STATES",
    "REVIEW_STATE_PROPOSED",
    "REVIEW_STATE_ACKNOWLEDGED",
    "REVIEW_STATE_DISMISSED",
    "REVIEW_STATE_DEFERRED",
    "EXECUTION_STATUS_NOT_EXECUTED",
    "PLAN_STATUS_UNAVAILABLE",
    "PLAN_STATUS_READY_FOR_REVIEW",
    "REVIEW_FOCUS_BY_CATEGORY",
    "suggested_review_focus",
    "build_plan",
    "empty_plan",
    "merge_review_state",
    "review_progress",
]
