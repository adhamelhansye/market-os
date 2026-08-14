"""Structured business profile. One per business.

Fields are mostly human-readable business context; some (target_market,
brand_positioning, brand_voice) are structured inputs for future AI features.
Deliberately flat and small — no arbitrary JSON blobs.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

MONEY = Numeric(12, 2)


class BusinessProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "business_profiles"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    business_model: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_market: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand_positioning: Mapped[str | None] = mapped_column(Text, nullable=True)
    average_order_value: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    primary_customer_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    brand_voice: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )