"""Small deterministic retrieval layer for the pre-embedding MVP."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.memory.repository import MemoryRepository
from app.modules.neural.models import MemoryItem, MemoryLayer, MemoryType

_LAYER_PRIORITY = {
    MemoryLayer.SEMANTIC: 1.5,
    MemoryLayer.PROCEDURAL: 1.25,
    MemoryLayer.WORKING: 1.0,
    MemoryLayer.EPISODIC: 0.5,
}
_TYPE_PRIORITY = {
    MemoryType.CONSTRAINT: 0,
    MemoryType.FACT: 1,
    # Decisions and goals are the closest current representation of
    # project context until a dedicated project scope is introduced.
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
    ) -> list[MemoryItem]:
        # Authorization and scope filtering happen in the repository first.
        candidates = self.repository.active_for_user(session, user_id, limit=100)
        terms = {term.casefold() for term in (query or "").split() if len(term) > 2}
        now = datetime.now(UTC)

        def score(memory: MemoryItem) -> tuple[int, int, float, float, datetime]:
            summary_terms = set(memory.summary.casefold().split())
            lexical = len(terms & summary_terms)
            confidence = memory.confidence / 100
            observed_at = memory.observed_at
            if observed_at.tzinfo is None:
                observed_at = observed_at.replace(tzinfo=UTC)
            age_days = max(0.0, (now - observed_at).total_seconds() / 86400)
            freshness = max(0.0, 1.0 - age_days / 365)
            # Lexical matches remain dominant for a question; otherwise the
            # context contract is deterministic: constraint, fact, project-like
            # decision/goal, preference, then less durable episodes.
            return (
                lexical,
                -_TYPE_PRIORITY[memory.memory_type],
                _LAYER_PRIORITY[memory.layer],
                confidence + freshness,
                observed_at,
            )

        return sorted(candidates, key=score, reverse=True)[: max(1, min(limit, 50))]
