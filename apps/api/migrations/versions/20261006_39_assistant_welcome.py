"""Persist assistant name and first welcome completion per account.

Revision ID: 20261006_39
Revises: 20261002_38
"""

import sqlalchemy as sa
from alembic import op

revision = "20261006_39"
down_revision = "20261002_38"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("assistant_name", sa.String(40), nullable=True))
    op.add_column("users", sa.Column("welcome_completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "welcome_completed_at")
    op.drop_column("users", "assistant_name")
