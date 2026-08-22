"""Creative learning thresholds and rule version (Phase 8D).

Single registry for the deterministic learning hierarchy
(OBSERVATION → SIGNAL → PATTERN → LEARNING → RECOMMENDATION).

Existing baselines are REUSED through the shared resolvers: sample-size
minima and decline/deadbands come from the Phase 8C / diagnostics
registries. Only learning-specific gaps are defined here:

- how many entities a pattern needs before it may exist,
- when a consistent pattern becomes "stable",
- when evidence counts as stale,
- what minority share turns consistency into a conflict,
- the named weights used for recommendation priority.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# Version stamp written into every learning snapshot. Bump when a rule
# meaning changes.
CREATIVE_LEARNING_RULES_VERSION = "clearning-v1"

UNIT_COUNT = "count"
UNIT_DAYS = "days"
UNIT_PERCENT = "percent"
UNIT_RATIO = "ratio"

# --- Reused registries ----------------------------------------------------

SAMPLE_MIN_IMPRESSIONS = "sample_min_impressions"
SAMPLE_MIN_SPEND = "sample_min_spend"
TREND_DEADBAND_PERCENT = "trend_deadband_percent"

# --- Learning-specific codes ----------------------------------------------

LEARNING_MIN_ENTITIES = "learning_min_entities"
LEARNING_STABLE_MIN_ENTITIES = "learning_stable_min_entities"
LEARNING_STALE_DAYS = "learning_stale_days"
LEARNING_CONFLICT_RATIO = "learning_conflict_ratio"


@dataclass(frozen=True)
class Threshold:
    code: str
    description: str
    value: Decimal
    unit: str


def _t(code: str, description: str, value_str: str, unit: str) -> Threshold:
    return Threshold(code=code, description=description, value=Decimal(value_str), unit=unit)


_ENTRIES: tuple[Threshold, ...] = (
    _t(
        LEARNING_MIN_ENTITIES,
        "Minimum sufficiently observed entities required for a pattern",
        "2",
        UNIT_COUNT,
    ),
    _t(
        LEARNING_STABLE_MIN_ENTITIES,
        "Minimum consistent entities for a pattern to become stable",
        "4",
        UNIT_COUNT,
    ),
    _t(
        LEARNING_STALE_DAYS,
        "Maximum age of the freshest underlying observation before a "
        "pattern is marked stale",
        "14",
        UNIT_DAYS,
    ),
    _t(
        LEARNING_CONFLICT_RATIO,
        "Minority share of contradicting entities that marks a pattern "
        "conflicting",
        "0.35",
        UNIT_RATIO,
    ),
)

THRESHOLDS: dict[str, Threshold] = {entry.code: entry for entry in _ENTRIES}


def _resolve(code: str) -> Threshold:
    if code in THRESHOLDS or code in WEIGHTS or code in BUCKETS:
        if code in THRESHOLDS:
            return THRESHOLDS[code]
        if code in WEIGHTS:
            return WEIGHTS[code]
        return BUCKETS[code]
    from src.modules.creative.performance.thresholds import threshold as perf_threshold

    return perf_threshold(code)


def threshold(code: str) -> Threshold:
    return _resolve(code)


def value(code: str) -> Decimal:
    return _resolve(code).value


def known(code: str) -> bool:
    from src.modules.creative.performance.thresholds import known as perf_known

    return code in THRESHOLDS or perf_known(code)


# --- Recommendation priority weights (Decimal, named) ----------------------

PRIORITY_WEIGHT_FATIGUE_SIGNAL = "priority_weight_fatigue_signal"
PRIORITY_WEIGHT_CONCENTRATION_RISK = "priority_weight_concentration_risk"
PRIORITY_WEIGHT_CONFLICTING_EVIDENCE = "priority_weight_conflicting_evidence"
PRIORITY_WEIGHT_PATTERN_STRONG = "priority_weight_pattern_strong"
PRIORITY_WEIGHT_PATTERN_MODERATE = "priority_weight_pattern_moderate"
PRIORITY_WEIGHT_PATTERN_WEAK = "priority_weight_pattern_weak"

_PRIORITY_WEIGHT_ENTRIES: tuple[Threshold, ...] = (
    _t(PRIORITY_WEIGHT_FATIGUE_SIGNAL, "Priority weight: active fatigue signal", "3.0", UNIT_COUNT),
    _t(
        PRIORITY_WEIGHT_CONCENTRATION_RISK,
        "Priority weight: portfolio concentration risk",
        "2.5",
        UNIT_COUNT,
    ),
    _t(
        PRIORITY_WEIGHT_CONFLICTING_EVIDENCE,
        "Priority weight: materially conflicting evidence",
        "2.0",
        UNIT_COUNT,
    ),
    _t(PRIORITY_WEIGHT_PATTERN_STRONG, "Priority weight: strong pattern", "2.0", UNIT_COUNT),
    _t(PRIORITY_WEIGHT_PATTERN_MODERATE, "Priority weight: moderate pattern", "1.5", UNIT_COUNT),
    _t(PRIORITY_WEIGHT_PATTERN_WEAK, "Priority weight: weak pattern", "1.0", UNIT_COUNT),
)

WEIGHTS: dict[str, Threshold] = {entry.code: entry for entry in _PRIORITY_WEIGHT_ENTRIES}


def weight(code: str) -> Decimal:
    """Numeric priority weight by name (raises when unknown)."""
    if code not in WEIGHTS:
        raise ValueError(f"Unknown priority weight: {code}")
    return WEIGHTS[code].value


# Priority buckets (score thresholds).
PRIORITY_HIGH_MIN_SCORE = "priority_high_min_score"
PRIORITY_MEDIUM_MIN_SCORE = "priority_medium_min_score"

_PRIORITY_BUCKET_ENTRIES: tuple[Threshold, ...] = (
    _t(PRIORITY_HIGH_MIN_SCORE, "Score at/above this is HIGH priority", "3.0", UNIT_COUNT),
    _t(PRIORITY_MEDIUM_MIN_SCORE, "Score at/above this is MEDIUM priority", "1.5", UNIT_COUNT),
)

BUCKETS: dict[str, Threshold] = {entry.code: entry for entry in _PRIORITY_BUCKET_ENTRIES}


__all__ = [
    "CREATIVE_LEARNING_RULES_VERSION",
    "THRESHOLDS",
    "Threshold",
    "threshold",
    "value",
    "known",
    "UNIT_COUNT",
    "UNIT_DAYS",
    "UNIT_PERCENT",
    "UNIT_RATIO",
    "SAMPLE_MIN_IMPRESSIONS",
    "SAMPLE_MIN_SPEND",
    "TREND_DEADBAND_PERCENT",
    "LEARNING_MIN_ENTITIES",
    "LEARNING_STABLE_MIN_ENTITIES",
    "LEARNING_STALE_DAYS",
    "LEARNING_CONFLICT_RATIO",
    "WEIGHTS",
    "weight",
    "PRIORITY_WEIGHT_FATIGUE_SIGNAL",
    "PRIORITY_WEIGHT_CONCENTRATION_RISK",
    "PRIORITY_WEIGHT_CONFLICTING_EVIDENCE",
    "PRIORITY_WEIGHT_PATTERN_STRONG",
    "PRIORITY_WEIGHT_PATTERN_MODERATE",
    "PRIORITY_WEIGHT_PATTERN_WEAK",
    "PRIORITY_HIGH_MIN_SCORE",
    "PRIORITY_MEDIUM_MIN_SCORE",
]
