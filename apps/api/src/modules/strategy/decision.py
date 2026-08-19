"""Deterministic strategy decision integration.

This module is an adapter over existing decision systems. It only reads their
canonical outputs and stores references plus a compact evaluation snapshot;
it does not recalculate KPIs, economics, diagnostics, forecasts, or
simulations.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.db.models import (
    Business,
    BusinessGoal,
    Forecast,
    OfferCandidate,
    OfferStrategy,
    PositioningCandidate,
    PositioningStrategy,
    Simulation,
    StrategyDecision,
)
from src.modules.diagnostics import service as diagnostics_service
from src.modules.economics.service import current_goal
from src.modules.metrics import service as metrics_service
from src.modules.research.intelligence import ResearchIntelligenceStore

DECISION_RULES_VERSION = "strategy_decision_v1"

POSITIONING_WEIGHTS = {
    "research_score": Decimal("0.20"),
    "customer_score": Decimal("0.15"),
    "differentiation_score": Decimal("0.15"),
    "capability_score": Decimal("0.15"),
    "economics_score": Decimal("0.10"),
    "goal_score": Decimal("0.10"),
    "performance_score": Decimal("0.05"),
    "evidence_score": Decimal("0.10"),
}
OFFER_WEIGHTS = {
    "economic_viability": Decimal("0.30"),
    "goal_alignment": Decimal("0.15"),
    "customer_relevance": Decimal("0.10"),
    "competitive_position": Decimal("0.10"),
    "performance_compatibility": Decimal("0.10"),
    "forecast_alignment": Decimal("0.05"),
    "simulation_alignment": Decimal("0.05"),
    "inventory_feasibility": Decimal("0.05"),
    "evidence_strength": Decimal("0.10"),
}


def _safe(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_safe(v) for v in value]
    return value


def _reason(
    type_: str,
    severity: str,
    statement: str,
    source: str,
    reference_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    return {
        "type": type_,
        "severity": severity,
        "statement": statement,
        "source": source,
        "reference_id": reference_id,
    }


def _measure(summary: dict[str, Any], key: str) -> Decimal | None:
    value = summary.get(key) or {}
    if value.get("status") != "available" or value.get("value") is None:
        return None
    return Decimal(str(value["value"]))


def _weighted_score(
    values: dict[str, Decimal | None], weights: dict[str, Decimal]
) -> Decimal | None:
    available = [
        (key, value) for key, value in values.items() if key in weights and value is not None
    ]
    if not available:
        return None
    total_weight = sum((weights[key] for key, _ in available), Decimal("0"))
    total = sum((weights[key] * value for key, value in available), Decimal("0"))
    return (total / total_weight).quantize(Decimal("0.0001"))


def _range_view(range_obj: Any) -> dict[str, Any]:
    return _safe(
        {
            "kind": range_obj.kind,
            "start": range_obj.start,
            "end": range_obj.end,
            "previous_start": range_obj.previous_start,
            "previous_end": range_obj.previous_end,
        }
    )


async def _candidate(
    session: AsyncSession, business: Business, candidate_type: str, candidate_id: uuid.UUID
) -> PositioningCandidate | OfferCandidate:
    model = PositioningCandidate if candidate_type == "positioning" else OfferCandidate
    row = await session.scalar(
        select(model).where(
            model.id == candidate_id,
            model.organization_id == business.organization_id,
            model.business_id == business.id,
        )
    )
    if row is None:
        raise NotFoundError("Strategy candidate not found")
    return row


async def _input_context(
    session: AsyncSession,
    business: Business,
    payload: Any,
    settings: Any,
) -> dict[str, Any]:
    range_obj = metrics_service.resolve_range(
        business.timezone,
        payload.range_kind,
        start=payload.period_start,
        end=payload.period_end,
    )
    metrics = await metrics_service.summary(session, business, range_obj)
    diagnostics = await diagnostics_service.diagnostics_for_business(
        session, business, range_obj, settings
    )
    goal = await current_goal(session, business.id, datetime.now(UTC))

    intelligence = ResearchIntelligenceStore(session)
    research_snapshot = await intelligence.ensure_snapshot(business)

    forecast = None
    if payload.forecast_id:
        forecast = await session.scalar(
            select(Forecast).where(
                Forecast.id == payload.forecast_id,
                Forecast.organization_id == business.organization_id,
                Forecast.business_id == business.id,
            )
        )
        if forecast is None:
            raise NotFoundError("Forecast not found")
    else:
        forecast = await session.scalar(
            select(Forecast)
            .where(
                Forecast.organization_id == business.organization_id,
                Forecast.business_id == business.id,
                Forecast.entity_type == "business",
            )
            .order_by(desc(Forecast.created_at))
            .limit(1)
        )

    simulation = None
    if payload.simulation_id:
        simulation = await session.scalar(
            select(Simulation).where(
                Simulation.id == payload.simulation_id,
                Simulation.organization_id == business.organization_id,
                Simulation.business_id == business.id,
            )
        )
        if simulation is None:
            raise NotFoundError("Simulation not found")
    else:
        simulation = await session.scalar(
            select(Simulation)
            .where(
                Simulation.organization_id == business.organization_id,
                Simulation.business_id == business.id,
            )
            .order_by(desc(Simulation.created_at))
            .limit(1)
        )

    return {
        "range": range_obj,
        "metrics": metrics,
        "diagnostics": diagnostics,
        "goal": goal,
        "research_snapshot": research_snapshot,
        "forecast": forecast,
        "simulation": simulation,
    }


def _research_refs(candidate: Any) -> list[dict[str, Any]]:
    return list(candidate.provenance or [])


def _metric_view(metrics: dict[str, Any]) -> dict[str, Any]:
    keys = ("ctr", "cpc", "cpm", "cvr", "cpa", "aov", "roas", "mer", "revenue", "spend", "profit")
    return {key: _safe(metrics.get(key)) for key in keys if key in metrics}


def _goal_view(goal: BusinessGoal | None) -> dict[str, Any]:
    if goal is None:
        return {"status": "unavailable", "reason": "No active business goal exists."}
    return _safe(
        {
            "status": "available",
            "id": goal.id,
            "period_start": goal.period_start,
            "period_end": goal.period_end,
            "target_revenue": goal.target_revenue,
            "target_profit": goal.target_profit,
            "maximum_cpa": goal.maximum_cpa,
            "target_roas": goal.target_roas,
            "ad_budget": goal.ad_budget,
            "currency": goal.currency,
        }
    )


def _forecast_view(forecast: Forecast | None) -> dict[str, Any]:
    if forecast is None:
        return {"status": "unavailable", "reason": "No persisted forecast exists."}
    return _safe(
        {
            "status": forecast.status,
            "id": forecast.id,
            "metric_code": forecast.metric_code,
            "model_version": forecast.model_version,
            "expected_value": forecast.expected_value,
            "lower_value": forecast.lower_value,
            "upper_value": forecast.upper_value,
            "confidence_level": forecast.confidence_level,
        }
    )


def _simulation_view(simulation: Simulation | None) -> dict[str, Any]:
    if simulation is None:
        return {"status": "unavailable", "reason": "No persisted simulation exists."}
    return _safe(
        {
            "status": "available",
            "id": simulation.id,
            "model_version": simulation.model_version,
            "data_quality": simulation.data_quality,
            "evidence_strength": simulation.evidence_strength,
            "results_reference": "simulation.results_snapshot",
        }
    )


def _diagnostic_view(diagnostics: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _safe(
            {
                "id": finding["id"],
                "category": finding["category"],
                "code": finding["code"],
                "severity": finding["severity"],
                "status": finding["status"],
            }
        )
        for finding in diagnostics.get("findings", [])
    ]


async def _positioning_evaluation(
    session: AsyncSession,
    business: Business,
    candidate: PositioningCandidate,
    context: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], Decimal | None]:
    refs = _research_refs(candidate)
    evidence_count = len({ref.get("evidence_id") for ref in refs if ref.get("evidence_id")})
    customer = (
        Decimal("1")
        if any(
            ref.get("data_source")
            in {"pain_point", "complaint", "desire", "review", "buying_trigger"}
            for ref in refs
        )
        else None
    )
    differentiation = (
        Decimal("1")
        if any(ref.get("data_source") in {"competitor_gap", "feature", "benefit"} for ref in refs)
        else None
    )
    research = min(Decimal("1"), Decimal(evidence_count) / Decimal("3")) if evidence_count else None
    capability = Decimal("1") if candidate.solution and candidate.promise else None
    economics = Decimal("1") if candidate.solution else None
    goal = Decimal("1") if context["goal"] else None
    metric_values = context["metrics"]
    performance = (
        Decimal("1")
        if _measure(metric_values, "ctr") is not None or _measure(metric_values, "cvr") is not None
        else None
    )
    evidence = (
        Decimal("1")
        if evidence_count >= 3
        else Decimal("0.66")
        if evidence_count == 2
        else Decimal("0.33")
        if evidence_count
        else None
    )
    scores = {
        "research_score": research,
        "customer_score": customer,
        "differentiation_score": differentiation,
        "capability_score": capability,
        "economics_score": economics,
        "goal_score": goal,
        "performance_score": performance,
        "evidence_score": evidence,
        "weights": POSITIONING_WEIGHTS,
        "formula": (
            "weighted mean of available dimensions; unavailable inputs are excluded and disclosed"
        ),
    }
    reasons: list[dict[str, Any]] = []
    if not refs:
        reasons.append(
            _reason(
                "research", "critical", "Positioning has no linked research evidence.", "research"
            )
        )
    if candidate.promise and not candidate.proof_points:
        reasons.append(
            _reason(
                "proof",
                "medium",
                "The promise has no supplied proof points.",
                "positioning_candidate",
                candidate.id,
            )
        )
    if candidate.differentiator and differentiation is None:
        reasons.append(
            _reason(
                "differentiation",
                "high",
                "The differentiator has no supporting feature, benefit, or "
                "competitor-gap evidence.",
                "research",
            )
        )
    score = _weighted_score(scores, POSITIONING_WEIGHTS)
    evaluation = {
        "dimensions": _safe(scores),
        "research_evidence_count": evidence_count,
        "goal_alignment": "available" if context["goal"] else "unavailable",
        "performance_compatibility": "available" if performance is not None else "unavailable",
    }
    return evaluation, reasons, score


async def _offer_evaluation(
    business: Business,
    candidate: OfferCandidate,
    context: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], Decimal | None]:
    economics_data = candidate.economics or {}
    profit = economics_data.get("contribution_profit")
    break_even_cpa = economics_data.get("break_even_cpa")
    break_even_roas = economics_data.get("break_even_roas")
    economic_viability = (
        Decimal("1")
        if profit is not None and Decimal(str(profit)) > 0 and break_even_roas is not None
        else Decimal("0")
    )
    goal = context["goal"]
    goal_alignment: Decimal | None = None
    reasons: list[dict[str, Any]] = []
    if goal:
        checks: list[bool] = []
        if goal.maximum_cpa is not None and break_even_cpa is not None:
            checks.append(Decimal(str(break_even_cpa)) >= goal.maximum_cpa)
        if goal.target_roas is not None and break_even_roas is not None:
            checks.append(Decimal(str(break_even_roas)) <= goal.target_roas)
        goal_alignment = (
            Decimal("1") if checks and all(checks) else Decimal("0") if checks else None
        )
        if goal_alignment == 0:
            reasons.append(
                _reason(
                    "goal",
                    "high",
                    "Offer economics do not satisfy the active CPA or ROAS goal.",
                    "business_goal",
                    goal.id,
                )
            )
    if economic_viability == 0:
        reasons.append(
            _reason(
                "economic",
                "critical",
                "Offer fails the existing contribution-profit or break-even gate.",
                "unit_economics",
                candidate.id,
            )
        )

    refs = _research_refs(candidate)
    evidence_strength = (
        Decimal("1")
        if len(refs) >= 3
        else Decimal("0.66")
        if len(refs) == 2
        else Decimal("0.33")
        if refs
        else None
    )
    customer_relevance = (
        Decimal("1")
        if any(
            ref.get("data_source")
            in {"pain_point", "objection", "desire", "review", "buying_trigger"}
            for ref in refs
        )
        else None
    )
    competitive = (
        Decimal("1")
        if any(ref.get("data_source") in {"competitor_gap", "pricing", "offer"} for ref in refs)
        else None
    )
    inventory = Decimal("1") if economics_data.get("inventory_quantity", 1) > 0 else Decimal("0")
    diagnostics = context["diagnostics"].get("findings", [])
    offer_diagnostic = any(
        finding.get("category") in {"offer", "conversion"} or "offer" in finding.get("code", "")
        for finding in diagnostics
    )
    performance = Decimal("1") if offer_diagnostic else Decimal("0.5") if diagnostics else None
    forecast = context["forecast"]
    forecast_alignment: Decimal | None = None
    if forecast and forecast.status == "available" and forecast.expected_value is not None:
        forecast_alignment = Decimal("1")
    simulation_alignment: Decimal | None = Decimal("1") if context["simulation"] else None
    scores = {
        "economic_viability": economic_viability,
        "goal_alignment": goal_alignment,
        "customer_relevance": customer_relevance,
        "competitive_position": competitive,
        "performance_compatibility": performance,
        "forecast_alignment": forecast_alignment,
        "simulation_alignment": simulation_alignment,
        "inventory_feasibility": inventory,
        "evidence_strength": evidence_strength,
        "weights": OFFER_WEIGHTS,
        "formula": "weighted mean of available dimensions; economic viability is a hard gate",
    }
    if forecast_alignment is None:
        reasons.append(
            _reason(
                "forecast",
                "medium",
                "No available forecast was supplied for comparison.",
                "forecast",
            )
        )
    if simulation_alignment is None:
        reasons.append(
            _reason(
                "simulation",
                "medium",
                "No simulation result was supplied; success is not assumed.",
                "simulator",
            )
        )
    if inventory == 0:
        reasons.append(
            _reason(
                "inventory",
                "high",
                "No positive inventory is available for this offer.",
                "inventory",
            )
        )
    score = _weighted_score(scores, OFFER_WEIGHTS)
    evaluation = {
        "dimensions": _safe(scores),
        "economics": _safe(economics_data),
        "goal_alignment": "aligned"
        if goal_alignment == 1
        else "mismatch"
        if goal_alignment == 0
        else "unavailable",
        "performance_compatibility": "directly_relevant"
        if offer_diagnostic
        else "indirectly_relevant"
        if diagnostics
        else "unavailable",
        "forecast_alignment": "available" if forecast_alignment is not None else "unavailable",
        "simulation_alignment": "available" if simulation_alignment is not None else "unavailable",
    }
    return evaluation, reasons, score


def _status(
    candidate_type: str,
    score: Decimal | None,
    reasons: list[dict[str, Any]],
    evaluation: dict[str, Any],
) -> str:
    if any(reason["severity"] == "critical" for reason in reasons):
        return "economically_invalid" if candidate_type == "offer" else "not_recommended"
    if evaluation.get("goal_alignment") == "mismatch":
        return "goal_mismatch"
    if score is None or any(
        value == "unavailable" for value in evaluation.values() if isinstance(value, str)
    ):
        return "insufficient_data"
    if score >= Decimal("0.75"):
        return "recommended"
    if score >= Decimal("0.50"):
        return "viable"
    return "needs_optimization"


async def evaluate_decision(
    session: AsyncSession,
    business: Business,
    payload: Any,
    settings: Any,
) -> StrategyDecision:
    candidate = await _candidate(session, business, payload.candidate_type, payload.candidate_id)
    context = await _input_context(session, business, payload, settings)
    if payload.candidate_type == "positioning":
        evaluation, reasons, score = await _positioning_evaluation(
            session, business, candidate, context
        )
        strategy = await session.get(PositioningStrategy, candidate.positioning_strategy_id)
        strategy_version = strategy.strategy_version if strategy else "positioning_v1"
    else:
        evaluation, reasons, score = await _offer_evaluation(business, candidate, context)
        strategy = await session.get(OfferStrategy, candidate.offer_strategy_id)
        strategy_version = strategy.strategy_version if strategy else "offer_v1"
    evaluation["diagnostics"] = _diagnostic_view(context["diagnostics"])
    evaluation["metrics"] = _metric_view(context["metrics"])
    evaluation["forecast"] = _forecast_view(context["forecast"])
    evaluation["simulation"] = _simulation_view(context["simulation"])
    evaluation["goal"] = _goal_view(context["goal"])
    status = _status(payload.candidate_type, score, reasons, evaluation)
    diagnostics = context["diagnostics"].get("findings", [])
    research_provenance = _research_refs(candidate)
    input_provenance = [
        *research_provenance,
        *[
            {
                "input_type": "diagnostic",
                "reference_id": finding.get("id"),
                "source": "diagnostics",
            }
            for finding in diagnostics
        ],
    ]
    if context["goal"]:
        input_provenance.append(
            {
                "input_type": "business_goal",
                "reference_id": context["goal"].id,
                "source": "business_goal",
            }
        )
    if context["forecast"]:
        input_provenance.append(
            {
                "input_type": "forecast",
                "reference_id": context["forecast"].id,
                "source": "forecast",
            }
        )
    if context["simulation"]:
        input_provenance.append(
            {
                "input_type": "simulation",
                "reference_id": context["simulation"].id,
                "source": "simulator",
            }
        )
    input_snapshot = _safe(
        {
            "business_id": business.id,
            "candidate_type": payload.candidate_type,
            "candidate_id": candidate.id,
            "strategy_id": strategy.id if strategy else None,
            "strategy_version": strategy_version,
            "decision_rules_version": DECISION_RULES_VERSION,
            "research_intelligence_snapshot_id": context["research_snapshot"].id,
            "research_intelligence_version": context["research_snapshot"].intelligence_version,
            "research_evidence_ids": [
                ref.get("evidence_id") for ref in research_provenance if ref.get("evidence_id")
            ],
            "business_goal_id": context["goal"].id if context["goal"] else None,
            "metrics_range": _range_view(context["range"]),
            "diagnostics_range": _range_view(context["range"]),
            "diagnostic_ids": [finding.get("id") for finding in diagnostics],
            "forecast_id": context["forecast"].id if context["forecast"] else None,
            "simulation_id": context["simulation"].id if context["simulation"] else None,
            "economic_calculation_reference": (
                {"candidate_id": candidate.id, "source": "offer_candidate.economics"}
                if payload.candidate_type == "offer"
                else None
            ),
        }
    )
    decision = StrategyDecision(
        organization_id=business.organization_id,
        business_id=business.id,
        candidate_type=payload.candidate_type,
        candidate_id=candidate.id,
        strategy_version=strategy_version,
        decision_rules_version=DECISION_RULES_VERSION,
        status=status,
        overall_score=score,
        input_snapshot=input_snapshot,
        evaluation=_safe(evaluation),
        reasons=_safe(reasons),
        provenance=_safe(input_provenance),
    )
    session.add(decision)
    await session.commit()
    await session.refresh(decision)
    return decision


async def list_decisions(session: AsyncSession, business: Business) -> list[StrategyDecision]:
    return list(
        await session.scalars(
            select(StrategyDecision)
            .where(
                StrategyDecision.organization_id == business.organization_id,
                StrategyDecision.business_id == business.id,
            )
            .order_by(desc(StrategyDecision.created_at))
        )
    )


async def get_decision(
    session: AsyncSession, business: Business, decision_id: uuid.UUID
) -> StrategyDecision:
    decision = await session.scalar(
        select(StrategyDecision).where(
            StrategyDecision.id == decision_id,
            StrategyDecision.organization_id == business.organization_id,
            StrategyDecision.business_id == business.id,
        )
    )
    if decision is None:
        raise NotFoundError("Strategy decision not found")
    return decision
