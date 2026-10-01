import logging

from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.modules.audit.models import AuditEvent
from app.modules.audit.service import client_ip
from app.modules.auth.models import User


def register(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        json={
            "email": "audit@example.com",
            "password": "A-strong-password-123",
            "display_name": "Audit",
            "installation_id": "audit-device",
            "name": "Test device",
            "platform": "ios",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_access_and_mutations_are_attributed_without_payloads(client: TestClient) -> None:
    tokens = register(client)
    login = client.post(
        "/api/auth/login",
        json={
            "email": "audit@example.com",
            "password": "A-strong-password-123",
            "installation_id": "audit-device",
            "name": "Test device",
            "platform": "ios",
        },
    )
    assert login.status_code == 200
    bad_login = client.post(
        "/api/auth/login",
        json={
            "email": "unknown@example.com",
            "password": "do-not-log-this",
            "installation_id": "audit-device",
            "name": "Test device",
            "platform": "ios",
        },
    )
    assert bad_login.status_code == 401
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    changed = client.put(
        "/api/auth/consents/assistant.memory",
        headers=headers,
        json={"policy_version": 2, "source": "mobile"},
    )
    assert changed.status_code == 200

    with client.app.state.test_session_factory() as session:
        events = list(session.scalars(select(AuditEvent).order_by(AuditEvent.occurred_at)))
        user = session.scalar(select(User).where(User.email == "audit@example.com"))
    assert user is not None
    assert [event.action for event in events].count("auth.login.password") == 2
    assert any(
        event.action == "auth.register" and event.actor_user_id == user.id for event in events
    )
    assert any(event.action == "api.put" and event.actor_user_id == user.id for event in events)
    assert any(
        event.action == "auth.login.password"
        and event.outcome == "denied"
        and event.actor_user_id is None
        for event in events
    )
    assert any(str(event.request_id) == changed.headers["X-Request-ID"] for event in events)
    assert all("password" not in (event.route or "") for event in events)
    assert all("assistant.memory" not in (event.route or "") for event in events)
    registration = next(event for event in events if event.action == "auth.register")
    assert registration.device_id is not None
    assert registration.client_platform == "ios"
    assert registration.request_details == {"platform": "ios"}
    assert registration.response_details["token_issued"] is True
    assert registration.duration_ms >= 0
    denied = next(
        event
        for event in events
        if event.action == "auth.login.password" and event.outcome == "denied"
    )
    assert len(denied.attempted_identity_ref) == 64
    assert denied.request_details == {"platform": "ios"}
    assert denied.response_details["error_code"] == "unauthorized"
    consent = next(event for event in events if event.action == "api.put")
    assert consent.request_details == {
        "policy_key": "assistant.memory",
        "policy_version": 2,
    }
    assert consent.response_details["active"] is True
    assert consent.response_details["policy_version"] == 2
    serialized = " ".join(str(event.__dict__) for event in events)
    assert "A-strong-password-123" not in serialized
    assert "do-not-log-this" not in serialized
    assert "unknown@example.com" not in serialized
    assert tokens["access_token"] not in serialized


def test_audit_reader_is_admin_only_and_secret_routes_are_hidden(client: TestClient) -> None:
    tokens = register(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert client.get("/api/admin/audit-events", headers=headers).status_code == 403

    secret = client.post(
        "/api/secret/unlock", json={"password": "a-long-enough-wrong-password"}, headers=headers
    )
    assert secret.status_code == 401
    with client.app.state.test_session_factory() as session:
        user = session.scalar(select(User).where(User.email == "audit@example.com"))
        assert user is not None
        user.is_superadmin = True
        session.commit()
        user_id = user.id

    response = client.get(
        "/api/admin/audit-events?limit=1&token=must-not-be-logged", headers=headers
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
    page = client.get("/api/admin/audit-events", headers=headers)
    assert page.status_code == 200
    secret_event = next(item for item in page.json() if item["action"] == "secret.unlock.password")
    assert secret_event["route"] is None
    assert secret_event["request_details"] is None
    assert secret_event["actor_user_id"] == str(user_id)
    assert secret_event["outcome"] == "denied"
    assert client.get("/api/admin/audit-events?limit=101", headers=headers).status_code == 422
    with client.app.state.test_session_factory() as session:
        read_events = list(
            session.scalars(select(AuditEvent).where(AuditEvent.action == "admin.audit.read"))
        )
    assert any(
        event.query_details == {"limit": 1}
        and event.actor_user_id == user_id
        and event.response_details["content_type"] == "application/json"
        for event in read_events
    )
    assert all("must-not-be-logged" not in str(event.query_details) for event in read_events)


def test_secret_resource_ids_do_not_reach_http_logs(client: TestClient, caplog) -> None:
    caplog.set_level(logging.INFO, logger="cocoon.http")
    tokens = register(client)
    resource_id = "8a40dd57-924e-4600-a95b-eb0ed4a22028"
    response = client.get(
        f"/api/secret/conversations/{resource_id}",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code in {401, 404}
    assert resource_id not in caplog.text
    assert "/api/secret/*" in caplog.text
    with client.app.state.test_session_factory() as session:
        secret_read = session.scalar(select(AuditEvent).where(AuditEvent.action == "secret.read"))
    assert secret_read is not None
    assert secret_read.route is None
    assert secret_read.request_details is None


def test_message_body_and_invitee_are_excluded_from_json_details(client: TestClient) -> None:
    tokens = register(client)
    other = client.post(
        "/api/auth/register",
        json={
            "email": "other-audit@example.com",
            "password": "another-strong-password-123",
            "display_name": "Other",
            "installation_id": "other-audit-device",
            "name": "Other device",
            "platform": "android",
        },
    )
    assert other.status_code == 201
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    created = client.post(
        "/api/conversations",
        headers=headers,
        json={"member_emails": ["other-audit@example.com"], "name": "Private family"},
    )
    assert created.status_code == 201
    body = "Confidential note"
    sent = client.post(
        f"/api/conversations/{created.json()['id']}/messages",
        headers=headers,
        json={"body": body},
    )
    assert sent.status_code == 201
    with client.app.state.test_session_factory() as session:
        events = list(
            session.scalars(
                select(AuditEvent).where(
                    AuditEvent.action.in_(["conversation.create", "message.send"])
                )
            )
        )
    created_event = next(event for event in events if event.action == "conversation.create")
    sent_event = next(event for event in events if event.action == "message.send")
    assert created_event.request_details == {"member_count": 2}
    assert sent_event.request_details["message_length"] == len(body)
    assert len(sent_event.request_details["conversation_ref"]) == 64
    assert created.json()["id"] not in str(sent_event.request_details)
    assert sent_event.response_details["resource_type"] == "message"
    details = " ".join(str((event.request_details, event.response_details)) for event in events)
    assert body not in details
    assert "Private family" not in details
    assert "other-audit@example.com" not in details


def test_forwarded_ip_is_used_only_for_a_trusted_peer(monkeypatch) -> None:
    monkeypatch.delenv("VERCEL", raising=False)
    request = Request(
        {
            "type": "http",
            "client": ("10.0.0.2", 1234),
            "headers": [(b"x-forwarded-for", b"203.0.113.9, 198.51.100.7")],
            "query_string": b"",
        }
    )
    monkeypatch.setattr(get_settings(), "audit_trusted_proxy_cidrs", [])
    assert client_ip(request) == ("10.0.0.2", "peer")
    monkeypatch.setattr(get_settings(), "audit_trusted_proxy_cidrs", ["10.0.0.0/8"])
    assert client_ip(request) == ("198.51.100.7", "forwarded")


def test_vercel_client_ip_uses_only_the_platform_header(monkeypatch) -> None:
    request = Request(
        {
            "type": "http",
            "client": ("10.0.0.2", 1234),
            "headers": [
                (b"x-forwarded-for", b"198.51.100.7"),
                (b"x-vercel-forwarded-for", b"203.0.113.9"),
            ],
            "query_string": b"",
        }
    )
    monkeypatch.setattr(get_settings(), "audit_trusted_proxy_cidrs", [])
    monkeypatch.delenv("VERCEL", raising=False)
    assert client_ip(request) == ("10.0.0.2", "peer")
    monkeypatch.setenv("VERCEL", "1")
    assert client_ip(request) == ("203.0.113.9", "vercel")
    request.scope["client"] = None
    assert client_ip(request) == ("203.0.113.9", "vercel")
    invalid = Request(
        {
            "type": "http",
            "client": ("10.0.0.2", 1234),
            "headers": [(b"x-vercel-forwarded-for", b"not-an-ip")],
            "query_string": b"",
        }
    )
    assert client_ip(invalid) == ("10.0.0.2", "peer")


def test_audit_stores_direct_ip_and_ignores_untrusted_forwarded_header(client: TestClient) -> None:
    with TestClient(client.app, client=("192.0.2.42", 50000)) as ip_client:
        response = ip_client.post(
            "/api/auth/login",
            headers={"X-Forwarded-For": "203.0.113.99"},
            json={
                "email": "absent-audit@example.com",
                "password": "wrong-password",
                "installation_id": "audit-device",
                "name": "Test device",
                "platform": "web",
            },
        )
    assert response.status_code == 401
    with client.app.state.test_session_factory() as session:
        event = session.scalar(select(AuditEvent).where(AuditEvent.action == "auth.login.password"))
    assert event is not None
    assert event.client_ip == "192.0.2.42"
    assert event.client_ip_source == "peer"


def test_button_press_is_attributed_and_only_accepts_known_action(client: TestClient) -> None:
    tokens = register(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    unauthenticated = client.post("/api/audit/button-press", json={"action": "home.profile.open"})
    assert unauthenticated.status_code == 401

    response = client.post(
        "/api/audit/button-press",
        headers=headers,
        json={"action": "home.profile.open"},
    )
    assert response.status_code == 204
    protected = client.post(
        "/api/audit/button-press",
        headers=headers,
        json={"action": "protected.press", "secret": "do-not-store"},
    )
    assert protected.status_code == 204
    rejected = client.post(
        "/api/audit/button-press",
        headers=headers,
        json={"action": "profile.open:someone@example.com", "secret": "do-not-store"},
    )
    assert rejected.status_code == 422

    with client.app.state.test_session_factory() as session:
        events = list(
            session.scalars(select(AuditEvent).where(AuditEvent.action == "ui.button.press"))
        )
        user = session.scalar(select(User).where(User.email == "audit@example.com"))
    assert user is not None
    accepted = next(event for event in events if event.status_code == 204)
    assert accepted.actor_user_id == user.id
    assert accepted.session_id is not None
    assert accepted.device_id is not None
    assert accepted.client_platform == "ios"
    assert accepted.method == "POST"
    assert accepted.route == "/api/audit/button-press"
    assert accepted.request_details == {"ui_action": "home.profile.open"}
    assert accepted.outcome == "success"
    assert any(event.request_details == {"ui_action": "protected.press"} for event in events)
    assert all("do-not-store" not in str(event.__dict__) for event in events)
    assert all("someone@example.com" not in str(event.__dict__) for event in events)
