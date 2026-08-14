"""Bundles: a priced group of products. The economics engine can compute the
underlying product cost of a bundle from its items."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

MONEY = Numeric(12, 2)


class Bundle(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bundles"
    __table_args__ = (
        CheckConstraint("price >= 0", name="bundle_price_non_negative"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list["BundleItem"]] = relationship(
        back_populates="bundle", cascade="all, delete-orphan", lazy="selectin"
    )


class BundleItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "bundle_items"
    __table_args__ = (
        UniqueConstraint("bundle_id", "product_id", name="bundle_item_product"),
        CheckConstraint("quantity > 0", name="bundle_item_quantity_positive"),
    )

    bundle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bundles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    bundle: Mapped[Bundle] = relationship(back_populates="items")