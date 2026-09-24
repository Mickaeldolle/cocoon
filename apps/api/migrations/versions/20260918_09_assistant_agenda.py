"""add private assistant calendar and recurring reminders

Revision ID: 20260918_09
Revises: 20260917_10
"""

import sqlalchemy as sa
from alembic import op

revision = "20260918_09"
down_revision = "20260917_10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("external_event_id", sa.String(255)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_calendar_events_user_id", "calendar_events", ["user_id"])
    op.create_index("ix_calendar_events_starts_at", "calendar_events", ["starts_at"])
    op.create_index("ix_calendar_events_ends_at", "calendar_events", ["ends_at"])
    op.create_table(
        "recurring_reminders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("anchor_date", sa.Date(), nullable=False),
        sa.Column("recurrence_months", sa.Integer(), nullable=False),
        sa.Column("lead_days", sa.Integer(), nullable=False),
        sa.Column("next_due_date", sa.Date(), nullable=False),
        sa.Column("next_reminder_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_recurring_reminders_user_id", "recurring_reminders", ["user_id"])
    op.create_index(
        "ix_recurring_reminders_next_due_date", "recurring_reminders", ["next_due_date"]
    )
    op.create_index(
        "ix_recurring_reminders_next_reminder_at", "recurring_reminders", ["next_reminder_at"]
    )


def downgrade() -> None:
    op.drop_table("recurring_reminders")
    op.drop_table("calendar_events")
