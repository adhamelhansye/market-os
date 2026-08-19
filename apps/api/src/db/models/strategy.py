"""Deterministic positioning and offer strategy records (Phase 7A)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class StrategySnapshot(Base):
    __tablename__ = "strategy_snapshots"
    __table_args__ = (
        Index("ix_strategy_snapshots_business_created", "business_id", "created_at"),
        Index("ix_strategy_snapshots_business_kind", "business_id", "strategy_kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    strategy_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    research_intelligence_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    input_snapshot_refs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    coverage_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    missing_research_areas: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PositioningStrategy(Base):
    __tablename__ = "positioning_strategies"
    __table_args__ = (
        Index("ix_positioning_strategies_business_version", "business_id", "version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    selected_candidate_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PositioningCandidate(Base):
    __tablename__ = "positioning_candidates"
    __table_args__ = (
        Index("ix_positioning_candidates_business_created", "business_id", "created_at"),
        Index("ix_positioning_candidates_strategy", "positioning_strategy_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    positioning_strategy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("positioning_strategies.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    candidate_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_customer: Mapped[str | None] = mapped_column(Text, nullable=True)
    problem: Mapped[str | None] = mapped_column(Text, nullable=True)
    solution: Mapped[str | None] = mapped_column(Text, nullable=True)
    differentiator: Mapped[str | None] = mapped_column(Text, nullable=True)
    promise: Mapped[str | None] = mapped_column(Text, nullable=True)
    supporting_benefits: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    proof_points: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    objections_addressed: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    positioning_statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    classification: Mapped[str] = mapped_column(String(20), nullable=False, default="hypothesis")
    strength: Mapped[str] = mapped_column(String(20), nullable=False, default="insufficient")
    score: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    assumptions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    risks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    provenance: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OfferStrategy(Base):
    __tablename__ = "offer_strategies"
    __table_args__ = (Index("ix_offer_strategies_business_version", "business_id", "version"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    selected_candidate_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OfferCandidate(Base):
    __tablename__ = "offer_candidates"
    __table_args__ = (
        Index("ix_offer_candidates_business_created", "business_id", "created_at"),
        Index("ix_offer_candidates_strategy", "offer_strategy_id"),
        Index("ix_offer_candidates_product", "product_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    offer_strategy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("offer_strategies.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    bundle_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("bundles.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    components: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    economics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    classification: Mapped[str] = mapped_column(String(20), nullable=False, default="hypothesis")
    strength: Mapped[str] = mapped_column(String(20), nullable=False, default="insufficient")
    score: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    assumptions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    risks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    provenance: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class StrategyDecision(Base):
    """Reproducible, tenant-scoped evaluation of one strategy candidate."""

    __tablename__ = "strategy_decisions"
    __table_args__ = (
        Index("ix_strategy_decisions_business_created", "business_id", "created_at"),
        Index("ix_strategy_decisions_candidate", "candidate_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    candidate_type: Mapped[str] = mapped_column(String(20), nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    decision_rules_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    evaluation: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    provenance: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MessagingStrategy(Base):
    """Immutable deterministic messaging snapshot built from strategy inputs."""

    __tablename__ = "messaging_strategies"
    __table_args__ = (
        Index("ix_messaging_strategies_business_created", "business_id", "created_at"),
        Index("ix_messaging_strategies_business_version", "business_id", "version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False)
    messaging_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    positioning_candidate_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    offer_candidate_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    strategy_decision_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    core_message: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    quality: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MessageComponent(Base):
    __tablename__ = "message_components"
    __table_args__ = (
        Index("ix_message_components_strategy", "messaging_strategy_id"),
        Index("ix_message_components_business_type", "business_id", "component_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    messaging_strategy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messaging_strategies.id", ondelete="CASCADE"), nullable=False
    )
    component_type: Mapped[str] = mapped_column(String(30), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    classification: Mapped[str] = mapped_column(String(40), nullable=False)
    strength: Mapped[str] = mapped_column(String(20), nullable=False)
    claim_status: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="available")
    funnel_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    provenance: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MessageAngle(Base):
    __tablename__ = "message_angles"
    __table_args__ = (
        Index("ix_message_angles_strategy", "messaging_strategy_id"),
        Index("ix_message_angles_business_type", "business_id", "angle_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    messaging_strategy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messaging_strategies.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    angle_type: Mapped[str] = mapped_column(String(30), nullable=False)
    core_message: Mapped[str] = mapped_column(Text, nullable=False)
    hook_direction: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_points: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    cta_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    funnel_stage: Mapped[str] = mapped_column(String(20), nullable=False)
    strength: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = [
    "OfferCandidate",
    "OfferStrategy",
    "PositioningCandidate",
    "PositioningStrategy",
    "StrategyDecision",
    "StrategySnapshot",
    "MessagingStrategy",
    "MessageComponent",
    "MessageAngle",
]
