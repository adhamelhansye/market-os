"""persist deterministic strategy decision evaluations.

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "strategy_decisions",
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
        sa.Column("candidate_type", sa.String(20), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("strategy_version", sa.String(40), nullable=False),
        sa.Column("decision_rules_version", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("overall_score", sa.Numeric(6, 4), nullable=True),
        sa.Column("input_snapshot", JSON, nullable=False, server_default="{}"),
        sa.Column("evaluation", JSON, nullable=False, server_default="{}"),
        sa.Column("reasons", JSON, nullable=False, server_default="[]"),
        sa.Column("provenance", JSON, nullable=False, server_default="[]"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_strategy_decisions_business_created",
        "strategy_decisions",
        ["business_id", "created_at"],
    )
    op.create_index("ix_strategy_decisions_candidate", "strategy_decisions", ["candidate_id"])


def downgrade() -> None:
    op.drop_index("ix_strategy_decisions_candidate", table_name="strategy_decisions")
    op.drop_index("ix_strategy_decisions_business_created", table_name="strategy_decisions")
    op.drop_table("strategy_decisions")
