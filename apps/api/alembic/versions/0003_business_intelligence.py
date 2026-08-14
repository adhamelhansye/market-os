"""business intelligence core: products, pricing, costs, shipping,
discounts, bundles, inventory, goals, profiles

Adds the Phase 1 business intelligence tables plus the new optional
Business columns (description, country, website_url).

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _money() -> sa.Numeric:
    return sa.Numeric(12, 2)


def upgrade() -> None:
    op.add_column(
        "businesses",
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.add_column(
        "businesses",
        sa.Column("country", sa.String(length=2), nullable=True),
    )
    op.add_column(
        "businesses",
        sa.Column("website_url", sa.String(length=500), nullable=True),
    )

    op.create_table(
        "business_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("industry", sa.String(length=100), nullable=True),
        sa.Column("business_model", sa.String(length=50), nullable=True),
        sa.Column("target_market", sa.String(length=255), nullable=True),
        sa.Column("brand_positioning", sa.Text(), nullable=True),
        sa.Column("average_order_value", _money(), nullable=True),
        sa.Column("primary_customer_type", sa.String(length=50), nullable=True),
        sa.Column("brand_voice", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], name="fk_business_profiles_businesses_business_id", ondelete="CASCADE"),
        sa.UniqueConstraint("business_id", name="uq_business_profiles_business_id"),
    )
    op.create_index("ix_business_profiles_business_id", "business_profiles", ["business_id"], unique=True)

    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('active', 'inactive', 'archived')", name="ck_products_product_status"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], name="fk_products_businesses_business_id", ondelete="CASCADE"),
    )
    op.create_index("ix_products_business_id", "products", ["business_id"])
    op.create_index(
        "uq_products_business_sku", "products", ["business_id", "sku"], unique=True,
        postgresql_where=sa.text("sku IS NOT NULL"),
    )

    op.create_table(
        "product_prices",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("price", _money(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("price >= 0", name="ck_product_prices_price_non_negative"),
        sa.CheckConstraint("effective_to IS NULL OR effective_to > effective_from", name="ck_product_prices_price_period"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_product_prices_products_product_id", ondelete="CASCADE"),
    )
    op.create_index("ix_product_prices_product_id", "product_prices", ["product_id"])
    op.create_index("ix_product_prices_effective_from", "product_prices", ["effective_from"])

    op.create_table(
        "product_costs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("cogs", _money(), nullable=False, server_default=sa.text("0")),
        sa.Column("packaging_cost", _money(), nullable=False, server_default=sa.text("0")),
        sa.Column("payment_fee_fixed", _money(), nullable=False, server_default=sa.text("0")),
        sa.Column("payment_fee_percent", sa.Numeric(8, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("cogs >= 0", name="ck_product_costs_cogs_non_negative"),
        sa.CheckConstraint("packaging_cost >= 0", name="ck_product_costs_packaging_non_negative"),
        sa.CheckConstraint("payment_fee_fixed >= 0", name="ck_product_costs_payment_fee_fixed_non_negative"),
        sa.CheckConstraint("payment_fee_percent >= 0 AND payment_fee_percent <= 100", name="ck_product_costs_payment_fee_percent_range"),
        sa.CheckConstraint("effective_to IS NULL OR effective_to > effective_from", name="ck_product_costs_cost_period"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_product_costs_products_product_id", ondelete="CASCADE"),
    )
    op.create_index("ix_product_costs_product_id", "product_costs", ["product_id"])
    op.create_index("ix_product_costs_effective_from", "product_costs", ["effective_from"])

    op.create_table(
        "shipping_rules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("country", sa.String(length=100), nullable=False),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("method", sa.String(length=50), nullable=False),
        sa.Column("cost", _money(), nullable=False, server_default=sa.text("0")),
        sa.Column("customer_price", _money(), nullable=False, server_default=sa.text("0")),
        sa.Column("free_shipping_threshold", _money(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("cost >= 0", name="ck_shipping_rules_shipping_cost_non_negative"),
        sa.CheckConstraint("customer_price >= 0", name="ck_shipping_rules_shipping_customer_price_non_negative"),
        sa.CheckConstraint("free_shipping_threshold IS NULL OR free_shipping_threshold >= 0", name="ck_shipping_rules_shipping_free_threshold_non_negative"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], name="fk_shipping_rules_businesses_business_id", ondelete="CASCADE"),
    )
    op.create_index("ix_shipping_rules_business_id", "shipping_rules", ["business_id"])

    op.create_table(
        "discounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("value", _money(), nullable=False),
        sa.Column("minimum_order_value", _money(), nullable=True),
        sa.Column("maximum_discount", _money(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("type IN ('percentage', 'fixed_amount')", name="ck_discounts_discount_type"),
        sa.CheckConstraint("value > 0", name="ck_discounts_discount_value_positive"),
        sa.CheckConstraint("type <> 'percentage' OR value <= 100", name="ck_discounts_discount_percentage_max"),
        sa.CheckConstraint("minimum_order_value IS NULL OR minimum_order_value >= 0", name="ck_discounts_discount_minimum_order_value_non_negative"),
        sa.CheckConstraint("maximum_discount IS NULL OR maximum_discount > 0", name="ck_discounts_discount_maximum_discount_positive"),
        sa.CheckConstraint("ends_at > starts_at", name="ck_discounts_discount_period"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], name="fk_discounts_businesses_business_id", ondelete="CASCADE"),
    )
    op.create_index("ix_discounts_business_id", "discounts", ["business_id"])

    op.create_table(
        "bundles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", _money(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("price >= 0", name="ck_bundles_bundle_price_non_negative"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], name="fk_bundles_businesses_business_id", ondelete="CASCADE"),
    )
    op.create_index("ix_bundles_business_id", "bundles", ["business_id"])

    op.create_table(
        "bundle_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("bundle_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("quantity > 0", name="ck_bundle_items_bundle_item_quantity_positive"),
        sa.ForeignKeyConstraint(["bundle_id"], ["bundles.id"], name="fk_bundle_items_bundles_bundle_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_bundle_items_products_product_id", ondelete="CASCADE"),
        sa.UniqueConstraint("bundle_id", "product_id", name="uq_bundle_items_bundle_id_product_id"),
    )
    op.create_index("ix_bundle_items_bundle_id", "bundle_items", ["bundle_id"])
    op.create_index("ix_bundle_items_product_id", "bundle_items", ["product_id"])

    op.create_table(
        "inventory_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("quantity >= 0", name="ck_inventory_snapshots_inventory_quantity_non_negative"),
        sa.CheckConstraint("source IN ('manual', 'system', 'shopify')", name="ck_inventory_snapshots_inventory_source"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_inventory_snapshots_products_product_id", ondelete="CASCADE"),
    )
    op.create_index("ix_inventory_snapshots_product_id", "inventory_snapshots", ["product_id"])
    op.create_index("ix_inventory_snapshots_recorded_at", "inventory_snapshots", ["recorded_at"])

    op.create_table(
        "business_goals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_revenue", sa.Numeric(14, 2), nullable=True),
        sa.Column("target_profit", sa.Numeric(14, 2), nullable=True),
        sa.Column("ad_budget", sa.Numeric(14, 2), nullable=True),
        sa.Column("maximum_cpa", sa.Numeric(14, 2), nullable=True),
        sa.Column("target_roas", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("period_end > period_start", name="ck_business_goals_goal_period"),
        sa.CheckConstraint("target_revenue IS NULL OR target_revenue >= 0", name="ck_business_goals_goal_revenue_non_negative"),
        sa.CheckConstraint("target_profit IS NULL OR target_profit >= 0", name="ck_business_goals_goal_profit_non_negative"),
        sa.CheckConstraint("ad_budget IS NULL OR ad_budget > 0", name="ck_business_goals_goal_ad_budget_positive"),
        sa.CheckConstraint("maximum_cpa IS NULL OR maximum_cpa > 0", name="ck_business_goals_goal_max_cpa_positive"),
        sa.CheckConstraint("target_roas IS NULL OR target_roas > 0", name="ck_business_goals_goal_roas_positive"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], name="fk_business_goals_businesses_business_id", ondelete="CASCADE"),
    )
    op.create_index("ix_business_goals_business_id", "business_goals", ["business_id"])
    op.create_index("ix_business_goals_period_start", "business_goals", ["period_start"])


def downgrade() -> None:
    op.drop_table("business_goals")
    op.drop_table("inventory_snapshots")
    op.drop_table("bundle_items")
    op.drop_table("bundles")
    op.drop_table("discounts")
    op.drop_table("shipping_rules")
    op.drop_table("product_costs")
    op.drop_table("product_prices")
    op.drop_table("products")
    op.drop_table("business_profiles")
    op.drop_column("businesses", "website_url")
    op.drop_column("businesses", "country")
    op.drop_column("businesses", "description")