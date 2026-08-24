"""Creative action preparation persistence (Phase 8G).

One linkage table connecting acknowledged Phase 8F opportunities to the
8B CreativeTest drafts they produced.

- The draft itself lives in the existing 8B ``creative_tests`` table and
  its ``status`` can never leave ``draft`` through this layer.
- This table is the idempotency mechanism: UNIQUE (business_id,
  source_opportunity_id) means one acknowledged opportunity yields at
  most one draft, forever.
- Second-stage human review reuses the same four non-executional states.
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


class CreativeActionDraft(Base):
    """Linkage between an acknowledged 8F opportunity and its 8B test draft."""

    __tablename__ = "creative_action_drafts"
    # Server-side defaults/onupdate are fetched within the flush so
    # post-commit attribute access never triggers implicit IO.
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(
            "draft_kind IN ('expansion','coverage_gap','fatigue')",
            name="ck_action_draft_kind_allowed",
        ),
        CheckConstraint(
            "review_state IN ('proposed','acknowledged','dismissed','deferred')",
            name="ck_action_draft_review_state_allowed",
        ),
        Index(
            "uq_creative_action_drafts_opportunity",
            "business_id",
            "source_opportunity_id",
            unique=True,
        ),
        Index(
            "ix_creative_action_drafts_business_created",
            "business_id",
            "created_at",
        ),
        Index(
            "ix_creative_action_drafts_test_id",
            "draft_test_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    source_opportunity_id: Mapped[str] = mapped_column(String(200), nullable=False)
    source_plan_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    draft_test_id: Mapped[str] = mapped_column(
        String(80), nullable=False
    )
    draft_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    review_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="proposed"
    )
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


__all__ = ["CreativeActionDraft"]


class CreativeTestActivation(Base):
    """Immutable lifecycle event for a Phase 8G creative test draft.

    One row per state transition. Activation requires the strict gate
    (review acknowledged + previous status draft) and records the human
    actor. Rows are never updated or deleted.
    """

    __tablename__ = "creative_test_activations"
    __table_args__ = (
        CheckConstraint(
            "previous_status IN ('draft','active','completed','cancelled')",
            name="ck_activation_previous_status_allowed",
        ),
        CheckConstraint(
            "new_status IN ('draft','active','completed','cancelled')",
            name="ck_activation_new_status_allowed",
        ),
        Index(
            "ix_creative_test_activations_test_created",
            "creative_test_id",
            "created_at",
        ),
        Index(
            "ix_creative_test_activations_business_created",
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
    creative_test_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    creative_test_external_ref: Mapped[str] = mapped_column(String(80), nullable=False)
    source_action_draft_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    source_opportunity_id: Mapped[str] = mapped_column(String(200), nullable=False)
    source_plan_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_status: Mapped[str] = mapped_column(String(20), nullable=False)
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    activated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = [
    "CreativeActionDraft",
    "CreativeTestActivation",
]
