"""Creative performance intelligence records (Phase 8C).

Two tables only — everything else in the performance layer is computed
deterministically on request from the canonical metrics layer:

- creative_performance_links
  Explicit, user-authored attribution between internal creative entities
  (concepts / test variants) and provider advertising objects (ads /
  provider creatives). The engine never infers these relationships and
  never distributes business-level revenue across creatives.

- creative_performance_snapshots
  Immutable audit snapshots of a computed performance report, stamped
  with the deterministic rules version. Snapshots are reproducible: the
  same business/scope/range/rules always produce the same fingerprint.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class CreativePerformanceLink(Base):
    """Explicit attribution link authored by a user — never inferred.

    Internal side: exactly one of ``creative_concept_id`` /
    ``creative_test_variant_id``. Provider side: exactly one of
    ``ad_id`` / ``provider_creative_id``. Strategy context (funnel,
    messaging, positioning, offer) is derived transitively through the
    concept's own references; test context through the variant's test.
    """

    __tablename__ = "creative_performance_links"
    __table_args__ = (
        CheckConstraint(
            "(creative_concept_id IS NOT NULL)::int"
            " + (creative_test_variant_id IS NOT NULL)::int"
            " = 1",
            name="ck_links_exactly_one_internal_target",
        ),
        CheckConstraint(
            "(ad_id IS NOT NULL)::int + (provider_creative_id IS NOT NULL)::int = 1",
            name="ck_links_exactly_one_provider_target",
        ),
        # No duplicate identical mappings regardless of status.
        Index(
            "uq_creative_performance_links_mapping",
            "business_id",
            text("COALESCE(creative_concept_id::text, '')"),
            text("COALESCE(creative_test_variant_id::text, '')"),
            text("COALESCE(ad_id::text, '')"),
            text("COALESCE(provider_creative_id::text, '')"),
            unique=True,
        ),
        Index("ix_creative_performance_links_business_created", "business_id", "created_at"),
        Index("ix_creative_performance_links_concept", "creative_concept_id"),
        Index("ix_creative_performance_links_variant", "creative_test_variant_id"),
        Index("ix_creative_performance_links_ad", "ad_id"),
        Index("ix_creative_performance_links_provider_creative", "provider_creative_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    creative_concept_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("creative_concepts.id", ondelete="CASCADE"), nullable=True
    )
    creative_test_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("creative_test_variants.id", ondelete="CASCADE"), nullable=True
    )
    ad_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ads.id", ondelete="CASCADE"), nullable=True
    )
    provider_creative_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("creatives.id", ondelete="CASCADE"), nullable=True
    )
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CreativePerformanceSnapshot(Base):
    """Immutable snapshot of a computed creative performance report."""

    __tablename__ = "creative_performance_snapshots"
    __table_args__ = (
        Index(
            "uq_creative_performance_snapshots_fingerprint",
            "business_id",
            "fingerprint",
            unique=True,
        ),
        Index(
            "ix_creative_performance_snapshots_business_created",
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
    entity_scope: Mapped[str] = mapped_column(String(20), nullable=False, default="all")
    rules_version: Mapped[str] = mapped_column(String(40), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = [
    "CreativePerformanceLink",
    "CreativePerformanceSnapshot",
]
