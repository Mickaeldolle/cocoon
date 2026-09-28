"""Add single-use WebAuthn login challenges.

Revision ID: 20260928_32
Revises: 20260925_31
"""

import sqlalchemy as sa
from alembic import op

revision = "20260928_32"
down_revision = "20260925_31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "passkey_login_challenges",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("challenge", sa.LargeBinary(), nullable=False),
        sa.Column("origin", sa.String(300), nullable=False),
        sa.Column("rp_id", sa.String(253), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_passkey_login_challenges_user_id", "passkey_login_challenges", ["user_id"])
    op.create_index(
        "ix_passkey_login_challenges_expires_at", "passkey_login_challenges", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_table("passkey_login_challenges")
