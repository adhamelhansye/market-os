"""Deterministic creative intelligence foundation records (Phase 8A)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class CreativeConcept(Base):
    """Deterministic creative concept anchored in Phase 7 research/strategy data.

    Every concept references existing Phase 7 data via foreign keys. No LLM, no
    asset generation, no performance learning. Creative defines what and why, not
    the final image/video.
    """

    __tablename__ = "creative_concepts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    strategy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    positioning_reference: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("positioning_strategies.id", ondelete="RESTRICT"), nullable=True
    )
    offer_reference: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("offer_candidates.id", ondelete="RESTRICT"), nullable=True
    )
    messaging_reference: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messaging_strategies.id", ondelete="RESTRICT"), nullable=True
    )
    funnel_reference: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("funnel_strategies.id", ondelete="RESTRICT"), nullable=True
    )
    funnel_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    angle: Mapped[str | None] = mapped_column(String(50), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    hook_direction: Mapped[str | None] = mapped_column(String(100), nullable=True)
    creative_format: Mapped[str] = mapped_column(String(50), nullable=False)
    creative_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    offer_direction: Mapped[str | None] = mapped_column(Text, nullable=True)
    cta: Mapped[str | None] = mapped_column(String(50), nullable=True)
    visual_direction: Mapped[str | None] = mapped_column(Text, nullable=True)
    copy_direction: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_emotion: Mapped[str | None] = mapped_column(String(30), nullable=True)
    secondary_emotion: Mapped[str | None] = mapped_column(String(30), nullable=True)
    objection: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reason_to_believe: Mapped[str | None] = mapped_column(Text, nullable=True)
    testing_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    success_metric: Mapped[str | None] = mapped_column(String(50), nullable=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    risks: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="draft"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Indexes created separately via migration to avoid class-definition-time
    # column validation issues. Will be added in v0017 migration.


class CreativeBrief(Base):
    """Deterministic creative brief generated from Phase 7 data.

    Consumes positioning/offer/strategy/funnel data to produce a structured
    brief. All fields reference existing Phase 7 data; never fabricated.
    """

    __tablename__ = "creative_briefs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    objective: Mapped[str] = mapped_column(String(50), nullable=False)
    target_audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    funnel_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    customer_problem: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_desire: Mapped[str | None] = mapped_column(Text, nullable=True)
    core_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    angle: Mapped[str | None] = mapped_column(String(50), nullable=True)
    hook_direction: Mapped[str | None] = mapped_column(String(100), nullable=True)
    offer: Mapped[str | None] = mapped_column(Text, nullable=True)
    proof: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    objection: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cta: Mapped[str | None] = mapped_column(String(50), nullable=True)
    creative_format: Mapped[str | None] = mapped_column(String(50), nullable=True)
    visual_direction: Mapped[str | None] = mapped_column(Text, nullable=True)
    copy_direction: Mapped[str | None] = mapped_column(Text, nullable=True)
    emotional_direction: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason_to_believe: Mapped[str | None] = mapped_column(Text, nullable=True)
    testing_hypothesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    success_metric: Mapped[str | None] = mapped_column(String(50), nullable=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="draft"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CreativeMatrixEntry(Base):
    """Angle × Funnel Stage × Format matrix entry for concept coverage."""

    __tablename__ = "creative_matrix_entries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    angle: Mapped[str | None] = mapped_column(String(50), nullable=True)
    funnel_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    creative_format: Mapped[str | None] = mapped_column(String(50), nullable=True)
    creative_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    offer: Mapped[str | None] = mapped_column(Text, nullable=True)
    proof: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    objective: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="draft"
    )
    evidence_strength: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CreativeRisk(Base):
    """Named deterministic risk rules for creative concepts."""

    __tablename__ = "creative_risks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    risk_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(30), nullable=False)
    related_concept_id: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True
    )
    resolved: Mapped[bool] = mapped_column(
        nullable=False, server_default=sa.false()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CreativeEvidence(Base):
    """Traceable evidence references for creative claims.

    Every important claim in a creative concept must have a provenance chain:
    Creative Concept → Creative Brief → Angle/Message → Funnel Stage →
    Positioning/Offer → Research Evidence → Source/Snapshot.
    """

    __tablename__ = "creative_evidence"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    evidence_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True
    )
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    citation: Mapped[str | None] = mapped_column(Text, nullable=True)
    captures: Mapped[str | None] = mapped_column(Text, nullable=True)
    captures_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="available"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CreativeSnapshot(Base):
    """Immutable snapshot of creative concept at generation time."""

    __tablename__ = "creative_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    creative_type: Mapped[str] = mapped_column(String(50), nullable=False)
    creative_format: Mapped[str] = mapped_column(String(50), nullable=False)
    angle: Mapped[str | None] = mapped_column(String(50), nullable=True)
    funnel_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    objective: Mapped[str | None] = mapped_column(String(50), nullable=True)
    positioning_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    offer_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    strategy_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True
    )
    messaging_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    funnel_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    research_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    creative_rules_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    output_summary: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CreativeProvenance(Base):
    """Provenance chain tracking for creative concepts.

    Creative → Brief → Angle/Message → Funnel Stage → Positioning/Offer →
    Research Evidence → Source/Snapshot. For every important claim.

    Uses explicitly typed foreign keys instead of a polymorphic reference_id/reference_type
    pair. Exactly one of positioning_id, offer_id, messaging_id, funnel_id must be NOT NULL.
    """

    __tablename__ = "creative_provenance"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    step: Mapped[str] = mapped_column(String(50), nullable=False)
    positioning_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("positioning_strategies.id", ondelete="RESTRICT"), nullable=True
    )
    offer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("offer_candidates.id", ondelete="RESTRICT"), nullable=True
    )
    messaging_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messaging_strategies.id", ondelete="RESTRICT"), nullable=True
    )
    funnel_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("funnel_strategies.id", ondelete="RESTRICT"), nullable=True
    )
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # CHECK constraint: exactly one of positioning_id, offer_id, messaging_id, funnel_id must be NOT NULL
        sa.CheckConstraint(
            "(positioning_id IS NOT NULL)::int"
            "+ (offer_id IS NOT NULL)::int"
            "+ (messaging_id IS NOT NULL)::int"
            "+ (funnel_id IS NOT NULL)::int"
            " = 1",
            name="ck_creative_provenance_exactly_one_reference",
        ),
    )



# ---------------------------------------------------------------------------
# Phase 8B: Creative Strategy & Testing Matrix ORM models
# ---------------------------------------------------------------------------

class CreativeStrategy(Base):
    """Versioned deterministic creative strategy container."""
    __tablename__ = "creative_strategies"
    __table_args__ = (Index("ix_creative_strategies_business_created", "business_id", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    version: Mapped[str] = mapped_column(String(30), nullable=False, default="v1")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    positioning_reference: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("positioning_strategies.id", ondelete="RESTRICT"), nullable=True)
    offer_reference: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("offer_candidates.id", ondelete="RESTRICT"), nullable=True)
    messaging_reference: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messaging_strategies.id", ondelete="RESTRICT"), nullable=True)
    funnel_reference: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("funnel_strategies.id", ondelete="RESTRICT"), nullable=True)
    research_reference: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_projects.id", ondelete="RESTRICT"), nullable=True)
    strategy_decision_reference: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("strategy_decisions.id", ondelete="RESTRICT"), nullable=True)
    creative_intelligence_reference: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("creative_concepts.id", ondelete="RESTRICT"), nullable=True)
    audience_coverage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    funnel_coverage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    rules_version: Mapped[str] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CreativeTest(Base):
    """Deterministic creative test design isolating one primary variable."""
    __tablename__ = "creative_tests"
    __table_args__ = (Index("ix_creative_tests_business_created", "business_id", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    test_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    objective: Mapped[str] = mapped_column(String(50), nullable=False)
    test_variable: Mapped[str] = mapped_column(String(50), nullable=False)
    control_variables: Mapped[str | None] = mapped_column(JSONB, nullable=False, default=dict)
    variants: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    based_on: Mapped[str | None] = mapped_column(Text, nullable=True)
    success_metric: Mapped[str] = mapped_column(String(50), nullable=True)
    minimum_data_requirement: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CreativeTestVariant(Base):
    """A variant within a CreativeTest."""
    __tablename__ = "creative_test_variants"
    __table_args__ = (Index("ix_creative_test_variants_test_id", "test_id"), Index("ix_creative_test_variants_business_created", "business_id", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    test_id: Mapped[str] = mapped_column(String(80), nullable=False)
    variant_id: Mapped[str] = mapped_column(String(80), nullable=False)
    test_variable_value: Mapped[str] = mapped_column(Text, nullable=False)
    control_state_frozen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CreativePortfolio(Base):
    """Portfolio categories for creative diversification."""
    __tablename__ = "creative_portfolios"
    __table_args__ = (Index("ix_creative_portfolios_business_created", "business_id", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    portfolio_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)  # core / exploration / proof / objection / offer / format / angle
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CreativeCoverage(Base):
    """Strategic coverage measurement."""
    __tablename__ = "creative_coverage"
    __table_args__ = (Index("ix_creative_coverage_business_created", "business_id", "created_at"), Index("ix_creative_coverage_business_type", "business_id", "coverage_type"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    coverage_type: Mapped[str] = mapped_column(String(50), nullable=False)
    dimension: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[str] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="available")
    evidence_ref: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("creative_evidence.id", ondelete="RESTRICT"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CreativeDiversity(Base):
    """Deterministic diversity detection."""
    __tablename__ = "creative_diversity"
    __table_args__ = (Index("ix_creative_diversity_business_created", "business_id", "created_at"), Index("ix_creative_diversity_business_type", "business_id", "risk_type"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    risk_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(30), nullable=False)
    related_concept_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    resolved: Mapped[bool] = mapped_column(nullable=False, server_default=sa.false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CreativeConceptPortfolio(Base):
    """Links creative concepts to portfolio categories."""
    __tablename__ = "creative_concept_portfolios"
    __table_args__ = (Index("ix_creative_concept_portfolios_concept_id", "creative_concept_id"), Index("ix_creative_concept_portfolios_business_created", "business_id", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    creative_concept_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("creative_concepts.id", ondelete="CASCADE"), nullable=False)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("creative_portfolios.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=True)  # core / exploration
    evidence_ref: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("creative_evidence.id", ondelete="RESTRICT"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CreativeStrategySnapshot(Base):
    """Immutable snapshot of creative strategy at generation time."""
    __tablename__ = "creative_strategy_snapshots"
    __table_args__ = (Index("ix_creative_strategy_snapshots_business_created", "business_id", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(80), nullable=False)
    creative_intelligence_version: Mapped[str] = mapped_column(String(40), nullable=True)
    positioning_version: Mapped[str] = mapped_column(String(40), nullable=True)
    offer_version: Mapped[str] = mapped_column(String(40), nullable=True)
    strategy_decision_version: Mapped[str] = mapped_column(String(40), nullable=True)
    messaging_version: Mapped[str] = mapped_column(String(40), nullable=True)
    funnel_version: Mapped[str] = mapped_column(String(40), nullable=True)
    research_version: Mapped[str] = mapped_column(String(40), nullable=True)
    creative_strategy_version: Mapped[str] = mapped_column(String(40), nullable=True)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    output_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

__all__ = [
    "CreativeConcept",
    "CreativeBrief",
    "CreativeMatrixEntry",
    "CreativeRisk",
    "CreativeEvidence",
    "CreativeSnapshot",
    "CreativeProvenance",
    "CreativeStrategy",
    "CreativeTest",
    "CreativeTestVariant",
    "CreativePortfolio",
    "CreativeCoverage",
    "CreativeDiversity",
    "CreativeConceptPortfolio",
    "CreativeStrategySnapshot",
]