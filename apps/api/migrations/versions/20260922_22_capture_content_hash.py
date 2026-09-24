"""store a verifiable hash for raw captures

Revision ID: 20260922_22
Revises: 20260922_21
"""

import sqlalchemy as sa
from alembic import op

revision = "20260922_22"
down_revision = "20260922_21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("captures", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_captures_content_hash", "captures", ["content_hash"])


def downgrade() -> None:
    op.drop_index("ix_captures_content_hash", table_name="captures")
    op.drop_column("captures", "content_hash")
