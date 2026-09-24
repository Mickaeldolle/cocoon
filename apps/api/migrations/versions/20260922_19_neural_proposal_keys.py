"""add stable keys and payload versions to capture proposals

Revision ID: 20260922_19
Revises: 20260922_18
"""

import sqlalchemy as sa
from alembic import op

revision = "20260922_19"
down_revision = "20260922_18"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("neural_proposals", sa.Column("proposal_key", sa.String(length=160), nullable=True))
    op.add_column("neural_proposals", sa.Column("payload_version", sa.Integer(), server_default="1", nullable=False))
    op.create_unique_constraint("uq_neural_proposals_proposal_key", "neural_proposals", ["proposal_key"])
    op.create_index("ix_neural_proposals_proposal_key", "neural_proposals", ["proposal_key"])


def downgrade() -> None:
    op.drop_index("ix_neural_proposals_proposal_key", table_name="neural_proposals")
    op.drop_constraint("uq_neural_proposals_proposal_key", "neural_proposals", type_="unique")
    op.drop_column("neural_proposals", "payload_version")
    op.drop_column("neural_proposals", "proposal_key")
