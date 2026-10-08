"""Leased, retryable indexing. Provider calls hold no database transaction."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.auth.consents import minimum_policy_version
from app.modules.auth.models import User, UserConsent
from app.modules.memory.embeddings import (
    configuration_hash,
    content_hash,
    embed,
    embedding_text,
    write_vector,
)
from app.modules.memory.models import MemoryEmbedding
from app.modules.memory.policy import memory_allowed
from app.modules.neural.models import MemoryItem, MemoryState
from app.modules.personal.models import PersonalProject

logger = logging.getLogger(__name__)


def _utc(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value


def _queue(session: Session, memory: MemoryItem, config: str) -> None:
    values = {
        "memory_id": memory.id,
        "config_hash": config,
        "content_hash": content_hash(memory),
        "status": "pending",
        "attempt": 0,
    }
    if session.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    session.execute(
        insert(MemoryEmbedding)
        .values(**values)
        .on_conflict_do_nothing(index_elements=["memory_id"])
    )


def process_once(
    session_factory: Callable[[], Session], worker_id: str | None = None
) -> UUID | None:
    settings = get_settings()
    if not settings.memory_embeddings_enabled:
        return None
    config = configuration_hash(settings)
    token = f"{worker_id or 'memory'}-{uuid4().hex}"[:80]
    now = datetime.now(UTC)
    with session_factory() as session:
        consent = (
            select(UserConsent.id)
            .where(
                UserConsent.user_id == MemoryItem.user_id,
                UserConsent.policy_key == "assistant.memory",
                UserConsent.policy_version >= minimum_policy_version("assistant.memory"),
                UserConsent.revoked_at.is_(None),
            )
            .exists()
        )
        accessible_project = MemoryItem.scope_id.in_(
            select(PersonalProject.id).where(PersonalProject.user_id == MemoryItem.user_id)
        )
        memory = session.scalar(
            select(MemoryItem)
            .join(User, User.id == MemoryItem.user_id)
            .outerjoin(MemoryEmbedding, MemoryEmbedding.memory_id == MemoryItem.id)
            .where(
                User.enable_assistant.is_(True),
                User.is_active.is_(True),
                consent,
                MemoryItem.owner_type == "user",
                MemoryItem.state == MemoryState.ACTIVE,
                MemoryItem.deleted_at.is_(None),
                or_(
                    MemoryItem.scope_type == "personal",
                    and_(MemoryItem.scope_type == "project", accessible_project),
                ),
                or_(MemoryItem.valid_from.is_(None), MemoryItem.valid_from <= now),
                or_(MemoryItem.valid_until.is_(None), MemoryItem.valid_until > now),
                or_(
                    MemoryEmbedding.memory_id.is_(None),
                    MemoryEmbedding.config_hash != config,
                    and_(
                        MemoryEmbedding.status != "ready",
                        MemoryEmbedding.attempt < 5,
                        or_(
                            MemoryEmbedding.lease_until.is_(None),
                            MemoryEmbedding.lease_until <= now,
                        ),
                        or_(MemoryEmbedding.retry_at.is_(None), MemoryEmbedding.retry_at <= now),
                    ),
                ),
            )
            .order_by(MemoryItem.observed_at, MemoryItem.id)
            .limit(1)
        )
        if memory is None:
            return None
        _queue(session, memory, config)
        session.flush()
        indexed = session.get(MemoryEmbedding, memory.id)
        if indexed is None:
            return None
        if indexed.config_hash != config:
            indexed.config_hash = config
            indexed.content_hash = content_hash(memory)
            indexed.status = "pending"
            indexed.attempt = 0
            indexed.vector = None
            indexed.lease_until = None
            indexed.retry_at = None
            session.flush()
        lease = now + timedelta(seconds=settings.memory_embedding_timeout_seconds + 30)
        claimed = session.execute(
            update(MemoryEmbedding)
            .where(
                MemoryEmbedding.memory_id == memory.id,
                MemoryEmbedding.config_hash == config,
                MemoryEmbedding.status != "ready",
                or_(MemoryEmbedding.lease_until.is_(None), MemoryEmbedding.lease_until <= now),
            )
            .values(
                status="running",
                lease_owner=token,
                lease_until=lease,
                attempt=MemoryEmbedding.attempt + 1,
            )
        )
        if claimed.rowcount != 1:
            session.rollback()
            return None
        memory_id, user_id = memory.id, memory.user_id
        value, digest = embedding_text(memory), content_hash(memory)
        session.commit()

    try:
        vector = embed(value, settings=settings)
        with session_factory() as session:
            finished_at = datetime.now(UTC)
            # Serialize completion with correction/forgetting and consent revocation.
            consent = session.scalar(
                select(UserConsent)
                .where(UserConsent.user_id == user_id, UserConsent.policy_key == "assistant.memory")
                .with_for_update()
            )
            memory = session.scalar(
                select(MemoryItem)
                .where(MemoryItem.id == memory_id, MemoryItem.user_id == user_id)
                .with_for_update()
            )
            indexed = session.scalar(
                select(MemoryEmbedding)
                .where(
                    MemoryEmbedding.memory_id == memory_id,
                    MemoryEmbedding.lease_owner == token,
                    MemoryEmbedding.config_hash == config,
                )
                .with_for_update()
            )
            if indexed is None:
                return memory_id
            if (
                consent is None
                or not memory_allowed(session, user_id)
                or memory is None
                or memory.state != MemoryState.ACTIVE
                or memory.deleted_at is not None
                or content_hash(memory) != digest
                or (
                    _utc(memory.valid_until) is not None and _utc(memory.valid_until) <= finished_at
                )
            ):
                session.execute(
                    delete(MemoryEmbedding).where(
                        MemoryEmbedding.memory_id == memory_id,
                        MemoryEmbedding.lease_owner == token,
                    )
                )
                session.commit()
                return memory_id
            if settings.memory_vector_enabled:
                write_vector(session, memory_id, config, digest, vector)
            indexed.vector = vector
            indexed.status = "ready"
            indexed.error_code = None
            indexed.lease_owner = None
            indexed.lease_until = None
            indexed.retry_at = None
            session.commit()
        logger.info("memory_index_finished status=ready")
    except (httpx.HTTPError, ValueError, TypeError, SQLAlchemyError):
        with session_factory() as session:
            indexed = session.scalar(
                select(MemoryEmbedding)
                .where(
                    MemoryEmbedding.memory_id == memory_id,
                    MemoryEmbedding.lease_owner == token,
                )
                .with_for_update()
            )
            if indexed is not None:
                indexed.status = "failed"
                indexed.error_code = "embedding_unavailable"
                indexed.lease_owner = None
                indexed.lease_until = None
                indexed.retry_at = datetime.now(UTC) + timedelta(
                    seconds=min(3600, 30 * 2**indexed.attempt)
                )
                session.commit()
        logger.warning("memory_index_finished status=failed")
    return memory_id
