"""add durable capture runs and events

Revision ID: 20260921_12
Revises: 20260921_11
"""

import sqlalchemy as sa
from alembic import op

revision = "20260921_12"
down_revision = "20260921_11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "capture_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("capture_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["capture_id"], ["captures.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("capture_id"),
    )
    op.create_index("ix_capture_runs_user_id", "capture_runs", ["user_id"])
    op.create_index("ix_capture_runs_capture_id", "capture_runs", ["capture_id"])
    op.create_table(
        "capture_run_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["capture_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "sequence", name="uq_capture_run_event_sequence"),
    )
    op.create_index("ix_capture_run_events_run_id", "capture_run_events", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_capture_run_events_run_id", table_name="capture_run_events")
    op.drop_table("capture_run_events")
    op.drop_index("ix_capture_runs_capture_id", table_name="capture_runs")
    op.drop_index("ix_capture_runs_user_id", table_name="capture_runs")
    op.drop_table("capture_runs")
