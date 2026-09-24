"""add the superadmin role

Revision ID: 20260913_04
Revises: 20260912_03
Create Date: 2026-09-13 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "20260913_04"
down_revision = "20260912_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_superadmin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "is_superadmin")
