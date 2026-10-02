from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.modules.auth.models import User
from app.modules.neural.models import CaptureRun, CaptureRunStatus
from app.modules.neural.worker import process_capture_run


def test_assistant_access_is_disabled_by_default_and_tracks_manual_db_changes(
    client: TestClient,
) -> None:
    registered = client.post(
        "/api/auth/register",
        json={
            "email": "access@example.com",
            "display_name": "Accès",
            "password": "A-strong-password-123",
            "installation_id": "assistant-access-test",
            "name": "Test device",
            "platform": "web",
        },
    )
    assert registered.status_code == 201
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=headers).json()["enable_assistant"] is False

    for path in ("/api/assistant/chat", "/api/assistant/chat/stream", "/api/assistant/turn"):
        response = client.post(path, headers=headers, json={"text": "Bonjour"})
        assert response.status_code == 403
    denied_capture = client.post("/api/captures/queue", headers=headers, json={"text": "Une idée"})
    assert denied_capture.status_code == 403

    with client.app.state.test_session_factory() as session:
        user = session.scalar(select(User).where(User.email == "access@example.com"))
        assert user is not None
        user.enable_assistant = True
        session.commit()

    assert client.get("/api/auth/me", headers=headers).json()["enable_assistant"] is True
    assert client.get("/api/assistant/history", headers=headers).status_code == 200
    allowed_capture = client.post("/api/captures/queue", headers=headers, json={"text": "Une idée"})
    assert allowed_capture.status_code == 202
    queued_run_id = UUID(allowed_capture.json()["id"])

    with client.app.state.test_session_factory() as session:
        user = session.scalar(select(User).where(User.email == "access@example.com"))
        assert user is not None
        user.enable_assistant = False
        session.commit()

    assert client.get("/api/auth/me", headers=headers).json()["enable_assistant"] is False
    denied_again = client.post("/api/assistant/chat", headers=headers, json={"text": "Bonjour"})
    assert denied_again.status_code == 403
    with client.app.state.test_session_factory() as session:
        with pytest.raises(HTTPException) as error:
            process_capture_run(session, queued_run_id)
        assert error.value.status_code == 403
        assert session.get(CaptureRun, queued_run_id).status is CaptureRunStatus.CANCELLED
