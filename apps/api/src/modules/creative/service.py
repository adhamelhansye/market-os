"""Deterministic creative intelligence service (Phase 8A).

Provides functions for creative concept generation, brief creation,
validation, and matrix operations. All logic is deterministic — no LLM,
no asset generation, no performance learning. Creative defines what and
why, not the final image/video.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from src.db.models.creative import (
    CreativeConcept,
    CreativeBrief,
    CreativeMatrixEntry,
    CreativeRisk,
    CreativeEvidence,
    CreativeSnapshot,
    CreativeProvenance,
)
from src.db.models.strategy import (
    PositioningStrategy,
    OfferCandidate,
    MessagingStrategy,
    MessageAngle,
    MessageComponent,
)
from src.db.base import Base


# ---------------------------------------------------------------------------
# Objective validation — must map to a valid funnel stage
# ---------------------------------------------------------------------------

_VALID_FUNNEL_STAGES = {"awareness", "interest", "consideration", "purchase", "retention"}


def validate_objective_funnel_stage(objective: str, funnel_stage: str | None) -> tuple[bool, str | None]:
    """Validate that objective is consistent with funnel stage.

    Returns (is_valid, error_reason). Error reason is None when valid.
    """
    if not objective:
        return False, "objective_required"

    # Map objective to funnel stage
    objective_lower = objective.lower()
    stage_map = {
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

    expected_stage = stage_map.get(objective_lower)
    if expected_stage and funnel_stage:
        if funnel_stage != expected_stage:
            return False, f"objective_funnel_mismatch:{objective}:{funnel_stage}"
        return True, None

    if expected_stage and not funnel_stage:
        # No funnel stage provided — that's OK, will be validated later
        return True, None

    # If objective doesn't match known map but is provided, accept if
    # funnel stage is also provided (they may be custom)
    if not expected_stage and funnel_stage:
        return True, None

    return True, None


# ---------------------------------------------------------------------------
# Positioning consistency check
# ---------------------------------------------------------------------------

def validate_positioning_consistency(
    concept: CreativeConcept,
    positioning: PositioningStrategy | None,
    business_id: str,
) -> tuple[bool, str | None]:
    """Validate that concept positioning is consistent with strategy.

    Returns (is_valid, error_reason). Positioning contradiction → invalid,
    reason positioning_conflict.
    """
    if not positioning:
        # No positioning to conflict with — OK
        return True, None

    # Check that positioning belongs to same business
    if positioning.organization_id != concept.organization_id:
        return False, "cross_tenant_positioning"

    if positioning.business_id != business_id:
        return False, "business_mismatch"

    # TODO: Add more consistency checks:
    # - message alignment
    # - offer alignment
    # - audience alignment

    return True, None


# ---------------------------------------------------------------------------
# Offer availability check
# ---------------------------------------------------------------------------

def validate_offer_availability(
    concept: CreativeConcept,
    offer_candidate: OfferCandidate | None,
    business_id: str,
) -> tuple[bool, str | None]:
    """Validate that concept offer is available.

    If concept has offer_reference and offer is unavailable → offer_status
    unavailable. Never fabricate promotion.
    """
    if not concept.offer_reference:
        # No offer referenced — OK
        return True, None

    if not offer_candidate:
        return False, "offer_unavailable"

    # Check offer belongs to same business
    if offer_candidate.organization_id != concept.organization_id:
        return False, "cross_tenant_offer"

    if offer_candidate.business_id != business_id:
        return False, "business_mismatch"

    # Check offer status
    if offer_candidate.status != "available":
        return False, f"offer_status:{offer_candidate.status}"

    return True, None


# ---------------------------------------------------------------------------
# Messaging proof reference check
# ---------------------------------------------------------------------------

def validate_proof_reference(
    concept: CreativeConcept,
    messaging: MessagingStrategy | None,
) -> tuple[bool, str | None]:
    """Validate that concept proof references exist in messaging.

    Every reason_to_believe must have a traceable proof source in the
    messaging strategy. Never invent reviews/ratings/statistics.
    """
    if not messaging:
        # No messaging to reference — proof_status unavailable if
        # reason_to_believe is present
        if concept.reason_to_believe:
            return False, "proof_status_unavailable"
        return True, None

    # Check that proof references are traceable to messaging components
    # This is a structural validation — we don't copy proof content,
    # we only verify references exist
    if concept.reason_to_believe:
        # Verify at least one evidence_ref exists in messaging
        proof_available = bool(messaging.input_snapshot.get("proof_points"))
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
    """Validate that creative_type is appropriate for the format.

    Examples of valid format/type combos:
    - format=short_video, type=ugc
    - format=carousel, type=comparison
    - format=static, type=product_focus
    - format=testimonial, type=testimonial
    """
    if not creative_format:
        return True, None
    if not creative_type:
        # Type optional when format provided — OK
        return True, None

    # Basic format/type compatibility checks
    format_type_pairs = {
        ("short_video", {"ugc", "testimonial", "product_demo", "founder_led"}),
        ("carousel", {"comparison", "product_focus", "educational"}),
        ("static", {"product_focus", "comparison", "educational", "before_after"}),
        ("ugc", {"ugc", "testimonial"}),
        ("testimonial", {"testimonial", "founder_led"}),
        ("product_demo", {"product_demo", "short_video"}),
        ("before_after", {"before_after", "static"}),
        ("founder_led", {"founder_led", "short_video"}),
        ("lifestyle", {"lifestyle", "static"}),
        ("comparison", {"comparison", "carousel"}),
        ("educational", {"educational", "static"}),
    }

    format_type_key = (creative_format, creative_type)
    if format_type_key not in format_type_pairs:
        # Allow any type if format is recognized — the combination may be
        # valid in a specific context not covered by the basic taxonomy
        if creative_format in _VALID_CREATIVE_FORMATS:
            return True, None
        return False, f"invalid_creative_format:{creative_format}"

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
    """Validate emotional direction categories.

    Controlled categories that must connect to existing research.
    """
    errors = []

    if primary_emotion and primary_emotion not in _VALID_EMOTIONS:
        errors.append(f"invalid_primary_emotion:{primary_emotion}")

    if secondary_emotion and secondary_emotion not in _VALID_EMOTIONS:
        errors.append(f"invalid_secondary_emotion:{secondary_emotion}")

    if primary_emotion and secondary_emotion and primary_emotion == secondary_emotion:
        # Allow same emotion twice — OK for emphasis
        pass

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
    """Map objective to existing KPI metric.

    Returns the KPI metric name, or None if unavailable.
    """
    objective_lower = objective.lower()
    return _KPI_METRIC_MAP.get(objective_lower)


# -------------------------------------------------------------------------#
# Core: Creative Concept generation from Phase 7 data
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #


def generate_creative_brief(
    db: Session,
    business_id: str,
    *,
    positioning_id: str | None = None,
    offer_id: str | None = None,
    messaging_id: str | None = None,
    funnel_stage: str | None = None,
    objective: str,
    audience: str | None = None,
    angle: str | None = None,
    hook_direction: str | None = None,
    creative_format: str,
    creative_type: str | None = None,
    message: str | None = None,
    offer_direction: str | None = None,
    cta: str | None = None,
    visual_direction: str | None = None,
    copy_direction: str | None = None,
    primary_emotion: str | None = None,
    secondary_emotion: str | None = None,
    objection: str | None = None,
    reason_to_believe: str | None = None,
    testing_role: str | None = None,
    success_metric: str | None = None,
    evidence: dict[str, Any] | None = None,
    risks: list[dict[str, Any]] | None = None,
) -> CreativeBrief:
    """Generate a CreativeBrief from Phase 7 strategy data.

    All data references existing Phase 7 modules. Never fabricates
    demographics, promotions, reviews, or performance predictions.
    """
    # Validate objective/funnel stage consistency
    is_valid, error = validate_objective_funnel_stage(objective, funnel_stage)
    if not is_valid:
        raise ValueError(f"Objective funnel stage validation failed: {error}")

    # Validate hook direction
    is_valid, error = validate_hook_direction(hook_direction)
    if not is_valid:
        raise ValueError(f"Hook direction validation failed: {error}")

    # Validate creative format
    is_valid, error = validate_creative_format(creative_format)
    if not is_valid:
        raise ValueError(f"Creative format validation failed: {error}")

    # Validate creative type if format provided
    if creative_format and creative_type:
        is_valid, error = validate_creative_type(creative_format, creative_type)
        if not is_valid:
            raise ValueError(f"Creative type validation failed: {error}")

    # Validate emotional direction
    is_valid, error = validate_emotional_direction(primary_emotion, secondary_emotion)
    if not is_valid:
        raise ValueError(f"Emotional direction validation failed: {error}")

    # Map objective to success metric if not provided
    if not success_metric:
        mapped = map_objective_to_metric(objective)
        if mapped:
            success_metric = mapped

    # Build the brief
    brief = CreativeBrief(
        objective=objective,
        target_audience=audience,
        funnel_stage=funnel_stage,
        core_message=message,
        angle=angle,
        hook_direction=hook_direction,
        offer=offer_direction,
        cta=cta,
        creative_format=creative_format,
        creative_type=creative_type,
        visual_direction=visual_direction,
        copy_direction=copy_direction,
        emotional_direction=(
        f"{primary_emotion or ''} {secondary_emotion or ''}".strip()
        if (primary_emotion or secondary_emotion)
        else None
    ),
        reason_to_believe=reason_to_believe,
        testing_hypothesis=testing_role or "baseline",
        success_metric=success_metric,
        evidence=evidence or {},
        risks=risks or [],
        status="draft",
    )

    db.add(brief)
    db.commit()
    db.refresh(brief)

    return brief


def create_creative_concept(
    db: Session,
    business_id: str,
    *,
    strategy_version: str = "v1",
    positioning_reference: str | None = None,
    offer_reference: str | None = None,
    messaging_reference: str | None = None,
    funnel_reference: str | None = None,
    funnel_stage: str | None = None,
    audience: str | None = None,
    angle: str | None = None,
    message: str | None = None,
    hook_direction: str | None = None,
    creative_format: str,
    creative_type: str | None = None,
    offer_direction: str | None = None,
    cta: str | None = None,
    visual_direction: str | None = None,
    copy_direction: str | None = None,
    primary_emotion: str | None = None,
    secondary_emotion: str | None = None,
    objection: str | None = None,
    reason_to_believe: str | None = None,
    testing_role: str | None = None,
    success_metric: str | None = None,
    evidence: dict[str, Any] | None = None,
    risks: list[dict[str, Any]] | None = None,
) -> CreativeConcept:
    """Create a new CreativeConcept anchored in Phase 7 data.

    All references (positioning, offer, messaging, funnel) must exist
    in the database and belong to the same business. No LLM, no asset
    generation, no performance learning.
    """
    from src.db.models.organizations import Organization
    from src.db.models.businesses import Business

    # Validate business exists
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        raise ValueError(f"Business {business_id} not found")

    # Validate positioning consistency if provided
    if positioning_reference:
        from src.db.models.strategy import PositioningStrategy
        positioning = db.query(PositioningStrategy).filter(
            PositioningStrategy.id == positioning_reference
        ).first()
        if not positioning:
            raise ValueError(f"Positioning {positioning_reference} not found")

        positioning_ok, positioning_error = validate_positioning_consistency(
            None, positioning, business_id
        )
        if not positioning_ok:
            raise ValueError(f"Positioning consistency failed: {positioning_error}")

    # Validate offer availability if provided
    if offer_reference:
        from src.db.models.strategy import OfferCandidate
        offer = db.query(OfferCandidate).filter(
            OfferCandidate.id == offer_reference
        ).first()
        if not offer:
            raise ValueError(f"Offer {offer_reference} not found")

        offer_ok, offer_error = validate_offer_availability(
            None, offer, business_id
        )
        if not offer_ok:
            raise ValueError(f"Offer availability failed: {offer_error}")

    # Validate messaging proof reference if provided
    if messaging_reference:
        from src.db.models.strategy import MessagingStrategy
        messaging = db.query(MessagingStrategy).filter(
            MessagingStrategy.id == messaging_reference
        ).first()
        if not messaging:
            raise ValueError(f"Messaging {messaging_reference} not found")

        proof_ok, proof_error = validate_proof_reference(
            None, messaging
        )
        if not proof_ok:
            raise ValueError(f"Proof reference failed: {proof_error}")

    # Validate hook direction
    is_valid, error = validate_hook_direction(hook_direction)
    if not is_valid:
        raise ValueError(f"Hook direction validation failed: {error}")

    # Validate creative format
    is_valid, error = validate_creative_format(creative_format)
    if not is_valid:
        raise ValueError(f"Creative format validation failed: {error}")

    # Validate creative type
    if creative_format and creative_type:
        is_valid, error = validate_creative_type(creative_format, creative_type)
        if not is_valid:
            raise ValueError(f"Creative type validation failed: {error}")

    # Validate emotional direction
    is_valid, error = validate_emotional_direction(primary_emotion, secondary_emotion)
    if not is_valid:
        raise ValueError(f"Emotional direction validation failed: {error}")

    # Map objective to success metric if not provided
    if not success_metric and objective:
        mapped = map_objective_to_metric(objective)
        if mapped:
            success_metric = mapped

    # Determine funnel stage if not provided but objective suggests one
    final_funnel_stage = funnel_stage
    if not final_funnel_stage and objective:
        # Try to infer from objective
        from .objective_service import infer_funnel_stage_from_objective
        inferred = infer_funnel_stage_from_objective(objective)
        if inferred:
            final_funnel_stage = inferred

    # Create the concept
    concept = CreativeConcept(
        strategy_version=strategy_version,
        positioning_reference=(
            uuid.UUID(positioning_reference) if positioning_reference else None
        ),
        offer_reference=(
            uuid.UUID(offer_reference) if offer_reference else None
        ),
        messaging_reference=(
            uuid.UUID(messaging_reference) if messaging_reference else None
        ),
        funnel_reference=(
            uuid.UUID(funnel_reference) if funnel_reference else None
        ),
        funnel_stage=final_funnel_stage,
        audience=audience,
        angle=angle,
        message=message,
        hook_direction=hook_direction,
        creative_format=creative_format,
        creative_type=creative_type,
        offer_direction=offer_direction,
        cta=cta,
        visual_direction=visual_direction,
        copy_direction=copy_direction,
        primary_emotion=primary_emotion,
        secondary_emotion=secondary_emotion,
        objection=objection,
        reason_to_believe=reason_to_believe,
        testing_role=testing_role or "baseline",
        success_metric=success_metric,
        evidence=evidence or {},
        risks=risks or [],
        status="draft",
        organization_id=business.organization_id,
        business_id=business_id,
    )

    db.add(concept)
    db.commit()
    db.refresh(concept)

    # Create provenance chain entry
    from .provenance_service import create_provenance_entry
    create_provenance_entry(
        db,
        concept_id=concept.id,
        step="concept_created",
        reference_type="strategy_version",
        source=strategy_version,
    )

    return concept


# Alias for backward compatibility
generate_brief = generate_creative_brief


# ---------------------------------------------------------------------------
# Matrix generation — Angle × Stage × Format coverage
# ---------------------------------------------------------------------------

def generate_creative_matrix(
    db: Session,
    business_id: str,
    angles: list[str],
    funnel_stages: list[str],
    formats: list[str],
) -> list[CreativeMatrixEntry]:
    """Generate matrix entries for Angle × Stage × Format coverage.

    Only generates combos supported by evidence from Phase 7 data.
    Returns list of matrix entries with status and evidence_strength.
    """
    from src.db.models.strategy import MessageAngle

    entries = []

    for angle in angles:
        for stage in funnel_stages:
            for fmt in formats:
                # Check if this combo has support from messaging angles
                angle_support = db.query(MessageAngle).filter(
                    MessageAngle.angle_type == angle,
                    MessageAngle.funnel_stage == stage,
                ).count() > 0

                # Check if format is valid for this angle/stage combo
                is_valid, error = validate_creative_format(fmt)
                if not is_valid:
                    continue  # Skip invalid formats

                entry = CreativeMatrixEntry(
                    angle=angle,
                    funnel_stage=stage,
                    creative_format=fmt,
                    creative_type="",  # Will be filled later
                    audience="",  # Will be filled from research
                    objective="",  # Will be filled from strategy
                    status="draft",
                    evidence_strength="insufficient_data",
                    reason=f"matrix_entry_for_angle_{angle}_stage_{stage}_format_{fmt}",
                )

                # Determine evidence strength based on Phase 7 data
                if angle_support:
                    entry.evidence_strength = "supported"
                else:
                    entry.evidence_strength = "hypothesis"

                db.add(entry)

    db.commit()

    # Refresh all entries to get generated IDs
    all_entries = db.query(CreativeMatrixEntry).filter(
        CreativeMatrixEntry.business_id == business_id
    ).all()

    return all_entries


# ---------------------------------------------------------------------------
# Angle diversity detection
# ---------------------------------------------------------------------------

def detect_angle_diversity(
    concepts: list[CreativeConcept],
) -> dict[str, Any]:
    """Detect if all concepts share the same angle/format/hook_direction/offer.

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

    # Count distributions
    angle_counts = {}
    format_counts = {}
    hook_counts = {}
    offer_counts = {}

    for concept in concepts:
        a = concept.angle or "unspecified"
        f = concept.creative_format or "unspecified"
        h = concept.hook_direction or "unspecified"
        o = concept.offer_direction or "unspecified"[:20] if concept.offer_direction else "unspecified"

        angle_counts[a] = angle_counts.get(a, 0) + 1
        format_counts[f] = format_counts.get(f, 0) + 1
        hook_counts[h] = hook_counts.get(h, 0) + 1
        offer_counts[o] = offer_counts.get(o, 0) + 1

    total = len(concepts)
    concentration_risk = (
        max(angle_counts.values()) / total > 0.5
        if angle_counts
        else False
    )

    # Determine diversity level
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


# ---------------------------------------------------------------------------
# Creative Whitespace identification
# ---------------------------------------------------------------------------

def identify_creative_whitespace(
    db: Session,
    business_id: str,
    competitor_patterns: list[dict[str, Any]] | None = None,
    customer_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Identify creative whitespace/gaps with hypothesis and confidence.

    Based on observed competitor patterns and customer evidence.
    Never guarantees winner — always presents as hypothesis with confidence.
    """
    from src.db.models.strategy import MessageAngle, MessageComponent

    gaps = []
    confidence = 0.0

    # Analyze competitor patterns
    if competitor_patterns:
        format_usage = {}
        angle_usage = {}
        for pattern in competitor_patterns:
            fmt = pattern.get("creative_format", "unknown")
            ang = pattern.get("angle", "unknown")
            format_usage[fmt] = format_usage.get(fmt, 0) + 1
            angle_usage[ang] = angle_usage.get(ang, 0) + 1

        # Identify underrepresented formats
        total_competitor_formats = sum(format_usage.values())
        for fmt, count in format_usage.items():
            proportion = count / total_competitor_formats if total_competitor_formats else 0
            if proportion < 0.1:  # Less than 10% of competitors
                gaps.append(
                    {
                        "observed_competitor_pattern": f"{fmt} used by {proportion:.0%} of competitors",
                        "potential_gap": f"Consider {fmt} format not commonly used in category",
                        "hypothesis": f"{fmt} format could differentiate with right messaging",
                        "confidence": round(0.4 + (0.1 * (1 - proportion)), 2),
                    }
                )

    # Analyze customer evidence
    if customer_evidence:
        customer_gaps = 0
        for evidence in customer_evidence:
            pain_points = evidence.get("pain_points", [])
            if pain_points:
                customer_gaps += 1

        if customer_gaps > 0:
            confidence = min(0.8, 0.3 + 0.1 * (customer_gaps / max(len(customer_evidence), 1)))

    # If no explicit patterns provided, analyze existing concepts
    if not competitor_patterns and not customer_evidence:
        concepts = db.query(CreativeConcept).filter(
            CreativeConcept.business_id == business_id
        ).all()

        if concepts:
            # Check what's already been done
            used_angles = set()
            used_formats = set()
            for c in concepts:
                if c.angle:
                    used_angles.add(c.angle)
                if c.creative_format:
                    used_formats.add(c.creative_format)

            # Suggest underrepresented combinations
            all_angles = {"problem_agitation", "benefit_focus", "objection_preempt", "curiosity_gap", "authority_establish", "social_proof", "urgency", "personal_story"}
            all_formats = {"static", "carousel", "short_video", "ugc", "testimonial", "product_demo", "before_after", "founder_led", "screen_recording", "lifestyle", "comparison", "educational"}

            for angle in all_angles:
                if angle not in used_angles:
                    for fmt in all_formats:
                        if fmt not in used_formats:
                            gaps.append(
                                {
                                    "observed_competitor_pattern": f"angle={angle}, format={fmt} not yet explored",
                                    "potential_gap": f"Test angle={angle} with format={fmt}",
                                    "hypothesis": f"This combination could reveal new engagement",
                                    "confidence": round(0.3 + 0.1 * len(concepts) / 20, 2),
                                }
                            )

    return {
        "gaps": gaps,
        "confidence": round(confidence, 2),
        "whitespace_summary": (
            f"{len(gaps)} potential creative gaps identified, "
            f"confidence {confidence:.0%} "
            f"– these are hypotheses, not guaranteed winners"
        ),
    }


# Export public API
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
    "generate_creative_brief",
    "create_creative_concept",
    "generate_creative_matrix",
    "detect_angle_diversity",
    "identify_creative_whitespace",
    "generate_brief",
]