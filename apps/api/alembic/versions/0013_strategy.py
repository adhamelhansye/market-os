"""deterministic positioning and offer strategy foundation.

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = postgresql.JSONB(astext_type=sa.Text())


def _tenant_columns() -> list[sa.Column]:
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
        "strategy_snapshots",
        *_tenant_columns(),
        sa.Column("strategy_kind", sa.String(20), nullable=False),
        sa.Column("strategy_version", sa.String(40), nullable=False),
        sa.Column("research_intelligence_version", sa.String(40), nullable=True),
        sa.Column("input_snapshot_refs", JSON, nullable=False, server_default="{}"),
        sa.Column("coverage_json", JSON, nullable=False, server_default="{}"),
        sa.Column("missing_research_areas", JSON, nullable=False, server_default="[]"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_strategy_snapshots_business_created",
        "strategy_snapshots",
        ["business_id", "created_at"],
    )
    op.create_index(
        "ix_strategy_snapshots_business_kind",
        "strategy_snapshots",
        ["business_id", "strategy_kind"],
    )

    op.create_table(
        "positioning_strategies",
        *_tenant_columns(),
        sa.Column(
            "snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("strategy_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("strategy_version", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("selected_candidate_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_positioning_strategies_business_version",
        "positioning_strategies",
        ["business_id", "version"],
    )

    op.create_table(
        "positioning_candidates",
        *_tenant_columns(),
        sa.Column(
            "positioning_strategy_id",
            sa.Uuid(),
            sa.ForeignKey("positioning_strategies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("candidate_type", sa.String(30), nullable=False),
        sa.Column("target_customer", sa.Text(), nullable=True),
        sa.Column("problem", sa.Text(), nullable=True),
        sa.Column("solution", sa.Text(), nullable=True),
        sa.Column("differentiator", sa.Text(), nullable=True),
        sa.Column("promise", sa.Text(), nullable=True),
        sa.Column("supporting_benefits", JSON, nullable=False, server_default="[]"),
        sa.Column("proof_points", JSON, nullable=False, server_default="[]"),
        sa.Column("objections_addressed", JSON, nullable=False, server_default="[]"),
        sa.Column("positioning_statement", sa.Text(), nullable=True),
        sa.Column("classification", sa.String(20), nullable=False, server_default="hypothesis"),
        sa.Column("strength", sa.String(20), nullable=False, server_default="insufficient"),
        sa.Column("score", sa.Numeric(6, 4), nullable=True),
        sa.Column("score_breakdown", JSON, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("assumptions", JSON, nullable=False, server_default="[]"),
        sa.Column("risks", JSON, nullable=False, server_default="[]"),
        sa.Column("provenance", JSON, nullable=False, server_default="[]"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_positioning_candidates_business_created",
        "positioning_candidates",
        ["business_id", "created_at"],
    )
    op.create_index(
        "ix_positioning_candidates_strategy", "positioning_candidates", ["positioning_strategy_id"]
    )

    op.create_table(
        "offer_strategies",
        *_tenant_columns(),
        sa.Column(
            "snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("strategy_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("strategy_version", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("selected_candidate_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_offer_strategies_business_version", "offer_strategies", ["business_id", "version"]
    )

    op.create_table(
        "offer_candidates",
        *_tenant_columns(),
        sa.Column(
            "offer_strategy_id",
            sa.Uuid(),
            sa.ForeignKey("offer_strategies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.Uuid(),
            sa.ForeignKey("products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "bundle_id", sa.Uuid(), sa.ForeignKey("bundles.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("components", JSON, nullable=False, server_default="{}"),
        sa.Column("economics", JSON, nullable=False, server_default="{}"),
        sa.Column("classification", sa.String(20), nullable=False, server_default="hypothesis"),
        sa.Column("strength", sa.String(20), nullable=False, server_default="insufficient"),
        sa.Column("score", sa.Numeric(6, 4), nullable=True),
        sa.Column("score_breakdown", JSON, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("assumptions", JSON, nullable=False, server_default="[]"),
        sa.Column("risks", JSON, nullable=False, server_default="[]"),
        sa.Column("provenance", JSON, nullable=False, server_default="[]"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_offer_candidates_business_created", "offer_candidates", ["business_id", "created_at"]
    )
    op.create_index("ix_offer_candidates_strategy", "offer_candidates", ["offer_strategy_id"])
    op.create_index("ix_offer_candidates_product", "offer_candidates", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_offer_candidates_product", table_name="offer_candidates")
    op.drop_index("ix_offer_candidates_strategy", table_name="offer_candidates")
    op.drop_index("ix_offer_candidates_business_created", table_name="offer_candidates")
    op.drop_table("offer_candidates")
    op.drop_index("ix_offer_strategies_business_version", table_name="offer_strategies")
    op.drop_table("offer_strategies")
    op.drop_index("ix_positioning_candidates_strategy", table_name="positioning_candidates")
    op.drop_index("ix_positioning_candidates_business_created", table_name="positioning_candidates")
    op.drop_table("positioning_candidates")
    op.drop_index("ix_positioning_strategies_business_version", table_name="positioning_strategies")
    op.drop_table("positioning_strategies")
    op.drop_index("ix_strategy_snapshots_business_kind", table_name="strategy_snapshots")
    op.drop_index("ix_strategy_snapshots_business_created", table_name="strategy_snapshots")
    op.drop_table("strategy_snapshots")
