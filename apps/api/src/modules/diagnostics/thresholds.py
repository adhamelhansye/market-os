"""Centralized diagnostic thresholds (Phase 3B).

Every rule threshold lives in this single registry: centralized, versioned
(`THRESHOLD_VERSION`), documented (description) and testable. Rules never
hardcode comparisons against magic numbers — they resolve thresholds here
by code, so boundary tests can target one place.

Units:

- ratio        relative measure (0.007 = 0.7%)
- percent      percentage points (30 = 30%)
- money        the business currency (SERIALIZED BY RULES AS-IS)
- count        integer counts
- multiplier   factor without unit (2.0 = double)

Money thresholds are documented baselines; market-aware per-business
overrides can be layered on top of this registry later without touching
any rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

UNIT_RATIO = "ratio"
UNIT_PERCENT = "percent"
UNIT_MONEY = "money"
UNIT_COUNT = "count"
UNIT_MULTIPLIER = "multiplier"

THRESHOLD_VERSION = 1

# Sample-size guardrails: below these minima a rule must report
# insufficient_data instead of a performance finding (never diagnose
# performance from tiny samples).
SAMPLE_MIN_IMPRESSIONS = "sample_min_impressions"
SAMPLE_MIN_CLICKS = "sample_min_clicks"
SAMPLE_MIN_PURCHASES = "sample_min_purchases"
SAMPLE_MIN_SPEND = "sample_min_spend"
SAMPLE_MIN_CONVERSIONS = "sample_min_conversions"
SCALING_MIN_DAYS = "scaling_min_days"

# Traffic / creative performance baselines.
CTR_LOW = "ctr_low"
CTR_CRITICAL = "ctr_critical"
DECLINE_PERCENT = "decline_percent"
CPC_HIGH = "cpc_high"
CPM_HIGH = "cpm_high"
FREQUENCY_HIGH = "frequency_high"

# Conversion / economics baselines.
CVR_LOW = "cvr_low"
CPA_OVER_TARGET_HIGH = "cpa_over_target_high_multiplier"
CPA_OVER_TARGET_CRITICAL = "cpa_over_target_critical_multiplier"
SPEND_WITHOUT_PURCHASE_HIGH = "spend_without_purchase_high_multiplier"
REVENUE_GROWTH_DIVERGENCE = "revenue_growth_divergence_percent"
PROFIT_DECLINE_DIVERGENCE = "profit_decline_divergence_percent"
PERSISTENT_PERIODS = "persistent_periods"

# Funnel / tracking baselines.
FUNNEL_LOW_TRANSITION = "funnel_low_transition"
CONVERSION_MISMATCH_PERCENT = "conversion_mismatch_percent"
MISSING_DAYS_INCOMPLETE = "missing_days_incomplete"


@dataclass(frozen=True)
class Threshold:
    code: str
    description: str
    value: Decimal
    unit: str


def _t(code: str, description: str, value: str, unit: str) -> Threshold:
    return Threshold(code=code, description=description, value=Decimal(value), unit=unit)


_THRESHOLD_ENTRIES: tuple[Threshold, ...] = (
    _t(
        SAMPLE_MIN_IMPRESSIONS,
        "Minimum impressions before traffic findings may fire",
        "500",
        UNIT_COUNT,
    ),
    _t(
        SAMPLE_MIN_CLICKS,
        "Minimum clicks before conversion/CPC findings may fire",
        "50",
        UNIT_COUNT,
    ),
    _t(
        SAMPLE_MIN_PURCHASES,
        "Minimum purchases before CPA findings may fire",
        "3",
        UNIT_COUNT,
    ),
    _t(
        SAMPLE_MIN_SPEND,
        "Minimum spend before spend findings may fire",
        "100.00",
        UNIT_MONEY,
    ),
    _t(
        SAMPLE_MIN_CONVERSIONS,
        "Minimum Meta conversions before scaling review is suggested",
        "3",
        UNIT_COUNT,
    ),
    _t(
        SCALING_MIN_DAYS,
        "Minimum days with facts before scaling review is suggested",
        "7",
        UNIT_COUNT,
    ),
    _t(CTR_LOW, "CTR below this ratio is a low-CTR finding", "0.007", UNIT_RATIO),
    _t(
        CTR_CRITICAL,
        "CTR below this ratio escalates low_ctr to high",
        "0.003",
        UNIT_RATIO,
    ),
    _t(
        DECLINE_PERCENT,
        "Relative decline vs previous period that flags deterioration",
        "30",
        UNIT_PERCENT,
    ),
    _t(
        CPC_HIGH,
        "CPC above this money value is flagged (baseline; overrides)",
        "10.00",
        UNIT_MONEY,
    ),
    _t(CPM_HIGH, "CPM above this money value is flagged (baseline)", "800.00", UNIT_MONEY),
    _t(
        FREQUENCY_HIGH,
        "Impressions/reach above this is high frequency (fatigue signal)",
        "2.5",
        UNIT_MULTIPLIER,
    ),
    _t(CVR_LOW, "CVR below this ratio is a low-CVR finding", "0.03", UNIT_RATIO),
    _t(
        CPA_OVER_TARGET_HIGH,
        "CPA above target x this multiplier is a high finding",
        "1.5",
        UNIT_MULTIPLIER,
    ),
    _t(
        CPA_OVER_TARGET_CRITICAL,
        "CPA above target x this multiplier is critical",
        "2.0",
        UNIT_MULTIPLIER,
    ),
    _t(
        SPEND_WITHOUT_PURCHASE_HIGH,
        "Spend without purchases above break-even CPA x this is high",
        "3.0",
        UNIT_MULTIPLIER,
    ),
    _t(
        REVENUE_GROWTH_DIVERGENCE,
        "Revenue growth at/above this percent with profit decline is a divergence",
        "20",
        UNIT_PERCENT,
    ),
    _t(
        PROFIT_DECLINE_DIVERGENCE,
        "Profit decline at/above this percent with revenue growth is a divergence",
        "15",
        UNIT_PERCENT,
    ),
    _t(
        PERSISTENT_PERIODS,
        "Periods (current + previous) below break-even mark persistence",
        "2",
        UNIT_COUNT,
    ),
    _t(
        FUNNEL_LOW_TRANSITION,
        "Lowest observed transition below this ratio is a bottleneck",
        "0.05",
        UNIT_RATIO,
    ),
    _t(
        CONVERSION_MISMATCH_PERCENT,
        "Meta conversions vs purchases differing by this percent is flagged",
        "50",
        UNIT_PERCENT,
    ),
    _t(
        MISSING_DAYS_INCOMPLETE,
        "Covered days missing this many range days marks incomplete reporting",
        "2",
        UNIT_COUNT,
    ),
)

THRESHOLDS: dict[str, Threshold] = {entry.code: entry for entry in _THRESHOLD_ENTRIES}

# Reserved for future per-business overrides (kept next to the registry so
# the resolution path is explicit and testable). Empty by design: thresholds
# are global baselines in this phase.
BUSINESS_OVERRIDES: dict[str, dict[str, str]] = {}


def threshold(code: str) -> Threshold:
    try:
        return THRESHOLDS[code]
    except KeyError:
        raise ValueError(f"Unknown threshold code: {code}") from None


def value(code: str) -> Decimal:
    return threshold(code).value


def known(code: str) -> bool:
    return code in THRESHOLDS


__all__ = [
    "THRESHOLD_VERSION",
    "THRESHOLDS",
    "BUSINESS_OVERRIDES",
    "Threshold",
    "threshold",
    "value",
    "known",
    "UNIT_RATIO",
    "UNIT_PERCENT",
    "UNIT_MONEY",
    "UNIT_COUNT",
    "UNIT_MULTIPLIER",
    "SAMPLE_MIN_IMPRESSIONS",
    "SAMPLE_MIN_CLICKS",
    "SAMPLE_MIN_PURCHASES",
    "SAMPLE_MIN_SPEND",
    "SAMPLE_MIN_CONVERSIONS",
    "SCALING_MIN_DAYS",
    "CTR_LOW",
    "CTR_CRITICAL",
    "DECLINE_PERCENT",
    "CPC_HIGH",
    "CPM_HIGH",
    "FREQUENCY_HIGH",
    "CVR_LOW",
    "CPA_OVER_TARGET_HIGH",
    "CPA_OVER_TARGET_CRITICAL",
    "SPEND_WITHOUT_PURCHASE_HIGH",
    "REVENUE_GROWTH_DIVERGENCE",
    "PROFIT_DECLINE_DIVERGENCE",
    "PERSISTENT_PERIODS",
    "FUNNEL_LOW_TRANSITION",
    "CONVERSION_MISMATCH_PERCENT",
    "MISSING_DAYS_INCOMPLETE",
]