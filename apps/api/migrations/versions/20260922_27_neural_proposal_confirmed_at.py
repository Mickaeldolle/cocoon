"""Add confirmation timestamp to capture proposals."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260922_27"
down_revision: str | None = "20260922_26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "neural_proposals",
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("neural_proposals", "confirmed_at")
