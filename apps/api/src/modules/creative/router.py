"""Creative Intelligence API endpoints (Phase 8A).

Follows Strategy API conventions:
- All endpoints under /api/v1/strategy/creative
- Tenant/business scoped
- POST generation requires write permission
- GET endpoints read-only for tenant scoping
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.core.dependencies import get_db, get_current_active_user
from src.db.models.organizations import Organization
from src.db.models.businesses import Business
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
    FunnelStrategy,
    MessageAngle,
    MessageComponent,
)
from src.modules.creative.service import (
    generate_creative_brief,
    create_creative_concept,
    generate_creative_matrix,
    detect_angle_diversity,
    identify_creative_whitespace,
    validate_objective_funnel_stage,
    validate_hook_direction,
    validate_creative_format,
    validate_creative_type,
    validate_emotional_direction,
    map_objective_to_metric,
    detect_angle_diversity,
    identify_creative_whitespace,
)

router = APIRouter(prefix="/v1/strategy/creative", tags=["creative-intelligence"])


# ----- Helpers -----

def _get_business(db: Session, business_id: str) -> Business:
    """Get business and verify tenant scoping."""
    biz = db.query(Business).filter(Business.id == business_id).first()
    if not biz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found",
        )
    return biz


def _verify_organization_access(
    db: Session, organization_id: str, user_org: str
) -> None:
    """Verify user belongs to the same organization."""
    if str(biz.organization_id) != organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant access denied",
        )


# ----- Creative Concept endpoints -----

@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_concept(
    business_id: str,
    *,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
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
):
    """Create a new CreativeConcept anchored in Phase 7 data.

    All references (positioning, offer, messaging, funnel) must exist
    in the database and belong to the same business. No LLM, no asset
    generation, no performance learning.
    """
    biz = _get_business(db, business_id)

    # Validate positioning consistency if provided
    if positioning_reference:
        from src.db.models.strategy import PositioningStrategy
        positioning = db.query(PositioningStrategy).filter(
            PositioningStrategy.id == positioning_reference
        ).first()
        if not positioning:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Positioning strategy not found",
            )
        if positioning.organization_id != biz.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cross-tenant positioning reference",
            )

    # Validate offer availability if provided
    if offer_reference:
        from src.db.models.strategy import OfferCandidate
        offer = db.query(OfferCandidate).filter(
            OfferCandidate.id == offer_reference
        ).first()
        if not offer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Offer candidate not found",
            )
        if offer.organization_id != biz.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cross-tenant offer reference",
            )
        if offer.status != "available":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Offer not available: status={offer.status}",
            )

    # Validate messaging proof reference if provided
    if messaging_reference:
        from src.db.models.strategy import MessagingStrategy
        messaging = db.query(MessagingStrategy).filter(
            MessagingStrategy.id == messaging_reference
        ).first()
        if not messaging:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Messaging strategy not found",
            )
        if messaging.organization_id != biz.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cross-tenant messaging reference",
            )

    # Create the concept via service layer
    try:
        concept = create_creative_concept(
            db=db,
            business_id=business_id,
            strategy_version=strategy_version,
            positioning_reference=positioning_reference,
            offer_reference=offer_reference,
            messaging_reference=messaging_reference,
            funnel_reference=funnel_reference,
            funnel_stage=funnel_stage,
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
            testing_role=testing_role,
            success_metric=success_metric,
            evidence=evidence or {},
            risks=risks or [],
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return {
        "id": str(concept.id),
        "organization_id": str(concept.organization_id),
        "business_id": str(concept.business_id),
        "strategy_version": concept.strategy_version,
        "positioning_reference": str(concept.positioning_reference) if concept.positioning_reference else None,
        "offer_reference": str(concept.offer_reference) if concept.offer_reference else None,
        "messaging_reference": str(concept.messaging_reference) if concept.messaging_reference else None,
        "funnel_reference": str(concept.funnel_reference) if concept.funnel_reference else None,
        "funnel_stage": concept.funnel_stage,
        "audience": concept.audience,
        "angle": concept.angle,
        "message": concept.message,
        "hook_direction": concept.hook_direction,
        "creative_format": concept.creative_format,
        "creative_type": concept.creative_type,
        "offer_direction": concept.offer_direction,
        "cta": concept.cta,
        "visual_direction": concept.visual_direction,
        "copy_direction": concept.copy_direction,
        "primary_emotion": concept.primary_emotion,
        "secondary_emotion": concept.secondary_emotion,
        "objection": concept.objection,
        "reason_to_believe": concept.reason_to_believe,
        "testing_role": concept.testing_role,
        "success_metric": concept.success_metric,
        "evidence": concept.evidence,
        "risks": concept.risks,
        "status": concept.status,
        "created_at": concept.created_at.isoformat(),
    }


@router.get("/", response_model=dict)
def list_concepts(
    business_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    angle: str | None = None,
    format: str | None = None,
    stage: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List creative concepts for a business, with optional filtering.

    All filters are tenant-scoped. Cross-tenant references return 404.
    """
    biz = _get_business(db, business_id)

    query = db.query(CreativeConcept).filter(
        CreativeConcept.business_id == business_id
    )

    # Apply filters
    if angle:
        query = query.filter(CreativeConcept.angle == angle)
    if format:
        query = query.filter(CreativeConcept.creative_format == format)
    if stage:
        query = query.filter(CreativeConcept.funnel_stage == stage)
    if status:
        query = query.filter(CreativeConcept.status == status)

    total = query.count()
    concepts = query.offset(offset).limit(limit).all()

    return {
        "concepts": [
            {
                "id": str(c.id),
                "strategy_version": c.strategy_version,
                "funnel_stage": c.funnel_stage,
                "angle": c.angle,
                "creative_format": c.creative_format,
                "creative_type": c.creative_type,
                "status": c.status,
                "created_at": c.created_at.isoformat(),
            }
            for c in concepts
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{concept_id}", response_model=dict)
def get_concept(
    business_id: str,
    concept_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Get a single CreativeConcept by ID.

    Cross-tenant references return 404. Never exposes internal DB IDs
    to untrusted clients.
    """
    biz = _get_business(db, business_id)

    concept = (
        db.query(CreativeConcept)
        .filter(
            CreativeConcept.id == concept_id,
            CreativeConcept.business_id == business_id,
        )
        .first()
    )

    if not concept:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creative concept not found",
        )

    return {
        "id": str(concept.id),
        "organization_id": str(concept.organization_id),
        "business_id": str(concept.business_id),
        "strategy_version": concept.strategy_version,
        "positioning_reference": (
            str(concept.positioning_reference) if concept.positioning_reference else None
        ),
        "offer_reference": (
            str(concept.offer_reference) if concept.offer_reference else None
        ),
        "messaging_reference": (
            str(concept.messaging_reference) if concept.messaging_reference else None
        ),
        "funnel_reference": (
            str(concept.funnel_reference) if concept.funnel_reference else None
        ),
        "funnel_stage": concept.funnel_stage,
        "audience": concept.audience,
        "angle": concept.angle,
        "message": concept.message,
        "hook_direction": concept.hook_direction,
        "creative_format": concept.creative_format,
        "creative_type": concept.creative_type,
        "offer_direction": concept.offer_direction,
        "cta": concept.cta,
        "visual_direction": concept.visual_direction,
        "copy_direction": concept.copy_direction,
        "primary_emotion": concept.primary_emotion,
        "secondary_emotion": concept.secondary_emotion,
        "objection": concept.objection,
        "reason_to_believe": concept.reason_to_believe,
        "testing_role": concept.testing_role,
        "success_metric": concept.success_metric,
        "evidence": concept.evidence,
        "risks": concept.risks,
        "status": concept.status,
        "created_at": concept.created_at.isoformat(),
        "updated_at": concept.updated_at.isoformat(),
    }


# ----- Creative Brief endpoints -----

@router.post("/brief/", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_brief(
    business_id: str,
    *,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    objective: str,
    target_audience: str | None = None,
    funnel_stage: str | None = None,
    customer_problem: str | None = None,
    customer_desire: str | None = None,
    core_message: str | None = None,
    angle: str | None = None,
    hook_direction: str | None = None,
    offer: str | None = None,
    proof: list[dict[str, Any]] | None = None,
    objection: str | None = None,
    cta: str | None = None,
    creative_format: str | None = None,
    visual_direction: str | None = None,
    copy_direction: str | None = None,
    emotional_direction: str | None = None,
    reason_to_believe: str | None = None,
    testing_hypothesis: str | None = None,
    success_metric: str | None = None,
    evidence: dict[str, Any] | None = None,
    risks: list[dict[str, Any]] | None = None,
):
    """Generate a CreativeBrief from Phase 7 strategy data.

    Consumes positioning/offer/strategy/funnel data to produce a structured
    brief. All fields reference existing Phase 7 data; never fabricated.
    """
    biz = _get_business(db, business_id)

    # Validate objective/funnel stage consistency
    is_valid, error = validate_objective_funnel_stage(objective, funnel_stage)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Objective funnel stage mismatch: {error}",
        )

    # Validate hook direction
    is_valid, error = validate_hook_direction(hook_direction)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid hook direction: {error}",
        )

    # Validate creative format if provided
    if creative_format:
        is_valid, error = validate_creative_format(creative_format)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid creative format: {error}",
            )

    # Validate emotional direction
    is_valid, error = validate_emotional_direction(
        emotional_direction.split(" ") if emotional_direction else None, None
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid emotional direction: {error}",
        )

    # Map objective to success metric if not provided
    final_success_metric = success_metric
    if not final_success_metric:
        mapped = map_objective_to_metric(objective)
        if mapped:
            final_success_metric = mapped

    # Generate brief via service layer
    try:
        brief = generate_creative_brief(
            db=db,
            business_id=business_id,
            objective=objective,
            target_audience=target_audience,
            funnel_stage=funnel_stage,
            customer_problem=customer_problem,
            customer_desire=customer_desire,
            core_message=core_message,
            angle=angle,
            hook_direction=hook_direction,
            offer=offer,
            proof=proof or [],
            objection=objection,
            cta=cta,
            creative_format=creative_format,
            visual_direction=visual_direction,
            copy_direction=copy_direction,
            emotional_direction=emotional_direction,
            reason_to_believe=reason_to_believe,
            testing_hypothesis=testing_hypothesis or "test hypothesis",
            success_metric=final_success_metric,
            evidence=evidence or {},
            risks=risks or [],
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return {
        "id": str(brief.id),
        "organization_id": str(brief.organization_id),
        "business_id": str(brief.business_id),
        "objective": brief.objective,
        "target_audience": brief.target_audience,
        "funnel_stage": brief.funnel_stage,
        "customer_problem": brief.customer_problem,
        "customer_desire": brief.customer_desire,
        "core_message": brief.core_message,
        "angle": brief.angle,
        "hook_direction": brief.hook_direction,
        "offer": brief.offer,
        "proof": brief.proof,
        "objection": brief.objection,
        "cta": brief.cta,
        "creative_format": brief.creative_format,
        "visual_direction": brief.visual_direction,
        "copy_direction": brief.copy_direction,
        "emotional_direction": brief.emotional_direction,
        "reason_to_believe": brief.reason_to_believe,
        "testing_hypothesis": brief.testing_hypothesis,
        "success_metric": brief.success_metric,
        "evidence": brief.evidence,
        "risks": brief.risks,
        "status": brief.status,
        "created_at": brief.created_at.isoformat(),
    }


@router.get("/brief/", response_model=dict)
def list_briefs(
    business_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    objective: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List creative briefs for a business, with optional filtering."""
    biz = _get_business(db, business_id)

    query = db.query(CreativeBrief).filter(
        CreativeBrief.business_id == business_id
    )

    if objective:
        query = query.filter(CreativeBrief.objective == objective)
    if status:
        query = query.filter(CreativeBrief.status == status)

    total = query.count()
    briefs = query.offset(offset).limit(limit).all()

    return {
        "briefs": [
            {
                "id": str(b.id),
                "objective": b.objective,
                "funnel_stage": b.funnel_stage,
                "status": b.status,
                "created_at": b.created_at.isoformat(),
            }
            for b in briefs
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/brief/{brief_id}", response_model=dict)
def get_brief(
    business_id: str,
    brief_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Get a single CreativeBrief by ID."""
    biz = _get_business(db, business_id)

    brief = (
        db.query(CreativeBrief)
        .filter(
            CreativeBrief.id == brief_id,
            CreativeBrief.business_id == business_id,
        )
        .first()
    )

    if not brief:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creative brief not found",
        )

    return {
        "id": str(brief.id),
        "organization_id": str(brief.organization_id),
        "business_id": str(brief.business_id),
        "objective": brief.objective,
        "target_audience": brief.target_audience,
        "funnel_stage": brief.funnel_stage,
        "customer_problem": brief.customer_problem,
        "customer_desire": brief.customer_desire,
        "core_message": brief.core_message,
        "angle": brief.angle,
        "hook_direction": brief.hook_direction,
        "offer": brief.offer,
        "proof": brief.proof,
        "objection": brief.objection,
        "cta": brief.cta,
        "creative_format": brief.creative_format,
        "visual_direction": brief.visual_direction,
        "copy_direction": brief.copy_direction,
        "emotional_direction": brief.emotional_direction,
        "reason_to_believe": brief.reason_to_believe,
        "testing_hypothesis": brief.testing_hypothesis,
        "success_metric": brief.success_metric,
        "evidence": brief.evidence,
        "risks": brief.risks,
        "status": brief.status,
        "created_at": brief.created_at.isoformat(),
        "updated_at": brief.updated_at.isoformat(),
    }


# ----- Creative Matrix endpoints -----

@router.post("/matrix/", response_model=dict)
def create_matrix(
    business_id: str,
    *,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    angles: list[str],
    funnel_stages: list[str],
    formats: list[str],
):
    """Generate matrix entries for Angle × Stage × Format coverage.

    Only generates combos supported by evidence from Phase 7 data.
    """
    biz = _get_business(db, business_id)

    entries = generate_creative_matrix(
        db=db,
        business_id=business_id,
        angles=angles,
        funnel_stages=funnel_stages,
        formats=formats,
    )

    return {
        "matrix_entries": [
            {
                "id": str(e.id),
                "angle": e.angle,
                "funnel_stage": e.funnel_stage,
                "creative_format": e.creative_format,
                "creative_type": e.creative_type,
                "objective": e.objective,
                "status": e.status,
                "evidence_strength": e.evidence_strength,
                "reason": e.reason,
                "created_at": e.created_at.isoformat(),
            }
            for e in entries
        ],
        "total": len(entries),
    }


@router.get("/matrix/diversity/", response_model=dict)
def get_angle_diversity(
    business_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    concepts: list[str] | None = None,
):
    """Detect angle diversity across existing concepts.

    Flags creative_concentration_risk if all concepts share same
    angle/format/hook_direction/offer.
    """
    biz = _get_business(db, business_id)

    # Fetch concepts if not provided
    if not concepts:
        concepts_db = (
            db.query(CreativeConcept)
            .filter(CreativeConcept.business_id == business_id)
            .all()
        )
        concepts = [c.angle for c in concepts_db if c.angle]

    diversity = detect_angle_diversity(
        [{"angle": a, "format": "", "hook_direction": "", "offer_direction": ""} for a in concepts]
    )

    # Enhance with actual concept data
    if concepts_db := (
        db.query(CreativeConcept)
        .filter(CreativeConcept.business_id == business_id)
        .all()
    ):
        diversity["concentration_risk"] = any(
            c.angle in concepts for c in concepts_db
        )

    return {"angle_diversity": diversity}


# ----- Creative Whitespace endpoints -----

@router.post("/whitespace/", response_model=dict)
def identify_whitespace(
    business_id: str,
    *,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    competitor_patterns: list[dict[str, Any]] | None = None,
    customer_evidence: list[dict[str, Any]] | None = None,
):
    """Identify creative whitespace/gaps with hypothesis and confidence.

    Based on observed competitor patterns and customer evidence.
    Never guarantees winner — always presents as hypothesis with confidence.
    """
    biz = _get_business(db, business_id)

    whitespace = identify_creative_whitespace(
        db=db,
        business_id=business_id,
        competitor_patterns=competitor_patterns,
        customer_evidence=customer_evidence,
    )

    return {"whitespace": whitespace}


# ----- Provenance endpoints -----

@router.post("/provenance/", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_provenance(
    business_id: str,
    *,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    creative_id: str | None = None,
    step: str,
    reference_id: str | None = None,
    reference_type: str | None = None,
    source: str | None = None,
):
    """Create a provenance chain entry for a creative concept.

    Creative → Brief → Angle/Message → Funnel Stage → Positioning/Offer →
    Research Evidence → Source/Snapshot. For every important claim.
    """
    biz = _get_business(db, business_id)

    # Validate creative exists and belongs to business
    if creative_id:
        concept = (
            db.query(CreativeConcept)
            .filter(
                CreativeConcept.id == creative_id,
                CreativeConcept.business_id == business_id,
            )
            .first()
        )
        if not concept:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Creative concept not found",
            )
    else:
        # Create provenance without specific creative link
        concept = None

    from src.db.models.creative import CreativeProvenance as CP

    provenance = CP(
        organization_id=biz.organization_id,
        business_id=biz.id,
        step=step,
        reference_id=(
            UUID(reference_id) if reference_id else None
        ),
        reference_type=reference_type,
        source=source,
    )

    db.add(provenance)
    db.commit()
    db.refresh(provenance)

    return {
        "id": str(provenance.id),
        "step": provenance.step,
        "reference_id": str(provenance.reference_id) if provenance.reference_id else None,
        "reference_type": provenance.reference_type,
        "source": provenance.source,
        "created_at": provenance.created_at.isoformat(),
    }


@router.get("/provenance/{creative_id}", response_model=dict)
def get_provenance(
    business_id: str,
    creative_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Get provenance chain for a creative concept.

    Creative → Brief → Angle/Message → Funnel Stage → Positioning/Offer →
    Research Evidence → Source/Snapshot. No hidden sources.
    """
    biz = _get_business(db, business_id)

    provenance_entries = (
        db.query(CreativeProvenance)
        .filter(CreativeProvenance.business_id == business_id)
        .filter(
            CreativeProvenance.step.contains(creative_id)
            | CreativeProvenance.reference_id == UUID(creative_id)
        )
        .all()
    )

    return {
        "provenance": [
            {
                "id": str(p.id),
                "step": p.step,
                "reference_id": str(p.reference_id) if p.reference_id else None,
                "reference_type": p.reference_type,
                "source": p.source,
                "created_at": p.created_at.isoformat(),
            }
            for p in provenance_entries
        ]
    }


# ----- Health check -----

@router.get("/health/", response_model=dict)
def health_check():
    """Creative intelligence service health check."""
    return {
        "status": "healthy",
        "version": "creative_intelligence_v1",
        "phase": "8A_foundational",
        "deterministic": True,
        "llm_free": True,
        "asset_generation": False,
        "performance_learning": False,
    }


# Register UUID helper for FastAPI path parameters
from uuid import UUID

# Override the router's path parameter parsing to accept string UUIDs
# and convert them internally


def _convert_uuid(value: str) -> UUID:
    """Convert string UUID to UUID object."""
    return UUID(value)


# Apply UUID conversion to path parameters
# FastAPI already handles this, but we ensure consistency