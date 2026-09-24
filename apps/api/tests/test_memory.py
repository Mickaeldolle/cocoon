from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.modules.auth.models import User
from app.modules.memory.conflicts import supersede_conflicting_preference
from app.modules.memory.context import ContextBuilder, accessible_memory_summary_keys
from app.modules.memory.repository import MemoryRepository
from app.modules.memory.retriever import MemoryRetriever
from app.modules.memory.service import forget_memory
from app.modules.neural.models import (
    Capture,
    CaptureSource,
    MemoryItem,
    MemoryKind,
    MemoryLayer,
    MemoryState,
    MemoryType,
)


def register(client: TestClient, email: str) -> dict[str, str]:
    return client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "A-strong-password-123",
            "display_name": "Memory test",
            "installation_id": str(uuid4()),
            "name": "Test device",
            "platform": "ios",
        },
    ).json()


def test_memory_repository_filters_owner_scope_and_deleted_rows(client: TestClient) -> None:
    register(client, "memory-a@example.com")
    register(client, "memory-b@example.com")
    session = app.state.test_session_factory()
    try:
        first = session.query(User).filter_by(email="memory-a@example.com").one()
        second = session.query(User).filter_by(email="memory-b@example.com").one()
        first_capture = Capture(user_id=first.id, source=CaptureSource.TEXT, content="source A")
        second_capture = Capture(user_id=second.id, source=CaptureSource.TEXT, content="source B")
        session.add_all([first_capture, second_capture])
        session.flush()
        session.add_all(
            [
                MemoryItem(
                    user_id=first.id,
                    capture_id=first_capture.id,
                    kind=MemoryKind.INFORMATION,
                    summary="Préférence A",
                    reason="explicit",
                ),
                MemoryItem(
                    user_id=first.id,
                    capture_id=first_capture.id,
                    kind=MemoryKind.INFORMATION,
                    summary="Souvenir expiré",
                    reason="explicit",
                    valid_until=datetime.now(UTC) - timedelta(minutes=1),
                ),
                MemoryItem(
                    user_id=first.id,
                    capture_id=first_capture.id,
                    kind=MemoryKind.INFORMATION,
                    summary="Souvenir supprimé",
                    reason="explicit",
                    state=MemoryState.DISMISSED,
                ),
                MemoryItem(
                    user_id=second.id,
                    capture_id=second_capture.id,
                    kind=MemoryKind.INFORMATION,
                    summary="Préférence B",
                    reason="explicit",
                ),
            ]
        )
        session.commit()
        memories = MemoryRepository().active_for_user(session, first.id)
        assert [memory.summary for memory in memories] == ["Préférence A"]
        assert ContextBuilder().memory_summaries(session, first.id) == ["Préférence A"]
        assert ContextBuilder().memory_summaries(session, first.id, query="Préférence A") == [
            "Préférence A"
        ]
        assert ContextBuilder().memory_summaries(session, first.id, query="Préférence B") == [
            "Préférence A"
        ]
        assert accessible_memory_summary_keys(session, first.id) == {"préférence a"}
    finally:
        session.close()


def test_memory_endpoints_correct_and_forget_without_deleting_capture(client: TestClient) -> None:
    tokens = register(client, "memory-endpoint@example.com")
    other_tokens = register(client, "memory-other@example.com")
    auth = {"Authorization": f"Bearer {tokens['access_token']}"}
    other_auth = {"Authorization": f"Bearer {other_tokens['access_token']}"}
    session = app.state.test_session_factory()
    try:
        user = session.query(User).filter_by(email="memory-endpoint@example.com").one()
        capture = Capture(user_id=user.id, source=CaptureSource.TEXT, content="capture retained")
        session.add(capture)
        session.flush()
        memory = MemoryItem(
            user_id=user.id,
            capture_id=capture.id,
            kind=MemoryKind.INFORMATION,
            summary="Je préfère le thé",
            reason="explicit",
        )
        session.add(memory)
        session.commit()
        memory_id = str(memory.id)
        capture_id = str(capture.id)
    finally:
        session.close()


    listed = client.get("/api/memories", headers=auth)
    assert listed.status_code == 200
    assert listed.json()["memories"][0]["summary"] == "Je préfère le thé"
    assert listed.json()["memories"][0]["capture_id"] == capture_id
    assert client.get(f"/api/memories/{memory_id}", headers=other_auth).status_code == 404

    corrected = client.patch(
        f"/api/memories/{memory_id}",
        headers=auth,
        json={"summary": "Je préfère le café", "memory_type": "preference"},
    )
    assert corrected.status_code == 200
    replacement_id = corrected.json()["id"]
    assert corrected.json()["supersedes_id"] == memory_id
    assert corrected.json()["owner_type"] == "user"
    assert corrected.json()["scope_type"] == "personal"
    assert corrected.json()["scope_id"] is None
    assert client.get(f"/api/memories/{memory_id}", headers=auth).status_code == 404

    forgotten = client.delete(f"/api/memories/{replacement_id}", headers=auth)
    assert forgotten.status_code == 200
    assert forgotten.json()["state"] == "dismissed"
    assert client.get("/api/memories", headers=auth).json() == {"memories": []}
    session = app.state.test_session_factory()
    try:
        assert session.get(Capture, UUID(capture_id)) is not None
    finally:
        session.close()


def test_memory_list_excludes_memories_outside_validity_window(client: TestClient) -> None:
    tokens = register(client, "memory-validity@example.com")
    auth = {"Authorization": f"Bearer {tokens['access_token']}"}
    session = app.state.test_session_factory()
    try:
        user = session.query(User).filter_by(email="memory-validity@example.com").one()
        capture = Capture(user_id=user.id, source=CaptureSource.TEXT, content="validity")
        session.add(capture)
        session.flush()
        session.add_all(
            [
                MemoryItem(
                    user_id=user.id,
                    capture_id=capture.id,
                    kind=MemoryKind.INFORMATION,
                    summary="Mémoire future",
                    reason="explicit",
                    valid_from=datetime.now(UTC) + timedelta(minutes=5),
                ),
                MemoryItem(
                    user_id=user.id,
                    capture_id=capture.id,
                    kind=MemoryKind.INFORMATION,
                    summary="Mémoire expirée",
                    reason="explicit",
                    valid_until=datetime.now(UTC) - timedelta(minutes=5),
                ),
                MemoryItem(
                    user_id=user.id,
                    capture_id=capture.id,
                    kind=MemoryKind.INFORMATION,
                    summary="Mémoire active",
                    reason="explicit",
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    listed = client.get("/api/memories", headers=auth)
    assert listed.status_code == 200
    assert [item["summary"] for item in listed.json()["memories"]] == ["Mémoire active"]


def test_memory_retriever_prioritizes_constraints_over_episodes(client: TestClient) -> None:
    register(client, "memory-priority@example.com")
    session = app.state.test_session_factory()
    try:
        user = session.query(User).filter_by(email="memory-priority@example.com").one()
        capture = Capture(user_id=user.id, source=CaptureSource.TEXT, content="context")
        session.add(capture)
        session.flush()
        session.add_all(
            [
                MemoryItem(
                    user_id=user.id,
                    capture_id=capture.id,
                    kind=MemoryKind.INFORMATION,
                    layer=MemoryLayer.EPISODIC,
                    memory_type=MemoryType.INTEREST,
                    summary="Épisode récent",
                    reason="episode",
                ),
                MemoryItem(
                    user_id=user.id,
                    capture_id=capture.id,
                    kind=MemoryKind.INFORMATION,
                    layer=MemoryLayer.SEMANTIC,
                    memory_type=MemoryType.CONSTRAINT,
                    summary="Contrainte durable",
                    reason="explicit",
                ),
            ]
        )
        session.commit()
        memories = MemoryRetriever().retrieve(session, user.id, limit=2)
        assert [memory.summary for memory in memories] == ["Contrainte durable", "Épisode récent"]
    finally:
        session.close()


def test_memory_retriever_follows_context_order_for_unmatched_memories(
    client: TestClient,
) -> None:
    register(client, "memory-context-order@example.com")
    session = app.state.test_session_factory()
    try:
        user = session.query(User).filter_by(email="memory-context-order@example.com").one()
        capture = Capture(user_id=user.id, source=CaptureSource.TEXT, content="context order")
        session.add(capture)
        session.flush()
        session.add_all(
            [
                MemoryItem(
                    user_id=user.id,
                    capture_id=capture.id,
                    kind=MemoryKind.INFORMATION,
                    memory_type=MemoryType.PREFERENCE,
                    summary="Préférence sans correspondance",
                    reason="explicit",
                ),
                MemoryItem(
                    user_id=user.id,
                    capture_id=capture.id,
                    kind=MemoryKind.INFORMATION,
                    memory_type=MemoryType.FACT,
                    summary="Fait sans correspondance",
                    reason="explicit",
                ),
                MemoryItem(
                    user_id=user.id,
                    capture_id=capture.id,
                    kind=MemoryKind.INFORMATION,
                    memory_type=MemoryType.CONSTRAINT,
                    summary="Contrainte sans correspondance",
                    reason="explicit",
                ),
                MemoryItem(
                    user_id=user.id,
                    capture_id=capture.id,
                    kind=MemoryKind.INFORMATION,
                    memory_type=MemoryType.INTEREST,
                    summary="Épisode sans correspondance",
                    reason="explicit",
                ),
            ]
        )
        session.commit()
        memories = MemoryRetriever().retrieve(session, user.id, query="terme absent", limit=4)
        assert [memory.memory_type for memory in memories] == [
            MemoryType.CONSTRAINT,
            MemoryType.FACT,
            MemoryType.PREFERENCE,
            MemoryType.INTEREST,
        ]
    finally:
        session.close()


def test_explicit_preference_replaces_previous_preference_with_provenance(
    client: TestClient,
) -> None:
    register(client, "memory-conflict@example.com")
    session = app.state.test_session_factory()
    try:
        user = session.query(User).filter_by(email="memory-conflict@example.com").one()
        capture = Capture(user_id=user.id, source=CaptureSource.TEXT, content="preference")
        session.add(capture)
        session.flush()
        previous = MemoryItem(
            user_id=user.id,
            capture_id=capture.id,
            kind=MemoryKind.INFORMATION,
            memory_type=MemoryType.PREFERENCE,
            summary="Je préfère le thé",
            reason="explicit",
        )
        session.add(previous)
        session.commit()

        replaced = supersede_conflicting_preference(session, user.id, "Je préfère le café")
        assert replaced is not None
        assert replaced.id == previous.id
        assert replaced.state is MemoryState.STALE
        assert replaced.valid_until is not None
    finally:
        session.close()


def test_preference_contradictions_are_grouped_without_cross_topic_replacement(
    client: TestClient,
) -> None:
    register(client, "memory-topic-conflict@example.com")
    session = app.state.test_session_factory()
    try:
        user = session.query(User).filter_by(email="memory-topic-conflict@example.com").one()
        capture = Capture(user_id=user.id, source=CaptureSource.TEXT, content="topics")
        session.add(capture)
        session.flush()
        beverage = MemoryItem(
            user_id=user.id,
            capture_id=capture.id,
            kind=MemoryKind.INFORMATION,
            memory_type=MemoryType.PREFERENCE,
            summary="Je préfère le thé",
            reason="explicit",
        )
        schedule = MemoryItem(
            user_id=user.id,
            capture_id=capture.id,
            kind=MemoryKind.INFORMATION,
            memory_type=MemoryType.PREFERENCE,
            summary="Je préfère travailler le matin",
            reason="explicit",
            created_at=datetime.now(UTC) + timedelta(seconds=1),
        )
        session.add_all([beverage, schedule])
        session.commit()

        replaced = supersede_conflicting_preference(session, user.id, "Je préfère le café")
        assert replaced is not None
        assert replaced.id == beverage.id
        assert schedule.state is MemoryState.ACTIVE
    finally:
        session.close()


def test_forget_propagates_through_a_multi_generation_memory_chain(client: TestClient) -> None:
    register(client, "memory-chain@example.com")
    session = app.state.test_session_factory()
    try:
        user = session.query(User).filter_by(email="memory-chain@example.com").one()
        capture = Capture(user_id=user.id, source=CaptureSource.TEXT, content="chain")
        session.add(capture)
        session.flush()
        root = MemoryItem(
            user_id=user.id,
            capture_id=capture.id,
            kind=MemoryKind.INFORMATION,
            summary="Racine",
            reason="explicit",
        )
        session.add(root)
        session.flush()
        middle = MemoryItem(
            user_id=user.id,
            capture_id=capture.id,
            kind=MemoryKind.INFORMATION,
            summary="Intermédiaire",
            reason="correction",
            supersedes_id=root.id,
        )
        session.add(middle)
        session.flush()
        leaf = MemoryItem(
            user_id=user.id,
            capture_id=capture.id,
            kind=MemoryKind.INFORMATION,
            summary="Dernière valeur",
            reason="correction",
            supersedes_id=middle.id,
        )
        session.add(leaf)
        session.commit()
        root_id = root.id
        leaf_id = leaf.id

        forget_memory(session, user.id, root_id)
        assert MemoryRepository().active_for_user(session, user.id) == []
        assert session.get(MemoryItem, leaf_id).state is MemoryState.DISMISSED
    finally:
        session.close()
