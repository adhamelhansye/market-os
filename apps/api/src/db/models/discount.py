"""Discounts. Phase 1 supports percentage and fixed-amount discounts only —
no coupon-code management yet. The purpose is economics, not a promotions
engine.
"""

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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

MONEY = Numeric(12, 2)

DISCOUNT_TYPES = ("percentage", "fixed_amount")


class Discount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "discounts"
    __table_args__ = (
        CheckConstraint(
            "type IN ('percentage', 'fixed_amount')", name="discount_type"
        ),
        CheckConstraint("value > 0", name="discount_value_positive"),
        # A percentage discount cannot exceed 100%.
        CheckConstraint(
            "type <> 'percentage' OR value <= 100", name="discount_percentage_max"
        ),
        CheckConstraint(
            "minimum_order_value IS NULL OR minimum_order_value >= 0",
            name="discount_minimum_order_value_non_negative",
        ),
        CheckConstraint(
            "maximum_discount IS NULL OR maximum_discount > 0",
            name="discount_maximum_discount_positive",
        ),
        CheckConstraint("ends_at > starts_at", name="discount_period"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    minimum_order_value: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    maximum_discount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )