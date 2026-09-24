import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.error import URLError
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.modules.assistant import service as assistant_service
from app.modules.assistant import voice as assistant_voice
from app.modules.assistant.models import (
    AssistantProposal,
    AssistantProposalStatus,
    ProposalExecution,
    RecurringReminder,
)
from app.modules.assistant.router import create_voice_transcription
from app.modules.neural.models import MemoryItem, MemoryLayer
from app.modules.personal.models import GroceryItem, PersonalTask, TrainingSession


@pytest.fixture(autouse=True)
def disable_live_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep contract tests independent from a locally running model."""

    def model(messages: list[dict[str, str]]) -> str | None:
        if "assistant personnel français de Cocoon" not in messages[0]["content"]:
            return None
        text = json.loads(messages[-1]["content"])["message"]
        if "médicament" in text or "douleur" in text:
            return '{"content":"Je ne fournis pas de conseil médical.","proposals":[]}'
        return json.dumps(
            {
                "content": "Je vous propose cette priorité.",
                "proposals": [
                    {
                        "kind": "task",
                        "payload": {
                            "title": text,
                            "detail": None,
                            "priority": "normal",
                            "due_date": None,
                            "reminder_at": None,
                        },
                    }
                ],
            }
        )

    monkeypatch.setattr(assistant_service, "llm_chat", model)


def register_payload() -> dict[str, object]:
    return {
        "email": "marie@example.com",
        "password": "A-strong-password-123",
        "display_name": "Marie Dupont",
        "installation_id": "assistant-test-device",
        "name": "Test device",
        "platform": "ios",
    }


def authenticated_headers(client: TestClient) -> dict[str, str]:
    tokens = client.post("/api/auth/register", json=register_payload()).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def test_assistant_organizes_thought_with_tags_and_reminder_date(client: TestClient) -> None:
    response = client.post(
        "/api/assistant/organize",
        headers=authenticated_headers(client),
        json={
            "thought": "Pense à acheter les fournitures pour l’école demain",
            "tags": ["family"],
            "reference_date": "2026-09-15",
        },
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "kind": "reminder",
        "title": "Acheter les fournitures pour l’école demain",
        "summary": "Rappel proposé pour le 16/09/2026.",
        "tags": ["family", "school", "errands"],
        "reminder_date": "2026-09-16",
        "mode": "rules",
    }


def test_assistant_requires_an_authenticated_user(client: TestClient) -> None:
    response = client.post("/api/assistant/organize", json={"thought": "Ranger le bureau"})

    assert response.status_code == 401


def test_structured_assistant_falls_back_only_when_provider_is_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(_messages: list[dict[str, str]]) -> None:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="provider unavailable")

    monkeypatch.setattr(assistant_service, "llm_chat", unavailable)
    response = client.post(
        "/api/assistant/organize",
        headers=authenticated_headers(client),
        json={"thought": "Ranger les documents demain"},
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "rules"


def test_structured_assistant_preserves_invalid_provider_errors(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def invalid(_messages: list[dict[str, str]]) -> None:
        from fastapi import HTTPException

        raise HTTPException(status_code=502, detail="invalid provider response")

    monkeypatch.setattr(assistant_service, "llm_chat", invalid)
    response = client.post(
        "/api/assistant/organize",
        headers=authenticated_headers(client),
        json={"thought": "Ranger les documents demain"},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "invalid provider response"


def test_chat_returns_direct_model_text_without_actions(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompts: list[dict[str, object]] = []

    def model(messages: list[dict[str, str]]) -> str:
        prompts.append(json.loads(messages[-1]["content"]))
        return json.dumps(
            {
                "reply": "Je retiens que vous préférez courir le matin.",
                "choices": ["Oui, le matin", "Finalement le soir"],
                "memories": ["La personne préfère courir le matin."],
            }
        )

    monkeypatch.setattr(assistant_service, "llm_chat", model)
    auth = authenticated_headers(client)
    first = client.post(
        "/api/assistant/chat", headers=auth, json={"text": "Je préfère courir le matin."}
    )

    assert first.status_code == 201
    assert first.json()["message"]["content"] == "Je retiens que vous préférez courir le matin."
    assert first.json()["choices"] == ["Oui, le matin", "Finalement le soir"]
    assert first.json()["remembered"] == []
    proposal = first.json()["message"]["proposals"][0]
    assert proposal["kind"] == "note"
    assert proposal["status"] == "pending"
    confirmed = client.post(f"/api/assistant/proposals/{proposal['id']}/confirm", headers=auth)
    assert confirmed.status_code == 200
    with app.state.test_session_factory() as session:
        memory = session.scalar(select(MemoryItem))
        assert memory is not None
        assert memory.layer is MemoryLayer.SEMANTIC

    second = client.post("/api/assistant/chat", headers=auth, json={"text": "Tu t'en souviens ?"})
    assert second.status_code == 201
    assert prompts[1]["recalled_memories"] == ["La personne préfère courir le matin."]
    repeated = client.post(
        "/api/assistant/chat", headers=auth, json={"text": "Je préfère courir le matin."}
    )
    assert repeated.status_code == 201
    assert repeated.json()["message"]["proposals"] == []


def test_small_agent_harness_never_shares_memories_between_users(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompts: list[dict[str, object]] = []

    def model(messages: list[dict[str, str]]) -> str:
        prompts.append(json.loads(messages[-1]["content"]))
        return '{"reply":"Bien noté.","choices":[],"memories":["Préférence personnelle"]}'

    monkeypatch.setattr(assistant_service, "llm_chat", model)
    marie = authenticated_headers(client)
    assert (
        client.post(
            "/api/assistant/chat", headers=marie, json={"text": "Je préfère le thé."}
        ).status_code
        == 201
    )
    paul = client.post(
        "/api/auth/register",
        json={
            **register_payload(),
            "email": "agent-isolation@example.com",
            "installation_id": "agent-isolation-device",
        },
    ).json()
    assert (
        client.post(
            "/api/assistant/chat",
            headers={"Authorization": f"Bearer {paul['access_token']}"},
            json={"text": "Bonjour"},
        ).status_code
        == 201
    )
    assert prompts[-1]["recalled_memories"] == []


def test_small_agent_harness_does_not_memorize_a_trivial_question(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        assistant_service,
        "llm_chat",
        lambda _messages: '{"reply":"Bonjour !","choices":[],"memories":["Information inventée"]}',
    )
    response = client.post(
        "/api/assistant/chat",
        headers=authenticated_headers(client),
        json={"text": "Bonjour, comment vas-tu ?"},
    )
    assert response.status_code == 201
    assert response.json()["message"]["proposals"] == []


def test_chat_retry_with_same_idempotency_key_replays_one_turn(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        assistant_service,
        "llm_chat",
        lambda _messages: '{"reply":"Bonjour","choices":[],"memories":[]}',
    )
    auth = authenticated_headers(client)
    headers = {**auth, "X-Assistant-Idempotency-Key": "chat-retry-1"}
    first = client.post("/api/assistant/chat", headers=headers, json={"text": "Bonjour"})
    second = client.post("/api/assistant/chat", headers=headers, json={"text": "Bonjour"})

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert second.json()["message"]["id"] == first.json()["message"]["id"]
    history = client.get("/api/assistant/history", headers=auth)
    assert len(history.json()["messages"]) == 2


def test_streaming_chat_emits_deltas_and_persists_the_completed_turn(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        assistant_service,
        "llm_stream",
        lambda _messages, **_kwargs: iter(
            [
                '{"reply":"Bon',
                'jour","choices":[],"memories":[]}',
            ]
        ),
    )
    auth = authenticated_headers(client)
    response = client.post(
        "/api/assistant/chat/stream",
        headers={**auth, "X-Assistant-Idempotency-Key": "stream-chat-1"},
        json={"text": "Bonjour"},
    )

    assert response.status_code == 200
    assert "event: started" in response.text
    assert 'event: delta\ndata: {"text": "Bon"}' in response.text
    assert 'event: delta\ndata: {"text": "jour"}' in response.text
    assert '"content": "Bonjour"' in response.text
    history = client.get("/api/assistant/history", headers=auth)
    assert [message["content"] for message in history.json()["messages"]] == ["Bonjour", "Bonjour"]


def test_streaming_chat_accepts_plain_text_from_model(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        assistant_service,
        "llm_stream",
        lambda _messages, **_kwargs: iter(["Bonjour", " !"]),
    )
    response = client.post(
        "/api/assistant/chat/stream",
        headers=authenticated_headers(client),
        json={"text": "Bonjour"},
    )
    assert response.status_code == 200
    assert 'event: delta\ndata: {"text": "Bonjour"}' in response.text
    assert '"content": "Bonjour !"' in response.text


def test_chat_creates_confirmable_memory_proposals(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        assistant_service,
        "llm_chat",
        lambda _messages: (
            '{"reply":"Je prends note.","choices":[],"memories":["Je préfère le thé"]}'
        ),
    )
    auth = authenticated_headers(client)
    response = client.post(
        "/api/assistant/chat",
        headers=auth,
        json={"text": "Je préfère le thé"},
    )
    assert response.status_code == 201

    assert response.json()["message"]["proposals"][0]["kind"] == "note"


def test_chat_accepts_plain_text_from_model(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(assistant_service, "llm_chat", lambda _messages: "Bonjour, je suis là.")
    response = client.post(
        "/api/assistant/chat",
        headers=authenticated_headers(client),
        json={"text": "Bonjour"},
    )
    assert response.status_code == 201
    assert response.json()["message"]["content"] == "Bonjour, je suis là."
    assert response.json()["message"]["proposals"] == []


def test_small_agent_harness_reports_missing_model(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(assistant_service, "llm_chat", lambda _messages: None)
    auth = authenticated_headers(client)
    response = client.post(
        "/api/assistant/chat", headers=auth, json={"text": "Bonjour"}
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "Le modèle est indisponible. Réessayez dans un instant."
    history = client.get("/api/assistant/history", headers=auth)
    assert history.status_code == 200
    assert history.json()["messages"][-1]["role"] == "user"
    assert history.json()["messages"][-1]["content"] == "Bonjour"


def test_voice_transcription_is_private_and_returns_editable_text(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.modules.assistant.router.transcribe_audio",
        lambda audio, content_type: "Pense à appeler le garage demain",
    )
    auth = authenticated_headers(client)
    consent = client.put(
        "/api/auth/consents/assistant.voice",
        headers=auth,
        json={"policy_version": 1, "source": "mobile"},
    )
    assert consent.status_code == 200
    response = client.post(
        "/api/assistant/voice/transcriptions",
        headers={**auth, "Content-Type": "audio/mp4"},
        content=b"short-audio-bytes",
    )

    assert response.status_code == 200
    assert response.json() == {"text": "Pense à appeler le garage demain"}


def test_voice_transcription_requires_authentication_and_supported_audio(
    client: TestClient,
) -> None:
    unauthenticated = client.post(
        "/api/assistant/voice/transcriptions",
        headers={"Content-Type": "audio/mp4"},
        content=b"short-audio-bytes",
    )
    assert unauthenticated.status_code == 401

    unsupported = client.post(
        "/api/assistant/voice/transcriptions",
        headers={**authenticated_headers(client), "Content-Type": "application/octet-stream"},
        content=b"short-audio-bytes",
    )
    assert unsupported.status_code == 415


def test_voice_transcription_reports_missing_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(assistant_voice, "transcription_is_configured", lambda: False)
    with pytest.raises(Exception) as error:
        assistant_voice.transcribe_audio(b"short-audio-bytes", "audio/mp4")
    assert "transcription vocale n’est pas configurée" in str(error.value.detail)


def test_voice_transcription_rejects_empty_and_oversized_audio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(assistant_voice, "transcription_is_configured", lambda: True)
    with pytest.raises(Exception) as empty:
        assistant_voice.transcribe_audio(b"", "audio/mp4")
    assert empty.value.status_code == 422
    with pytest.raises(Exception) as oversized:
        assistant_voice.transcribe_audio(
            b"x" * (assistant_voice.MAX_VOICE_BYTES + 1), "audio/mp4"
        )
    assert oversized.value.status_code == 413


def test_voice_route_stops_chunked_upload_before_reading_past_limit() -> None:
    class ChunkedRequest:
        headers = {"content-type": "audio/mp4"}

        async def stream(self):
            yield b"x" * (4 * 1024 * 1024)
            yield b"x" * (4 * 1024 * 1024 + 1)

    with pytest.raises(Exception) as error:
        asyncio.run(create_voice_transcription(ChunkedRequest(), None))

    assert error.value.status_code == 413


@pytest.mark.parametrize(
    ("content_type", "extension"),
    [("audio/mp4", "m4a"), ("audio/m4a", "m4a"), ("audio/webm", "webm"), ("audio/wav", "wav")],
)
def test_voice_adapter_calls_private_openai_compatible_stt_without_persisting_audio(
    monkeypatch: pytest.MonkeyPatch,
    content_type: str,
    extension: str,
) -> None:
    settings = SimpleNamespace(
        stt_api_url="http://stt.internal/v1",
        stt_model="faster-whisper-small",
        stt_api_key="private-key",
        stt_timeout_seconds=10,
    )
    captured: dict[str, object] = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"text":"  Appeler le dentiste demain  "}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = request.data
        captured["authorization"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(assistant_voice, "get_settings", lambda: settings)
    monkeypatch.setattr(assistant_voice, "urlopen", fake_urlopen)
    assert assistant_voice.transcribe_audio(b"temporary-audio", content_type) == (
        "Appeler le dentiste demain"
    )
    assert captured["url"] == "http://stt.internal/v1/audio/transcriptions"
    assert captured["authorization"] == "Bearer private-key"
    assert b"temporary-audio" in captured["body"]
    assert f'filename="cocoon-voice.{extension}"'.encode() in captured["body"]
    assert f"Content-Type: {content_type}".encode() in captured["body"]
    assert captured["timeout"] == 10


def test_voice_adapter_distinguishes_provider_failure_from_invalid_transcription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        stt_api_url="http://stt.internal/v1",
        stt_model="faster-whisper-small",
        stt_api_key=None,
        stt_timeout_seconds=10,
    )
    monkeypatch.setattr(assistant_voice, "get_settings", lambda: settings)

    def unavailable_urlopen(*_args, **_kwargs):
        raise URLError("offline")

    monkeypatch.setattr(assistant_voice, "urlopen", unavailable_urlopen)
    with pytest.raises(Exception) as unavailable:
        assistant_voice.transcribe_audio(b"audio", "audio/mp4")
    assert unavailable.value.status_code == 503

    class EmptyResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"text":"   "}'

    monkeypatch.setattr(assistant_voice, "urlopen", lambda *_args, **_kwargs: EmptyResponse())
    with pytest.raises(Exception) as invalid:
        assistant_voice.transcribe_audio(b"audio", "audio/mp4")
    assert invalid.value.status_code == 502


def test_assistant_reports_an_unavailable_model_without_a_rule_based_reply(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(assistant_service, "llm_chat", lambda _messages: None)

    response = client.post(
        "/api/assistant/turn",
        headers=authenticated_headers(client),
        json={"text": "Pense à acheter du lait"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Le modèle est indisponible. Réessayez dans un instant."


def test_assistant_keeps_an_undated_thought_as_a_note(client: TestClient) -> None:
    response = client.post(
        "/api/assistant/organize",
        headers=authenticated_headers(client),
        json={"thought": "Une idée de sortie avec la famille"},
    )

    assert response.status_code == 200
    assert response.json()["kind"] == "note"
    assert response.json()["reminder_date"] is None
    assert response.json()["tags"] == ["family"]


def test_assistant_builds_a_meal_plan_from_the_explicit_grocery_list(client: TestClient) -> None:
    response = client.post(
        "/api/assistant/meal-plan",
        headers=authenticated_headers(client),
        json={
            "grocery_items": ["Pâtes complètes", "Courgettes", "Basilic", "Œufs"],
        },
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "meals": [
            {
                "day": "Lundi",
                "name": "Pâtes aux légumes du placard",
                "description": "Un dîner rapide à ajuster avec les légumes déjà prévus.",
                "uses": ["Pâtes", "Courgettes", "Basilic"],
                "missing_items": ["Parmesan ou levure maltée"],
            },
            {
                "day": "Mercredi",
                "name": "Omelette verte et salade",
                "description": "Une option courte pour le milieu de semaine.",
                "uses": ["Œufs"],
                "missing_items": ["Pain complet"],
            },
            {
                "day": "Vendredi",
                "name": "Bowl de pois chiches méditerranéen",
                "description": "Un bol frais qui valorise les conserves et les crudités.",
                "uses": [],
                "missing_items": ["Citron"],
            },
        ],
        "mode": "rules",
    }


def test_turn_requires_confirmation_and_is_private_and_idempotent(client: TestClient) -> None:
    marie = authenticated_headers(client)
    paul = client.post(
        "/api/auth/register",
        json={
            **register_payload(),
            "email": "paul@example.com",
            "installation_id": "paul-assistant-device",
        },
    ).json()
    paul_headers = {"Authorization": f"Bearer {paul['access_token']}"}

    turn = client.post("/api/assistant/turn", headers=marie, json={"text": "Appeler le dentiste"})
    assert turn.status_code == 201
    proposal = turn.json()["message"]["proposals"][0]
    assert client.get("/api/personal/tasks", headers=marie).json() == []
    assert client.get("/api/assistant/history", headers=paul_headers).json() == {"messages": []}
    assert (
        client.post(
            f"/api/assistant/proposals/{proposal['id']}/confirm", headers=paul_headers
        ).status_code
        == 404
    )

    confirmed = client.post(f"/api/assistant/proposals/{proposal['id']}/confirm", headers=marie)
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"
    repeated = client.post(f"/api/assistant/proposals/{proposal['id']}/confirm", headers=marie)
    assert repeated.status_code == 200
    assert [task["title"] for task in client.get("/api/personal/tasks", headers=marie).json()] == [
        "Appeler le dentiste"
    ]
    session = client.app.state.test_session_factory()
    try:
        execution = (
            session.query(ProposalExecution)
            .filter_by(proposal_type="assistant", proposal_id=UUID(proposal["id"]))
            .one()
        )
        assert execution.status == "committed"
    finally:
        session.close()


def test_turn_retry_reuses_the_same_persisted_exchange(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def model(_messages: list[dict[str, str]]) -> str:
        nonlocal calls
        calls += 1
        return json.dumps(
            {
                "content": "Je propose une tâche.",
                "proposals": [
                    {
                        "kind": "task",
                        "payload": {
                            "title": "Préparer le dossier",
                            "detail": None,
                            "priority": "normal",
                            "due_date": None,
                            "reminder_at": None,
                        },
                    }
                ],
            }
        )

    monkeypatch.setattr(assistant_service, "llm_chat", model)
    auth = authenticated_headers(client)
    request_headers = {**auth, "X-Assistant-Idempotency-Key": "turn-retry-001"}
    first = client.post(
        "/api/assistant/turn", headers=request_headers, json={"text": "Prépare le dossier"}
    )
    second = client.post(
        "/api/assistant/turn", headers=request_headers, json={"text": "Prépare le dossier"}
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert second.json() == first.json()
    assert calls == 1
    assert len(client.get("/api/assistant/history", headers=auth).json()["messages"]) == 2


def test_expired_proposal_cannot_be_confirmed(client: TestClient) -> None:
    auth = authenticated_headers(client)
    turn = client.post("/api/assistant/turn", headers=auth, json={"text": "Appeler le dentiste"})
    assert turn.status_code == 201
    proposal_id = turn.json()["message"]["proposals"][0]["id"]

    session = client.app.state.test_session_factory()
    try:
        proposal = session.get(AssistantProposal, UUID(proposal_id))
        assert proposal is not None
        proposal.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()
    finally:
        session.close()

    response = client.post(f"/api/assistant/proposals/{proposal_id}/confirm", headers=auth)
    assert response.status_code == 409
    assert "expiré" in response.json()["detail"]

    session = client.app.state.test_session_factory()
    try:
        proposal = session.get(AssistantProposal, UUID(proposal_id))
        assert proposal is not None
        assert proposal.status is AssistantProposalStatus.EXPIRED
    finally:
        session.close()


def test_cancelling_assistant_proposal_is_terminal_and_serialized(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        assistant_service,
        "llm_chat",
        lambda _messages: '{"content":"Je propose une tâche.","proposals":[{"kind":"task",'
        '"payload":{"title":"Préparer le dossier"}}]}',
    )
    auth = authenticated_headers(client)
    response = client.post(
        "/api/assistant/turn", headers=auth, json={"text": "Prépare le dossier"}
    )
    assert response.status_code == 201
    proposal_id = response.json()["message"]["proposals"][0]["id"]

    cancelled = client.post(f"/api/assistant/proposals/{proposal_id}/cancel", headers=auth)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    repeated = client.post(f"/api/assistant/proposals/{proposal_id}/cancel", headers=auth)
    assert repeated.status_code == 200
    assert repeated.json()["status"] == "cancelled"
    confirmed = client.post(f"/api/assistant/proposals/{proposal_id}/confirm", headers=auth)
    assert confirmed.status_code == 409


def test_invalid_assistant_proposal_is_failed_and_cannot_be_replayed(
    client: TestClient,
) -> None:
    auth = authenticated_headers(client)
    turn = client.post("/api/assistant/turn", headers=auth, json={"text": "Appeler le dentiste"})
    assert turn.status_code == 201
    proposal_id = turn.json()["message"]["proposals"][0]["id"]

    session = client.app.state.test_session_factory()
    try:
        proposal = session.get(AssistantProposal, UUID(proposal_id))
        assert proposal is not None
        proposal.payload = {"title": ""}
        session.commit()
    finally:
        session.close()

    response = client.post(f"/api/assistant/proposals/{proposal_id}/confirm", headers=auth)
    assert response.status_code == 422
    assert response.json()["detail"] == "La proposition est invalide."

    session = client.app.state.test_session_factory()
    try:
        proposal = session.get(AssistantProposal, UUID(proposal_id))
        execution = session.scalar(
            select(ProposalExecution).where(
                ProposalExecution.proposal_type == "assistant",
                ProposalExecution.proposal_id == UUID(proposal_id),
            )
        )
        assert proposal is not None
        assert proposal.status is AssistantProposalStatus.FAILED
        assert execution is not None
        assert execution.status == "failed"
        assert execution.error_code == "invalid_payload"
    finally:
        session.close()

    replay = client.post(f"/api/assistant/proposals/{proposal_id}/confirm", headers=auth)
    assert replay.status_code == 409


def test_stale_assistant_proposal_version_is_rejected_without_effect(
    client: TestClient,
) -> None:
    auth = authenticated_headers(client)
    turn = client.post("/api/assistant/turn", headers=auth, json={"text": "Appeler le dentiste"})
    proposal = turn.json()["message"]["proposals"][0]

    session = client.app.state.test_session_factory()
    try:
        stored = session.get(AssistantProposal, UUID(proposal["id"]))
        assert stored is not None
        stored.payload_version = 2
        session.commit()
    finally:
        session.close()

    stale = client.post(
        f"/api/assistant/proposals/{proposal['id']}/confirm",
        headers={**auth, "X-Proposal-Version": "1"},
    )
    assert stale.status_code == 409
    assert client.get("/api/personal/tasks", headers=auth).json() == []

    current = client.post(f"/api/assistant/proposals/{proposal['id']}/confirm", headers=auth)
    assert current.status_code == 200


def test_assistant_health_guardrail_does_not_create_a_proposal(client: TestClient) -> None:
    response = client.post(
        "/api/assistant/turn",
        headers=authenticated_headers(client),
        json={"text": "Quel médicament prendre pour cette douleur ?"},
    )
    assert response.status_code == 201
    assert response.json()["message"]["proposals"] == []


def test_assistant_uses_model_response_and_note_proposal_when_requested(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        assistant_service,
        "llm_chat",
        lambda _messages: (
            '{"content":"Je peux garder cette pensée. Voulez-vous la confirmer ?",'
            '"proposals":[{"kind":"note","payload":{"summary":"Idée de cadeau pour Paul"}}]}'
        ),
    )
    auth = authenticated_headers(client)
    response = client.post("/api/assistant/turn", headers=auth, json={"text": "Garde cette idée"})

    assert response.status_code == 201
    assert response.json()["mode"] == "llm"
    assert response.json()["message"]["content"] == (
        "Je peux garder cette pensée. Voulez-vous la confirmer ?"
    )
    proposal = response.json()["message"]["proposals"][0]
    assert proposal["kind"] == "note"
    confirmed = client.post(f"/api/assistant/proposals/{proposal['id']}/confirm", headers=auth)
    assert confirmed.status_code == 200


def test_confirming_one_assistant_alternative_cancels_the_other(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        assistant_service,
        "llm_chat",
        lambda _messages: (
            '{"content":"Voici deux façons de garder cette idée.","proposals":['
            '{"kind":"note","payload":{"summary":"Première formulation"}},'
            '{"kind":"note","payload":{"summary":"Seconde formulation"}}]}'
        ),
    )
    auth = authenticated_headers(client)
    response = client.post(
        "/api/assistant/turn", headers=auth, json={"text": "Choisir une formulation"}
    )
    assert response.status_code == 201
    proposals = response.json()["message"]["proposals"]
    assert len(proposals) == 2

    confirmed = client.post(f"/api/assistant/proposals/{proposals[0]['id']}/confirm", headers=auth)
    assert confirmed.status_code == 200
    with app.state.test_session_factory() as session:
        stored = session.scalars(
            select(AssistantProposal).where(
                AssistantProposal.assistant_message_id
                == UUID(response.json()["message"]["id"])
            )
        ).all()
        statuses = {str(item.id): item.status for item in stored}
    assert statuses[proposals[0]["id"]] is AssistantProposalStatus.CONFIRMED
    assert statuses[proposals[1]["id"]] is AssistantProposalStatus.CANCELLED


def test_assistant_accepts_json_wrapped_in_a_markdown_fence(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        assistant_service,
        "llm_chat",
        lambda _messages: '```json\n{"content":"Je vous ai compris.","proposals":[]}\n```',
    )
    response = client.post(
        "/api/assistant/turn",
        headers=authenticated_headers(client),
        json={"text": "Une idée à garder"},
    )

    assert response.status_code == 201
    assert response.json()["mode"] == "llm"


def test_assistant_passes_recent_conversation_to_model(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    messages: list[list[dict[str, str]]] = []

    def model(prompt: list[dict[str, str]]) -> str:
        payload = prompt[-1]["content"]
        messages.append(json.loads(payload)["recent_conversation"])
        return '{"content":"Pouvez-vous préciser le jour et l’heure ?","proposals":[]}'

    monkeypatch.setattr(assistant_service, "llm_chat", model)
    auth = authenticated_headers(client)
    first = client.post("/api/assistant/turn", headers=auth, json={"text": "Pense à appeler Paul"})
    second = client.post("/api/assistant/turn", headers=auth, json={"text": "Oui, garde-la"})
    assert first.status_code == 201
    assert second.status_code == 201

    assert messages[1][-2:] == [
        {"role": "user", "content": "Pense à appeler Paul"},
        {"role": "assistant", "content": "Pouvez-vous préciser le jour et l’heure ?"},
    ]


def test_assistant_detects_a_calendar_conflict_before_confirmation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        assistant_service,
        "llm_chat",
        lambda _messages: (
            '{"content":"Je vous propose ce créneau.","proposals":[{"kind":"calendar_event",'
            '"payload":{"title":"Dîner avec des amis","starts_at":"2026-10-03T18:00:00+02:00",'
            '"ends_at":"2026-10-03T22:00:00+02:00","timezone":"Europe/Paris"}}]}'
        ),
    )
    auth = authenticated_headers(client)
    first = client.post(
        "/api/assistant/turn", headers=auth, json={"text": "Samedi, des amis viennent"}
    )
    proposal_id = first.json()["message"]["proposals"][0]["id"]
    assert (
        client.post(f"/api/assistant/proposals/{proposal_id}/confirm", headers=auth).status_code
        == 200
    )
    listed = client.get("/api/assistant/calendar/events", headers=auth)
    assert listed.status_code == 200
    assert [event["title"] for event in listed.json()["events"]] == ["Dîner avec des amis"]
    other = client.post(
        "/api/auth/register",
        json={
            **register_payload(),
            "email": "other-calendar@example.com",
            "installation_id": "other-calendar-device",
        },
    ).json()
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}
    assert client.get("/api/assistant/calendar/events", headers=other_headers).json() == {
        "events": []
    }

    second = client.post("/api/assistant/turn", headers=auth, json={"text": "Ajoute le même dîner"})
    assert second.status_code == 201
    assert second.json()["message"]["proposals"] == []
    assert "déjà" in second.json()["message"]["content"]


def test_deadline_and_recurring_reminder_are_only_created_after_confirmation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    responses = iter(
        (
            '{"content":"Je vous propose un rappel avant la fin de garantie.","proposals":['
            '{"kind":"deadline_reminder","payload":{"title":"Fin de garantie du lave-linge",'
            '"due_date":"2027-03-10","lead_days":7,"timezone":"Europe/Paris"}}]}',
            '{"content":"Je vous propose ce rappel récurrent.","proposals":['
            '{"kind":"recurring_reminder","payload":{"title":"Contrôle technique",'
            '"anchor_date":"2026-09-18","recurrence_months":24,"lead_days":14,'
            '"timezone":"Europe/Paris"}}]}',
        )
    )
    monkeypatch.setattr(assistant_service, "llm_chat", lambda _messages: next(responses))
    auth = authenticated_headers(client)

    deadline = client.post(
        "/api/assistant/turn", headers=auth, json={"text": "Garantie lave-linge"}
    )
    deadline_id = deadline.json()["message"]["proposals"][0]["id"]
    assert (
        client.post(f"/api/assistant/proposals/{deadline_id}/confirm", headers=auth).status_code
        == 200
    )
    recurring = client.post(
        "/api/assistant/turn", headers=auth, json={"text": "Contrôle technique"}
    )
    recurring_id = recurring.json()["message"]["proposals"][0]["id"]
    assert (
        client.post(f"/api/assistant/proposals/{recurring_id}/confirm", headers=auth).status_code
        == 200
    )

    session = client.app.state.test_session_factory()
    try:
        task = session.query(PersonalTask).one()
        rule = session.query(RecurringReminder).one()
        assert task.reminder_at == datetime(2027, 3, 3, 8)
        assert rule.next_due_date.isoformat() == "2028-09-18"
        assert rule.next_reminder_at == datetime(2028, 9, 4, 7)
    finally:
        session.close()


def test_grocery_and_training_writes_require_explicit_confirmation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    responses = iter(
        (
            '{"content":"Je propose cet article.","proposals":[{"kind":"grocery_item",'
            '"payload":{"label":"Lait entier"}}]}',
            '{"content":"Je propose cette séance.","proposals":[{"kind":"training",'
            '"payload":{"label":"Course légère","training_type":"course",'
            '"timing":"Samedi matin"}}]}',
        )
    )
    monkeypatch.setattr(assistant_service, "llm_chat", lambda _messages: next(responses))
    auth = authenticated_headers(client)

    grocery = client.post("/api/assistant/turn", headers=auth, json={"text": "Ajoute du lait"})
    assert grocery.status_code == 201
    grocery_proposal = grocery.json()["message"]["proposals"][0]
    assert client.get("/api/personal/groceries", headers=auth).json() == []
    assert (
        client.post(
            f"/api/assistant/proposals/{grocery_proposal['id']}/confirm", headers=auth
        ).status_code
        == 200
    )

    training = client.post(
        "/api/assistant/turn", headers=auth, json={"text": "Programme une course"}
    )
    assert training.status_code == 201
    training_proposal = training.json()["message"]["proposals"][0]
    assert client.get("/api/personal/trainings", headers=auth).json() == []
    assert (
        client.post(
            f"/api/assistant/proposals/{training_proposal['id']}/confirm", headers=auth
        ).status_code
        == 200
    )

    session = client.app.state.test_session_factory()
    try:
        assert session.query(GroceryItem).one().label == "Lait entier"
        assert session.query(TrainingSession).one().label == "Course légère"
    finally:
        session.close()
