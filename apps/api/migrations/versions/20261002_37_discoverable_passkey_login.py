"""Mark username-free passkey login challenges.

Revision ID: 20261002_37
Revises: 20261001_36
"""

import sqlalchemy as sa
from alembic import op

revision = "20261002_37"
down_revision = "20261001_36"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "passkey_login_challenges",
        sa.Column("discoverable", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("passkey_login_challenges", "discoverable")
