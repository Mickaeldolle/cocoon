"""Opt-in integration tests, restricted to a disposable PostgreSQL database."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import Base
from app.modules.assistant.executor import execute_assistant_proposal
from app.modules.assistant.models import (
    AssistantMessage,
    AssistantMessageRole,
    AssistantProposal,
    AssistantProposalKind,
    AssistantThread,
)
from app.modules.auth.models import User, UserConsent
from app.modules.memory import embeddings, worker
from app.modules.memory.models import MemoryEmbedding
from app.modules.memory.repository import MemoryRepository
from app.modules.memory.retriever import MemoryRetriever
from app.modules.memory.schemas import MemoryCorrectionRequest
from app.modules.memory.service import correct_memory, forget_memory
from app.modules.neural.models import Capture, CaptureSource, MemoryItem, MemoryKind


@pytest.fixture
def postgres_factory(monkeypatch):
    url = os.getenv("MEMORY_TEST_DATABASE_URL")
    local_schema = os.getenv("MEMORY_TEST_LOCAL_SCHEMA") == "1"
    if local_schema and url:
        raise ValueError("Choose a disposable test database or the local isolated schema")
    if local_schema:
        url = get_settings().database_url
    if not url:
        pytest.skip("MEMORY_TEST_DATABASE_URL must name a disposable PostgreSQL test database")
    parsed = make_url(url)
    safe_local = (
        local_schema and parsed.host in {"127.0.0.1", "localhost"} and parsed.database == "cocoon"
    )
    safe_disposable = not local_schema and (parsed.database or "").endswith(("_test", "_ci"))
    if parsed.get_backend_name() != "postgresql" or not (safe_local or safe_disposable):
        raise ValueError(
            "Integration tests require a disposable _test/_ci database or "
            "MEMORY_TEST_LOCAL_SCHEMA=1 on local cocoon PostgreSQL"
        )
    schema = "memory_test_" + uuid4().hex
    root = create_engine(url)
    with root.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = get_settings()
    monkeypatch.setattr(settings, "memory_embeddings_enabled", False)
    monkeypatch.setattr(settings, "memory_vector_enabled", False)
    monkeypatch.setattr(settings, "memory_embedding_dimensions", 2)
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT current_schema()")) == schema
            assert connection.scalar(text("SELECT to_regclass('memory_items')")) is None
        # Fully qualify test tables, even if the database already has public tables.
        Base.metadata.create_all(engine.execution_options(schema_translate_map={None: schema}))
        with root.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT to_regclass(:table_name)"),
                    {"table_name": f"{schema}.memory_items"},
                )
                is not None
            )
        with factory() as session:
            # create_all does not run the PostgreSQL-only Alembic FTS index.
            session.execute(
                text(
                    "CREATE INDEX ix_memory_items_fts ON memory_items USING gin "
                    "(to_tsvector('french'::regconfig, summary))"
                )
            )
            session.commit()
        yield factory
    finally:
        engine.dispose()
        # The generated schema is private to this test; never delete the configured database.
        assert schema.startswith("memory_test_") and len(schema) == 44
        with root.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        root.dispose()


@pytest.fixture
def postgres_vector_factory(postgres_factory, monkeypatch):
    factory = postgres_factory
    with factory() as session:
        if not session.scalar(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")):
            pytest.skip("pgvector is not installed on this PostgreSQL server")
        embeddings.install_vector_storage(session)
        assert embeddings.vector_storage_status(session)["ready"] is True
        session.commit()
    settings = get_settings()
    monkeypatch.setattr(settings, "memory_embeddings_enabled", True)
    monkeypatch.setattr(settings, "memory_vector_enabled", True)
    return factory


def corpus(factory):
    with factory() as session:
        user = User(
            email="memory@example.com",
            display_name="Test",
            password_hash="unused",
            enable_assistant=True,
        )
        other = User(
            email="other@example.com",
            display_name="Other",
            password_hash="unused",
            enable_assistant=True,
        )
        session.add_all([user, other])
        session.flush()
        items = []
        for account in (user, other):
            session.add(
                UserConsent(user_id=account.id, policy_key="assistant.memory", policy_version=1)
            )
            capture = Capture(
                user_id=account.id, content="Développeur Python", source=CaptureSource.TEXT
            )
            session.add(capture)
            session.flush()
            memory = MemoryItem(
                user_id=account.id,
                capture_id=capture.id,
                kind=MemoryKind.INFORMATION,
                summary="Je développe avec Python",
                reason="explicit",
                observed_at=datetime.now(UTC),
            )
            session.add(memory)
            session.flush()
            items.append(memory.id)
        session.commit()
        return user.id, other.id, items


def test_fulltext_and_vector_search_obey_owner_configuration_and_forgetting(
    postgres_vector_factory, monkeypatch
):
    factory = postgres_vector_factory
    user_id, _, ids = corpus(factory)
    monkeypatch.setattr(worker, "embed", lambda *_, **__: [1.0, 0.0])
    monkeypatch.setattr(embeddings, "embed", lambda *_, **__: [1.0, 0.0])
    assert worker.process_once(factory)
    assert worker.process_once(factory)
    with factory() as session:
        assert [
            item.id for item in MemoryRetriever().retrieve(session, user_id, query="profession")
        ] == [ids[0]]
        # French stemming is exercised independently from semantic similarity.
        get_settings().memory_embeddings_enabled = False
        assert [
            item.id for item in MemoryRetriever().retrieve(session, user_id, query="développer")
        ] == [ids[0]]
        get_settings().memory_embeddings_enabled = True
        forget_memory(session, user_id, ids[0])
        assert (
            session.scalar(select(MemoryEmbedding).where(MemoryEmbedding.memory_id == ids[0]))
            is None
        )
        assert MemoryRetriever().retrieve(session, user_id, query="profession") == []


def test_concurrent_indexers_claim_one_job_each(postgres_vector_factory, monkeypatch):
    factory = postgres_vector_factory
    _, _, ids = corpus(factory)
    monkeypatch.setattr(worker, "embed", lambda *_, **__: [1.0, 0.0])
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: worker.process_once(factory), range(2)))
    # A loser can yield instead of claiming another row; no duplicate provider work.
    completed = [result for result in results if result is not None]
    assert len(completed) == len(set(completed))
    while worker.process_once(factory) is not None:
        pass
    with factory() as session:
        assert session.scalar(text("SELECT count(*) FROM memory_vector_index")) == len(ids)


@pytest.mark.parametrize("operation", ["correction", "confirmation"])
def test_memory_write_waits_for_consent_revocation(postgres_factory, operation):
    factory = postgres_factory
    with factory() as session:
        user = User(
            email=f"consent-{uuid4().hex}@example.com",
            display_name="Consent test",
            password_hash="unused",
            enable_assistant=True,
        )
        session.add(user)
        session.flush()
        session.add(UserConsent(user_id=user.id, policy_key="assistant.memory", policy_version=1))
        capture = Capture(user_id=user.id, content="Je préfère Python", source=CaptureSource.TEXT)
        session.add(capture)
        session.flush()
        memory = MemoryItem(
            user_id=user.id,
            capture_id=capture.id,
            kind=MemoryKind.INFORMATION,
            summary="Je préfère Python",
            reason="explicit",
        )
        session.add(memory)
        thread = AssistantThread(user_id=user.id)
        session.add(thread)
        session.flush()
        source = AssistantMessage(
            thread_id=thread.id,
            role=AssistantMessageRole.USER,
            content="Je préfère Python",
        )
        session.add(source)
        session.flush()
        reply = AssistantMessage(
            thread_id=thread.id,
            role=AssistantMessageRole.ASSISTANT,
            content="Bien compris.",
            source_user_message_id=source.id,
        )
        session.add(reply)
        session.flush()
        proposal = AssistantProposal(
            user_id=user.id,
            assistant_message_id=reply.id,
            kind=AssistantProposalKind.NOTE,
            payload={"summary": "Je pratique le piano"},
        )
        session.add(proposal)
        session.commit()
        user_id, memory_id, proposal_id = user.id, memory.id, proposal.id

    with factory() as revoker:
        consent = revoker.scalar(
            select(UserConsent)
            .where(UserConsent.user_id == user_id, UserConsent.policy_key == "assistant.memory")
            .with_for_update()
        )
        assert consent is not None
        started = Event()
        name = f"memory-{operation}-{uuid4().hex}"

        def attempt_write() -> int:
            with factory() as session:
                session.execute(
                    text("SELECT set_config('application_name', :name, false)"), {"name": name}
                )
                started.set()
                try:
                    if operation == "correction":
                        correct_memory(
                            session,
                            user_id,
                            memory_id,
                            MemoryCorrectionRequest(summary="Je préfère Rust"),
                        )
                    else:
                        proposal = session.get(AssistantProposal, proposal_id)
                        assert proposal is not None
                        execute_assistant_proposal(session, proposal, user_id)
                except HTTPException as error:
                    session.rollback()
                    return error.status_code
                session.commit()
                return 200

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(attempt_write)
            blocked = False
            try:
                assert started.wait(5)
                with factory() as observer:
                    deadline = monotonic() + 5
                    while monotonic() < deadline:
                        wait_type = observer.scalar(
                            text(
                                "SELECT wait_event_type FROM pg_stat_activity "
                                "WHERE application_name = :name"
                            ),
                            {"name": name},
                        )
                        observer.rollback()  # Read a fresh pg_stat_activity snapshot.
                        if wait_type == "Lock":
                            blocked = True
                            break
                        if future.done():
                            break
                        sleep(0.05)
            finally:
                consent.revoked_at = datetime.now(UTC)
                revoker.commit()
            assert blocked
            assert future.result(timeout=5) == 403
    with factory() as session:
        replacement = session.scalar(
            select(MemoryItem).where(MemoryItem.supersedes_id == memory_id)
        )
        assert replacement is None
        assert (
            session.scalar(select(MemoryItem).where(MemoryItem.summary == "Je pratique le piano"))
            is None
        )


def test_fulltext_keeps_stemming_without_substring_false_positives(postgres_factory):
    factory = postgres_factory
    user_id, _, ids = corpus(factory)
    with factory() as session:
        capture = Capture(user_id=user_id, content="Lexical test", source=CaptureSource.TEXT)
        session.add(capture)
        session.flush()
        art = MemoryItem(
            user_id=user_id,
            capture_id=capture.id,
            kind=MemoryKind.INFORMATION,
            summary="Je pratique l'art",
            reason="explicit",
        )
        carton = MemoryItem(
            user_id=user_id,
            capture_id=capture.id,
            kind=MemoryKind.INFORMATION,
            summary="Le carton est prêt",
            reason="explicit",
        )
        session.add_all([art, carton])
        session.commit()
        get_settings().memory_embeddings_enabled = False
        assert [item.id for item in MemoryRetriever().retrieve(session, user_id, query="art")] == [
            art.id
        ]
        assert [
            item.id for item in MemoryRetriever().retrieve(session, user_id, query="développer")
        ] == [ids[0]]


def test_postgres_search_plan_at_100_and_1000_memories(postgres_factory):
    factory = postgres_factory
    user_id, other_id, _ = corpus(factory)
    reports = []
    with factory() as session:
        assert session.scalar(text("SELECT to_regclass('ix_memory_items_fts')")) is not None
        capture = Capture(
            user_id=user_id, content="Plan SQL synthétique", source=CaptureSource.TEXT
        )
        session.add(capture)
        session.flush()
        target = MemoryItem(
            user_id=user_id,
            capture_id=capture.id,
            kind=MemoryKind.INFORMATION,
            summary="Le projet Archipel utilise PostgreSQL",
            reason="synthetic target",
        )
        session.add(target)
        session.commit()

        for size, additions in ((100, 98), (1000, 900)):
            session.add_all(
                MemoryItem(
                    user_id=user_id,
                    capture_id=capture.id,
                    kind=MemoryKind.INFORMATION,
                    summary=f"Recette numéro {index}",
                    reason="synthetic filler",
                )
                for index in range(size - additions, size)
            )
            session.commit()
            session.execute(text("ANALYZE memory_items"))
            captured = []

            def record_search(
                _conn, _cursor, statement, parameters, _context, _many, found=captured
            ):
                if "FROM memory_items" in statement and "to_tsvector" in statement:
                    found.append((statement, parameters))

            engine = session.get_bind()
            event.listen(engine, "before_cursor_execute", record_search)
            try:
                matches = MemoryRepository().search(session, user_id, "Archipel", limit=5)
            finally:
                event.remove(engine, "before_cursor_execute", record_search)
            assert target.id in {item.id for item in matches}
            assert all(item.user_id != other_id for item in matches)
            assert len(captured) == 1
            statement, parameters = captured[0]
            plan = (
                session.connection()
                .exec_driver_sql("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, parameters)
                .scalar_one()
            )
            if isinstance(plan, str):
                plan = json.loads(plan)
            root = plan[0]
            reports.append(
                {
                    "owner_memories": size,
                    "execution_ms": root["Execution Time"],
                    "planning_ms": root["Planning Time"],
                    "plan": root["Plan"],
                }
            )

    output = os.getenv("MEMORY_PG_PLAN_OUTPUT")
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(reports, indent=2) + "\n", encoding="utf-8")
