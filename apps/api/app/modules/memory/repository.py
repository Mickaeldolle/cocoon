"""SQL authorization, scope and validity precede candidate selection."""

import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import case, func, literal_column, or_, select
from sqlalchemy.orm import Session

from app.modules.memory.text import normalize, summary_key, terms
from app.modules.neural.models import MemoryItem, MemoryState


class MemoryRepository:
    def predicates(
        self, user_id: UUID, *, project_ids: tuple[UUID, ...] = (), history: bool = False
    ) -> tuple:
        now = datetime.now(UTC)
        scope = MemoryItem.scope_type == "personal"
        if project_ids:
            scope = or_(
                scope, (MemoryItem.scope_type == "project") & MemoryItem.scope_id.in_(project_ids)
            )
        common = (
            MemoryItem.user_id == user_id,
            MemoryItem.owner_type == "user",
            scope,
            MemoryItem.deleted_at.is_(None),
        )
        if history:
            return (*common, MemoryItem.state.in_([MemoryState.ACTIVE, MemoryState.STALE]))
        return (
            *common,
            MemoryItem.state == MemoryState.ACTIVE,
            or_(MemoryItem.valid_from.is_(None), MemoryItem.valid_from <= now),
            or_(MemoryItem.valid_until.is_(None), MemoryItem.valid_until > now),
        )

    def active_for_user(
        self,
        session: Session,
        user_id: UUID,
        *,
        limit: int = 100,
        project_ids: tuple[UUID, ...] = (),
        history: bool = False,
        offset: int = 0,
        prioritize: bool = False,
    ) -> list[MemoryItem]:
        order = [MemoryItem.observed_at.desc(), MemoryItem.id]
        if prioritize:
            order = [
                case(
                    (MemoryItem.memory_type == "constraint", 0),
                    (MemoryItem.memory_type == "fact", 1),
                    (MemoryItem.memory_type.in_(["decision", "goal"]), 2),
                    (MemoryItem.memory_type == "preference", 3),
                    else_=4,
                ),
                MemoryItem.confidence.desc(),
                *order,
            ]
        return list(
            session.scalars(
                select(MemoryItem)
                .where(*self.predicates(user_id, project_ids=project_ids, history=history))
                .order_by(*order)
                .offset(max(0, offset))
                .limit(max(1, min(limit, 1000)))
            )
        )

    def search(
        self,
        session: Session,
        user_id: UUID,
        query: str,
        *,
        limit: int = 50,
        project_ids: tuple[UUID, ...] = (),
        history: bool = False,
    ) -> list[MemoryItem]:
        words = sorted(terms(query))[:32]
        if not words:
            return []
        normalized = func.lower(MemoryItem.summary)
        for accented, plain in zip("àâäéèêëîïôöùûüç", "aaaeeeeiioouuuc", strict=True):
            normalized = func.replace(normalized, accented, plain)
            normalized = func.replace(normalized, accented.upper(), plain)
        postgresql = session.get_bind().dialect.name == "postgresql"
        # PostgreSQL FTS handles French stemming; this fallback handles exact
        # accent-insensitive words without matching inside unrelated words.
        matches = [
            normalized.op("~")(rf"(^|[^a-z0-9]){word}([^a-z0-9]|$)")
            if postgresql
            else normalized.contains(word, autoescape=True)
            for word in words
        ]
        score = sum(case((match, 1), else_=0) for match in matches)
        match_filter = or_(*matches)
        if postgresql:
            config = literal_column("'french'::regconfig")
            document = func.to_tsvector(config, MemoryItem.summary)
            # Keep accents for French stemming; the accent-free words above are
            # reserved for the exact-word fallback and must not feed the FTS parser.
            source_words = sorted(
                {
                    word
                    for word in re.findall(r"[^\W_]+", query.casefold())
                    if normalize(word) in words
                }
            )
            search_query = func.websearch_to_tsquery(config, " OR ".join(source_words))
            match_filter = or_(match_filter, document.op("@@")(search_query))
            score = score + func.ts_rank_cd(document, search_query)
        return list(
            session.scalars(
                select(MemoryItem)
                .where(
                    *self.predicates(user_id, project_ids=project_ids, history=history),
                    match_filter,
                )
                .order_by(
                    score.desc(),
                    case(
                        (MemoryItem.memory_type == "constraint", 0),
                        (MemoryItem.memory_type == "fact", 1),
                        else_=2,
                    ),
                    MemoryItem.observed_at.desc(),
                    MemoryItem.id,
                )
                .limit(max(1, min(limit, 100)))
            )
        )

    def soft_delete(self, session: Session, memory: MemoryItem) -> None:
        memory.deleted_at = datetime.now(UTC)
        memory.state = MemoryState.DISMISSED

    def active_summary_keys(self, session: Session, user_id: UUID) -> set[str]:
        now = datetime.now(UTC)
        return {
            summary_key(summary)
            for summary in session.scalars(
                select(MemoryItem.summary)
                .where(
                    MemoryItem.user_id == user_id,
                    MemoryItem.owner_type == "user",
                    MemoryItem.state == MemoryState.ACTIVE,
                    MemoryItem.deleted_at.is_(None),
                    or_(MemoryItem.valid_from.is_(None), MemoryItem.valid_from <= now),
                    or_(MemoryItem.valid_until.is_(None), MemoryItem.valid_until > now),
                )
                .execution_options(yield_per=500)
            )
        }
