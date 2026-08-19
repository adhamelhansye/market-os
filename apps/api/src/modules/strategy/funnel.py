"""Deterministic, evidence-backed funnel strategy (Phase 7C).

No LLM or campaign execution occurs here. The funnel *defines* a strategy:
stage objectives, directions (message/offer/content), channel assignments,
KPIs with availability status, transitions, health, gaps and provenance —
all computed from stored business strategy, research, metrics, diagnostics
and goals. Nothing is fetched from providers and nothing is mutated on any
provider account.

Rules are versioned (``FUNNEL_RULES_VERSION``) and every generated strategy
persists an ``input_snapshot`` so historical outputs stay reproducible.

Honesty rules applied throughout:

- KPI references carry the real measurement status (available /
  insufficient_data / unavailable / not_configured); missing values are
  never converted to zero.
- Transition rates are computed from observed metrics only and are
  gated by the registry sample minima; below those they report
  ``insufficient_data``.
- Bottleneck language is limited to "likely bottleneck" and "potential
  bottleneck" — causality is never claimed.
- A channel is ``connected`` only when a connected integration connection
  exists; otherwise it is ``recommended``.
- A strategy decision with status ``insufficient_data`` is never treated
  as validated.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.db.models import (
    Business,
    FunnelGap,
    FunnelStage,
    FunnelStageChannel,
    FunnelStageKpi,
    FunnelStrategy,
    IntegrationConnection,
    MessageComponent,
    MessagingStrategy,
    OfferCandidate,
    PositioningCandidate,
    ResearchIntelligenceSnapshot,
    StrategyDecision,
)
from src.modules.diagnostics import service as diagnostics_service
from src.modules.diagnostics import thresholds as th
from src.modules.economics.service import current_goal
from src.modules.integrations.registry import get_registry
from src.modules.metrics import service as metrics_service
from src.modules.strategy.messaging import MESSAGING_VERSION
from src.modules.strategy.service import POSITIONING_VERSION

FUNNEL_VERSION = "funnel_v1"
FUNNEL_RULES_VERSION = "funnel_rules_v1"

# Named, documented stage-status weights used for the overall funnel score.
# not_configured stages are excluded from the score and disclosed.
STAGE_STATUS_WEIGHTS = {
    "healthy": Decimal("1.0"),
    "warning": Decimal("0.5"),
    "insufficient_data": Decimal("0.25"),
    "unavailable": Decimal("0.0"),
}

# Overall funnel status thresholds (mirrors strategy decision vocabulary).
SCORE_RECOMMENDED = Decimal("0.7500")
SCORE_VIABLE = Decimal("0.5000")

# Core funnel stages in order. retention has no registry metric yet, so it
# reports not_configured instead of inventing one.
FUNNEL_STAGES = ("awareness", "interest", "consideration", "purchase", "retention")

# Audience state per stage.
_AUDIENCE_STATES = {
    "awareness": "unaware",
    "interest": "problem_aware",
    "consideration": "solution_aware",
    "purchase": "decision_ready",
    "retention": "retained",
}

# Funnel variants. Selection weights/conditions are documented beside each
# entry; the default (no explicit variant) is inferred deterministically.
VARIANTS = (
    "direct_response",
    "content_led",
    "product_led",
    "education_led",
    "lead_generation",
    "ecommerce",
)

_VARIANT_SIGNALS: dict[str, str] = {
    # ecommerce requires an offer referencing a real product or bundle.
    "ecommerce": "offer",
    # product_led additionally requires a differentiator on positioning.
    "product_led": "offer_differentiator",
    # content_led requires a generated messaging strategy with components.
    "content_led": "messaging",
    # education_led requires research coverage of the problem/desire space.
    "education_led": "research_coverage",
    # No lead-capture mechanics are modeled yet; explicitly requesting the
    # variant yields status invalid (never a silently built funnel).
    "lead_generation": "unsupported",
    # direct_response is the documented default when no offer exists.
    "direct_response": "",
}


# Deterministic inference when no variant is requested.
def _infer_variant(offer: OfferCandidate | None) -> str:
    if offer is not None and (offer.product_id or offer.bundle_id):
        return "ecommerce"
    return "direct_response"


# Stage -> channel assignments (provider ids from the integration registry).
_STAGE_CHANNELS: dict[str, tuple[str, ...]] = {
    "awareness": ("meta",),
    "interest": ("meta",),
    "consideration": ("meta", "shopify"),
    "purchase": ("shopify",),
    "retention": ("shopify",),
}

_CHANNEL_PURPOSES = {
    "meta": "Paid social reach, traffic and conversion tracking.",
    "shopify": "Storefront catalog, checkout and order data.",
}

# Stage -> KPI assignments. metric entries map to registry metric codes;
# rate entries map to engine KPI codes (metric_code stays None).
_STAGE_KPIS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "awareness": (
        ("impressions", "metric", "primary"),
        ("reach", "metric", "secondary"),
        ("cpm", "rate", "secondary"),
    ),
    "interest": (
        ("clicks", "metric", "primary"),
        ("ctr", "rate", "primary"),
        ("cpc", "rate", "secondary"),
    ),
    "consideration": (
        ("landing_page_views", "metric", "primary"),
        ("cvr", "rate", "primary"),
    ),
    "purchase": (
        ("purchases", "metric", "primary"),
        ("revenue", "metric", "primary"),
        ("cpa", "rate", "secondary"),
        ("roas", "rate", "secondary"),
        ("aov", "rate", "secondary"),
    ),
    "retention": (("repeat_purchases", "unavailable", "primary"),),
}

# Threshold codes from the diagnostics registry attached to rate KPIs.
_KPI_THRESHOLDS = {
    "ctr": th.CTR_LOW,
    "cpc": th.CPC_HIGH,
    "cpm": th.CPM_HIGH,
    "cvr": th.CVR_LOW,
}

# Diagnostic finding code -> funnel stage (unmapped findings are skipped).
_FINDING_STAGES = {
    "ctr_low": "interest",
    "ctr_critical": "interest",
    "cpc_high": "interest",
    "cpm_high": "awareness",
    "frequency_high": "awareness",
    "cvr_low": "consideration",
    "cpa_over_target_high": "purchase",
    "cpa_over_target_critical": "purchase",
    "spend_without_purchase_high": "purchase",
    "conversion_mismatch_percent": "purchase",
}

# Transition definitions per adjacent stage pair (numerator/denominator
# registry metric codes). purchase -> retention has no registry metric.
_TRANSITIONS: dict[tuple[str, str], tuple[str, str]] = {
    ("awareness", "interest"): ("clicks", "impressions"),
    ("interest", "consideration"): ("landing_page_views", "clicks"),
    ("consideration", "purchase"): ("purchases", "landing_page_views"),
}

_UNIT_BY_KIND = {"count": "count", "money": "money", "rate": "ratio"}


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


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _measure(summary: dict[str, Any], key: str) -> dict[str, Any] | None:
    measure = summary.get(key) or {}
    if measure.get("status") != "available" or measure.get("value") is None:
        return None
    return measure


def _bottleneck_label(rate: Decimal | None, threshold: Decimal) -> str | None:
    if rate is None:
        return None
    if rate < threshold:
        return "likely"
    return "potential"


def _evidence_ref(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "evidence_id": entry.get("evidence_id"),
        "source_id": entry.get("source_id"),
        "snapshot_id": entry.get("snapshot_id"),
        "source_title": entry.get("source_title"),
        "data_source": entry.get("data_source"),
    }


def _stage_provenance(
    *,
    positioning: PositioningCandidate | None,
    offer: OfferCandidate | None,
    messaging: MessagingStrategy | None,
    decision: StrategyDecision | None,
    goal: Any,
    diagnostics: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[uuid.UUID | None] = set()
    entries: list[dict[str, Any]] = []
    if positioning is not None:
        entries.extend(positioning.provenance or [])
    if offer is not None:
        entries.extend(offer.provenance or [])
    for entry in entries:
        evidence_id = entry.get("evidence_id")
        if evidence_id in seen:
            continue
        seen.add(evidence_id)
        rows.append(_safe(entry))
    for component in (messaging.components if messaging is not None else None) or []:
        for entry in component.provenance or []:
            evidence_id = entry.get("evidence_id")
            if evidence_id in seen:
                continue
            seen.add(evidence_id)
            rows.append(_safe(entry))
    for finding in diagnostics:
        rows.append(
            {
                "input_type": "diagnostic",
                "reference_id": finding.get("id"),
                "source": "diagnostics",
                "code": finding.get("code"),
            }
        )
    if goal is not None:
        rows.append(
            {"input_type": "business_goal", "reference_id": goal.id, "source": "business_goal"}
        )
    if decision is not None:
        rows.append(
            {
                "input_type": "strategy_decision",
                "reference_id": decision.id,
                "source": "strategy",
            }
        )
    return rows


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
        raise NotFoundError("Funnel input not found")
    return row


async def _inputs(
    session: AsyncSession, business: Business, payload: Any, settings: Any
) -> dict[str, Any]:
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
    messaging = (
        await _row(session, MessagingStrategy, business, payload.messaging_strategy_id)
        if payload.messaging_strategy_id
        else await _latest(session, MessagingStrategy, business)
    )
    if messaging is not None:
        messaging.components = list(
            await session.scalars(
                select(MessageComponent).where(
                    MessageComponent.messaging_strategy_id == messaging.id
                )
            )
        )
    research = await _latest(
        session, ResearchIntelligenceSnapshot, business, order_column="generated_at"
    )
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
    registry = get_registry()
    connections = list(
        await session.scalars(
            select(IntegrationConnection).where(
                IntegrationConnection.business_id == business.id,
                IntegrationConnection.status == "connected",
            )
        )
    )
    latest_connection: dict[str, IntegrationConnection] = {}
    for connection in connections:
        current = latest_connection.get(connection.provider)
        if current is None or (
            connection.connected_at is not None
            and (current.connected_at is None or connection.connected_at > current.connected_at)
        ):
            latest_connection[connection.provider] = connection
    return {
        "positioning": positioning,
        "offer": offer,
        "decision": decision,
        "messaging": messaging,
        "research": research,
        "range": range_obj,
        "metrics": metrics,
        "diagnostics": diagnostics,
        "goal": goal,
        "providers": tuple(registry.providers),
        "connections": latest_connection,
        "variant": payload.variant or _infer_variant(offer),
    }


def _variant_supported(inputs: dict[str, Any]) -> tuple[bool, str]:
    variant = inputs["variant"]
    signal = _VARIANT_SIGNALS[variant]
    if signal == "unsupported":
        return False, "Lead-capture mechanics are not modeled in this phase."
    if signal == "offer":
        return inputs["offer"] is not None, "The variant requires an offer candidate."
    if signal == "offer_differentiator":
        if inputs["offer"] is None:
            return False, "The variant requires an offer candidate."
        if not (inputs["positioning"] and inputs["positioning"].differentiator):
            return False, "The variant requires a positioning differentiator."
        return True, ""
    if signal == "messaging":
        if inputs["messaging"] is None:
            return False, "The variant requires a generated messaging strategy."
        return len(inputs["messaging"].components) > 0, (
            "The variant requires messaging components to anchor directions."
        )
    if signal == "research_coverage":
        snapshot = inputs["research"]
        coverage = (snapshot.coverage_json or {}) if snapshot else {}
        areas = coverage.get("areas") if isinstance(coverage, dict) else None
        count = (
            sum(1 for row in areas if row.get("status") == "covered")
            if isinstance(areas, list)
            else 0
        )
        return count >= 3, "The variant requires covered research areas."
    return True, ""


def _content_directions(variant: str) -> dict[str, str]:
    directions = {
        "awareness": "Problem and desire-led content built from stored evidence.",
        "interest": "Benefit-led content demonstrating the supported outcome.",
        "consideration": "Comparison content around the differentiator with documented proof.",
        "purchase": "Offer-focused content presenting the validated action.",
        "retention": "Content that supports repeat behaviors without performance claims.",
    }
    if variant == "product_led":
        directions["awareness"] = "Product-led content anchored on the documented problem."
        directions["interest"] = "Product-led content anchored on the supported benefit."
    elif variant == "content_led":
        directions["awareness"] = (
            "Educational content surfaced where the target searches for answers."
        )
        directions["interest"] = "Educational content demonstrating the supported outcome."
    elif variant == "education_led":
        directions["awareness"] = "Educational content built from covered research areas."
        directions["interest"] = "Educational content built from covered research areas."
    elif variant == "lead_generation":
        directions["purchase"] = (
            "Lead-focused content requires lead-capture mechanics; none modeled."
        )
    return directions


def _message_direction(stage: str, positioning: PositioningCandidate | None) -> str:
    if stage == "awareness":
        return "Lead with the documented problem and desired outcome."
    if stage == "interest":
        return "Lead with the supported benefits of the solution."
    if stage == "consideration":
        differentiator = positioning.differentiator if positioning else None
        if differentiator:
            return (
                "Lead with the supported differentiator and address documented objections "
                "with available proof."
            )
        return "Address documented objections with available proof."
    if stage == "purchase":
        return "Present the validated offer and its available action."
    return "Encourage repeat behaviors without performance claims."


def _offer_direction(stage: str, offer: OfferCandidate | None) -> str | None:
    if stage != "purchase" or offer is None:
        return None
    return "Present the validated offer with its supported proof."


def _stage_objective(stage: str, variant: str, offer: OfferCandidate | None) -> str:
    if stage == "awareness":
        return "Make the target audience aware of the documented problem and desired outcome."
    if stage == "interest":
        return "Build interest in the solution using supported benefits."
    if stage == "consideration":
        return "Enable comparison and reduce perceived risk with documented proof."
    if stage == "purchase":
        if offer is not None and offer.product_id:
            return "Convert decision-ready intent into the available product action."
        return "Enable the available action at decision-ready intent."
    return "Keep the customer engaged after the first action."


def _cta(purchase_stage: bool, offer: OfferCandidate | None) -> tuple[str | None, dict[str, Any]]:
    cta_type = "view_product" if offer is not None and offer.product_id else None
    validation = {
        "cta_type": cta_type,
        "available": cta_type is not None,
        "basis": "offer product reference" if cta_type else "no available action",
    }
    return cta_type, validation


def _kpi_status(measure: dict[str, Any] | None) -> str:
    if measure is None:
        return "unavailable"
    status = measure.get("status")
    if status in {"available", "insufficient_data", "unavailable"}:
        return status
    return "unavailable"


def _value_ref(
    measure: dict[str, Any] | None, kind: str, currency: str | None
) -> dict[str, Any] | None:
    if measure is None:
        return None
    kind = _UNIT_BY_KIND.get(kind, "count")
    ref: dict[str, Any] = {"value": _safe(measure["value"]), "unit": f"{kind}"}
    if currency:
        ref["currency"] = currency
    return ref


def _transition(
    summary: dict[str, Any],
    from_stage: str,
    to_stage: str,
    numerator: str,
    denominator: str,
    below: list[dict[str, Any]],
) -> dict[str, Any]:
    top = _measure(summary, numerator)
    bottom = _measure(summary, denominator)
    sample_gates = {
        "impressions": th.value(th.SAMPLE_MIN_IMPRESSIONS),
        "clicks": th.value(th.SAMPLE_MIN_CLICKS),
        "purchases": th.value(th.SAMPLE_MIN_PURCHASES),
    }
    if top is None or bottom is None:
        return {
            "transition": f"{numerator}/{denominator}",
            "status": "unavailable",
            "source": "metrics",
            "basis": "numerator and denominator must both be available",
            "numerator_available": top is not None,
            "denominator_available": bottom is not None,
        }
    bottom_count = _dec(bottom["value"])
    if bottom_count is None or bottom_count <= 0:
        return {
            "transition": f"{numerator}/{denominator}",
            "status": "unavailable",
            "source": "metrics",
            "basis": "denominator is zero; the rate is undefined",
        }
    gate = sample_gates.get(denominator)
    if gate is not None and bottom_count < gate:
        return {
            "transition": f"{numerator}/{denominator}",
            "status": "insufficient_data",
            "basis": f"denominator sample {bottom_count} below minimum {gate}",
        }
    rate = (_dec(top["value"]) / bottom_count).quantize(Decimal("0.0001"))
    threshold = th.value(th.FUNNEL_LOW_TRANSITION)
    label = _bottleneck_label(rate, threshold)
    if label == "likely":
        below.append(
            {
                "from": from_stage,
                "to": to_stage,
                "rate": str(rate),
                "threshold": str(threshold),
            }
        )
    return {
        "transition": f"{numerator}/{denominator}",
        "status": "available",
        "value": str(rate),
        "threshold_code": th.FUNNEL_LOW_TRANSITION,
        "threshold_value": str(threshold),
        "bottleneck": label,
    }


def _stage_status(
    stage: str,
    kpis: list[dict[str, Any]],
    exits: dict[str, Any],
    findings: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    risks: list[dict[str, Any]] = []
    if stage == "retention":
        risks.append(
            {
                "code": "no_retention_metric",
                "reason": "No observed repeat-purchase metric exists in the registry.",
            }
        )
        return "not_configured", risks
    stage_findings = [
        finding
        for finding in findings
        if finding.get("affected_stage") == stage
        or _FINDING_STAGES.get(finding.get("code")) == stage
    ]
    for finding in stage_findings:
        risks.append(
            {
                "code": finding.get("code"),
                "reason": finding.get("reason") or "Diagnostic finding affects this stage.",
                "severity": finding.get("severity"),
                "status": finding.get("status"),
                "finding_id": finding.get("id"),
            }
        )
    if any(finding.get("status") == "detected" for finding in stage_findings):
        return "warning", risks
    if any(
        finding.get("status") in {"insufficient_data", "low_data"} for finding in stage_findings
    ):
        return "insufficient_data", risks
    available = [kpi for kpi in kpis if kpi["status"] == "available"]
    if not available:
        return "unavailable", risks
    if exits.get("status") not in {None, "available"}:
        return "insufficient_data", risks
    return "healthy", risks


def _stage_conditions(
    transitions: dict[tuple[str, str], dict[str, Any]],
    stage: str,
    positions: dict[str, int],
) -> tuple[dict[str, Any], dict[str, Any]]:
    entry: dict[str, Any] = {}
    exit_condition: dict[str, Any] = {}
    for (source, target), value in transitions.items():
        if target == stage:
            entry = {"source_stage": source, **value}
        if source == stage:
            exit_condition = {"target_stage": target, **value}
    if stage == "awareness":
        entry = {"source_stage": None, "transition": "enter_funnel"}
    if stage == "retention":
        exit_condition = {"target_stage": None, "transition": "repeat_engagement"}
    return entry, exit_condition


def _build_gaps(
    inputs: dict[str, Any],
    stages: list[dict[str, Any]],
    below: list[dict[str, Any]],
    cta_validation: dict[str, Any],
    variant: str,
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    positioning = inputs["positioning"]
    offer = inputs["offer"]
    messaging = inputs["messaging"]
    decision = inputs["decision"]
    if positioning is None and messaging is None:
        gaps.append(
            {
                "gap_type": "evidence",
                "stage_from": None,
                "stage_to": None,
                "severity": "high",
                "title": "No evidence-backed strategy layer anchors the funnel",
                "description": (
                    "Neither a positioning candidate nor a messaging strategy exists; "
                    "stage directions cannot be traced to stored evidence."
                ),
                "evidence": [],
                "recommended_direction": (
                    "Build a positioning candidate and generate a messaging strategy before "
                    "using this funnel."
                ),
            }
        )
    signal_message = _variant_supported(inputs)
    if not signal_message[0] and variant != "lead_generation":
        gaps.append(
            {
                "gap_type": "variant_signal",
                "stage_from": None,
                "stage_to": None,
                "severity": "critical",
                "title": f"The {variant} variant lacks a required input",
                "description": signal_message[1],
                "evidence": [],
                "recommended_direction": (
                    "Supply the missing strategy input or choose another variant."
                ),
            }
        )
    if variant in {"ecommerce", "product_led"} and offer is None:
        gaps.append(
            {
                "gap_type": "offer",
                "stage_from": "consideration",
                "stage_to": "purchase",
                "severity": "high",
                "title": "No offer candidate exists to anchor purchase",
                "description": "The funnel has no validated offer to present at purchase intent.",
                "evidence": [],
                "recommended_direction": "Create and validate an offer candidate.",
            }
        )
    if decision is None:
        gaps.append(
            {
                "gap_type": "decision",
                "stage_from": None,
                "stage_to": None,
                "severity": "info",
                "title": "No evaluated strategy decision exists",
                "description": (
                    "Goal and performance alignment has not been evaluated for the funnel inputs."
                ),
                "evidence": [],
                "recommended_direction": "Evaluate a strategy decision to verify alignment.",
            }
        )
    if decision is not None and decision.status == "insufficient_data":
        gaps.append(
            {
                "gap_type": "decision",
                "stage_from": None,
                "stage_to": None,
                "severity": "medium",
                "title": "The strategy decision is insufficient_data",
                "description": (
                    "A strategy decision with status insufficient_data is not treated as "
                    "validated; the funnel inherits the uncertainty."
                ),
                "evidence": [{"input_type": "strategy_decision", "status": decision.status}],
                "recommended_direction": "Re-run the decision once inputs are available.",
            }
        )
    for row in below:
        gaps.append(
            {
                "gap_type": "transition",
                "stage_from": row["from"],
                "stage_to": row["to"],
                "severity": "high",
                "title": f"Likely transition bottleneck {row['from']} to {row['to']}",
                "description": (
                    f"The observed transition rate {row['rate']} is below the documented "
                    f"threshold {row['threshold']}."
                ),
                "evidence": [{"metric": "transition_rate", "value": row["rate"], "unit": "ratio"}],
                "recommended_direction": (
                    "Verify the transition with additional data before changing anything."
                ),
            }
        )
    if not cta_validation["available"]:
        gaps.append(
            {
                "gap_type": "cta",
                "stage_from": "purchase",
                "stage_to": "purchase",
                "severity": "medium",
                "title": "No available purchase action",
                "description": (
                    "The offer does not reference a product, so no purchase CTA is emitted."
                ),
                "evidence": [{"cta_type": None, "basis": cta_validation["basis"]}],
                "recommended_direction": (
                    "Anchor the offer to a product to enable the purchase action."
                ),
            }
        )
    providers = set(inputs["providers"])
    for stage in stages:
        for channel in stage["channels"]:
            if channel["channel"] not in providers:
                continue
            status = channel["status"]
            if status == "recommended":
                gaps.append(
                    {
                        "gap_type": "channel",
                        "stage_from": stage["stage"],
                        "stage_to": stage["stage"],
                        "severity": "info",
                        "title": f"{channel['channel']} integration is not connected",
                        "description": (
                            f"The {channel['channel']} integration is registered but has no "
                            "connected connection; the channel is recommended for this stage."
                        ),
                        "evidence": [],
                        "recommended_direction": "Connect the integration to enable measurement.",
                    }
                )
    return gaps


def _overall_health(
    stages: list[dict[str, Any]],
    stage_statuses: dict[str, str],
    cta_validation: dict[str, Any],
) -> tuple[str, Decimal | None, dict[str, Any]]:
    contributions: dict[str, Any] = {}
    total_weight = Decimal("0")
    weighted = Decimal("0")
    included = 0
    for stage in stages:
        status = stage_statuses[stage["stage"]]
        weight = STAGE_STATUS_WEIGHTS.get(status)
        if weight is None:
            contributions[stage["stage"]] = {"status": status, "weight": None, "excluded": True}
            continue
        contributions[stage["stage"]] = {
            "status": status,
            "weight": str(weight),
            "excluded": False,
        }
        total_weight += weight
        weighted += weight * weight
        included += 1
    score = (weighted / total_weight).quantize(Decimal("0.0001")) if total_weight else None
    if any(status == "warning" for status in stage_statuses.values()):
        bucket = "warning"
    elif any(status == "insufficient_data" for status in stage_statuses.values()):
        bucket = "insufficient_data"
    elif included == 0 or all(
        status in {"unavailable", "not_configured"} for status in stage_statuses.values()
    ):
        bucket = "unavailable"
    else:
        bucket = "healthy"
    return (
        bucket,
        score,
        {
            "bucket": bucket,
            "score": str(score) if score is not None else None,
            "stage_breakdown": contributions,
            "cta_validation": cta_validation,
            "performance_claims": "no_performance_claim",
            "rules_version": FUNNEL_RULES_VERSION,
        },
    )


def _funnel_status(
    supported: tuple[bool, str],
    variant: str,
    gaps: list[dict[str, Any]],
    score: Decimal | None,
) -> str:
    if variant == "lead_generation":
        return "invalid"
    if not supported[0]:
        return "insufficient_data"
    worst = sorted(
        [gap["severity"] for gap in gaps],
        key=lambda severity: ("critical", "high", "medium", "low", "info").index(severity),
    )
    if worst and worst[0] == "critical":
        return "needs_optimization"
    if score is None:
        return "needs_evidence"
    if score >= SCORE_RECOMMENDED and (not worst or worst[0] in {"low", "info"}):
        return "recommended"
    if score >= SCORE_VIABLE:
        return "viable"
    return "needs_optimization"


async def generate(
    session: AsyncSession, business: Business, payload: Any, settings: Any
) -> FunnelStrategy:
    inputs = await _inputs(session, business, payload, settings)
    positioning: PositioningCandidate | None = inputs["positioning"]
    offer: OfferCandidate | None = inputs["offer"]
    messaging: MessagingStrategy | None = inputs["messaging"]
    decision: StrategyDecision | None = inputs["decision"]
    variant = inputs["variant"]
    supported = _variant_supported(inputs)
    version = (
        int(
            await session.scalar(
                select(func.max(FunnelStrategy.version)).where(
                    FunnelStrategy.business_id == business.id
                )
            )
            or 0
        )
        + 1
    )
    strategy = FunnelStrategy(
        organization_id=business.organization_id,
        business_id=business.id,
        version=version,
        funnel_version=FUNNEL_VERSION,
        variant=variant,
        status="pending",
        positioning_candidate_id=positioning.id if positioning else None,
        offer_candidate_id=offer.id if offer else None,
        strategy_decision_id=decision.id if decision else None,
        messaging_strategy_id=messaging.id if messaging else None,
        input_snapshot={},
        health={},
    )
    session.add(strategy)
    await session.flush()

    transitions: dict[tuple[str, str], dict[str, Any]] = {}
    below: list[dict[str, Any]] = []
    findings = inputs["diagnostics"].get("findings", [])
    for (source, target), (numerator, denominator) in _TRANSITIONS.items():
        transitions[(source, target)] = _transition(
            inputs["metrics"], source, target, numerator, denominator, below
        )
    summary = inputs["metrics"]
    currency = summary.get("currency")
    positions = {stage: index for index, stage in enumerate(FUNNEL_STAGES)}
    directions = _content_directions(variant)
    cta_type = None
    cta_validation: dict[str, Any] = {"cta_type": None, "available": False}
    stage_rows: list[FunnelStage] = []
    stage_records: list[dict[str, Any]] = []
    for stage in FUNNEL_STAGES:
        position = positions[stage]
        cta_type, cta_validation = _cta(stage == "purchase", offer)
        kpi_rows: list[dict[str, Any]] = []
        for kpi_code, kind, role in _STAGE_KPIS[stage]:
            if kind == "unavailable":
                kpi_rows.append(
                    {
                        "kpi_code": kpi_code,
                        "kpi_kind": "condition",
                        "role": role,
                        "status": "not_configured",
                        "metric_code": None,
                        "value_ref": None,
                        "threshold_code": None,
                        "details": {
                            "reason": "No observed repeat-purchase metric exists in the registry."
                        },
                    }
                )
                continue
            measure = _measure(summary, kpi_code)
            kpi_rows.append(
                {
                    "kpi_code": kpi_code,
                    "kpi_kind": kind,
                    "role": role,
                    "status": _kpi_status(measure),
                    "metric_code": kpi_code if kind == "metric" else None,
                    "value_ref": _value_ref(measure, kind, currency),
                    "threshold_code": _KPI_THRESHOLDS.get(kpi_code),
                    "details": {"unit": _UNIT_BY_KIND.get(kind, "count")},
                }
            )
        channel_rows: list[dict[str, Any]] = []
        for priority, channel in enumerate(_STAGE_CHANNELS[stage], start=1):
            connection = inputs["connections"].get(channel)
            in_registry = channel in set(inputs["providers"])
            status = (
                "connected"
                if connection is not None
                else "recommended"
                if in_registry
                else "unsupported"
            )
            channel_rows.append(
                {
                    "channel": channel,
                    "status": status,
                    "role": "primary" if priority == 1 else "secondary",
                    "priority": priority,
                    "weight": Decimal("1.0000") if priority == 1 else Decimal("0.5000"),
                    "rationale": _CHANNEL_PURPOSES.get(
                        channel, "Channel relevant to this funnel stage."
                    ),
                    "integration_connection_id": connection.id if connection else None,
                    "evidence_refs": [],
                }
            )
        entry, exit_condition = _stage_conditions(transitions, stage, positions)
        status, risks = _stage_status(stage, kpi_rows, exit_condition, findings)
        provenance = _stage_provenance(
            positioning=positioning,
            offer=offer,
            messaging=messaging,
            decision=decision,
            goal=inputs["goal"],
            diagnostics=findings,
        )
        evidence_refs = [ref for ref in provenance if ref.get("evidence_id") is not None]
        row = FunnelStage(
            organization_id=business.organization_id,
            business_id=business.id,
            funnel_strategy_id=strategy.id,
            stage=stage,
            position=position,
            objective=_stage_objective(stage, variant, offer),
            audience_state=_AUDIENCE_STATES[stage],
            customer_problem=(
                positioning.problem if positioning and stage in {"awareness", "interest"} else None
            ),
            customer_desire=(
                positioning.promise
                if positioning and stage in {"interest", "consideration"}
                else None
            ),
            message_direction=_message_direction(stage, positioning),
            offer_direction=_offer_direction(stage, offer),
            content_direction=directions[stage],
            cta_type=cta_type if stage == "purchase" else None,
            entry_condition=_safe(entry),
            exit_condition=_safe(exit_condition),
            status=status,
            risks=_safe(risks),
            evidence_refs=_safe(evidence_refs),
            provenance=_safe(provenance),
        )
        session.add(row)
        await session.flush()
        session.add_all(
            FunnelStageChannel(
                organization_id=business.organization_id,
                business_id=business.id,
                funnel_stage_id=row.id,
                **channel_data,
            )
            for channel_data in channel_rows
        )
        session.add_all(
            FunnelStageKpi(
                organization_id=business.organization_id,
                business_id=business.id,
                funnel_stage_id=row.id,
                **kpi_data,
            )
            for kpi_data in kpi_rows
        )
        stage_rows.append(row)
        stage_records.append(
            {
                "stage": stage,
                "channels": channel_rows,
                "kpis": kpi_rows,
                "status": status,
            }
        )
    gaps = (
        []
        if variant == "lead_generation"
        else _build_gaps(inputs, stage_records, below, cta_validation, variant)
    )
    bucket, score, health = _overall_health(
        stage_records,
        {record["stage"]: record["status"] for record in stage_records},
        cta_validation,
    )
    goals_view = None
    if inputs["goal"] is not None:
        goal = inputs["goal"]
        goals_view = _safe(
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
    else:
        goals_view = {"status": "unavailable", "reason": "No active business goal exists."}
    strategy.status = _funnel_status(supported, variant, gaps, score)
    strategy.input_snapshot = _safe(
        {
            "business_id": business.id,
            "variant": variant,
            "variant_signal": _VARIANT_SIGNALS[variant],
            "funnel_rules_version": FUNNEL_RULES_VERSION,
            "positioning_version": POSITIONING_VERSION,
            "positioning_candidate_id": positioning.id if positioning else None,
            "offer_candidate_id": offer.id if offer else None,
            "strategy_decision_id": decision.id if decision else None,
            "strategy_decision_status": decision.status if decision else None,
            "messaging_version": MESSAGING_VERSION,
            "messaging_strategy_id": messaging.id if messaging else None,
            "messaging_status": messaging.status if messaging else None,
            "research_intelligence_snapshot_id": inputs["research"].id
            if inputs["research"]
            else None,
            "research_intelligence_version": inputs["research"].intelligence_version
            if inputs["research"]
            else None,
            "evidence_ids": [ref.get("evidence_id") for ref in provenance if ref.get("evidence_id")]
            if stage_records
            else [],
            "metrics_range": _range_view(inputs["range"]),
            "diagnostics_range": _range_view(inputs["range"]),
            "diagnostic_ids": [finding.get("id") for finding in findings],
            "business_goal": goals_view,
            "integrations": {
                provider: {
                    "status": "connected" if provider in inputs["connections"] else "recommended"
                }
                for provider in inputs["providers"]
            },
        }
    )
    strategy.health = _safe(health)
    session.add_all(
        FunnelGap(
            organization_id=business.organization_id,
            business_id=business.id,
            funnel_strategy_id=strategy.id,
            gap_type=gap["gap_type"],
            stage_from=gap["stage_from"],
            stage_to=gap["stage_to"],
            severity=gap["severity"],
            title=gap["title"],
            description=gap["description"],
            evidence=_safe(gap["evidence"]),
            recommended_direction=gap["recommended_direction"],
            status="open",
        )
        for gap in gaps
    )
    await session.commit()
    await session.refresh(strategy)
    return strategy


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


async def get_strategy(
    session: AsyncSession, business: Business, strategy_id: uuid.UUID
) -> FunnelStrategy:
    return await _row(session, FunnelStrategy, business, strategy_id)


async def latest(session: AsyncSession, business: Business) -> FunnelStrategy | None:
    return await _latest(session, FunnelStrategy, business)


async def stages(session: AsyncSession, strategy: FunnelStrategy) -> list[FunnelStage]:
    return list(
        await session.scalars(
            select(FunnelStage)
            .where(FunnelStage.funnel_strategy_id == strategy.id)
            .order_by(FunnelStage.position)
        )
    )


async def channels(session: AsyncSession, stage_row: FunnelStage) -> list[FunnelStageChannel]:
    return list(
        await session.scalars(
            select(FunnelStageChannel).where(FunnelStageChannel.funnel_stage_id == stage_row.id)
        )
    )


async def kpis(session: AsyncSession, stage_row: FunnelStage) -> list[FunnelStageKpi]:
    return list(
        await session.scalars(
            select(FunnelStageKpi).where(FunnelStageKpi.funnel_stage_id == stage_row.id)
        )
    )


async def gaps(session: AsyncSession, strategy: FunnelStrategy) -> list[FunnelGap]:
    return list(
        await session.scalars(
            select(FunnelGap)
            .where(FunnelGap.funnel_strategy_id == strategy.id)
            .order_by(FunnelGap.created_at)
        )
    )


async def versions(session: AsyncSession, business: Business) -> list[FunnelStrategy]:
    return list(
        await session.scalars(
            select(FunnelStrategy)
            .where(
                FunnelStrategy.organization_id == business.organization_id,
                FunnelStrategy.business_id == business.id,
            )
            .order_by(desc(FunnelStrategy.version))
        )
    )
