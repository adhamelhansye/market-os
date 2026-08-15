"""unified metrics: canonical metric_facts view + rollup indexes

Creates `metric_facts`, the single canonical metrics layer read by the
deterministic KPI engine. It is a UNION VIEW over the provider canonical
facts (ad_insights for Meta, orders/order_items for Shopify) — a read-only
projection, so there is exactly one source of truth and no sync step to
diverge. Each row carries provenance (source_type/source_id) back to its
canonical fact row.

Grains: 'ad' (finest advertising grain; every current ad_insight row is an
ad-level row because insights are ingested at `level=ad`), 'business'
(one row per order), 'product' (one row per order item). Higher ad grains
(ad_set/campaign/ad_account) are rollups of the 'ad' rows, never stored.

Ad rows expose Meta-reported `conversion_value` (attributed value, all
action types) separately from commerce `revenue`; the KPI engine keeps the
two labeled sources apart (reconciliation, never assumed equal).

Also adds ad_insights rollup indexes used by the metrics aggregation
(campaign_id/ad_set_id/ad_id grouping and business-wide date scans).

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MONEY = "numeric(14, 2)"

_METRIC_FACTS_VIEW = sa.text(
    f"""
CREATE VIEW metric_facts AS
SELECT
    ai.business_id                             AS business_id,
    ai.provider                                AS provider,
    'ad_insight'                               AS source_type,
    ai.id::text                                AS source_id,
    ai.ad_account_id                           AS ad_account_id,
    ai.campaign_id                             AS campaign_id,
    ai.ad_set_id                               AS ad_set_id,
    ai.ad_id                                   AS ad_id,
    NULL::uuid                                 AS product_id,
    ai.date                                    AS date,
    CASE
        WHEN ai.ad_id IS NOT NULL THEN 'ad'
        WHEN ai.ad_set_id IS NOT NULL THEN 'ad_set'
        WHEN ai.campaign_id IS NOT NULL THEN 'campaign'
        ELSE 'ad_account'
    END                                        AS grain,
    ai.currency                                AS currency,
    ai.impressions::bigint                     AS impressions,
    ai.reach::bigint                           AS reach,
    ai.clicks::bigint                          AS clicks,
    ai.link_clicks::bigint                     AS link_clicks,
    ai.landing_page_views::bigint              AS landing_page_views,
    NULL::bigint                               AS sessions,
    NULL::bigint                               AS product_views,
    NULL::bigint                               AS add_to_cart,
    NULL::bigint                               AS checkout_started,
    NULL::bigint                               AS purchases,
    NULL::{_MONEY}                             AS revenue,
    ai.spend                                   AS spend,
    NULL::{_MONEY}                             AS refunds,
    NULL::{_MONEY}                             AS cogs,
    NULL::{_MONEY}                             AS shipping_cost,
    NULL::{_MONEY}                             AS payment_fees,
    ai.conversions::bigint                     AS conversions,
    ai.conversion_value                        AS conversion_value
FROM ad_insights ai

UNION ALL

SELECT
    o.business_id                              AS business_id,
    o.source                                   AS provider,
    'order'                                    AS source_type,
    o.id::text                                 AS source_id,
    NULL::uuid                                 AS ad_account_id,
    NULL::uuid                                 AS campaign_id,
    NULL::uuid                                 AS ad_set_id,
    NULL::uuid                                 AS ad_id,
    NULL::uuid                                 AS product_id,
    o.ordered_at::date                         AS date,
    'business'                                 AS grain,
    o.currency                                 AS currency,
    NULL::bigint                               AS impressions,
    NULL::bigint                               AS reach,
    NULL::bigint                               AS clicks,
    NULL::bigint                               AS link_clicks,
    NULL::bigint                               AS landing_page_views,
    NULL::bigint                               AS sessions,
    NULL::bigint                               AS product_views,
    NULL::bigint                               AS add_to_cart,
    NULL::bigint                               AS checkout_started,
    1::bigint                                  AS purchases,
    o.total                                    AS revenue,
    NULL::{_MONEY}                             AS spend,
    CASE
        WHEN o.financial_status IN ('refunded', 'partially_refunded')
        THEN o.total
        ELSE 0::{_MONEY}
    END                                        AS refunds,
    NULL::{_MONEY}                             AS cogs,
    NULL::{_MONEY}                             AS shipping_cost,
    NULL::{_MONEY}                             AS payment_fees,
    NULL::bigint                               AS conversions,
    NULL::{_MONEY}                             AS conversion_value
FROM orders o

UNION ALL

SELECT
    o.business_id                              AS business_id,
    o.source                                   AS provider,
    'order_item'                               AS source_type,
    oi.id::text                                AS source_id,
    NULL::uuid                                 AS ad_account_id,
    NULL::uuid                                 AS campaign_id,
    NULL::uuid                                 AS ad_set_id,
    NULL::uuid                                 AS ad_id,
    oi.product_id                              AS product_id,
    o.ordered_at::date                         AS date,
    'product'                                  AS grain,
    o.currency                                 AS currency,
    NULL::bigint                               AS impressions,
    NULL::bigint                               AS reach,
    NULL::bigint                               AS clicks,
    NULL::bigint                               AS link_clicks,
    NULL::bigint                               AS landing_page_views,
    NULL::bigint                               AS sessions,
    NULL::bigint                               AS product_views,
    NULL::bigint                               AS add_to_cart,
    NULL::bigint                               AS checkout_started,
    oi.quantity::bigint                        AS purchases,
    oi.line_total                              AS revenue,
    NULL::{_MONEY}                             AS spend,
    NULL::{_MONEY}                             AS refunds,
    NULL::{_MONEY}                             AS cogs,
    NULL::{_MONEY}                             AS shipping_cost,
    NULL::{_MONEY}                             AS payment_fees,
    NULL::bigint                               AS conversions,
    NULL::{_MONEY}                             AS conversion_value
FROM order_items oi
JOIN orders o ON o.id = oi.order_id
"""
)


def upgrade() -> None:
    op.execute(_METRIC_FACTS_VIEW)
    # Rollup/grouping indexes for the metrics aggregation layer.
    op.create_index("ix_ad_insights_campaign_id", "ad_insights", ["campaign_id"])
    op.create_index("ix_ad_insights_ad_set_id", "ad_insights", ["ad_set_id"])
    op.create_index("ix_ad_insights_ad_id", "ad_insights", ["ad_id"])
    op.create_index("ix_ad_insights_business_date", "ad_insights", ["business_id", "date"])


def downgrade() -> None:
    op.drop_index("ix_ad_insights_business_date", table_name="ad_insights")
    op.drop_index("ix_ad_insights_ad_id", table_name="ad_insights")
    op.drop_index("ix_ad_insights_ad_set_id", table_name="ad_insights")
    op.drop_index("ix_ad_insights_campaign_id", table_name="ad_insights")
    op.execute("DROP VIEW IF EXISTS metric_facts")