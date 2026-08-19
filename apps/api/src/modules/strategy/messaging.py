"""Deterministic, evidence-backed messaging strategy (Phase 7B).

No LLM or creative-copy generation occurs here. Statements are copied only
from explicit business strategy fields or stored evidence; angle hooks are
directions for later creative work, not finished advertising copy.

Rules are versioned (``MESSAGING_RULES_VERSION`` / ``PRIORITIZATION_RULES_VERSION``)
and every generated strategy persists an ``input_snapshot`` so historical
outputs stay reproducible.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.db.models import (
    Business,
    MessageAngle,
    MessageComponent,
    MessagingStrategy,
    OfferCandidate,
    PositioningCandidate,
    ResearchCompetitor,
    ResearchEvidence,
    ResearchIntelligenceSnapshot,
    ResearchSource,
    StrategyDecision,
)

MESSAGING_VERSION = "messaging_v1"
MESSAGING_RULES_VERSION = "messaging_rules_v1"
PRIORITIZATION_RULES_VERSION = "messaging_prioritization_v1"

# Deterministic prioritization weights (named constants, versioned above).
PRIORITY_WEIGHTS = {
    "customer_relevance": 0.25,
    "evidence_strength": 0.2,
    "positioning_alignment": 0.15,
    "offer_alignment": 0.15,
    "proof_strength": 0.1,
    "differentiation": 0.1,
    "stage_relevance": 0.05,
}
STRENGTH_SCORE = {"strong": 1.0, "moderate": 0.6, "weak": 0.3, "unavailable": 0.0}
CLASSIFICATION_SCORE = {
    "observed": 1.0,
    "validated": 1.0,
    "supported": 0.8,
    "inferred": 0.5,
    "claimed": 0.4,
    "hypothesis": 0.2,
    "unsupported": 0.0,
}

# Objection severity thresholds (evidence count) - named, deterministic.
_OBJECTION_SEVERITY_HIGH = 3
_OBJECTION_SEVERITY_MEDIUM = 2

# Minimum competitor sample before saturation can be classified.
MIN_COMPETITOR_SAMPLE = 3
SATURATION_COMMON = 0.5
SATURATION_MODERATE = 0.25

# Unsupported-claim vocabulary (declarative, never turned silently factual).
_UNSUPPORTED_CLAIM_WORDS = (
    "best",
    "number one",
    "number 1",
    "#1",
    "top rated",
    "guaranteed results",
    "guaranteed",
    "fastest",
    "cheapest",
    "clinically proven",
    "100% effective",
    "100% guaranteed",
    "world's best",
)

# Deterministic mapping from evidence type to message component types.
_EVIDENCE_COMPONENTS = {
    "pain_point": ("problem", "pain"),
    "complaint": ("problem", "pain"),
    "desire": ("desire",),
    "benefit": ("benefit",),
    "feature": ("feature",),
    "objection": ("objection",),
    "review": ("proof",),
    "trust_signal": ("proof",),
}

# Funnel-stage mapping per message component type (stage-only attachment;
# Funnel Strategy itself is out of scope for this phase).
_STAGES = {
    "problem": "awareness",
    "pain": "awareness",
    "desire": "awareness",
    "benefit": "interest",
    "feature": "interest",
    "differentiator": "consideration",
    "promise": "consideration",
    "objection": "consideration",
    "proof": "consideration",
    "cta": "purchase",
}

# Angle generation rules: component type -> (angle type, hook direction, stage).
_ANGLE_RULES = {
    "problem": ("problem_led", "Lead with the customer's documented problem.", "awareness"),
    "pain": ("pain_led", "Lead with documented friction without exaggeration.", "awareness"),
    "desire": ("desire_led", "Lead with the documented desired outcome.", "awareness"),
    "benefit": ("benefit_led", "Lead with the supported customer benefit.", "interest"),
    "differentiator": (
        "differentiator_led",
        "Lead with the supported differentiator.",
        "consideration",
    ),
    "proof": ("proof_led", "Lead with traceable proof, not an unverified claim.", "consideration"),
    "objection": (
        "objection_led",
        "Address the documented objection with available proof.",
        "purchase",
    ),
    "cta": ("offer_led", "Use the available action at purchase intent.", "purchase"),
}

# Basic retention directions only - no Retention system is implemented here.
_RETENTION_DIRECTIONS = (
    "product_usage",
    "customer_success",
    "repeat_purchase",
    "loyalty",
)

# Competitor pattern vocabulary: keyword -> pattern name. Only patterns
# actually observed in stored competitor descriptions/metadata are reported.
_COMPETITOR_PATTERNS = (
    ("price", ("price", "pricing", "discount", "save", "deal", "cheap")),
    ("shipping", ("shipping", "delivery", "free shipping", "fast shipping")),
    ("guarantee", ("guarantee", "guaranteed", "warranty", "refund", "returns")),
    ("superlative", ("best", "#1", "number one", "top rated", "leading")),
    ("social_proof", ("reviews", "trusted", "loved by", "customers say")),
    ("offer", ("bundle", "free trial", "bonus", "gift")),
)


def _strength(count: int) -> str:
    return (
        "strong" if count >= 3 else "moderate" if count >= 2 else "weak" if count else "unavailable"
    )


def _classification(evidence: list[ResearchEvidence], fallback: str = "claimed") -> str:
    values = {row.confidence for row in evidence}
    if "hypothesis" in values:
        return "hypothesis"
    if "inferred" in values:
        return "inferred"
    if "observed" in values or "supported" in values:
        return "observed"
    if values:
        return "claimed"
    return fallback


def _claim_status(classification: str, evidence_count: int) -> str:
    if not evidence_count:
        return "unsupported" if classification in {"claimed", "validated"} else "unknown"
    if classification == "hypothesis":
        return "unknown"
    return (
        "supported"
        if evidence_count >= 2 or classification in {"observed", "validated"}
        else "partially_supported"
    )


def _severity(count: int) -> str:
    if count >= _OBJECTION_SEVERITY_HIGH:
        return "high"
    if count >= _OBJECTION_SEVERITY_MEDIUM:
        return "medium"
    if count:
        return "low"
    return "unavailable"


def _differentiator_classification(positioning: PositioningCandidate | None) -> str:
    """Map positioning classifications onto the differentiator vocabulary.

    Inference is never silently promoted to fact: observed -> observed_*,
    validated -> validated_*, claimed -> claimed_*, anything weaker -> hypothesis.
    """
    value = (positioning.classification if positioning else None) or "claimed"
    if value in {"observed", "validated"}:
        return f"{value}_differentiator"
    if value == "claimed":
        return "claimed_differentiator"
    return "hypothesis"


def _score_dimension(name: str, raw: float) -> dict[str, Any]:
    return {"dimension": name, "weight": PRIORITY_WEIGHTS[name], "raw_score": round(raw, 4)}


def _unsupported_claims(statement: str, text: str) -> list[str]:
    lowered = text.lower()
    return [word for word in _UNSUPPORTED_CLAIM_WORDS if word in lowered]


def _evidence_ref(evidence: ResearchEvidence, source: ResearchSource | None) -> dict[str, Any]:
    return {
        "evidence_id": str(evidence.id),
        "source_id": str(evidence.source_id),
        "snapshot_id": str(evidence.snapshot_id) if evidence.snapshot_id else None,
        "source_title": source.title if source else None,
        "statement": evidence.statement,
        "data_source": evidence.evidence_type,
    }


async def _latest(
    session: AsyncSession, model: Any, business: Business, order_column: str = "created_at"
) -> Any | None:
    column = getattr(model, order_column)
    return await session.scalar(
        select(model)
        .where(model.organization_id == business.organization_id, model.business_id == business.id)
        .order_by(desc(column))
        .limit(1)
    )


async def _row(session: AsyncSession, model: Any, business: Business, row_id: uuid.UUID) -> Any:
    row = await session.scalar(
        select(model).where(
            model.id == row_id,
            model.organization_id == business.organization_id,
            model.business_id == business.id,
        )
    )
    if row is None:
        raise NotFoundError("Messaging input not found")
    return row


def _competitor_analysis(
    competitors: list[ResearchCompetitor], customer_evidence: list[ResearchEvidence]
) -> dict[str, Any]:
    """Deterministic pattern/saturation/whitespace analysis from stored data.

    Only patterns that literally appear in stored competitor descriptions or
    metadata are counted; nothing is scraped or fetched at generation time.
    """
    text_by_id: list[tuple[uuid.UUID, str]] = []
    for competitor in competitors:
        chunks = [competitor.description or ""]
        for value in (competitor.metadata_json or {}).values():
            if isinstance(value, str):
                chunks.append(value)
            elif isinstance(value, list):
                chunks.extend(str(item) for item in value if isinstance(item, str))
        text_by_id.append((competitor.id, " ".join(chunks).lower()))

    sample = len(text_by_id)
    patterns: list[dict[str, Any]] = []
    for pattern, keywords in _COMPETITOR_PATTERNS:
        matches = [row_id for row_id, text in text_by_id if any(k in text for k in keywords)]
        frequency = len(matches)
        if not frequency:
            continue
        if sample < MIN_COMPETITOR_SAMPLE:
            saturation = "unknown"
        elif frequency / sample >= SATURATION_COMMON:
            saturation = "common"
        elif frequency / sample >= SATURATION_MODERATE:
            saturation = "moderately_common"
        else:
            saturation = "rare"
        patterns.append(
            {
                "pattern": pattern,
                "frequency": frequency,
                "saturation": saturation,
                "competitor_ids": [str(row_id) for row_id in matches],
            }
        )

    whitespace: list[dict[str, Any]] = []
    if patterns:
        covered = {pattern["pattern"] for pattern in patterns}
        for row in customer_evidence:
            if row.evidence_type not in {"pain_point", "complaint", "desire"}:
                continue
            # A customer theme that appears in no competitor pattern is a
            # *potential* whitespace - never a promise of better performance.
            if not any(
                keyword in row.statement.lower()
                for pattern, keywords in _COMPETITOR_PATTERNS
                for keyword in keywords
                if pattern in covered
            ):
                whitespace.append(
                    {
                        "theme": row.statement,
                        "evidence_id": str(row.id),
                        "classification": "hypothesis",
                    }
                )

    return {
        "competitor_sample_size": sample,
        "patterns": patterns,
        "potential_messaging_whitespace": whitespace[:5],
        "whitespace_claim": "no_performance_claim",
    }


async def _inputs(session: AsyncSession, business: Business, payload: Any) -> dict[str, Any]:
    positioning = (
        await _row(session, PositioningCandidate, business, payload.positioning_candidate_id)
        if payload.positioning_candidate_id
        else await _latest(session, PositioningCandidate, business)
    )
    offer = (
        await _row(session, OfferCandidate, business, payload.offer_candidate_id)
        if payload.offer_candidate_id
        else await _latest(session, OfferCandidate, business)
    )
    decision = (
        await _row(session, StrategyDecision, business, payload.strategy_decision_id)
        if payload.strategy_decision_id
        else await _latest(session, StrategyDecision, business)
    )
    evidence = list(
        await session.scalars(
            select(ResearchEvidence).where(
                ResearchEvidence.organization_id == business.organization_id,
                ResearchEvidence.business_id == business.id,
            )
        )
    )
    sources = {
        source.id: source
        for source in await session.scalars(
            select(ResearchSource).where(
                ResearchSource.organization_id == business.organization_id,
                ResearchSource.business_id == business.id,
            )
        )
    }
    competitors = list(
        await session.scalars(
            select(ResearchCompetitor).where(
                ResearchCompetitor.organization_id == business.organization_id,
                ResearchCompetitor.business_id == business.id,
            )
        )
    )
    research = await _latest(
        session, ResearchIntelligenceSnapshot, business, order_column="generated_at"
    )
    return {
        "positioning": positioning,
        "offer": offer,
        "decision": decision,
        "evidence": evidence,
        "sources": sources,
        "competitors": competitors,
        "research": research,
    }


async def generate(session: AsyncSession, business: Business, payload: Any) -> MessagingStrategy:
    inputs = await _inputs(session, business, payload)
    positioning: PositioningCandidate | None = inputs["positioning"]
    offer: OfferCandidate | None = inputs["offer"]
    evidence: list[ResearchEvidence] = inputs["evidence"]
    sources: dict[uuid.UUID, ResearchSource] = inputs["sources"]
    grouped: dict[str, list[ResearchEvidence]] = defaultdict(list)
    for row in evidence:
        grouped[row.evidence_type].append(row)
    version = (
        int(
            await session.scalar(
                select(func.max(MessagingStrategy.version)).where(
                    MessagingStrategy.business_id == business.id
                )
            )
            or 0
        )
        + 1
    )
    components: list[dict[str, Any]] = []
    for evidence_type, types in _EVIDENCE_COMPONENTS.items():
        for row in grouped.get(evidence_type, []):
            refs = [_evidence_ref(row, sources.get(row.source_id))]
            classification = _classification([row])
            for component_type in types:
                details: dict[str, Any] = {"evidence_count": 1}
                if component_type == "objection":
                    details["severity"] = _severity(1)
                    details["response_available"] = False
                if component_type == "pain":
                    details["pain_kind"] = "friction"
                components.append(
                    {
                        "component_type": component_type,
                        "statement": row.statement,
                        "classification": classification,
                        "strength": _strength(1),
                        "claim_status": _claim_status(classification, 1),
                        "funnel_stage": _STAGES[component_type],
                        "details": details,
                        "evidence_refs": refs,
                        "provenance": refs,
                    }
                )

    positioning_refs = list(positioning.provenance or []) if positioning else []
    if positioning:
        for component_type, statement in (
            ("differentiator", positioning.differentiator),
            ("promise", positioning.promise),
        ):
            if not statement:
                continue
            classification = (
                _differentiator_classification(positioning)
                if component_type == "differentiator"
                else positioning.classification
            )
            components.append(
                {
                    "component_type": component_type,
                    "statement": statement,
                    "classification": classification,
                    "strength": positioning.strength,
                    "claim_status": _claim_status(
                        "observed"
                        if classification.endswith("_differentiator")
                        else positioning.classification,  # noqa: E501
                        len(positioning_refs),
                    ),
                    "funnel_stage": _STAGES[component_type],
                    "details": {"source": "positioning_candidate"},
                    "evidence_refs": positioning_refs,
                    "provenance": positioning_refs,
                }
            )
        for proof in positioning.proof_points:
            components.append(
                {
                    "component_type": "proof",
                    "statement": proof,
                    "classification": "claimed",
                    "strength": positioning.strength,
                    "claim_status": _claim_status("claimed", len(positioning_refs)),
                    "funnel_stage": "consideration",
                    "details": {"source": "positioning_candidate"},
                    "evidence_refs": positioning_refs,
                    "provenance": positioning_refs,
                }
            )
    offer_refs = list(offer.provenance or []) if offer else []
    if offer:
        for proof in (offer.components or {}).get("proof", []):
            components.append(
                {
                    "component_type": "proof",
                    "statement": proof,
                    "classification": "claimed",
                    "strength": offer.strength,
                    "claim_status": _claim_status("claimed", len(offer_refs)),
                    "funnel_stage": "purchase",
                    "details": {"source": "offer_candidate"},
                    "evidence_refs": offer_refs,
                    "provenance": offer_refs,
                }
            )

    # CTA is only emitted when an actual available action exists (the offer
    # references a real product). No booking/trial CTAs are guessed.
    cta_type = "view_product" if offer and offer.product_id else None
    cta_validation = {
        "cta_type": cta_type,
        "available": cta_type is not None,
        "basis": "offer product reference" if cta_type else "no available action",
    }
    if cta_type:
        components.append(
            {
                "component_type": "cta",
                "statement": "View the available product.",
                "classification": "validated",
                "strength": "strong",
                "claim_status": "supported",
                "funnel_stage": "purchase",
                "details": {"validation": cta_validation},
                "evidence_refs": offer_refs,
                "provenance": [{"product_id": str(offer.product_id), "source": "offer_candidate"}],
            }
        )

    # Objection responses reference the strongest available proof statement -
    # never an invented guarantee ("100% guaranteed" is only used if the
    # business actually supplies it as stored proof).
    proof_rank = {"strong": 0, "moderate": 1, "weak": 2, "unavailable": 3}
    proofs = sorted(
        (item for item in components if item["component_type"] == "proof"),
        key=lambda item: proof_rank.get(item["strength"], 3),
    )
    strongest_proof = proofs[0]["statement"] if proofs else None
    strongest_proof_refs = proofs[0]["evidence_refs"] if proofs else []
    for item in components:
        if item["component_type"] != "objection":
            continue
        item["details"]["response"] = strongest_proof
        item["details"]["response_available"] = strongest_proof is not None
        item["details"]["response_provenance"] = strongest_proof_refs

    # Deterministic claim + quality evaluation per component.
    quality_flags: list[dict[str, Any]] = []
    for item in components:
        flagged = _unsupported_claims(item["statement"], item["statement"])
        item["details"]["unsupported_claims"] = flagged
        if flagged:
            quality_flags.append(
                {
                    "component_type": item["component_type"],
                    "statement": item["statement"],
                    "claims": flagged,
                    "claim_status": item["claim_status"],
                }
            )

    # Prioritization scoring (named constants, versioned rules).
    prioritization: list[dict[str, Any]] = []
    for index, item in enumerate(components):
        dimensions: list[dict[str, Any]] = []
        dimensions.append(
            _score_dimension("evidence_strength", STRENGTH_SCORE.get(item["strength"], 0.0))
        )
        classification = item["classification"]
        if classification.endswith("_differentiator"):
            classification = "validated"
        dimensions.append(
            _score_dimension("customer_relevance", CLASSIFICATION_SCORE.get(classification, 0.2))
        )
        positioning_alignment = 1.0 if "positioning_candidate" in str(item["details"]) else 0.0
        offer_alignment = 1.0 if "offer_candidate" in str(item["details"]) else 0.0
        dimensions.append(_score_dimension("positioning_alignment", positioning_alignment))
        dimensions.append(_score_dimension("offer_alignment", offer_alignment))
        dimensions.append(
            _score_dimension(
                "differentiation",
                1.0 if item["component_type"] == "differentiator" else 0.0,
            )
        )
        dimensions.append(
            _score_dimension(
                "proof_strength",
                STRENGTH_SCORE.get(item["strength"], 0.0)
                if item["component_type"] == "proof"
                else 0.0,
            )
        )
        dimensions.append(
            _score_dimension(
                "stage_relevance",
                1.0 if item["funnel_stage"] else 0.0,
            )
        )
        score = round(
            sum(dimension["weight"] * dimension["raw_score"] for dimension in dimensions),
            4,
        )
        item["details"]["priority_score"] = score
        prioritization.append(
            {
                "rank": index,
                "component_type": item["component_type"],
                "statement": item["statement"],
                "score": score,
                "dimensions": dimensions,
            }
        )
    prioritization.sort(key=lambda row: row["score"], reverse=True)
    for rank, row in enumerate(prioritization, start=1):
        row["rank"] = rank

    core = {
        "who": positioning.target_customer if positioning else None,
        "problem": positioning.problem if positioning else None,
        "desired_outcome": positioning.promise if positioning else None,
        "solution": positioning.solution if positioning else None,
        "differentiator": positioning.differentiator if positioning else None,
        "promise": positioning.promise if positioning else None,
        "proof_available": any(item["component_type"] == "proof" for item in components),
        "cta": cta_type,
    }
    missing = [name for name in ("who", "problem", "solution", "promise") if not core[name]]
    status = "insufficient_data" if missing else "draft"
    snapshot = {
        "messaging_rules_version": MESSAGING_RULES_VERSION,
        "prioritization_rules_version": PRIORITIZATION_RULES_VERSION,
        "positioning_candidate_id": str(positioning.id) if positioning else None,
        "offer_candidate_id": str(offer.id) if offer else None,
        "strategy_decision_id": str(inputs["decision"].id) if inputs["decision"] else None,
        "research_intelligence_snapshot_id": str(inputs["research"].id)
        if inputs["research"]
        else None,
        "research_intelligence_version": inputs["research"].intelligence_version
        if inputs["research"]
        else None,
        "evidence_ids": [str(row.id) for row in evidence],
    }
    strategy = MessagingStrategy(
        organization_id=business.organization_id,
        business_id=business.id,
        version=version,
        messaging_version=MESSAGING_VERSION,
        status=status,
        positioning_candidate_id=positioning.id if positioning else None,
        offer_candidate_id=offer.id if offer else None,
        strategy_decision_id=inputs["decision"].id if inputs["decision"] else None,
        input_snapshot=snapshot,
        core_message=core,
        quality={
            "rules_version": MESSAGING_RULES_VERSION,
            "prioritization_rules_version": PRIORITIZATION_RULES_VERSION,
            "missing_components": missing,
            "performance_attribution": "no_performance_attribution",
            "cta_validation": cta_validation,
            "unsupported_claims": quality_flags,
            "prioritization": prioritization,
            "retention_directions": [
                {
                    "direction": direction,
                    "funnel_stage": "retention",
                    "classification": "hypothesis",
                    "status": "no_performance_attribution",
                }
                for direction in _RETENTION_DIRECTIONS
            ],
            "competitor_messaging": _competitor_analysis(inputs["competitors"], evidence),
        },
    )
    session.add(strategy)
    await session.flush()
    component_rows = [
        MessageComponent(
            organization_id=business.organization_id,
            business_id=business.id,
            messaging_strategy_id=strategy.id,
            status="available",
            **item,
        )
        for item in components
    ]
    session.add_all(component_rows)
    for item in component_rows:
        rule = _ANGLE_RULES.get(item.component_type)
        if not rule:
            continue
        angle_type, hook_direction, funnel_stage = rule
        session.add(
            MessageAngle(
                organization_id=business.organization_id,
                business_id=business.id,
                messaging_strategy_id=strategy.id,
                name=f"{item.component_type.replace('_', ' ').title()} angle",
                angle_type=angle_type,
                core_message=item.statement,
                hook_direction=hook_direction,
                supporting_points=[],
                cta_type=cta_type if funnel_stage == "purchase" else None,
                funnel_stage=funnel_stage,
                strength=item.strength,
                status="no_performance_attribution",
                evidence_refs=item.evidence_refs,
            )
        )
    await session.commit()
    await session.refresh(strategy)
    return strategy


async def get_strategy(
    session: AsyncSession, business: Business, strategy_id: uuid.UUID
) -> MessagingStrategy:
    return await _row(session, MessagingStrategy, business, strategy_id)


async def latest(session: AsyncSession, business: Business) -> MessagingStrategy | None:
    return await _latest(session, MessagingStrategy, business)


async def components(session: AsyncSession, strategy: MessagingStrategy) -> list[MessageComponent]:
    return list(
        await session.scalars(
            select(MessageComponent).where(MessageComponent.messaging_strategy_id == strategy.id)
        )
    )


async def angles(session: AsyncSession, strategy: MessagingStrategy) -> list[MessageAngle]:
    return list(
        await session.scalars(
            select(MessageAngle).where(MessageAngle.messaging_strategy_id == strategy.id)
        )
    )


async def versions(session: AsyncSession, business: Business) -> list[MessagingStrategy]:
    return list(
        await session.scalars(
            select(MessagingStrategy)
            .where(
                MessagingStrategy.organization_id == business.organization_id,
                MessagingStrategy.business_id == business.id,
            )
            .order_by(desc(MessagingStrategy.version))
        )
    )
