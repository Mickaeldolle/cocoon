import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.commands import run_reminder_worker as worker
from app.modules.assistant.models import NotificationOutbox
from app.modules.auth.models import Device, User, WebPushSubscription
from app.modules.secret.models import SecretNotificationDebounce


def _account(client: TestClient, name: str) -> tuple[dict[str, str], str]:
    password = "une-phrase-de-passe-solide"
    response = client.post(
        "/api/auth/register",
        json={
            "email": f"{name}@example.com",
            "display_name": name,
            "password": password,
            "installation_id": f"secret-notification-{name}",
            "name": "Test device",
            "platform": "web",
        },
    )
    assert response.status_code == 201
    basic = {"Authorization": f"Bearer {response.json()['access_token']}"}
    unlocked = client.post("/api/secret/unlock", json={"password": password}, headers=basic)
    assert unlocked.status_code == 200
    return {
        **basic,
        "X-Cocoon-Secret-Access": unlocked.json()["secret_access_token"],
    }, client.get("/api/auth/me", headers=basic).json()["id"]


def test_secret_push_is_sent_immediately_and_is_idempotent(
    client: TestClient, monkeypatch
) -> None:
    sender, sender_id = _account(client, "sender")
    recipient, recipient_id = _account(client, "recipient")
    session_factory = client.app.state.test_session_factory
    with session_factory() as session:
        session.get(User, UUID(sender_id)).is_superadmin = True
        session.commit()
    created = client.post(
        "/api/secret/conversations",
        json={"invitee": "recipient@example.com"},
        headers=sender,
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]
    assert client.post(
        f"/api/secret/conversations/{conversation_id}/accept", headers=recipient
    ).status_code == 200
    messages_url = f"/api/secret/conversations/{conversation_id}/messages"
    assert client.put(
        "/api/auth/consents/notifications.push",
        json={"policy_version": 1, "source": "web"},
        headers=recipient,
    ).status_code == 200
    assert client.put(
        "/api/auth/web-push/subscription",
        json={
            "endpoint": "https://fcm.googleapis.com/fcm/send/secret-recipient",
            "p256dh": "A" * 80,
            "auth": "B" * 24,
        },
        headers=recipient,
    ).status_code == 204
    sent_payloads: list[dict] = []
    monkeypatch.setattr(worker, "SessionLocal", session_factory)
    monkeypatch.setattr(
        worker,
        "get_settings",
        lambda: SimpleNamespace(
            expo_push_endpoint="https://exp.host/--/api/v2/push/send",
            web_push_private_key="private",
            web_push_subject="mailto:admin@example.com",
        ),
    )
    monkeypatch.setattr(worker, "webpush", lambda **kwargs: sent_payloads.append(kwargs))

    message_id = str(uuid4())
    first = client.post(
        messages_url,
        json={"body": "Premier message", "client_message_id": message_id},
        headers=sender,
    )
    assert first.status_code == 201
    assert len(sent_payloads) == 1
    assert "Premier message" not in sent_payloads[0]["data"]
    assert str(conversation_id) not in sent_payloads[0]["data"]
    with session_factory() as session:
        alert = session.scalar(
            select(NotificationOutbox).where(NotificationOutbox.user_id == UUID(recipient_id))
        )
        assert alert is not None
        assert alert.body == "Votre assistant a du nouveau pour vous."
        assert alert.sent_at is not None
        assert str(conversation_id) not in str(alert.data)
        assert session.get(SecretNotificationDebounce, UUID(recipient_id)) is None

    retry = client.post(
        messages_url,
        json={"body": "Premier message", "client_message_id": message_id},
        headers=sender,
    )
    assert retry.status_code == 201
    assert len(sent_payloads) == 1

    # A normal page must not reveal that a hidden conversation generated the push.
    assert client.get("/api/assistant/notifications", headers=recipient).json() == []
    listed = client.get("/api/secret/conversations", headers=recipient)
    assert listed.status_code == 200
    assert listed.json()[0]["has_unread_messages"] is True
    with session_factory() as session:
        alert = session.scalar(
            select(NotificationOutbox).where(NotificationOutbox.user_id == UUID(recipient_id))
        )
        assert alert.cancelled_at is None

    assert client.get(messages_url, headers=recipient).status_code == 200
    listed = client.get("/api/secret/conversations", headers=recipient)
    assert listed.json()[0]["has_unread_messages"] is False

    second = client.post(messages_url, json={"body": "Deuxième message"}, headers=sender)
    assert second.status_code == 201
    assert len(sent_payloads) == 2

    def unavailable_push(**_kwargs) -> None:
        raise ValueError("provider unavailable")

    monkeypatch.setattr(worker, "webpush", unavailable_push)
    third = client.post(messages_url, json={"body": "Troisième message"}, headers=sender)
    assert third.status_code == 201
    with session_factory() as session:
        failed_attempt = session.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.user_id == UUID(recipient_id),
                NotificationOutbox.dedupe_key == (
                    f"secret-nudge:{third.json()['id']}:{recipient_id}"
                ),
            )
        )
        assert failed_attempt is not None
        assert failed_attempt.provider_status == "retrying"


def test_web_push_requires_consent_and_sends_only_generic_content(
    client: TestClient, monkeypatch
) -> None:
    headers, user_id = _account(client, "webrecipient")
    payload = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/test-subscription",
        "p256dh": "A" * 80,
        "auth": "B" * 24,
    }
    url = "/api/auth/web-push/subscription"
    assert client.put(url, json=payload, headers=headers).status_code == 403
    assert client.put(
        "/api/auth/consents/notifications.push",
        json={"policy_version": 1, "source": "web"},
        headers=headers,
    ).status_code == 200
    assert client.put(
        url,
        json={**payload, "endpoint": "https://example.org/private"},
        headers=headers,
    ).status_code == 422
    assert client.put(url, json=payload, headers=headers).status_code == 204

    session_factory = client.app.state.test_session_factory
    with session_factory() as session:
        session.add(
            NotificationOutbox(
                user_id=UUID(user_id),
                dedupe_key="secret-nudge:test",
                title="Cocoon",
                body="Votre assistant a du nouveau pour vous.",
                data={"kind": "assistant_update"},
            )
        )
        session.commit()
    sent_payloads: list[dict] = []
    monkeypatch.setattr(worker, "SessionLocal", session_factory)
    monkeypatch.setattr(
        worker,
        "get_settings",
        lambda: SimpleNamespace(
            expo_push_endpoint="https://exp.host/--/api/v2/push/send",
            web_push_private_key="test-private-key",
            web_push_subject="mailto:admin@example.com",
        ),
    )
    monkeypatch.setattr(worker, "webpush", lambda **kwargs: sent_payloads.append(kwargs))
    assert worker.send_pending_notifications(datetime.now(UTC)) == 1
    assert len(sent_payloads) == 1
    assert sent_payloads[0]["subscription_info"]["endpoint"] == payload["endpoint"]
    assert sent_payloads[0]["data"] == (
        '{"title": "Cocoon", "body": "Votre assistant a du nouveau pour vous.", '
        '"url": "/home"}'
    )

    revoked = client.delete("/api/auth/consents/notifications.push", headers=headers)
    assert revoked.status_code == 200
    with session_factory() as session:
        assert session.query(WebPushSubscription).count() == 0


def test_browser_sends_bounded_generic_test_push_immediately(
    client: TestClient, monkeypatch
) -> None:
    headers, user_id = _account(client, "testpush")
    monkeypatch.setattr(
        "app.modules.assistant.router.get_settings",
        lambda: SimpleNamespace(
            web_push_public_key="public",
            web_push_private_key="private",
            web_push_subject="mailto:admin@example.com",
        ),
    )
    test_url = "/api/assistant/notifications/test"
    assert client.post(test_url, headers=headers).status_code == 403
    assert client.put(
        "/api/auth/consents/notifications.push",
        json={"policy_version": 1, "source": "web"},
        headers=headers,
    ).status_code == 200
    assert client.post(test_url, headers=headers).status_code == 409
    assert client.put(
        "/api/auth/web-push/subscription",
        json={
            "endpoint": "https://fcm.googleapis.com/fcm/send/test-push",
            "p256dh": "A" * 80,
            "auth": "B" * 24,
        },
        headers=headers,
    ).status_code == 204
    sent_payloads: list[dict] = []
    monkeypatch.setattr(worker, "SessionLocal", client.app.state.test_session_factory)
    monkeypatch.setattr(
        worker,
        "get_settings",
        lambda: SimpleNamespace(
            expo_push_endpoint="https://exp.host/--/api/v2/push/send",
            web_push_private_key="private",
            web_push_subject="mailto:admin@example.com",
        ),
    )
    monkeypatch.setattr(worker, "webpush", lambda **kwargs: sent_payloads.append(kwargs))

    for _ in range(5):
        created = client.post(test_url, headers=headers)
        assert created.status_code == 201
        assert created.json()["body"] == "Ceci est une notification de test."
        assert created.json()["provider_status"] == "accepted"
    assert len(sent_payloads) == 5
    assert client.post(test_url, headers=headers).status_code == 429
    with client.app.state.test_session_factory() as session:
        items = list(
            session.scalars(
                select(NotificationOutbox).where(NotificationOutbox.user_id == UUID(user_id))
            )
        )
        assert len(items) == 5
        assert all(item.data["kind"] == "notification_test" for item in items)
        assert len({item.data["device_id"] for item in items}) == 1


def test_web_push_test_targets_only_its_browser(client: TestClient, monkeypatch) -> None:
    _headers, user_id = _account(client, "targetedtest")
    session_factory = client.app.state.test_session_factory
    with session_factory() as session:
        browser = session.scalar(select(Device).where(Device.user_id == UUID(user_id)))
        assert browser is not None
        other = Device(
            user_id=UUID(user_id),
            installation_id="other-test-device",
            name="Other device",
            platform="ios",
            push_token="ExponentPushToken[other]",
        )
        session.add(other)
        session.flush()
        session.add_all(
            [
                WebPushSubscription(
                    user_id=UUID(user_id),
                    device_id=browser.id,
                    endpoint="https://fcm.googleapis.com/fcm/send/current",
                    p256dh="A" * 80,
                    auth="B" * 24,
                ),
                WebPushSubscription(
                    user_id=UUID(user_id),
                    device_id=other.id,
                    endpoint="https://fcm.googleapis.com/fcm/send/other",
                    p256dh="A" * 80,
                    auth="B" * 24,
                ),
                NotificationOutbox(
                    user_id=UUID(user_id),
                    dedupe_key="web-push-test:targeted",
                    title="Cocoon",
                    body="Ceci est une notification de test.",
                    data={"kind": "notification_test", "device_id": str(browser.id)},
                ),
            ]
        )
        session.commit()
    sent: list[str] = []
    monkeypatch.setattr(worker, "SessionLocal", session_factory)
    monkeypatch.setattr(
        worker,
        "get_settings",
        lambda: SimpleNamespace(
            expo_push_endpoint="https://exp.host/--/api/v2/push/send",
            web_push_private_key="private",
            web_push_subject="mailto:admin@example.com",
        ),
    )
    monkeypatch.setattr(
        worker, "webpush", lambda **kwargs: sent.append(kwargs["subscription_info"]["endpoint"])
    )
    def fail_native(*_args, **_kwargs):
        raise AssertionError("The browser test must not send an Expo push")

    monkeypatch.setattr(worker, "urlopen", fail_native)
    assert worker.send_pending_notifications(datetime.now(UTC)) == 1
    assert sent == ["https://fcm.googleapis.com/fcm/send/current"]


def test_read_notification_is_hidden_on_next_list_load(client: TestClient) -> None:
    headers, user_id = _account(client, "readnotification")
    session_factory = client.app.state.test_session_factory
    with session_factory() as session:
        first = NotificationOutbox(
            user_id=UUID(user_id),
            dedupe_key="read-test:first",
            title="Cocoon",
            body="Premier rappel",
            data={"kind": "reminder"},
        )
        second = NotificationOutbox(
            user_id=UUID(user_id),
            dedupe_key="read-test:second",
            title="Cocoon",
            body="Deuxième rappel",
            data={"kind": "reminder"},
        )
        session.add_all([first, second])
        session.commit()
        first_id = first.id
        second_id = second.id

    list_url = "/api/assistant/notifications"
    assert {item["id"] for item in client.get(list_url, headers=headers).json()} == {
        str(first_id),
        str(second_id),
    }
    read = client.post(f"{list_url}/{first_id}/read", headers=headers)
    assert read.status_code == 200
    assert read.json()["read_at"] is not None
    assert [item["id"] for item in client.get(list_url, headers=headers).json()] == [
        str(second_id)
    ]
    with session_factory() as session:
        assert session.get(NotificationOutbox, first_id).read_at is not None


def test_android_can_send_immediate_test_push(client: TestClient, monkeypatch) -> None:
    registered = client.post(
        "/api/auth/register",
        json={
            "email": "androidtest@example.com",
            "display_name": "Android test",
            "password": "une-phrase-de-passe-solide",
            "installation_id": "android-notification-test-device",
            "name": "Android",
            "platform": "android",
        },
    )
    assert registered.status_code == 201
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    test_url = "/api/assistant/notifications/test"
    assert client.post(test_url, headers=headers).status_code == 403
    assert client.put(
        "/api/auth/consents/notifications.push",
        json={"policy_version": 1, "source": "mobile"},
        headers=headers,
    ).status_code == 200
    assert client.post(test_url, headers=headers).status_code == 409
    assert client.put(
        "/api/auth/push-token",
        json={"push_token": "ExpoPushToken[android-test]"},
        headers=headers,
    ).status_code == 204

    class PushResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self) -> bytes:
            return b'{"data":[{"status":"ok","id":"ticket-1"}]}'

    sent_payloads: list[dict] = []

    def fake_urlopen(request, *, timeout):
        assert timeout == 10
        sent_payloads.extend(json.loads(request.data))
        return PushResponse()

    monkeypatch.setattr(worker, "SessionLocal", client.app.state.test_session_factory)
    monkeypatch.setattr(worker, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        worker,
        "get_settings",
        lambda: SimpleNamespace(
            expo_push_endpoint="https://exp.host/--/api/v2/push/send",
            web_push_private_key=None,
            web_push_subject=None,
        ),
    )
    response = client.post(test_url, headers=headers)
    assert response.status_code == 201
    assert response.json()["provider_status"] == "accepted"
    assert len(sent_payloads) == 1
    assert sent_payloads[0]["to"] == "ExpoPushToken[android-test]"

    class RejectedResponse(PushResponse):
        def read(self) -> bytes:
            return b'{"data":[{"status":"error","details":{"error":"InvalidCredentials"}}]}'

    monkeypatch.setattr(worker, "urlopen", lambda *_args, **_kwargs: RejectedResponse())
    rejected = client.post(test_url, headers=headers)
    assert rejected.status_code == 201
    assert rejected.json()["provider_status"] == "retrying"
