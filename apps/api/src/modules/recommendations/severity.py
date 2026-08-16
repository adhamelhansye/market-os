"""Severity levels for decisions and evidence.

Maps diagnostic severities to decision severities and defines the
decision-specific severity scale.
"""

from __future__ import annotations

# Diagnostic severity levels (from Phase 3B)
SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

SEVERITIES = (
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SEVERITY_LOW,
    SEVERITY_INFO,
)

# Rank for ordering (higher = more severe)
SEVERITY_RANK = {
    SEVERITY_CRITICAL: 5,
    SEVERITY_HIGH: 4,
    SEVERITY_MEDIUM: 3,
    SEVERITY_LOW: 2,
    SEVERITY_INFO: 1,
}


def rank(severity: str) -> int:
    """Get numeric rank for a severity (higher = more severe)."""
    return SEVERITY_RANK.get(severity, 0)


def max_severity(severities: list[str]) -> str | None:
    """Return the highest severity from a list."""
    if not severities:
        return None
    return max(severities, key=rank)


# Decision evidence strength levels
EVIDENCE_INSUFFICIENT = "insufficient"
EVIDENCE_WEAK = "weak"
EVIDENCE_MODERATE = "moderate"
EVIDENCE_STRONG = "strong"

EVIDENCE_STRENGTHS = (
    EVIDENCE_INSUFFICIENT,
    EVIDENCE_WEAK,
    EVIDENCE_MODERATE,
    EVIDENCE_STRONG,
)

EVIDENCE_STRENGTH_RANK = {
    EVIDENCE_INSUFFICIENT: 0,
    EVIDENCE_WEAK: 1,
    EVIDENCE_MODERATE: 2,
    EVIDENCE_STRONG: 3,
}


def evidence_strength_rank(strength: str) -> int:
    return EVIDENCE_STRENGTH_RANK.get(strength, 0)


# Decision types and their default severity mapping
DECISION_TYPES = (
    "tracking_issue",
    "data_quality_issue",
    "insufficient_data",
    "learning",
    "kill_review",
    "scale_review",
    "optimize",
    "maintain",
)

# Maps decision types to their inherent severity for display
# (not to be confused with evidence strength)
DECISION_SEVERITY_MAP = {
    "tracking_issue": SEVERITY_CRITICAL,
    "data_quality_issue": SEVERITY_HIGH,
    "insufficient_data": SEVERITY_INFO,
    "learning": SEVERITY_LOW,
    "kill_review": SEVERITY_CRITICAL,
    "scale_review": SEVERITY_MEDIUM,
    "optimize": SEVERITY_MEDIUM,
    "maintain": SEVERITY_INFO,
}

# Precedence order for decision resolution (first match wins)
DECISION_PRECEDENCE = (
    "tracking_issue",
    "data_quality_issue",
    "insufficient_data",
    "learning",
    "kill_review",
    "scale_review",
    "optimize",
    "maintain",
)


__all__ = [
    "SEVERITY_CRITICAL",
    "SEVERITY_HIGH",
    "SEVERITY_MEDIUM",
    "SEVERITY_LOW",
    "SEVERITY_INFO",
    "SEVERITIES",
    "rank",
    "max_severity",
    "EVIDENCE_INSUFFICIENT",
    "EVIDENCE_WEAK",
    "EVIDENCE_MODERATE",
    "EVIDENCE_STRONG",
    "EVIDENCE_STRENGTHS",
    "evidence_strength_rank",
    "DECISION_TYPES",
    "DECISION_SEVERITY_MAP",
    "DECISION_PRECEDENCE",
]