"""Product cost period. Costs are immutable history records: changing a cost
creates a new period instead of mutating the old one.

All money and percentages are NUMERIC/Decimal — never float.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base, UUIDPrimaryKeyMixin

MONEY = Numeric(12, 2)
PERCENT = Numeric(8, 4)


class ProductCost(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "product_costs"
    __table_args__ = (
        CheckConstraint("cogs >= 0", name="cogs_non_negative"),
        CheckConstraint("packaging_cost >= 0", name="packaging_non_negative"),
        CheckConstraint("payment_fee_fixed >= 0", name="payment_fee_fixed_non_negative"),
        CheckConstraint(
            "payment_fee_percent >= 0 AND payment_fee_percent <= 100",
            name="payment_fee_percent_range",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="cost_period",
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cogs: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    packaging_cost: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0")
    )
    payment_fee_fixed: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0")
    )
    payment_fee_percent: Mapped[Decimal] = mapped_column(
        PERCENT, nullable=False, default=Decimal("0")
    )
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    effective_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )