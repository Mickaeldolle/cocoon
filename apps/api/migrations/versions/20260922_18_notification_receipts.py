"""track provider acceptance and user notification reads

Revision ID: 20260922_18
Revises: 20260922_17
"""

import sqlalchemy as sa
from alembic import op

revision = "20260922_18"
down_revision = "20260922_17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notification_outbox", sa.Column("provider_status", sa.String(length=24), server_default="pending", nullable=False))
    op.add_column("notification_outbox", sa.Column("provider_receipt", sa.JSON(), nullable=True))
    op.add_column("notification_outbox", sa.Column("read_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_notification_outbox_provider_status", "notification_outbox", ["provider_status"])
    op.create_index("ix_notification_outbox_read_at", "notification_outbox", ["read_at"])


def downgrade() -> None:
    op.drop_index("ix_notification_outbox_read_at", table_name="notification_outbox")
    op.drop_index("ix_notification_outbox_provider_status", table_name="notification_outbox")
    op.drop_column("notification_outbox", "read_at")
    op.drop_column("notification_outbox", "provider_receipt")
    op.drop_column("notification_outbox", "provider_status")
