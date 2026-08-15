"""Canonical metrics layer model.

`metric_facts` is the single read-mostly lens over provider-canonical facts
(see migration 0006). It is a UNION VIEW, not a table: no sync step, no
second source of truth. Every row carries provenance (source_type/source_id)
back to the canonical fact that produced it.

The SQLAlchemy Core table below is query-only — the same shape as the
PostgreSQL view it maps onto. Grains:

- 'ad'          finest advertising grain (every current ad_insight row)
- 'business'    one row per order
- 'product'     one row per order item

Higher advertising grains (ad_set, campaign, ad_account) are rollups of the
'ad' rows and are never stored. Ad rows expose Meta-reported facts
(conversions, conversion_value) as columns distinct from commerce columns
(revenue, refunds, purchases); the engine keeps sources labeled separately.
"""

from __future__ import annotations

import sqlalchemy as sa

from src.modules.metrics.definitions import PROVIDER_META, PROVIDER_SHOPIFY
from src.modules.metrics.provenance import (
    SOURCE_TYPE_AD_INSIGHT,
    SOURCE_TYPE_ORDER,
    SOURCE_TYPE_ORDER_ITEM,
)

GRAIN_AD = "ad"
GRAIN_AD_SET = "ad_set"
GRAIN_CAMPAIGN = "campaign"
GRAIN_AD_ACCOUNT = "ad_account"
GRAIN_BUSINESS = "business"
GRAIN_PRODUCT = "product"

# Grains that carry advertising facts (rollup sources).
AD_GRAINS = frozenset((GRAIN_AD, GRAIN_AD_SET, GRAIN_CAMPAIGN, GRAIN_AD_ACCOUNT))
# Grains that carry canonical commerce facts.
COMMERCE_GRAINS = frozenset((GRAIN_BUSINESS, GRAIN_PRODUCT))

_MONEY = sa.Numeric(14, 2)
_BIGINT = sa.BigInteger()
_ID = sa.Uuid()

metric_facts = sa.Table(
    "metric_facts",
    sa.MetaData(),
    sa.Column("business_id", _ID, nullable=False),
    sa.Column("provider", sa.String(20), nullable=False),
    sa.Column("source_type", sa.String(20), nullable=False),
    sa.Column("source_id", sa.String(36), nullable=False),
    sa.Column("ad_account_id", _ID, nullable=True),
    sa.Column("campaign_id", _ID, nullable=True),
    sa.Column("ad_set_id", _ID, nullable=True),
    sa.Column("ad_id", _ID, nullable=True),
    sa.Column("product_id", _ID, nullable=True),
    sa.Column("date", sa.Date(), nullable=False),
    sa.Column("grain", sa.String(12), nullable=False),
    sa.Column("currency", sa.String(3), nullable=False),
    sa.Column("impressions", _BIGINT, nullable=True),
    sa.Column("reach", _BIGINT, nullable=True),
    sa.Column("clicks", _BIGINT, nullable=True),
    sa.Column("link_clicks", _BIGINT, nullable=True),
    sa.Column("landing_page_views", _BIGINT, nullable=True),
    sa.Column("sessions", _BIGINT, nullable=True),
    sa.Column("product_views", _BIGINT, nullable=True),
    sa.Column("add_to_cart", _BIGINT, nullable=True),
    sa.Column("checkout_started", _BIGINT, nullable=True),
    sa.Column("purchases", _BIGINT, nullable=True),
    sa.Column("revenue", _MONEY, nullable=True),
    sa.Column("spend", _MONEY, nullable=True),
    sa.Column("refunds", _MONEY, nullable=True),
    sa.Column("cogs", _MONEY, nullable=True),
    sa.Column("shipping_cost", _MONEY, nullable=True),
    sa.Column("payment_fees", _MONEY, nullable=True),
    sa.Column("conversions", _BIGINT, nullable=True),
    sa.Column("conversion_value", _MONEY, nullable=True),
)

# Field aliases mirrored from the view so aggregation queries stay typed.
F = {column.name: column for column in metric_facts.columns}

__all__ = [
    "metric_facts",
    "F",
    "GRAIN_AD",
    "GRAIN_AD_SET",
    "GRAIN_CAMPAIGN",
    "GRAIN_AD_ACCOUNT",
    "GRAIN_BUSINESS",
    "GRAIN_PRODUCT",
    "AD_GRAINS",
    "COMMERCE_GRAINS",
    "PROVIDER_META",
    "PROVIDER_SHOPIFY",
    "SOURCE_TYPE_AD_INSIGHT",
    "SOURCE_TYPE_ORDER",
    "SOURCE_TYPE_ORDER_ITEM",
]
