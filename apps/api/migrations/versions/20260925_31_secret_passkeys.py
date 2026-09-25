"""Add WebAuthn passkeys and single-use secret access challenges.

Revision ID: 20260925_31
Revises: 20260922_30
"""

import sqlalchemy as sa
from alembic import op

revision = "20260925_31"
down_revision = "20260922_30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "secret_passkeys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("rp_id", sa.String(253), nullable=False),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False, unique=True),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_secret_passkeys_user_id", "secret_passkeys", ["user_id"])
    op.create_table(
        "secret_passkey_challenges",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "user_session_id",
            sa.Uuid(),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("challenge", sa.LargeBinary(), nullable=False),
        sa.Column("origin", sa.String(300), nullable=False),
        sa.Column("rp_id", sa.String(253), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_secret_passkey_challenges_user_id", "secret_passkey_challenges", ["user_id"]
    )
    op.create_index(
        "ix_secret_passkey_challenges_user_session_id",
        "secret_passkey_challenges",
        ["user_session_id"],
    )
    op.create_index(
        "ix_secret_passkey_challenges_expires_at", "secret_passkey_challenges", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_table("secret_passkey_challenges")
    op.drop_table("secret_passkeys")
