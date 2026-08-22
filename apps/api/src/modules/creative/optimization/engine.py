"""Pure deterministic optimization engine (Phase 8E).

Consumes Phase 8D learning artifacts plus strategy-context availability
and produces a versioned, evidence-backed OPTIMIZATION PLAN.

This module is PURE: no database access, no API calls, no LLM, no
timestamps in output (the service stamps persistence time). Identical
inputs always produce identical plans and fingerprints.

Hard boundaries:

- opportunities are review-only; there is no action payload,
- positive expansion types must PASS the gate precedence
  (O1 insufficient_data / O2 stale_data / O3 conflicting_evidence block;
  O7 supported_pattern enables) - blocked candidates are reported in
  `blocked_opportunities` with the blocking gate code, never dropped,
- scoring is a named-Decimal-weight prioritization score ONLY; it is not
  a probability and never predicts outcomes,
- diversity/coverage claims use "reduces concentration risk" /
  "improves strategic coverage" phrasing - never performance promises.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from src.modules.creative.learning.engine import (
    PATTERN_CONFLICTING,
    PATTERN_EMERGING,
    PATTERN_INSUFFICIENT_DATA,
    PATTERN_STABLE,
    PATTERN_STALE,
    PATTERN_SUPPORTED,
    SIGNAL_POSITIVE,
)
from src.modules.creative.optimization.thresholds import (
    GATE_CONFLICTING_EVIDENCE,
    GATE_INSUFFICIENT_DATA,
    GATE_STALE_DATA,
    GATE_SUPPORTED_PATTERN,
    OPTIMIZATION_RULES_VERSION,
    PENALTY_CONTRADICTION,
    PRIORITY_HIGH_MIN_SCORE,
    PRIORITY_MEDIUM_MIN_SCORE,
    WEIGHT_COVERAGE_VALUE,
    WEIGHT_DATA_SUFFICIENCY,
    WEIGHT_DIVERSITY_VALUE,
    WEIGHT_EVIDENCE_MODERATE,
    WEIGHT_EVIDENCE_STRONG,
    WEIGHT_EVIDENCE_WEAK,
    WEIGHT_FATIGUE_RELEVANCE,
    WEIGHT_FRESHNESS,
    WEIGHT_FUNNEL_RELEVANCE,
    WEIGHT_LEARNING_VALUE_HIGH,
    WEIGHT_LEARNING_VALUE_MEDIUM,
    WEIGHT_STRATEGIC_ALIGNMENT,
    weight,
)

_ZERO = Decimal("0")

CANONICAL_FUNNEL_STAGES: tuple[str, ...] = (
    "awareness",
    "interest",
    "consideration",
    "purchase",
    "retention",
)

# Bounded opportunity taxonomy.
OPT_EXPAND_SUPPORTED_ANGLE = "expand_supported_angle"
OPT_TEST_NEW_ANGLE = "test_new_angle"
OPT_TEST_NEW_HOOK = "test_new_hook"
OPT_TEST_NEW_FORMAT = "test_new_format"
OPT_REFRESH_FATIGUED = "refresh_fatigued_creative"
OPT_REDUCE_ANGLE_CONCENTRATION = "reduce_angle_concentration"
OPT_REDUCE_FORMAT_CONCENTRATION = "reduce_format_concentration"
OPT_IMPROVE_FUNNEL_COVERAGE = "improve_funnel_coverage"
OPT_IMPROVE_PROOF_COVERAGE = "improve_proof_coverage"
OPT_IMPROVE_OBJECTION_COVERAGE = "improve_objection_coverage"
OPT_INVESTIGATE_UNDERPERFORMANCE = "investigate_underperformance"
OPT_INVESTIGATE_CONFLICTING = "investigate_conflicting_evidence"
OPT_GATHER_MORE_EVIDENCE = "gather_more_evidence"
OPT_VALIDATE_OFFER_ALIGNMENT = "validate_offer_alignment"
OPT_VALIDATE_MESSAGE_ALIGNMENT = "validate_message_alignment"

# Opportunity categories drive gate treatment.
CATEGORY_EXPANSION = "expansion"      # needs O7 pass + O1/O2/O3 not blocking
CATEGORY_COVERAGE = "coverage"        # O6
CATEGORY_CONCENTRATION = "concentration"  # O5
CATEGORY_FATIGUE = "fatigue"          # O4
CATEGORY_INVESTIGATION = "investigation"  # always allowed, status-driven
CATEGORY_ALIGNMENT = "alignment"      # O8

OPPORTUNITY_CATEGORIES: dict[str, str] = {
    OPT_EXPAND_SUPPORTED_ANGLE: CATEGORY_EXPANSION,
    OPT_TEST_NEW_ANGLE: CATEGORY_EXPANSION,
    OPT_TEST_NEW_HOOK: CATEGORY_EXPANSION,
    OPT_TEST_NEW_FORMAT: CATEGORY_EXPANSION,
    OPT_REFRESH_FATIGUED: CATEGORY_FATIGUE,
    OPT_REDUCE_ANGLE_CONCENTRATION: CATEGORY_CONCENTRATION,
    OPT_REDUCE_FORMAT_CONCENTRATION: CATEGORY_CONCENTRATION,
    OPT_IMPROVE_FUNNEL_COVERAGE: CATEGORY_COVERAGE,
    OPT_IMPROVE_PROOF_COVERAGE: CATEGORY_COVERAGE,
    OPT_IMPROVE_OBJECTION_COVERAGE: CATEGORY_COVERAGE,
    OPT_INVESTIGATE_UNDERPERFORMANCE: CATEGORY_INVESTIGATION,
    OPT_INVESTIGATE_CONFLICTING: CATEGORY_INVESTIGATION,
    OPT_GATHER_MORE_EVIDENCE: CATEGORY_INVESTIGATION,
    OPT_VALIDATE_OFFER_ALIGNMENT: CATEGORY_ALIGNMENT,
    OPT_VALIDATE_MESSAGE_ALIGNMENT: CATEGORY_ALIGNMENT,
}

PRIORITY_HIGH = "high"
PRIORITY_MEDIUM = "medium"
PRIORITY_LOW = "low"

STRENGTH_STRONG = "strong"
STRENGTH_MODERATE = "moderate"
STRENGTH_WEAK = "weak"
STRENGTH_INSUFFICIENT = "insufficient"

LEARNING_VALUE_HIGH = "high"
LEARNING_VALUE_MEDIUM = "medium"
LEARNING_VALUE_LOW = "low"

DATA_SUFFICIENT = "sufficient"
DATA_INSUFFICIENT = "insufficient"
DATA_UNAVAILABLE = "unavailable"
DATA_STALE = "stale"

PLAN_UNAVAILABLE = "unavailable"
PLAN_INSUFFICIENT_DATA = "insufficient_data"
PLAN_INVESTIGATE = "investigate"
PLAN_TEST_READY = "test_ready"
PLAN_REVIEW_READY = "review_ready"

# Strategy-context reference keys on concept descriptors (Phase 7 chain).
_STRATEGY_REF_KEYS: tuple[str, ...] = (
    "positioning_reference",
    "offer_reference",
    "messaging_reference",
    "funnel_reference",
)

_EVIDENCE_WEIGHT_BY_STRENGTH = {
    STRENGTH_STRONG: WEIGHT_EVIDENCE_STRONG,
    STRENGTH_MODERATE: WEIGHT_EVIDENCE_MODERATE,
    STRENGTH_WEAK: WEIGHT_EVIDENCE_WEAK,
    STRENGTH_INSUFFICIENT: None,
}


def _learning_value_for(
    category: str, pattern_status: str | None, is_conflict_resolution: bool
) -> str:
    """Strategic information value - NOT a performance prediction."""
    if category == CATEGORY_INVESTIGATION:
        return LEARNING_VALUE_HIGH if is_conflict_resolution else LEARNING_VALUE_MEDIUM
    if category == CATEGORY_COVERAGE:
        return LEARNING_VALUE_MEDIUM
    if category == CATEGORY_EXPANSION:
        if pattern_status == PATTERN_EMERGING:
            return LEARNING_VALUE_MEDIUM
        return LEARNING_VALUE_LOW if pattern_status == PATTERN_STALE else LEARNING_VALUE_LOW
    return LEARNING_VALUE_LOW


def _score_opportunity(
    *,
    strength: str | None,
    data_sufficiency: str,
    freshness_days: int | None,
    has_strategy_alignment: bool,
    has_funnel_stage: bool,
    learning_value: str,
    fills_coverage_gap: bool,
    reduces_concentration: bool,
    fatigue_relevant: bool,
    contradicting_count: int,
) -> dict[str, Any]:
    """Named-Decimal-weight prioritization score. NOT a probability."""
    factors: list[dict[str, Any]] = []
    score = _ZERO

    def _apply(code: str, enabled: bool) -> None:
        nonlocal score
        if not enabled:
            return
        w = weight(code)
        score += w
        factors.append({"factor": code, "weight": w})

    _apply(WEIGHT_EVIDENCE_STRONG, strength == STRENGTH_STRONG)
    _apply(WEIGHT_EVIDENCE_MODERATE, strength == STRENGTH_MODERATE)
    _apply(WEIGHT_EVIDENCE_WEAK, strength == STRENGTH_WEAK)
    _apply(WEIGHT_DATA_SUFFICIENCY, data_sufficiency == DATA_SUFFICIENT)
    _apply(WEIGHT_FRESHNESS, freshness_days is not None and freshness_days <= int(_stale_days()))
    _apply(WEIGHT_STRATEGIC_ALIGNMENT, has_strategy_alignment)
    _apply(WEIGHT_FUNNEL_RELEVANCE, has_funnel_stage)
    _apply(
        WEIGHT_LEARNING_VALUE_HIGH,
        learning_value == LEARNING_VALUE_HIGH,
    )
    _apply(
        WEIGHT_LEARNING_VALUE_MEDIUM,
        learning_value == LEARNING_VALUE_MEDIUM,
    )
    _apply(WEIGHT_COVERAGE_VALUE, fills_coverage_gap)
    _apply(WEIGHT_DIVERSITY_VALUE, reduces_concentration)
    _apply(WEIGHT_FATIGUE_RELEVANCE, fatigue_relevant)

    # Contradiction penalty: the registered value is negative by design,
    # applied once per contradicting entity (bounded at four).
    for _index in range(max(0, min(contradicting_count, 4))):
        _apply(PENALTY_CONTRADICTION, True)

    if score >= weight(PRIORITY_HIGH_MIN_SCORE):
        priority = PRIORITY_HIGH
    elif score >= weight(PRIORITY_MEDIUM_MIN_SCORE):
        priority = PRIORITY_MEDIUM
    else:
        priority = PRIORITY_LOW

    return {
        "priority_score": score,
        "priority": priority,
        "factors": factors,
        "note": (
            "deterministic prioritization score; not a probability of "
            "success and not an outcome prediction"
        ),
    }


def _stale_days() -> Decimal:
    from src.modules.creative.learning.thresholds import LEARNING_STALE_DAYS
    from src.modules.creative.optimization.thresholds import value as threshold_value

    return threshold_value(LEARNING_STALE_DAYS)


def _data_sufficiency_of(pattern: Mapping[str, Any] | None, fresh: int | None) -> str:
    if pattern is None:
        return DATA_UNAVAILABLE
    if pattern["status"] == PATTERN_INSUFFICIENT_DATA:
        return DATA_INSUFFICIENT
    if fresh is not None and fresh > int(_stale_days()):
        return DATA_STALE
    return DATA_SUFFICIENT


def make_opportunity_id(opportunity_type: str, dimension: str, ref: str) -> str:
    """Stable, deterministic opportunity id (no randomness)."""
    return f"{opportunity_type}:{dimension}:{ref}"


# ---------------------------------------------------------------------------
# Opportunity construction from Phase 8D artifacts
# ---------------------------------------------------------------------------


def _base_opportunity(
    *,
    opportunity_type: str,
    dimension: str,
    target_reference: str,
    status: str,
    strength: str | None,
    data_sufficiency: str,
    freshness_days: int | None,
    supporting_entity_ids: Sequence[str],
    contradicting_entity_ids: Sequence[str],
    rationale: str,
    provenance_refs: list[dict[str, Any]],
    has_strategy_alignment: bool = False,
    has_funnel_stage: bool = False,
    fills_coverage_gap: bool = False,
    reduces_concentration: bool = False,
    fatigue_relevant: bool = False,
    is_conflict_resolution: bool = False,
) -> dict[str, Any]:
    category = OPPORTUNITY_CATEGORIES[opportunity_type]
    pattern_status = (
        PATTERN_STABLE
        if status == "supported_pattern"
        else PATTERN_EMERGING
        if status == "emerging"
        else PATTERN_STALE
        if status == "stale_data"
        else PATTERN_CONFLICTING
        if status == "conflicting_evidence"
        else None
    )
    learning_value = _learning_value_for(
        category, pattern_status, is_conflict_resolution
    )
    scored = _score_opportunity(
        strength=strength,
        data_sufficiency=data_sufficiency,
        freshness_days=freshness_days,
        has_strategy_alignment=has_strategy_alignment,
        has_funnel_stage=has_funnel_stage,
        learning_value=learning_value,
        fills_coverage_gap=fills_coverage_gap,
        reduces_concentration=reduces_concentration,
        fatigue_relevant=fatigue_relevant,
        contradicting_count=len(contradicting_entity_ids),
    )
    return {
        "opportunity_id": make_opportunity_id(opportunity_type, dimension, target_reference),
        "type": opportunity_type,
        "dimension": dimension,
        "target_reference": target_reference,
        "status": status,
        "evidence_strength": strength or STRENGTH_INSUFFICIENT,
        "learning_value": learning_value,
        "priority_score": scored["priority_score"],
        "priority": scored["priority"],
        "scoring_factors": scored["factors"],
        "score_note": scored["note"],
        "rationale": rationale,
        "supporting_entity_ids": sorted(supporting_entity_ids),
        "contradicting_entity_ids": sorted(contradicting_entity_ids),
        "evidence_count": len(supporting_entity_ids) + len(contradicting_entity_ids),
        "freshness_days": freshness_days,
        "data_sufficiency": data_sufficiency,
        "category": category,
        "review_only": True,
        "provenance": provenance_refs,
        "rules_version": OPTIMIZATION_RULES_VERSION,
    }


def _gate_check_expansion(pattern: Mapping[str, Any]) -> dict[str, Any]:
    """O1 > O2 > O3 block; O7 enables. Returns gate evaluation record."""
    blocking: str | None = None
    if pattern["status"] == PATTERN_INSUFFICIENT_DATA:
        blocking = GATE_INSUFFICIENT_DATA
    elif pattern["status"] == PATTERN_STALE:
        blocking = GATE_STALE_DATA
    elif pattern["status"] == PATTERN_CONFLICTING:
        blocking = GATE_CONFLICTING_EVIDENCE
    passed = blocking is None
    return {
        "gate_supported_pattern": GATE_SUPPORTED_PATTERN,
        "passed": passed,
        "blocking_gate": blocking,
        "evaluated_precedence": [
            GATE_INSUFFICIENT_DATA,
            GATE_STALE_DATA,
            GATE_CONFLICTING_EVIDENCE,
            GATE_SUPPORTED_PATTERN,
        ],
    }


def build_opportunities(
    *,
    patterns: Sequence[Mapping[str, Any]],
    portfolio_intelligence: Mapping[str, Any],
    coverage_gaps: Sequence[Mapping[str, Any]],
    profiles: Sequence[Mapping[str, Any]],
    strategy_context_by_entity: Mapping[str, Mapping[str, Any]],
    funnel_stages_observed: set[str] | None = None,
    proof_coverage_present: bool = True,
    objection_coverage_present: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Deterministic opportunities + blocked candidates + evidence gaps.

    Positive expansion types require the O1/O2/O3-precedence gate check to
    pass (O7 supported_pattern). Everything that fails lands in
    `blocked` with its blocking gate - never silently dropped, never
    silently positive.
    """
    opportunities: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    evidence_gaps: list[dict[str, Any]] = []

    def _strategy_flags(entity_ids: Sequence[str]) -> tuple[bool, bool, list[dict[str, Any]]]:
        aligned = False
        funnel_known = False
        missing_refs: list[dict[str, Any]] = []
        for entity_id in entity_ids:
            ctx = strategy_context_by_entity.get(entity_id) or {}
            present = [key for key in _STRATEGY_REF_KEYS if ctx.get(key)]
            if present:
                aligned = True
            else:
                missing_refs.append(
                    {"entity_id": entity_id, "missing": list(_STRATEGY_REF_KEYS)}
                )
            if ctx.get("funnel_stage") in CANONICAL_FUNNEL_STAGES:
                funnel_known = True
        return aligned, funnel_known, missing_refs

    def _provenance_for(entity_ids: Sequence[str]) -> list[dict[str, Any]]:
        refs: list[dict[str, Any]] = []
        for entity_id in entity_ids:
            chain = strategy_context_by_entity.get(entity_id, {}).get("provenance_chain")
            refs.append({"entity_id": entity_id, "chain": chain})
        return refs

    # --- Expansion / evidence opportunities from patterns ---------------
    for pattern in patterns:
        if pattern["dimension"] != "angle":
            continue
        supporting = list(pattern["supporting_entity_ids"])
        contradicting = list(pattern["contradicting_entity_ids"])
        aligned, funnel_known, missing = _strategy_flags(
            supporting + contradicting
        )
        evidence_gaps.extend(
            {"kind": "missing_strategy_context", **m} for m in missing[:2]
        )
        prov = _provenance_for(sorted(set(supporting + contradicting))[:3])

        # Gate evaluation runs for EVERY angle pattern so blocking gates
        # are recorded explicitly (O1/O2/O3 block, O7 enables).
        gate = _gate_check_expansion(pattern)
        if pattern["dominant_direction"] == SIGNAL_POSITIVE:
            if gate["passed"]:
                opportunities.append(
                    _base_opportunity(
                        opportunity_type=OPT_EXPAND_SUPPORTED_ANGLE,
                        dimension="angle",
                        target_reference=str(pattern["value"]),
                        status="supported_pattern",
                        strength=pattern["evidence_strength"],
                        data_sufficiency=DATA_SUFFICIENT,
                        freshness_days=pattern["max_freshness_days"],
                        supporting_entity_ids=supporting,
                        contradicting_entity_ids=contradicting,
                        rationale=(
                            f"Angle '{pattern['value']}' is associated with stronger "
                            f"observed CTR across {pattern['observed_entities']} "
                            "sufficiently observed creatives; expansion is an "
                            "evidence-supported review option."
                        ),
                        provenance_refs=prov,
                        has_strategy_alignment=aligned,
                        has_funnel_stage=funnel_known,
                        is_conflict_resolution=False,
                    )
                )
            else:
                blocked.append(
                    {
                        "type": OPT_EXPAND_SUPPORTED_ANGLE,
                        "dimension": "angle",
                        "target_reference": str(pattern["value"]),
                        "blocked_by_gate": gate["blocking_gate"],
                        "reason_code": "expansion_blocked",
                        "statement": (
                            "Positive association exists but a blocking gate "
                            f"({gate['blocking_gate']}) prevents an expansion "
                            "recommendation; resolve the gate before reconsidering."
                        ),
                    }
                )
        if pattern["status"] == PATTERN_CONFLICTING:
            opportunities.append(
                _base_opportunity(
                    opportunity_type=OPT_INVESTIGATE_CONFLICTING,
                    dimension="angle",
                    target_reference=str(pattern["value"]),
                    status="conflicting_evidence",
                    strength=pattern["evidence_strength"],
                    data_sufficiency=DATA_INSUFFICIENT,
                    freshness_days=pattern["max_freshness_days"],
                    supporting_entity_ids=supporting,
                    contradicting_entity_ids=contradicting,
                    rationale=(
                        "Contradicting observations for this angle; resolution "
                        "requires additional sufficiently observed creatives."
                    ),
                    provenance_refs=prov,
                    is_conflict_resolution=True,
                )
            )
        elif pattern["status"] in (PATTERN_INSUFFICIENT_DATA, PATTERN_EMERGING):
            opportunities.append(
                _base_opportunity(
                    opportunity_type=OPT_GATHER_MORE_EVIDENCE,
                    dimension="angle",
                    target_reference=str(pattern["value"]),
                    status=(
                        "insufficient_data"
                        if pattern["status"] == PATTERN_INSUFFICIENT_DATA
                        else "emerging"
                    ),
                    strength=pattern["evidence_strength"],
                    data_sufficiency=DATA_INSUFFICIENT
                    if pattern["status"] == PATTERN_INSUFFICIENT_DATA
                    else DATA_SUFFICIENT,
                    freshness_days=pattern["max_freshness_days"],
                    supporting_entity_ids=[],
                    contradicting_entity_ids=[],
                    rationale=(
                        "Observation volume does not yet support any directional "
                        "conclusion; gather more evidence instead of changing "
                        "direction."
                    ),
                    provenance_refs=prov,
                )
            )

    # Non-angle supported patterns feed explore-style testing.
    for pattern in patterns:
        if pattern["dimension"] == "angle":
            continue
        if pattern["dominant_direction"] != SIGNAL_POSITIVE:
            continue
        if pattern["status"] not in (PATTERN_STABLE, PATTERN_SUPPORTED):
            continue
        supporting = list(pattern["supporting_entity_ids"])
        aligned, funnel_known, _missing = _strategy_flags(supporting)
        opp_type = (
            OPT_TEST_NEW_HOOK
            if pattern["dimension"] == "hook_direction"
            else OPT_TEST_NEW_FORMAT
            if pattern["dimension"] == "creative_format"
            else OPT_GATHER_MORE_EVIDENCE
        )
        if opp_type == OPT_GATHER_MORE_EVIDENCE:
            continue
        opportunities.append(
            _base_opportunity(
                opportunity_type=opp_type,
                dimension=pattern["dimension"],
                target_reference=str(pattern["value"]),
                status="supported_pattern",
                strength=pattern["evidence_strength"],
                data_sufficiency=DATA_SUFFICIENT,
                freshness_days=pattern["max_freshness_days"],
                supporting_entity_ids=supporting,
                contradicting_entity_ids=list(pattern["contradicting_entity_ids"]),
                rationale=(
                    f"{pattern['dimension'].replace('_', ' ')} "
                    f"'{pattern['value']}' is associated with stronger observed "
                    "CTR; testing more of this value is an evidence-backed "
                    "review option."
                ),
                provenance_refs=_provenance_for(supporting[:3]),
                has_strategy_alignment=aligned,
                has_funnel_stage=funnel_known,
            )
        )

    # --- Fatigue opportunities (O4) --------------------------------------
    for profile in profiles:
        fatigue = profile.get("fatigue_status")
        if fatigue != "fatigue_signal":
            continue
        entity_id = profile["entity"]["id"]
        opportunities.append(
            _base_opportunity(
                opportunity_type=OPT_REFRESH_FATIGUED,
                dimension="entity",
                target_reference=entity_id,
                status="fatigue_signal",
                strength=STRENGTH_MODERATE,
                data_sufficiency=DATA_SUFFICIENT
                if profile["sufficiently_observed"]
                else DATA_INSUFFICIENT,
                freshness_days=profile.get("freshness_days"),
                supporting_entity_ids=[entity_id],
                contradicting_entity_ids=[],
                rationale=(
                    "Phase 8C observed a fatigue signal on this creative; "
                    "a refresh deserves review. No automatic action is taken."
                ),
                provenance_refs=[
                    {
                        "entity_id": entity_id,
                        "chain": strategy_context_by_entity.get(entity_id, {}).get(
                            "provenance_chain"
                        ),
                    }
                ],
                fatigue_relevant=True,
            )
        )

    # --- Underperformance investigation ----------------------------------
    for profile in profiles:
        if profile.get("classification_status") != "underperforming":
            continue
        if not profile["sufficiently_observed"]:
            continue
        entity_id = profile["entity"]["id"]
        opportunities.append(
            _base_opportunity(
                opportunity_type=OPT_INVESTIGATE_UNDERPERFORMANCE,
                dimension="entity",
                target_reference=entity_id,
                status="investigate",
                strength=STRENGTH_WEAK,
                data_sufficiency=DATA_SUFFICIENT,
                freshness_days=profile.get("freshness_days"),
                supporting_entity_ids=[entity_id],
                contradicting_entity_ids=[],
                rationale=(
                    "Classification underperforming with sufficient volume; "
                    "investigate diagnostics before considering changes."
                ),
                provenance_refs=[
                    {
                        "entity_id": entity_id,
                        "chain": strategy_context_by_entity.get(entity_id, {}).get(
                            "provenance_chain"
                        ),
                    }
                ],
            )
        )

    # --- Concentration opportunities (O5) ---------------------------------
    angle_conc = portfolio_intelligence.get("angle_concentration") or {}
    if angle_conc.get("risk"):
        opportunities.append(
            _base_opportunity(
                opportunity_type=OPT_REDUCE_ANGLE_CONCENTRATION,
                dimension="portfolio",
                target_reference=str(angle_conc.get("top_value", "")),
                status="concentration_risk",
                strength=STRENGTH_MODERATE,
                data_sufficiency=DATA_SUFFICIENT,
                freshness_days=None,
                supporting_entity_ids=[],
                contradicting_entity_ids=[],
                rationale=(
                    f"Most concepts concentrate on angle "
                    f"'{angle_conc.get('top_value')}'; diversification reduces "
                    "concentration risk and improves strategic coverage."
                ),
                provenance_refs=[{"kind": "portfolio_intelligence"}],
                reduces_concentration=True,
            )
        )
    format_conc = portfolio_intelligence.get("format_concentration") or {}
    if format_conc.get("risk"):
        opportunities.append(
            _base_opportunity(
                opportunity_type=OPT_REDUCE_FORMAT_CONCENTRATION,
                dimension="portfolio",
                target_reference=str(format_conc.get("top_value", "")),
                status="concentration_risk",
                strength=STRENGTH_MODERATE,
                data_sufficiency=DATA_SUFFICIENT,
                freshness_days=None,
                supporting_entity_ids=[],
                contradicting_entity_ids=[],
                rationale=(
                    f"Format concentration on '{format_conc.get('top_value')}'; "
                    "diversification reduces concentration risk."
                ),
                provenance_refs=[{"kind": "portfolio_intelligence"}],
                reduces_concentration=True,
            )
        )

    # --- Coverage opportunities (O6) ---------------------------------------
    observed_stages = (
        funnel_stages_observed
        if funnel_stages_observed is not None
        else {
            str((p.get("context") or {}).get("funnel_stage"))
            for p in profiles
            if (p.get("context") or {}).get("funnel_stage")
        }
    )
    for stage in CANONICAL_FUNNEL_STAGES:
        if stage not in observed_stages:
            opportunities.append(
                _base_opportunity(
                    opportunity_type=OPT_IMPROVE_FUNNEL_COVERAGE,
                    dimension="funnel_stage",
                    target_reference=stage,
                    status="coverage_gap",
                    strength=STRENGTH_WEAK,
                    data_sufficiency=DATA_UNAVAILABLE,
                    freshness_days=None,
                    supporting_entity_ids=[],
                    contradicting_entity_ids=[],
                    rationale=(
                        f"No concepts observe funnel stage '{stage}'; coverage "
                        "gap limits what the learning layer can see."
                    ),
                    provenance_refs=[{"kind": "coverage"}],
                    fills_coverage_gap=True,
                )
            )
    for gap in coverage_gaps:
        gap_dimension = gap.get("dimension")
        if gap_dimension == "hook_direction":
            opp_type = OPT_TEST_NEW_HOOK
        elif gap_dimension == "creative_format":
            opp_type = OPT_TEST_NEW_FORMAT
        elif gap_dimension == "angle":
            opp_type = OPT_TEST_NEW_ANGLE
        else:
            continue
        opportunities.append(
            _base_opportunity(
                opportunity_type=opp_type,
                dimension=gap_dimension,
                target_reference=str(gap.get("value")),
                status="coverage_gap",
                strength=STRENGTH_WEAK,
                data_sufficiency=DATA_UNAVAILABLE,
                freshness_days=None,
                supporting_entity_ids=[],
                contradicting_entity_ids=[],
                rationale=(
                    f"No concept covers this canonical {gap_dimension.replace('_', ' ')} "
                    "value; closing the gap improves strategic coverage."
                ),
                provenance_refs=[{"kind": "coverage", "gap": dict(gap)}],
                fills_coverage_gap=True,
            )
        )
    if not proof_coverage_present:
        opportunities.append(
            _base_opportunity(
                opportunity_type=OPT_IMPROVE_PROOF_COVERAGE,
                dimension="proof",
                target_reference="reason_to_believe",
                status="coverage_gap",
                strength=STRENGTH_WEAK,
                data_sufficiency=DATA_UNAVAILABLE,
                freshness_days=None,
                supporting_entity_ids=[],
                contradicting_entity_ids=[],
                rationale=(
                    "Concepts lack reason-to-believe proof direction; adding "
                    "proof improves strategic coverage."
                ),
                provenance_refs=[{"kind": "coverage"}],
                fills_coverage_gap=True,
            )
        )
    if not objection_coverage_present:
        opportunities.append(
            _base_opportunity(
                opportunity_type=OPT_IMPROVE_OBJECTION_COVERAGE,
                dimension="objection",
                target_reference="objection",
                status="coverage_gap",
                strength=STRENGTH_WEAK,
                data_sufficiency=DATA_UNAVAILABLE,
                freshness_days=None,
                supporting_entity_ids=[],
                contradicting_entity_ids=[],
                rationale=(
                    "Concepts do not cover the primary objection; closing this "
                    "gap improves strategic coverage."
                ),
                provenance_refs=[{"kind": "coverage"}],
                fills_coverage_gap=True,
            )
        )

    # --- Alignment validations (O8) -----------------------------------------
    unaligned = [
        entity_id
        for entity_id, ctx in strategy_context_by_entity.items()
        if not any(ctx.get(key) for key in _STRATEGY_REF_KEYS)
    ]
    offers_missing = all(
        not (ctx or {}).get("offer_reference")
        for ctx in strategy_context_by_entity.values()
    ) if strategy_context_by_entity else False
    messaging_missing = all(
        not (ctx or {}).get("messaging_reference")
        for ctx in strategy_context_by_entity.values()
    ) if strategy_context_by_entity else False

    if strategy_context_by_entity and offers_missing:
        opportunities.append(
            _base_opportunity(
                opportunity_type=OPT_VALIDATE_OFFER_ALIGNMENT,
                dimension="offer",
                target_reference="concept_portfolio",
                status="strategic_alignment_review",
                strength=STRENGTH_WEAK,
                data_sufficiency=DATA_UNAVAILABLE,
                freshness_days=None,
                supporting_entity_ids=sorted(unaligned)[:5],
                contradicting_entity_ids=[],
                rationale=(
                    "Linked concepts reference no offer candidate; validating "
                    "offer alignment is a strategic-coverage review item."
                ),
                provenance_refs=[{"kind": "strategy_context"}],
                has_strategy_alignment=False,
            )
        )
    if strategy_context_by_entity and messaging_missing:
        opportunities.append(
            _base_opportunity(
                opportunity_type=OPT_VALIDATE_MESSAGE_ALIGNMENT,
                dimension="messaging",
                target_reference="concept_portfolio",
                status="strategic_alignment_review",
                strength=STRENGTH_WEAK,
                data_sufficiency=DATA_UNAVAILABLE,
                freshness_days=None,
                supporting_entity_ids=sorted(unaligned)[:5],
                contradicting_entity_ids=[],
                rationale=(
                    "Linked concepts reference no messaging strategy; "
                    "validating message alignment is a review item."
                ),
                provenance_refs=[{"kind": "strategy_context"}],
                has_strategy_alignment=False,
            )
        )

    # Deterministic ordering everywhere.
    def _sort_key(opp: Mapping[str, Any]) -> tuple[Any, ...]:
        return (
            -opp["priority_score"],
            opp["opportunity_id"],
        )

    opportunities.sort(key=_sort_key)
    blocked.sort(key=lambda b: (b["blocked_by_gate"], b["type"], b["target_reference"]))
    return opportunities, blocked, evidence_gaps


def dedupe_opportunities(
    opportunities: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Stable de-duplication by deterministic opportunity id."""
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for opportunity in opportunities:
        oid = opportunity["opportunity_id"]
        if oid in seen:
            continue
        seen.add(oid)
        unique.append(dict(opportunity))
    return unique


# ---------------------------------------------------------------------------
# Plan assembly (8E.4)
# ---------------------------------------------------------------------------

_EXPANSION_TYPES = {
    OPT_EXPAND_SUPPORTED_ANGLE,
    OPT_TEST_NEW_ANGLE,
    OPT_TEST_NEW_HOOK,
    OPT_TEST_NEW_FORMAT,
}
_REVIEW_TYPES = {
    OPT_REFRESH_FATIGUED,
    OPT_REDUCE_ANGLE_CONCENTRATION,
    OPT_REDUCE_FORMAT_CONCENTRATION,
    OPT_IMPROVE_FUNNEL_COVERAGE,
    OPT_IMPROVE_PROOF_COVERAGE,
    OPT_IMPROVE_OBJECTION_COVERAGE,
    OPT_VALIDATE_OFFER_ALIGNMENT,
    OPT_VALIDATE_MESSAGE_ALIGNMENT,
}


def plan_status(
    opportunities: Sequence[Mapping[str, Any]],
    *,
    entities_total: int,
    entities_sufficient: int,
) -> str:
    """Deterministic overall plan state. No 'optimized'/'guaranteed' states.

    insufficient_data when fewer than LEARNING_MIN_ENTITIES entities are
    sufficiently observed - no pattern can exist below that floor, so the
    plan cannot be more actionable than that regardless of coverage noise.
    """
    if entities_total == 0:
        return PLAN_UNAVAILABLE
    from src.modules.creative.learning.thresholds import LEARNING_MIN_ENTITIES
    from src.modules.creative.optimization.thresholds import value as threshold_value

    if entities_sufficient < int(threshold_value(LEARNING_MIN_ENTITIES)):
        return PLAN_INSUFFICIENT_DATA
    types = {o["type"] for o in opportunities}
    if types & _EXPANSION_TYPES:
        return PLAN_TEST_READY
    if types & _REVIEW_TYPES:
        return PLAN_REVIEW_READY
    return PLAN_INVESTIGATE


def build_plan(
    *,
    profiles: Sequence[Mapping[str, Any]],
    patterns: Sequence[Mapping[str, Any]],
    portfolio_intelligence: Mapping[str, Any],
    coverage_gaps: Sequence[Mapping[str, Any]],
    strategy_context_by_entity: Mapping[str, Mapping[str, Any]],
    learning_summary: Mapping[str, Any] | None = None,
    learning_fingerprint: str | None = None,
    proof_coverage_present: bool = True,
    objection_coverage_present: bool = True,
) -> dict[str, Any]:
    """Full deterministic optimization plan (no timestamps inside)."""
    opportunities, blocked, evidence_gaps = build_opportunities(
        patterns=patterns,
        portfolio_intelligence=portfolio_intelligence,
        coverage_gaps=coverage_gaps,
        profiles=profiles,
        strategy_context_by_entity=strategy_context_by_entity,
        proof_coverage_present=proof_coverage_present,
        objection_coverage_present=objection_coverage_present,
    )
    opportunities = dedupe_opportunities(opportunities)

    entities_total = len(profiles)
    entities_sufficient = sum(1 for p in profiles if p.get("sufficiently_observed"))
    status = plan_status(
        opportunities,
        entities_total=entities_total,
        entities_sufficient=entities_sufficient,
    )

    fatigue_summary = {
        "fatigue_signal": sorted(
            p["entity"]["id"] for p in profiles if p.get("fatigue_status") == "fatigue_signal"
        ),
        "watch": sorted(
            p["entity"]["id"] for p in profiles if p.get("fatigue_status") == "watch"
        ),
        "healthy": sorted(
            p["entity"]["id"] for p in profiles if p.get("fatigue_status") == "healthy"
        ),
    }
    conflicts_summary = [
        {
            "dimension": pattern["dimension"],
            "value": pattern["value"],
            "supporting_count": pattern["positive_count"],
            "contradicting_count": pattern["negative_count"],
            "supporting_ids": pattern["supporting_entity_ids"],
            "contradicting_ids": pattern["contradicting_entity_ids"],
            "minority_share": pattern["minority_share"],
            "freshness_days": pattern["max_freshness_days"],
        }
        for pattern in patterns
        if pattern["status"] == PATTERN_CONFLICTING
    ]

    test_opportunities = [o for o in opportunities if o["type"] in _EXPANSION_TYPES]
    refresh_opportunities = [o for o in opportunities if o["type"] == OPT_REFRESH_FATIGUED]

    concentration_analysis = {
        "angle_concentration": dict(portfolio_intelligence.get("angle_concentration") or {}),
        "format_concentration": dict(portfolio_intelligence.get("format_concentration") or {}),
        "role_balance": portfolio_intelligence.get("role_balance"),
    }

    coverage_analysis = {
        "coverage_gaps": list(coverage_gaps),
        "funnel_stages_observed": sorted(
            {
                str((p.get("context") or {}).get("funnel_stage"))
                for p in profiles
                if (p.get("context") or {}).get("funnel_stage")
            }
        ),
        "canonical_funnel_stages": list(CANONICAL_FUNNEL_STAGES),
    }

    plan = {
        "rules_versions": {"engine": OPTIMIZATION_RULES_VERSION},
        "optimization_status": status,
        "summary": {
            "entities_total": entities_total,
            "entities_sufficient": entities_sufficient,
            "opportunities_total": len(opportunities),
            "blocked_total": len(blocked),
            "by_priority": {
                priority: sum(1 for o in opportunities if o["priority"] == priority)
                for priority in (PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW)
            },
            "note": (
                "prioritization score is deterministic review ordering; "
                "not a probability of success"
            ),
        },
        "opportunities": opportunities,
        "blocked_opportunities": blocked,
        "evidence_gaps": evidence_gaps,
        "recommended_tests": test_opportunities,
        "refresh_investigations": refresh_opportunities,
        "concentration_analysis": concentration_analysis,
        "coverage_analysis": coverage_analysis,
        "fatigue_summary": fatigue_summary,
        "conflicting_evidence_summary": conflicts_summary,
        "learning_summary": dict(learning_summary or {}),
        "learning_snapshot_reference": learning_fingerprint,
        "provenance_index": [
            {"entity_id": entity_id, "chain": (ctx or {}).get("provenance_chain")}
            for entity_id, ctx in sorted(strategy_context_by_entity.items())
        ],
    }
    plan["fingerprint"] = fingerprint_payload(plan)
    return plan


def empty_plan() -> dict[str, Any]:
    """Explicit empty plan when nothing is linked/observed yet."""
    return {
        "rules_versions": {"engine": OPTIMIZATION_RULES_VERSION},
        "optimization_status": PLAN_UNAVAILABLE,
        "summary": {
            "entities_total": 0,
            "entities_sufficient": 0,
            "opportunities_total": 0,
            "blocked_total": 0,
            "by_priority": {"high": 0, "medium": 0, "low": 0},
            "reason": "no_performance_links_recorded",
            "note": (
                "prioritization score is deterministic review ordering; "
                "not a probability of success"
            ),
        },
        "opportunities": [],
        "blocked_opportunities": [],
        "evidence_gaps": [],
        "recommended_tests": [],
        "refresh_investigations": [],
        "concentration_analysis": {},
        "coverage_analysis": {},
        "fatigue_summary": {},
        "conflicting_evidence_summary": [],
        "learning_summary": {},
        "learning_snapshot_reference": None,
        "provenance_index": [],
        "fingerprint": "",
    }


def fingerprint_payload(value: Any) -> str:
    from src.modules.creative.performance.engine import fingerprint, to_jsonable

    return fingerprint(to_jsonable(value))


__all__ = [
    "OPTIMIZATION_RULES_VERSION",
    "build_plan",
    "plan_status",
    "build_opportunities",
    "dedupe_opportunities",
    "make_opportunity_id",
    "_gate_check_expansion",
]
