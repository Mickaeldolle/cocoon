"""link capture proposals to their producing run

Revision ID: 20260922_25
Revises: 20260922_24
"""

import sqlalchemy as sa
from alembic import op

revision = "20260922_25"
down_revision = "20260922_24"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "neural_proposals",
        sa.Column("source_run_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_neural_proposals_source_run_id",
        "neural_proposals",
        "capture_runs",
        ["source_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_neural_proposals_source_run_id",
        "neural_proposals",
        ["source_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_neural_proposals_source_run_id", table_name="neural_proposals")
    op.drop_constraint(
        "fk_neural_proposals_source_run_id", "neural_proposals", type_="foreignkey"
    )
    op.drop_column("neural_proposals", "source_run_id")
