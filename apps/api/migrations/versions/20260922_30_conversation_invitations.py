"""conversation invitation statuses

Revision ID: 20260922_30
Revises: 20260922_29
"""

import sqlalchemy as sa
from alembic import op

revision = "20260922_30"
down_revision = "20260922_29"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_members",
        sa.Column("status", sa.String(16), nullable=False, server_default="accepted"),
    )


def downgrade() -> None:
    op.drop_column("conversation_members", "status")
