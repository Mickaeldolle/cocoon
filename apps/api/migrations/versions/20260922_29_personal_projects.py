"""Add owner-scoped personal projects for assistant context."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260922_29"
down_revision: str | None = "20260922_28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "personal_projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_personal_projects_user_id", "personal_projects", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_personal_projects_user_id", table_name="personal_projects")
    op.drop_table("personal_projects")
