"""integration core: connections, credentials, sync runs, webhook events,
canonical orders/items and customers; products gain external sync anchors

Adds the Phase 2A tables for provider connections (encrypted credentials),
background sync bookkeeping, webhook deduplication and canonical commerce
data, plus the external_id/external_source columns on products used to map
provider products onto the existing product model.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _money() -> sa.Numeric:
    return sa.Numeric(14, 2)


def upgrade() -> None:
    op.add_column("products", sa.Column("external_id", sa.String(length=255), nullable=True))
    op.add_column("products", sa.Column("external_source", sa.String(length=20), nullable=True))
    op.create_index(
        "uq_products_business_external_id",
        "products",
        ["business_id", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )

    op.create_table(
        "integration_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("external_account_id", sa.String(length=255), nullable=True),
        sa.Column("external_account_name", sa.String(length=255), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("provider_metadata", sa.JSON(), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('pending', 'connected', 'disconnected', 'error')",
            name="ck_integration_connections_integration_connection_status",
        ),
        sa.ForeignKeyConstraint(
            ["business_id"], ["businesses.id"],
            name="fk_integration_connections_businesses_business_id", ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "business_id", "provider", name="uq_integration_connections_business_id_provider"
        ),
    )
    op.create_index("ix_integration_connections_business_id", "integration_connections", ["business_id"])

    op.create_table(
        "integration_credentials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("key_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["integration_connections.id"],
            name="fk_credentials_connection_id", ondelete="CASCADE",
        ),
        sa.UniqueConstraint("connection_id", name="uq_integration_credentials_connection_id"),
    )

    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("records_processed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("cursor", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'partial', 'failed')", name="ck_sync_runs_sync_run_status"
        ),
        sa.CheckConstraint("records_processed >= 0", name="ck_sync_runs_sync_run_records_processed_non_negative"),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["integration_connections.id"],
            name="fk_sync_runs_integration_connections_connection_id", ondelete="CASCADE",
        ),
    )
    op.create_index("ix_sync_runs_connection_id_resource_type", "sync_runs", ["connection_id", "resource_type"])

    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("external_event_id", sa.String(length=255), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="received"),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('received', 'processing', 'processed', 'failed', 'ignored')",
            name="ck_webhook_events_webhook_event_status",
        ),
    )
    op.create_index("ix_webhook_events_provider", "webhook_events", ["provider"])
    op.create_index(
        "uq_webhook_events_provider_external_event_id",
        "webhook_events",
        ["provider", "external_event_id"],
        unique=True,
        postgresql_where=sa.text("external_event_id IS NOT NULL"),
    )

    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["business_id"], ["businesses.id"],
            name="fk_customers_businesses_business_id", ondelete="CASCADE",
        ),
        sa.UniqueConstraint("business_id", "external_id", name="uq_customers_business_id_external_id"),
    )
    op.create_index("ix_customers_business_id", "customers", ["business_id"])

    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("subtotal", _money(), nullable=False),
        sa.Column("discount_total", _money(), nullable=False, server_default=sa.text("0")),
        sa.Column("shipping_revenue", _money(), nullable=False, server_default=sa.text("0")),
        sa.Column("tax_total", _money(), nullable=True),
        sa.Column("total", _money(), nullable=False),
        sa.Column("financial_status", sa.String(length=30), nullable=False),
        sa.Column("fulfillment_status", sa.String(length=30), nullable=True),
        sa.Column("ordered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "financial_status IN ('pending', 'authorized', 'partially_paid', 'paid', "
            "'partially_refunded', 'refunded', 'voided')",
            name="ck_orders_order_financial_status",
        ),
        sa.CheckConstraint(
            "fulfillment_status IS NULL OR fulfillment_status IN "
            "('unfulfilled', 'partial', 'scheduled', 'fulfilled')",
            name="ck_orders_order_fulfillment_status",
        ),
        sa.CheckConstraint("subtotal >= 0", name="ck_orders_order_subtotal_non_negative"),
        sa.CheckConstraint("discount_total >= 0", name="ck_orders_order_discount_total_non_negative"),
        sa.CheckConstraint("shipping_revenue >= 0", name="ck_orders_order_shipping_revenue_non_negative"),
        sa.CheckConstraint("tax_total IS NULL OR tax_total >= 0", name="ck_orders_order_tax_total_non_negative"),
        sa.CheckConstraint("total >= 0", name="ck_orders_order_total_non_negative"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_orders_order_currency_format"),
        sa.ForeignKeyConstraint(
            ["business_id"], ["businesses.id"],
            name="fk_orders_businesses_business_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"],
            name="fk_orders_customers_customer_id", ondelete="SET NULL",
        ),
        sa.UniqueConstraint("business_id", "source", "external_id", name="uq_orders_business_id_source_external_id"),
    )
    op.create_index("ix_orders_business_id", "orders", ["business_id"])
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"])
    op.create_index("ix_orders_business_id_ordered_at", "orders", ["business_id", "ordered_at"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("external_product_id", sa.String(length=255), nullable=False),
        sa.Column("external_variant_id", sa.String(length=255), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", _money(), nullable=False),
        sa.Column("discount_amount", _money(), nullable=False, server_default=sa.text("0")),
        sa.Column("line_total", _money(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_order_items_order_item_quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_order_items_order_item_unit_price_non_negative"),
        sa.CheckConstraint("discount_amount >= 0", name="ck_order_items_order_item_discount_non_negative"),
        sa.CheckConstraint("line_total >= 0", name="ck_order_items_order_item_line_total_non_negative"),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"],
            name="fk_order_items_orders_order_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"],
            name="fk_order_items_products_product_id", ondelete="SET NULL",
        ),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_index("ix_order_items_product_id", "order_items", ["product_id"])


def downgrade() -> None:
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("customers")
    op.drop_table("webhook_events")
    op.drop_table("sync_runs")
    op.drop_table("integration_credentials")
    op.drop_table("integration_connections")
    op.drop_index("uq_products_business_external_id", table_name="products")
    op.drop_column("products", "external_source")
    op.drop_column("products", "external_id")
