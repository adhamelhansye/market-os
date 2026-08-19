"""Deterministic funnel strategy records (Phase 7C)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class FunnelStrategy(Base):
    """Immutable deterministic funnel snapshot built from strategy inputs."""

    __tablename__ = "funnel_strategies"
    __table_args__ = (
        Index("ix_funnel_strategies_business_created", "business_id", "created_at"),
        Index("ix_funnel_strategies_business_version", "business_id", "version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False)
    funnel_version: Mapped[str] = mapped_column(String(40), nullable=False)
    variant: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    positioning_candidate_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    offer_candidate_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    strategy_decision_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    messaging_strategy_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    health: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FunnelStage(Base):
    __tablename__ = "funnel_stages"
    __table_args__ = (
        Index("ix_funnel_stages_strategy", "funnel_strategy_id"),
        Index("ix_funnel_stages_business_stage", "business_id", "stage"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    funnel_strategy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("funnel_strategies.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)
    objective: Mapped[str] = mapped_column(String(200), nullable=False)
    audience_state: Mapped[str] = mapped_column(String(40), nullable=False)
    customer_problem: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_desire: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_direction: Mapped[str] = mapped_column(Text, nullable=False)
    offer_direction: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_direction: Mapped[str] = mapped_column(Text, nullable=False)
    cta_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    entry_condition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    exit_condition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    risks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    provenance: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FunnelStageChannel(Base):
    __tablename__ = "funnel_stage_channels"
    __table_args__ = (
        Index("ix_funnel_stage_channels_stage", "funnel_stage_id"),
        Index("ix_funnel_stage_channels_business_channel", "business_id", "channel"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    funnel_stage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("funnel_stages.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    priority: Mapped[int] = mapped_column(nullable=False)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    integration_connection_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FunnelStageKpi(Base):
    __tablename__ = "funnel_stage_kpis"
    __table_args__ = (
        Index("ix_funnel_stage_kpis_stage", "funnel_stage_id"),
        Index("ix_funnel_stage_kpis_business_kpi", "business_id", "kpi_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    funnel_stage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("funnel_stages.id", ondelete="CASCADE"), nullable=False
    )
    kpi_code: Mapped[str] = mapped_column(String(50), nullable=False)
    kpi_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    metric_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    value_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    threshold_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FunnelGap(Base):
    __tablename__ = "funnel_gaps"
    __table_args__ = (
        Index("ix_funnel_gaps_strategy", "funnel_strategy_id"),
        Index("ix_funnel_gaps_business_severity", "business_id", "severity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    funnel_strategy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("funnel_strategies.id", ondelete="CASCADE"), nullable=False
    )
    gap_type: Mapped[str] = mapped_column(String(30), nullable=False)
    stage_from: Mapped[str | None] = mapped_column(String(20), nullable=True)
    stage_to: Mapped[str | None] = mapped_column(String(20), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    recommended_direction: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = [
    "FunnelStrategy",
    "FunnelStage",
    "FunnelStageChannel",
    "FunnelStageKpi",
    "FunnelGap",
]
