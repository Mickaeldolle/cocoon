"""add short-lived server-side secret access sessions

Revision ID: 20260917_09
Revises: 20260915_08
"""

import sqlalchemy as sa
from alembic import op

revision = "20260917_09"
down_revision = "20260915_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "secret_access_sessions",
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
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_secret_access_sessions_user_id", "secret_access_sessions", ["user_id"])
    op.create_index(
        "ix_secret_access_sessions_user_session_id", "secret_access_sessions", ["user_session_id"]
    )
    op.create_index(
        "ix_secret_access_sessions_token_hash", "secret_access_sessions", ["token_hash"]
    )
    op.create_index(
        "ix_secret_access_sessions_expires_at", "secret_access_sessions", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_secret_access_sessions_expires_at", table_name="secret_access_sessions")
    op.drop_index("ix_secret_access_sessions_token_hash", table_name="secret_access_sessions")
    op.drop_index("ix_secret_access_sessions_user_session_id", table_name="secret_access_sessions")
    op.drop_index("ix_secret_access_sessions_user_id", table_name="secret_access_sessions")
    op.drop_table("secret_access_sessions")
