"""Creative intelligence foundation (Phase 8A).

Creates the 7 creative intelligence tables matching the ORM models in
``src/db/models/creative.py``:

- creative_concepts
- creative_briefs
- creative_matrix_entries
- creative_risks
- creative_evidence
- creative_snapshots
- creative_provenance

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-19
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "creative_concepts",
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("strategy_version", sa.String(40), nullable=False),
        sa.Column(
            "positioning_reference",
            sa.Uuid(),
            sa.ForeignKey("positioning_strategies.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "offer_reference",
            sa.Uuid(),
            sa.ForeignKey("offer_candidates.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "messaging_reference",
            sa.Uuid(),
            sa.ForeignKey("messaging_strategies.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "funnel_reference",
            sa.Uuid(),
            sa.ForeignKey("funnel_strategies.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("funnel_stage", sa.String(20), nullable=True),
        sa.Column("audience", sa.Text(), nullable=True),
        sa.Column("angle", sa.String(50), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("hook_direction", sa.String(100), nullable=True),
        sa.Column("creative_format", sa.String(50), nullable=False),
        sa.Column("creative_type", sa.String(50), nullable=True),
        sa.Column("offer_direction", sa.Text(), nullable=True),
        sa.Column("cta", sa.String(50), nullable=True),
        sa.Column("visual_direction", sa.Text(), nullable=True),
        sa.Column("copy_direction", sa.Text(), nullable=True),
        sa.Column("primary_emotion", sa.String(30), nullable=True),
        sa.Column("secondary_emotion", sa.String(30), nullable=True),
        sa.Column("objection", sa.String(50), nullable=True),
        sa.Column("reason_to_believe", sa.Text(), nullable=True),
        sa.Column("testing_role", sa.String(50), nullable=True),
        sa.Column("success_metric", sa.String(50), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("risks", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
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
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_creative_concepts_business_created",
        "creative_concepts",
        ["business_id", "created_at"],
    )
    op.create_index(
        "ix_creative_concepts_business_status",
        "creative_concepts",
        ["business_id", "status"],
    )

    op.create_table(
        "creative_briefs",
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("objective", sa.String(50), nullable=False),
        sa.Column("target_audience", sa.Text(), nullable=True),
        sa.Column("funnel_stage", sa.String(20), nullable=True),
        sa.Column("customer_problem", sa.Text(), nullable=True),
        sa.Column("customer_desire", sa.Text(), nullable=True),
        sa.Column("core_message", sa.Text(), nullable=True),
        sa.Column("angle", sa.String(50), nullable=True),
        sa.Column("hook_direction", sa.String(100), nullable=True),
        sa.Column("offer", sa.Text(), nullable=True),
        sa.Column("proof", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("objection", sa.String(50), nullable=True),
        sa.Column("cta", sa.String(50), nullable=True),
        sa.Column("creative_format", sa.String(50), nullable=True),
        sa.Column("visual_direction", sa.Text(), nullable=True),
        sa.Column("copy_direction", sa.Text(), nullable=True),
        sa.Column("emotional_direction", sa.Text(), nullable=True),
        sa.Column("reason_to_believe", sa.Text(), nullable=True),
        sa.Column("testing_hypothesis", sa.Text(), nullable=True),
        sa.Column("success_metric", sa.String(50), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
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
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_creative_briefs_business_created",
        "creative_briefs",
        ["business_id", "created_at"],
    )

    op.create_table(
        "creative_matrix_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("angle", sa.String(50), nullable=True),
        sa.Column("funnel_stage", sa.String(20), nullable=True),
        sa.Column("creative_format", sa.String(50), nullable=True),
        sa.Column("creative_type", sa.String(50), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("offer", sa.Text(), nullable=True),
        sa.Column("proof", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("audience", sa.Text(), nullable=True),
        sa.Column("objective", sa.String(50), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("evidence_strength", sa.String(30), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_creative_matrix_entries_business_created",
        "creative_matrix_entries",
        ["business_id", "created_at"],
    )

    op.create_table(
        "creative_risks",
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("risk_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(30), nullable=False),
        sa.Column("related_concept_id", sa.Uuid(), nullable=True),
        sa.Column(
            "resolved", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_creative_risks_business_created",
        "creative_risks",
        ["business_id", "created_at"],
    )

    op.create_table(
        "creative_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("evidence_type", sa.String(50), nullable=False),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("reference_id", sa.Uuid(), nullable=True),
        sa.Column("reference_type", sa.String(50), nullable=True),
        sa.Column("citation", sa.Text(), nullable=True),
        sa.Column("captures", sa.Text(), nullable=True),
        sa.Column("captures_url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="available"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_creative_evidence_business_created",
        "creative_evidence",
        ["business_id", "created_at"],
    )

    op.create_table(
        "creative_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("creative_type", sa.String(50), nullable=False),
        sa.Column("creative_format", sa.String(50), nullable=False),
        sa.Column("angle", sa.String(50), nullable=True),
        sa.Column("funnel_stage", sa.String(20), nullable=True),
        sa.Column("objective", sa.String(50), nullable=True),
        sa.Column("positioning_version", sa.String(40), nullable=True),
        sa.Column("offer_version", sa.String(40), nullable=True),
        sa.Column("strategy_decision_id", sa.Uuid(), nullable=True),
        sa.Column("messaging_version", sa.String(40), nullable=True),
        sa.Column("funnel_version", sa.String(40), nullable=True),
        sa.Column("research_version", sa.String(40), nullable=True),
        sa.Column("creative_rules_version", sa.String(40), nullable=True),
        sa.Column("input_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("output_summary", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_creative_snapshots_business_created",
        "creative_snapshots",
        ["business_id", "created_at"],
    )

    op.create_table(
        "creative_provenance",
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("step", sa.String(50), nullable=False),
        sa.Column(
            "positioning_id",
            sa.Uuid(),
            sa.ForeignKey("positioning_strategies.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "offer_id",
            sa.Uuid(),
            sa.ForeignKey("offer_candidates.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "messaging_id",
            sa.Uuid(),
            sa.ForeignKey("messaging_strategies.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "funnel_id",
            sa.Uuid(),
            sa.ForeignKey("funnel_strategies.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "(positioning_id IS NOT NULL)::int"
            "+ (offer_id IS NOT NULL)::int"
            "+ (messaging_id IS NOT NULL)::int"
            "+ (funnel_id IS NOT NULL)::int"
            " = 1",
            name="ck_creative_provenance_exactly_one_reference",
        ),
    )
    op.create_index(
        "ix_creative_provenance_business_created",
        "creative_provenance",
        ["business_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_creative_provenance_business_created", table_name="creative_provenance"
    )
    op.drop_table("creative_provenance")
    op.drop_index(
        "ix_creative_snapshots_business_created", table_name="creative_snapshots"
    )
    op.drop_table("creative_snapshots")
    op.drop_index(
        "ix_creative_evidence_business_created", table_name="creative_evidence"
    )
    op.drop_table("creative_evidence")
    op.drop_index(
        "ix_creative_risks_business_created", table_name="creative_risks"
    )
    op.drop_table("creative_risks")
    op.drop_index(
        "ix_creative_matrix_entries_business_created", table_name="creative_matrix_entries"
    )
    op.drop_table("creative_matrix_entries")
    op.drop_index(
        "ix_creative_briefs_business_created", table_name="creative_briefs"
    )
    op.drop_table("creative_briefs")
    op.drop_index(
        "ix_creative_concepts_business_status", table_name="creative_concepts"
    )
    op.drop_index(
        "ix_creative_concepts_business_created", table_name="creative_concepts"
    )
    op.drop_table("creative_concepts")
