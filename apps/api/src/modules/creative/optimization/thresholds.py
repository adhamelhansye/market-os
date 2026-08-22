"""Optimization intelligence thresholds and gates (Phase 8E).

Named, versioned gates O1-O8 with explicit precedence, plus Decimal-safe
priority weights. Existing baselines are REUSED through the resolver
chain (learning -> performance -> diagnostics); only optimization-
specific weights are defined here.

The priority score is a deterministic prioritization score ONLY.
It is never a probability of success and must not be presented as one.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

OPTIMIZATION_RULES_VERSION = "copt-v1"

UNIT_COUNT = "count"
UNIT_DAYS = "days"
UNIT_RATIO = "ratio"

# --- Reused registries ----------------------------------------------------

SAMPLE_MIN_IMPRESSIONS = "sample_min_impressions"
SAMPLE_MIN_SPEND = "sample_min_spend"
LEARNING_MIN_ENTITIES = "learning_min_entities"
LEARNING_STALE_DAYS = "learning_stale_days"
LEARNING_CONFLICT_RATIO = "learning_conflict_ratio"


# --- Gates O1-O8 (named codes; precedence defined in engine.py) -----------

GATE_INSUFFICIENT_DATA = "insufficient_data"          # O1
GATE_STALE_DATA = "stale_data"                        # O2
GATE_CONFLICTING_EVIDENCE = "conflicting_evidence"    # O3
GATE_FATIGUE_SIGNAL = "fatigue_signal"                # O4
GATE_CONCENTRATION_RISK = "concentration_risk"        # O5
GATE_COVERAGE_GAP = "coverage_gap"                    # O6
GATE_SUPPORTED_PATTERN = "supported_pattern"          # O7
GATE_STRATEGIC_ALIGNMENT = "strategic_alignment"      # O8

# Explicit gate precedence for POSITIVE opportunity types
# (expand/test recommendations). First blocking gate wins:
#   O1 > O2 > O3 block; O7 enables; O4/O5/O6/O8 classify other types.
POSITIVE_OPPORTUNITY_GATE_PRECEDENCE: tuple[str, ...] = (
    GATE_INSUFFICIENT_DATA,     # O1 blocks
    GATE_STALE_DATA,            # O2 blocks
    GATE_CONFLICTING_EVIDENCE,  # O3 blocks
)


@dataclass(frozen=True)
class Threshold:
    code: str
    description: str
    value: Decimal
    unit: str


def _t(code: str, description: str, value_str: str, unit: str) -> Threshold:
    return Threshold(code=code, description=description, value=Decimal(value_str), unit=unit)


_ENTRIES: tuple[Threshold, ...] = ()

THRESHOLDS: dict[str, Threshold] = {entry.code: entry for entry in _ENTRIES}

# --- Optimization priority weights (Decimal) -------------------------------

WEIGHT_EVIDENCE_STRONG = "opt_weight_evidence_strong"
WEIGHT_EVIDENCE_MODERATE = "opt_weight_evidence_moderate"
WEIGHT_EVIDENCE_WEAK = "opt_weight_evidence_weak"
WEIGHT_DATA_SUFFICIENCY = "opt_weight_data_sufficiency"
WEIGHT_FRESHNESS = "opt_weight_freshness"
WEIGHT_STRATEGIC_ALIGNMENT = "opt_weight_strategic_alignment"
WEIGHT_FUNNEL_RELEVANCE = "opt_weight_funnel_relevance"
WEIGHT_LEARNING_VALUE_HIGH = "opt_weight_learning_value_high"
WEIGHT_LEARNING_VALUE_MEDIUM = "opt_weight_learning_value_medium"
WEIGHT_COVERAGE_VALUE = "opt_weight_coverage_value"
WEIGHT_DIVERSITY_VALUE = "opt_weight_diversity_value"
WEIGHT_FATIGUE_RELEVANCE = "opt_weight_fatigue_relevance"
PENALTY_CONTRADICTION = "opt_penalty_contradiction"

PRIORITY_HIGH_MIN_SCORE = "opt_priority_high_min_score"
PRIORITY_MEDIUM_MIN_SCORE = "opt_priority_medium_min_score"

_WEIGHT_ENTRIES: tuple[Threshold, ...] = (
    _t(WEIGHT_EVIDENCE_STRONG, "Weight: strong evidence", "3.0", UNIT_COUNT),
    _t(WEIGHT_EVIDENCE_MODERATE, "Weight: moderate evidence", "2.0", UNIT_COUNT),
    _t(WEIGHT_EVIDENCE_WEAK, "Weight: weak evidence", "1.0", UNIT_COUNT),
    _t(WEIGHT_DATA_SUFFICIENCY, "Weight: all members sufficiently observed", "1.0", UNIT_COUNT),
    _t(WEIGHT_FRESHNESS, "Weight: observations fresh", "0.5", UNIT_COUNT),
    _t(WEIGHT_STRATEGIC_ALIGNMENT, "Weight: strategy references present", "1.0", UNIT_COUNT),
    _t(WEIGHT_FUNNEL_RELEVANCE, "Weight: funnel stage known", "0.5", UNIT_COUNT),
    _t(WEIGHT_LEARNING_VALUE_HIGH, "Weight: high learning value", "2.0", UNIT_COUNT),
    _t(WEIGHT_LEARNING_VALUE_MEDIUM, "Weight: medium learning value", "1.0", UNIT_COUNT),
    _t(WEIGHT_COVERAGE_VALUE, "Weight: fills a canonical coverage gap", "1.0", UNIT_COUNT),
    _t(WEIGHT_DIVERSITY_VALUE, "Weight: reduces concentration risk", "1.5", UNIT_COUNT),
    _t(WEIGHT_FATIGUE_RELEVANCE, "Weight: fatigue evidence present", "2.5", UNIT_COUNT),
    _t(PENALTY_CONTRADICTION, "Penalty applied per contradicting entity", "-0.5", UNIT_COUNT),
    _t(PRIORITY_HIGH_MIN_SCORE, "Score at/above this is HIGH priority", "5.0", UNIT_COUNT),
    _t(PRIORITY_MEDIUM_MIN_SCORE, "Score at/above this is MEDIUM priority", "2.5", UNIT_COUNT),
)

WEIGHTS: dict[str, Threshold] = {entry.code: entry for entry in _WEIGHT_ENTRIES}


def _resolve(code: str) -> Threshold:
    if code in THRESHOLDS or code in WEIGHTS:
        return THRESHOLDS.get(code) or WEIGHTS[code]
    from src.modules.creative.learning.thresholds import threshold as learning_threshold

    return learning_threshold(code)


def threshold(code: str) -> Threshold:
    return _resolve(code)


def value(code: str) -> Decimal:
    return _resolve(code).value


def weight(code: str) -> Decimal:
    """Numeric weight by registry key (raises when unknown)."""
    if code not in WEIGHTS:
        raise ValueError(f"Unknown optimization weight: {code}")
    return WEIGHTS[code].value


__all__ = [
    "OPTIMIZATION_RULES_VERSION",
    "THRESHOLDS",
    "Threshold",
    "threshold",
    "value",
    "weight",
    "UNIT_COUNT",
    "UNIT_DAYS",
    "UNIT_RATIO",
    "SAMPLE_MIN_IMPRESSIONS",
    "SAMPLE_MIN_SPEND",
    "LEARNING_MIN_ENTITIES",
    "LEARNING_STALE_DAYS",
    "LEARNING_CONFLICT_RATIO",
    "GATE_INSUFFICIENT_DATA",
    "GATE_STALE_DATA",
    "GATE_CONFLICTING_EVIDENCE",
    "GATE_FATIGUE_SIGNAL",
    "GATE_CONCENTRATION_RISK",
    "GATE_COVERAGE_GAP",
    "GATE_SUPPORTED_PATTERN",
    "GATE_STRATEGIC_ALIGNMENT",
    "POSITIVE_OPPORTUNITY_GATE_PRECEDENCE",
    "WEIGHTS",
    "WEIGHT_EVIDENCE_STRONG",
    "WEIGHT_EVIDENCE_MODERATE",
    "WEIGHT_EVIDENCE_WEAK",
    "WEIGHT_DATA_SUFFICIENCY",
    "WEIGHT_FRESHNESS",
    "WEIGHT_STRATEGIC_ALIGNMENT",
    "WEIGHT_FUNNEL_RELEVANCE",
    "WEIGHT_LEARNING_VALUE_HIGH",
    "WEIGHT_LEARNING_VALUE_MEDIUM",
    "WEIGHT_COVERAGE_VALUE",
    "WEIGHT_DIVERSITY_VALUE",
    "WEIGHT_FATIGUE_RELEVANCE",
    "PENALTY_CONTRADICTION",
    "PRIORITY_HIGH_MIN_SCORE",
    "PRIORITY_MEDIUM_MIN_SCORE",
]
