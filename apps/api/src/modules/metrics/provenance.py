"""Source provenance helpers.

Every metric the analytics layer returns is labelled with where the number
came from. Providers never feed user-facing numbers directly; they write
canonical facts whose rows carry source_type/source_id, and every aggregate
preserves the source label (commerce vs Meta-reported vs economics).
"""

from __future__ import annotations

from src.modules.metrics.definitions import (
    SOURCE_COMMERCE,
    SOURCE_ECONOMICS,
    SOURCE_META_REPORTED,
)

# metric_facts view source_type values (provenance anchor strings).
SOURCE_TYPE_AD_INSIGHT = "ad_insight"
SOURCE_TYPE_ORDER = "order"
SOURCE_TYPE_ORDER_ITEM = "order_item"

# Text labels attached to money values in API responses.
REVENUE_SOURCE_COMMERCE = SOURCE_COMMERCE
REVENUE_SOURCE_META_REPORTED = SOURCE_META_REPORTED
PROFIT_SOURCE_ECONOMICS = SOURCE_ECONOMICS


def commerce_revenue(currency: str, value) -> dict:
    """Business-grain revenue from canonical order data."""
    return {"value": value, "currency": currency, "source": REVENUE_SOURCE_COMMERCE}


def ad_spend(currency: str, value) -> dict:
    """Advertising spend from canonical ad facts (Meta-reported spend)."""
    return {"value": value, "currency": currency, "source": "meta"}


def meta_reported_revenue(currency: str, value) -> dict:
    """Ad-grain revenue as attributed by Meta (conversion_value, all action
    types) — never conflated with commerce revenue."""
    return {"value": value, "currency": currency, "source": REVENUE_SOURCE_META_REPORTED}


def economics_profit(currency: str, value) -> dict:
    """Contribution profit derived from the configured unit-economics
    profile (reuses the Phase 1 calculator)."""
    return {"value": value, "currency": currency, "source": PROFIT_SOURCE_ECONOMICS}
