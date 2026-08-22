"""Creative strategy and testing matrix (Phase 8B).

Creates the 8 creative strategy/testing tables matching the ORM models in
``src/db/models/creative.py``:

- creative_strategies
- creative_tests
- creative_test_variants
- creative_portfolios
- creative_coverage
- creative_diversity
- creative_concept_portfolios
- creative_strategy_snapshots

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-20
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "creative_strategies",
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
        sa.Column("strategy_id", sa.String(80), nullable=False),
        sa.Column("version", sa.String(30), nullable=False, server_default="v1"),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column(
            "positioning_reference",
            sa.Uuid(),
            sa.ForeignKey("positioning_strategies.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "offer_reference",
            sa.Uuid(),
            sa.ForeignKey("offer_candidates.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "messaging_reference",
            sa.Uuid(),
            sa.ForeignKey("messaging_strategies.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "funnel_reference",
            sa.Uuid(),
            sa.ForeignKey("funnel_strategies.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "research_reference",
            sa.Uuid(),
            sa.ForeignKey("research_projects.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "strategy_decision_reference",
            sa.Uuid(),
            sa.ForeignKey("strategy_decisions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "creative_intelligence_reference",
            sa.Uuid(),
            sa.ForeignKey("creative_concepts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("audience_coverage", sa.String(30), nullable=True),
        sa.Column("funnel_coverage", sa.String(30), nullable=True),
        sa.Column("rules_version", sa.String(40), nullable=True),
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
        sa.UniqueConstraint("strategy_id", name="uq_creative_strategies_strategy_id"),
    )
    op.create_index(
        "ix_creative_strategies_business_created",
        "creative_strategies",
        ["business_id", "created_at"],
    )

    op.create_table(
        "creative_tests",
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
        sa.Column("test_id", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("objective", sa.String(50), nullable=False),
        sa.Column("test_variable", sa.String(50), nullable=False),
        sa.Column("control_variables", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("variants", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("based_on", sa.Text(), nullable=True),
        sa.Column("success_metric", sa.String(50), nullable=True),
        sa.Column("minimum_data_requirement", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
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
        sa.UniqueConstraint("test_id", name="uq_creative_tests_test_id"),
    )
    op.create_index(
        "ix_creative_tests_business_created",
        "creative_tests",
        ["business_id", "created_at"],
    )

    op.create_table(
        "creative_test_variants",
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
        sa.Column("test_id", sa.String(80), nullable=False),
        sa.Column("variant_id", sa.String(80), nullable=False),
        sa.Column("test_variable_value", sa.Text(), nullable=False),
        sa.Column(
            "control_state_frozen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
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
        "ix_creative_test_variants_test_id", "creative_test_variants", ["test_id"]
    )
    op.create_index(
        "ix_creative_test_variants_business_created",
        "creative_test_variants",
        ["business_id", "created_at"],
    )

    op.create_table(
        "creative_portfolios",
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
        sa.Column("portfolio_id", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
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
        sa.UniqueConstraint("portfolio_id", name="uq_creative_portfolios_portfolio_id"),
    )
    op.create_index(
        "ix_creative_portfolios_business_created",
        "creative_portfolios",
        ["business_id", "created_at"],
    )

    op.create_table(
        "creative_coverage",
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
        sa.Column("coverage_type", sa.String(50), nullable=False),
        sa.Column("dimension", sa.String(50), nullable=False),
        sa.Column("value", sa.String(100), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="available"),
        sa.Column(
            "evidence_ref",
            sa.Uuid(),
            sa.ForeignKey("creative_evidence.id", ondelete="RESTRICT"),
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
    )
    op.create_index(
        "ix_creative_coverage_business_created",
        "creative_coverage",
        ["business_id", "created_at"],
    )
    op.create_index(
        "ix_creative_coverage_business_type",
        "creative_coverage",
        ["business_id", "coverage_type"],
    )

    op.create_table(
        "creative_diversity",
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
        sa.Column("risk_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(30), nullable=False),
        sa.Column("related_concept_id", sa.Uuid(), nullable=True),
        sa.Column(
            "resolved", sa.Boolean(), nullable=False, server_default=sa.false()
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
        "ix_creative_diversity_business_created",
        "creative_diversity",
        ["business_id", "created_at"],
    )
    op.create_index(
        "ix_creative_diversity_business_type",
        "creative_diversity",
        ["business_id", "risk_type"],
    )

    op.create_table(
        "creative_concept_portfolios",
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
        sa.Column(
            "creative_concept_id",
            sa.Uuid(),
            sa.ForeignKey("creative_concepts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "portfolio_id",
            sa.Uuid(),
            sa.ForeignKey("creative_portfolios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(30), nullable=True),
        sa.Column(
            "evidence_ref",
            sa.Uuid(),
            sa.ForeignKey("creative_evidence.id", ondelete="RESTRICT"),
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
        "ix_creative_concept_portfolios_concept_id",
        "creative_concept_portfolios",
        ["creative_concept_id"],
    )
    op.create_index(
        "ix_creative_concept_portfolios_business_created",
        "creative_concept_portfolios",
        ["business_id", "created_at"],
    )

    op.create_table(
        "creative_strategy_snapshots",
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
        sa.Column("strategy_id", sa.String(80), nullable=False),
        sa.Column("creative_intelligence_version", sa.String(40), nullable=True),
        sa.Column("positioning_version", sa.String(40), nullable=True),
        sa.Column("offer_version", sa.String(40), nullable=True),
        sa.Column("strategy_decision_version", sa.String(40), nullable=True),
        sa.Column("messaging_version", sa.String(40), nullable=True),
        sa.Column("funnel_version", sa.String(40), nullable=True),
        sa.Column("research_version", sa.String(40), nullable=True),
        sa.Column("creative_strategy_version", sa.String(40), nullable=True),
        sa.Column("input_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("output_summary", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_creative_strategy_snapshots_business_created",
        "creative_strategy_snapshots",
        ["business_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_creative_strategy_snapshots_business_created",
        table_name="creative_strategy_snapshots",
    )
    op.drop_table("creative_strategy_snapshots")
    op.drop_index(
        "ix_creative_concept_portfolios_business_created",
        table_name="creative_concept_portfolios",
    )
    op.drop_index(
        "ix_creative_concept_portfolios_concept_id",
        table_name="creative_concept_portfolios",
    )
    op.drop_table("creative_concept_portfolios")
    op.drop_index(
        "ix_creative_diversity_business_type", table_name="creative_diversity"
    )
    op.drop_index(
        "ix_creative_diversity_business_created", table_name="creative_diversity"
    )
    op.drop_table("creative_diversity")
    op.drop_index(
        "ix_creative_coverage_business_type", table_name="creative_coverage"
    )
    op.drop_index(
        "ix_creative_coverage_business_created", table_name="creative_coverage"
    )
    op.drop_table("creative_coverage")
    op.drop_index(
        "ix_creative_portfolios_business_created", table_name="creative_portfolios"
    )
    op.drop_table("creative_portfolios")
    op.drop_index(
        "ix_creative_test_variants_business_created", table_name="creative_test_variants"
    )
    op.drop_index(
        "ix_creative_test_variants_test_id", table_name="creative_test_variants"
    )
    op.drop_table("creative_test_variants")
    op.drop_index(
        "ix_creative_tests_business_created", table_name="creative_tests"
    )
    op.drop_table("creative_tests")
    op.drop_index(
        "ix_creative_strategies_business_created", table_name="creative_strategies"
    )
    op.drop_table("creative_strategies")
