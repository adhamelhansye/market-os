"""Pure deterministic action-preparation engine (Phase 8G).

Translates ACKNOWLEDGED Phase 8F decision items into Phase 8B creative
test draft specifications. This module is PURE: no database access, no
API calls, no LLM, no timestamps in output.

Hard boundaries:

- The 8B taxonomy is the ONLY taxonomy: hook directions, formats,
  objectives and emotions are validated with the existing Phase 8B
  validators before a draft may be produced.
- Terminology: the value carried by an opportunity is the "supported
  value" / "source opportunity value". Winner language is banned.
- Category map (approved):
    expansion     -> draft
    coverage_gap  -> draft
    fatigue       -> draft
    investigation -> NO draft (explicit skip)
    alignment     -> NO draft (explicit skip)
- Drafts are specifications only. ``status`` is always ``draft`` and
  nothing in this module can change that.
- No timestamps; identical inputs produce identical outputs.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from src.modules.creative.service import (
    _OBJECTIVE_FUNNEL_STAGE_MAP,
    map_objective_to_metric,
)

DECISION_ACTION_RULES_VERSION = "caction-v1"

DRAFT_KIND_EXPANSION = "expansion"
DRAFT_KIND_COVERAGE_GAP = "coverage_gap"
DRAFT_KIND_FATIGUE = "fatigue"

# Categories that translate into drafts vs explicit skips.
DRAFT_CATEGORIES: frozenset[str] = frozenset(
    {DRAFT_KIND_EXPANSION, DRAFT_KIND_COVERAGE_GAP, DRAFT_KIND_FATIGUE}
)
SKIP_CATEGORY_INVESTIGATION = "investigation"
SKIP_CATEGORY_ALIGNMENT = "alignment"
SKIP_CATEGORY_CONCENTRATION = "concentration"

EXECUTION_STATUS_NOT_EXECUTED = "not_executed"

# Creative-test dimension currently varied by each draft kind.
TEST_VARIABLE_BY_KIND = {
    DRAFT_KIND_EXPANSION: "angle",
    DRAFT_KIND_COVERAGE_GAP: "coverage",
    DRAFT_KIND_FATIGUE: "creative_refresh",
}

_INVERSE_OBJECTIVE_BY_STAGE = {}
for _objective, _stage in _OBJECTIVE_FUNNEL_STAGE_MAP.items():
    # First canonical objective per stage wins (deterministic).
    _INVERSE_OBJECTIVE_BY_STAGE.setdefault(_stage, _objective)


def draft_test_id(business_id: str, opportunity_id: str) -> str:
    """Deterministic, collision-safe draft test id.

    ``draft_`` + sha256(business_id : opportunity_id) truncated to 40 hex
    characters (<= String(80)). Arbitrary characters in opportunity ids
    never leak into the identifier.
    """
    digest = hashlib.sha256(f"{business_id}:{opportunity_id}".encode()).hexdigest()
    return f"draft_{digest[:40]}"


def draft_name(opportunity_type: str, target_reference: str) -> str:
    """Deterministic human-readable name (data label, not user copy)."""
    return f"Draft test - {opportunity_type} - {target_reference}"[:200]


def hypothesis_text(kind: str, supported_value: str | None, rationale: str) -> str:
    """Deterministic hypothesis referencing the source rationale.

    Association language only: the draft exists to OBSERVE whether the
    supported pattern holds for this business - never to promise it will.
    """
    value_part = (
        f"supported value '{supported_value}'" if supported_value else "the source context"
    )
    return (
        f"Observe whether {value_part} associated with the source evidence "
        f"also holds here. Source rationale: {rationale}"
    )


def objective_for_stage(funnel_stage: str | None) -> str:
    """Deterministic objective from a known funnel stage (8B map inverse)."""
    if funnel_stage and funnel_stage in _INVERSE_OBJECTIVE_BY_STAGE:
        return _INVERSE_OBJECTIVE_BY_STAGE[funnel_stage]
    return "awareness"


def success_metric_for_objective(objective: str) -> str | None:
    """Reuse the existing 8B objective-to-KPI mapping."""
    return map_objective_to_metric(objective)


def _majority(values: Sequence[str | None]) -> str | None:
    """Deterministic majority of non-empty values; None when no values.

    Ties break lexicographically so input order cannot matter.
    """
    counts: dict[str, int] = {}
    for value in values:
        if value in (None, ""):
            continue
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return None
    best = max(sorted(counts), key=lambda k: counts[k])
    return best


def _majority_with_fallback(
    primary_values: Sequence[str | None],
    scope_contexts: Mapping[str, Mapping[str, Any]] | None,
    key: str,
) -> str | None:
    """Supporting-entity majority first; else majority over ALL in-scope
    concept contexts (real Phase 8A data - deterministic, never invented).
    """
    direct = _majority(primary_values)
    if direct is not None or scope_contexts is None:
        return direct
    return _majority([ctx.get(key) for ctx in scope_contexts.values()])


def translate_opportunity(
    *,
    item: Mapping[str, Any],
    concept_contexts: Mapping[str, Mapping[str, Any]],
    business_id: str,
    source_plan_fingerprint: str,
    scope_contexts: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Translate ONE acknowledged plan item into a draft spec or a skip.

    Returns a dict with either ``draft`` or ``skip`` populated plus shared
    bookkeeping fields.
    """
    opportunity_id = str(item["opportunity_id"])
    category = str(item.get("category", ""))
    supporting = sorted(str(x) for x in item.get("supporting_entity_ids", []))
    contradicting = sorted(str(x) for x in item.get("contradicting_entity_ids", []))
    provenance = [
        {
            "entity_id": entity_id,
            "chain": concept_contexts.get(entity_id, {}).get("provenance_chain"),
        }
        for entity_id in (supporting + contradicting)[:5]
    ]

    base = {
        "source_opportunity_id": opportunity_id,
        "source_plan_fingerprint": source_plan_fingerprint,
        "category": category,
        "supporting_entity_ids": supporting,
        "contradicting_entity_ids": contradicting,
        "provenance": provenance,
        "review_only": True,
        "rules_version": DECISION_ACTION_RULES_VERSION,
    }

    if category in (
        SKIP_CATEGORY_INVESTIGATION,
        SKIP_CATEGORY_ALIGNMENT,
        SKIP_CATEGORY_CONCENTRATION,
    ):
        return {
            **base,
            "skip": {
                "reason_code": f"category_{category}",
                "reason": (
                    "Investigation, strategy-alignment and portfolio-"
                    "concentration opportunities are not translated into "
                    "creative test drafts."
                ),
            },
        }

    if category == DRAFT_KIND_FATIGUE:
        target_entity = str(item.get("target_reference", ""))
        ctx = concept_contexts.get(target_entity) or concept_contexts.get(
            next(iter(supporting), "")
        ) or {}
        kind = DRAFT_KIND_FATIGUE
        test_variable = TEST_VARIABLE_BY_KIND[kind]
        supported_value = ctx.get("angle") or None
        variants = [
            {"variant_id": "v1", "test_variable_value": "current"},
            {"variant_id": "v2", "test_variable_value": "refreshed"},
        ]
    else:
        kind = (
            DRAFT_KIND_COVERAGE_GAP
            if category == DRAFT_KIND_COVERAGE_GAP
            else DRAFT_KIND_EXPANSION
        )
        test_variable = str(item.get("dimension", "")) or TEST_VARIABLE_BY_KIND.get(
            kind, "angle"
        )
        # For coverage gaps the uncovered canonical value IS the spec.
        # For expansion, the supported pattern value is reused verbatim.
        supported_value = str(item.get("target_reference", "")) or None

        contexts = [concept_contexts.get(e, {}) for e in supporting]
        majority_hook = _majority_with_fallback(
            [c.get("hook_direction") for c in contexts], scope_contexts, "hook_direction"
        )
        majority_format = _majority_with_fallback(
            [c.get("creative_format") for c in contexts], scope_contexts, "creative_format"
        )
        majority_stage = _majority_with_fallback(
            [c.get("funnel_stage") for c in contexts], scope_contexts, "funnel_stage"
        )

        if test_variable == "hook_direction":
            hook_direction = supported_value
            creative_format = majority_format
        elif test_variable == "creative_format":
            creative_format = supported_value
            hook_direction = majority_hook
        elif test_variable == "angle":
            hook_direction = majority_hook
            creative_format = majority_format
        else:
            hook_direction = None
            creative_format = None

        variants = [
            {"variant_id": "v1", "test_variable_value": supported_value or ""}
        ]

        primary_id = next((e for e in supporting if e in concept_contexts), None)
        primary_ctx = concept_contexts.get(primary_id, {}) if primary_id else {}
        stage = (
            primary_ctx.get("funnel_stage")
            or majority_stage
            or ("purchase" if False else None)
        )

        spec = {
            "objective": objective_for_stage(stage),
            "funnel_stage": stage,
            "angle": (
                supported_value
                if test_variable == "angle"
                else primary_ctx.get("angle")
            ),
            "hook_direction": hook_direction,
            "creative_format": creative_format,
            "message": primary_ctx.get("message"),
            "offer_reference": primary_ctx.get("offer_reference"),
            "messaging_reference": primary_ctx.get("messaging_reference"),
            "positioning_reference": primary_ctx.get("positioning_reference"),
            "success_metric": success_metric_for_objective(
                objective_for_stage(stage)
            ),
        }
        draft_payload = {
            **base,
            "kind": kind,
            "test_variable": test_variable,
            "supported_value": supported_value,
            "spec": spec,
            "variants": variants,
            "hypothesis": hypothesis_text(
                kind, supported_value, str(item.get("rationale", ""))
            ),
            "execution_status": EXECUTION_STATUS_NOT_EXECUTED,
        }
        missing = [
            field
            for field in ("creative_format",)
            if not spec.get(field)
        ]
        if missing:
            draft_payload["skip"] = {
                "reason_code": "missing_required_taxonomy_field",
                "reason": (
                    f"Cannot assemble a draft without {', '.join(missing)}; "
                    "no source context provides it."
                ),
            }
        return draft_payload

    # Fatigue draft assembly (entity context based).
    stage = ctx.get("funnel_stage")
    draft_payload = {
        **base,
        "kind": kind,
        "test_variable": test_variable,
        "supported_value": supported_value,
        "spec": {
            "objective": objective_for_stage(stage),
            "funnel_stage": stage,
            "angle": ctx.get("angle"),
            "hook_direction": ctx.get("hook_direction"),
            "creative_format": ctx.get("creative_format"),
            "message": ctx.get("message"),
            "offer_reference": ctx.get("offer_reference"),
            "messaging_reference": ctx.get("messaging_reference"),
            "positioning_reference": ctx.get("positioning_reference"),
            "success_metric": success_metric_for_objective(
                objective_for_stage(stage)
            ),
        },
        "variants": variants,
        "hypothesis": hypothesis_text(kind, supported_value, str(item.get("rationale", ""))),
        "execution_status": EXECUTION_STATUS_NOT_EXECUTED,
    }
    if not draft_payload["spec"].get("creative_format"):
        draft_payload["skip"] = {
            "reason_code": "missing_required_taxonomy_field",
            "reason": (
                "Fatigued entity context lacks a creative format; cannot "
                "assemble a draft without inventing one."
            ),
        }
    return draft_payload


def build_action_report(
    *,
    acknowledged_items: Sequence[Mapping[str, Any]],
    concept_contexts: Mapping[str, Mapping[str, Any]],
    business_id: str,
    source_plan_fingerprint: str,
    scope_contexts: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Translate all acknowledged items deterministically.

    Output sections:
      drafts       - translatable acknowledged items (spec payloads)
      skipped      - acknowledged items that cannot become drafts, each
                     with an explicit machine-readable reason
      excluded     - acknowledged items outside 8G scope entirely
                     (investigation / alignment categories)
      untranslated - stale acknowledgments whose opportunity is absent
                     from the latest plan (never fabricated into drafts)
    """
    drafts: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    ordered = sorted(acknowledged_items, key=lambda i: str(i["opportunity_id"]))
    for item in ordered:
        result = translate_opportunity(
            item=item,
            concept_contexts=concept_contexts,
            business_id=business_id,
            source_plan_fingerprint=source_plan_fingerprint,
            scope_contexts=scope_contexts,
        )
        category = result.get("category")
        if "skip" in result:
            record = {k: v for k, v in result.items() if k != "skip"}
            record["skip_reason"] = result["skip"]
            if category in (
                SKIP_CATEGORY_INVESTIGATION,
                SKIP_CATEGORY_ALIGNMENT,
                SKIP_CATEGORY_CONCENTRATION,
            ):
                excluded.append(record)
            else:
                skipped.append(record)
            continue
        result["draft_test_id"] = draft_test_id(
            business_id, result["source_opportunity_id"]
        )
        result["draft_name"] = draft_name(
            str(item.get("type", "")), str(item.get("target_reference", ""))
        )
        drafts.append(result)

    return {
        "rules_versions": {"engine": DECISION_ACTION_RULES_VERSION},
        "summary": {
            "acknowledged_total": len(ordered),
            "drafts_created_spec": len(drafts),
            "skipped_total": len(skipped),
            "excluded_total": len(excluded),
        },
        "drafts": drafts,
        "skipped": skipped,
        "excluded": excluded,
    }


def empty_report() -> dict[str, Any]:
    """Explicit empty state when nothing is acknowledged yet."""
    return {
        "rules_versions": {"engine": DECISION_ACTION_RULES_VERSION},
        "summary": {
            "acknowledged_total": 0,
            "drafts_created_spec": 0,
            "skipped_total": 0,
            "excluded_total": 0,
            "reason": "no_acknowledged_opportunities",
        },
        "drafts": [],
        "skipped": [],
        "excluded": [],
    }


__all__ = [
    "DECISION_ACTION_RULES_VERSION",
    "DRAFT_CATEGORIES",
    "draft_test_id",
    "draft_name",
    "translate_opportunity",
    "build_action_report",
    "empty_report",
]
