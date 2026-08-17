"""simulations: deterministic campaign simulator persistence

Adds the Phase 5A tables for the deterministic simulator:

- `simulations` — one row per simulation (business or campaign scope).
  The `assumptions_hash` column is a deterministic SHA-256 of the
  resolved assumptions and reference window; the unique constraint
  (organization_id, business_id, entity_type, entity_id,
  assumptions_hash, model_version) makes replaying identical inputs
  collapse to the same row (upsert). Input, assumptions and results
  snapshots are JSONB with money stored as Decimal strings (never float).
- `simulation_assumptions` — flat assumption rows for querying.
- `simulation_results` — flat scenario rows for querying.

Simulations are read-only analysis: nothing in this migration or the
module that writes these rows ever executes provider actions, budget
changes or campaign edits (see docs/architecture/simulator.md).

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MONEY = sa.Numeric(14, 2)
_RATE = sa.Numeric(14, 6)


def upgrade() -> None:
    op.create_table(
        "simulations",
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
        sa.Column("model_version", sa.String(20), nullable=False),
        sa.Column("assumptions_hash", sa.String(64), nullable=False),
        sa.Column("model_used", sa.String(40), nullable=False),
        sa.Column("calculation_path", sa.String(255), nullable=False),
        sa.Column("data_quality", sa.String(20), nullable=False),
        sa.Column("evidence_strength", sa.String(20), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("budget", _MONEY, nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("historical_window_days", sa.Integer(), nullable=False),
        sa.Column("reference_start", sa.Date(), nullable=True),
        sa.Column("reference_end", sa.Date(), nullable=True),
        sa.Column("input_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("assumptions_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("results_snapshot", postgresql.JSONB(), nullable=False),
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
            "entity_type",
            "entity_id",
            "assumptions_hash",
            "model_version",
            name="uq_simulation_identity",
            postgresql_nulls_not_distinct=True,
        ),
        sa.CheckConstraint("duration_days > 0", name="ck_simulation_duration_positive"),
        sa.CheckConstraint("historical_window_days > 0", name="ck_simulation_window_days_positive"),
        sa.CheckConstraint(
            "reference_end >= reference_start",
            name="ck_simulation_reference_window_valid",
        ),
    )
    op.create_index(
        "ix_simulations_business_entity",
        "simulations",
        ["business_id", "entity_type", "entity_id"],
    )
    op.create_index(
        "ix_simulations_business_created",
        "simulations",
        ["business_id", "created_at"],
    )

    op.create_table(
        "simulation_assumptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "simulation_id",
            sa.Uuid(),
            sa.ForeignKey("simulations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("value", _MONEY, nullable=True),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("source_entity", sa.String(40), nullable=True),
        sa.Column("historical_value", _MONEY, nullable=True),
        sa.Column("override", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("unavailable_reason", sa.String(200), nullable=True),
        sa.UniqueConstraint("simulation_id", "name", name="uq_simulation_assumption_name"),
    )
    op.create_index(
        "ix_simulation_assumptions_simulation",
        "simulation_assumptions",
        ["simulation_id"],
    )

    op.create_table(
        "simulation_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "simulation_id",
            sa.Uuid(),
            sa.ForeignKey("simulations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scenario", sa.String(20), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=True),
        sa.Column("available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.UniqueConstraint("simulation_id", "scenario", name="uq_simulation_result_scenario"),
    )
    op.create_index("ix_simulation_results_simulation", "simulation_results", ["simulation_id"])


def downgrade() -> None:
    op.drop_index("ix_simulation_results_simulation", table_name="simulation_results")
    op.drop_table("simulation_results")
    op.drop_index("ix_simulation_assumptions_simulation", table_name="simulation_assumptions")
    op.drop_table("simulation_assumptions")
    op.drop_index("ix_simulations_business_created", table_name="simulations")
    op.drop_index("ix_simulations_business_entity", table_name="simulations")
    op.drop_table("simulations")
