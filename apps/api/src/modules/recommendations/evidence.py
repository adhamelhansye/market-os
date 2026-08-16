"""Structured evidence types for decisions.

Every decision must contain structured evidence items. No prose generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class EvidenceMetric:
    """Current and previous metric values for comparison."""
    code: str
    current: Decimal | None = None
    previous: Decimal | None = None
    unit: str | None = None
    status: str = "unavailable"
    reason: str | None = None


@dataclass(frozen=True)
class EvidenceThreshold:
    """Threshold that was evaluated."""
    code: str
    operator: str  # "lt", "lte", "gt", "gte", "eq"
    value: Decimal
    unit: str | None = None


@dataclass(frozen=True)
class EvidenceComparison:
    """Period-over-period comparison."""
    change_percent: Decimal | None = None
    status: str = "unavailable"
    reason: str | None = None


@dataclass(frozen=True)
class EvidenceFunnel:
    """Funnel bottleneck evidence."""
    from_stage: str | None = None
    to_stage: str | None = None
    conversion_rate: Decimal | None = None
    previous_rate: Decimal | None = None


@dataclass(frozen=True)
class EvidenceFact:
    """Additional supporting facts."""
    code: str
    value: Decimal | str
    unit: str | None = None


@dataclass(frozen=True)
class EvidenceItem:
    """A single piece of structured evidence supporting a decision."""
    metric: EvidenceMetric | None = None
    threshold: EvidenceThreshold | None = None
    comparison: EvidenceComparison | None = None
    funnel: EvidenceFunnel | None = None
    facts: list[EvidenceFact] = field(default_factory=list)
    rule: str | None = None
    source: str | None = None  # "metrics", "diagnostics", "forecast", "economics", "goals"

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API response and JSONB persistence.

        Decimal values become strings (money never floats; JSONB has no
        Decimal type). Response schemas coerce them back to Decimal.
        """
        return {
            "metric": self._metric_dict(),
            "threshold": self._threshold_dict(),
            "comparison": self._comparison_dict(),
            "funnel": self._funnel_dict(),
            "facts": self._facts_dict(),
            "rule": self.rule,
            "source": self.source,
        }

    def _metric_dict(self) -> dict[str, Any] | None:
        if self.metric is None:
            return None
        data = dict(self.metric.__dict__)
        data["current"] = _json_safe(data.get("current"))
        data["previous"] = _json_safe(data.get("previous"))
        return data

    def _threshold_dict(self) -> dict[str, Any] | None:
        if self.threshold is None:
            return None
        data = dict(self.threshold.__dict__)
        data["value"] = _json_safe(data["value"])
        return data

    def _comparison_dict(self) -> dict[str, Any] | None:
        if self.comparison is None:
            return None
        data = dict(self.comparison.__dict__)
        data["change_percent"] = _json_safe(data.get("change_percent"))
        return data

    def _funnel_dict(self) -> dict[str, Any] | None:
        if self.funnel is None:
            return None
        data = dict(self.funnel.__dict__)
        data["conversion_rate"] = _json_safe(data.get("conversion_rate"))
        data["previous_rate"] = _json_safe(data.get("previous_rate"))
        return data

    def _facts_dict(self) -> list[dict[str, Any]]:
        facts: list[dict[str, Any]] = []
        for fact in self.facts:
            data = dict(fact.__dict__)
            data["value"] = _json_safe(data["value"])
            facts.append(data)
        return facts


def _json_safe(value: Any) -> Any:
    """Decimal → str for JSONB persistence; everything else passes through."""
    if isinstance(value, Decimal):
        return str(value)
    return value


@dataclass(frozen=True)
class DecisionEvidence:
    """Complete evidence bundle for a decision."""
    primary_reason: str
    evidence_items: list[EvidenceItem]
    evidence_strength: str  # insufficient, weak, moderate, strong
    diagnostics_refs: list[str] = field(default_factory=list)  # finding IDs
    forecast_refs: list[str] = field(default_factory=list)  # forecast metric codes
    goal_refs: list[str] = field(default_factory=list)  # goal types

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API response."""
        return {
            "primary_reason": self.primary_reason,
            "evidence_strength": self.evidence_strength,
            "evidence_items": [e.to_dict() for e in self.evidence_items],
            "diagnostics_refs": self.diagnostics_refs,
            "forecast_refs": self.forecast_refs,
            "goal_refs": self.goal_refs,
        }


# --- Helper functions for building evidence -----------------------------------

def make_metric_evidence(
    code: str,
    current: Decimal | None,
    previous: Decimal | None = None,
    unit: str | None = None,
    status: str = "available",
    reason: str | None = None,
) -> EvidenceMetric:
    return EvidenceMetric(
        code=code,
        current=current,
        previous=previous,
        unit=unit,
        status=status,
        reason=reason,
    )


def make_threshold_evidence(
    code: str,
    operator: str,
    value: Decimal,
    unit: str | None = None,
) -> EvidenceThreshold:
    return EvidenceThreshold(
        code=code,
        operator=operator,
        value=value,
        unit=unit,
    )


def make_comparison_evidence(
    change_percent: Decimal | None = None,
    status: str = "unavailable",
    reason: str | None = None,
) -> EvidenceComparison:
    return EvidenceComparison(
        change_percent=change_percent,
        status=status,
        reason=reason,
    )


def make_funnel_evidence(
    from_stage: str,
    to_stage: str,
    conversion_rate: Decimal,
    previous_rate: Decimal | None = None,
) -> EvidenceFunnel:
    return EvidenceFunnel(
        from_stage=from_stage,
        to_stage=to_stage,
        conversion_rate=conversion_rate,
        previous_rate=previous_rate,
    )


def make_fact_evidence(
    code: str,
    value: Decimal | str,
    unit: str | None = None,
) -> EvidenceFact:
    return EvidenceFact(code=code, value=value, unit=unit)


def make_evidence_item(
    *,
    metric: EvidenceMetric | None = None,
    threshold: EvidenceThreshold | None = None,
    comparison: EvidenceComparison | None = None,
    funnel: EvidenceFunnel | None = None,
    facts: list[EvidenceFact] | None = None,
    rule: str | None = None,
    source: str | None = None,
) -> EvidenceItem:
    return EvidenceItem(
        metric=metric,
        threshold=threshold,
        comparison=comparison,
        funnel=funnel,
        facts=facts or [],
        rule=rule,
        source=source,
    )


def make_decision_evidence(
    *,
    primary_reason: str,
    evidence_items: list[EvidenceItem],
    evidence_strength: str,
    diagnostics_refs: list[str] | None = None,
    forecast_refs: list[str] | None = None,
    goal_refs: list[str] | None = None,
) -> DecisionEvidence:
    return DecisionEvidence(
        primary_reason=primary_reason,
        evidence_items=evidence_items,
        evidence_strength=evidence_strength,
        diagnostics_refs=diagnostics_refs or [],
        forecast_refs=forecast_refs or [],
        goal_refs=goal_refs or [],
    )


__all__ = [
    "EvidenceMetric",
    "EvidenceThreshold",
    "EvidenceComparison",
    "EvidenceFunnel",
    "EvidenceFact",
    "EvidenceItem",
    "DecisionEvidence",
    "make_metric_evidence",
    "make_threshold_evidence",
    "make_comparison_evidence",
    "make_funnel_evidence",
    "make_fact_evidence",
    "make_evidence_item",
    "make_decision_evidence",
]