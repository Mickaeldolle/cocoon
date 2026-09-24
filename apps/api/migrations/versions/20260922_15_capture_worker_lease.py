"""add capture worker queue and leases

Revision ID: 20260922_15
Revises: 20260922_14
"""

import sqlalchemy as sa
from alembic import op

revision = "20260922_15"
down_revision = "20260922_14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "capture_runs",
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
    )
    op.add_column("capture_runs", sa.Column("lease_owner", sa.String(length=128), nullable=True))
    op.add_column("capture_runs", sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "capture_runs",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.add_column("capture_runs", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_capture_runs_lease_until", "capture_runs", ["lease_until"])


def downgrade() -> None:
    op.drop_index("ix_capture_runs_lease_until", table_name="capture_runs")
    for column in ("cancelled_at", "updated_at", "lease_until", "lease_owner", "max_attempts"):
        op.drop_column("capture_runs", column)
