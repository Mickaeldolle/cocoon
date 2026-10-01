"""Store minimal access and action audit events.

Revision ID: 20261001_34
Revises: 20260930_33
"""

import sqlalchemy as sa
from alembic import op

revision = "20261001_34"
down_revision = "20260930_33"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("method", sa.String(8), nullable=False),
        sa.Column("route", sa.String(180), nullable=True),
        sa.Column("status_code", sa.SmallInteger(), nullable=False),
    )
    op.create_index("ix_audit_events_actor_time", "audit_events", ["actor_user_id", "occurred_at"])
    op.create_index("ix_audit_events_time", "audit_events", ["occurred_at"])


def downgrade() -> None:
    op.drop_table("audit_events")
