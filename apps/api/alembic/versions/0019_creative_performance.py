"""Creative performance intelligence (Phase 8C).

Creates the two persistence tables of the deterministic creative
performance layer:

- creative_performance_links
  Explicit user-authored attribution between internal creative entities
  and provider advertising objects. Never inferred by the engine.

- creative_performance_snapshots
  Immutable audit snapshots of computed performance reports.

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-22
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "creative_performance_links",
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
            nullable=True,
        ),
        sa.Column(
            "creative_test_variant_id",
            sa.Uuid(),
            sa.ForeignKey("creative_test_variants.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "ad_id",
            sa.Uuid(),
            sa.ForeignKey("ads.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "provider_creative_id",
            sa.Uuid(),
            sa.ForeignKey("creatives.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("label", sa.String(200), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
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
        sa.CheckConstraint(
            "(creative_concept_id IS NOT NULL)::int"
            " + (creative_test_variant_id IS NOT NULL)::int"
            " = 1",
            name="ck_links_exactly_one_internal_target",
        ),
        sa.CheckConstraint(
            "(ad_id IS NOT NULL)::int + (provider_creative_id IS NOT NULL)::int = 1",
            name="ck_links_exactly_one_provider_target",
        ),
    )
    op.create_index(
        "uq_creative_performance_links_mapping",
        "creative_performance_links",
        [
            "business_id",
            sa.text("COALESCE(creative_concept_id::text, '')"),
            sa.text("COALESCE(creative_test_variant_id::text, '')"),
            sa.text("COALESCE(ad_id::text, '')"),
            sa.text("COALESCE(provider_creative_id::text, '')"),
        ],
        unique=True,
    )
    op.create_index(
        "ix_creative_performance_links_business_created",
        "creative_performance_links",
        ["business_id", "created_at"],
    )
    op.create_index(
        "ix_creative_performance_links_concept",
        "creative_performance_links",
        ["creative_concept_id"],
    )
    op.create_index(
        "ix_creative_performance_links_variant",
        "creative_performance_links",
        ["creative_test_variant_id"],
    )
    op.create_index(
        "ix_creative_performance_links_ad",
        "creative_performance_links",
        ["ad_id"],
    )
    op.create_index(
        "ix_creative_performance_links_provider_creative",
        "creative_performance_links",
        ["provider_creative_id"],
    )

    op.create_table(
        "creative_performance_snapshots",
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
        sa.Column("entity_scope", sa.String(20), nullable=False, server_default="all"),
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
        "uq_creative_performance_snapshots_fingerprint",
        "creative_performance_snapshots",
        ["business_id", "fingerprint"],
        unique=True,
    )
    op.create_index(
        "ix_creative_performance_snapshots_business_created",
        "creative_performance_snapshots",
        ["business_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_creative_performance_snapshots_business_created",
        table_name="creative_performance_snapshots",
    )
    op.drop_index(
        "uq_creative_performance_snapshots_fingerprint",
        table_name="creative_performance_snapshots",
    )
    op.drop_table("creative_performance_snapshots")
    op.drop_index(
        "ix_creative_performance_links_provider_creative",
        table_name="creative_performance_links",
    )
    op.drop_index(
        "ix_creative_performance_links_ad", table_name="creative_performance_links"
    )
    op.drop_index(
        "ix_creative_performance_links_variant", table_name="creative_performance_links"
    )
    op.drop_index(
        "ix_creative_performance_links_concept", table_name="creative_performance_links"
    )
    op.drop_index(
        "ix_creative_performance_links_business_created",
        table_name="creative_performance_links",
    )
    op.drop_index(
        "uq_creative_performance_links_mapping", table_name="creative_performance_links"
    )
    op.drop_table("creative_performance_links")
