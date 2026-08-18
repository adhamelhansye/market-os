"""deterministic research intelligence snapshots and items.

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_intelligence_snapshots",
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
            nullable=True,
        ),
        sa.Column(
            "generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snapshot_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("finding_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "intelligence_version",
            sa.String(40),
            nullable=False,
            server_default="research_intelligence_v1",
        ),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("freshness", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column(
            "coverage_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "missing_areas_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.create_index(
        "ix_research_intelligence_snapshots_business_generated",
        "research_intelligence_snapshots",
        ["business_id", "generated_at"],
    )
    op.create_index(
        "ix_research_intelligence_snapshots_project_generated",
        "research_intelligence_snapshots",
        ["research_project_id", "generated_at"],
    )

    op.create_table(
        "research_intelligence_items",
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
            "snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("research_intelligence_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "research_project_id",
            sa.Uuid(),
            sa.ForeignKey("research_projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "competitor_id",
            sa.Uuid(),
            sa.ForeignKey("research_competitors.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("intelligence_type", sa.String(20), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("classification", sa.String(20), nullable=False),
        sa.Column("strength", sa.String(20), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("freshness", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_research_intelligence_items_snapshot_type",
        "research_intelligence_items",
        ["snapshot_id", "intelligence_type"],
    )
    op.create_index(
        "ix_research_intelligence_items_business_category",
        "research_intelligence_items",
        ["business_id", "category"],
    )
    op.create_index(
        "ix_research_intelligence_items_competitor",
        "research_intelligence_items",
        ["competitor_id"],
    )

    op.create_table(
        "research_intelligence_item_findings",
        sa.Column(
            "item_id",
            sa.Uuid(),
            sa.ForeignKey("research_intelligence_items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "finding_id",
            sa.Uuid(),
            sa.ForeignKey("research_findings.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_research_intelligence_item_findings_finding",
        "research_intelligence_item_findings",
        ["finding_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_intelligence_item_findings_finding",
        table_name="research_intelligence_item_findings",
    )
    op.drop_table("research_intelligence_item_findings")
    op.drop_index(
        "ix_research_intelligence_items_competitor",
        table_name="research_intelligence_items",
    )
    op.drop_index(
        "ix_research_intelligence_items_business_category",
        table_name="research_intelligence_items",
    )
    op.drop_index(
        "ix_research_intelligence_items_snapshot_type",
        table_name="research_intelligence_items",
    )
    op.drop_table("research_intelligence_items")
    op.drop_index(
        "ix_research_intelligence_snapshots_project_generated",
        table_name="research_intelligence_snapshots",
    )
    op.drop_index(
        "ix_research_intelligence_snapshots_business_generated",
        table_name="research_intelligence_snapshots",
    )
    op.drop_table("research_intelligence_snapshots")
