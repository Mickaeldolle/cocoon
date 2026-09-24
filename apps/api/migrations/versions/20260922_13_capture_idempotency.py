"""add capture run idempotency key

Revision ID: 20260922_13
Revises: 20260921_12
"""

import sqlalchemy as sa
from alembic import op

revision = "20260922_13"
down_revision = "20260921_12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "capture_runs",
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "uq_capture_run_user_idempotency_key",
        "capture_runs",
        ["user_id", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_capture_run_user_idempotency_key", table_name="capture_runs")
    op.drop_column("capture_runs", "idempotency_key")
