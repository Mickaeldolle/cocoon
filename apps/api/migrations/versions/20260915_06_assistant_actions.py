"""persist assistant history, confirmed proposals and personal-planning refinements

Revision ID: 20260915_06
Revises: 20260915_05
Create Date: 2026-09-15 01:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "20260915_06"
down_revision = "20260915_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("weekly_training_target", sa.Integer(), nullable=True))
    op.execute("UPDATE user_profiles SET weekly_training_target = 3 WHERE weekly_training_target IS NULL")
    op.alter_column("user_profiles", "weekly_training_target", nullable=False)
    op.add_column("personal_tasks", sa.Column("due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("personal_tasks", sa.Column("reminder_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("personal_tasks", sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("personal_tasks", sa.Column("priority", sa.String(length=16), nullable=True))
    op.execute("UPDATE personal_tasks SET priority = 'normal' WHERE priority IS NULL")
    op.alter_column("personal_tasks", "priority", nullable=False)
    op.create_table(
        "grocery_lists",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_grocery_lists_user_id", "grocery_lists", ["user_id"])
    op.add_column("grocery_items", sa.Column("list_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_grocery_items_list_id", "grocery_items", "grocery_lists", ["list_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_grocery_items_list_id", "grocery_items", ["list_id"])
    op.create_table(
        "weight_check_ins",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("recorded_on", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_weight_check_ins_user_id", "weight_check_ins", ["user_id"])
    op.create_table(
        "assistant_threads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_assistant_thread_user"),
    )
    op.create_index("ix_assistant_threads_user_id", "assistant_threads", ["user_id"])
    op.create_table(
        "assistant_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=9), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["assistant_threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assistant_messages_thread_id", "assistant_messages", ["thread_id"])
    op.create_table(
        "assistant_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("assistant_message_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=9), nullable=False),
        sa.Column("confirmed_resource_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assistant_message_id"], ["assistant_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assistant_proposals_user_id", "assistant_proposals", ["user_id"])
    op.create_index("ix_assistant_proposals_assistant_message_id", "assistant_proposals", ["assistant_message_id"])
    op.create_table(
        "assistant_preferences",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("delivery_time", sa.String(length=5), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("assistant_preferences")
    op.drop_index("ix_assistant_proposals_assistant_message_id", table_name="assistant_proposals")
    op.drop_index("ix_assistant_proposals_user_id", table_name="assistant_proposals")
    op.drop_table("assistant_proposals")
    op.drop_index("ix_assistant_messages_thread_id", table_name="assistant_messages")
    op.drop_table("assistant_messages")
    op.drop_index("ix_assistant_threads_user_id", table_name="assistant_threads")
    op.drop_table("assistant_threads")
    op.drop_index("ix_weight_check_ins_user_id", table_name="weight_check_ins")
    op.drop_table("weight_check_ins")
    op.drop_index("ix_grocery_items_list_id", table_name="grocery_items")
    op.drop_constraint("fk_grocery_items_list_id", "grocery_items", type_="foreignkey")
    op.drop_column("grocery_items", "list_id")
    op.drop_index("ix_grocery_lists_user_id", table_name="grocery_lists")
    op.drop_table("grocery_lists")
    op.drop_column("personal_tasks", "priority")
    op.drop_column("personal_tasks", "reminder_sent_at")
    op.drop_column("personal_tasks", "reminder_at")
    op.drop_column("personal_tasks", "due_at")
    op.drop_column("user_profiles", "weekly_training_target")
