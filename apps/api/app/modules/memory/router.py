from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.memory.schemas import (
    MemoryActionResponse,
    MemoryCorrectionRequest,
    MemoryListResponse,
    MemoryResponse,
)
from app.modules.memory.service import correct_memory, forget_memory, get_owned_memory
from app.modules.neural.models import MemoryItem, MemoryState

router = APIRouter(prefix="/api/memories", tags=["memory"])


def memory_response(memory: MemoryItem) -> MemoryResponse:
    return MemoryResponse(
        id=memory.id,
        capture_id=memory.capture_id,
        source_run_id=memory.source_run_id,
        source_message_id=memory.source_message_id,
        summary=memory.summary,
        reason=memory.reason,
        kind=memory.kind.value,
        layer=memory.layer,
        memory_type=memory.memory_type,
        owner_type=memory.owner_type,
        scope_type=memory.scope_type,
        scope_id=memory.scope_id,
        source_type=memory.source_type,
        confidence=memory.confidence,
        valid_from=memory.valid_from,
        valid_until=memory.valid_until,
        supersedes_id=memory.supersedes_id,
        created_at=memory.created_at,
    )


@router.get("", response_model=MemoryListResponse)
def list_memories(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MemoryListResponse:
    now = datetime.now(UTC)
    memories = session.scalars(
        select(MemoryItem)
        .where(
            MemoryItem.user_id == current_user.id,
            MemoryItem.owner_type == "user",
            MemoryItem.scope_type == "personal",
            MemoryItem.state == MemoryState.ACTIVE,
            MemoryItem.deleted_at.is_(None),
            or_(MemoryItem.valid_from.is_(None), MemoryItem.valid_from <= now),
            or_(MemoryItem.valid_until.is_(None), MemoryItem.valid_until > now),
        )
        .order_by(MemoryItem.observed_at.desc())
        .limit(limit)
    )
    return MemoryListResponse(memories=[memory_response(memory) for memory in memories])


@router.get("/{memory_id}", response_model=MemoryResponse)
def read_memory(
    memory_id: UUID,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MemoryResponse:
    return memory_response(get_owned_memory(session, current_user.id, memory_id))


@router.patch("/{memory_id}", response_model=MemoryResponse)
def update_memory(
    memory_id: UUID,
    payload: MemoryCorrectionRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MemoryResponse:
    return memory_response(correct_memory(session, current_user.id, memory_id, payload))


@router.delete("/{memory_id}", response_model=MemoryActionResponse)
def delete_memory(
    memory_id: UUID,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MemoryActionResponse:
    memory = forget_memory(session, current_user.id, memory_id)
    return MemoryActionResponse(id=memory.id, state=memory.state.value)
