"""add development biometric credentials

Revision ID: 20260917_10
Revises: 20260917_09
"""

import sqlalchemy as sa
from alembic import op

revision = "20260917_10"
down_revision = "20260917_09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "development_biometric_credentials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.Uuid(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("credential_hash", sa.String(64), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", "device_id", name="uq_dev_biometric_user_device"),
        sa.UniqueConstraint("credential_hash"),
    )
    op.create_index(
        "ix_development_biometric_credentials_user_id",
        "development_biometric_credentials",
        ["user_id"],
    )
    op.create_index(
        "ix_development_biometric_credentials_device_id",
        "development_biometric_credentials",
        ["device_id"],
    )
    op.create_index(
        "ix_development_biometric_credentials_credential_hash",
        "development_biometric_credentials",
        ["credential_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_development_biometric_credentials_credential_hash", table_name="development_biometric_credentials")
    op.drop_index("ix_development_biometric_credentials_device_id", table_name="development_biometric_credentials")
    op.drop_index("ix_development_biometric_credentials_user_id", table_name="development_biometric_credentials")
    op.drop_table("development_biometric_credentials")
