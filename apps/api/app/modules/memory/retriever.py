"""Authorized lexical/vector candidates, reciprocal rank fusion and deduplication."""

import logging
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.memory.policy import memory_allowed
from app.modules.memory.repository import MemoryRepository
from app.modules.memory.text import summary_key, terms
from app.modules.neural.models import MemoryItem, MemoryType

logger = logging.getLogger(__name__)
_TYPE_PRIORITY = {
    MemoryType.CONSTRAINT: 0,
    MemoryType.FACT: 1,
    MemoryType.DECISION: 2,
    MemoryType.GOAL: 2,
    MemoryType.PREFERENCE: 3,
    MemoryType.HABIT: 4,
    MemoryType.INTEREST: 4,
}


class MemoryRetriever:
    def __init__(self, repository: MemoryRepository | None = None) -> None:
        self.repository = repository or MemoryRepository()

    def retrieve(
        self,
        session: Session,
        user_id: UUID,
        *,
        query: str | None = None,
        limit: int = 12,
        project_ids: tuple[UUID, ...] = (),
        history: bool = False,
    ) -> list[MemoryItem]:
        if not memory_allowed(session, user_id):
            return []
        started = perf_counter()
        count = max(1, min(limit, 50))
        if query is None:
            lexical = self.repository.active_for_user(
                session,
                user_id,
                limit=100,
                project_ids=project_ids,
                history=history,
                prioritize=True,
            )
            lexical.sort(key=lambda item: (_TYPE_PRIORITY[item.memory_type], -item.confidence))
        else:
            lexical = self.repository.search(
                session, user_id, query, limit=100, project_ids=project_ids, history=history
            )
            if session.get_bind().dialect.name != "postgresql":
                lexical = [item for item in lexical if terms(query) & terms(item.summary)]
        semantic: list[MemoryItem] = []
        settings = get_settings()
        if query and settings.memory_embeddings_enabled and settings.memory_vector_enabled:
            from app.modules.memory.embeddings import semantic_search

            semantic = semantic_search(session, user_id, query, project_ids=project_ids)
        scores: dict[UUID, float] = {}
        items: dict[UUID, MemoryItem] = {}
        for ranking in (lexical, semantic):
            for rank, item in enumerate(ranking, 1):
                items[item.id] = item
                scores[item.id] = scores.get(item.id, 0) + 1 / (60 + rank)
        now = datetime.now(UTC)

        def key(item: MemoryItem) -> tuple:
            observed = (
                item.observed_at.replace(tzinfo=UTC)
                if item.observed_at.tzinfo is None
                else item.observed_at
            )
            return (
                -scores[item.id],
                item.scope_id not in project_ids,
                _TYPE_PRIORITY[item.memory_type],
                -item.confidence,
                (now - observed).total_seconds(),
                str(item.id),
            )

        result: list[MemoryItem] = []
        seen: set[str] = set()
        for item in sorted(items.values(), key=key):
            marker = f"{item.scope_type}:{item.scope_id}:{summary_key(item.summary)}"
            if marker not in seen:
                result.append(item)
                seen.add(marker)
            if len(result) >= count:
                break
        logger.info(
            "memory_retrieval lexical=%d semantic=%d selected=%d duration_ms=%.1f",
            len(lexical),
            len(semantic),
            len(result),
            (perf_counter() - started) * 1000,
        )
        return result
