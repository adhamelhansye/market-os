"""Shipping rules. Distinguishes the business's actual shipping cost from
the shipping price charged to the customer — critical for profitability.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

MONEY = Numeric(12, 2)


class ShippingRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "shipping_rules"
    __table_args__ = (
        CheckConstraint("cost >= 0", name="shipping_cost_non_negative"),
        CheckConstraint("customer_price >= 0", name="shipping_customer_price_non_negative"),
        CheckConstraint(
            "free_shipping_threshold IS NULL OR free_shipping_threshold >= 0",
            name="shipping_free_threshold_non_negative",
        ),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    method: Mapped[str] = mapped_column(String(50), nullable=False)
    cost: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    customer_price: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0")
    )
    free_shipping_threshold: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )