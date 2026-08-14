"""Inventory snapshots. Each change appends a snapshot; "current inventory"
is the latest snapshot per product. Sources: manual (Phase 1), system,
shopify (both future)."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base, UUIDPrimaryKeyMixin

INVENTORY_SOURCES = ("manual", "system", "shopify")


class InventorySnapshot(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "inventory_snapshots"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="inventory_quantity_non_negative"),
        CheckConstraint(
            "source IN ('manual', 'system', 'shopify')", name="inventory_source"
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )