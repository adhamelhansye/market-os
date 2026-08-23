"""Creative action drafts linkage (Phase 8G).

Creates one table:

- creative_action_drafts
  Links acknowledged Phase 8F opportunities to the 8B CreativeTest
  drafts produced by deterministic action preparation. UNIQUE
  (business_id, source_opportunity_id) is the idempotency mechanism;
  draft review state reuses the four non-executional states.

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-23
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "creative_action_drafts",
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
        sa.Column("source_opportunity_id", sa.String(200), nullable=False),
        sa.Column("source_plan_fingerprint", sa.String(64), nullable=False),
        sa.Column("draft_test_id", sa.String(80), nullable=False),
        sa.Column("draft_kind", sa.String(30), nullable=False),
        sa.Column("review_state", sa.String(20), nullable=False, server_default="proposed"),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "decided_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
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
        sa.CheckConstraint(
            "draft_kind IN ('expansion','coverage_gap','fatigue')",
            name="ck_action_draft_kind_allowed",
        ),
        sa.CheckConstraint(
            "review_state IN ('proposed','acknowledged','dismissed','deferred')",
            name="ck_action_draft_review_state_allowed",
        ),
    )
    op.create_index(
        "uq_creative_action_drafts_opportunity",
        "creative_action_drafts",
        ["business_id", "source_opportunity_id"],
        unique=True,
    )
    op.create_index(
        "ix_creative_action_drafts_business_created",
        "creative_action_drafts",
        ["business_id", "created_at"],
    )
    op.create_index(
        "ix_creative_action_drafts_test_id",
        "creative_action_drafts",
        ["draft_test_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_creative_action_drafts_test_id", table_name="creative_action_drafts"
    )
    op.drop_index(
        "ix_creative_action_drafts_business_created",
        table_name="creative_action_drafts",
    )
    op.drop_index(
        "uq_creative_action_drafts_opportunity", table_name="creative_action_drafts"
    )
    op.drop_table("creative_action_drafts")
