"""Typed API contracts for diagnostics endpoints.

Findings are structured: they carry evidence (metric values, thresholds,
comparisons, funnel transitions, observed facts) and translation keys for
the UI — never generated prose as the source of truth. Money and ratios are
Decimal (serialized as strings by the app encoder); value fields may be
NULL when a comparison was not computable.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field

from src.modules.metrics.schemas import CampaignMetrics, ProviderQuality, RangeRead


class MetricEvidenceRead(BaseModel):
    code: str | None = None
    current: Decimal | None = None
    previous: Decimal | None = None


class ThresholdEvidenceRead(BaseModel):
    code: str | None = None
    operator: str | None = None  # lt | lte | gt | gte | eq
    value: Decimal | None = None
    unit: str = "ratio"


class ComparisonEvidenceRead(BaseModel):
    change_percent: Decimal | None = None
    status: str = "available"
    reason: str | None = None


class FunnelEvidenceRead(BaseModel):
    from_stage: str | None = None
    to_stage: str | None = None
    conversion_rate: Decimal | None = None
    previous_rate: Decimal | None = None


class FactRead(BaseModel):
    code: str
    value: Decimal | None = None
    unit: str = "count"


class EvidenceRead(BaseModel):
    metric: MetricEvidenceRead | None = None
    threshold: ThresholdEvidenceRead | None = None
    comparison: ComparisonEvidenceRead | None = None
    funnel: FunnelEvidenceRead | None = None
    facts: list[FactRead] = Field(default_factory=list)


class FindingRead(BaseModel):
    id: str
    business_id: uuid.UUID
    business_name: str
    entity_type: str
    entity_id: uuid.UUID | None = None
    entity_name: str | None = None
    category: str
    code: str
    severity: str
    status: str
    title_key: str
    description_key: str
    reason: str | None = None
    evidence: EvidenceRead
    affected_stage: str | None = None
    range: RangeRead
    currency: str
    review_status: str | None = None


class ScalingReadinessRead(BaseModel):
    status: str
    ready_for_review: bool = False
    gates: list[FactRead] = Field(default_factory=list)


class CampaignStateRead(BaseModel):
    campaign_id: uuid.UUID
    name: str | None = None
    performance_state: str
    scaling_readiness: ScalingReadinessRead | None = None
    finding_count: int = 0
    highest_severity: str | None = None


class DiagnosticsSummaryRead(BaseModel):
    total_findings: int
    critical: int
    high: int
    medium: int
    low: int
    info: int
    insufficient_data: int
    affected_entities: int


class DiagnosticsRead(BaseModel):
    business_id: uuid.UUID
    currency: str
    timezone: str
    range: RangeRead
    findings: list[FindingRead]
    campaign_states: list[CampaignStateRead]
    summary: DiagnosticsSummaryRead


class CampaignDiagnosticsRead(BaseModel):
    business_id: uuid.UUID
    currency: str
    timezone: str
    range: RangeRead
    campaign: CampaignMetrics
    performance_state: str
    scaling_readiness: ScalingReadinessRead
    findings: list[FindingRead]
    data_quality: ProviderQuality | None = None