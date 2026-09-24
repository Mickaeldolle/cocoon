"""Add capture run provenance to durable memories."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260922_28"
down_revision: str | None = "20260922_27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("memory_items", sa.Column("source_run_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_memory_items_source_run_id",
        "memory_items",
        "capture_runs",
        ["source_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_memory_items_source_run_id", "memory_items", ["source_run_id"])


def downgrade() -> None:
    op.drop_index("ix_memory_items_source_run_id", table_name="memory_items")
    op.drop_constraint("fk_memory_items_source_run_id", "memory_items", type_="foreignkey")
    op.drop_column("memory_items", "source_run_id")
