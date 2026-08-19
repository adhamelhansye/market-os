"""Deterministic strategy services for Phase 7A.

Scoring rules are intentionally explicit:

* positioning score = 0.40 evidence coverage + 0.20 customer relevance
  + 0.20 differentiation evidence + 0.20 business capability evidence;
* offer score = 0.50 economic viability + 0.25 evidence strength
  + 0.25 inventory feasibility.

Each dimension is in [0, 1]. A recommendation is withheld when the score is
below 0.60 or critical inputs are unavailable. No service here calls an LLM
or mutates a product, promotion, budget, campaign, or provider account.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.db.models import (
    Bundle,
    BundleItem,
    Business,
    Discount,
    InventorySnapshot,
    OfferCandidate,
    OfferStrategy,
    PositioningCandidate,
    PositioningStrategy,
    Product,
    ResearchEvidence,
    ResearchFinding,
    ResearchIntelligenceSnapshot,
    ResearchSource,
    ResearchSourceSnapshot,
    ShippingRule,
    StrategySnapshot,
    research_finding_evidence,
)
from src.modules.economics.calculator import (
    ZERO,
    calculate_bundle_economics,
    calculate_product_economics,
)
from src.modules.economics.service import (
    resolve_active_cost,
    resolve_active_price,
    resolve_shipping_rule,
)
from src.modules.research.intelligence import INTELLIGENCE_VERSION, ResearchIntelligenceStore

STRATEGY_VERSION = "strategy_v1"
POSITIONING_VERSION = "positioning_v1"
OFFER_VERSION = "offer_v1"


def _safe(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_safe(v) for v in value]
    return value


def _classification(rows: list[ResearchEvidence], explicit: str | None) -> str:
    if explicit:
        return explicit
    values = {row.confidence for row in rows}
    if "hypothesis" in values:
        return "hypothesis"
    if "inferred" in values:
        return "inferred"
    return "observed" if rows else "hypothesis"


def _strength(count: int) -> str:
    if count >= 3:
        return "strong"
    if count == 2:
        return "moderate"
    if count == 1:
        return "weak"
    return "insufficient"


async def _evidence_context(
    session: AsyncSession, business: Business, evidence_ids: list[uuid.UUID]
) -> tuple[list[ResearchEvidence], list[dict[str, Any]]]:
    if not evidence_ids:
        return [], []
    rows = list(
        await session.scalars(
            select(ResearchEvidence).where(
                ResearchEvidence.id.in_(evidence_ids),
                ResearchEvidence.organization_id == business.organization_id,
                ResearchEvidence.business_id == business.id,
            )
        )
    )
    if len(rows) != len(set(evidence_ids)):
        raise NotFoundError("Research evidence not found")
    source_ids = {row.source_id for row in rows}
    sources = {
        source.id: source
        for source in await session.scalars(
            select(ResearchSource).where(
                ResearchSource.id.in_(source_ids),
                ResearchSource.organization_id == business.organization_id,
                ResearchSource.business_id == business.id,
            )
        )
    }
    finding_rows = list(
        await session.execute(
            select(research_finding_evidence.c.evidence_id, ResearchFinding)
            .join(ResearchFinding, ResearchFinding.id == research_finding_evidence.c.finding_id)
            .where(
                research_finding_evidence.c.evidence_id.in_(evidence_ids),
                ResearchFinding.organization_id == business.organization_id,
                ResearchFinding.business_id == business.id,
            )
        )
    )
    findings_by_evidence: dict[uuid.UUID, list[ResearchFinding]] = {}
    for evidence_id, finding in finding_rows:
        findings_by_evidence.setdefault(evidence_id, []).append(finding)
    snapshots = {
        snapshot.id: snapshot
        for snapshot in await session.scalars(
            select(ResearchSourceSnapshot).where(ResearchSourceSnapshot.source_id.in_(source_ids))
        )
    }
    provenance: list[dict[str, Any]] = []
    for row in rows:
        source = sources.get(row.source_id)
        snapshot = snapshots.get(row.snapshot_id) if row.snapshot_id else None
        for finding in findings_by_evidence.get(row.id, [None]):
            provenance.append(
                _safe(
                    {
                        "evidence_id": row.id,
                        "finding_id": finding.id if finding else None,
                        "source_id": row.source_id,
                        "snapshot_id": snapshot.id if snapshot else row.snapshot_id,
                        "source_title": source.title if source else None,
                        "statement": row.statement,
                        "data_source": row.evidence_type,
                    }
                )
            )
    return rows, provenance


async def _research_context(
    session: AsyncSession, business: Business
) -> tuple[ResearchIntelligenceSnapshot | None, dict[str, Any], list[dict[str, Any]]]:
    intelligence = ResearchIntelligenceStore(session)
    snapshot = await intelligence.ensure_snapshot(business)
    return snapshot, snapshot.coverage_json or {}, snapshot.missing_areas_json or []


async def _next_version(session: AsyncSession, model: Any, business_id: uuid.UUID) -> int:
    value = await session.scalar(
        select(func.max(model.version)).where(model.business_id == business_id)
    )
    return int(value or 0) + 1


def _positioning_statement(candidate: PositioningCandidate) -> str | None:
    parts = [
        candidate.target_customer,
        candidate.problem,
        candidate.solution,
        candidate.differentiator,
        candidate.promise,
    ]
    if not all(parts):
        return None
    return (
        f"For {candidate.target_customer} facing {candidate.problem}, "
        f"{candidate.solution} with {candidate.differentiator}, "
        f"so they can {candidate.promise}."
    )


async def create_positioning_candidate(
    session: AsyncSession, business: Business, payload: Any
) -> PositioningCandidate:
    evidence, provenance = await _evidence_context(session, business, payload.evidence_ids)
    intelligence_snapshot, coverage, missing = await _research_context(session, business)
    version = await _next_version(session, PositioningStrategy, business.id)
    snapshot = StrategySnapshot(
        organization_id=business.organization_id,
        business_id=business.id,
        strategy_kind="positioning",
        strategy_version=POSITIONING_VERSION,
        research_intelligence_version=(
            intelligence_snapshot.intelligence_version
            if intelligence_snapshot
            else INTELLIGENCE_VERSION
        ),
        input_snapshot_refs={
            "research_intelligence_snapshot_id": str(intelligence_snapshot.id)
            if intelligence_snapshot
            else None,
            "evidence_ids": [str(row.id) for row in evidence],
        },
        coverage_json=coverage,
        missing_research_areas=missing,
    )
    session.add(snapshot)
    await session.flush()
    strategy = PositioningStrategy(
        organization_id=business.organization_id,
        business_id=business.id,
        snapshot_id=snapshot.id,
        version=version,
        strategy_version=POSITIONING_VERSION,
        status="draft",
    )
    session.add(strategy)
    await session.flush()
    customer_types = {"pain_point", "complaint", "desire", "buying_trigger", "trust_signal"}
    evidence_coverage = min(Decimal("1"), Decimal(len(evidence)) / Decimal("3"))
    customer_relevance = (
        Decimal("1")
        if any(row.evidence_type in customer_types for row in evidence)
        else Decimal("0")
    )
    differentiation = (
        Decimal("1")
        if any(row.evidence_type in {"competitor_gap", "feature", "benefit"} for row in evidence)
        else Decimal("0")
    )
    capability = Decimal("1") if payload.solution or payload.differentiator else Decimal("0")
    score_breakdown = {
        "evidence_coverage": str(evidence_coverage),
        "customer_relevance": str(customer_relevance),
        "differentiation_evidence": str(differentiation),
        "business_capability": str(capability),
        "formula": (
            "0.40*evidence_coverage + 0.20*customer_relevance + "
            "0.20*differentiation_evidence + 0.20*business_capability"
        ),
    }
    score = (
        Decimal("0.40") * evidence_coverage
        + Decimal("0.20") * customer_relevance
        + Decimal("0.20") * differentiation
        + Decimal("0.20") * capability
    ).quantize(Decimal("0.0001"))
    risks: list[dict[str, Any]] = []
    if not evidence:
        risks.append(
            {
                "code": "insufficient_customer_evidence",
                "reason": "No linked research evidence was supplied.",
            }
        )
    if payload.differentiator and not differentiation:
        risks.append(
            {
                "code": "unsupported_differentiation",
                "reason": (
                    "No linked feature, benefit, or competitor-gap evidence supports "
                    "the differentiator."
                ),
            }
        )
    if not payload.proof_points:
        risks.append({"code": "missing_proof", "reason": "No proof points were supplied."})
    candidate = PositioningCandidate(
        organization_id=business.organization_id,
        business_id=business.id,
        positioning_strategy_id=strategy.id,
        name=payload.name,
        candidate_type=payload.candidate_type,
        target_customer=payload.target_customer,
        problem=payload.problem,
        solution=payload.solution,
        differentiator=payload.differentiator,
        promise=payload.promise,
        supporting_benefits=payload.supporting_benefits,
        proof_points=payload.proof_points,
        objections_addressed=payload.objections_addressed,
        classification=_classification(evidence, payload.classification),
        strength=_strength(len(evidence)),
        score=score,
        score_breakdown=score_breakdown,
        status="draft",
        assumptions=payload.assumptions,
        risks=risks,
        provenance=provenance,
    )
    candidate.positioning_statement = _positioning_statement(candidate)
    session.add(candidate)
    await session.commit()
    await session.refresh(candidate)
    return candidate


async def _latest_positioning(
    session: AsyncSession, business: Business
) -> PositioningStrategy | None:
    return await session.scalar(
        select(PositioningStrategy)
        .where(
            PositioningStrategy.organization_id == business.organization_id,
            PositioningStrategy.business_id == business.id,
        )
        .order_by(desc(PositioningStrategy.version))
        .limit(1)
    )


async def _latest_offer(session: AsyncSession, business: Business) -> OfferStrategy | None:
    return await session.scalar(
        select(OfferStrategy)
        .where(
            OfferStrategy.organization_id == business.organization_id,
            OfferStrategy.business_id == business.id,
        )
        .order_by(desc(OfferStrategy.version))
        .limit(1)
    )


async def positioning_response(
    session: AsyncSession, business: Business, strategy: PositioningStrategy | None = None
) -> dict[str, Any]:
    if strategy is None:
        strategy = await _latest_positioning(session, business)
    if strategy is None:
        return {
            "strategy_id": None,
            "version": None,
            "strategy_version": POSITIONING_VERSION,
            "status": "insufficient_data",
            "selected_candidate_id": None,
            "candidates": [],
            "coverage": {},
            "missing_research_areas": [
                {
                    "area": "positioning",
                    "reason": "No positioning candidates exist.",
                    "severity": "high",
                }
            ],
        }
    candidates = list(
        await session.scalars(
            select(PositioningCandidate)
            .where(PositioningCandidate.positioning_strategy_id == strategy.id)
            .order_by(PositioningCandidate.created_at)
        )
    )
    snapshot = await session.get(StrategySnapshot, strategy.snapshot_id)
    return {
        "strategy_id": strategy.id,
        "version": strategy.version,
        "strategy_version": strategy.strategy_version,
        "status": strategy.status,
        "selected_candidate_id": strategy.selected_candidate_id,
        "candidates": [
            {
                **{
                    column.name: getattr(candidate, column.name)
                    for column in PositioningCandidate.__table__.columns
                },
                "strategy_version": strategy.strategy_version,
            }
            for candidate in candidates
        ],
        "coverage": snapshot.coverage_json if snapshot else {},
        "missing_research_areas": snapshot.missing_research_areas if snapshot else [],
    }


async def recommend_positioning(session: AsyncSession, business: Business) -> dict[str, Any]:
    strategy = await _latest_positioning(session, business)
    if strategy is None:
        return await positioning_response(session, business)
    candidates = list(
        await session.scalars(
            select(PositioningCandidate)
            .where(PositioningCandidate.positioning_strategy_id == strategy.id)
            .order_by(PositioningCandidate.score.desc().nullslast(), PositioningCandidate.id)
        )
    )
    candidate = candidates[0] if candidates else None
    if (
        candidate is None
        or candidate.score is None
        or candidate.score < Decimal("0.6000")
        or candidate.strength == "insufficient"
    ):
        strategy.status = "insufficient_data"
        strategy.selected_candidate_id = None
    else:
        candidate.status = "recommended"
        strategy.status = "recommended"
        strategy.selected_candidate_id = candidate.id
    await session.commit()
    return await positioning_response(session, business, strategy)


async def positioning_versions(session: AsyncSession, business: Business) -> list[dict[str, Any]]:
    rows = list(
        await session.scalars(
            select(PositioningStrategy)
            .where(
                PositioningStrategy.organization_id == business.organization_id,
                PositioningStrategy.business_id == business.id,
            )
            .order_by(desc(PositioningStrategy.version))
        )
    )
    return [await positioning_response(session, business, row) for row in rows]


async def get_positioning_candidate(
    session: AsyncSession, business: Business, candidate_id: uuid.UUID
) -> PositioningCandidate:
    candidate = await session.scalar(
        select(PositioningCandidate).where(
            PositioningCandidate.id == candidate_id,
            PositioningCandidate.organization_id == business.organization_id,
            PositioningCandidate.business_id == business.id,
        )
    )
    if candidate is None:
        raise NotFoundError("Positioning candidate not found")
    return candidate


async def _offer_economics(
    session: AsyncSession, business: Business, payload: Any
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    now = datetime.now(UTC)
    risks: list[dict[str, Any]] = []
    assumptions: list[str] = []
    if payload.product_id:
        product = await session.scalar(
            select(Product).where(
                Product.id == payload.product_id, Product.business_id == business.id
            )
        )
        if product is None:
            raise NotFoundError("Product not found")
        price = await resolve_active_price(session, product.id, now)
        cost = await resolve_active_cost(session, product.id, now)
        shipping = (
            await session.scalar(
                select(ShippingRule).where(
                    ShippingRule.id == payload.shipping_rule_id,
                    ShippingRule.business_id == business.id,
                )
            )
            if payload.shipping_rule_id
            else await resolve_shipping_rule(session, business.id, now)
        )
        discount = (
            await session.scalar(
                select(Discount).where(
                    Discount.id == payload.discount_id, Discount.business_id == business.id
                )
            )
            if payload.discount_id
            else None
        )
        if price is None:
            return (
                {},
                [{"code": "missing_price", "reason": "The product has no active price."}],
                assumptions,
            )
        if cost is None:
            assumptions.append(
                "No active product cost was configured; COGS and packaging default "
                "to zero in the canonical calculator."
            )
        economics = calculate_product_economics(
            price=payload.price_override if payload.price_override is not None else price.price,
            cogs=cost.cogs if cost else ZERO,
            packaging_cost=cost.packaging_cost if cost else ZERO,
            payment_fee_fixed=cost.payment_fee_fixed if cost else ZERO,
            payment_fee_percent=cost.payment_fee_percent if cost else ZERO,
            shipping_cost=shipping.cost if shipping else ZERO,
            shipping_customer_price=shipping.customer_price if shipping else ZERO,
            discount_type=discount.type if discount else None,
            discount_value=discount.value if discount else ZERO,
            discount_minimum_order_value=discount.minimum_order_value if discount else None,
            discount_maximum_discount=discount.maximum_discount if discount else None,
        )
        result = {
            "selling_price": economics.product_revenue,
            "discount_value": economics.discount_amount,
            "net_price": economics.product_revenue - economics.discount_amount,
            "cogs": economics.product_cost,
            "shipping_cost": economics.shipping_cost,
            "payment_fees": economics.payment_fees,
            "contribution_profit": economics.contribution_profit,
            "contribution_margin": economics.contribution_margin,
            "break_even_cpa": economics.break_even_cpa,
            "break_even_roas": economics.break_even_roas,
            "target_cpa": economics.target_cpa,
            "currency": product.currency,
            "product_id": product.id,
            "inventory_quantity": await _inventory(session, product.id),
        }
        if result["inventory_quantity"] <= 0:
            risks.append(
                {"code": "inventory_risk", "reason": "No positive inventory snapshot is available."}
            )
        if economics.contribution_profit <= ZERO:
            risks.append({"code": "margin_risk", "reason": "Contribution profit is not positive."})
        return _safe(result), risks, assumptions
    bundle = await session.scalar(
        select(Bundle).where(Bundle.id == payload.bundle_id, Bundle.business_id == business.id)
    )
    if bundle is None:
        raise NotFoundError("Bundle not found")
    items = list(await session.scalars(select(BundleItem).where(BundleItem.bundle_id == bundle.id)))
    costs = []
    quantities = []
    for item in items:
        cost = await resolve_active_cost(session, item.product_id, now)
        costs.append((cost.cogs + cost.packaging_cost) if cost else ZERO)
        quantities.append(item.quantity)
    economics = calculate_bundle_economics(
        bundle_price=payload.price_override if payload.price_override is not None else bundle.price,
        item_costs=costs,
        quantities=quantities,
    )
    if economics.contribution_profit <= ZERO:
        risks.append(
            {"code": "margin_risk", "reason": "Bundle contribution profit is not positive."}
        )
    if payload.discount_id:
        risks.append(
            {
                "code": "discount_not_applied",
                "reason": (
                    "The canonical bundle calculator does not apply product discounts to bundles."
                ),
            }
        )
    result = {
        "selling_price": economics.bundle_price,
        "discount_value": ZERO,
        "net_price": economics.bundle_price,
        "cogs": economics.items_cost,
        "shipping_cost": None,
        "payment_fees": None,
        "contribution_profit": economics.contribution_profit,
        "contribution_margin": economics.contribution_margin,
        "break_even_cpa": economics.contribution_profit,
        "break_even_roas": (economics.bundle_price / economics.contribution_profit).quantize(
            Decimal("0.0001")
        )
        if economics.contribution_profit > ZERO
        else None,
        "target_cpa": None,
        "currency": bundle.currency,
        "bundle_id": bundle.id,
    }
    return _safe(result), risks, assumptions


async def _inventory(session: AsyncSession, product_id: uuid.UUID) -> int:
    value = await session.scalar(
        select(InventorySnapshot.quantity)
        .where(InventorySnapshot.product_id == product_id)
        .order_by(InventorySnapshot.recorded_at.desc())
        .limit(1)
    )
    return int(value or 0)


async def create_offer_candidate(
    session: AsyncSession, business: Business, payload: Any
) -> OfferCandidate:
    evidence, provenance = await _evidence_context(session, business, payload.evidence_ids)
    intelligence_snapshot, coverage, missing = await _research_context(session, business)
    version = await _next_version(session, OfferStrategy, business.id)
    snapshot = StrategySnapshot(
        organization_id=business.organization_id,
        business_id=business.id,
        strategy_kind="offer",
        strategy_version=OFFER_VERSION,
        research_intelligence_version=intelligence_snapshot.intelligence_version
        if intelligence_snapshot
        else INTELLIGENCE_VERSION,
        input_snapshot_refs={
            "research_intelligence_snapshot_id": str(intelligence_snapshot.id)
            if intelligence_snapshot
            else None,
            "evidence_ids": [str(row.id) for row in evidence],
        },
        coverage_json=coverage,
        missing_research_areas=missing,
    )
    session.add(snapshot)
    await session.flush()
    strategy = OfferStrategy(
        organization_id=business.organization_id,
        business_id=business.id,
        snapshot_id=snapshot.id,
        version=version,
        strategy_version=OFFER_VERSION,
        status="draft",
    )
    session.add(strategy)
    await session.flush()
    economics, risks, assumptions = await _offer_economics(session, business, payload)
    economic_viability = (
        Decimal("1")
        if economics.get("contribution_profit") is not None
        and Decimal(str(economics["contribution_profit"])) > ZERO
        and not any(r["code"] == "missing_price" for r in risks)
        else Decimal("0")
    )
    evidence_strength = (
        Decimal("1")
        if len(evidence) >= 3
        else Decimal("0.66")
        if len(evidence) == 2
        else Decimal("0.33")
        if evidence
        else Decimal("0")
    )
    inventory = Decimal("1") if economics.get("inventory_quantity", 1) > 0 else Decimal("0")
    score_breakdown = {
        "economic_viability": str(economic_viability),
        "evidence_strength": str(evidence_strength),
        "inventory_feasibility": str(inventory),
        "formula": "0.50*economic_viability + 0.25*evidence_strength + 0.25*inventory_feasibility",
    }
    score = (
        Decimal("0.50") * economic_viability
        + Decimal("0.25") * evidence_strength
        + Decimal("0.25") * inventory
    ).quantize(Decimal("0.0001"))
    components = _safe(
        {
            "guarantee": payload.guarantee,
            "bonus": payload.bonus,
            "urgency": payload.urgency,
            "risk_reversal": payload.risk_reversal,
            "proof": payload.proof,
            "discount_id": payload.discount_id,
            "shipping_rule_id": payload.shipping_rule_id,
        }
    )
    if (
        payload.urgency
        and not payload.urgency.get("end_at")
        and not payload.urgency.get("inventory_supported")
    ):
        risks.append(
            {
                "code": "unsupported_urgency",
                "reason": "Urgency requires a real deadline or supported inventory signal.",
            }
        )
    if not payload.proof:
        risks.append({"code": "weak_proof", "reason": "No proof points were supplied."})
    candidate = OfferCandidate(
        organization_id=business.organization_id,
        business_id=business.id,
        offer_strategy_id=strategy.id,
        product_id=payload.product_id,
        bundle_id=payload.bundle_id,
        name=payload.name,
        components=components,
        economics=economics,
        classification=_classification(evidence, payload.classification),
        strength=_strength(len(evidence)),
        score=score,
        score_breakdown=score_breakdown,
        status="draft",
        assumptions=assumptions + payload.assumptions,
        risks=risks,
        provenance=provenance,
    )
    session.add(candidate)
    await session.commit()
    await session.refresh(candidate)
    return candidate


async def offer_response(
    session: AsyncSession, business: Business, strategy: OfferStrategy | None = None
) -> dict[str, Any]:
    if strategy is None:
        strategy = await _latest_offer(session, business)
    if strategy is None:
        return {
            "strategy_id": None,
            "version": None,
            "strategy_version": OFFER_VERSION,
            "status": "insufficient_data",
            "selected_candidate_id": None,
            "candidates": [],
            "coverage": {},
            "missing_research_areas": [
                {"area": "offer", "reason": "No offer candidates exist.", "severity": "high"}
            ],
        }
    candidates = list(
        await session.scalars(
            select(OfferCandidate)
            .where(OfferCandidate.offer_strategy_id == strategy.id)
            .order_by(OfferCandidate.created_at)
        )
    )
    snapshot = await session.get(StrategySnapshot, strategy.snapshot_id)
    return {
        "strategy_id": strategy.id,
        "version": strategy.version,
        "strategy_version": strategy.strategy_version,
        "status": strategy.status,
        "selected_candidate_id": strategy.selected_candidate_id,
        "candidates": [
            {
                **{
                    column.name: getattr(candidate, column.name)
                    for column in OfferCandidate.__table__.columns
                },
                "strategy_version": strategy.strategy_version,
            }
            for candidate in candidates
        ],
        "coverage": snapshot.coverage_json if snapshot else {},
        "missing_research_areas": snapshot.missing_research_areas if snapshot else [],
    }


async def get_offer_candidate(
    session: AsyncSession, business: Business, candidate_id: uuid.UUID
) -> OfferCandidate:
    candidate = await session.scalar(
        select(OfferCandidate).where(
            OfferCandidate.id == candidate_id,
            OfferCandidate.organization_id == business.organization_id,
            OfferCandidate.business_id == business.id,
        )
    )
    if candidate is None:
        raise NotFoundError("Offer candidate not found")
    return candidate


async def validate_offer(
    session: AsyncSession, business: Business, candidate_id: uuid.UUID
) -> dict[str, Any]:
    candidate = await get_offer_candidate(session, business, candidate_id)
    candidate.status = (
        "invalid"
        if any(
            r.get("code") in {"missing_price", "margin_risk", "unsupported_urgency"}
            for r in candidate.risks
        )
        else "validated"
    )
    strategy = await session.get(OfferStrategy, candidate.offer_strategy_id)
    if strategy:
        strategy.status = candidate.status
    await session.commit()
    return await offer_response(session, business, strategy)


async def recommend_offer(session: AsyncSession, business: Business) -> dict[str, Any]:
    strategy = await _latest_offer(session, business)
    if strategy is None:
        return await offer_response(session, business)
    candidates = list(
        await session.scalars(
            select(OfferCandidate)
            .where(OfferCandidate.offer_strategy_id == strategy.id)
            .order_by(OfferCandidate.score.desc().nullslast(), OfferCandidate.id)
        )
    )
    candidate = next(
        (
            row
            for row in candidates
            if row.status in {"validated", "draft"} and row.score is not None
        ),
        None,
    )
    if (
        candidate is None
        or candidate.score < Decimal("0.6000")
        or any(r.get("code") == "missing_price" for r in candidate.risks)
    ):
        strategy.status = "insufficient_data" if candidate is None else "invalid"
        strategy.selected_candidate_id = None
    else:
        candidate.status = "recommended"
        strategy.status = "recommended"
        strategy.selected_candidate_id = candidate.id
    await session.commit()
    return await offer_response(session, business, strategy)


async def offer_versions(session: AsyncSession, business: Business) -> list[dict[str, Any]]:
    rows = list(
        await session.scalars(
            select(OfferStrategy)
            .where(
                OfferStrategy.organization_id == business.organization_id,
                OfferStrategy.business_id == business.id,
            )
            .order_by(desc(OfferStrategy.version))
        )
    )
    return [await offer_response(session, business, row) for row in rows]


async def strategy_summary(session: AsyncSession, business: Business) -> dict[str, Any]:
    positioning = await positioning_response(session, business)
    offers = await offer_response(session, business)
    return {
        "positioning": positioning,
        "offers": offers,
        "missing_research_areas": positioning["missing_research_areas"]
        + offers["missing_research_areas"],
    }


async def latest_snapshot(session: AsyncSession, business: Business) -> StrategySnapshot | None:
    return await session.scalar(
        select(StrategySnapshot)
        .where(
            StrategySnapshot.organization_id == business.organization_id,
            StrategySnapshot.business_id == business.id,
        )
        .order_by(desc(StrategySnapshot.created_at))
        .limit(1)
    )
