from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.modules.auth.models import Device, User
from app.modules.conversations.models import ConversationMember


def valid_device() -> dict[str, str]:
    return {
        "installation_id": "install-5ef93e63-60c2-48e2-b71a-0fa720987251",
        "name": "Téléphone de test",
        "platform": "ios",
    }


def register_payload() -> dict[str, str]:
    return {
        **valid_device(),
        "email": "membre@example.com",
        "display_name": "Camille",
        "password": "une-phrase-de-passe-solide",
    }


def test_register_login_refresh_and_logout_revoke_access(client: TestClient) -> None:
    test_client = client
    registered = test_client.post("/api/auth/register", json=register_payload())
    assert registered.status_code == 201
    assert registered.headers["cache-control"] == "no-store"
    tokens = registered.json()
    assert tokens["token_type"] == "bearer"
    assert "refresh_token" in tokens

    me = test_client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == "membre@example.com"
    assert "password_hash" not in me.json()

    refreshed = test_client.post(
        "/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refreshed.status_code == 200
    refreshed_tokens = refreshed.json()
    assert refreshed_tokens["refresh_token"] != tokens["refresh_token"]

    reused_refresh = test_client.post(
        "/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert reused_refresh.status_code == 401

    logout = test_client.post(
        "/api/auth/logout", headers={"Authorization": f"Bearer {refreshed_tokens['access_token']}"}
    )
    assert logout.status_code == 204
    revoked_access = test_client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {refreshed_tokens['access_token']}"}
    )
    assert revoked_access.status_code == 401


def test_protected_endpoint_rejects_missing_access_token(client: TestClient) -> None:
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_logout_revokes_the_current_device_push_token(client: TestClient) -> None:
    tokens = client.post("/api/auth/register", json=register_payload()).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    consent = client.put(
        "/api/auth/consents/notifications.push",
        headers=headers,
        json={"policy_version": 1, "source": "mobile"},
    )
    assert consent.status_code == 200
    registered = client.put(
        "/api/auth/push-token",
        headers=headers,
        json={"push_token": "ExpoPushToken[logout-device-token]"},
    )
    assert registered.status_code == 204

    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    with client.app.state.test_session_factory() as session:
        device = session.scalar(
            select(Device).where(Device.installation_id == valid_device()["installation_id"])
        )
        assert device is not None
        assert device.push_token is None


def test_push_token_requires_an_expo_token_and_is_bound_to_the_current_device(
    client: TestClient,
) -> None:
    tokens = client.post("/api/auth/register", json=register_payload()).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    invalid = client.put(
        "/api/auth/push-token",
        headers=headers,
        json={"push_token": "arbitrary-credential-value"},
    )
    assert invalid.status_code == 422

    valid = client.put(
        "/api/auth/push-token",
        headers=headers,
        json={"push_token": "ExpoPushToken[test-device-token]"},
    )
    assert valid.status_code == 403

    consent = client.put(
        "/api/auth/consents/notifications.push",
        headers=headers,
        json={"policy_version": 1, "source": "mobile"},
    )
    assert consent.status_code == 200
    valid = client.put(
        "/api/auth/push-token",
        headers=headers,
        json={"push_token": "ExpoPushToken[test-device-token]"},
    )
    assert valid.status_code == 204

    revoked = client.delete("/api/auth/consents/notifications.push", headers=headers)
    assert revoked.status_code == 200
    with client.app.state.test_session_factory() as session:
        device = session.scalar(
            select(Device).where(Device.installation_id == valid_device()["installation_id"])
        )
        assert device is not None
        assert device.push_token is None

    blocked_after_revoke = client.put(
        "/api/auth/push-token",
        headers=headers,
        json={"push_token": "ExpoPushToken[test-device-token-2]"},
    )
    assert blocked_after_revoke.status_code == 403


def test_devices_are_account_scoped_and_revocation_invalidates_the_device_sessions(
    client: TestClient,
) -> None:
    first = client.post("/api/auth/register", json=register_payload()).json()
    first_headers = {"Authorization": f"Bearer {first['access_token']}"}
    second_device = {
        **valid_device(),
        "installation_id": "install-second-device-123456789",
        "name": "Ordinateur de test",
        "platform": "web",
    }
    second = client.post(
        "/api/auth/login",
        json={
            **second_device,
            "email": register_payload()["email"],
            "password": register_payload()["password"],
        },
    ).json()
    second_headers = {"Authorization": f"Bearer {second['access_token']}"}

    devices = client.get("/api/auth/devices", headers=first_headers)
    assert devices.status_code == 200
    assert {item["platform"] for item in devices.json()} == {"ios", "web"}
    current = next(item for item in devices.json() if item["current"])
    other = next(item for item in devices.json() if not item["current"])

    revoked = client.delete(f"/api/auth/devices/{other['id']}", headers=first_headers)
    assert revoked.status_code == 204
    assert client.get("/api/auth/me", headers=second_headers).status_code == 401
    assert (
        client.delete(f"/api/auth/devices/{other['id']}", headers=first_headers).status_code
        == 204
    )
    assert (
        client.delete(f"/api/auth/devices/{current['id']}", headers=first_headers).status_code
        == 204
    )
    assert client.get("/api/auth/me", headers=first_headers).status_code == 401


def test_consents_are_versioned_revocable_and_account_scoped(client: TestClient) -> None:
    first = client.post("/api/auth/register", json=register_payload()).json()
    second = client.post(
        "/api/auth/register",
        json={
            **register_payload(),
            "email": "consent-other@example.com",
            "installation_id": "install-consent-other-123456789",
        },
    ).json()
    first_headers = {"Authorization": f"Bearer {first['access_token']}"}
    second_headers = {"Authorization": f"Bearer {second['access_token']}"}

    granted = client.put(
        "/api/auth/consents/assistant.memory",
        headers=first_headers,
        json={"policy_version": 2, "source": "mobile"},
    )
    assert granted.status_code == 200
    assert granted.json()["active"] is True
    assert granted.json()["policy_version"] == 2
    assert client.get("/api/auth/consents", headers=second_headers).json() == []

    unknown = client.put(
        "/api/auth/consents/provider.unknown",
        headers=first_headers,
        json={"policy_version": 1, "source": "mobile"},
    )
    assert unknown.status_code == 422
    outdated = client.put(
        "/api/auth/consents/assistant.memory",
        headers=first_headers,
        json={"policy_version": 0, "source": "mobile"},
    )
    assert outdated.status_code == 422

    revoked = client.delete("/api/auth/consents/assistant.memory", headers=first_headers)
    assert revoked.status_code == 200
    assert revoked.json()["active"] is False
    assert client.get("/api/auth/consents", headers=first_headers).json()[0]["active"] is False
    assert client.delete("/api/auth/consents/invalid key", headers=first_headers).status_code == 404


def test_superadmin_access_is_explicit_and_protected(client: TestClient) -> None:
    tokens = client.post("/api/auth/register", json=register_payload()).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    assert client.get("/api/admin/status", headers=headers).status_code == 403

    with app.state.test_session_factory() as session:
        user = session.scalar(select(User).where(User.email == "membre@example.com"))
        assert user is not None
        user.is_superadmin = True
        session.commit()

    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["is_superadmin"] is True
    assert client.get("/api/admin/status", headers=headers).status_code == 200


def test_login_error_does_not_reveal_account_existence(client: TestClient) -> None:
    test_client = client
    unknown = test_client.post(
        "/api/auth/login",
        json={**valid_device(), "email": "absent@example.com", "password": "wrong-password"},
    )
    assert unknown.status_code == 401
    assert unknown.json()["detail"] == "Email ou mot de passe incorrect."


def test_family_space_is_invisible_until_membership_is_granted(client: TestClient) -> None:
    owner = client.post("/api/auth/register", json=register_payload()).json()
    second_user_payload = {
        **valid_device(),
        "installation_id": "install-f7ced2c9-57a0-4410-b6a0-5be1246a9b83",
        "email": "autre@example.com",
        "display_name": "Morgan",
        "password": "un-autre-mot-de-passe-solide",
    }
    second_user = client.post("/api/auth/register", json=second_user_payload).json()
    owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
    second_headers = {"Authorization": f"Bearer {second_user['access_token']}"}

    created = client.post(
        "/api/family-spaces", json={"name": "Famille proche"}, headers=owner_headers
    )
    assert created.status_code == 201
    space_id = created.json()["id"]
    assert created.json()["role"] == "OWNER"

    assert client.get("/api/family-spaces", headers=second_headers).json() == []
    assert client.get(f"/api/family-spaces/{space_id}", headers=second_headers).status_code == 404
    assert (
        client.post(
            f"/api/family-spaces/{space_id}/members",
            json={"email": "autre@example.com"},
            headers=second_headers,
        ).status_code
        == 404
    )

    added = client.post(
        f"/api/family-spaces/{space_id}/members",
        json={"email": "autre@example.com", "role": "MEMBER"},
        headers=owner_headers,
    )
    assert added.status_code == 204
    spaces = client.get("/api/family-spaces", headers=second_headers)
    assert spaces.status_code == 200
    assert spaces.json()[0]["id"] == space_id
    assert spaces.json()[0]["role"] == "MEMBER"


def test_standard_conversation_api_never_returns_a_hidden_membership(client: TestClient) -> None:
    owner = client.post("/api/auth/register", json=register_payload()).json()
    other = client.post(
        "/api/auth/register",
        json={
            **valid_device(),
            "installation_id": "install-32a9f040-3c04-4c1f-a04b-cbde5b4816f1",
            "email": "message@example.com",
            "display_name": "Alex",
            "password": "un-mot-de-passe-tres-solide",
        },
    ).json()
    owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}
    created = client.post(
        "/api/conversations",
        json={"member_emails": ["message@example.com"]},
        headers=owner_headers,
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]
    assert (
        client.post(
            f"/api/conversations/{conversation_id}/messages",
            json={"body": "Bonjour"},
            headers=owner_headers,
        ).status_code
        == 201
    )
    other_user_id = client.get("/api/auth/me", headers=other_headers).json()["id"]
    with app.state.test_session_factory() as session:
        membership = session.scalar(
            select(ConversationMember).where(
                ConversationMember.conversation_id == UUID(conversation_id),
                ConversationMember.user_id == UUID(other_user_id),
            )
        )
        assert membership is not None
        membership.is_hidden = True
        session.commit()
    assert client.get("/api/conversations", headers=other_headers).json() == []
    assert (
        client.get(
            f"/api/conversations/{conversation_id}/messages", headers=other_headers
        ).status_code
        == 404
    )


def test_realtime_ticket_authenticates_before_message_delivery(client: TestClient) -> None:
    owner = client.post("/api/auth/register", json=register_payload()).json()
    recipient = client.post(
        "/api/auth/register",
        json={
            **valid_device(),
            "installation_id": "install-cc7d8101-0262-4b9a-9cf9-70f5221c6ce0",
            "email": "realtime@example.com",
            "display_name": "Robin",
            "password": "un-mot-de-passe-tres-solide",
        },
    ).json()
    owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
    recipient_headers = {"Authorization": f"Bearer {recipient['access_token']}"}
    conversation = client.post(
        "/api/conversations",
        json={"member_emails": ["realtime@example.com"]},
        headers=owner_headers,
    ).json()
    ticket = client.post("/api/realtime/ticket", headers=recipient_headers).json()["ticket"]

    with client.websocket_connect("/api/ws") as socket:
        socket.send_json({"type": "authenticate", "ticket": ticket})
        assert socket.receive_json() == {"type": "authenticated"}
        response = client.post(
            f"/api/conversations/{conversation['id']}/messages",
            json={"body": "En direct"},
            headers=owner_headers,
        )
        assert response.status_code == 201
        event = socket.receive_json()
        assert event["type"] == "message.created"
        assert event["message"]["body"] == "En direct"
