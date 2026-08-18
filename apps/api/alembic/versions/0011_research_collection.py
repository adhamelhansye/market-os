"""research collection jobs and reproducible collection pages.

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("research_sources", sa.Column("original_url", sa.String(2048)))
    op.add_column("research_sources", sa.Column("normalized_url", sa.String(2048)))
    op.add_column(
        "research_evidence",
        sa.Column(
            "research_project_id",
            sa.Uuid(),
            sa.ForeignKey("research_projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.add_column(
        "research_evidence",
        sa.Column(
            "snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("research_source_snapshots.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_research_evidence_project", "research_evidence", ["research_project_id"])
    op.create_index("ix_research_evidence_snapshot", "research_evidence", ["snapshot_id"])

    op.create_table(
        "research_collection_jobs",
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
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("research_sources.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("mode", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("max_pages", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("same_domain", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("refresh", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "requested_urls",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("pages_collected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("change_status", sa.String(20), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_research_collection_jobs_business_created",
        "research_collection_jobs",
        ["business_id", "created_at"],
    )
    op.create_index(
        "ix_research_collection_jobs_project_status",
        "research_collection_jobs",
        ["research_project_id", "status"],
    )
    op.create_index(
        "ix_research_collection_jobs_source_created",
        "research_collection_jobs",
        ["source_id", "created_at"],
    )
    op.create_unique_constraint(
        "uq_research_collection_idempotency",
        "research_collection_jobs",
        ["organization_id", "business_id", "idempotency_key"],
    )

    op.create_table(
        "research_collection_pages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "collection_job_id",
            sa.Uuid(),
            sa.ForeignKey("research_collection_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("research_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original_url", sa.String(2048), nullable=False),
        sa.Column("normalized_url", sa.String(2048), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("canonical_url", sa.String(2048), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("response_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "retrieved_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_unique_constraint(
        "uq_research_collection_page_url",
        "research_collection_pages",
        ["collection_job_id", "normalized_url"],
    )
    op.create_index(
        "ix_research_collection_pages_job", "research_collection_pages", ["collection_job_id"]
    )
    op.create_index(
        "ix_research_collection_pages_source", "research_collection_pages", ["source_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_research_collection_pages_source", table_name="research_collection_pages")
    op.drop_index("ix_research_collection_pages_job", table_name="research_collection_pages")
    op.drop_constraint(
        "uq_research_collection_page_url", "research_collection_pages", type_="unique"
    )
    op.drop_table("research_collection_pages")
    op.drop_constraint(
        "uq_research_collection_idempotency", "research_collection_jobs", type_="unique"
    )
    op.drop_index(
        "ix_research_collection_jobs_source_created", table_name="research_collection_jobs"
    )
    op.drop_index(
        "ix_research_collection_jobs_project_status", table_name="research_collection_jobs"
    )
    op.drop_index(
        "ix_research_collection_jobs_business_created", table_name="research_collection_jobs"
    )
    op.drop_table("research_collection_jobs")
    op.drop_index("ix_research_evidence_snapshot", table_name="research_evidence")
    op.drop_index("ix_research_evidence_project", table_name="research_evidence")
    op.drop_column("research_evidence", "snapshot_id")
    op.drop_column("research_evidence", "research_project_id")
    op.drop_column("research_sources", "normalized_url")
    op.drop_column("research_sources", "original_url")
