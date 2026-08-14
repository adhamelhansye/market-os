"""align roles.organization_id delete behavior with the ORM model

The model declares ondelete="CASCADE"; migration 0001 created the FK
without cascade (NO ACTION). Recreate the constraint so deleting an
organization also deletes its org-scoped roles, matching the model.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-13
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT_NAME = "fk_roles_organizations_organization_id"


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, "roles", type_="foreignkey")
    op.create_foreign_key(
        CONSTRAINT_NAME,
        "roles",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, "roles", type_="foreignkey")
    op.create_foreign_key(
        CONSTRAINT_NAME,
        "roles",
        "organizations",
        ["organization_id"],
        ["id"],
    )