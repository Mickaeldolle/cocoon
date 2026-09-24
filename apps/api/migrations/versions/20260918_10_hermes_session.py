"""store the private Hermes session bound to an assistant thread

Revision ID: 20260918_10
Revises: 20260918_09
"""

import sqlalchemy as sa
from alembic import op

revision = "20260918_10"
down_revision = "20260918_09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assistant_threads", sa.Column("hermes_session_id", sa.String(128), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("assistant_threads", "hermes_session_id")
