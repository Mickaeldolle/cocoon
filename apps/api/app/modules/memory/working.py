"""Bounded, source-backed conversation checkpoints, without inferred personal facts."""

import json
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.assistant.models import AssistantMessage, AssistantMessageRole, AssistantThread
from app.modules.memory.models import MemoryExclusion, WorkingMemory
from app.modules.memory.policy import memory_allowed
from app.modules.memory.text import normalize, terms
from app.modules.personal.models import PersonalProject

DECISION_MARKERS = (
    "on utilisera",
    "on utilise",
    "on garde",
    "on retient",
    "nous avons choisi",
    "j'ai choisi",
    "j’ai choisi",
    "on a décidé",
    "on a decide",
    "il faut",
    "devra",
    "obligatoire",
    "objectif",
    "on abandonne",
    "finalement",
    "à partir de",
    "a partir de",
)


def visible_message_predicate(user_id: UUID):
    return (
        ~select(MemoryExclusion.source_id)
        .where(
            MemoryExclusion.user_id == user_id,
            MemoryExclusion.source_type == "message",
            MemoryExclusion.source_id == AssistantMessage.id,
        )
        .exists()
    )


def current_projects(session: Session, user_id: UUID, query: str) -> tuple[UUID, ...]:
    from app.modules.auth.consents import minimum_policy_version
    from app.modules.auth.models import UserConsent

    permitted = session.scalar(
        select(UserConsent.id).where(
            UserConsent.user_id == user_id,
            UserConsent.policy_key == "assistant.projects",
            UserConsent.policy_version >= minimum_policy_version("assistant.projects"),
            UserConsent.revoked_at.is_(None),
        )
    )
    if not permitted:
        return ()
    normalized = normalize(query)
    return tuple(
        item.id
        for item in session.scalars(
            select(PersonalProject).where(
                PersonalProject.user_id == user_id, PersonalProject.status != "completed"
            )
        )
        if f" {normalize(item.name)} " in f" {normalized} "
    )


def working_context(session: Session, user_id: UUID, query: str) -> dict[str, object] | None:
    if not memory_allowed(session, user_id):
        return None
    thread = session.scalar(select(AssistantThread).where(AssistantThread.user_id == user_id))
    if thread is None:
        return None
    markers = [AssistantMessage.content.ilike(f"%{marker}%") for marker in DECISION_MARKERS]
    markers.append(AssistantMessage.content.contains("?"))
    query_terms = terms(query)
    project_ids = current_projects(session, user_id, query)
    source_query = select(AssistantMessage).where(
        AssistantMessage.thread_id == thread.id,
        AssistantMessage.role == AssistantMessageRole.USER,
        visible_message_predicate(user_id),
        or_(*markers),
    )
    if project_ids:
        names = list(
            session.scalars(
                select(PersonalProject.name).where(
                    PersonalProject.user_id == user_id, PersonalProject.id.in_(project_ids)
                )
            )
        )
        source_query = source_query.where(
            or_(*[AssistantMessage.content.ilike(f"%{name}%") for name in names])
        )
    elif query_terms and not any(
        marker in normalize(query)
        for marker in (
            "on garde",
            "deuxieme option",
            "cela",
            "continue",
            "souviens",
            "reprenons",
        )
    ):
        source_query = source_query.where(
            or_(*[AssistantMessage.content.ilike(f"%{word}%") for word in sorted(query_terms)[:32]])
        )
    messages = list(
        session.scalars(
            source_query.order_by(AssistantMessage.created_at.desc(), AssistantMessage.id).limit(80)
        )
    )
    messages.sort(
        key=lambda item: (
            -len(query_terms & terms(item.content)),
            -item.created_at.timestamp(),
            str(item.id),
        )
    )
    entries = [
        {
            "source_message_id": str(item.id),
            "observed_at": item.created_at.isoformat(),
            "statement": item.content[:320],
            "kind": "question" if "?" in item.content else "user_statement",
            "truncated": "true" if len(item.content) > 320 else "false",
        }
        for item in messages[:8]
    ]
    if any(
        marker in normalize(query)
        for marker in (
            "option",
            "premiere",
            "deuxieme",
            "on garde",
            "continue",
            "reprenons",
        )
    ):
        proposed = session.scalar(
            select(AssistantMessage)
            .where(
                AssistantMessage.thread_id == thread.id,
                AssistantMessage.role == AssistantMessageRole.ASSISTANT,
                AssistantMessage.working_choices.is_not(None),
                visible_message_predicate(user_id),
            )
            .order_by(AssistantMessage.created_at.desc())
            .limit(1)
        )
        if proposed is not None:
            entries.insert(
                0,
                {
                    "source_message_id": str(proposed.id),
                    "observed_at": proposed.created_at.isoformat(),
                    "statement": "Options proposées : "
                    + json.dumps(proposed.working_choices, ensure_ascii=False),
                    "kind": "assistant_options",
                    "truncated": "false",
                },
            )
    budget = get_settings().memory_context_tokens
    bounded_entries = []
    for entry in entries:
        cost = len(json.dumps(entry, ensure_ascii=False).encode("utf-8")) + 32
        if cost <= budget:
            bounded_entries.append(entry)
            budget -= cost
    entries = bounded_entries
    # Rebuild from authorized sources every time; a checkpoint is never independent evidence.
    existing = session.get(WorkingMemory, thread.id)
    if existing is None:
        if session.get_bind().dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        session.execute(
            insert(WorkingMemory)
            .values(
                thread_id=thread.id,
                user_id=user_id,
                entries=entries,
            )
            .on_conflict_do_update(index_elements=["thread_id"], set_={"entries": entries})
        )
    else:
        existing.entries = entries
    return {
        "source": "conversation.working",
        "entries": entries,
        "project_ids": [str(value) for value in project_ids],
        "notice": (
            "Déclarations de conversation, provisoires et non confirmées comme mémoire durable."
        ),
    }
