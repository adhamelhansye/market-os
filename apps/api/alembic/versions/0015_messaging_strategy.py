"""add deterministic messaging strategy records.

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
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
        "messaging_strategies",
        *_tenant(),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("messaging_version", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("positioning_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("offer_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("strategy_decision_id", sa.Uuid(), nullable=True),
        sa.Column("input_snapshot", JSON, nullable=False, server_default="{}"),
        sa.Column("core_message", JSON, nullable=False, server_default="{}"),
        sa.Column("quality", JSON, nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_messaging_strategies_business_created",
        "messaging_strategies",
        ["business_id", "created_at"],
    )
    op.create_index(
        "ix_messaging_strategies_business_version",
        "messaging_strategies",
        ["business_id", "version"],
    )
    op.create_table(
        "message_components",
        *_tenant(),
        sa.Column(
            "messaging_strategy_id",
            sa.Uuid(),
            sa.ForeignKey("messaging_strategies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("component_type", sa.String(30), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("classification", sa.String(40), nullable=False),
        sa.Column("strength", sa.String(20), nullable=False),
        sa.Column("claim_status", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="available"),
        sa.Column("funnel_stage", sa.String(20), nullable=True),
        sa.Column("details", JSON, nullable=False, server_default="{}"),
        sa.Column("evidence_refs", JSON, nullable=False, server_default="[]"),
        sa.Column("provenance", JSON, nullable=False, server_default="[]"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_message_components_strategy", "message_components", ["messaging_strategy_id"]
    )
    op.create_index(
        "ix_message_components_business_type",
        "message_components",
        ["business_id", "component_type"],
    )
    op.create_table(
        "message_angles",
        *_tenant(),
        sa.Column(
            "messaging_strategy_id",
            sa.Uuid(),
            sa.ForeignKey("messaging_strategies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("angle_type", sa.String(30), nullable=False),
        sa.Column("core_message", sa.Text(), nullable=False),
        sa.Column("hook_direction", sa.Text(), nullable=False),
        sa.Column("supporting_points", JSON, nullable=False, server_default="[]"),
        sa.Column("cta_type", sa.String(30), nullable=True),
        sa.Column("funnel_stage", sa.String(20), nullable=False),
        sa.Column("strength", sa.String(20), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("evidence_refs", JSON, nullable=False, server_default="[]"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_message_angles_strategy", "message_angles", ["messaging_strategy_id"])
    op.create_index(
        "ix_message_angles_business_type", "message_angles", ["business_id", "angle_type"]
    )


def downgrade() -> None:
    op.drop_index("ix_message_angles_business_type", table_name="message_angles")
    op.drop_index("ix_message_angles_strategy", table_name="message_angles")
    op.drop_table("message_angles")
    op.drop_index("ix_message_components_business_type", table_name="message_components")
    op.drop_index("ix_message_components_strategy", table_name="message_components")
    op.drop_table("message_components")
    op.drop_index("ix_messaging_strategies_business_version", table_name="messaging_strategies")
    op.drop_index("ix_messaging_strategies_business_created", table_name="messaging_strategies")
    op.drop_table("messaging_strategies")
