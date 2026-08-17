"""research: research intelligence foundation persistence

Adds the Phase 6A tables for the deterministic research layer:

- `research_projects` — an investigation (market / customer / competitor
  / mixed) with a lifecycle status (draft → collecting → processing →
  completed → archived; failed is a terminal error state).
- `research_competitors` — competitor records; domain optional.
- `research_sources` — origin of information (website, product page,
  review, ...). Optional url, optional content hash; the unique
  constraint (organization_id, business_id, content_hash) makes
  re-submitting identical content collapse to the same source. The URL
  is never fetched by the backend (no scraping, no SSRF surface).
- `research_source_snapshots` — reproducible captures keyed by
  (source_id, content_hash).
- `research_evidence` — deterministic claims referencing exactly one
  source, with a fixed confidence vocabulary (observed / supported /
  inferred / hypothesis) and explicit provenance.
- `research_findings` — normalized conclusions per project (category +
  classification), linked to one or more evidence rows through
  `research_finding_evidence`.

Monetary values inside JSONB (`structured_value`, metadata) are stored
as Decimal strings, never float. This layer performs no external
requests, no LLM calls and no autonomous action.

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_projects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "business_id",
            sa.Uuid(),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("scope", sa.String(1000), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_research_projects_business_created",
        "research_projects",
        ["business_id", "created_at"],
    )

    op.create_table(
        "research_competitors",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "business_id",
            sa.Uuid(),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("domain", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("market", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "organization_id",
            "business_id",
            "name",
            name="uq_research_competitor_name",
        ),
    )
    op.create_index(
        "ix_research_competitors_business",
        "research_competitors",
        ["business_id"],
    )

    op.create_table(
        "research_sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "business_id",
            sa.Uuid(),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("url", sa.String(1024), nullable=True),
        sa.Column("domain", sa.String(255), nullable=True),
        sa.Column("author", sa.String(255), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column(
            "competitor_id",
            sa.Uuid(),
            sa.ForeignKey("research_competitors.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "organization_id",
            "business_id",
            "content_hash",
            name="uq_research_source_content_hash",
        ),
    )
    op.create_index(
        "ix_research_sources_business_type",
        "research_sources",
        ["business_id", "source_type"],
    )
    op.create_index(
        "ix_research_sources_business_competitor",
        "research_sources",
        ["business_id", "competitor_id"],
    )
    op.create_index(
        "ix_research_sources_business_captured",
        "research_sources",
        ["business_id", "captured_at"],
    )

    op.create_table(
        "research_source_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("research_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.UniqueConstraint("source_id", "content_hash", name="uq_research_snapshot_hash"),
    )
    op.create_index("ix_research_snapshots_source", "research_source_snapshots", ["source_id"])

    op.create_table(
        "research_evidence",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "business_id",
            sa.Uuid(),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("research_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("evidence_type", sa.String(30), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("raw_excerpt", sa.Text(), nullable=True),
        sa.Column("structured_value", postgresql.JSONB(), nullable=True),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("provenance", sa.String(30), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_research_evidence_business_type",
        "research_evidence",
        ["business_id", "evidence_type"],
    )
    op.create_index(
        "ix_research_evidence_business_captured",
        "research_evidence",
        ["business_id", "captured_at"],
    )
    op.create_index("ix_research_evidence_source", "research_evidence", ["source_id"])

    op.create_table(
        "research_findings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "business_id",
            sa.Uuid(),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "research_project_id",
            sa.Uuid(),
            sa.ForeignKey("research_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("classification", sa.String(20), nullable=False),
        sa.Column("importance", sa.String(10), nullable=False, server_default="medium"),
        sa.Column(
            "evidence_strength",
            sa.String(20),
            nullable=False,
            server_default="insufficient",
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_research_findings_business_category",
        "research_findings",
        ["business_id", "category"],
    )
    op.create_index(
        "ix_research_findings_project",
        "research_findings",
        ["research_project_id"],
    )
    op.create_index(
        "ix_research_findings_business_created",
        "research_findings",
        ["business_id", "created_at"],
    )

    op.create_table(
        "research_finding_evidence",
        sa.Column(
            "finding_id",
            sa.Uuid(),
            sa.ForeignKey("research_findings.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "evidence_id",
            sa.Uuid(),
            sa.ForeignKey("research_evidence.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_research_finding_evidence_evidence",
        "research_finding_evidence",
        ["evidence_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_research_finding_evidence_evidence", table_name="research_finding_evidence")
    op.drop_table("research_finding_evidence")
    op.drop_index("ix_research_findings_business_created", table_name="research_findings")
    op.drop_index("ix_research_findings_project", table_name="research_findings")
    op.drop_index("ix_research_findings_business_category", table_name="research_findings")
    op.drop_table("research_findings")
    op.drop_index("ix_research_evidence_source", table_name="research_evidence")
    op.drop_index("ix_research_evidence_business_captured", table_name="research_evidence")
    op.drop_index("ix_research_evidence_business_type", table_name="research_evidence")
    op.drop_table("research_evidence")
    op.drop_index("ix_research_snapshots_source", table_name="research_source_snapshots")
    op.drop_table("research_source_snapshots")
    op.drop_index("ix_research_sources_business_captured", table_name="research_sources")
    op.drop_index("ix_research_sources_business_competitor", table_name="research_sources")
    op.drop_index("ix_research_sources_business_type", table_name="research_sources")
    op.drop_table("research_sources")
    op.drop_index("ix_research_competitors_business", table_name="research_competitors")
    op.drop_table("research_competitors")
    op.drop_index("ix_research_projects_business_created", table_name="research_projects")
    op.drop_table("research_projects")