"""add structured memory metadata

Revision ID: 20260922_14
Revises: 20260922_13
"""

import sqlalchemy as sa
from alembic import op

revision = "20260922_14"
down_revision = "20260922_13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "memory_items",
        sa.Column("layer", sa.String(length=16), nullable=False, server_default="episodic"),
    )
    op.add_column(
        "memory_items",
        sa.Column("memory_type", sa.String(length=16), nullable=False, server_default="fact"),
    )
    op.add_column(
        "memory_items",
        sa.Column("owner_type", sa.String(length=24), nullable=False, server_default="user"),
    )
    op.add_column(
        "memory_items",
        sa.Column("scope_type", sa.String(length=24), nullable=False, server_default="personal"),
    )
    op.add_column("memory_items", sa.Column("scope_id", sa.Uuid(), nullable=True))
    op.add_column(
        "memory_items",
        sa.Column("source_type", sa.String(length=32), nullable=False, server_default="capture"),
    )
    op.add_column("memory_items", sa.Column("source_message_id", sa.Uuid(), nullable=True))
    op.add_column("memory_items", sa.Column("supersedes_id", sa.Uuid(), nullable=True))
    op.add_column("memory_items", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_memory_items_source_message_id", "memory_items", ["source_message_id"])
    op.create_index("ix_memory_items_supersedes_id", "memory_items", ["supersedes_id"])
    op.create_foreign_key(
        "fk_memory_items_supersedes_id",
        "memory_items",
        "memory_items",
        ["supersedes_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_memory_items_supersedes_id", "memory_items", type_="foreignkey")
    op.drop_index("ix_memory_items_supersedes_id", table_name="memory_items")
    op.drop_index("ix_memory_items_source_message_id", table_name="memory_items")
    for column in (
        "deleted_at",
        "supersedes_id",
        "source_message_id",
        "source_type",
        "scope_id",
        "scope_type",
        "owner_type",
        "memory_type",
        "layer",
    ):
        op.drop_column("memory_items", column)
