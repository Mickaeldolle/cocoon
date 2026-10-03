"""Add secret-message debounce and browser push subscriptions.

Revision ID: 20261002_38
Revises: 20261002_37
"""

import sqlalchemy as sa
from alembic import op

revision = "20261002_38"
down_revision = "20261002_37"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "secret_notification_debounce",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_secret_notification_debounce_due_at", "secret_notification_debounce", ["due_at"])
    op.create_table(
        "web_push_subscriptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.Uuid(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("endpoint", sa.String(2048), nullable=False, unique=True),
        sa.Column("p256dh", sa.String(256), nullable=False),
        sa.Column("auth", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_web_push_subscriptions_user_id", "web_push_subscriptions", ["user_id"])
    op.create_index("ix_web_push_subscriptions_device_id", "web_push_subscriptions", ["device_id"])


def downgrade() -> None:
    op.drop_table("web_push_subscriptions")
    op.drop_table("secret_notification_debounce")
