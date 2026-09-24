"""persist assistant turn idempotency keys

Revision ID: 20260922_21
Revises: 20260922_20
"""

import sqlalchemy as sa
from alembic import op

revision = "20260922_21"
down_revision = "20260922_20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assistant_messages",
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_assistant_messages_idempotency_key",
        "assistant_messages",
        ["idempotency_key"],
    )
    op.create_index(
        "uq_assistant_messages_thread_idempotency",
        "assistant_messages",
        ["thread_id", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_assistant_messages_thread_idempotency", table_name="assistant_messages")
    op.drop_index("ix_assistant_messages_idempotency_key", table_name="assistant_messages")
    op.drop_column("assistant_messages", "idempotency_key")
