"""Persist source dependencies used by a generated assistant message."""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.assistant.models import AssistantMessage, AssistantMessageRole, AssistantThread
from app.modules.memory.models import ContextDependency, MemoryExclusion, MemoryUsage
from app.modules.memory.service import exclude_source
from app.modules.neural.models import MemoryItem

logger = logging.getLogger(__name__)


def record_memory_usage(
    session: Session,
    message_id: UUID,
    memories: list[dict[str, object]],
    recent_turns: list[dict[str, str]],
    personal_context: list[dict[str, object]],
) -> None:
    """Link a reply to remembered items and conversation sources for later forgetting."""
    memory_ids = {UUID(str(memory["id"])) for memory in memories}
    source_ids = {
        UUID(item["source_message_id"])
        for item in recent_turns
        if item.get("source_message_id")
    }
    for block in personal_context:
        if block.get("source") == "conversation.working":
            source_ids.update(
                UUID(item["source_message_id"]) for item in block.get("entries", [])
            )
    message = session.get(AssistantMessage, message_id)
    if message is None:
        raise ValueError("assistant_message_missing")
    owner_id = session.scalar(
        select(AssistantThread.user_id).where(AssistantThread.id == message.thread_id)
    )
    if owner_id is None:
        raise ValueError("assistant_thread_missing")
    current_source = message.source_user_message_id or session.scalar(
        select(AssistantMessage.id)
        .where(
            AssistantMessage.thread_id == message.thread_id,
            AssistantMessage.role == AssistantMessageRole.USER,
            AssistantMessage.created_at <= message.created_at,
        )
        .order_by(AssistantMessage.created_at.desc())
        .limit(1)
    )
    if current_source:
        source_ids.add(current_source)
    authorized_sources = (
        set(
            session.scalars(
                select(AssistantMessage.id)
                .join(AssistantThread, AssistantThread.id == AssistantMessage.thread_id)
                .where(AssistantThread.user_id == owner_id, AssistantMessage.id.in_(source_ids))
            )
        )
        if source_ids
        else set()
    )
    if len(authorized_sources) != len(source_ids):
        logger.warning("memory_dependency_source_rejected")
    source_ids = authorized_sources
    if source_ids:
        memory_ids.update(
            session.scalars(select(MemoryUsage.memory_id).where(MemoryUsage.message_id.in_(source_ids)))
        )
    authorized_memories = (
        set(
            session.scalars(
                select(MemoryItem.id).where(
                    MemoryItem.user_id == owner_id,
                    MemoryItem.owner_type == "user",
                    MemoryItem.id.in_(memory_ids),
                )
            )
        )
        if memory_ids
        else set()
    )
    if len(authorized_memories) != len(memory_ids):
        logger.warning("memory_dependency_item_rejected")
    memory_ids = authorized_memories
    for memory_id in memory_ids:
        session.add(MemoryUsage(message_id=message_id, memory_id=memory_id))
    for source_id in source_ids:
        session.add(ContextDependency(message_id=message_id, source_message_id=source_id))
    excluded_parent = session.scalar(
        select(MemoryExclusion.source_id)
        .where(
            MemoryExclusion.user_id == owner_id,
            MemoryExclusion.source_type == "message",
            MemoryExclusion.source_id.in_(source_ids),
        )
        .limit(1)
    )
    forgotten_memory = session.scalar(
        select(MemoryItem.id)
        .where(
            MemoryItem.id.in_(memory_ids),
            MemoryItem.deleted_at.is_not(None),
        )
        .limit(1)
    )
    if excluded_parent is not None or forgotten_memory is not None:
        exclude_source(session, owner_id, "message", message_id)
