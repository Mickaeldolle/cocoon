from types import SimpleNamespace

from fastapi.testclient import TestClient


def test_scheduler_route_requires_shared_secret_and_limits_work(
    client: TestClient, monkeypatch
) -> None:
    from app.modules.assistant import worker_router

    calls: list[int | None] = []
    monkeypatch.setattr(
        worker_router,
        "get_settings",
        lambda: SimpleNamespace(notification_worker_token=None),
    )
    url = "/api/internal/notifications/run"
    assert client.post(url).status_code == 404

    monkeypatch.setattr(
        worker_router,
        "get_settings",
        lambda: SimpleNamespace(notification_worker_token="a" * 32),
    )
    monkeypatch.setattr(
        worker_router,
        "process_once",
        lambda *, max_items: (calls.append(max_items) or (2, 1)),
    )
    assert client.post(url).status_code == 401
    assert client.post(url, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert calls == []
    response = client.post(url, headers={"Authorization": f"Bearer {'a' * 32}"})
    assert response.status_code == 200
    assert response.json() == {"queued": 2, "sent": 1}
    assert client.get(url, headers={"Authorization": f"Bearer {'a' * 32}"}).status_code == 200
    assert calls == [3, 3]
