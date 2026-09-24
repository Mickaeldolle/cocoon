"""Owner-, scope- and validity-filtered access to personal memories."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.neural.models import MemoryItem, MemoryState


class MemoryRepository:
    """Keep authorization predicates in SQL, before ranking or truncation."""

    def active_for_user(
        self, session: Session, user_id: UUID, *, limit: int = 100
    ) -> list[MemoryItem]:
        bounded_limit = max(1, min(limit, 100))
        now = datetime.now(UTC)
        return list(
            session.scalars(
                select(MemoryItem)
                .where(
                    MemoryItem.user_id == user_id,
                    MemoryItem.owner_type == "user",
                    MemoryItem.scope_type == "personal",
                    MemoryItem.state == MemoryState.ACTIVE,
                    MemoryItem.deleted_at.is_(None),
                    or_(MemoryItem.valid_from.is_(None), MemoryItem.valid_from <= now),
                    or_(MemoryItem.valid_until.is_(None), MemoryItem.valid_until > now),
                )
                .order_by(MemoryItem.observed_at.desc())
                .limit(bounded_limit)
            )
        )

    def soft_delete(self, session: Session, memory: MemoryItem) -> None:
        """Hide a memory from retrieval while retaining auditable provenance."""
        memory.deleted_at = datetime.now(UTC)
        memory.state = MemoryState.DISMISSED

    def active_summary_keys(self, session: Session, user_id: UUID) -> set[str]:
        """Return normalized active summaries for owner-scoped deduplication."""
        memories = self.active_for_user(session, user_id, limit=100)
        return {" ".join(memory.summary.casefold().split()) for memory in memories}
