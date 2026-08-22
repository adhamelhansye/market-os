"""Creative decision plans and human review (Phase 8F).

Creates two tables:

- creative_decision_plans
  Immutable, fingerprint-keyed decision-plan snapshots assembled from
  the latest Phase 8E optimization snapshot.

- creative_decision_item_reviews
  The repository's only mutable human-review state. Review states are
  deliberately non-executional (proposed/acknowledged/dismissed/
  deferred); a review never executes or modifies anything.

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-22
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "creative_decision_plans",
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
        sa.Column("rules_version", sa.String(40), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("source_optimization_fingerprint", sa.String(64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_by",
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
    )
    op.create_index(
        "uq_creative_decision_plans_fingerprint",
        "creative_decision_plans",
        ["business_id", "fingerprint"],
        unique=True,
    )
    op.create_index(
        "ix_creative_decision_plans_business_created",
        "creative_decision_plans",
        ["business_id", "created_at"],
    )

    op.create_table(
        "creative_decision_item_reviews",
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
        sa.Column("opportunity_id", sa.String(200), nullable=False),
        sa.Column("source_plan_fingerprint", sa.String(64), nullable=False),
        sa.Column("review_state", sa.String(20), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column(
            "decided_by",
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "review_state IN ('proposed','acknowledged','dismissed','deferred')",
            name="ck_decision_review_state_allowed",
        ),
    )
    op.create_index(
        "uq_creative_decision_item_reviews_opportunity",
        "creative_decision_item_reviews",
        ["business_id", "opportunity_id"],
        unique=True,
    )
    op.create_index(
        "ix_creative_decision_item_reviews_business_updated",
        "creative_decision_item_reviews",
        ["business_id", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_creative_decision_item_reviews_business_updated",
        table_name="creative_decision_item_reviews",
    )
    op.drop_index(
        "uq_creative_decision_item_reviews_opportunity",
        table_name="creative_decision_item_reviews",
    )
    op.drop_table("creative_decision_item_reviews")
    op.drop_index(
        "ix_creative_decision_plans_business_created",
        table_name="creative_decision_plans",
    )
    op.drop_index(
        "uq_creative_decision_plans_fingerprint",
        table_name="creative_decision_plans",
    )
    op.drop_table("creative_decision_plans")
