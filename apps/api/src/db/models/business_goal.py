"""Business goals: target revenue/profit and ad constraints for a period.

A business may have multiple historical goals. Periods are half-open
[period_start, period_end) and must not overlap (enforced in the service
layer). All money is NUMERIC/Decimal — never float.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

MONEY = Numeric(14, 2)


class BusinessGoal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "business_goals"
    __table_args__ = (
        CheckConstraint("period_end > period_start", name="goal_period"),
        CheckConstraint(
            "target_revenue IS NULL OR target_revenue >= 0", name="goal_revenue_non_negative"
        ),
        CheckConstraint(
            "target_profit IS NULL OR target_profit >= 0", name="goal_profit_non_negative"
        ),
        CheckConstraint(
            "ad_budget IS NULL OR ad_budget > 0", name="goal_ad_budget_positive"
        ),
        CheckConstraint(
            "maximum_cpa IS NULL OR maximum_cpa > 0", name="goal_max_cpa_positive"
        ),
        CheckConstraint(
            "target_roas IS NULL OR target_roas > 0", name="goal_roas_positive"
        ),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    target_revenue: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    target_profit: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    ad_budget: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    maximum_cpa: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    target_roas: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )