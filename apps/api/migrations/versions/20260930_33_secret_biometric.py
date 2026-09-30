"""Add device-bound biometric credentials for secret access.

Revision ID: 20260930_33
Revises: 20260928_32
"""

import sqlalchemy as sa
from alembic import op

revision = "20260930_33"
down_revision = "20260928_32"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "secret_biometric_credentials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "device_id", sa.Uuid(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("credential_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("user_id", "device_id", name="uq_secret_biometric_user_device"),
    )
    op.create_index(
        "ix_secret_biometric_credentials_user_id", "secret_biometric_credentials", ["user_id"]
    )
    op.create_index(
        "ix_secret_biometric_credentials_device_id", "secret_biometric_credentials", ["device_id"]
    )
    op.create_index(
        "ix_secret_biometric_credentials_credential_hash",
        "secret_biometric_credentials",
        ["credential_hash"],
    )


def downgrade() -> None:
    op.drop_table("secret_biometric_credentials")
