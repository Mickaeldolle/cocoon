from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base
from app.modules.assistant.proposal_types import ProposalStatus, proposal_status_values


class CaptureSource(StrEnum):
    TEXT = "text"
    DEVICE_CALENDAR = "device_calendar"


class CaptureRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MemoryKind(StrEnum):
    INFORMATION = "information"
    INTENTION = "intention"
    ENGAGEMENT = "engagement"
    QUESTION = "question"


class MemoryState(StrEnum):
    ACTIVE = "active"
    STALE = "stale"
    DISMISSED = "dismissed"


class MemoryLayer(StrEnum):
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


class MemoryType(StrEnum):
    FACT = "fact"
    PREFERENCE = "preference"
    CONSTRAINT = "constraint"
    DECISION = "decision"
    GOAL = "goal"
    INTEREST = "interest"
    HABIT = "habit"


json_type = JSON().with_variant(JSONB, "postgresql")


def enum_values(enum_type: type[StrEnum]) -> list[str]:
    """Persist the stable lowercase values used by the migrations."""
    return [item.value for item in enum_type]


class Capture(Base):
    __tablename__ = "captures"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source: Mapped[CaptureSource] = mapped_column(
        SqlEnum(CaptureSource, native_enum=False, values_callable=enum_values)
    )
    content: Mapped[str] = mapped_column(Text())
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Paris")
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CaptureRun(Base):
    __tablename__ = "capture_runs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    capture_id: Mapped[UUID] = mapped_column(
        ForeignKey("captures.id", ondelete="CASCADE"), unique=True, index=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[CaptureRunStatus] = mapped_column(
        SqlEnum(CaptureRunStatus, native_enum=False, values_callable=enum_values),
        default=CaptureRunStatus.QUEUED,
    )
    attempt: Mapped[int] = mapped_column(Integer(), default=1)
    max_attempts: Mapped[int] = mapped_column(Integer(), default=3)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CaptureRunEvent(Base):
    __tablename__ = "capture_run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_capture_run_event_sequence"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("capture_runs.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer())
    event_type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, object]] = mapped_column(json_type, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MemoryItem(Base):
    __tablename__ = "memory_items"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    capture_id: Mapped[UUID] = mapped_column(
        ForeignKey("captures.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[MemoryKind] = mapped_column(
        SqlEnum(MemoryKind, native_enum=False, values_callable=enum_values)
    )
    layer: Mapped[MemoryLayer] = mapped_column(
        SqlEnum(MemoryLayer, native_enum=False, values_callable=enum_values),
        default=MemoryLayer.EPISODIC,
    )
    memory_type: Mapped[MemoryType] = mapped_column(
        SqlEnum(MemoryType, native_enum=False, values_callable=enum_values),
        default=MemoryType.FACT,
    )
    owner_type: Mapped[str] = mapped_column(String(24), default="user")
    scope_type: Mapped[str] = mapped_column(String(24), default="personal")
    scope_id: Mapped[UUID | None] = mapped_column(nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), default="capture")
    source_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("capture_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_message_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    summary: Mapped[str] = mapped_column(String(240))
    reason: Mapped[str] = mapped_column(String(320))
    confidence: Mapped[int] = mapped_column(Integer(), default=70)
    state: Mapped[MemoryState] = mapped_column(
        SqlEnum(MemoryState, native_enum=False, values_callable=enum_values),
        default=MemoryState.ACTIVE,
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supersedes_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("memory_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NeuralProposal(Base):
    __tablename__ = "neural_proposals"
    __table_args__ = (UniqueConstraint("proposal_key", name="uq_neural_proposals_proposal_key"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    capture_id: Mapped[UUID] = mapped_column(
        ForeignKey("captures.id", ondelete="CASCADE"), index=True
    )
    source_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("capture_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    memory_item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("memory_items.id", ondelete="SET NULL"), nullable=True
    )
    capability: Mapped[str] = mapped_column(String(32))
    proposal_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    payload_version: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    payload: Mapped[dict[str, object]] = mapped_column(json_type, default=dict)
    reason: Mapped[str] = mapped_column(String(320))
    status: Mapped[ProposalStatus] = mapped_column(
        SqlEnum(
            ProposalStatus,
            native_enum=False,
            values_callable=proposal_status_values,
        ),
        default=ProposalStatus.PENDING,
    )
    confirmed_resource_id: Mapped[UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=lambda: datetime.now(UTC) + timedelta(hours=24),
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
