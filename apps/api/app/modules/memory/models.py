"""Reconstructible indexes and durable exclusions; never independent evidence."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.neural.models import json_type


class MemoryEmbedding(Base):
    __tablename__ = "memory_embeddings"

    memory_id: Mapped[UUID] = mapped_column(
        ForeignKey("memory_items.id", ondelete="CASCADE"), primary_key=True
    )
    config_hash: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64))
    vector: Mapped[list[float] | None] = mapped_column(json_type, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    attempt: Mapped[int] = mapped_column(Integer(), default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(80), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MemoryExclusion(Base):
    """Suppress forgotten source messages/captures during context reconstruction."""

    __tablename__ = "memory_exclusions"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    source_type: Mapped[str] = mapped_column(String(24), primary_key=True)
    source_id: Mapped[UUID] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkingMemory(Base):
    __tablename__ = "working_memories"
    thread_id: Mapped[UUID] = mapped_column(
        ForeignKey("assistant_threads.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    entries: Mapped[list[dict[str, str]]] = mapped_column(json_type, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MemoryUsage(Base):
    """Track response dependencies so forgetting can exclude derived assistant turns."""

    __tablename__ = "memory_usages"
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("assistant_messages.id", ondelete="CASCADE"), primary_key=True
    )
    memory_id: Mapped[UUID] = mapped_column(
        ForeignKey("memory_items.id", ondelete="CASCADE"), primary_key=True
    )


class ContextDependency(Base):
    __tablename__ = "context_dependencies"
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("assistant_messages.id", ondelete="CASCADE"), primary_key=True
    )
    source_message_id: Mapped[UUID] = mapped_column(
        ForeignKey("assistant_messages.id", ondelete="CASCADE"), primary_key=True, index=True
    )
