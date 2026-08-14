"""Shared constants for the economics module."""

from decimal import Decimal

ZERO = Decimal("0")

# Reason codes for metrics that cannot be derived from the available data.
TARGET_CPA_REASON_NOT_PROVIDED = "target_profit_per_order_not_provided"
TARGET_CPA_REASON_NO_PRICE = "no_active_price"
TARGET_CPA_REASON_NEGATIVE_CONTRIBUTION = "negative_contribution_profit"
