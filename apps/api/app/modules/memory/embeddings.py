"""Local Ollama embeddings and optional exact pgvector search."""

import hashlib
import json
import logging
import math
from uuid import UUID

import httpx
from sqlalchemy import Float, Uuid, bindparam, cast, column, func, select, table, text, type_coerce
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.types import UserDefinedType

from app.core.config import Settings, get_settings
from app.modules.memory.models import MemoryEmbedding
from app.modules.memory.repository import MemoryRepository
from app.modules.neural.models import MemoryItem

logger = logging.getLogger(__name__)


class _VectorType(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kw) -> str:
        return "vector"


def configuration_hash(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    value = [
        settings.memory_embedding_base_url,
        settings.memory_embedding_model,
        settings.memory_embedding_revision,
        settings.memory_embedding_dimensions,
        "personal-v1",
        settings.memory_vector_enabled,
    ]
    return hashlib.sha256(json.dumps(value).encode()).hexdigest()


def embedding_text(memory: MemoryItem) -> str:
    return json.dumps(
        {
            "summary": memory.summary,
            "entity": memory.entity,
            "attribute": memory.attribute,
            "value": memory.value,
            "scope": memory.scope_type,
            "scope_id": str(memory.scope_id) if memory.scope_id else None,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def content_hash(memory: MemoryItem) -> str:
    return hashlib.sha256(embedding_text(memory).encode()).hexdigest()


def embed(value: str, *, query: bool = False, settings: Settings | None = None) -> list[float]:
    settings = settings or get_settings()
    if query:
        value = (
            "Instruct: Retrieve personal memories relevant to the user's question.\nQuery: " + value
        )
    timeout = (
        settings.memory_query_timeout_seconds
        if query
        else settings.memory_embedding_timeout_seconds
    )
    with httpx.Client(
        timeout=httpx.Timeout(timeout, connect=min(5, timeout)), trust_env=False
    ) as client:
        response = client.post(
            settings.memory_embedding_base_url + "/api/embed",
            json={
                "model": settings.memory_embedding_model,
                "input": value,
                "dimensions": settings.memory_embedding_dimensions,
                "truncate": False,
            },
        )
        response.raise_for_status()
        vectors = response.json().get("embeddings")
    if not isinstance(vectors, list) or len(vectors) != 1:
        raise ValueError("invalid_embeddings")
    vector = vectors[0]
    if not isinstance(vector, list) or len(vector) != settings.memory_embedding_dimensions:
        raise ValueError("invalid_dimensions")
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in vector):
        raise ValueError("invalid_vector")
    try:
        floats = [float(x) for x in vector]
    except OverflowError as error:
        raise ValueError("invalid_vector") from error
    if not all(math.isfinite(x) for x in floats):
        raise ValueError("invalid_vector")
    norm = math.hypot(*floats)
    if not math.isfinite(norm) or norm == 0:
        raise ValueError("invalid_norm")
    return [x / norm for x in floats]


def install_vector_storage(session: Session) -> None:
    if session.get_bind().dialect.name != "postgresql":
        raise ValueError("pgvector requiert PostgreSQL")
    # Explicit setup command only. Never install an extension from an HTTP request.
    session.execute(text("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public"))
    vector_namespace(session)
    session.execute(
        text("""
        CREATE TABLE IF NOT EXISTS memory_vector_index (
            memory_id uuid PRIMARY KEY REFERENCES memory_items(id) ON DELETE CASCADE,
            config_hash varchar(64) NOT NULL,
            content_hash varchar(64) NOT NULL,
            embedding vector NOT NULL
        )
    """)
    )


def vector_namespace(session: Session) -> None:
    # Managed PostgreSQL can install pgvector in an 'extensions' schema.
    session.execute(
        text("""
        SELECT set_config('search_path', current_setting('search_path') || ',' ||
            quote_ident(n.nspname), true)
        FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace
        WHERE e.extname = 'vector'
    """)
    )


def vector_storage_exists(session: Session) -> bool:
    return session.get_bind().dialect.name == "postgresql" and bool(
        session.scalar(text("SELECT to_regclass('memory_vector_index') IS NOT NULL"))
    )


def write_vector(
    session: Session, memory_id: UUID, config: str, digest: str, vector: list[float]
) -> None:
    vector_namespace(session)
    session.execute(
        text("""
        INSERT INTO memory_vector_index (memory_id, config_hash, content_hash, embedding)
        VALUES (:id, :config, :digest, CAST(:vector AS vector))
        ON CONFLICT (memory_id) DO UPDATE SET config_hash = EXCLUDED.config_hash,
            content_hash = EXCLUDED.content_hash, embedding = EXCLUDED.embedding
    """),
        {"id": memory_id, "config": config, "digest": digest, "vector": json.dumps(vector)},
    )


def semantic_search(
    session: Session,
    user_id: UUID,
    query: str,
    *,
    project_ids: tuple[UUID, ...] = (),
) -> list[MemoryItem]:
    settings = get_settings()
    if session.get_bind().dialect.name != "postgresql":
        logger.info("memory_vector_degraded reason=postgresql_required")
        return []
    try:
        if not vector_storage_exists(session):
            logger.info("memory_vector_degraded reason=storage_missing")
            return []
        vector_namespace(session)
        vector = embed(query, query=True, settings=settings)
        # Materialize the authorized, valid corpus before computing distances.
        owners = select(MemoryItem.id).where(
            *MemoryRepository().predicates(user_id, project_ids=project_ids)
        )
        vectors = table(
            "memory_vector_index",
            column("memory_id", Uuid()),
            column("config_hash"),
            column("content_hash"),
            column("embedding"),
        )
        authorized = (
            select(vectors.c.memory_id, vectors.c.embedding)
            .join(MemoryEmbedding, MemoryEmbedding.memory_id == vectors.c.memory_id)
            .where(
                vectors.c.memory_id.in_(owners),
                vectors.c.config_hash == configuration_hash(settings),
                MemoryEmbedding.status == "ready",
                MemoryEmbedding.config_hash == vectors.c.config_hash,
                MemoryEmbedding.content_hash == vectors.c.content_hash,
                func.vector_dims(vectors.c.embedding) == len(vector),
            )
            .cte("authorized")
            .prefix_with("MATERIALIZED")
        )
        distance = type_coerce(
            authorized.c.embedding.op("<=>")(cast(bindparam("query_vector"), _VectorType())),
            Float,
        )
        ids_query = (
            select(authorized.c.memory_id)
            .where(1 - distance >= settings.memory_min_similarity)
            .order_by(distance, authorized.c.memory_id)
            .limit(50)
        )
        with session.begin_nested():
            ids = list(session.scalars(ids_query, {"query_vector": json.dumps(vector)}))
        memories = {
            item.id: item
            for item in session.scalars(
                select(MemoryItem).where(
                    *MemoryRepository().predicates(user_id, project_ids=project_ids),
                    MemoryItem.id.in_(ids),
                )
            )
        }
        return [memories[item_id] for item_id in ids if item_id in memories]
    except (httpx.HTTPError, ValueError, TypeError, SQLAlchemyError):
        # Do not log response bodies or private text.
        logger.warning("memory_vector_degraded reason=embedding_or_storage_unavailable")
        return []


def delete_vectors(session: Session, ids: list[UUID]) -> None:
    session.query(MemoryEmbedding).filter(MemoryEmbedding.memory_id.in_(ids)).delete(
        synchronize_session=False
    )
    if vector_storage_exists(session):
        session.execute(
            text("DELETE FROM memory_vector_index WHERE memory_id IN :ids").bindparams(
                bindparam("ids", expanding=True)
            ),
            {"ids": ids},
        )
