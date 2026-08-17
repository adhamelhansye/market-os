"""Simulator constants (Phase 5A).

All thresholds and model codes live here so they are easy to audit and
tune without touching rule code. Numbers are deliberately conservative:
the simulator prefers to surface `unavailable` over inventing a result.
"""

from __future__ import annotations

from decimal import Decimal

# -- Simulator version ----------------------------------------------------

SIMULATOR_VERSION = "1.0.0"

# -- Calculation models ---------------------------------------------------

MODEL_CPM_CTR_CVR_AOV = "cpm_ctr_cvr_aov"
MODEL_CPC_CVR_AOV = "cpc_cvr_aov"
MODEL_CPA_AOV = "cpa_aov"

MODEL_PATHS: dict[str, str] = {
    MODEL_CPM_CTR_CVR_AOV: (
        "budget → impressions → clicks → purchases → revenue → contribution_profit"
    ),
    MODEL_CPC_CVR_AOV: "budget → clicks → purchases → revenue → contribution_profit",
    MODEL_CPA_AOV: "budget → purchases → revenue → contribution_profit",
}

ALL_MODELS: tuple[str, ...] = (
    MODEL_CPM_CTR_CVR_AOV,
    MODEL_CPC_CVR_AOV,
    MODEL_CPA_AOV,
)

# -- Assumption sources ---------------------------------------------------

SOURCE_USER_INPUT = "user_input"
SOURCE_CAMPAIGN_HISTORY = "campaign_history"
SOURCE_AD_ACCOUNT_HISTORY = "ad_account_history"
SOURCE_BUSINESS_HISTORY = "business_history"
SOURCE_ECONOMICS = "economics"
SOURCE_GOAL = "goal"
SOURCE_SYSTEM_DEFAULT = "system_default"

ALL_SOURCES: tuple[str, ...] = (
    SOURCE_USER_INPUT,
    SOURCE_CAMPAIGN_HISTORY,
    SOURCE_AD_ACCOUNT_HISTORY,
    SOURCE_BUSINESS_HISTORY,
    SOURCE_ECONOMICS,
    SOURCE_GOAL,
    SOURCE_SYSTEM_DEFAULT,
)

# -- Historical windows ---------------------------------------------------

ALLOWED_HISTORICAL_WINDOWS: tuple[int, ...] = (7, 14, 30, 60, 90)

# -- Scenario levels ------------------------------------------------------

SCENARIO_DOWNSIDE = "downside"
SCENARIO_EXPECTED = "expected"
SCENARIO_UPSIDE = "upside"

ALL_SCENARIOS: tuple[str, ...] = (
    SCENARIO_DOWNSIDE,
    SCENARIO_EXPECTED,
    SCENARIO_UPSIDE,
)

# -- Percentiles for scenario derivation ----------------------------------

PERCENTILE_DOWNSIDE = Decimal("25")
PERCENTILE_EXPECTED = Decimal("50")
PERCENTILE_UPSIDE = Decimal("75")

# -- Data quality / evidence strength -------------------------------------

DATA_QUALITY_STRONG = "strong"
DATA_QUALITY_MODERATE = "moderate"
DATA_QUALITY_WEAK = "weak"
DATA_QUALITY_INSUFFICIENT = "insufficient"

ALL_DATA_QUALITY: tuple[str, ...] = (
    DATA_QUALITY_STRONG,
    DATA_QUALITY_MODERATE,
    DATA_QUALITY_WEAK,
    DATA_QUALITY_INSUFFICIENT,
)

MIN_OBSERVATIONS_STRONG = 30
MIN_OBSERVATIONS_MODERATE = 14
MIN_OBSERVATIONS_WEAK = 7
MIN_OBSERVATIONS_INSUFFICIENT = 0

# -- Sensitivity analysis -------------------------------------------------

SENSITIVITY_STEPS: tuple[Decimal, ...] = (
    Decimal("-0.20"),
    Decimal("-0.10"),
    Decimal("-0.05"),
    Decimal("0"),
    Decimal("0.05"),
    Decimal("0.10"),
    Decimal("0.20"),
)

SENSITIVITY_VARIABLES: tuple[str, ...] = (
    "ctr",
    "cpc",
    "cpm",
    "cvr",
    "aov",
    "budget",
)

# -- Profitability status -------------------------------------------------

PROFITABILITY_PROFITABLE = "profitable"
PROFITABILITY_NEAR_BREAK_EVEN = "near_break_even"
PROFITABILITY_UNPROFITABLE = "unprofitable"
PROFITABILITY_UNAVAILABLE = "unavailable"

NEAR_BREAK_EVEN_THRESHOLD = Decimal("0.05")

# -- Entity types ---------------------------------------------------------

ENTITY_TYPE_BUSINESS = "business"
ENTITY_TYPE_CAMPAIGN = "campaign"

ALL_ENTITY_TYPES: tuple[str, ...] = (ENTITY_TYPE_BUSINESS, ENTITY_TYPE_CAMPAIGN)

# -- Decimal precisions ---------------------------------------------------

PRECISION_MONEY = Decimal("0.01")
PRECISION_RATE = Decimal("0.0001")


__all__ = [
    "ALLOWED_HISTORICAL_WINDOWS",
    "ALL_DATA_QUALITY",
    "ALL_ENTITY_TYPES",
    "ALL_MODELS",
    "ALL_SCENARIOS",
    "ALL_SOURCES",
    "DATA_QUALITY_INSUFFICIENT",
    "DATA_QUALITY_MODERATE",
    "DATA_QUALITY_STRONG",
    "DATA_QUALITY_WEAK",
    "ENTITY_TYPE_BUSINESS",
    "ENTITY_TYPE_CAMPAIGN",
    "MIN_OBSERVATIONS_INSUFFICIENT",
    "MIN_OBSERVATIONS_MODERATE",
    "MIN_OBSERVATIONS_STRONG",
    "MIN_OBSERVATIONS_WEAK",
    "MODEL_CPA_AOV",
    "MODEL_CPC_CVR_AOV",
    "MODEL_CPM_CTR_CVR_AOV",
    "MODEL_PATHS",
    "NEAR_BREAK_EVEN_THRESHOLD",
    "PERCENTILE_DOWNSIDE",
    "PERCENTILE_EXPECTED",
    "PERCENTILE_UPSIDE",
    "PRECISION_MONEY",
    "PRECISION_RATE",
    "PROFITABILITY_NEAR_BREAK_EVEN",
    "PROFITABILITY_PROFITABLE",
    "PROFITABILITY_UNAVAILABLE",
    "PROFITABILITY_UNPROFITABLE",
    "SCENARIO_DOWNSIDE",
    "SCENARIO_EXPECTED",
    "SCENARIO_UPSIDE",
    "SENSITIVITY_STEPS",
    "SENSITIVITY_VARIABLES",
    "SIMULATOR_VERSION",
    "SOURCE_AD_ACCOUNT_HISTORY",
    "SOURCE_BUSINESS_HISTORY",
    "SOURCE_CAMPAIGN_HISTORY",
    "SOURCE_ECONOMICS",
    "SOURCE_GOAL",
    "SOURCE_SYSTEM_DEFAULT",
    "SOURCE_USER_INPUT",
]
