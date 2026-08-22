"""Creative optimization snapshots (Phase 8E).

Creates one table:

- creative_optimization_snapshots
  Immutable, fingerprint-keyed optimization plans computed
  deterministically from Phase 8C/8D artifacts and Phase 7 context.

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-22
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "creative_optimization_snapshots",
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
        sa.Column("range_kind", sa.String(30), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("rules_version", sa.String(40), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
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
        "uq_creative_optimization_snapshots_fingerprint",
        "creative_optimization_snapshots",
        ["business_id", "fingerprint"],
        unique=True,
    )
    op.create_index(
        "ix_creative_optimization_snapshots_business_created",
        "creative_optimization_snapshots",
        ["business_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_creative_optimization_snapshots_business_created",
        table_name="creative_optimization_snapshots",
    )
    op.drop_index(
        "uq_creative_optimization_snapshots_fingerprint",
        table_name="creative_optimization_snapshots",
    )
    op.drop_table("creative_optimization_snapshots")
