"""add personal neural capture core

Revision ID: 20260915_08
Revises: 20260915_07
"""
import sqlalchemy as sa
from alembic import op

revision = "20260915_08"
down_revision = "20260915_07"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("captures", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("source", sa.String(32), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("timezone", sa.String(64), nullable=False), sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.create_index("ix_captures_user_id", "captures", ["user_id"])
    op.create_table("memory_items", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("capture_id", sa.Uuid(), sa.ForeignKey("captures.id", ondelete="CASCADE"), nullable=False), sa.Column("kind", sa.String(32), nullable=False), sa.Column("summary", sa.String(240), nullable=False), sa.Column("reason", sa.String(320), nullable=False), sa.Column("confidence", sa.Integer(), nullable=False), sa.Column("state", sa.String(16), nullable=False), sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("valid_from", sa.DateTime(timezone=True)), sa.Column("valid_until", sa.DateTime(timezone=True)), sa.Column("review_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.create_index("ix_memory_items_user_id", "memory_items", ["user_id"])
    op.create_table("neural_proposals", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("capture_id", sa.Uuid(), sa.ForeignKey("captures.id", ondelete="CASCADE"), nullable=False), sa.Column("memory_item_id", sa.Uuid(), sa.ForeignKey("memory_items.id", ondelete="SET NULL")), sa.Column("capability", sa.String(32), nullable=False), sa.Column("payload", sa.JSON(), nullable=False), sa.Column("reason", sa.String(320), nullable=False), sa.Column("status", sa.String(16), nullable=False), sa.Column("confirmed_resource_id", sa.Uuid()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.create_index("ix_neural_proposals_user_id", "neural_proposals", ["user_id"])

def downgrade() -> None:
    op.drop_table("neural_proposals")
    op.drop_table("memory_items")
    op.drop_table("captures")
