"""add deterministic funnel strategy records.

Revision ID: 0016
Revises: 0015
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = postgresql.JSONB(astext_type=sa.Text())


def _tenant() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "funnel_strategies",
        *_tenant(),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("funnel_version", sa.String(40), nullable=False),
        sa.Column("variant", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("positioning_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("offer_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("strategy_decision_id", sa.Uuid(), nullable=True),
        sa.Column("messaging_strategy_id", sa.Uuid(), nullable=True),
        sa.Column("input_snapshot", JSON, nullable=False, server_default="{}"),
        sa.Column("health", JSON, nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_funnel_strategies_business_created",
        "funnel_strategies",
        ["business_id", "created_at"],
    )
    op.create_index(
        "ix_funnel_strategies_business_version",
        "funnel_strategies",
        ["business_id", "version"],
    )
    op.create_table(
        "funnel_stages",
        *_tenant(),
        sa.Column(
            "funnel_strategy_id",
            sa.Uuid(),
            sa.ForeignKey("funnel_strategies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("objective", sa.String(200), nullable=False),
        sa.Column("audience_state", sa.String(40), nullable=False),
        sa.Column("customer_problem", sa.Text(), nullable=True),
        sa.Column("customer_desire", sa.Text(), nullable=True),
        sa.Column("message_direction", sa.Text(), nullable=False),
        sa.Column("offer_direction", sa.Text(), nullable=True),
        sa.Column("content_direction", sa.Text(), nullable=False),
        sa.Column("cta_type", sa.String(30), nullable=True),
        sa.Column("entry_condition", JSON, nullable=False, server_default="{}"),
        sa.Column("exit_condition", JSON, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("risks", JSON, nullable=False, server_default="[]"),
        sa.Column("evidence_refs", JSON, nullable=False, server_default="[]"),
        sa.Column("provenance", JSON, nullable=False, server_default="[]"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_funnel_stages_strategy", "funnel_stages", ["funnel_strategy_id"])
    op.create_index(
        "ix_funnel_stages_business_stage", "funnel_stages", ["business_id", "stage"]
    )
    op.create_table(
        "funnel_stage_channels",
        *_tenant(),
        sa.Column(
            "funnel_stage_id",
            sa.Uuid(),
            sa.ForeignKey("funnel_stages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Numeric(5, 4), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("integration_connection_id", sa.Uuid(), nullable=True),
        sa.Column("evidence_refs", JSON, nullable=False, server_default="[]"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_funnel_stage_channels_stage", "funnel_stage_channels", ["funnel_stage_id"])
    op.create_index(
        "ix_funnel_stage_channels_business_channel",
        "funnel_stage_channels",
        ["business_id", "channel"],
    )
    op.create_table(
        "funnel_stage_kpis",
        *_tenant(),
        sa.Column(
            "funnel_stage_id",
            sa.Uuid(),
            sa.ForeignKey("funnel_stages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kpi_code", sa.String(50), nullable=False),
        sa.Column("kpi_kind", sa.String(20), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("metric_code", sa.String(50), nullable=True),
        sa.Column("value_ref", JSON, nullable=True),
        sa.Column("threshold_code", sa.String(50), nullable=True),
        sa.Column("details", JSON, nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_funnel_stage_kpis_stage", "funnel_stage_kpis", ["funnel_stage_id"])
    op.create_index(
        "ix_funnel_stage_kpis_business_kpi", "funnel_stage_kpis", ["business_id", "kpi_code"]
    )
    op.create_table(
        "funnel_gaps",
        *_tenant(),
        sa.Column(
            "funnel_strategy_id",
            sa.Uuid(),
            sa.ForeignKey("funnel_strategies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("gap_type", sa.String(30), nullable=False),
        sa.Column("stage_from", sa.String(20), nullable=True),
        sa.Column("stage_to", sa.String(20), nullable=True),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence", JSON, nullable=False, server_default="[]"),
        sa.Column("recommended_direction", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_funnel_gaps_strategy", "funnel_gaps", ["funnel_strategy_id"])
    op.create_index(
        "ix_funnel_gaps_business_severity", "funnel_gaps", ["business_id", "severity"]
    )


def downgrade() -> None:
    op.drop_index("ix_funnel_gaps_business_severity", table_name="funnel_gaps")
    op.drop_index("ix_funnel_gaps_strategy", table_name="funnel_gaps")
    op.drop_table("funnel_gaps")
    op.drop_index("ix_funnel_stage_kpis_business_kpi", table_name="funnel_stage_kpis")
    op.drop_index("ix_funnel_stage_kpis_stage", table_name="funnel_stage_kpis")
    op.drop_table("funnel_stage_kpis")
    op.drop_index("ix_funnel_stage_channels_business_channel", table_name="funnel_stage_channels")
    op.drop_index("ix_funnel_stage_channels_stage", table_name="funnel_stage_channels")
    op.drop_table("funnel_stage_channels")
    op.drop_index("ix_funnel_stages_business_stage", table_name="funnel_stages")
    op.drop_index("ix_funnel_stages_strategy", table_name="funnel_stages")
    op.drop_table("funnel_stages")
    op.drop_index("ix_funnel_strategies_business_version", table_name="funnel_strategies")
    op.drop_index("ix_funnel_strategies_business_created", table_name="funnel_strategies")
    op.drop_table("funnel_strategies")