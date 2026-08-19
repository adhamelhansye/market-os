from __future__ import annotations

import uuid
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
