"""Deterministic Analytics Diagnostics (Phase 3B).

Transforms deterministic metrics into structured diagnostic findings:

    Provider Data → Canonical Facts → KPI Engine → Diagnostics Engine
    → Structured Findings → Dashboard

The engine is entirely deterministic: rules reference actual metric values,
previous-period comparisons, centralized thresholds, the concrete entity and
the date range. No LLM, no forecasting, no simulation and no autonomous
actions (see docs/architecture/diagnostics.md).
"""

from src.modules.diagnostics.evidence import (
    CATEGORIES,
    ENTITY_TYPES,
    Finding,
    finding_fingerprint,
)
from src.modules.diagnostics.rules import RULE_CODES, RULES
from src.modules.diagnostics.severity import SEVERITIES
from src.modules.diagnostics.thresholds import THRESHOLD_VERSION, THRESHOLDS

__all__ = [
    "CATEGORIES",
    "ENTITY_TYPES",
    "Finding",
    "finding_fingerprint",
    "RULES",
    "RULE_CODES",
    "SEVERITIES",
    "THRESHOLDS",
    "THRESHOLD_VERSION",
]