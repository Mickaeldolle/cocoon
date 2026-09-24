"""Token-bounded context builder for the personal assistant."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.memory.repository import MemoryRepository
from app.modules.memory.retriever import MemoryRetriever


class ContextBuilder:
    def __init__(self, retriever: MemoryRetriever | None = None) -> None:
        self.retriever = retriever or MemoryRetriever()

    def memory_summaries(
        self,
        session: Session,
        user_id: UUID,
        *,
        query: str | None = None,
        limit: int = 12,
        max_characters: int = 2400,
    ) -> list[str]:
        result: list[str] = []
        total = 0
        for memory in self.retriever.retrieve(session, user_id, query=query, limit=limit):
            if total + len(memory.summary) > max_characters:
                break
            result.append(memory.summary)
            total += len(memory.summary)
        return result


def accessible_memory_summary_keys(session: Session, user_id: UUID) -> set[str]:
    """Return normalized summary keys from active personal memories only."""
    return MemoryRepository().active_summary_keys(session, user_id)
