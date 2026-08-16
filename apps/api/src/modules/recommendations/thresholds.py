"""Centralized thresholds for the deterministic decision engine.

All thresholds are Decimal strings to avoid float precision issues.
Thresholds are versioned to ensure historical decisions identify which
rules produced them.

See Phase 3B thresholds for sample-size gates — this module ONLY adds
decision-specific thresholds. Sample-size and data-quality thresholds
are sourced from Phase 3B (diagnostics.thresholds).
"""

from __future__ import annotations

from decimal import Decimal

# Threshold version — increment when any threshold value changes.
THRESHOLD_VERSION = "1.0"

# --- Decision-specific thresholds ---------------------------------------------

# Minimum spend for a campaign to be evaluated for scale/kill decisions
MIN_SPEND_FOR_DECISION = Decimal("100.00")

# Minimum purchases for a campaign to be evaluated for profitability decisions
MIN_PURCHASES_FOR_DECISION = 5

# Minimum ROAS above break-even to consider for scale_review
ROAS_BUFFER_ABOVE_BREAKEVEN = Decimal("0.2")  # 20% buffer

# Minimum CPA below target to consider for scale_review
CPA_BUFFER_BELOW_TARGET = Decimal("0.8")  # 80% of target

# Maximum CPA above viable CPA to trigger kill_review
CPA_KILL_MULTIPLIER = Decimal("2.0")  # 2x viable CPA

# Maximum ROAS below break-even to trigger kill_review
ROAS_KILL_BUFFER = Decimal("0.1")  # 10% below break-even

# Minimum days of history for kill_review
MIN_DAYS_FOR_KILL_REVIEW = 14

# Minimum spend for kill_review
MIN_SPEND_FOR_KILL_REVIEW = Decimal("500.00")

# Minimum purchases for kill_review
MIN_PURCHASES_FOR_KILL_REVIEW = 10

# Forecast deterioration threshold (forecast ROAS drop from current)
FORECAST_DETERIORATION_THRESHOLD = Decimal("0.15")  # 15% drop

# Forecast improvement threshold (forecast ROAS improvement)
FORECAST_IMPROVEMENT_THRESHOLD = Decimal("0.10")  # 10% improvement

# Learning state: minimum spend before exiting learning
LEARNING_MIN_SPEND = Decimal("50.00")

# Learning state: minimum impressions before exiting learning
LEARNING_MIN_IMPRESSIONS = Decimal("1000")

# Learning state: minimum days before exiting learning
LEARNING_MIN_DAYS = 7

# Data freshness: maximum hours since last sync for confident decisions
MAX_DATA_STALE_HOURS = 24

# Goal achievement buffer (for target CPA/ROAS)
GOAL_ACHIEVEMENT_BUFFER = Decimal("0.05")  # 5% buffer


# --- Threshold registry for validation ----------------------------------------

THRESHOLDS = {
    "MIN_SPEND_FOR_DECISION": MIN_SPEND_FOR_DECISION,
    "MIN_PURCHASES_FOR_DECISION": MIN_PURCHASES_FOR_DECISION,
    "ROAS_BUFFER_ABOVE_BREAKEVEN": ROAS_BUFFER_ABOVE_BREAKEVEN,
    "CPA_BUFFER_BELOW_TARGET": CPA_BUFFER_BELOW_TARGET,
    "CPA_KILL_MULTIPLIER": CPA_KILL_MULTIPLIER,
    "ROAS_KILL_BUFFER": ROAS_KILL_BUFFER,
    "MIN_DAYS_FOR_KILL_REVIEW": MIN_DAYS_FOR_KILL_REVIEW,
    "MIN_SPEND_FOR_KILL_REVIEW": MIN_SPEND_FOR_KILL_REVIEW,
    "MIN_PURCHASES_FOR_KILL_REVIEW": MIN_PURCHASES_FOR_KILL_REVIEW,
    "FORECAST_DETERIORATION_THRESHOLD": FORECAST_DETERIORATION_THRESHOLD,
    "FORECAST_IMPROVEMENT_THRESHOLD": FORECAST_IMPROVEMENT_THRESHOLD,
    "LEARNING_MIN_SPEND": LEARNING_MIN_SPEND,
    "LEARNING_MIN_IMPRESSIONS": LEARNING_MIN_IMPRESSIONS,
    "LEARNING_MIN_DAYS": LEARNING_MIN_DAYS,
    "MAX_DATA_STALE_HOURS": MAX_DATA_STALE_HOURS,
    "GOAL_ACHIEVEMENT_BUFFER": GOAL_ACHIEVEMENT_BUFFER,
}


def value(key: str) -> Decimal:
    """Get a threshold value by key (for use in rules)."""
    return THRESHOLDS[key]


def all_thresholds() -> dict[str, Decimal]:
    """Return all thresholds as a dict for serialization."""
    return dict(THRESHOLDS)


__all__ = [
    "THRESHOLD_VERSION",
    "THRESHOLDS",
    "value",
    "all_thresholds",
    "MIN_SPEND_FOR_DECISION",
    "MIN_PURCHASES_FOR_DECISION",
    "ROAS_BUFFER_ABOVE_BREAKEVEN",
    "CPA_BUFFER_BELOW_TARGET",
    "CPA_KILL_MULTIPLIER",
    "ROAS_KILL_BUFFER",
    "MIN_DAYS_FOR_KILL_REVIEW",
    "MIN_SPEND_FOR_KILL_REVIEW",
    "MIN_PURCHASES_FOR_KILL_REVIEW",
    "FORECAST_DETERIORATION_THRESHOLD",
    "FORECAST_IMPROVEMENT_THRESHOLD",
    "LEARNING_MIN_SPEND",
    "LEARNING_MIN_IMPRESSIONS",
    "LEARNING_MIN_DAYS",
    "MAX_DATA_STALE_HOURS",
    "GOAL_ACHIEVEMENT_BUFFER",
]