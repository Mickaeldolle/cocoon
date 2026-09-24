"""add registered device tokens and the durable reminder outbox

Revision ID: 20260915_07
Revises: 20260915_06
Create Date: 2026-09-15 02:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "20260915_07"
down_revision = "20260915_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("push_token", sa.String(length=256), nullable=True))
    op.create_unique_constraint("uq_devices_push_token", "devices", ["push_token"])
    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("body", sa.String(length=240), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_notification_outbox_dedupe"),
    )
    op.create_index("ix_notification_outbox_user_id", "notification_outbox", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_notification_outbox_user_id", table_name="notification_outbox")
    op.drop_table("notification_outbox")
    op.drop_constraint("uq_devices_push_token", "devices", type_="unique")
    op.drop_column("devices", "push_token")
