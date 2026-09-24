from datetime import date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base
from app.modules.assistant.proposal_types import ProposalStatus, proposal_status_values


class AssistantMessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class AssistantProposalKind(StrEnum):
    TASK = "task"
    GROCERY_ITEM = "grocery_item"
    TRAINING = "training"
    NOTE = "note"
    CALENDAR_EVENT = "calendar_event"
    RECURRING_REMINDER = "recurring_reminder"
    DEADLINE_REMINDER = "deadline_reminder"


AssistantProposalStatus = ProposalStatus


json_type = JSON().with_variant(JSONB, "postgresql")


class AssistantThread(Base):
    __tablename__ = "assistant_threads"
    __table_args__ = (UniqueConstraint("user_id", name="uq_assistant_thread_user"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    hermes_session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    thread_id: Mapped[UUID] = mapped_column(
        ForeignKey("assistant_threads.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[AssistantMessageRole] = mapped_column(
        SqlEnum(AssistantMessageRole, native_enum=False), nullable=False
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    content: Mapped[str] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AssistantProposal(Base):
    __tablename__ = "assistant_proposals"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    assistant_message_id: Mapped[UUID] = mapped_column(
        ForeignKey("assistant_messages.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[AssistantProposalKind] = mapped_column(
        SqlEnum(AssistantProposalKind, native_enum=False), nullable=False
    )
    proposal_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    payload_version: Mapped[int] = mapped_column(nullable=False, default=1)
    payload: Mapped[dict[str, object]] = mapped_column(json_type, nullable=False)
    status: Mapped[AssistantProposalStatus] = mapped_column(
        SqlEnum(
            AssistantProposalStatus,
            native_enum=False,
            values_callable=proposal_status_values,
        ),
        nullable=False,
        default=AssistantProposalStatus.PENDING,
    )
    confirmed_resource_id: Mapped[UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProposalExecution(Base):
    """Audit record for the durable effect created by a confirmed proposal."""

    __tablename__ = "proposal_executions"
    __table_args__ = (
        UniqueConstraint(
            "proposal_type", "proposal_id", name="uq_proposal_execution_proposal"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    proposal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    proposal_id: Mapped[UUID] = mapped_column(index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="committed")
    resource_id: Mapped[UUID | None] = mapped_column(nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Paris")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="cocoon")
    external_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecurringReminder(Base):
    __tablename__ = "recurring_reminders"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    anchor_date: Mapped[date] = mapped_column(nullable=False)
    recurrence_months: Mapped[int] = mapped_column(nullable=False)
    lead_days: Mapped[int] = mapped_column(nullable=False, default=7)
    next_due_date: Mapped[date] = mapped_column(nullable=False, index=True)
    next_reminder_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Paris")
    active: Mapped[bool] = mapped_column(nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AssistantPreference(Base):
    __tablename__ = "assistant_preferences"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Paris")
    delivery_time: Mapped[str] = mapped_column(String(5), nullable=False, default="08:00")
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    daily_notification_quota: Mapped[int] = mapped_column(nullable=False, default=20)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_notification_outbox_dedupe"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(String(240), nullable=False)
    data: Mapped[dict[str, object]] = mapped_column(json_type, nullable=False, default=dict)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(nullable=False, default=5)
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_ticket: Mapped[dict[str, object] | None] = mapped_column(json_type, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    provider_receipt: Mapped[dict[str, object] | None] = mapped_column(json_type, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
