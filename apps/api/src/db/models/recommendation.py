"""SQLAlchemy ORM for deterministic decisions (Phase 4B).

A decision is the persisted output of the deterministic decision engine,
computed from canonical metrics, diagnostics, forecasts, unit economics and
business goals — never from an LLM, never by simulation and never by an
autonomous action. Every row carries the structured evidence, the metric and
forecast snapshots at decision time, the rules version and the range it
covers, so any historical decision is fully auditable.

Decisions are review recommendations only. This table never triggers
provider mutations, budget changes or campaign edits.

Idempotency: the `fingerprint` is a deterministic SHA-256 of
(organization_id, business_id, entity_type, entity_id, range_start,
range_end, rules_version). The unique constraint on `fingerprint` makes
regenerating the same decision collapse to the same row.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        UniqueConstraint("fingerprint", name="uq_recommendation_fingerprint"),
        CheckConstraint(
            "range_end >= range_start", name="ck_recommendation_range_valid"
        ),
        Index(
            "ix_recommendations_business_entity",
            "business_id",
            "entity_type",
            "entity_id",
        ),
        Index("ix_recommendations_business_decision", "business_id", "decision"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=True
    )
    entity_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    evidence_strength: Mapped[str] = mapped_column(String(20), nullable=False)
    primary_reason: Mapped[str] = mapped_column(String(120), nullable=False)
    diagnostics: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    review_suggestions: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    metrics_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    forecast_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    range_start: Mapped[date] = mapped_column(Date, nullable=False)
    range_end: Mapped[date] = mapped_column(Date, nullable=False)
    rules_version: Mapped[str] = mapped_column(String(20), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


__all__ = ["Recommendation"]