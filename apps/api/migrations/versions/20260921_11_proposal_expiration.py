"""add explicit expiration to assistant proposals

Revision ID: 20260921_11
Revises: 20260918_10
"""

import sqlalchemy as sa
from alembic import op

revision = "20260921_11"
down_revision = "20260918_10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assistant_proposals",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "neural_proposals",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("neural_proposals", "expires_at")
    op.drop_column("assistant_proposals", "expires_at")
