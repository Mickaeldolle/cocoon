"""add a common proposal execution journal

Revision ID: 20260922_20
Revises: 20260922_19
"""

import sqlalchemy as sa
from alembic import op

revision = "20260922_20"
down_revision = "20260922_19"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proposal_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("proposal_type", sa.String(length=32), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="committed"),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("proposal_type", "proposal_id", name="uq_proposal_execution_proposal"),
    )
    op.create_index("ix_proposal_executions_proposal_id", "proposal_executions", ["proposal_id"])
    op.create_index("ix_proposal_executions_user_id", "proposal_executions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_proposal_executions_user_id", table_name="proposal_executions")
    op.drop_index("ix_proposal_executions_proposal_id", table_name="proposal_executions")
    op.drop_table("proposal_executions")
