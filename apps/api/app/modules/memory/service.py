from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.memory.repository import MemoryRepository
from app.modules.memory.schemas import MemoryCorrectionRequest
from app.modules.neural.models import MemoryItem, MemoryState


def get_owned_memory(session: Session, user_id: UUID, memory_id: UUID) -> MemoryItem:
    now = datetime.now(UTC)
    memory = session.scalar(
        select(MemoryItem).where(
            MemoryItem.id == memory_id,
            MemoryItem.user_id == user_id,
            MemoryItem.owner_type == "user",
            MemoryItem.scope_type == "personal",
            MemoryItem.deleted_at.is_(None),
            MemoryItem.state == MemoryState.ACTIVE,
            or_(MemoryItem.valid_from.is_(None), MemoryItem.valid_from <= now),
            or_(MemoryItem.valid_until.is_(None), MemoryItem.valid_until > now),
        )
    )
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mémoire introuvable.")
    return memory


def correct_memory(
    session: Session, user_id: UUID, memory_id: UUID, payload: MemoryCorrectionRequest
) -> MemoryItem:
    current = get_owned_memory(session, user_id, memory_id)
    now = datetime.now(UTC)
    current.state = MemoryState.STALE
    current.valid_until = now
    replacement = MemoryItem(
        user_id=user_id,
        capture_id=current.capture_id,
        source_run_id=current.source_run_id,
        kind=current.kind,
        layer=payload.layer or current.layer,
        memory_type=payload.memory_type or current.memory_type,
        owner_type=current.owner_type,
        scope_type=current.scope_type,
        scope_id=current.scope_id,
        source_type="correction",
        source_message_id=current.source_message_id,
        summary=" ".join(payload.summary.split()),
        reason=f"Correction de la mémoire {current.id}.",
        confidence=payload.confidence,
        state=MemoryState.ACTIVE,
        valid_from=now,
        supersedes_id=current.id,
    )
    session.add(replacement)
    session.flush()
    session.commit()
    session.refresh(replacement)
    return replacement


def forget_memory(session: Session, user_id: UUID, memory_id: UUID) -> MemoryItem:
    memory = get_owned_memory(session, user_id, memory_id)
    repository = MemoryRepository()
    pending_ids = [memory.id]
    seen_ids: set[UUID] = set()
    while pending_ids:
        current_id = pending_ids.pop()
        if current_id in seen_ids:
            continue
        seen_ids.add(current_id)
        current = session.scalar(
            select(MemoryItem).where(
                MemoryItem.id == current_id,
                MemoryItem.user_id == user_id,
                MemoryItem.state == MemoryState.ACTIVE,
                MemoryItem.deleted_at.is_(None),
            )
        )
        if current is None:
            continue
        repository.soft_delete(session, current)
        pending_ids.extend(
            session.scalars(
                select(MemoryItem.id).where(
                    MemoryItem.user_id == user_id,
                    MemoryItem.supersedes_id == current.id,
                    MemoryItem.state == MemoryState.ACTIVE,
                    MemoryItem.deleted_at.is_(None),
                )
            )
        )
    session.commit()
    session.refresh(memory)
    return memory
