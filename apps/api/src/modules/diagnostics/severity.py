"""Deterministic severity model for diagnostic findings.

Severity is derived by rules from evidence (measured values vs thresholds),
never from AI confidence or subjective scoring. The ordering below is the
single ranking used for sorting, filtering and summary aggregation.
"""

from __future__ import annotations

SEVERITY_INFO = "info"
SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"
SEVERITY_CRITICAL = "critical"

SEVERITIES: tuple[str, ...] = (
    SEVERITY_INFO,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    SEVERITY_HIGH,
    SEVERITY_CRITICAL,
)

_RANK: dict[str, int] = {severity: index for index, severity in enumerate(SEVERITIES)}


def rank(severity: str) -> int:
    """0 = info … 4 = critical; unknown severities rank below info."""
    return _RANK.get(severity, -1)


def is_valid(severity: str) -> bool:
    return severity in _RANK


def max_severity(severities: list[str]) -> str | None:
    """The highest severity in a list (or None when empty)."""
    if not severities:
        return None
    return max(severities, key=rank)


def filter_matches(severity_filter: str | None, severity: str) -> bool:
    """True when `severity` satisfies a severity filter (or no filter)."""
    return severity_filter is None or severity == severity_filter


__all__ = [
    "SEVERITY_INFO",
    "SEVERITY_LOW",
    "SEVERITY_MEDIUM",
    "SEVERITY_HIGH",
    "SEVERITY_CRITICAL",
    "SEVERITIES",
    "rank",
    "is_valid",
    "max_severity",
    "filter_matches",
]