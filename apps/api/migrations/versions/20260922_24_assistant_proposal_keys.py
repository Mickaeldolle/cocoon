"""version assistant proposals and add stable payload keys

Revision ID: 20260922_24
Revises: 20260922_23
"""

import sqlalchemy as sa
from alembic import op

revision = "20260922_24"
down_revision = "20260922_23"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assistant_proposals",
        sa.Column("proposal_key", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "assistant_proposals",
        sa.Column("payload_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_assistant_proposals_proposal_key", "assistant_proposals", ["proposal_key"])


def downgrade() -> None:
    op.drop_index("ix_assistant_proposals_proposal_key", table_name="assistant_proposals")
    op.drop_column("assistant_proposals", "payload_version")
    op.drop_column("assistant_proposals", "proposal_key")
