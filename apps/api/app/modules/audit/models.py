from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Index, Integer, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditEvent(Base):
    """Bounded audit metadata and explicitly selected JSON details."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_actor_time", "actor_user_id", "occurred_at"),
        Index("ix_audit_events_time", "occurred_at"),
        Index("ix_audit_events_identity_time", "attempted_identity_ref", "occurred_at"),
        Index("ix_audit_events_ip_time", "client_ip", "occurred_at"),
        Index("ix_audit_events_action_time", "action", "occurred_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(nullable=True)
    session_id: Mapped[UUID | None] = mapped_column(nullable=True)
    device_id: Mapped[UUID | None] = mapped_column(nullable=True)
    attempted_identity_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    client_ip_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    user_agent_family: Mapped[str | None] = mapped_column(String(32), nullable=True)
    client_platform: Mapped[str | None] = mapped_column(String(32), nullable=True)
    request_id: Mapped[UUID] = mapped_column()
    action: Mapped[str] = mapped_column(String(100))
    outcome: Mapped[str] = mapped_column(String(16))
    method: Mapped[str] = mapped_column(String(8))
    route: Mapped[str | None] = mapped_column(String(180), nullable=True)
    status_code: Mapped[int] = mapped_column(SmallInteger)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_details: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    query_details: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    response_details: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
