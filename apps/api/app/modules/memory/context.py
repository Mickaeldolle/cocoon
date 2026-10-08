"""Byte-bounded memory context for the personal assistant."""

import json
import re
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.memory.repository import MemoryRepository
from app.modules.memory.retriever import MemoryRetriever
from app.modules.memory.text import normalize


class ContextBuilder:
    def __init__(self, retriever: MemoryRetriever | None = None) -> None:
        self.retriever = retriever or MemoryRetriever()

    def memory_context(
        self,
        session: Session,
        user_id: UUID,
        *,
        query: str | None = None,
        limit: int = 12,
        project_ids: tuple[UUID, ...] = (),
    ) -> list[dict[str, object]]:
        # UTF-8 bytes conservatively bound tokens when the provider tokenizer is unknown.
        budget = get_settings().memory_context_tokens
        result: list[dict[str, object]] = []
        historical = bool(
            re.search(
                r"\b(avant|autrefois|ancienne?|precedemment)\b|pourquoi.*\b(choisi|retenu|decide)\b",
                normalize(query or ""),
            )
        )
        for item in self.retriever.retrieve(
            session, user_id, query=query, limit=50, project_ids=project_ids, history=historical
        ):
            entry = {
                "id": str(item.id),
                "summary": item.summary,
                "type": item.memory_type.value,
                "layer": item.layer.value,
                "state": item.state.value,
                "scope": item.scope_type,
                "scope_id": str(item.scope_id) if item.scope_id else None,
                "origin": item.origin,
                "observed_at": item.observed_at.isoformat(),
                "valid_from": item.valid_from.isoformat() if item.valid_from else None,
                "valid_until": item.valid_until.isoformat() if item.valid_until else None,
                "source_message_id": str(item.source_message_id)
                if item.source_message_id
                else None,
                "capture_id": str(item.capture_id),
                "confidence_indicator": item.confidence,
            }
            cost = len(json.dumps(entry, ensure_ascii=False).encode("utf-8")) + 32
            if cost > budget:
                continue
            result.append(entry)
            budget -= cost
            if len(result) >= limit:
                break
        return result


def accessible_memory_summary_keys(session: Session, user_id: UUID) -> set[str]:
    """Return normalized summary keys from active personal memories only."""
    return MemoryRepository().active_summary_keys(session, user_id)
