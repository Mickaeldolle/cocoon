"""family spaces and memberships

Revision ID: 20260912_02
Revises: 20260912_01
Create Date: 2026-09-12 01:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "20260912_02"
down_revision = "20260912_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "family_spaces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("avatar_key", sa.String(length=512), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_family_spaces_created_by", "family_spaces", ["created_by"])
    op.create_table(
        "family_space_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("family_space_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=6), nullable=False),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["family_space_id"], ["family_spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("family_space_id", "user_id", name="uq_family_space_member"),
    )
    op.create_index(
        "ix_family_space_members_family_space_id", "family_space_members", ["family_space_id"]
    )
    op.create_index("ix_family_space_members_user_id", "family_space_members", ["user_id"])


def downgrade() -> None:
    op.drop_table("family_space_members")
    op.drop_table("family_spaces")
