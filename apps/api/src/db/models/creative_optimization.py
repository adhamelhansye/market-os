"""Creative optimization persistence (Phase 8E).

One immutable, fingerprint-keyed snapshot table holding the full
deterministic optimization plan, following the Phase 8D convention.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class CreativeOptimizationSnapshot(Base):
    """Immutable optimization plan computed from 8C/8D artifacts."""

    __tablename__ = "creative_optimization_snapshots"
    __table_args__ = (
        Index(
            "uq_creative_optimization_snapshots_fingerprint",
            "business_id",
            "fingerprint",
            unique=True,
        ),
        Index(
            "ix_creative_optimization_snapshots_business_created",
            "business_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    range_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    start_date: Mapped[date] = mapped_column(Date(), nullable=False)
    end_date: Mapped[date] = mapped_column(Date(), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rules_version: Mapped[str] = mapped_column(String(40), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = ["CreativeOptimizationSnapshot"]
