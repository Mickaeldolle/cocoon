from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.commands.run_capture_worker import process_once
from app.main import app
from app.modules.assistant.models import ProposalExecution
from app.modules.neural import service as neural_service
from app.modules.neural import worker as neural_worker
from app.modules.neural.models import (
    Capture,
    CaptureRun,
    CaptureRunStatus,
    MemoryItem,
    NeuralProposal,
)
from app.modules.neural.worker import process_capture_run


@pytest.fixture(autouse=True)
def disable_live_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(neural_service, "llm_chat", lambda _messages: None)


def headers(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "A-strong-password-123",
            "display_name": "Marie Dupont",
            "installation_id": email,
            "name": "Test device",
            "platform": "ios",
        },
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_capture_is_private_and_never_creates_an_action_without_confirmation(
    client: TestClient,
) -> None:
    marie = headers(client, "marie-neural@example.com")
    paul = headers(client, "paul-neural@example.com")
    response = client.post(
        "/api/captures",
        headers=marie,
        json={"text": "Pense à acheter du lait demain", "timezone": "Europe/Paris"},
    )
    assert response.status_code == 201
    run_id = response.json()["run_id"]
    run = client.get(f"/api/runs/{run_id}", headers=marie)
    assert run.status_code == 200
    assert run.json()["status"] == "completed"
    assert [event["event_type"] for event in run.json()["events"]] == [
        "capture_persisted",
        "claimed",
        "understand_started",
        "completed",
    ]
    resumed = client.get(f"/api/runs/{run_id}?after_sequence=1", headers=marie)
    assert [event["event_type"] for event in resumed.json()["events"]] == [
        "claimed",
        "understand_started",
        "completed",
    ]
    assert client.get(f"/api/runs/{run_id}", headers=paul).status_code == 404
    proposal = response.json()["proposals"][0]
    with app.state.test_session_factory() as session:
        stored_proposal = session.get(NeuralProposal, UUID(proposal["id"]))
        assert stored_proposal is not None
        assert str(stored_proposal.source_run_id) == run_id
    assert client.get("/api/personal/tasks", headers=marie).json() == []
    assert client.get("/api/home", headers=paul).json() == {"signals": []}
    assert (
        client.post(f"/api/neural-proposals/{proposal['id']}/confirm", headers=paul).status_code
        == 404
    )
    assert (
        client.post(f"/api/neural-proposals/{proposal['id']}/confirm", headers=marie).status_code
        == 200
    )
    assert [task["title"] for task in client.get("/api/personal/tasks", headers=marie).json()] == [
        "acheter du lait demain"
    ]


def test_confirmed_capture_memory_keeps_source_run_provenance(client: TestClient) -> None:
    auth = headers(client, "memory-provenance@example.com")
    response = client.post(
        "/api/captures",
        headers=auth,
        json={"text": "Je préfère le thé", "timezone": "Europe/Paris"},
    )
    assert response.status_code == 201
    note = next(item for item in response.json()["proposals"] if item["capability"] == "note")

    confirmed = client.post(f"/api/neural-proposals/{note['id']}/confirm", headers=auth)
    assert confirmed.status_code == 200

    with app.state.test_session_factory() as session:
        memory = session.scalar(select(MemoryItem).where(MemoryItem.user_id.is_not(None)))
        assert memory is not None
        assert memory.source_run_id == UUID(response.json()["run_id"])


def test_home_is_limited_to_three_signals(client: TestClient) -> None:
    auth = headers(client, "home-neural@example.com")
    for title in (
        "Appeler le dentiste",
        "Acheter du pain",
        "Réserver le train",
        "Envoyer le dossier",
    ):
        assert client.post("/api/captures", headers=auth, json={"text": title}).status_code == 201
    response = client.get("/api/home", headers=auth)
    assert response.status_code == 200
    assert len(response.json()["signals"]) <= 3


def test_capture_uses_a_validated_llm_interpretation_when_available(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(
        neural_service,
        "llm_chat",
        lambda _messages: (
            '{"kind":"intention","summary":"Acheter du thé vert",'
            '"reason":"Vous avez formulé une action explicite.",'
            '"capability":"task","clarification":null}'
        ),
    )
    auth = headers(client, "llm-neural@example.com")
    response = client.post(
        "/api/captures",
        headers=auth,
        json={
            "text": "Rappelle-moi d’acheter du thé vert demain à 18 h",
            "timezone": "Europe/Paris",
        },
    )
    assert response.status_code == 201
    assert response.json()["mode"] == "llm"
    assert response.json()["summary"] == "Acheter du thé vert"
    assert response.json()["proposals"][0]["payload"]["due_date"]
    home = client.get("/api/home", headers=auth)
    assert home.json()["signals"][0]["title"] == "Acheter du thé vert"


def test_capture_stream_emits_safe_progress_and_keeps_memory_until_choice(
    client: TestClient,
) -> None:
    auth = headers(client, "stream-neural@example.com")
    response = client.post(
        "/api/captures/stream",
        headers=auth,
        json={"text": "Pense à appeler le dentiste demain à 18h", "timezone": "Europe/Paris"},
    )
    assert response.status_code == 200
    assert "event: run_event" in response.text
    assert '"run_id":' in response.text
    assert response.text.index('"event_type": "capture_persisted"') < response.text.index(
        '"event_type": "understand_started"'
    )
    assert '"event_type": "understand_started"' in response.text
    assert "id: 3" in response.text
    assert "event: complete" in response.text
    session = app.state.test_session_factory()
    try:
        assert session.scalar(select(MemoryItem)) is None
        capture = session.scalar(select(Capture))
        assert capture is not None
        assert capture.content_hash is not None
        assert len(capture.content_hash) == 64
    finally:
        session.close()


def test_capture_stream_replays_from_last_event_id_with_idempotency(
    client: TestClient,
) -> None:
    auth = headers(client, "stream-resume@example.com")
    request = {
        "text": "Préparer le dossier vendredi",
        "timezone": "Europe/Paris",
    }
    first = client.post(
        "/api/captures/stream",
        headers={**auth, "X-Capture-Idempotency-Key": "stream-resume-1"},
        json=request,
    )
    assert first.status_code == 200
    assert '"event_type": "capture_persisted"' in first.text

    resumed = client.post(
        "/api/captures/stream",
        headers={
            **auth,
            "X-Capture-Idempotency-Key": "stream-resume-1",
            "Last-Event-ID": "1",
        },
        json=request,
    )
    assert resumed.status_code == 200
    assert '"event_type": "capture_persisted"' not in resumed.text
    assert '"event_type": "understand_started"' in resumed.text
    assert resumed.text.count("event: complete") == 1


def test_engagement_keeps_explicit_weekday_and_day_when_llm_is_generic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        neural_service,
        "llm_chat",
        lambda _messages: (
            '{"kind":"information","summary":"une date",'
            '"reason":"Information generale.","capability":null,'
            'clarification":"À quelle heure ?"}'
        ),
    )
    result = neural_service.understand("J'ai un entretien vendredi 25")
    assert result.kind.value == "engagement"
    assert "entretien" in result.summary
    assert "vendredi 25" in result.summary
    assert "vendredi 25" in (result.clarification or "")


def test_question_cannot_be_reclassified_as_durable_memory_by_llm(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        neural_service,
        "llm_chat",
        lambda _messages: (
            '{"kind":"information","summary":"La personne utilise Docker",'
            '"reason":"Le modèle a inféré une information.",'
            '"capability":null,"clarification":null}'
        ),
    )
    auth = headers(client, "question-no-memory@example.com")
    response = client.post(
        "/api/captures",
        headers=auth,
        json={"text": "Comment fonctionne Docker ?", "timezone": "Europe/Paris"},
    )

    assert response.status_code == 201
    assert response.json()["proposals"] == []
    assert response.json()["clarification"]
    with app.state.test_session_factory() as session:
        assert session.scalar(select(MemoryItem)) is None


def test_rules_resolve_explicit_relative_and_numeric_dates() -> None:
    reference = datetime(2026, 9, 22, tzinfo=UTC).date()

    assert neural_service.infer_relative_date("à faire aujourd'hui", reference) == reference
    assert (
        neural_service.infer_relative_date("rappelle-moi après-demain", reference).isoformat()
        == "2026-09-24"
    )
    assert (
        neural_service.infer_relative_date("rendez-vous dans 12 jours", reference).isoformat()
        == "2026-10-04"
    )
    assert neural_service.infer_explicit_date("le 05/10", reference).isoformat() == "2026-10-05"
    assert neural_service.infer_explicit_date("le 31/02", reference) is None


def test_reminder_choice_creates_task_with_reminder_and_cancels_alternatives(
    client: TestClient,
) -> None:
    auth = headers(client, "reminder-neural@example.com")
    result = client.post(
        "/api/captures",
        headers=auth,
        json={"text": "Appeler le dentiste demain à 18h", "timezone": "Europe/Paris"},
    ).json()
    reminder = next(item for item in result["proposals"] if item["capability"] == "reminder")
    assert (
        client.post(f"/api/neural-proposals/{reminder['id']}/confirm", headers=auth).status_code
        == 200
    )
    tasks = client.get("/api/personal/tasks", headers=auth).json()
    assert tasks[0]["reminder_at"] is not None
    assert client.get("/api/home", headers=auth).json()["signals"]
    session = app.state.test_session_factory()
    try:
        execution = session.scalar(
            select(ProposalExecution).where(
                ProposalExecution.proposal_type == "capture",
                ProposalExecution.proposal_id == UUID(reminder["id"]),
            )
        )
        assert execution is not None
        assert execution.status == "committed"
    finally:
        session.close()


def test_expired_capture_proposal_cannot_be_confirmed(client: TestClient) -> None:
    auth = headers(client, "expired-neural@example.com")
    result = client.post(
        "/api/captures",
        headers=auth,
        json={"text": "Appeler le dentiste demain à 18h", "timezone": "Europe/Paris"},
    ).json()
    proposal_id = result["proposals"][0]["id"]
    session = app.state.test_session_factory()
    try:
        proposal = session.get(NeuralProposal, UUID(proposal_id))
        assert proposal is not None
        proposal.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()
    finally:
        session.close()

    response = client.post(f"/api/neural-proposals/{proposal_id}/confirm", headers=auth)
    assert response.status_code == 409


def test_invalid_capture_proposal_is_failed_and_cannot_be_replayed(client: TestClient) -> None:
    auth = headers(client, "failed-capture@example.com")
    result = client.post(
        "/api/captures",
        headers=auth,
        json={"text": "Acheter du lait demain", "timezone": "Europe/Paris"},
    ).json()
    proposal_id = result["proposals"][0]["id"]

    session = client.app.state.test_session_factory()
    try:
        proposal = session.get(NeuralProposal, UUID(proposal_id))
        assert proposal is not None
        proposal.payload = {"title": ""}
        session.commit()
    finally:
        session.close()

    response = client.post(f"/api/neural-proposals/{proposal_id}/confirm", headers=auth)
    assert response.status_code == 422
    assert response.json()["detail"] == "La proposition est invalide."

    session = client.app.state.test_session_factory()
    try:
        proposal = session.get(NeuralProposal, UUID(proposal_id))
        execution = session.scalar(
            select(ProposalExecution).where(
                ProposalExecution.proposal_type == "capture",
                ProposalExecution.proposal_id == UUID(proposal_id),
            )
        )
        assert proposal is not None
        assert proposal.status == "failed"
        assert execution is not None
        assert execution.status == "failed"
        assert execution.error_code == "invalid_payload"
    finally:
        session.close()

    replay = client.post(f"/api/neural-proposals/{proposal_id}/confirm", headers=auth)
    assert replay.status_code == 409


def test_stale_capture_proposal_version_is_rejected_without_effect(client: TestClient) -> None:
    auth = headers(client, "stale-capture@example.com")
    result = client.post(
        "/api/captures",
        headers=auth,
        json={"text": "Acheter du lait demain", "timezone": "Europe/Paris"},
    ).json()
    proposal = result["proposals"][0]

    session = client.app.state.test_session_factory()
    try:
        stored = session.get(NeuralProposal, UUID(proposal["id"]))
        assert stored is not None
        stored.payload_version = 2
        session.commit()
    finally:
        session.close()

    stale = client.post(
        f"/api/neural-proposals/{proposal['id']}/confirm",
        headers={**auth, "X-Proposal-Version": "1"},
    )
    assert stale.status_code == 409
    assert client.get("/api/personal/tasks", headers=auth).json() == []

    current = client.post(f"/api/neural-proposals/{proposal['id']}/confirm", headers=auth)
    assert current.status_code == 200
    assert current.json()["confirmed_at"] is not None


def test_capture_proposal_can_be_cancelled_and_cannot_be_confirmed_afterward(
    client: TestClient,
) -> None:
    auth = headers(client, "cancel-proposal@example.com")
    result = client.post(
        "/api/captures",
        headers=auth,
        json={"text": "Appeler le dentiste demain à 18h", "timezone": "Europe/Paris"},
    ).json()
    proposal_id = result["proposals"][0]["id"]

    cancelled = client.post(f"/api/neural-proposals/{proposal_id}/cancel", headers=auth)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert (
        client.post(f"/api/neural-proposals/{proposal_id}/confirm", headers=auth).status_code
        == 409
    )
    repeated = client.post(f"/api/neural-proposals/{proposal_id}/cancel", headers=auth)
    assert repeated.status_code == 200
    assert repeated.json()["status"] == "cancelled"


def test_running_capture_run_can_be_cancelled_by_its_owner(client: TestClient) -> None:
    auth = headers(client, "cancel-run@example.com")
    result = client.post("/api/captures", headers=auth, json={"text": "Une idée"}).json()
    run_id = result["run_id"]
    session = app.state.test_session_factory()
    try:
        run = session.get(CaptureRun, UUID(run_id))
        assert run is not None
        run.status = CaptureRunStatus.RUNNING
        run.finished_at = None
        session.commit()
    finally:
        session.close()

    cancelled = client.post(f"/api/runs/{run_id}/cancel", headers=auth)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["events"][-1]["event_type"] == "cancelled"


def test_separate_capture_worker_reclaims_a_queued_run(client: TestClient) -> None:
    auth = headers(client, "capture-worker@example.com")
    result = client.post(
        "/api/captures", headers=auth, json={"text": "Une idée à revoir"}
    ).json()
    session = app.state.test_session_factory()
    try:
        run = session.get(CaptureRun, UUID(result["run_id"]))
        assert run is not None
        run.status = CaptureRunStatus.QUEUED
        run.finished_at = None
        run.error_code = None
        session.commit()
    finally:
        session.close()

    assert (
        process_once("test-capture-worker", app.state.test_session_factory)
        == result["run_id"]
    )
    resumed = client.get(f"/api/runs/{result['run_id']}", headers=auth)
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "completed"
    assert "claimed" in [event["event_type"] for event in resumed.json()["events"]]


def test_capture_queue_endpoint_defers_processing_to_worker(client: TestClient) -> None:
    auth = headers(client, "queued-capture@example.com")
    response = client.post(
        "/api/captures/queue",
        headers={**auth, "X-Capture-Idempotency-Key": "queued-capture-1"},
        json={"text": "Préparer le dossier lundi", "timezone": "Europe/Paris"},
    )
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert [event["event_type"] for event in response.json()["events"]] == [
        "capture_persisted"
    ]

    run_id = response.json()["id"]
    assert process_once("queued-capture-worker", client.app.state.test_session_factory) == run_id
    completed = client.get(f"/api/runs/{run_id}", headers=auth)
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    home = client.get("/api/home", headers=auth)
    assert home.status_code == 200
    assert len(home.json()["signals"]) == 1
    proposal_id = home.json()["signals"][0]["proposal_id"]
    confirmed = client.post(f"/api/neural-proposals/{proposal_id}/confirm", headers=auth)
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"


def test_cancellation_during_understanding_does_not_persist_proposals(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = headers(client, "cancel-during-understanding@example.com")
    result = client.post(
        "/api/captures", headers=auth, json={"text": "Une idée à annuler"}
    ).json()
    run_id = UUID(result["run_id"])

    session = app.state.test_session_factory()
    try:
        run = session.get(CaptureRun, run_id)
        assert run is not None
        run.status = CaptureRunStatus.QUEUED
        run.finished_at = None
        run.error_code = None
        session.query(NeuralProposal).filter(NeuralProposal.capture_id == run.capture_id).delete()
        session.commit()
    finally:
        session.close()

    original_understand = neural_worker.understand

    def cancel_before_return(content: str):
        other_session = app.state.test_session_factory()
        try:
            current = other_session.get(CaptureRun, run_id)
            assert current is not None
            current.status = CaptureRunStatus.CANCELLED
            current.finished_at = datetime.now(UTC)
            other_session.commit()
        finally:
            other_session.close()
        return original_understand(content)

    monkeypatch.setattr(neural_worker, "understand", cancel_before_return)
    processing_session = app.state.test_session_factory()
    try:
        with pytest.raises(Exception) as error:
            process_capture_run(processing_session, run_id, worker_id="cancel-race-worker")
        assert error.value.status_code == 409
    finally:
        processing_session.close()

    session = app.state.test_session_factory()
    try:
        run = session.get(CaptureRun, run_id)
        assert run is not None
        assert run.status is CaptureRunStatus.CANCELLED
        assert (
            session.query(NeuralProposal)
            .filter(NeuralProposal.capture_id == run.capture_id)
            .count()
            == 0
        )
    finally:
        session.close()


def test_dated_appointment_becomes_a_reminder_instead_of_a_generic_note(
    client: TestClient,
) -> None:
    auth = headers(client, "appointment-neural@example.com")
    result = client.post(
        "/api/captures",
        headers=auth,
        json={"text": "J'ai un entretien vendredi 25", "timezone": "Europe/Paris"},
    ).json()
    assert result["proposals"]
    assert [proposal["capability"] for proposal in result["proposals"]] == ["reminder"]
    proposal = result["proposals"][0]
    assert "entretien" in proposal["payload"]["title"]
    confirmed = client.post(f"/api/neural-proposals/{proposal['id']}/confirm", headers=auth)
    assert confirmed.status_code == 200
    assert client.get("/api/personal/tasks", headers=auth).json()[0]["reminder_at"]


def test_capture_idempotency_key_reuses_completed_run(client: TestClient) -> None:
    auth = headers(client, "idempotent-neural@example.com")
    request = {"text": "Appeler le dentiste demain", "timezone": "Europe/Paris"}
    first = client.post(
        "/api/captures",
        headers={**auth, "X-Capture-Idempotency-Key": "capture-001"},
        json=request,
    )
    second = client.post(
        "/api/captures",
        headers={**auth, "X-Capture-Idempotency-Key": "capture-001"},
        json={"text": "Texte différent", "timezone": "Europe/Paris"},
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["run_id"] == first.json()["run_id"]
    session = app.state.test_session_factory()
    try:
        assert session.query(CaptureRun).count() == 1
        assert session.query(Capture).count() == 1
    finally:
        session.close()


def test_capture_without_idempotency_key_reuses_same_completed_content(client: TestClient) -> None:
    auth = headers(client, "hash-neural@example.com")
    request = {"text": "  Appeler   le dentiste demain  ", "timezone": "Europe/Paris"}
    first = client.post("/api/captures", headers=auth, json=request)
    second = client.post(
        "/api/captures",
        headers=auth,
        json={"text": "Appeler le dentiste demain", "timezone": "UTC"},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["run_id"] == first.json()["run_id"]
    with app.state.test_session_factory() as session:
        assert session.query(CaptureRun).count() == 1
        assert session.query(Capture).count() == 1
