from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

StrategyStatus = Literal[
    "draft", "validated", "recommended", "archived", "insufficient_data", "invalid"
]


class ProvenanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evidence_id: uuid.UUID | None = None
    finding_id: uuid.UUID | None = None
    source_id: uuid.UUID | None = None
    snapshot_id: uuid.UUID | None = None
    source_title: str | None = None
    statement: str | None = None
    data_source: str | None = None


class PositioningCandidateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    candidate_type: str = Field(default="problem_led", min_length=1, max_length=30)
    target_customer: str | None = None
    problem: str | None = None
    solution: str | None = None
    differentiator: str | None = None
    promise: str | None = None
    supporting_benefits: list[str] = Field(default_factory=list)
    proof_points: list[str] = Field(default_factory=list)
    objections_addressed: list[str] = Field(default_factory=list)
    evidence_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    classification: Literal["observed", "inferred", "hypothesis"] | None = None
    assumptions: list[str] = Field(default_factory=list)


class PositioningCandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    candidate_type: str
    target_customer: str | None
    problem: str | None
    solution: str | None
    differentiator: str | None
    promise: str | None
    supporting_benefits: list[str]
    proof_points: list[str]
    objections_addressed: list[str]
    positioning_statement: str | None
    classification: str
    strength: str
    score: Decimal | None
    score_breakdown: dict[str, Any] = Field(default_factory=dict)
    status: str
    assumptions: list[str]
    risks: list[dict[str, Any]]
    provenance: list[ProvenanceRead]
    strategy_version: str


class PositioningResponse(BaseModel):
    strategy_id: uuid.UUID | None
    version: int | None
    strategy_version: str
    status: str
    selected_candidate_id: uuid.UUID | None
    candidates: list[PositioningCandidateRead]
    coverage: dict[str, Any]
    missing_research_areas: list[dict[str, Any]]


class PositioningVersionsResponse(BaseModel):
    versions: list[PositioningResponse]


class OfferCandidateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    product_id: uuid.UUID | None = None
    bundle_id: uuid.UUID | None = None
    price_override: Decimal | None = Field(default=None, ge=0)
    discount_id: uuid.UUID | None = None
    shipping_rule_id: uuid.UUID | None = None
    guarantee: dict[str, Any] | None = None
    bonus: dict[str, Any] | None = None
    urgency: dict[str, Any] | None = None
    risk_reversal: dict[str, Any] | None = None
    proof: list[str] = Field(default_factory=list)
    evidence_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    classification: Literal["observed", "inferred", "hypothesis"] | None = None
    assumptions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def one_anchor(self) -> OfferCandidateCreate:
        if (self.product_id is None) == (self.bundle_id is None):
            raise ValueError("exactly one of product_id or bundle_id is required")
        return self


class OfferCandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    product_id: uuid.UUID | None
    bundle_id: uuid.UUID | None
    components: dict[str, Any]
    economics: dict[str, Any]
    classification: str
    strength: str
    score: Decimal | None
    score_breakdown: dict[str, Any] = Field(default_factory=dict)
    status: str
    assumptions: list[str]
    risks: list[dict[str, Any]]
    provenance: list[ProvenanceRead]
    strategy_version: str


class OfferResponse(BaseModel):
    strategy_id: uuid.UUID | None
    version: int | None
    strategy_version: str
    status: str
    selected_candidate_id: uuid.UUID | None
    candidates: list[OfferCandidateRead]
    coverage: dict[str, Any]
    missing_research_areas: list[dict[str, Any]]


class OfferVersionsResponse(BaseModel):
    versions: list[OfferResponse]


class OfferValidateRequest(BaseModel):
    candidate_id: uuid.UUID


class StrategySummaryResponse(BaseModel):
    positioning: PositioningResponse
    offers: OfferResponse
    missing_research_areas: list[dict[str, Any]]


class StrategySnapshotResponse(BaseModel):
    id: uuid.UUID
    strategy_kind: str
    strategy_version: str
    research_intelligence_version: str | None
    input_snapshot_refs: dict[str, Any]
    coverage: dict[str, Any]
    missing_research_areas: list[dict[str, Any]]
    created_at: Any


class StrategyDecisionEvaluateRequest(BaseModel):
    candidate_type: Literal["positioning", "offer"]
    candidate_id: uuid.UUID
    range_kind: Literal[
        "today",
        "yesterday",
        "last_7_days",
        "last_14_days",
        "last_30_days",
        "month_to_date",
        "custom",
    ] = "last_30_days"
    period_start: date | None = None
    period_end: date | None = None
    forecast_id: uuid.UUID | None = None
    simulation_id: uuid.UUID | None = None


class StrategyDecisionReasonRead(BaseModel):
    type: str
    severity: str
    statement: str
    source: str
    reference_id: uuid.UUID | None = None


class StrategyDecisionRead(BaseModel):
    id: uuid.UUID
    candidate_type: str
    candidate_id: uuid.UUID
    strategy_version: str
    decision_rules_version: str
    status: str
    overall_score: Decimal | None = None
    input_snapshot: dict[str, Any]
    evaluation: dict[str, Any]
    reasons: list[StrategyDecisionReasonRead]
    provenance: list[dict[str, Any]]
    created_at: datetime


class StrategyDecisionListResponse(BaseModel):
    decisions: list[StrategyDecisionRead]


class StrategyDecisionProvenanceResponse(BaseModel):
    decision_id: uuid.UUID
    candidate_type: str
    candidate_id: uuid.UUID
    provenance: list[dict[str, Any]]


class MessagingGenerateRequest(BaseModel):
    positioning_candidate_id: uuid.UUID | None = None
    offer_candidate_id: uuid.UUID | None = None
    strategy_decision_id: uuid.UUID | None = None


class MessageComponentRead(BaseModel):
    id: uuid.UUID
    component_type: str
    statement: str
    classification: str
    strength: str
    claim_status: str
    status: str
    funnel_stage: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[dict[str, Any]]
    provenance: list[dict[str, Any]]


class MessageAngleRead(BaseModel):
    id: uuid.UUID
    name: str
    angle_type: str
    core_message: str
    hook_direction: str
    supporting_points: list[str]
    cta_type: str | None = None
    funnel_stage: str
    strength: str
    status: str
    evidence_refs: list[dict[str, Any]]


class MessagingStrategyRead(BaseModel):
    id: uuid.UUID
    version: int
    messaging_version: str
    status: str
    positioning_candidate_id: uuid.UUID | None = None
    offer_candidate_id: uuid.UUID | None = None
    strategy_decision_id: uuid.UUID | None = None
    input_snapshot: dict[str, Any]
    core_message: dict[str, Any]
    quality: dict[str, Any]
    components: list[MessageComponentRead] = Field(default_factory=list)
    angles: list[MessageAngleRead] = Field(default_factory=list)
    created_at: datetime


class MessagingVersionsResponse(BaseModel):
    versions: list[MessagingStrategyRead]


class MessagingProvenanceResponse(BaseModel):
    messaging_strategy_id: uuid.UUID
    provenance: list[dict[str, Any]]


FunnelVariant = Literal[
    "direct_response",
    "content_led",
    "product_led",
    "education_led",
    "lead_generation",
    "ecommerce",
]


class FunnelGenerateRequest(BaseModel):
    positioning_candidate_id: uuid.UUID | None = None
    offer_candidate_id: uuid.UUID | None = None
    strategy_decision_id: uuid.UUID | None = None
    messaging_strategy_id: uuid.UUID | None = None
    variant: FunnelVariant | None = None
    range_kind: Literal[
        "today",
        "yesterday",
        "last_7_days",
        "last_14_days",
        "last_30_days",
        "month_to_date",
        "custom",
    ] = "last_30_days"
    period_start: date | None = None
    period_end: date | None = None


class FunnelStageChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    channel: str
    status: str
    role: str
    priority: int
    weight: Decimal | None = None
    rationale: str
    integration_connection_id: uuid.UUID | None = None
    evidence_refs: list[dict[str, Any]]


class FunnelStageKpiRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kpi_code: str
    kpi_kind: str
    role: str
    status: str
    metric_code: str | None = None
    value_ref: dict[str, Any] | None = None
    threshold_code: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class FunnelStageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    stage: str
    position: int
    objective: str
    audience_state: str
    customer_problem: str | None = None
    customer_desire: str | None = None
    message_direction: str
    offer_direction: str | None = None
    content_direction: str
    cta_type: str | None = None
    entry_condition: dict[str, Any] = Field(default_factory=dict)
    exit_condition: dict[str, Any] = Field(default_factory=dict)
    status: str
    risks: list[dict[str, Any]]
    evidence_refs: list[dict[str, Any]]
    provenance: list[dict[str, Any]]
    channels: list[FunnelStageChannelRead] = Field(default_factory=list)
    kpis: list[FunnelStageKpiRead] = Field(default_factory=list)


class FunnelGapRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    gap_type: str
    stage_from: str | None = None
    stage_to: str | None = None
    severity: str
    title: str
    description: str
    evidence: list[dict[str, Any]]
    recommended_direction: str
    status: str


class FunnelStrategyRead(BaseModel):
    id: uuid.UUID
    version: int
    funnel_version: str
    variant: str
    status: str
    positioning_candidate_id: uuid.UUID | None = None
    offer_candidate_id: uuid.UUID | None = None
    strategy_decision_id: uuid.UUID | None = None
    messaging_strategy_id: uuid.UUID | None = None
    input_snapshot: dict[str, Any]
    health: dict[str, Any]
    stages: list[FunnelStageRead] = Field(default_factory=list)
    gaps: list[FunnelGapRead] = Field(default_factory=list)
    created_at: datetime


class FunnelVersionsResponse(BaseModel):
    versions: list[FunnelStrategyRead]


class FunnelProvenanceResponse(BaseModel):
    funnel_strategy_id: uuid.UUID
    provenance: list[dict[str, Any]]
