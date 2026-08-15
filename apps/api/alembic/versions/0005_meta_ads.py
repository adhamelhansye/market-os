"""meta ads: canonical ad account hierarchy + daily insights; multi-account
connections

Adds the Phase 2B tables for Meta Ads read-only ingestion: one ad account
per connection row (the old business+provider singleton uniqueness is
widened to business+provider+external_account_id), canonical
account/campaign/ad-set/ad/creative metadata, and daily insights facts with
a NULL-safe hierarchy.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _money() -> sa.Numeric:
    return sa.Numeric(14, 2)


def _uuid_pk() -> sa.Column:
    return sa.Column("id", sa.Uuid(), primary_key=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    # One connection per (business, provider, external account): Meta may
    # connect several ad accounts per business; Shopify keeps its singleton
    # behavior because its external_account_id is always set.
    op.drop_constraint(
        "uq_integration_connections_business_id_provider",
        "integration_connections",
        type_="unique",
    )
    op.create_index(
        "uq_integration_connections_business_provider_account",
        "integration_connections",
        ["business_id", "provider", "external_account_id"],
        unique=True,
        postgresql_where=sa.text("external_account_id IS NOT NULL"),
    )

    op.create_table(
        "ad_accounts",
        _uuid_pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("integration_connection_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("timezone", sa.String(length=100), nullable=True),
        sa.Column("timezone_offset_hours_utc", sa.Numeric(8, 4), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        *_timestamps(),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_ad_accounts_currency_format"),
        sa.ForeignKeyConstraint(
            ["business_id"], ["businesses.id"],
            name="fk_ad_accounts_businesses_business_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["integration_connection_id"], ["integration_connections.id"],
            name="fk_ad_accounts_connections_connection_id", ondelete="CASCADE",
        ),
    )
    op.create_index("ix_ad_accounts_business_id", "ad_accounts", ["business_id"])
    op.create_index(
        "uq_ad_accounts_business_external_id", "ad_accounts",
        ["business_id", "external_id"], unique=True,
    )
    op.create_index(
        "uq_ad_accounts_connection_id", "ad_accounts", ["integration_connection_id"], unique=True
    )

    op.create_table(
        "creatives",
        _uuid_pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("external_id", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("type", sa.String(length=50), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("call_to_action", sa.String(length=50), nullable=True),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("created_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_time", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["business_id"], ["businesses.id"],
            name="fk_creatives_businesses_business_id", ondelete="CASCADE",
        ),
    )
    op.create_index("ix_creatives_business_id", "creatives", ["business_id"])
    op.create_index(
        "uq_creatives_business_provider_external_id",
        "creatives", ["business_id", "provider", "external_id"], unique=True,
    )

    op.create_table(
        "campaigns",
        _uuid_pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("ad_account_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("objective", sa.String(length=50), nullable=True),
        sa.Column("buying_type", sa.String(length=30), nullable=True),
        sa.Column("created_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_time", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["business_id"], ["businesses.id"],
            name="fk_campaigns_businesses_business_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ad_account_id"], ["ad_accounts.id"],
            name="fk_campaigns_ad_accounts_ad_account_id", ondelete="CASCADE",
        ),
    )
    op.create_index("ix_campaigns_business_id", "campaigns", ["business_id"])
    op.create_index("ix_campaigns_ad_account_id", "campaigns", ["ad_account_id"])
    op.create_index(
        "uq_campaigns_business_account_external_id",
        "campaigns", ["business_id", "ad_account_id", "external_id"], unique=True,
    )

    op.create_table(
        "ad_sets",
        _uuid_pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("ad_account_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=True),
        sa.Column("external_id", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("optimization_goal", sa.String(length=100), nullable=True),
        sa.Column("billing_event", sa.String(length=50), nullable=True),
        sa.Column("created_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_time", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["business_id"], ["businesses.id"],
            name="fk_ad_sets_businesses_business_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ad_account_id"], ["ad_accounts.id"],
            name="fk_ad_sets_ad_accounts_ad_account_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["campaigns.id"],
            name="fk_ad_sets_campaigns_campaign_id", ondelete="SET NULL",
        ),
    )
    op.create_index("ix_ad_sets_business_id", "ad_sets", ["business_id"])
    op.create_index("ix_ad_sets_ad_account_id", "ad_sets", ["ad_account_id"])
    op.create_index("ix_ad_sets_campaign_id", "ad_sets", ["campaign_id"])
    op.create_index(
        "uq_ad_sets_business_account_external_id",
        "ad_sets", ["business_id", "ad_account_id", "external_id"], unique=True,
    )

    op.create_table(
        "ads",
        _uuid_pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("ad_account_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=True),
        sa.Column("ad_set_id", sa.Uuid(), nullable=True),
        sa.Column("creative_id", sa.Uuid(), nullable=True),
        sa.Column("external_id", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_time", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["business_id"], ["businesses.id"],
            name="fk_ads_businesses_business_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ad_account_id"], ["ad_accounts.id"],
            name="fk_ads_ad_accounts_ad_account_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["campaigns.id"],
            name="fk_ads_campaigns_campaign_id", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["ad_set_id"], ["ad_sets.id"],
            name="fk_ads_ad_sets_ad_set_id", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["creative_id"], ["creatives.id"],
            name="fk_ads_creatives_creative_id", ondelete="SET NULL",
        ),
    )
    op.create_index("ix_ads_business_id", "ads", ["business_id"])
    op.create_index("ix_ads_ad_account_id", "ads", ["ad_account_id"])
    op.create_index("ix_ads_campaign_id", "ads", ["campaign_id"])
    op.create_index("ix_ads_ad_set_id", "ads", ["ad_set_id"])
    op.create_index(
        "uq_ads_business_account_external_id",
        "ads", ["business_id", "ad_account_id", "external_id"], unique=True,
    )

    op.create_table(
        "ad_insights",
        _uuid_pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("ad_account_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=True),
        sa.Column("ad_set_id", sa.Uuid(), nullable=True),
        sa.Column("ad_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("grain", sa.String(length=10), nullable=False, server_default="daily"),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("reach", sa.Integer(), nullable=True),
        sa.Column("frequency", sa.Numeric(14, 4), nullable=True),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("link_clicks", sa.Integer(), nullable=True),
        sa.Column("landing_page_views", sa.Integer(), nullable=True),
        sa.Column("spend", _money(), nullable=False, server_default=sa.text("0")),
        sa.Column("conversions", sa.Integer(), nullable=True),
        sa.Column("conversion_value", _money(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("impressions >= 0", name="ck_ad_insights_impressions_non_negative"),
        sa.CheckConstraint("clicks >= 0", name="ck_ad_insights_clicks_non_negative"),
        sa.CheckConstraint("spend >= 0", name="ck_ad_insights_spend_non_negative"),
        sa.CheckConstraint(
            "conversion_value IS NULL OR conversion_value >= 0",
            name="ck_ad_insights_conversion_value_non_negative",
        ),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_ad_insights_currency_format"),
        sa.ForeignKeyConstraint(
            ["business_id"], ["businesses.id"],
            name="fk_ad_insights_businesses_business_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ad_account_id"], ["ad_accounts.id"],
            name="fk_ad_insights_ad_accounts_ad_account_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["campaigns.id"],
            name="fk_ad_insights_campaigns_campaign_id", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["ad_set_id"], ["ad_sets.id"],
            name="fk_ad_insights_ad_sets_ad_set_id", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["ad_id"], ["ads.id"],
            name="fk_ad_insights_ads_ad_id", ondelete="SET NULL",
        ),
    )
    op.create_index("ix_ad_insights_business_id", "ad_insights", ["business_id"])
    op.create_index("ix_ad_insights_account_date", "ad_insights", ["ad_account_id", "date"])
    op.create_index(
        "uq_ad_insights_business_account_hierarchy",
        "ad_insights",
        [
            "business_id",
            "ad_account_id",
            "provider",
            "date",
            "grain",
            sa.text("COALESCE(campaign_id::text, '')"),
            sa.text("COALESCE(ad_set_id::text, '')"),
            sa.text("COALESCE(ad_id::text, '')"),
        ],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_ad_insights_business_account_hierarchy", table_name="ad_insights")
    op.drop_index("ix_ad_insights_account_date", table_name="ad_insights")
    op.drop_index("ix_ad_insights_business_id", table_name="ad_insights")
    op.drop_table("ad_insights")
    op.drop_index("uq_ads_business_account_external_id", table_name="ads")
    op.drop_index("ix_ads_ad_set_id", table_name="ads")
    op.drop_index("ix_ads_campaign_id", table_name="ads")
    op.drop_index("ix_ads_ad_account_id", table_name="ads")
    op.drop_index("ix_ads_business_id", table_name="ads")
    op.drop_table("ads")
    op.drop_index("uq_ad_sets_business_account_external_id", table_name="ad_sets")
    op.drop_index("ix_ad_sets_campaign_id", table_name="ad_sets")
    op.drop_index("ix_ad_sets_ad_account_id", table_name="ad_sets")
    op.drop_index("ix_ad_sets_business_id", table_name="ad_sets")
    op.drop_table("ad_sets")
    op.drop_index("uq_campaigns_business_account_external_id", table_name="campaigns")
    op.drop_index("ix_campaigns_ad_account_id", table_name="campaigns")
    op.drop_index("ix_campaigns_business_id", table_name="campaigns")
    op.drop_table("campaigns")
    op.drop_index("uq_creatives_business_provider_external_id", table_name="creatives")
    op.drop_index("ix_creatives_business_id", table_name="creatives")
    op.drop_table("creatives")
    op.drop_index("uq_ad_accounts_connection_id", table_name="ad_accounts")
    op.drop_index("uq_ad_accounts_business_external_id", table_name="ad_accounts")
    op.drop_index("ix_ad_accounts_business_id", table_name="ad_accounts")
    op.drop_table("ad_accounts")
    op.drop_index(
        "uq_integration_connections_business_provider_account",
        table_name="integration_connections",
    )
    op.create_unique_constraint(
        "uq_integration_connections_business_id_provider",
        "integration_connections",
        ["business_id", "provider"],
    )