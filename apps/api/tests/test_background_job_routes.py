"""The hosted scheduler can trigger only one authenticated job per call."""

from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.modules.auth.models import User


def test_internal_jobs_require_a_private_token_before_work(client: TestClient, monkeypatch) -> None:
    from app.modules.neural import worker_router

    calls = []

    @contextmanager
    def session_factory():
        calls.append("opened")
        yield object()

    monkeypatch.setattr(worker_router, "SessionLocal", session_factory)
    monkeypatch.setattr(
        worker_router,
        "get_settings",
        lambda: SimpleNamespace(internal_worker_token=None, memory_embeddings_enabled=True),
    )
    for path in ("captures", "memory"):
        assert client.post(f"/api/internal/jobs/{path}/run").status_code == 404

    monkeypatch.setattr(
        worker_router,
        "get_settings",
        lambda: SimpleNamespace(internal_worker_token="a" * 32, memory_embeddings_enabled=True),
    )
    for path in ("captures", "memory"):
        url = f"/api/internal/jobs/{path}/run"
        assert client.post(url).status_code == 401
        assert client.post(url, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert calls == []


def test_internal_jobs_process_one_item_and_report_disabled_memory(
    client: TestClient, monkeypatch
) -> None:
    from app.modules.neural import worker_router

    token = "a" * 32
    auth = {"Authorization": f"Bearer {token}"}
    calls = []

    @contextmanager
    def session_factory():
        calls.append("session")
        yield object()

    monkeypatch.setattr(worker_router, "SessionLocal", session_factory)
    monkeypatch.setattr(
        worker_router,
        "get_settings",
        lambda: SimpleNamespace(internal_worker_token=token, memory_embeddings_enabled=True),
    )
    monkeypatch.setattr(
        worker_router,
        "process_next_pending_run",
        lambda _session, _worker_id: calls.append("capture") or uuid4(),
    )
    monkeypatch.setattr(
        worker_router,
        "process_one_memory",
        lambda _factory: calls.append("memory") or uuid4(),
    )

    assert client.post("/api/internal/jobs/captures/run", headers=auth).json() == {
        "processed": True
    }
    assert client.post("/api/internal/jobs/memory/run", headers=auth).json() == {
        "processed": True
    }
    assert client.get("/api/internal/jobs/captures/run", headers=auth).json() == {
        "processed": True
    }
    assert calls == ["session", "capture", "memory", "session", "capture"]

    monkeypatch.setattr(
        worker_router,
        "get_settings",
        lambda: SimpleNamespace(internal_worker_token=token, memory_embeddings_enabled=False),
    )
    assert client.post("/api/internal/jobs/memory/run", headers=auth).status_code == 409
    assert calls == ["session", "capture", "memory", "session", "capture"]


def test_internal_capture_route_completes_one_queued_run(client: TestClient, monkeypatch) -> None:
    from app.modules.neural import service, worker_router

    token = "b" * 32
    monkeypatch.setattr(
        worker_router,
        "get_settings",
        lambda: SimpleNamespace(internal_worker_token=token, memory_embeddings_enabled=False),
    )
    monkeypatch.setattr(worker_router, "SessionLocal", app.state.test_session_factory)
    monkeypatch.setattr(service, "llm_chat", lambda _messages: None)

    account = client.post(
        "/api/auth/register",
        json={
            "email": "scheduled-capture@example.com",
            "password": "A-strong-password-123",
            "display_name": "Scheduled capture",
            "installation_id": str(uuid4()),
            "name": "Test device",
            "platform": "ios",
        },
    ).json()
    with app.state.test_session_factory() as session:
        user = session.query(User).filter_by(email="scheduled-capture@example.com").one()
        user.enable_assistant = True
        session.commit()
    auth = {"Authorization": f"Bearer {account['access_token']}"}
    queued = client.post(
        "/api/captures/queue", headers=auth, json={"text": "Préparer un dossier"}
    )
    assert queued.status_code == 202
    run_id = queued.json()["id"]

    trigger = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/internal/jobs/captures/run", headers=trigger).json() == {
        "processed": True
    }
    assert client.get(f"/api/runs/{run_id}", headers=auth).json()["status"] == "completed"
    assert client.post("/api/internal/jobs/captures/run", headers=trigger).json() == {
        "processed": False
    }
