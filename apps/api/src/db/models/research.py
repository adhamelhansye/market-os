"""SQLAlchemy ORM for the research intelligence foundation (Phase 6A).

The research layer is a deterministic evidence store, independent from
metrics, forecasting, diagnostics, recommendations and the simulator.
It persists the Source → Snapshot → Evidence → Finding chain:

- `research_projects` — an investigation the user runs (market / customer
  / competitor / mixed) with a lifecycle status.
- `research_sources` — the origin of information (website, product page,
  review, ...); entirely optional `url`, an optional attribution to a
  competitor record, and a `content_hash` for deduplication when the
  content was captured.
- `research_source_snapshots` — reproducible captures; the unique
  constraint (source_id, content_hash) makes re-capturing identical
  content collapse to the same snapshot.
- `research_evidence` — a single structured claim with `statement`,
  `structured_value`, a deterministic `confidence` (observed / supported /
  inferred / hypothesis) and explicit `provenance`. Evidence references
  exactly one source.
- `research_competitors` — competitor records; a domain is NOT required.
- `research_findings` — normalized conclusions tied to a project, each
  classified observed / inferred / hypothesis and traceable back to one or
  more evidence rows through `research_finding_evidence`.

The layer performs no scraping, no external requests, no LLM calls and no
autonomous action: it only stores what clients submit. Money values inside
`structured_value` / `metadata` are stored as Decimal strings (never
float). Nothing in this module ever executes provider mutations.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class ResearchProject(Base):
    __tablename__ = "research_projects"
    __table_args__ = (Index("ix_research_projects_business_created", "business_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    scope: Mapped[str | None] = mapped_column(String(1000), nullable=True)
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


class ResearchCompetitor(Base):
    __tablename__ = "research_competitors"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "business_id",
            "name",
            name="uq_research_competitor_name",
        ),
        Index("ix_research_competitors_business", "business_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    market: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
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


class ResearchSource(Base):
    __tablename__ = "research_sources"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "business_id",
            "content_hash",
            name="uq_research_source_content_hash",
        ),
        Index("ix_research_sources_business_type", "business_id", "source_type"),
        Index("ix_research_sources_business_competitor", "business_id", "competitor_id"),
        Index("ix_research_sources_business_captured", "business_id", "captured_at"),
    )
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    original_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    normalized_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    competitor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_competitors.id", ondelete="CASCADE"), nullable=True
    )
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


class ResearchSourceSnapshot(Base):
    __tablename__ = "research_source_snapshots"
    __table_args__ = (
        UniqueConstraint("source_id", "content_hash", name="uq_research_snapshot_hash"),
        Index("ix_research_snapshots_source", "source_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_sources.id", ondelete="CASCADE"), nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class ResearchEvidence(Base):
    __tablename__ = "research_evidence"
    __table_args__ = (
        Index("ix_research_evidence_business_type", "business_id", "evidence_type"),
        Index("ix_research_evidence_business_captured", "business_id", "captured_at"),
        Index("ix_research_evidence_source", "source_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_sources.id", ondelete="CASCADE"), nullable=False
    )
    research_project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=True
    )
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_source_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    evidence_type: Mapped[str] = mapped_column(String(30), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    raw_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    provenance: Mapped[str] = mapped_column(String(30), nullable=False)
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

    @property
    def classification(self) -> str:
        return self.confidence

    @classification.setter
    def classification(self, value: str) -> None:
        self.confidence = value


class ResearchCollectionJob(Base):
    __tablename__ = "research_collection_jobs"
    __table_args__ = (
        Index("ix_research_collection_jobs_business_created", "business_id", "created_at"),
        Index("ix_research_collection_jobs_project_status", "research_project_id", "status"),
        Index("ix_research_collection_jobs_source_created", "source_id", "created_at"),
        UniqueConstraint(
            "organization_id",
            "business_id",
            "idempotency_key",
            name="uq_research_collection_idempotency",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    research_project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_sources.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    mode: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    max_pages: Mapped[int] = mapped_column(nullable=False, default=1)
    max_depth: Mapped[int] = mapped_column(nullable=False, default=0)
    same_domain: Mapped[bool] = mapped_column(nullable=False, default=True)
    refresh: Mapped[bool] = mapped_column(nullable=False, default=False)
    requested_urls: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    pages_collected: Mapped[int] = mapped_column(nullable=False, default=0)
    change_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ResearchCollectionPage(Base):
    __tablename__ = "research_collection_pages"
    __table_args__ = (
        UniqueConstraint(
            "collection_job_id", "normalized_url", name="uq_research_collection_page_url"
        ),
        Index("ix_research_collection_pages_job", "collection_job_id"),
        Index("ix_research_collection_pages_source", "source_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    collection_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_collection_jobs.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_sources.id", ondelete="CASCADE"), nullable=False
    )
    original_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    normalized_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    http_status: Mapped[int] = mapped_column(nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    response_size: Mapped[int] = mapped_column(nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(nullable=False, default=0)
    depth: Mapped[int] = mapped_column(nullable=False, default=0)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchIntelligenceSnapshot(Base):
    __tablename__ = "research_intelligence_snapshots"
    __table_args__ = (
        Index(
            "ix_research_intelligence_snapshots_business_generated",
            "business_id",
            "generated_at",
        ),
        Index(
            "ix_research_intelligence_snapshots_project_generated",
            "research_project_id",
            "generated_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    research_project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=True
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source_count: Mapped[int] = mapped_column(nullable=False, default=0)
    snapshot_count: Mapped[int] = mapped_column(nullable=False, default=0)
    evidence_count: Mapped[int] = mapped_column(nullable=False, default=0)
    finding_count: Mapped[int] = mapped_column(nullable=False, default=0)
    intelligence_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="research_intelligence_v1"
    )
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    freshness: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    coverage_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    missing_areas_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )


class ResearchIntelligenceItem(Base):
    __tablename__ = "research_intelligence_items"
    __table_args__ = (
        Index(
            "ix_research_intelligence_items_snapshot_type",
            "snapshot_id",
            "intelligence_type",
        ),
        Index(
            "ix_research_intelligence_items_business_category",
            "business_id",
            "category",
        ),
        Index("ix_research_intelligence_items_competitor", "competitor_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_intelligence_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    research_project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=True
    )
    competitor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_competitors.id", ondelete="CASCADE"), nullable=True
    )
    intelligence_type: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    classification: Mapped[str] = mapped_column(String(20), nullable=False)
    strength: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence_count: Mapped[int] = mapped_column(nullable=False, default=0)
    source_count: Mapped[int] = mapped_column(nullable=False, default=0)
    freshness: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


research_intelligence_item_findings = Table(
    "research_intelligence_item_findings",
    Base.metadata,
    Column(
        "item_id",
        ForeignKey("research_intelligence_items.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "finding_id",
        ForeignKey("research_findings.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Index("ix_research_intelligence_item_findings_finding", "finding_id"),
)


class ResearchFinding(Base):
    __tablename__ = "research_findings"
    __table_args__ = (
        Index("ix_research_findings_business_category", "business_id", "category"),
        Index("ix_research_findings_project", "research_project_id"),
        Index("ix_research_findings_business_created", "business_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    research_project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    classification: Mapped[str] = mapped_column(String(20), nullable=False)
    importance: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")
    evidence_strength: Mapped[str] = mapped_column(
        String(20), nullable=False, default="insufficient"
    )
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


research_finding_evidence = Table(
    "research_finding_evidence",
    Base.metadata,
    Column(
        "finding_id",
        ForeignKey("research_findings.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "evidence_id",
        ForeignKey("research_evidence.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Index("ix_research_finding_evidence_evidence", "evidence_id"),
)


__all__ = [
    "ResearchCompetitor",
    "ResearchCollectionJob",
    "ResearchCollectionPage",
    "ResearchIntelligenceItem",
    "ResearchIntelligenceSnapshot",
    "ResearchEvidence",
    "ResearchFinding",
    "ResearchProject",
    "ResearchSource",
    "ResearchSourceSnapshot",
    "research_intelligence_item_findings",
    "research_finding_evidence",
]
