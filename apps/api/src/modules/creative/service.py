"""Deterministic creative intelligence service (Phases 8A/8B).

Pure validators and taxonomy checks plus async persistence helpers for
creative concepts. All logic is deterministic — no LLM, no asset
generation, no performance learning. Creative defines what and why, not
the final image/video.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.creative import (
    CreativeBrief,
    CreativeConcept,
    CreativeConceptPortfolio,
    CreativePortfolio,
    CreativeStrategy,
    CreativeTest,
    CreativeTestVariant,
)
from src.db.models.strategy import (
    MessagingStrategy,
    OfferCandidate,
    PositioningStrategy,
)
from src.modules.creative.errors import InvalidCreativeInputError
from src.modules.creative.schemas import WhitespaceGap, WhitespaceOut


# ---------------------------------------------------------------------------
# Objective validation — must map to a valid funnel stage
# ---------------------------------------------------------------------------

_VALID_FUNNEL_STAGES = {"awareness", "interest", "consideration", "purchase", "retention"}

_OBJECTIVE_FUNNEL_STAGE_MAP = {
    "awareness": "awareness",
    "traffic": "awareness",
    "reach": "awareness",
    "interest": "interest",
    "consideration": "consideration",
    "evaluation": "consideration",
    "purchase": "purchase",
    "conversion": "purchase",
    "sale": "purchase",
    "retention": "retention",
    "churn-reduction": "retention",
    "loyalty": "retention",
}


def infer_funnel_stage_from_objective(objective: str | None) -> str | None:
    """Deterministic objective → funnel stage mapping (None when unmapped)."""
    if not objective:
        return None
    return _OBJECTIVE_FUNNEL_STAGE_MAP.get(objective.lower())


def validate_objective_funnel_stage(
    objective: str, funnel_stage: str | None
) -> tuple[bool, str | None]:
    """Validate that objective is consistent with funnel stage.

    Returns (is_valid, error_reason). Error reason is None when valid.
    """
    if not objective:
        return False, "objective_required"

    expected_stage = _OBJECTIVE_FUNNEL_STAGE_MAP.get(objective.lower())
    if expected_stage and funnel_stage:
        if funnel_stage != expected_stage:
            return False, f"objective_funnel_mismatch:{objective}:{funnel_stage}"
        return True, None

    return True, None


# ---------------------------------------------------------------------------
# Positioning consistency check
# ---------------------------------------------------------------------------


def validate_positioning_consistency(
    positioning: PositioningStrategy | None,
    *,
    organization_id: uuid.UUID,
    business_id: uuid.UUID,
) -> tuple[bool, str | None]:
    """Validate that a positioning strategy belongs to the same tenant/business.

    Returns (is_valid, error_reason).
    """
    if positioning is None:
        return True, None
    if positioning.organization_id != organization_id:
        return False, "cross_tenant_positioning"
    if positioning.business_id != business_id:
        return False, "business_mismatch"
    return True, None


# ---------------------------------------------------------------------------
# Offer availability check
# ---------------------------------------------------------------------------


def validate_offer_availability(
    offer_candidate: OfferCandidate | None,
) -> tuple[bool, str | None]:
    """Validate that a referenced offer exists and is available.

    Never fabricates promotion: an unavailable offer is an explicit error.
    """
    if offer_candidate is None:
        return False, "offer_unavailable"
    if offer_candidate.status != "available":
        return False, f"offer_status:{offer_candidate.status}"
    return True, None


# ---------------------------------------------------------------------------
# Messaging proof reference check
# ---------------------------------------------------------------------------


def validate_proof_reference(
    concept_reason_to_believe: str | None,
    messaging: MessagingStrategy | None,
) -> tuple[bool, str | None]:
    """Validate that proof references exist in messaging.

    Every reason_to_believe must have traceable proof in the messaging
    strategy. Never invents reviews/ratings/statistics.
    """
    if not concept_reason_to_believe:
        return True, None
    if messaging is None:
        return False, "proof_status_unavailable"
    proof_available = bool((messaging.input_snapshot or {}).get("proof_points"))
    if not proof_available:
        return False, "proof_status_unavailable"
    return True, None


# ---------------------------------------------------------------------------
# Hook Direction validation
# ---------------------------------------------------------------------------

_VALID_HOOK_DIRECTIONS = {
    "problem_agitation",     # Open with the customer's problem
    "benefit_focus",        # Open with primary benefit
    "objection_preempt",    # Open by addressing main objection
    "curiosity_gap",        # Open with knowledge gap
    "authority_establish",  # Open with credible authority
    "social_proof",         # Open with customer social proof
    "urgency",              # Open with time-sensitive urgency
    "personal_story",       # Open with relatable personal story
}


def validate_hook_direction(hook_direction: str | None) -> tuple[bool, str | None]:
    """Validate hook direction is from the controlled taxonomy.

    Hook Direction is a strategic direction — NOT final ad copy. It
    explains the opening objective, not the final sentence.
    """
    if not hook_direction:
        return True, None  # Optional field

    if hook_direction not in _VALID_HOOK_DIRECTIONS:
        return False, f"invalid_hook_direction:{hook_direction}"

    return True, None


# ---------------------------------------------------------------------------
# Creative Format taxonomy validation
# ---------------------------------------------------------------------------

_VALID_CREATIVE_FORMATS = {
    "static",
    "carousel",
    "short_video",
    "ugc",
    "testimonial",
    "product_demo",
    "before_after",
    "founder_led",
    "screen_recording",
    "lifestyle",
    "comparison",
    "educational",
}


def validate_creative_format(creative_format: str | None) -> tuple[bool, str | None]:
    """Validate creative format is from the controlled taxonomy."""
    if not creative_format:
        return True, None
    if creative_format not in _VALID_CREATIVE_FORMATS:
        return False, f"invalid_creative_format:{creative_format}"
    return True, None


# ---------------------------------------------------------------------------
# Creative Type separation (format ≠ type)
# ---------------------------------------------------------------------------


def validate_creative_type(
    creative_format: str | None,
    creative_type: str | None,
) -> tuple[bool, str | None]:
    """Validate that creative_type is appropriate for the format."""
    if not creative_format:
        return True, None
    if creative_format not in _VALID_CREATIVE_FORMATS:
        return False, f"invalid_creative_format:{creative_format}"
    # Any type is accepted for a recognized format; format/type compatibility
    # may be tightened per vertical without changing this contract.
    return True, None


# ---------------------------------------------------------------------------
# Emotional Direction validation
# ---------------------------------------------------------------------------

_VALID_EMOTIONS = {
    "relief",
    "confidence",
    "aspiration",
    "curiosity",
    "trust",
    "urgency",
    "desire",
    "belonging",
    "authority",
    "security",
}


def validate_emotional_direction(
    primary_emotion: str | None,
    secondary_emotion: str | None,
) -> tuple[bool, str | None]:
    """Validate emotional direction categories (controlled taxonomy).

    Only ``None`` means "not provided"; an empty string is rejected.
    """
    errors = []

    if primary_emotion is not None and primary_emotion not in _VALID_EMOTIONS:
        errors.append(f"invalid_primary_emotion:{primary_emotion}")

    if secondary_emotion is not None and secondary_emotion not in _VALID_EMOTIONS:
        errors.append(f"invalid_secondary_emotion:{secondary_emotion}")

    if errors:
        return False, "; ".join(errors)

    return True, None


# ---------------------------------------------------------------------------
# Success Metric mapping to existing KPIs
# ---------------------------------------------------------------------------

_KPI_METRIC_MAP = {
    "awareness": "CTR",
    "traffic": "CTR",
    "reach": "CTR",
    "interest": "CTR",
    "consideration": "CVR",
    "purchase": "CPA",
    "conversion": "CPA",
    "sale": "CPA",
    "retention": "Repeat Rate",
    "churn-reduction": "Churn Rate",
    "loyalty": "AOV",
}


def map_objective_to_metric(objective: str) -> str | None:
    """Map objective to an existing KPI metric name (None when unavailable)."""
    if not objective:
        return None
    return _KPI_METRIC_MAP.get(objective.lower())


# ---------------------------------------------------------------------------
# Diversity / redundancy analysis (pure functions over concepts)
# ---------------------------------------------------------------------------


def detect_angle_diversity(concepts: Sequence[CreativeConcept]) -> dict[str, Any]:
    """Detect whether concepts share the same angle/format/hook/offer.

    Returns diversity analysis with concentration risk flag.
    """
    if not concepts:
        return {
            "angle_diversity": "none",
            "concentration_risk": False,
            "angle_distribution": {},
            "format_distribution": {},
            "hook_direction_distribution": {},
            "offer_distribution": {},
        }

    angle_counts: dict[str, int] = {}
    format_counts: dict[str, int] = {}
    hook_counts: dict[str, int] = {}
    offer_counts: dict[str, int] = {}

    for concept in concepts:
        angle = concept.angle or "unspecified"
        fmt = concept.creative_format or "unspecified"
        hook = concept.hook_direction or "unspecified"
        offer = (concept.offer_direction or "")[:20] or "unspecified"

        angle_counts[angle] = angle_counts.get(angle, 0) + 1
        format_counts[fmt] = format_counts.get(fmt, 0) + 1
        hook_counts[hook] = hook_counts.get(hook, 0) + 1
        offer_counts[offer] = offer_counts.get(offer, 0) + 1

    total = len(concepts)
    concentration_risk = max(angle_counts.values()) / total > 0.5

    unique_angles = len(angle_counts)
    if unique_angles == total:
        diversity_level = "maximum"
    elif unique_angles >= total / 2:
        diversity_level = "good"
    elif unique_angles >= total / 4:
        diversity_level = "limited"
    else:
        diversity_level = "poor"

    return {
        "angle_diversity": diversity_level,
        "concentration_risk": concentration_risk,
        "angle_distribution": angle_counts,
        "format_distribution": format_counts,
        "hook_direction_distribution": hook_counts,
        "offer_distribution": offer_counts,
    }


def compute_redundancy_analysis(
    concepts: Sequence[CreativeConcept],
) -> dict[str, Any]:
    """Detect redundancy across creative concepts.

    Redundancy is determined by shared strategic attributes: angle,
    creative_format, hook_direction and offer_direction.
    """
    if not concepts:
        return {
            "is_duplicate": False,
            "shared_attributes": 0,
            "total_attributes": 4,
            "redundant_groups": [],
            "redundancy_score": 0.0,
        }

    total = len(concepts)

    angle_freq: dict[str, int] = {}
    format_freq: dict[str, int] = {}
    hook_freq: dict[str, int] = {}
    offer_freq: dict[str, int] = {}

    for concept in concepts:
        angle = concept.angle or "unspecified"
        fmt = concept.creative_format or "unspecified"
        hook = concept.hook_direction or "unspecified"
        offer = (concept.offer_direction or "")[:20] or "unspecified"

        angle_freq[angle] = angle_freq.get(angle, 0) + 1
        format_freq[fmt] = format_freq.get(fmt, 0) + 1
        hook_freq[hook] = hook_freq.get(hook, 0) + 1
        offer_freq[offer] = offer_freq.get(offer, 0) + 1

    shared_attributes = 0
    for freq in (angle_freq, format_freq, hook_freq, offer_freq):
        if max(freq.values()) / total > Decimal("0.5"):
            shared_attributes += 1
    total_attributes = 4

    redundant_groups: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()

    for i, c1 in enumerate(concepts):
        for c2 in concepts[i + 1:]:
            shared_attrs = sum(
                (
                    (c1.angle or "") == (c2.angle or ""),
                    (c1.creative_format or "") == (c2.creative_format or ""),
                    (c1.hook_direction or "") == (c2.hook_direction or ""),
                )
            )
            if shared_attrs >= 2:
                pair_key = tuple(sorted([str(c1.id), str(c2.id)]))
                if pair_key not in seen_pairs:
                    seen_pairs.add(pair_key)
                    redundant_groups.append(
                        {
                            "concept_ids": [str(c1.id), str(c2.id)],
                            "shared_attributes": shared_attrs,
                        }
                    )

    redundancy_score = round(shared_attributes / total_attributes, 2)

    is_duplicate = total >= 2 and shared_attributes / total_attributes > 0.5

    return {
        "is_duplicate": is_duplicate,
        "shared_attributes": shared_attributes,
        "total_attributes": total_attributes,
        "redundant_groups": redundant_groups,
        "redundancy_score": redundancy_score,
    }


# ---------------------------------------------------------------------------
# Test prioritization (pure)
# ---------------------------------------------------------------------------


def prioritize_test_groups(
    test_groups: list[dict[str, Any]],
    concepts: Sequence[CreativeConcept] | None = None,
) -> list[dict[str, Any]]:
    """Prioritize test groups by learning value, evidence and redundancy.

    Returns test groups sorted by priority score (high to low); ties keep
    input order (stable sort).
    """
    if not test_groups:
        return []

    redundancy = compute_redundancy_analysis(concepts) if concepts and len(concepts) > 1 else None

    scored_groups: list[dict[str, Any]] = []

    for group in test_groups:
        score = 0
        reasons: list[str] = []

        learning_value = group.get("learning_value", "low")
        if learning_value == "high":
            score += 3
            reasons.append("high learning value")
        elif learning_value == "medium":
            score += 2
            reasons.append("medium learning value")
        else:
            score += 1
            reasons.append("low learning value")

        evidence_strength = group.get("evidence_strength", "hypothesis")
        if evidence_strength == "supported":
            score += 2
            reasons.append("supported by evidence")
        elif evidence_strength == "hypothesis":
            score += 1
            reasons.append("hypothesis-based")

        if redundancy is not None and redundancy["is_duplicate"]:
            score -= 2
            reasons.append("redundant with existing concepts")

        status = group.get("status", "draft")
        if status == "valid":
            score += 1
            reasons.append("valid strategy")
        elif status == "needs_evidence":
            reasons.append("needs evidence")
        elif status == "insufficient_data":
            score += 3
            reasons.append("fills gap (insufficient data)")

        scored_groups.append(
            {
                "group": group,
                "priority_score": score,
                "prioritization_reasons": reasons,
            }
        )

    scored_groups.sort(key=lambda x: x["priority_score"], reverse=True)
    return scored_groups


# ---------------------------------------------------------------------------
# Whitespace identification (pure)
# ---------------------------------------------------------------------------

_ALL_ANGLES = frozenset(_VALID_HOOK_DIRECTIONS)


def identify_creative_whitespace(
    *,
    competitor_patterns: list[dict[str, Any]] | None = None,
    customer_evidence: list[dict[str, Any]] | None = None,
    concepts: Sequence[CreativeConcept] | None = None,
) -> WhitespaceOut:
    """Identify creative gaps as hypotheses — never guaranteed winners.

    Deterministic confidence from evidence density; strength classification
    low/medium/high. No LLM and no performance prediction.
    """
    gaps: list[WhitespaceGap] = []
    confidence = 0.0
    evidence_sources: set[str] = set()

    if competitor_patterns:
        format_usage: dict[str, int] = {}
        for pattern in competitor_patterns:
            fmt = str(pattern.get("creative_format", "unknown"))
            format_usage[fmt] = format_usage.get(fmt, 0) + 1

        total_competitor_formats = sum(format_usage.values())
        for fmt, count in sorted(format_usage.items()):
            proportion = count / total_competitor_formats if total_competitor_formats else 0.0
            if proportion < 0.1:
                underrep_factor = 1.0 - proportion
                gap_confidence = round(0.35 + 0.15 * underrep_factor, 2)
                gaps.append(
                    WhitespaceGap(
                        observed_competitor_pattern=(
                            f"{fmt} used by {proportion:.0%} of competitors"
                        ),
                        potential_gap=(
                            f"Consider {fmt} format not commonly used in category"
                        ),
                        hypothesis=(f"{fmt} format could differentiate with right messaging"),
                        confidence=gap_confidence,
                        strength=(
                            "high"
                            if underrep_factor > 0.5
                            else "medium"
                            if underrep_factor > 0.2
                            else "low"
                        ),
                    )
                )

    if customer_evidence:
        for evidence in customer_evidence:
            pain_points = evidence.get("pain_points") or {}
            if isinstance(pain_points, dict):
                evidence_sources.update(str(key) for key in pain_points.keys())

        raw_confidence = min(
            0.95,
            0.2
            + 0.1 * min(len(customer_evidence), 10)
            + 0.05 * min(len(evidence_sources), 10),
        )
        confidence = max(confidence, raw_confidence)

    if not competitor_patterns and not customer_evidence and concepts:
        used_angles = {c.angle for c in concepts if c.angle}
        used_formats = {c.creative_format for c in concepts if c.creative_format}
        unused_formats = sorted(_VALID_CREATIVE_FORMATS - used_formats)
        unused_angles = sorted(_ALL_ANGLES - used_angles)
        for angle in unused_angles[:3]:
            for fmt in unused_formats[:3]:
                confidence_base = max(0.1, 0.5 - 0.02 * len(concepts))
                novelty_boost = 0.1 if len(gaps) < 3 else 0.0
                gap_confidence = round(min(0.9, confidence_base + novelty_boost), 2)
                gaps.append(
                    WhitespaceGap(
                        observed_competitor_pattern=(
                            f"angle={angle}, format={fmt} not yet explored"
                        ),
                        potential_gap=f"Test angle={angle} with format={fmt}",
                        hypothesis="This combination could reveal new engagement",
                        confidence=gap_confidence,
                        strength=(
                            "high"
                            if gap_confidence >= 0.7
                            else "medium"
                            if gap_confidence >= 0.4
                            else "low"
                        ),
                    )
                )
        confidence = max(confidence, 0.1)

    if competitor_patterns and customer_evidence and gaps:
        gap_avg = sum(gap.confidence for gap in gaps) / len(gaps)
        confidence = round((confidence + gap_avg) / 2, 2)

    strength = "high" if confidence >= 0.7 else "medium" if confidence >= 0.4 else "low"

    summary = (
        f"{len(gaps)} potential creative gaps identified, "
        f"confidence {confidence:.0%} ({strength}) — hypotheses, not guaranteed winners"
    )

    return WhitespaceOut(
        gaps=gaps,
        confidence=round(confidence, 2),
        strength=strength,
        whitespace_summary=summary,
    )


# ---------------------------------------------------------------------------
# Async persistence helpers
# ---------------------------------------------------------------------------


async def _resolve_reference(
    session: AsyncSession,
    model: type,
    *,
    reference_id: uuid.UUID | None,
    organization_id: uuid.UUID,
    business_id: uuid.UUID,
    label: str,
):
    """Fetch a strategy reference scoped to org+business (404 semantics)."""
    if reference_id is None:
        return None
    row = (
        await session.execute(
            select(model).where(
                model.id == reference_id,
                model.organization_id == organization_id,
                model.business_id == business_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        from src.core.exceptions import NotFoundError

        raise NotFoundError(f"{label} not found in this business")
    return row


async def create_creative_concept(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    business_id: uuid.UUID,
    **fields: Any,
) -> CreativeConcept:
    """Create a CreativeConcept anchored in Phase 7 data.

    All references are validated inside the same tenant/business. No LLM,
    no asset generation, no performance learning.
    """
    hook_direction = fields.get("hook_direction")
    creative_format = fields.get("creative_format")
    creative_type = fields.get("creative_type")
    primary_emotion = fields.get("primary_emotion")
    secondary_emotion = fields.get("secondary_emotion")
    success_metric = fields.get("success_metric")
    funnel_stage = fields.get("funnel_stage")

    is_valid, error = validate_hook_direction(hook_direction)
    if not is_valid:
        raise InvalidCreativeInputError(error or "invalid hook direction")

    is_valid, error = validate_creative_format(creative_format)
    if not is_valid:
        raise InvalidCreativeInputError(error or "invalid creative format")

    is_valid, error = validate_creative_type(creative_format, creative_type)
    if not is_valid:
        raise InvalidCreativeInputError(error or "invalid creative type")

    is_valid, error = validate_emotional_direction(primary_emotion, secondary_emotion)
    if not is_valid:
        raise InvalidCreativeInputError(error or "invalid emotional direction")

    positioning = await _resolve_reference(
        session,
        PositioningStrategy,
        reference_id=fields.get("positioning_reference"),
        organization_id=organization_id,
        business_id=business_id,
        label="Positioning strategy",
    )
    offer = await _resolve_reference(
        session,
        OfferCandidate,
        reference_id=fields.get("offer_reference"),
        organization_id=organization_id,
        business_id=business_id,
        label="Offer candidate",
    )
    messaging = await _resolve_reference(
        session,
        MessagingStrategy,
        reference_id=fields.get("messaging_reference"),
        organization_id=organization_id,
        business_id=business_id,
        label="Messaging strategy",
    )

    if positioning is not None:
        is_valid, error = validate_positioning_consistency(
            positioning,
            organization_id=organization_id,
            business_id=business_id,
        )
        if not is_valid:
            raise InvalidCreativeInputError(error or "positioning inconsistent")

    if fields.get("offer_reference") is not None:
        is_valid, error = validate_offer_availability(offer)
        if not is_valid:
            raise InvalidCreativeInputError(error or "offer unavailable")

    if fields.get("messaging_reference") is not None:
        is_valid, error = validate_proof_reference(
            fields.get("reason_to_believe"), messaging
        )
        if not is_valid:
            raise InvalidCreativeInputError(error or "proof unavailable")

    if not success_metric:
        # Optional transient objective (not persisted) drives the KPI mapping.
        success_metric = map_objective_to_metric(fields.get("objective"))

    if not funnel_stage:
        funnel_stage = infer_funnel_stage_from_objective(fields.get("objective"))

    concept = CreativeConcept(
        organization_id=organization_id,
        business_id=business_id,
        strategy_version=fields.get("strategy_version", "v1"),
        positioning_reference=fields.get("positioning_reference"),
        offer_reference=fields.get("offer_reference"),
        messaging_reference=fields.get("messaging_reference"),
        funnel_reference=fields.get("funnel_reference"),
        funnel_stage=funnel_stage,
        audience=fields.get("audience"),
        angle=fields.get("angle"),
        message=fields.get("message"),
        hook_direction=hook_direction,
        creative_format=creative_format,
        creative_type=creative_type,
        offer_direction=fields.get("offer_direction"),
        cta=fields.get("cta"),
        visual_direction=fields.get("visual_direction"),
        copy_direction=fields.get("copy_direction"),
        primary_emotion=primary_emotion,
        secondary_emotion=secondary_emotion,
        objection=fields.get("objection"),
        reason_to_believe=fields.get("reason_to_believe"),
        testing_role=fields.get("testing_role"),
        success_metric=success_metric,
        evidence=fields.get("evidence") or {},
        risks=fields.get("risks") or [],
        status="draft",
    )
    session.add(concept)
    await session.flush()
    return concept


async def generate_creative_brief(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    business_id: uuid.UUID,
    objective: str,
    creative_format: str,
    **fields: Any,
) -> CreativeBrief:
    """Generate a CreativeBrief from Phase 7 strategy data (deterministic)."""
    funnel_stage = fields.get("funnel_stage")
    hook_direction = fields.get("hook_direction")
    primary_emotion = fields.get("primary_emotion")
    secondary_emotion = fields.get("secondary_emotion")

    is_valid, error = validate_objective_funnel_stage(objective, funnel_stage)
    if not is_valid:
        raise InvalidCreativeInputError(error or "objective invalid")

    is_valid, error = validate_hook_direction(hook_direction)
    if not is_valid:
        raise InvalidCreativeInputError(error or "invalid hook direction")

    is_valid, error = validate_creative_format(creative_format)
    if not is_valid:
        raise InvalidCreativeInputError(error or "invalid creative format")

    is_valid, error = validate_emotional_direction(primary_emotion, secondary_emotion)
    if not is_valid:
        raise InvalidCreativeInputError(error or "invalid emotional direction")

    success_metric = fields.get("success_metric") or map_objective_to_metric(objective)

    brief = CreativeBrief(
        organization_id=organization_id,
        business_id=business_id,
        objective=objective,
        target_audience=fields.get("audience"),
        funnel_stage=funnel_stage,
        customer_problem=fields.get("customer_problem"),
        customer_desire=fields.get("customer_desire"),
        core_message=fields.get("message"),
        angle=fields.get("angle"),
        hook_direction=hook_direction,
        offer=fields.get("offer_direction"),
        cta=fields.get("cta"),
        creative_format=creative_format,
        visual_direction=fields.get("visual_direction"),
        copy_direction=fields.get("copy_direction"),
        emotional_direction=(
            f"{primary_emotion or ''} {secondary_emotion or ''}".strip()
            if (primary_emotion or secondary_emotion)
            else None
        ),
        reason_to_believe=fields.get("reason_to_believe"),
        testing_hypothesis=fields.get("testing_role") or "baseline",
        success_metric=success_metric,
        evidence=fields.get("evidence") or {},
        status="draft",
    )
    session.add(brief)
    await session.flush()
    return brief


# ---------------------------------------------------------------------------
# Read helpers (tenant/business scoped)
# ---------------------------------------------------------------------------


async def list_concepts(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    business_id: uuid.UUID,
    limit: int = 50,
    cursor: datetime | None = None,
    cursor_id: uuid.UUID | None = None,
    include_archived: bool = False,
) -> tuple[list[CreativeConcept], uuid.UUID | None]:
    """Keyset-paginated concept listing; returns (items, next_cursor)."""
    conditions = [
        CreativeConcept.organization_id == organization_id,
        CreativeConcept.business_id == business_id,
    ]
    if not include_archived:
        conditions.append(CreativeConcept.status != "archived")
    if cursor is not None and cursor_id is not None:
        conditions.append(
            (CreativeConcept.created_at, CreativeConcept.id) < (cursor, cursor_id)
        )
    rows = (
        (
            await session.execute(
                select(CreativeConcept)
                .where(*conditions)
                .order_by(CreativeConcept.created_at.desc(), CreativeConcept.id.desc())
                .limit(limit + 1)
            )
        )
        .scalars()
        .all()
    )
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = rows[-1].id
    return list(rows), next_cursor


async def get_concept(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    business_id: uuid.UUID,
    concept_id: uuid.UUID,
) -> CreativeConcept | None:
    return (
        await session.execute(
            select(CreativeConcept).where(
                CreativeConcept.id == concept_id,
                CreativeConcept.organization_id == organization_id,
                CreativeConcept.business_id == business_id,
            )
        )
    ).scalar_one_or_none()


async def list_strategies(
    session: AsyncSession, *, organization_id: uuid.UUID, business_id: uuid.UUID
) -> list[CreativeStrategy]:
    rows = (
        (
            await session.execute(
                select(CreativeStrategy)
                .where(
                    CreativeStrategy.organization_id == organization_id,
                    CreativeStrategy.business_id == business_id,
                )
                .order_by(CreativeStrategy.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def list_tests(
    session: AsyncSession, *, organization_id: uuid.UUID, business_id: uuid.UUID
) -> list[CreativeTest]:
    rows = (
        (
            await session.execute(
                select(CreativeTest)
                .where(
                    CreativeTest.organization_id == organization_id,
                    CreativeTest.business_id == business_id,
                )
                .order_by(CreativeTest.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def get_test(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    business_id: uuid.UUID,
    test_id: str,
) -> CreativeTest | None:
    return (
        await session.execute(
            select(CreativeTest).where(
                CreativeTest.test_id == test_id,
                CreativeTest.organization_id == organization_id,
                CreativeTest.business_id == business_id,
            )
        )
    ).scalar_one_or_none()


async def list_test_variants(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    business_id: uuid.UUID,
    test_id: str,
) -> list[CreativeTestVariant]:
    rows = (
        (
            await session.execute(
                select(CreativeTestVariant)
                .where(
                    CreativeTestVariant.test_id == test_id,
                    CreativeTestVariant.organization_id == organization_id,
                    CreativeTestVariant.business_id == business_id,
                )
                .order_by(CreativeTestVariant.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def list_portfolios(
    session: AsyncSession, *, organization_id: uuid.UUID, business_id: uuid.UUID
) -> list[CreativePortfolio]:
    rows = (
        (
            await session.execute(
                select(CreativePortfolio)
                .where(
                    CreativePortfolio.organization_id == organization_id,
                    CreativePortfolio.business_id == business_id,
                )
                .order_by(CreativePortfolio.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def list_concept_portfolios(
    session: AsyncSession, *, organization_id: uuid.UUID, business_id: uuid.UUID
) -> list[CreativeConceptPortfolio]:
    rows = (
        (
            await session.execute(
                select(CreativeConceptPortfolio)
                .where(
                    CreativeConceptPortfolio.organization_id == organization_id,
                    CreativeConceptPortfolio.business_id == business_id,
                )
                .order_by(CreativeConceptPortfolio.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


__all__ = [
    "validate_objective_funnel_stage",
    "validate_positioning_consistency",
    "validate_offer_availability",
    "validate_proof_reference",
    "validate_hook_direction",
    "validate_creative_format",
    "validate_creative_type",
    "validate_emotional_direction",
    "map_objective_to_metric",
    "infer_funnel_stage_from_objective",
    "generate_creative_brief",
    "create_creative_concept",
    "detect_angle_diversity",
    "identify_creative_whitespace",
    "compute_redundancy_analysis",
    "prioritize_test_groups",
    "list_concepts",
    "get_concept",
    "list_strategies",
    "list_tests",
    "get_test",
    "list_test_variants",
    "list_portfolios",
    "list_concept_portfolios",
]
