"""Authenticated context assembly for the personal assistant.

Every query in this module is scoped by the authenticated user's id before any
ordering or limiting is applied. The secret-conversation domain is intentionally
not imported here and therefore cannot enter assistant context accidentally.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.assistant.models import AssistantMessage, AssistantMessageRole, AssistantThread
from app.modules.assistant.tools import ToolBudget, tool_registry
from app.modules.memory.context import ContextBuilder
from app.modules.memory.working import current_projects, visible_message_predicate, working_context
from app.modules.personal.models import PersonalTask

_context_builder = ContextBuilder()


def get_or_create_thread(session: Session, user_id: UUID) -> AssistantThread:
    """Return only the assistant thread owned by ``user_id``."""
    thread = session.scalar(select(AssistantThread).where(AssistantThread.user_id == user_id))
    if thread is None:
        thread = AssistantThread(user_id=user_id)
        session.add(thread)
        session.flush()
    return thread


def recent_messages(
    session: Session,
    thread_id: UUID,
    *,
    limit: int,
    exclude_message_id: UUID | None = None,
    include_sources: bool = False,
) -> list[dict[str, str]]:
    """Load a bounded conversation slice from one already-authorized thread."""
    query = select(AssistantMessage).where(AssistantMessage.thread_id == thread_id)
    owner = session.scalar(select(AssistantThread.user_id).where(AssistantThread.id == thread_id))
    if owner is None:
        return []
    query = query.where(visible_message_predicate(owner))
    if exclude_message_id is not None:
        query = query.where(AssistantMessage.id != exclude_message_id)
    messages = list(
        session.scalars(query.order_by(AssistantMessage.created_at.desc()).limit(limit))
    )
    return [
        {
            "role": message.role.value,
            "content": message.content,
            **({"source_message_id": str(message.id)} if include_sources else {}),
        }
        for message in reversed(messages)
    ]


def accessible_memory_summaries(
    session: Session, user_id: UUID, *, limit: int, query: str | None = None
) -> list[dict[str, object]]:
    """Return active personal memories; no family or hidden conversation data is queried."""
    # An unqualified recall request can refer to the last conversation rather than keywords.
    from app.modules.memory.text import terms

    search = query
    if query and terms(query) and terms(query) <= {"souviens", "souvenir", "souvenirs", "souvient"}:
        search = None
    return _context_builder.memory_context(
        session,
        user_id,
        query=search,
        limit=limit,
        project_ids=current_projects(session, user_id, query or ""),
    )


def open_task_titles(session: Session, user_id: UUID, *, limit: int) -> list[str]:
    """Return open personal tasks for the current account only."""
    return list(
        session.scalars(
            select(PersonalTask.title)
            .where(PersonalTask.user_id == user_id, PersonalTask.completed.is_(False))
            .order_by(PersonalTask.created_at.desc())
            .limit(limit)
        )
    )


def accessible_personal_context(
    session: Session, user_id: UUID, *, limit: int = 8, query: str = ""
) -> list[dict[str, object]]:
    """Expose only bounded read-only personal objects to the chat provider."""
    settings = get_settings()
    budget = ToolBudget(
        max_calls=settings.assistant_max_tool_calls,
        max_duration_ms=settings.assistant_tool_budget_ms,
    )
    result = [
        {
            "source": "personal.tasks.list",
            "items": tool_registry.execute(
                "personal.tasks.list",
                {"limit": limit},
                session=session,
                user_id=user_id,
                budget=budget,
            ),
        },
        {
            "source": "personal.calendar.list",
            "items": tool_registry.execute(
                "personal.calendar.list",
                {"limit": limit},
                session=session,
                user_id=user_id,
                budget=budget,
            ),
        },
        {
            "source": "personal.projects.list",
            "items": tool_registry.execute(
                "personal.projects.list",
                {"limit": limit},
                session=session,
                user_id=user_id,
                budget=budget,
            ),
        },
    ]
    working = working_context(session, user_id, query)
    if working is not None:
        result.append(working)
    return result


def assistant_message_role(value: AssistantMessageRole) -> str:
    """Keep the role conversion in one place for prompt construction."""
    return value.value
