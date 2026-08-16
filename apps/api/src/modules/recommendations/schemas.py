"""Typed API contracts for the deterministic decision engine (Phase 4B).

Every decision is a review recommendation — never an action. The response
carries structured evidence (metrics, thresholds, funnel, facts), the
deterministic evidence strength, the diagnostics/forecast/goal references
that were used, the metric snapshot at decision time, the rules version and
safe review suggestions (translation keys, advisory only).

Money is Decimal (serialized as strings by the app encoder). Snapshots are
JSONB in the database and plain dicts on the wire.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from src.modules.metrics.schemas import RangeRead


class EvidenceMetricRead(BaseModel):
    code: str
    current: Decimal | None = None
    previous: Decimal | None = None
    unit: str | None = None
    status: str = "unavailable"
    reason: str | None = None


class EvidenceThresholdRead(BaseModel):
    code: str
    operator: str
    value: Decimal
    unit: str | None = None


class EvidenceComparisonRead(BaseModel):
    change_percent: Decimal | None = None
    status: str = "unavailable"
    reason: str | None = None


class EvidenceFunnelRead(BaseModel):
    from_stage: str | None = None
    to_stage: str | None = None
    conversion_rate: Decimal | None = None
    previous_rate: Decimal | None = None


class EvidenceFactRead(BaseModel):
    code: str
    value: Decimal | str
    unit: str | None = None


class EvidenceItemRead(BaseModel):
    metric: EvidenceMetricRead | None = None
    threshold: EvidenceThresholdRead | None = None
    comparison: EvidenceComparisonRead | None = None
    funnel: EvidenceFunnelRead | None = None
    facts: list[EvidenceFactRead] = Field(default_factory=list)
    rule: str | None = None
    source: str | None = None


class DecisionEvidenceRead(BaseModel):
    primary_reason: str
    evidence_strength: str
    evidence_items: list[EvidenceItemRead] = Field(default_factory=list)
    diagnostics_refs: list[str] = Field(default_factory=list)
    forecast_refs: list[str] = Field(default_factory=list)
    goal_refs: list[str] = Field(default_factory=list)


class DiagnosticReferenceRead(BaseModel):
    """A diagnostic finding referenced by the decision (never re-computed)."""
    id: str
    code: str
    category: str
    severity: str
    status: str


class DecisionRead(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID | None = None
    entity_name: str | None = None
    decision: str
    evidence_strength: str
    primary_reason: str
    diagnostics: list[DiagnosticReferenceRead] = Field(default_factory=list)
    evidence: DecisionEvidenceRead
    review_suggestions: list[str] = Field(default_factory=list)
    metrics_snapshot: dict[str, Any] = Field(default_factory=dict)
    forecast_snapshot: dict[str, Any] | None = None
    range: RangeRead
    created_at: datetime
    rules_version: str


class DecisionSummaryRead(BaseModel):
    business_id: uuid.UUID
    total: int
    scale_review: int = 0
    optimize: int = 0
    maintain: int = 0
    kill_review: int = 0
    learning: int = 0
    insufficient_data: int = 0
    tracking_issue: int = 0
    data_quality_issue: int = 0
    by_decision: dict[str, int] = Field(default_factory=dict)
    by_entity_type: dict[str, int] = Field(default_factory=dict)


class DecisionsRead(BaseModel):
    business_id: uuid.UUID
    currency: str
    range: RangeRead
    decisions: list[DecisionRead] = Field(default_factory=list)
    summary: DecisionSummaryRead


class GenerateRequest(BaseModel):
    """Generate (recompute and persist) recommendations.

    POST only calculates and stores decisions; it never executes any
    action on providers or budgets.
    """
    range_kind: str = Field(default="last_30_days")
    date_from: date | None = None
    date_to: date | None = None


__all__ = [
    "DecisionRead",
    "DecisionSummaryRead",
    "DecisionsRead",
    "GenerateRequest",
    "DecisionEvidenceRead",
    "EvidenceItemRead",
    "EvidenceMetricRead",
    "EvidenceThresholdRead",
    "EvidenceComparisonRead",
    "EvidenceFunnelRead",
    "EvidenceFactRead",
    "DiagnosticReferenceRead",
]