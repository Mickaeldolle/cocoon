"""Opt-in integration tests, restricted to a disposable PostgreSQL database."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import Base
from app.modules.auth.models import User, UserConsent
from app.modules.memory import embeddings, worker
from app.modules.memory.models import MemoryEmbedding
from app.modules.memory.retriever import MemoryRetriever
from app.modules.memory.service import forget_memory
from app.modules.neural.models import Capture, CaptureSource, MemoryItem, MemoryKind


@pytest.fixture
def postgres_factory(monkeypatch):
    url = os.getenv("MEMORY_TEST_DATABASE_URL")
    if not url:
        pytest.skip("MEMORY_TEST_DATABASE_URL must name a disposable PostgreSQL test database")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or not (parsed.database or "").endswith(
        ("_test", "_ci")
    ):
        raise ValueError("Integration tests require a database name ending in _test or _ci")
    schema = "memory_test_" + uuid4().hex
    root = create_engine(url)
    with root.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema},public"})
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = get_settings()
    monkeypatch.setattr(settings, "memory_embeddings_enabled", True)
    monkeypatch.setattr(settings, "memory_vector_enabled", True)
    monkeypatch.setattr(settings, "memory_embedding_dimensions", 2)
    try:
        Base.metadata.create_all(engine)
        with factory() as session:
            embeddings.install_vector_storage(session)
            session.commit()
        yield factory
    finally:
        engine.dispose()
        # The generated schema is private to this test; never delete the configured database.
        with root.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        root.dispose()


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
    postgres_factory, monkeypatch
):
    factory = postgres_factory
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


def test_concurrent_indexers_claim_one_job_each(postgres_factory, monkeypatch):
    factory = postgres_factory
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
