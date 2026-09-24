"""add reminder modification and notification quota controls

Revision ID: 20260922_17
Revises: 20260922_16
"""

import sqlalchemy as sa
from alembic import op

revision = "20260922_17"
down_revision = "20260922_16"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recurring_reminders", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.add_column("assistant_preferences", sa.Column("daily_notification_quota", sa.Integer(), server_default="20", nullable=False))
    op.add_column("notification_outbox", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_notification_outbox_cancelled_at", "notification_outbox", ["cancelled_at"])


def downgrade() -> None:
    op.drop_index("ix_notification_outbox_cancelled_at", table_name="notification_outbox")
    op.drop_column("notification_outbox", "cancelled_at")
    op.drop_column("assistant_preferences", "daily_notification_quota")
    op.drop_column("recurring_reminders", "updated_at")
