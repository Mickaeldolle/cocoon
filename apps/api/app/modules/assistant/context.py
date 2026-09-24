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
from app.modules.personal.models import PersonalTask

_context_builder = ContextBuilder()


def get_or_create_thread(session: Session, user_id: UUID) -> AssistantThread:
    """Return only the assistant thread owned by ``user_id``."""
    thread = session.scalar(
        select(AssistantThread).where(AssistantThread.user_id == user_id)
    )
    if thread is None:
        thread = AssistantThread(user_id=user_id)
        session.add(thread)
        session.flush()
    return thread


def recent_messages(
    session: Session, thread_id: UUID, *, limit: int
) -> list[dict[str, str]]:
    """Load a bounded conversation slice from one already-authorized thread."""
    messages = list(
        session.scalars(
            select(AssistantMessage)
            .where(AssistantMessage.thread_id == thread_id)
            .order_by(AssistantMessage.created_at.desc())
            .limit(limit)
        )
    )
    return [
        {"role": message.role.value, "content": message.content}
        for message in reversed(messages)
    ]


def accessible_memory_summaries(
    session: Session, user_id: UUID, *, limit: int, query: str | None = None
) -> list[str]:
    """Return active personal memories; no family or hidden conversation data is queried."""
    return _context_builder.memory_summaries(
        session,
        user_id,
        query=query,
        limit=limit,
        max_characters=max(240, limit * 240),
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
    session: Session, user_id: UUID, *, limit: int = 8
) -> list[dict[str, object]]:
    """Expose only bounded read-only personal objects to the chat provider."""
    settings = get_settings()
    budget = ToolBudget(
        max_calls=settings.assistant_max_tool_calls,
        max_duration_ms=settings.assistant_tool_budget_ms,
    )
    return [
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


def assistant_message_role(value: AssistantMessageRole) -> str:
    """Keep the role conversion in one place for prompt construction."""
    return value.value
