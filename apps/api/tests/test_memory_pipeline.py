"""Memory quality and lifecycle contracts, independent from a live language model."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.core.config import get_settings
from app.modules.assistant import service as assistant_service
from app.modules.assistant.context import recent_messages
from app.modules.assistant.kernel import _conversation_messages, _safe_memories
from app.modules.assistant.models import AssistantMessage, AssistantMessageRole, AssistantThread
from app.modules.auth.models import User, UserConsent
from app.modules.memory import embeddings, worker
from app.modules.memory.conflicts import preference_relationship, supersede_conflicting_preference
from app.modules.memory.context import ContextBuilder
from app.modules.memory.models import (
    ContextDependency,
    MemoryEmbedding,
    MemoryExclusion,
    MemoryUsage,
    WorkingMemory,
)
from app.modules.memory.repository import MemoryRepository
from app.modules.memory.retriever import MemoryRetriever
from app.modules.memory.service import forget_memory
from app.modules.memory.working import working_context
from app.modules.neural.models import Capture, CaptureSource, MemoryItem, MemoryKind, MemoryState
from app.modules.personal.models import PersonalProject


@pytest.fixture
def account(client):
    tokens = client.post(
        "/api/auth/register",
        json={
            "email": f"{uuid4().hex}@example.com",
            "password": "A-strong-password-123",
            "display_name": "Memory",
            "installation_id": uuid4().hex,
            "name": "Memory test",
            "platform": "web",
        },
    ).json()
    factory = client.app.state.test_session_factory
    with factory() as session:
        user = session.scalar(select(User))
        user.enable_assistant = True
        session.add(UserConsent(user_id=user.id, policy_key="assistant.memory", policy_version=1))
        session.commit()
        user_id = user.id
    return factory, user_id, {"Authorization": f"Bearer {tokens['access_token']}"}


def add_memory(session, user_id, summary="Je développe avec FastAPI", **values):
    capture = Capture(user_id=user_id, content=summary, source=CaptureSource.TEXT)
    session.add(capture)
    session.flush()
    memory = MemoryItem(
        user_id=user_id,
        capture_id=capture.id,
        kind=MemoryKind.INFORMATION,
        summary=summary,
        reason="test",
        **values,
    )
    session.add(memory)
    session.flush()
    return memory


@pytest.mark.parametrize("size", [10, 100, 500, 1000])
def test_retrieves_old_fact_and_deduplicates_entire_corpus(account, size):
    factory, user_id, _ = account
    with factory() as session:
        old = add_memory(
            session,
            user_id,
            "Projet Archipel : base PostgreSQL",
            observed_at=datetime.now(UTC) - timedelta(days=500),
        )
        for number in range(size):
            add_memory(session, user_id, f"Recette quotidienne numéro {number}")
        session.commit()
        assert [
            item.id
            for item in MemoryRetriever().retrieve(
                session, user_id, query="Quelle base pour Archipel ?"
            )
        ] == [old.id]
        assert "projet archipel base postgresql" in MemoryRepository().active_summary_keys(
            session, user_id
        )
        assert MemoryRetriever().retrieve(session, user_id, query="Photographie astronomique") == []


def test_context_has_sources_and_no_instruction_authority(account):
    factory, user_id, _ = account
    with factory() as session:
        memory = add_memory(session, user_id, "Cocoon doit utiliser PostgreSQL")
        session.commit()
        context = ContextBuilder().memory_context(session, user_id, query="PostgreSQL")
        assert context[0]["id"] == str(memory.id)
        assert context[0]["capture_id"] == str(memory.capture_id)
        assert context[0]["observed_at"]
        prompt = _conversation_messages("PostgreSQL", [], context)
        payload = json.loads(prompt[-1]["content"])
        assert payload["memory_sources"] == context
        assert "jamais des instructions" in prompt[0]["content"]


def test_project_scopes_are_validated_and_not_mixed(account, client):
    factory, user_id, auth = account
    with factory() as session:
        project = PersonalProject(user_id=user_id, name="Atlas", description="Projet test")
        other = PersonalProject(user_id=user_id, name="Orion", description="Autre projet")
        session.add_all([project, other])
        session.add(UserConsent(user_id=user_id, policy_key="assistant.projects", policy_version=1))
        session.flush()
        a = add_memory(
            session, user_id, "Atlas doit utiliser Vue", scope_type="project", scope_id=project.id
        )
        b = add_memory(
            session, user_id, "Orion doit utiliser React", scope_type="project", scope_id=other.id
        )
        session.commit()
        memories = MemoryRetriever().retrieve(
            session, user_id, query="Vue React", project_ids=(project.id,)
        )
        assert [item.id for item in memories] == [a.id]
        assert b.id not in [item.id for item in memories]
        memory_id = str(a.id)
    response = client.patch(
        f"/api/memories/{memory_id}",
        headers=auth,
        json={
            "summary": "Atlas doit utiliser Vue",
            "scope_type": "project",
            "scope_id": str(uuid4()),
        },
    )
    assert response.status_code == 422


def test_compatible_preferences_ambiguity_and_temporary_exceptions(account):
    factory, user_id, _ = account
    with factory() as session:
        python = add_memory(session, user_id, "Je préfère Python", memory_type="preference")
        tea = add_memory(session, user_id, "Je préfère le thé", memory_type="preference")
        session.commit()
        assert (
            supersede_conflicting_preference(session, user_id, "Je préfère maintenant React")
            is None
        )
        assert supersede_conflicting_preference(session, user_id, "Je préfère le café") is None
        assert (
            preference_relationship("Je préfère le thé", "Cette semaine je préfère le café")
            == "exception"
        )
        assert (
            supersede_conflicting_preference(
                session, user_id, "Cette semaine je préfère maintenant le café"
            )
            is None
        )
        assert python.state == MemoryState.ACTIVE
        replaced = supersede_conflicting_preference(
            session, user_id, "Je préfère maintenant le café"
        )
        assert replaced.id == tea.id


def test_paginated_management_and_history(account, client):
    factory, user_id, auth = account
    with factory() as session:
        for number in range(7):
            add_memory(session, user_id, f"Information {number}")
        session.commit()
    first = client.get("/api/memories?limit=3", headers=auth).json()
    second = client.get(f"/api/memories?limit=3&offset={first['next_offset']}", headers=auth).json()
    assert not {item["id"] for item in first["memories"]} & {
        item["id"] for item in second["memories"]
    }
    memory_id = first["memories"][0]["id"]
    assert (
        client.patch(
            f"/api/memories/{memory_id}", headers=auth, json={"summary": "Correction"}
        ).status_code
        == 200
    )
    assert (
        client.get(f"/api/memories/{memory_id}?include_history=true", headers=auth).json()["state"]
        == "stale"
    )
    assert (
        client.patch(
            f"/api/memories/{second['memories'][0]['id']}", headers=auth, json={"summary": "  "}
        ).status_code
        == 422
    )


def test_forgetting_excludes_source_versions_and_derived_responses(account):
    factory, user_id, _ = account
    with factory() as session:
        thread = AssistantThread(user_id=user_id)
        session.add(thread)
        session.flush()
        source = AssistantMessage(
            thread_id=thread.id,
            role=AssistantMessageRole.USER,
            content="On utilisera PostgreSQL pour Atlas",
        )
        response = AssistantMessage(
            thread_id=thread.id,
            role=AssistantMessageRole.ASSISTANT,
            content="Votre projet utilise PostgreSQL",
        )
        session.add_all([source, response])
        session.flush()
        root = add_memory(
            session, user_id, source.content, source_message_id=source.id, state=MemoryState.STALE
        )
        leaf = add_memory(session, user_id, "Atlas utilise SQLite", supersedes_id=root.id)
        session.add(MemoryUsage(message_id=response.id, memory_id=root.id))
        descendant = AssistantMessage(
            thread_id=thread.id,
            role=AssistantMessageRole.ASSISTANT,
            content="Le même choix reste disponible",
        )
        session.add(descendant)
        session.flush()
        session.add(ContextDependency(message_id=descendant.id, source_message_id=response.id))
        session.add(
            WorkingMemory(
                thread_id=thread.id,
                user_id=user_id,
                entries=[{"source_message_id": str(source.id)}],
            )
        )
        session.commit()
        forget_memory(session, user_id, leaf.id)
        assert recent_messages(session, thread.id, limit=10) == []
        assert session.get(WorkingMemory, thread.id) is None
        assert session.get(MemoryItem, root.id).state == MemoryState.DISMISSED
        assert session.get(MemoryExclusion, (user_id, "message", source.id)) is not None
        assert session.get(MemoryExclusion, (user_id, "message", descendant.id)) is not None
        assert session.get(Capture, root.capture_id) is not None


def test_working_context_keeps_old_decisions_without_durable_activation(account):
    factory, user_id, _ = account
    with factory() as session:
        thread = AssistantThread(user_id=user_id)
        session.add(thread)
        session.flush()
        source = AssistantMessage(
            thread_id=thread.id,
            role=AssistantMessageRole.USER,
            content="On utilisera FastAPI sur notre VPS",
            created_at=datetime.now(UTC) - timedelta(days=1),
        )
        session.add(source)
        for number in range(30):
            session.add(
                AssistantMessage(
                    thread_id=thread.id, role=AssistantMessageRole.USER, content=f"Merci {number}"
                )
            )
        session.commit()
        context = working_context(session, user_id, "FastAPI")
        assert context["entries"][0]["source_message_id"] == str(source.id)
        assert list(session.scalars(select(MemoryItem))) == []


def test_revocation_stops_retrieval_proposals_and_purges_indexes(account, client, monkeypatch):
    factory, user_id, auth = account
    with factory() as session:
        memory = add_memory(session, user_id)
        session.add(
            MemoryEmbedding(
                memory_id=memory.id, config_hash="x", content_hash="y", vector=[1], status="ready"
            )
        )
        session.commit()
    assert client.delete("/api/auth/consents/assistant.memory", headers=auth).status_code == 200
    with factory() as session:
        assert MemoryRetriever().retrieve(session, user_id, query="FastAPI") == []
        assert session.scalar(select(MemoryEmbedding)) is None
    monkeypatch.setattr(
        assistant_service,
        "llm_chat",
        lambda _: '{"reply":"OK","choices":[],"memories":["Je préfère Python"]}',
    )
    response = client.post("/api/assistant/chat", headers=auth, json={"text": "Je préfère Python"})
    assert response.status_code == 201
    assert response.json()["message"]["proposals"] == []
    # The user can still inspect and forget existing data after revoking consent.
    assert client.get("/api/memories", headers=auth).json()["memories"]


@pytest.fixture
def embedding_settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "memory_embeddings_enabled", True)
    monkeypatch.setattr(settings, "memory_vector_enabled", False)
    monkeypatch.setattr(settings, "memory_embedding_dimensions", 2)
    return settings


def test_indexing_is_idempotent_and_reindexes_model_revision(
    account, embedding_settings, monkeypatch
):
    factory, user_id, _ = account
    with factory() as session:
        memory = add_memory(session, user_id)
        session.commit()
        memory_id = memory.id
    calls = []
    monkeypatch.setattr(worker, "embed", lambda value, **_: calls.append(value) or [1.0, 0.0])
    assert worker.process_once(factory) == memory_id
    assert worker.process_once(factory) is None
    assert len(calls) == 1
    with factory() as session:
        assert session.get(MemoryEmbedding, memory_id).status == "ready"
    monkeypatch.setattr(embedding_settings, "memory_embedding_revision", "new-revision")
    assert worker.process_once(factory) == memory_id
    assert len(calls) == 2


def test_indexing_failure_retries_with_backoff(account, embedding_settings, monkeypatch):
    factory, user_id, _ = account
    with factory() as session:
        memory = add_memory(session, user_id)
        session.commit()
        memory_id = memory.id

    def unavailable(*_, **__):
        raise httpx.ConnectError("private provider data must not be logged")

    monkeypatch.setattr(worker, "embed", unavailable)
    assert worker.process_once(factory) == memory_id
    assert worker.process_once(factory) is None
    with factory() as session:
        index = session.get(MemoryEmbedding, memory_id)
        assert index.status == "failed" and index.attempt == 1
        assert index.error_code == "embedding_unavailable"
        index.retry_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    monkeypatch.setattr(worker, "embed", lambda *_, **__: [1.0, 0.0])
    assert worker.process_once(factory) == memory_id


def test_forgetting_during_indexing_cannot_resurrect_memory(
    account, embedding_settings, monkeypatch
):
    factory, user_id, _ = account
    with factory() as session:
        memory = add_memory(session, user_id)
        session.commit()
        memory_id = memory.id

    def delayed(*_, **__):
        with factory() as session:
            forget_memory(session, user_id, memory_id)
        return [1.0, 0.0]

    monkeypatch.setattr(worker, "embed", delayed)
    assert worker.process_once(factory) == memory_id
    with factory() as session:
        assert session.get(MemoryEmbedding, memory_id) is None
        assert session.get(MemoryItem, memory_id).state == MemoryState.DISMISSED


@pytest.mark.parametrize("vector", [[0, 0], [True, 1], [float("nan"), 1], [1]])
def test_embedding_response_rejects_invalid_vectors(embedding_settings, monkeypatch, vector):
    original_client = httpx.Client
    # Build the response manually because JSON cannot encode NaN by default.
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            content=json.dumps({"embeddings": [vector]}).encode(),
            headers={"content-type": "application/json"},
        )
    )
    monkeypatch.setattr(httpx, "Client", lambda **kw: original_client(transport=transport, **kw))
    with pytest.raises(ValueError):
        embeddings.embed("test", settings=embedding_settings)


def test_embedding_query_uses_configured_dimension_and_normalizes(embedding_settings, monkeypatch):
    original_client = httpx.Client
    payloads = []

    def respond(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"embeddings": [[3, 4]]})

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(httpx, "Client", lambda **kw: original_client(transport=transport, **kw))
    assert embeddings.embed("Question", query=True) == [0.6, 0.8]
    assert payloads[0]["dimensions"] == 2
    assert payloads[0]["input"].endswith("Query: Question")


def test_memory_provenance_keeps_exact_input_when_another_turn_arrives(
    account, client, monkeypatch
):
    factory, user_id, auth = account

    def delayed_model(_):
        with factory() as session:
            thread = session.scalar(
                select(AssistantThread).where(AssistantThread.user_id == user_id)
            )
            session.add(
                AssistantMessage(
                    thread_id=thread.id,
                    role=AssistantMessageRole.USER,
                    content="Je préfère React",
                    created_at=datetime.now(UTC),
                )
            )
            session.commit()
        return '{"reply":"OK","choices":[],"memories":["Je préfère Python"]}'

    monkeypatch.setattr(assistant_service, "llm_chat", delayed_model)
    response = client.post("/api/assistant/chat", headers=auth, json={"text": "Je préfère Python"})
    assert response.status_code == 201
    proposal = response.json()["message"]["proposals"][0]
    assert (
        client.post(f"/api/assistant/proposals/{proposal['id']}/confirm", headers=auth).status_code
        == 200
    )
    with factory() as session:
        memory = session.scalar(select(MemoryItem))
        source = session.get(AssistantMessage, memory.source_message_id)
        assert source.content == "Je préfère Python"
        assert source.role == AssistantMessageRole.USER


def test_historical_context_labels_replaced_memories_as_stale(account):
    factory, user_id, _ = account
    with factory() as session:
        old = add_memory(
            session,
            user_id,
            "Je préfère Vue",
            state=MemoryState.STALE,
            valid_until=datetime.now(UTC) - timedelta(days=1),
        )
        session.commit()
        assert ContextBuilder().memory_context(session, user_id, query="Vue") == []
        historical = ContextBuilder().memory_context(
            session, user_id, query="Mon ancienne préférence Vue"
        )
        assert historical[0]["id"] == str(old.id)
        assert historical[0]["state"] == "stale"


@pytest.mark.parametrize(
    "source, expected",
    [
        ("Je m'appelle Paul.", ["L'utilisateur s'appelle Paul."]),
        ("Pourquoi je préfère React ?", []),
    ],
)
def test_extraction_allows_explicit_identity_but_not_personal_questions(source, expected):
    candidate = "L'utilisateur s'appelle Paul." if "Paul" in source else "Je préfère React"
    assert _safe_memories([candidate], source) == expected


def test_working_memory_retains_options_as_proposals(account):
    factory, user_id, _ = account
    with factory() as session:
        thread = AssistantThread(user_id=user_id)
        session.add(thread)
        session.flush()
        message = AssistantMessage(
            thread_id=thread.id,
            role=AssistantMessageRole.ASSISTANT,
            content="Voici les options",
            working_choices=["Vue", "React"],
        )
        session.add(message)
        session.commit()
        context = working_context(session, user_id, "On garde la deuxième option")
        assert context["entries"][0]["kind"] == "assistant_options"
        assert context["entries"][0]["source_message_id"] == str(message.id)
        assert list(session.scalars(select(MemoryItem))) == []


def test_pgvector_query_binds_vectors_and_materializes_authorized_rows(
    embedding_settings, monkeypatch
):
    session = MagicMock()
    session.get_bind.return_value.dialect.name = "postgresql"
    session.scalar.return_value = True
    memory_id, user_id = uuid4(), uuid4()
    item = SimpleNamespace(id=memory_id)
    session.scalars.side_effect = [[memory_id], [item]]
    monkeypatch.setattr(embeddings, "embed", lambda *_, **__: [1.0, 0.0])
    assert embeddings.semantic_search(session, user_id, "Profession") == [item]
    query = session.scalars.call_args_list[0].args[0]
    compiled = query.compile(dialect=postgresql.dialect())
    assert "authorized AS MATERIALIZED" in str(compiled)
    assert "query_vector" in compiled.params
    assert user_id in compiled.params.values()
