"""Pydantic v2 schemas for the creative intelligence API contracts.

API contracts stay explicit: ORM models are never exposed directly. All
models are tenant/business-scoped by their parent endpoints.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WhitespaceGap(BaseModel):
    """A single creative whitespace gap identified."""

    observed_competitor_pattern: str = Field(description="What competitors are doing")
    potential_gap: str = Field(description="The gap opportunity")
    hypothesis: str = Field(description="Testable hypothesis for the gap")
    confidence: float = Field(ge=0.0, le=1.0)
    strength: str = Field(description="Strength classification: low/medium/high")


class WhitespaceOut(BaseModel):
    """Deterministic whitespace identification result."""

    gaps: list[WhitespaceGap] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    strength: str
    whitespace_summary: str


class CreativeConceptCreate(BaseModel):
    strategy_version: str = "v1"
    positioning_reference: UUID | None = None
    offer_reference: UUID | None = None
    messaging_reference: UUID | None = None
    funnel_reference: UUID | None = None
    funnel_stage: str | None = None
    audience: str | None = None
    angle: str | None = None
    message: str | None = None
    hook_direction: str | None = None
    creative_format: str
    creative_type: str | None = None
    offer_direction: str | None = None
    cta: str | None = None
    visual_direction: str | None = None
    copy_direction: str | None = None
    primary_emotion: str | None = None
    secondary_emotion: str | None = None
    objection: str | None = None
    reason_to_believe: str | None = None
    testing_role: str | None = None
    success_metric: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    risks: list[dict[str, Any]] = Field(default_factory=list)


class CreativeConceptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    business_id: UUID
    strategy_version: str
    positioning_reference: UUID | None = None
    offer_reference: UUID | None = None
    messaging_reference: UUID | None = None
    funnel_reference: UUID | None = None
    funnel_stage: str | None = None
    audience: str | None = None
    angle: str | None = None
    message: str | None = None
    hook_direction: str | None = None
    creative_format: str
    creative_type: str | None = None
    offer_direction: str | None = None
    cta: str | None = None
    visual_direction: str | None = None
    copy_direction: str | None = None
    primary_emotion: str | None = None
    secondary_emotion: str | None = None
    objection: str | None = None
    reason_to_believe: str | None = None
    testing_role: str | None = None
    success_metric: str | None = None
    evidence: dict[str, Any]
    risks: list[dict[str, Any]]
    status: str
    created_at: datetime
    updated_at: datetime


class CreativeConceptPage(BaseModel):
    items: list[CreativeConceptRead]
    next_cursor: UUID | None = None


class CreativeStrategyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    business_id: UUID
    strategy_id: str
    version: str
    status: str
    positioning_reference: UUID | None = None
    offer_reference: UUID | None = None
    messaging_reference: UUID | None = None
    funnel_reference: UUID | None = None
    research_reference: UUID | None = None
    strategy_decision_reference: UUID | None = None
    creative_intelligence_reference: UUID | None = None
    audience_coverage: str | None = None
    funnel_coverage: str | None = None
    rules_version: str | None = None
    created_at: datetime
    updated_at: datetime


class CreativeTestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    business_id: UUID
    test_id: str
    name: str
    objective: str
    test_variable: str
    control_variables: dict[str, Any]
    variants: list[dict[str, Any]]
    hypothesis: str
    based_on: str | None = None
    success_metric: str | None = None
    minimum_data_requirement: dict[str, Any] | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class CreativeTestVariantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    business_id: UUID
    test_id: str
    variant_id: str
    test_variable_value: str
    control_state_frozen_at: datetime
    created_at: datetime


class CreativePortfolioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    business_id: UUID
    portfolio_id: str
    name: str
    category: str
    description: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
