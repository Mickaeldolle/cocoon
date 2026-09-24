"""normalize proposal lifecycle values before sharing the enum contract"""

from alembic import op

revision = "20260922_26"
down_revision = "20260922_25"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Both tables were historically String columns, so this is additive and
    # safe for SQLite/PostgreSQL while making old uppercase enum names readable
    # by the shared value-based SQLAlchemy enum.
    op.execute("UPDATE assistant_proposals SET status = lower(status)")
    op.execute("UPDATE neural_proposals SET status = lower(status)")


def downgrade() -> None:
    op.execute("UPDATE assistant_proposals SET status = upper(status)")
    op.execute("UPDATE neural_proposals SET status = upper(status)")
