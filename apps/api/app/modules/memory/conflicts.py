"""Conservative contradiction handling for explicitly stated preferences."""

import re
import unicodedata
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.neural.models import MemoryItem, MemoryState, MemoryType

_PREFERENCE_MARKERS = (
    "je prefere",
    "la personne prefere",
    "je n aime pas",
    "la personne n aime pas",
)
_SUBJECT_GROUPS = {
    "beverage": ("cafe", "the", "tisane"),
    "diet": ("repas", "vegetarien", "porc", "noix", "viande"),
    "schedule": ("matin", "soir", "tot", "tard", "heure"),
    "technology": ("python", "fastapi", "vue", "react", "docker", "kubernetes"),
    "exercise": ("courir", "course", "sport", "velo", "natation"),
}


def _normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9 ]+", " ", without_accents).strip()


def preference_subject(summary: str) -> str | None:
    """Return a subject marker only for explicit preference statements."""
    normalized = _normalized(summary)
    for marker in _PREFERENCE_MARKERS:
        if marker in normalized:
            tail = normalized.split(marker, maxsplit=1)[1].strip()
            for subject, terms in _SUBJECT_GROUPS.items():
                if any(re.search(rf"\b{re.escape(term)}\b", tail) for term in terms):
                    return subject
            # Unknown subjects only conflict when their first meaningful token
            # is identical; unrelated preferences must never be collapsed.
            stop_words = {"le", "la", "les", "un", "une", "de", "des", "pour"}
            words = [word for word in tail.split() if word not in stop_words]
            return f"generic:{words[0]}" if words else None
    return None


def supersede_conflicting_preference(
    session: Session,
    user_id: UUID,
    summary: str,
    *,
    now: datetime | None = None,
) -> MemoryItem | None:
    """Mark the latest matching preference stale and return it for provenance."""
    subject = preference_subject(summary)
    if subject is None:
        return None
    effective_now = now or datetime.now(UTC)
    candidates = session.scalars(
        select(MemoryItem)
        .where(
            MemoryItem.user_id == user_id,
            MemoryItem.owner_type == "user",
            MemoryItem.scope_type == "personal",
            MemoryItem.memory_type == MemoryType.PREFERENCE,
            MemoryItem.state == MemoryState.ACTIVE,
            MemoryItem.deleted_at.is_(None),
            or_(MemoryItem.valid_from.is_(None), MemoryItem.valid_from <= effective_now),
            or_(MemoryItem.valid_until.is_(None), MemoryItem.valid_until > effective_now),
        )
        .order_by(MemoryItem.created_at.desc())
    )
    existing = next(
        (candidate for candidate in candidates if preference_subject(candidate.summary) == subject),
        None,
    )
    if existing is None:
        return None
    timestamp = effective_now
    existing.state = MemoryState.STALE
    existing.valid_until = timestamp
    return existing
