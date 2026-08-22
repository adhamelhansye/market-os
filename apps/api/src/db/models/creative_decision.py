"""Creative decision plan persistence (Phase 8F).

Two tables with sharply different mutability:

- creative_decision_plans
  Immutable, fingerprint-keyed decision-plan snapshots assembled
  deterministically from the latest Phase 8E optimization snapshot.

- creative_decision_item_reviews
  The repository's ONLY mutable human-review state. A review records
  that a human reviewed an opportunity — nothing else. It never
  executes, modifies or triggers anything.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class CreativeDecisionPlan(Base):
    """Immutable decision plan assembled from Phase 8E opportunities."""

    __tablename__ = "creative_decision_plans"
    __table_args__ = (
        Index(
            "uq_creative_decision_plans_fingerprint",
            "business_id",
            "fingerprint",
            unique=True,
        ),
        Index(
            "ix_creative_decision_plans_business_created",
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
    rules_version: Mapped[str] = mapped_column(String(40), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    source_optimization_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CreativeDecisionItemReview(Base):
    """Mutable human review state for one opportunity.

    States are deliberately non-executional:
    proposed / acknowledged / dismissed / deferred.
    Acknowledging means "a human reviewed this item" — nothing more.
    """

    __tablename__ = "creative_decision_item_reviews"
    __table_args__ = (
        CheckConstraint(
            "review_state IN ('proposed','acknowledged','dismissed','deferred')",
            name="ck_decision_review_state_allowed",
        ),
        # Latest review wins per opportunity within a business.
        Index(
            "uq_creative_decision_item_reviews_opportunity",
            "business_id",
            "opportunity_id",
            unique=True,
        ),
        Index(
            "ix_creative_decision_item_reviews_business_updated",
            "business_id",
            "updated_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    opportunity_id: Mapped[str] = mapped_column(String(200), nullable=False)
    source_plan_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    review_state: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


__all__ = [
    "CreativeDecisionPlan",
    "CreativeDecisionItemReview",
]
