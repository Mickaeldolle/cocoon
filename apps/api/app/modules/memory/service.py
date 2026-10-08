from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.modules.auth.consents import require_active_consent
from app.modules.memory.embeddings import delete_vectors
from app.modules.memory.models import ContextDependency, MemoryExclusion, MemoryUsage, WorkingMemory
from app.modules.memory.repository import MemoryRepository
from app.modules.memory.schemas import MemoryCorrectionRequest
from app.modules.neural.models import MemoryItem, MemoryState
from app.modules.personal.models import PersonalProject


def get_owned_memory(
    session: Session,
    user_id: UUID,
    memory_id: UUID,
    *,
    active_only: bool = True,
) -> MemoryItem:
    now = datetime.now(UTC)
    query = select(MemoryItem).where(
        MemoryItem.id == memory_id,
        MemoryItem.user_id == user_id,
        MemoryItem.owner_type == "user",
        MemoryItem.scope_type.in_(["personal", "project"]),
        MemoryItem.deleted_at.is_(None),
    )
    if active_only:
        query = query.where(
            MemoryItem.state == MemoryState.ACTIVE,
            or_(MemoryItem.valid_from.is_(None), MemoryItem.valid_from <= now),
            or_(MemoryItem.valid_until.is_(None), MemoryItem.valid_until > now),
        )
    memory = session.scalar(query.with_for_update())
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mémoire introuvable.")
    return memory


def correct_memory(
    session: Session, user_id: UUID, memory_id: UUID, payload: MemoryCorrectionRequest
) -> MemoryItem:
    # Keep the consent lock until commit so a concurrent revocation cannot
    # commit between authorization and the replacement memory insert.
    require_active_consent(session, user_id, "assistant.memory", for_update=True)
    current = get_owned_memory(session, user_id, memory_id)
    now = datetime.now(UTC)
    scope_type = payload.scope_type or current.scope_type
    scope_id = payload.scope_id if "scope_id" in payload.model_fields_set else current.scope_id
    if scope_type == "personal":
        scope_id = None
    elif (
        scope_id is None
        or session.scalar(
            select(PersonalProject.id).where(
                PersonalProject.id == scope_id,
                PersonalProject.user_id == user_id,
            )
        )
        is None
    ):
        raise HTTPException(status_code=422, detail="Projet personnel introuvable.")
    if scope_type == "project":
        require_active_consent(session, user_id, "assistant.projects")
    valid_until = (
        payload.valid_until if "valid_until" in payload.model_fields_set else current.valid_until
    )
    if valid_until is not None and valid_until.tzinfo is None:
        valid_until = valid_until.replace(tzinfo=UTC)
    if valid_until is not None and valid_until <= now:
        raise HTTPException(
            status_code=422, detail="La nouvelle mémoire doit être valide à présent."
        )
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
        scope_type=scope_type,
        scope_id=scope_id,
        source_type="correction",
        source_message_id=current.source_message_id,
        summary=" ".join(payload.summary.split()),
        reason=f"Correction de la mémoire {current.id}.",
        confidence=payload.confidence,
        state=MemoryState.ACTIVE,
        valid_from=now,
        valid_until=valid_until,
        origin="explicit",
        entity=payload.entity if "entity" in payload.model_fields_set else current.entity,
        attribute=payload.attribute
        if "attribute" in payload.model_fields_set
        else current.attribute,
        value=payload.value if "value" in payload.model_fields_set else current.value,
        supersedes_id=current.id,
    )
    session.add(replacement)
    session.flush()
    delete_vectors(session, [current.id])
    session.commit()
    session.refresh(replacement)
    return replacement


def forget_memory(session: Session, user_id: UUID, memory_id: UUID) -> MemoryItem:
    memory = get_owned_memory(session, user_id, memory_id, active_only=False)
    repository = MemoryRepository()
    pending_ids = [memory.id]
    seen_ids: set[UUID] = set()
    while pending_ids:
        current_id = pending_ids.pop()
        if current_id in seen_ids:
            continue
        seen_ids.add(current_id)
        current = session.scalar(
            select(MemoryItem)
            .where(
                MemoryItem.id == current_id,
                MemoryItem.user_id == user_id,
            )
            .with_for_update()
        )
        if current is None:
            continue
        repository.soft_delete(session, current)
        exclude_source(session, user_id, "capture", current.capture_id)
        if current.source_message_id:
            exclude_source(session, user_id, "message", current.source_message_id)
        if current.supersedes_id:
            pending_ids.append(current.supersedes_id)
        pending_ids.extend(
            session.scalars(
                select(MemoryItem.id).where(
                    MemoryItem.user_id == user_id,
                    MemoryItem.supersedes_id == current.id,
                )
            )
        )
    from app.modules.assistant.models import AssistantProposal

    for message_id in session.scalars(
        select(AssistantProposal.assistant_message_id).where(
            AssistantProposal.user_id == user_id,
            AssistantProposal.confirmed_resource_id.in_(seen_ids),
        )
    ):
        exclude_source(session, user_id, "message", message_id)
    for message_id in session.scalars(
        select(MemoryUsage.message_id).where(
            MemoryUsage.memory_id.in_(seen_ids),
        )
    ):
        exclude_source(session, user_id, "message", message_id)
    delete_vectors(session, list(seen_ids))
    propagate_exclusions(session, user_id)
    session.execute(delete(WorkingMemory).where(WorkingMemory.user_id == user_id))
    session.commit()
    session.refresh(memory)
    return memory


def exclude_source(session: Session, user_id: UUID, kind: str, source_id: UUID) -> None:
    if session.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    session.execute(
        insert(MemoryExclusion)
        .values(
            user_id=user_id,
            source_type=kind,
            source_id=source_id,
        )
        .on_conflict_do_nothing(index_elements=["user_id", "source_type", "source_id"])
    )


def assert_source_available(session: Session, user_id: UUID, kind: str, source_id: UUID) -> None:
    if session.get(MemoryExclusion, (user_id, kind, source_id)) is not None:
        raise HTTPException(
            status_code=409, detail="Cette source a été exclue par une demande d'oubli."
        )


def propagate_exclusions(session: Session, user_id: UUID) -> None:
    from app.modules.assistant.models import AssistantMessage, AssistantThread

    blocked = set(
        session.scalars(
            select(MemoryExclusion.source_id).where(
                MemoryExclusion.user_id == user_id,
                MemoryExclusion.source_type == "message",
            )
        )
    )
    pending = set(blocked)
    while pending:
        batch = list(pending)[:500]
        pending.difference_update(batch)
        derived = (
            set(
                session.scalars(
                    select(ContextDependency.message_id)
                    .join(AssistantMessage, AssistantMessage.id == ContextDependency.message_id)
                    .join(AssistantThread, AssistantThread.id == AssistantMessage.thread_id)
                    .where(
                        AssistantThread.user_id == user_id,
                        ContextDependency.source_message_id.in_(batch),
                    )
                )
            )
            - blocked
        )
        for message_id in derived:
            exclude_source(session, user_id, "message", message_id)
        blocked.update(derived)
        pending.update(derived)


def invalidate_user_indexes(session: Session, user_id: UUID) -> None:
    ids = list(session.scalars(select(MemoryItem.id).where(MemoryItem.user_id == user_id)))
    if ids:
        delete_vectors(session, ids)
    session.execute(delete(WorkingMemory).where(WorkingMemory.user_id == user_id))
