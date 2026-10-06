"""Source-backed personal memory, durable index leases and forgetting exclusions.

Revision ID: 20261006_39
Revises: 20261002_38
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261006_39"
down_revision = "20261002_38"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assistant_messages", sa.Column("source_user_message_id", sa.Uuid(), nullable=True)
    )
    op.create_index(
        "ix_assistant_messages_source_user_message_id",
        "assistant_messages",
        ["source_user_message_id"],
    )
    for name, length in (("entity", 160), ("attribute", 80), ("value", 240), ("origin", 16)):
        op.add_column("memory_items", sa.Column(name, sa.String(length), nullable=True))
    json_type = sa.JSON().with_variant(JSONB, "postgresql")
    op.add_column("assistant_messages", sa.Column("working_choices", json_type, nullable=True))
    op.create_table(
        "memory_embeddings",
        sa.Column(
            "memory_id",
            sa.Uuid(),
            sa.ForeignKey("memory_items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("vector", json_type, nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(80), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(32), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_memory_embeddings_status", "memory_embeddings", ["status"])
    op.create_table(
        "memory_exclusions",
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("source_type", sa.String(24), primary_key=True),
        sa.Column("source_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "working_memories",
        sa.Column(
            "thread_id",
            sa.Uuid(),
            sa.ForeignKey("assistant_threads.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("entries", json_type, nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_working_memories_user_id", "working_memories", ["user_id"])
    op.create_table(
        "memory_usages",
        sa.Column(
            "message_id",
            sa.Uuid(),
            sa.ForeignKey("assistant_messages.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "memory_id",
            sa.Uuid(),
            sa.ForeignKey("memory_items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "context_dependencies",
        sa.Column(
            "message_id",
            sa.Uuid(),
            sa.ForeignKey("assistant_messages.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "source_message_id",
            sa.Uuid(),
            sa.ForeignKey("assistant_messages.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_context_dependencies_source_message_id", "context_dependencies", ["source_message_id"]
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_memory_items_fts ON memory_items USING gin "
            "(to_tsvector('french'::regconfig, summary))"
        )


def downgrade() -> None:
    op.drop_column("assistant_messages", "working_choices")
    op.drop_index("ix_assistant_messages_source_user_message_id", table_name="assistant_messages")
    op.drop_column("assistant_messages", "source_user_message_id")
    op.drop_table("context_dependencies")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TABLE IF EXISTS memory_vector_index")
        op.execute("DROP INDEX IF EXISTS ix_memory_items_fts")
    for name in ("memory_usages", "working_memories", "memory_exclusions", "memory_embeddings"):
        op.drop_table(name)
    for name in ("origin", "value", "attribute", "entity"):
        op.drop_column("memory_items", name)
