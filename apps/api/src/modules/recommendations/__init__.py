"""Deterministic Decision Engine (Phase 4B).

Transforms deterministic diagnostics, forecasts, and economics into structured
decisions for human review:

    Metrics → Diagnostics → Forecast → Economics → Goals → Decision Engine
    → Structured Decisions

The engine is entirely deterministic: decisions reference actual metric values,
diagnostic findings, forecast snapshots, unit economics, and business goals.
No LLM, no simulation, no autonomous actions.

Decisions are for human review only. The system never executes Meta mutations,
budget changes, or campaign modifications.
"""

from src.modules.recommendations.engine import (
    DECISION_PRECEDENCE,
    DECISION_TYPES,
    EVIDENCE_STRENGTHS,
    decide_business,
    decide_campaign,
)
from src.modules.recommendations.evidence import (
    DecisionEvidence,
    EvidenceComparison,
    EvidenceFact,
    EvidenceFunnel,
    EvidenceItem,
    EvidenceMetric,
    EvidenceThreshold,
)
from src.modules.recommendations.rules import RULE_CODES, RULES
from src.modules.recommendations.severity import (
    DECISION_SEVERITY_MAP,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_INFO,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
)
from src.modules.recommendations.thresholds import THRESHOLD_VERSION, THRESHOLDS

__all__ = [
    "DECISION_TYPES",
    "DECISION_PRECEDENCE",
    "EVIDENCE_STRENGTHS",
    "decide_business",
    "decide_campaign",
    "DecisionEvidence",
    "EvidenceItem",
    "EvidenceMetric",
    "EvidenceThreshold",
    "EvidenceComparison",
    "EvidenceFunnel",
    "EvidenceFact",
    "RULES",
    "RULE_CODES",
    "SEVERITY_CRITICAL",
    "SEVERITY_HIGH",
    "SEVERITY_INFO",
    "SEVERITY_LOW",
    "SEVERITY_MEDIUM",
    "DECISION_SEVERITY_MAP",
    "THRESHOLD_VERSION",
    "THRESHOLDS",
]