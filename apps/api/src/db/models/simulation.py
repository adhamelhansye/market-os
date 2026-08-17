"""SQLAlchemy ORM for deterministic simulations (Phase 5A).

A simulation is the persisted output of the deterministic simulator:
a budget with a set of funnel assumptions, three scenario levels
(downside / expected / upside) derived from the historical daily
distribution, break-even hints from the economics profile, profitability
status and sensitivity tables. Snapshots (input / assumptions / results)
are JSONB with money stored as Decimal strings — never float.

Simulations are read-only analysis: nothing in this module or the
simulator service ever executes provider mutations, budget changes or
campaign edits.

Idempotency: `assumptions_hash` is a deterministic SHA-256 of the
resolved assumptions and reference window. The unique constraint
(organization_id, business_id, entity_type, entity_id,
assumptions_hash, model_version) makes replaying identical inputs
collapse to the same row (the service upserts on conflict).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base

_MONEY = Numeric(14, 2)
_RATE = Numeric(14, 6)


class Simulation(Base):
    __tablename__ = "simulations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "business_id",
            "entity_type",
            "entity_id",
            "assumptions_hash",
            "model_version",
            name="uq_simulation_identity",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint("duration_days > 0", name="ck_simulation_duration_positive"),
        CheckConstraint(
            "historical_window_days > 0",
            name="ck_simulation_window_days_positive",
        ),
        CheckConstraint(
            "reference_end >= reference_start",
            name="ck_simulation_reference_window_valid",
        ),
        Index(
            "ix_simulations_business_entity",
            "business_id",
            "entity_type",
            "entity_id",
        ),
        Index(
            "ix_simulations_business_created",
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
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=True
    )
    model_version: Mapped[str] = mapped_column(String(20), nullable=False)
    assumptions_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    model_used: Mapped[str] = mapped_column(String(40), nullable=False)
    calculation_path: Mapped[str] = mapped_column(String(255), nullable=False)
    data_quality: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence_strength: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    budget: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    historical_window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    reference_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    assumptions_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    results_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SimulationAssumption(Base):
    __tablename__ = "simulation_assumptions"
    __table_args__ = (
        UniqueConstraint("simulation_id", "name", name="uq_simulation_assumption_name"),
        Index("ix_simulation_assumptions_simulation", "simulation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    simulation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("simulations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    source_entity: Mapped[str | None] = mapped_column(String(40), nullable=True)
    historical_value: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    unavailable_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)


class SimulationResult(Base):
    __tablename__ = "simulation_results"
    __table_args__ = (
        UniqueConstraint("simulation_id", "scenario", name="uq_simulation_result_scenario"),
        Index("ix_simulation_results_simulation", "simulation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    simulation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("simulations.id", ondelete="CASCADE"), nullable=False
    )
    scenario: Mapped[str] = mapped_column(String(20), nullable=False)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)


__all__ = ["Simulation", "SimulationAssumption", "SimulationResult"]
