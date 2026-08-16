"""recommendations: deterministic decision persistence

Adds the Phase 4B table for the deterministic decision engine:

- `recommendations` — one row per decision (business or campaign scope) for
  a range. The `fingerprint` column is a deterministic SHA-256 of
  (organization_id, business_id, entity_type, entity_id, range_start,
  range_end, rules_version); the unique constraint on it makes
  recomputation idempotent. Evidence, snapshots and review suggestions are
  JSONB. Money values inside snapshots are stored as Decimal strings
  (never float).

Decisions are review recommendations only: nothing in this migration or the
module that writes these rows ever executes provider actions, budget
changes or campaign edits (see docs/architecture/recommendations.md).

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-15
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recommendations",
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
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column(
            "entity_id",
            sa.Uuid(),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("entity_name", sa.String(255), nullable=True),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("evidence_strength", sa.String(20), nullable=False),
        sa.Column("primary_reason", sa.String(120), nullable=False),
        sa.Column("diagnostics", postgresql.JSONB(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("review_suggestions", postgresql.JSONB(), nullable=False),
        sa.Column("metrics_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("forecast_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("range_start", sa.Date(), nullable=False),
        sa.Column("range_end", sa.Date(), nullable=False),
        sa.Column("rules_version", sa.String(20), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
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
        sa.UniqueConstraint("fingerprint", name="uq_recommendation_fingerprint"),
        sa.CheckConstraint(
            "range_end >= range_start", name="ck_recommendation_range_valid"
        ),
    )
    op.create_index(
        "ix_recommendations_business_entity",
        "recommendations",
        ["business_id", "entity_type", "entity_id"],
    )
    op.create_index(
        "ix_recommendations_business_decision",
        "recommendations",
        ["business_id", "decision"],
    )


def downgrade() -> None:
    op.drop_index("ix_recommendations_business_decision", table_name="recommendations")
    op.drop_index("ix_recommendations_business_entity", table_name="recommendations")
    op.drop_table("recommendations")