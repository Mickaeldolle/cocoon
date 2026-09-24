"""add notification delivery leases and bounded retry state

Revision ID: 20260922_16
Revises: 20260922_15
"""

import sqlalchemy as sa
from alembic import op

revision = "20260922_16"
down_revision = "20260922_15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notification_outbox", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("notification_outbox", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"))
    op.add_column("notification_outbox", sa.Column("lease_owner", sa.String(length=128), nullable=True))
    op.add_column("notification_outbox", sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("notification_outbox", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("notification_outbox", sa.Column("last_error_code", sa.String(length=64), nullable=True))
    op.add_column("notification_outbox", sa.Column("provider_ticket", sa.JSON(), nullable=True))
    op.add_column(
        "notification_outbox",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_notification_outbox_lease_until", "notification_outbox", ["lease_until"])
    op.create_index("ix_notification_outbox_next_attempt_at", "notification_outbox", ["next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_notification_outbox_next_attempt_at", table_name="notification_outbox")
    op.drop_index("ix_notification_outbox_lease_until", table_name="notification_outbox")
    for column in (
        "updated_at", "provider_ticket", "last_error_code", "next_attempt_at",
        "lease_until", "lease_owner", "max_attempts", "attempts",
    ):
        op.drop_column("notification_outbox", column)
