"""Creative test lifecycle events (Phase 8H).

Creates one table and one constraint:

- creative_test_activations
  Immutable audit events for creative-test lifecycle transitions
  (draft -> active -> completed/cancelled). Activation requires the
  strict Phase 8G gate (second-stage review acknowledged) and records
  the human actor; rows are never updated.

- CHECK on creative_tests.status bounding the lifecycle vocabulary to
  draft / active / completed / cancelled.

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-23
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels = None
depends_on = None

ALLOWED = "draft','active','completed','cancelled"


def upgrade() -> None:
    op.create_table(
        "creative_test_activations",
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
        sa.Column("creative_test_id", sa.Uuid(), nullable=False),
        sa.Column("creative_test_external_ref", sa.String(80), nullable=False),
        sa.Column("source_action_draft_id", sa.Uuid(), nullable=False),
        sa.Column("source_opportunity_id", sa.String(200), nullable=False),
        sa.Column("source_plan_fingerprint", sa.String(64), nullable=False),
        sa.Column("previous_status", sa.String(20), nullable=False),
        sa.Column("new_status", sa.String(20), nullable=False),
        sa.Column(
            "activated_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            f"previous_status IN ('{ALLOWED}')",
            name="ck_activation_previous_status_allowed",
        ),
        sa.CheckConstraint(
            f"new_status IN ('{ALLOWED}')",
            name="ck_activation_new_status_allowed",
        ),
    )
    op.create_index(
        "ix_creative_test_activations_test_created",
        "creative_test_activations",
        ["creative_test_id", "created_at"],
    )
    op.create_index(
        "ix_creative_test_activations_business_created",
        "creative_test_activations",
        ["business_id", "created_at"],
    )

    op.create_check_constraint(
        "ck_creative_tests_status_allowed",
        "creative_tests",
        f"status IN ('{ALLOWED}')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_creative_tests_status_allowed", "creative_tests", type_="check"
    )
    op.drop_index(
        "ix_creative_test_activations_business_created",
        table_name="creative_test_activations",
    )
    op.drop_index(
        "ix_creative_test_activations_test_created",
        table_name="creative_test_activations",
    )
    op.drop_table("creative_test_activations")
