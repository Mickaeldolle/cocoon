"""Add selected request, response and client context to audit events.

Revision ID: 20261001_35
Revises: 20261001_34
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261001_35"
down_revision = "20261001_34"
branch_labels = None
depends_on = None


def json_type() -> sa.JSON:
    return sa.JSON().with_variant(JSONB, "postgresql")


def upgrade() -> None:
    op.add_column("audit_events", sa.Column("device_id", sa.Uuid(), nullable=True))
    op.add_column("audit_events", sa.Column("attempted_identity_ref", sa.String(64), nullable=True))
    op.add_column("audit_events", sa.Column("client_ip", sa.String(45), nullable=True))
    op.add_column("audit_events", sa.Column("client_ip_source", sa.String(16), nullable=True))
    op.add_column("audit_events", sa.Column("user_agent_family", sa.String(32), nullable=True))
    op.add_column("audit_events", sa.Column("client_platform", sa.String(32), nullable=True))
    op.add_column("audit_events", sa.Column("duration_ms", sa.Integer(), nullable=True))
    op.add_column("audit_events", sa.Column("response_bytes", sa.Integer(), nullable=True))
    op.add_column("audit_events", sa.Column("request_details", json_type(), nullable=True))
    op.add_column("audit_events", sa.Column("query_details", json_type(), nullable=True))
    op.add_column("audit_events", sa.Column("response_details", json_type(), nullable=True))
    op.create_index("ix_audit_events_identity_time", "audit_events", ["attempted_identity_ref", "occurred_at"])
    op.create_index("ix_audit_events_ip_time", "audit_events", ["client_ip", "occurred_at"])
    op.create_index("ix_audit_events_action_time", "audit_events", ["action", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_action_time", table_name="audit_events")
    op.drop_index("ix_audit_events_ip_time", table_name="audit_events")
    op.drop_index("ix_audit_events_identity_time", table_name="audit_events")
    for column in (
        "response_details", "query_details", "request_details", "response_bytes",
        "duration_ms", "client_platform", "user_agent_family", "client_ip_source",
        "client_ip", "attempted_identity_ref", "device_id",
    ):
        op.drop_column("audit_events", column)
