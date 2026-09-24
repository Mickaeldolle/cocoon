import logging

from fastapi.testclient import TestClient

from app import main


def test_http_correlation_id_is_returned_and_logs_contain_no_request_body(
    client: TestClient, caplog
) -> None:
    caplog.set_level(logging.INFO, logger="cocoon.http")
    response = client.post("/api/auth/register", json={
        "email": "observability@example.com",
        "password": "A-strong-password-123",
        "display_name": "Observability",
        "installation_id": "observability-device",
        "name": "Test device",
        "platform": "ios",
    })
    assert response.status_code == 201
    request_id = response.headers.get("X-Request-ID")
    assert request_id
    assert any(request_id in record.message for record in caplog.records)
    assert all("A-strong-password-123" not in record.message for record in caplog.records)
    assert all("observability@example.com" not in record.message for record in caplog.records)


def test_client_correlation_id_is_normalized(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "not-a-safe-id\nforged"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "not-a-safe-id\nforged"
    assert len(response.headers["X-Request-ID"]) == 36


def test_liveness_and_readiness_are_distinct(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ready"}


def test_readiness_reports_database_failure_without_changing_liveness(
    client: TestClient, monkeypatch
) -> None:
    class BrokenEngine:
        def connect(self):
            raise RuntimeError("database offline")

    monkeypatch.setattr(main, "engine", BrokenEngine())
    assert client.get("/health").status_code == 200
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["detail"] == "database_not_ready"


def test_metrics_are_private_and_expose_only_aggregate_counters(
    client: TestClient, monkeypatch
) -> None:
    assert client.get("/internal/metrics").status_code == 404
    token = "m" * 32
    monkeypatch.setattr(main.settings, "metrics_token", token)

    response = client.get("/internal/metrics", headers={"X-Metrics-Token": token})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "cocoon_http_requests_total" in response.text
    assert "observability@example.com" not in response.text
    assert "Authorization" not in response.text


def test_browser_preflight_allows_mvp_mutation_and_resume_headers(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(main.settings, "cors_origins", ["http://localhost:8081"])
    response = client.options(
        "/api/memories/example",
        headers={
            "Origin": "http://localhost:8081",
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": (
                "authorization,content-type,last-event-id,x-capture-idempotency-key,x-request-id"
            ),
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:8081"
    assert "DELETE" in response.headers["access-control-allow-methods"]
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "last-event-id" in allowed_headers
    assert "x-capture-idempotency-key" in allowed_headers
