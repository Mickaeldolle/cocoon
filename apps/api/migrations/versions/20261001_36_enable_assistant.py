"""Disable assistant access by default for every account.

Revision ID: 20261001_36
Revises: 20261001_35
"""

import sqlalchemy as sa
from alembic import op

revision = "20261001_36"
down_revision = "20261001_35"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("enable_assistant", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "enable_assistant")
