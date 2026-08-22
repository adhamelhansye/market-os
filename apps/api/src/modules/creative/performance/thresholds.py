"""Creative performance thresholds (Phase 8C).

Single registry for every creative-performance rule threshold: named,
versioned, documented. Rules never compare against magic numbers.

Existing diagnostics baselines are REUSED by reference (sample minima,
decline percent, frequency, CTR floors) so the platform keeps one set of
numbers. Only creative-specific gaps (fatigue window size, trend
deadband, classification runway) are defined here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# Version stamp written into every signal/fatigue/classification/readiness
# payload and every persisted snapshot. Bump when a rule meaning changes.
CREATIVE_PERFORMANCE_RULES_VERSION = "cperf-1"

UNIT_COUNT = "count"
UNIT_MONEY = "money"
UNIT_RATIO = "ratio"
UNIT_PERCENT = "percent"
UNIT_MULTIPLIER = "multiplier"
UNIT_DAYS = "days"

# --- Reused diagnostics registry codes (single source of truth) ----------

SAMPLE_MIN_IMPRESSIONS = "sample_min_impressions"
SAMPLE_MIN_CLICKS = "sample_min_clicks"
SAMPLE_MIN_CONVERSIONS = "sample_min_conversions"
SAMPLE_MIN_SPEND = "sample_min_spend"
SCALING_MIN_DAYS = "scaling_min_days"
DECLINE_PERCENT = "decline_percent"
FREQUENCY_HIGH = "frequency_high"
CTR_LOW = "ctr_low"
CTR_CRITICAL = "ctr_critical"

# --- Creative-performance specific codes ---------------------------------

FATIGUE_WINDOW_DAYS = "fatigue_window_days"
FATIGUE_MIN_OBSERVATIONS = "fatigue_min_observations"
TREND_MIN_OBSERVATIONS = "trend_min_observations"
TREND_DEADBAND_PERCENT = "trend_deadband_percent"
CLASSIFICATION_MIN_DAYS = "classification_min_days"


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
        FATIGUE_WINDOW_DAYS,
        "Length of each comparison window (recent vs prior) in days",
        "7",
        UNIT_DAYS,
    ),
    _t(
        FATIGUE_MIN_OBSERVATIONS,
        "Minimum distinct observed days required in EACH fatigue window",
        "5",
        UNIT_DAYS,
    ),
    _t(
        TREND_MIN_OBSERVATIONS,
        "Minimum distinct observed days required for a trend signal",
        "5",
        UNIT_DAYS,
    ),
    _t(
        TREND_DEADBAND_PERCENT,
        "Half-range change within this percent is a stable trend",
        "10",
        UNIT_PERCENT,
    ),
    _t(
        CLASSIFICATION_MIN_DAYS,
        "Minimum distinct observed days before a classification may fire",
        "3",
        UNIT_DAYS,
    ),
)

THRESHOLDS: dict[str, Threshold] = {entry.code: entry for entry in _ENTRIES}


def _resolve(code: str) -> Threshold:
    """Resolve a threshold from this registry or the shared diagnostics one."""
    if code in THRESHOLDS:
        return THRESHOLDS[code]
    from src.modules.diagnostics.thresholds import threshold as diag_threshold

    return diag_threshold(code)


def threshold(code: str) -> Threshold:
    return _resolve(code)


def value(code: str) -> Decimal:
    """Numeric value of a threshold code."""
    return _resolve(code).value


def known(code: str) -> bool:
    from src.modules.diagnostics.thresholds import known as diag_known

    return code in THRESHOLDS or diag_known(code)


__all__ = [
    "CREATIVE_PERFORMANCE_RULES_VERSION",
    "THRESHOLDS",
    "Threshold",
    "threshold",
    "value",
    "known",
    "UNIT_COUNT",
    "UNIT_MONEY",
    "UNIT_RATIO",
    "UNIT_PERCENT",
    "UNIT_MULTIPLIER",
    "UNIT_DAYS",
    "SAMPLE_MIN_IMPRESSIONS",
    "SAMPLE_MIN_CLICKS",
    "SAMPLE_MIN_CONVERSIONS",
    "SAMPLE_MIN_SPEND",
    "SCALING_MIN_DAYS",
    "DECLINE_PERCENT",
    "FREQUENCY_HIGH",
    "CTR_LOW",
    "CTR_CRITICAL",
    "FATIGUE_WINDOW_DAYS",
    "FATIGUE_MIN_OBSERVATIONS",
    "TREND_MIN_OBSERVATIONS",
    "TREND_DEADBAND_PERCENT",
    "CLASSIFICATION_MIN_DAYS",
]
