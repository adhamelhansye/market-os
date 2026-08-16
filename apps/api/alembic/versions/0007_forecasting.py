"""forecasting: deterministic forecast persistence

Adds the Phase 4A tables for the deterministic forecasting engine:

- `forecasts`  — one row per persisted forecast (business + entity + metric
  + horizon + cutoff + model_version). The unique constraint on
  (organization_id, business_id, entity_type, entity_id, metric_code,
  horizon_days, training_end, model_version) gives a deterministic
  idempotency key: regenerating the same forecast never creates
  duplicates.
- `forecast_points` — daily expected/lower/upper values for the
  forecast window. Unique on (forecast_id, date). Stored as money/count
  Decimal strings (never float).

Forecasts are computed deterministically from canonical metric_facts (see
the Phase 3A migration 0006). No LLM, no simulator, no autonomous
actions (see docs/architecture/forecasting.md).

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-15
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_MONEY = sa.Numeric(14, 2)


def _uuid_pk() -> sa.Column:
    return sa.Column("id", sa.Uuid(), primary_key=True)


def upgrade() -> None:
    op.create_table(
        "forecasts",
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
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("metric_code", sa.String(40), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("forecast_start", sa.Date(), nullable=False),
        sa.Column("forecast_end", sa.Date(), nullable=False),
        sa.Column("training_start", sa.Date(), nullable=False),
        sa.Column("training_end", sa.Date(), nullable=False),
        sa.Column("model", sa.String(40), nullable=False),
        sa.Column("model_version", sa.String(20), nullable=False),
        sa.Column("confidence_level", _MONEY, nullable=False),
        sa.Column("expected_value", _MONEY, nullable=True),
        sa.Column("lower_value", _MONEY, nullable=True),
        sa.Column("upper_value", _MONEY, nullable=True),
        sa.Column("observations_used", sa.Integer(), nullable=False),
        sa.Column("missing_observations", sa.Integer(), nullable=False),
        sa.Column("backtest_mae", _MONEY, nullable=True),
        sa.Column("backtest_smape", _MONEY, nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
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
            "metric_code",
            "horizon_days",
            "training_end",
            "model_version",
            name="uq_forecast_identity",
        ),
        sa.CheckConstraint(
            "horizon_days > 0", name="ck_forecast_horizon_positive"
        ),
        sa.CheckConstraint(
            "confidence_level > 0 AND confidence_level < 1",
            name="ck_forecast_confidence_valid",
        ),
        sa.CheckConstraint(
            "forecast_end >= forecast_start",
            name="ck_forecast_window_valid",
        ),
        sa.CheckConstraint(
            "training_end >= training_start",
            name="ck_forecast_training_window_valid",
        ),
        sa.CheckConstraint(
            "expected_value IS NULL OR expected_value >= 0",
            name="ck_forecast_expected_non_negative",
        ),
        sa.CheckConstraint(
            "(lower_value IS NULL) OR (upper_value IS NULL) OR "
            "(lower_value <= upper_value)",
            name="ck_forecast_interval_ordered",
        ),
        sa.CheckConstraint(
            "(lower_value IS NULL) OR (expected_value IS NULL) OR "
            "(expected_value >= lower_value)",
            name="ck_forecast_expected_above_lower",
        ),
        sa.CheckConstraint(
            "(expected_value IS NULL) OR (upper_value IS NULL) OR "
            "(expected_value <= upper_value)",
            name="ck_forecast_expected_below_upper",
        ),
    )
    op.create_index(
        "ix_forecasts_business_entity",
        "forecasts",
        ["business_id", "entity_type", "entity_id", "metric_code"],
    )
    op.create_index(
        "ix_forecasts_business_training_end",
        "forecasts",
        ["business_id", "training_end"],
    )

    op.create_table(
        "forecast_points",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "forecast_id",
            sa.Uuid(),
            sa.ForeignKey("forecasts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("expected_value", _MONEY, nullable=False),
        sa.Column("lower_value", _MONEY, nullable=False),
        sa.Column("upper_value", _MONEY, nullable=False),
        sa.UniqueConstraint("forecast_id", "date", name="uq_forecast_point"),
        sa.CheckConstraint(
            "lower_value <= expected_value",
            name="ck_forecast_point_lower_below_expected",
        ),
        sa.CheckConstraint(
            "expected_value <= upper_value",
            name="ck_forecast_point_expected_below_upper",
        ),
        sa.CheckConstraint(
            "expected_value >= 0",
            name="ck_forecast_point_expected_non_negative",
        ),
    )
    op.create_index(
        "ix_forecast_points_forecast", "forecast_points", ["forecast_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_forecast_points_forecast", table_name="forecast_points")
    op.drop_table("forecast_points")
    op.drop_index(
        "ix_forecasts_business_training_end", table_name="forecasts"
    )
    op.drop_index("ix_forecasts_business_entity", table_name="forecasts")
    op.drop_table("forecasts")
