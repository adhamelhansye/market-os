"""Structured evidence model for diagnostic findings.

Every finding references actual metric values, actual comparison values
where available, actual thresholds, the concrete entity, the date range and
provenance. No prose is stored as the source of truth: the UI renders
translation keys (`title_key`/`description_key`) over this evidence.

Findings are computed deterministically on request (no persistence, see
docs/architecture/diagnostics.md), so their id is a stable fingerprint:
the same business/entity/rule/date-range always produces the same id.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from src.modules.metrics.kpi_engine import STATUS_AVAILABLE, Comparison

# Entity types the diagnostic engine understands.
ENTITY_TYPE_BUSINESS = "business"
ENTITY_TYPE_AD_ACCOUNT = "ad_account"
ENTITY_TYPE_CAMPAIGN = "campaign"
ENTITY_TYPE_AD_SET = "ad_set"
ENTITY_TYPE_AD = "ad"
ENTITY_TYPE_PRODUCT = "product"
ENTITY_TYPE_FUNNEL_STAGE = "funnel_stage"

ENTITY_TYPES: tuple[str, ...] = (
    ENTITY_TYPE_BUSINESS,
    ENTITY_TYPE_AD_ACCOUNT,
    ENTITY_TYPE_CAMPAIGN,
    ENTITY_TYPE_AD_SET,
    ENTITY_TYPE_AD,
    ENTITY_TYPE_PRODUCT,
    ENTITY_TYPE_FUNNEL_STAGE,
)

# Finding lifecycle statuses. Detection-only in this phase.
STATUS_DETECTED = "detected"
STATUS_RESOLVED = "resolved"
STATUS_INSUFFICIENT_DATA = "insufficient_data"

# Informational review flags — diagnostics only, never actions.
REVIEW_READY = "ready_for_review"
REVIEW_REQUIRED = "review_required"

CATEGORY_TRAFFIC = "traffic"
CATEGORY_CREATIVE = "creative"
CATEGORY_CONVERSION = "conversion"
CATEGORY_OFFER = "offer"
CATEGORY_FUNNEL = "funnel"
CATEGORY_ECONOMICS = "economics"
CATEGORY_TRACKING = "tracking"
CATEGORY_DATA_QUALITY = "data_quality"
CATEGORY_PERFORMANCE = "performance"
CATEGORY_SCALING_READINESS = "scaling_readiness"

CATEGORIES: tuple[str, ...] = (
    CATEGORY_TRAFFIC,
    CATEGORY_CREATIVE,
    CATEGORY_CONVERSION,
    CATEGORY_OFFER,
    CATEGORY_FUNNEL,
    CATEGORY_ECONOMICS,
    CATEGORY_TRACKING,
    CATEGORY_DATA_QUALITY,
    CATEGORY_PERFORMANCE,
    CATEGORY_SCALING_READINESS,
)


@dataclass(frozen=True)
class MetricEvidence:
    """The metric a finding observes, with its previous-period value."""

    code: str
    current: Decimal | None
    previous: Decimal | None = None


@dataclass(frozen=True)
class ThresholdEvidence:
    """The exact threshold that was tested (registry or dynamic target)."""

    code: str
    operator: str  # lt | lte | gt | gte | eq
    value: Decimal
    unit: str = "ratio"


@dataclass(frozen=True)
class ComparisonEvidence:
    """Relative change vs the previous period (never fabricated)."""

    change_percent: Decimal | None
    status: str = STATUS_AVAILABLE
    reason: str | None = None

    @classmethod
    def of(cls, current: Decimal | None, previous: Decimal | None) -> ComparisonEvidence:
        comparison = Comparison.of(current, previous)
        percent = comparison.percentage_change
        value = percent.value if percent and percent.status == STATUS_AVAILABLE else None
        return cls(
            change_percent=value,
            status=percent.status if percent else STATUS_AVAILABLE,
            reason=percent.reason if percent else None,
        )


@dataclass(frozen=True)
class FunnelEvidence:
    """The observed transition a funnel finding references."""

    from_stage: str
    to_stage: str
    conversion_rate: Decimal | None
    previous_rate: Decimal | None = None


@dataclass(frozen=True)
class Fact:
    """An observed number the finding references (spend, purchases, ...)."""

    code: str
    value: Decimal | None
    unit: str = "count"


@dataclass(frozen=True)
class Evidence:
    metric: MetricEvidence | None = None
    threshold: ThresholdEvidence | None = None
    comparison: ComparisonEvidence | None = None
    funnel: FunnelEvidence | None = None
    facts: tuple[Fact, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Finding:
    """A deterministic diagnostic finding.

    `id` is the stable fingerprint (same entity/rule/range → same id), used
    downstream for deduplication. `status` is the lifecycle status
    (detection-only in this phase); `review_status` is an informational
    flag (ready_for_review / review_required) — diagnostics only.
    """

    id: str
    business_id: uuid.UUID
    business_name: str
    entity_type: str
    entity_id: uuid.UUID | None
    entity_name: str | None
    category: str
    code: str
    severity: str
    status: str
    title_key: str
    description_key: str
    reason: str | None
    evidence: Evidence
    affected_stage: str | None
    range_start: date
    range_end: date
    currency: str
    review_status: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "business_id": self.business_id,
            "business_name": self.business_name,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "category": self.category,
            "code": self.code,
            "severity": self.severity,
            "status": self.status,
            "title_key": self.title_key,
            "description_key": self.description_key,
            "reason": self.reason,
            "evidence": {
                "metric": {
                    "code": self.evidence.metric.code if self.evidence.metric else None,
                    "current": self.evidence.metric.current if self.evidence.metric else None,
                    "previous": self.evidence.metric.previous if self.evidence.metric else None,
                },
                "threshold": {
                    "code": self.evidence.threshold.code if self.evidence.threshold else None,
                    "operator": (
                        self.evidence.threshold.operator if self.evidence.threshold else None
                    ),
                    "value": self.evidence.threshold.value if self.evidence.threshold else None,
                    "unit": self.evidence.threshold.unit if self.evidence.threshold else None,
                },
                "comparison": {
                    "change_percent": self.evidence.comparison.change_percent
                    if self.evidence.comparison
                    else None,
                    "status": self.evidence.comparison.status if self.evidence.comparison else None,
                    "reason": self.evidence.comparison.reason if self.evidence.comparison else None,
                },
                "funnel": {
                    "from_stage": self.evidence.funnel.from_stage if self.evidence.funnel else None,
                    "to_stage": self.evidence.funnel.to_stage if self.evidence.funnel else None,
                    "conversion_rate": self.evidence.funnel.conversion_rate
                    if self.evidence.funnel
                    else None,
                    "previous_rate": self.evidence.funnel.previous_rate
                    if self.evidence.funnel
                    else None,
                },
                "facts": [
                    {"code": fact.code, "value": fact.value, "unit": fact.unit}
                    for fact in self.evidence.facts
                ],
            },
            "affected_stage": self.affected_stage,
            "range": {"start": self.range_start, "end": self.range_end},
            "currency": self.currency,
            "review_status": self.review_status,
        }


def finding_fingerprint(
    *,
    business_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID | None,
    code: str,
    range_start: date,
    range_end: date,
) -> str:
    """Stable deterministic id for a finding (see module docstring)."""
    material = "|".join(
        (
            str(business_id),
            entity_type,
            str(entity_id) if entity_id else "",
            code,
            str(range_start),
            str(range_end),
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


__all__ = [
    "ENTITY_TYPE_BUSINESS",
    "ENTITY_TYPE_AD_ACCOUNT",
    "ENTITY_TYPE_CAMPAIGN",
    "ENTITY_TYPE_AD_SET",
    "ENTITY_TYPE_AD",
    "ENTITY_TYPE_PRODUCT",
    "ENTITY_TYPE_FUNNEL_STAGE",
    "ENTITY_TYPES",
    "STATUS_DETECTED",
    "STATUS_RESOLVED",
    "STATUS_INSUFFICIENT_DATA",
    "REVIEW_READY",
    "REVIEW_REQUIRED",
    "CATEGORY_TRAFFIC",
    "CATEGORY_CREATIVE",
    "CATEGORY_CONVERSION",
    "CATEGORY_OFFER",
    "CATEGORY_FUNNEL",
    "CATEGORY_ECONOMICS",
    "CATEGORY_TRACKING",
    "CATEGORY_DATA_QUALITY",
    "CATEGORY_PERFORMANCE",
    "CATEGORY_SCALING_READINESS",
    "CATEGORIES",
    "MetricEvidence",
    "ThresholdEvidence",
    "ComparisonEvidence",
    "FunnelEvidence",
    "Fact",
    "Evidence",
    "Finding",
    "finding_fingerprint",
]