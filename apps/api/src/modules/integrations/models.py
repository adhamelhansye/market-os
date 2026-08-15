"""Integration domain models: connections, credentials, sync runs, webhook
events, canonical orders/items and customers.

All money columns are NUMERIC (Decimal in Python); external identifiers get
database-level unique constraints so integrity never depends on application
logic alone.

Provider/source columns intentionally have NO check constraint: the provider
enum is extensible (shopify, meta, ga4, ...) and new values must not require
editing past migrations. Status columns are bounded for this phase.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

CONNECTION_STATUSES = ("pending", "connected", "disconnected", "error")
SYNC_STATUSES = ("running", "success", "partial", "failed")
WEBHOOK_STATUSES = ("received", "processing", "processed", "failed", "ignored")

# Canonical order financial/fulfillment states (Shopify subset for now).
FINANCIAL_STATUSES = (
    "pending",
    "authorized",
    "partially_paid",
    "paid",
    "partially_refunded",
    "refunded",
    "voided",
)
FULFILLMENT_STATUSES = ("unfulfilled", "partial", "scheduled", "fulfilled")

_MONEY = Numeric(14, 2)


class IntegrationConnection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "integration_connections"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'connected', 'disconnected', 'error')",
            name="integration_connection_status",
        ),
        # One connection per provider per business.
        Index(
            "uq_integration_connections_business_provider",
            "business_id",
            "provider",
            unique=True,
        ),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending"
    )
    external_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_account_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    provider_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<IntegrationConnection id={self.id} provider={self.provider!r} "
            f"status={self.status!r}>"
        )


class IntegrationCredential(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "integration_credentials"
    __table_args__ = (
        Index("uq_integration_credentials_connection_id", "connection_id", unique=True),
    )

    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("integration_connections.id", ondelete="CASCADE"), nullable=False
    )
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    key_version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))


class SyncRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sync_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'success', 'partial', 'failed')",
            name="sync_run_status",
        ),
        CheckConstraint(
            "records_processed >= 0", name="sync_run_records_processed_non_negative"
        ),
        Index("ix_sync_runs_connection_resource", "connection_id", "resource_type"),
    )

    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("integration_connections.id", ondelete="CASCADE"), nullable=False
    )
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="running", server_default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    records_processed: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WebhookEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "webhook_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('received', 'processing', 'processed', 'failed', 'ignored')",
            name="webhook_event_status",
        ),
        # Idempotency: a provider event id may only ever be recorded once.
        Index(
            "uq_webhook_events_provider_external_event_id",
            "provider",
            "external_event_id",
            unique=True,
            postgresql_where=text("external_event_id IS NOT NULL"),
        ),
    )

    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    external_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="received", server_default="received")
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class Customer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (
        Index("uq_customers_business_external_id", "business_id", "external_id", unique=True),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)


class Order(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "financial_status IN "
            "('pending', 'authorized', 'partially_paid', 'paid', "
            "'partially_refunded', 'refunded', 'voided')",
            name="order_financial_status",
        ),
        CheckConstraint(
            "fulfillment_status IS NULL OR fulfillment_status IN "
            "('unfulfilled', 'partial', 'scheduled', 'fulfilled')",
            name="order_fulfillment_status",
        ),
        CheckConstraint("subtotal >= 0", name="order_subtotal_non_negative"),
        CheckConstraint("discount_total >= 0", name="order_discount_total_non_negative"),
        CheckConstraint("shipping_revenue >= 0", name="order_shipping_revenue_non_negative"),
        CheckConstraint("tax_total IS NULL OR tax_total >= 0", name="order_tax_total_non_negative"),
        CheckConstraint("total >= 0", name="order_total_non_negative"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="order_currency_format"),
        # Idempotency anchor: an external order can exist at most once.
        Index(
            "uq_orders_business_source_external_id",
            "business_id",
            "source",
            "external_id",
            unique=True,
        ),
        Index("ix_orders_business_ordered_at", "business_id", "ordered_at"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    discount_total: Mapped[Decimal] = mapped_column(_MONEY, nullable=False, default=Decimal("0"))
    shipping_revenue: Mapped[Decimal] = mapped_column(
        _MONEY, nullable=False, default=Decimal("0")
    )
    tax_total: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    total: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    financial_status: Mapped[str] = mapped_column(String(30), nullable=False)
    fulfillment_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    ordered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OrderItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="order_item_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="order_item_unit_price_non_negative"),
        CheckConstraint("discount_amount >= 0", name="order_item_discount_non_negative"),
        CheckConstraint("line_total >= 0", name="order_item_line_total_non_negative"),
        Index("ix_order_items_order_id", "order_id"),
        Index("ix_order_items_product_id", "product_id"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    external_product_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_variant_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(_MONEY, nullable=False, default=Decimal("0"))
    line_total: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
