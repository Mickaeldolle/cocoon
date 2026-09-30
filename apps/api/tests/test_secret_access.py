from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.main import app
from app.modules.auth.models import User
from app.modules.conversations.models import ConversationMember, ConversationMemberStatus


def device(installation_id: str) -> dict[str, str]:
    return {"installation_id": installation_id, "name": "Téléphone de test", "platform": "ios"}


def register(
    client: TestClient, *, email: str, name: str, password: str, installation_id: str
) -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        json={
            **device(installation_id),
            "email": email,
            "display_name": name,
            "password": password,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_secret_access_requires_step_up_and_is_bound_to_its_normal_session(
    client: TestClient,
) -> None:
    password = "une-phrase-de-passe-solide"
    owner = register(
        client,
        email="proprietaire@example.com",
        name="Camille",
        password=password,
        installation_id="install-proprietaire-5ef93e63-60c2-48e2-b71a",
    )
    hidden_member = register(
        client,
        email="cache@example.com",
        name="Alex",
        password=password,
        installation_id="install-cache-5ef93e63-60c2-48e2-b71a-0fa7",
    )
    owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
    hidden_headers = {"Authorization": f"Bearer {hidden_member['access_token']}"}
    conversation = client.post(
        "/api/conversations",
        json={"member_emails": ["cache@example.com"]},
        headers=owner_headers,
    )
    assert conversation.status_code == 201
    conversation_id = conversation.json()["id"]
    hidden_user_id = client.get("/api/auth/me", headers=hidden_headers).json()["id"]
    with app.state.test_session_factory() as session:
        membership = session.scalar(
            select(ConversationMember).where(
                ConversationMember.conversation_id == UUID(conversation_id),
                ConversationMember.user_id == UUID(hidden_user_id),
            )
        )
        assert membership is not None
        membership.is_hidden = True
        membership.status = ConversationMemberStatus.ACCEPTED
        session.commit()

    assert client.get("/api/conversations", headers=hidden_headers).json() == []
    assert client.get("/api/secret/conversations", headers=hidden_headers).status_code == 401
    assert (
        client.post(
            "/api/secret/unlock", json={"password": "mauvais-mot-de-passe"}, headers=hidden_headers
        ).status_code
        == 401
    )

    unlocked = client.post(
        "/api/secret/unlock", json={"password": password}, headers=hidden_headers
    )
    assert unlocked.status_code == 200
    secret_token = unlocked.json()["secret_access_token"]
    assert secret_token
    secret_headers = {**hidden_headers, "X-Cocoon-Secret-Access": secret_token}
    listed = client.get("/api/secret/conversations", headers=secret_headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [conversation_id]
    assert client.get("/api/secret/conversations", headers=owner_headers).status_code == 401

    second_unlocked = client.post(
        "/api/secret/unlock", json={"password": password}, headers=hidden_headers
    )
    assert second_unlocked.status_code == 200
    second_secret_headers = {
        **hidden_headers,
        "X-Cocoon-Secret-Access": second_unlocked.json()["secret_access_token"],
    }
    assert client.get("/api/secret/conversations", headers=secret_headers).status_code == 401
    assert client.get("/api/secret/conversations", headers=second_secret_headers).status_code == 200
    secret_headers = second_secret_headers

    assert (
        client.get(
            f"/api/secret/conversations/{conversation_id}/messages", headers=secret_headers
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/secret/conversations/{conversation_id}/messages",
            json={"body": "Message privé"},
            headers=secret_headers,
        ).status_code
        == 201
    )
    assert (
        client.get(
            f"/api/conversations/{conversation_id}/messages", headers=hidden_headers
        ).status_code
        == 404
    )
    assert client.post("/api/secret/lock", headers=secret_headers).status_code == 204
    assert client.get("/api/secret/conversations", headers=secret_headers).status_code == 401


def test_secret_typing_and_message_retry_stay_inside_accepted_hidden_membership(
    client: TestClient,
) -> None:
    password = "une-phrase-de-passe-solide"
    owner = register(
        client,
        email="secret-typing-owner@example.com",
        name="Camille",
        password=password,
        installation_id="secret-typing-owner-install",
    )
    invitee = register(
        client,
        email="secret-typing-invitee@example.com",
        name="Alex",
        password=password,
        installation_id="secret-typing-invitee-install",
    )
    owner_basic = {"Authorization": f"Bearer {owner['access_token']}"}
    invitee_basic = {"Authorization": f"Bearer {invitee['access_token']}"}
    with app.state.test_session_factory() as session:
        creator = session.scalar(
            select(User).where(User.email == "secret-typing-owner@example.com")
        )
        assert creator is not None
        creator.is_superadmin = True
        session.commit()
    owner_unlock = client.post(
        "/api/secret/unlock", json={"password": password}, headers=owner_basic
    )
    invitee_unlock = client.post(
        "/api/secret/unlock", json={"password": password}, headers=invitee_basic
    )
    assert owner_unlock.status_code == invitee_unlock.status_code == 200
    owner_headers = {
        **owner_basic,
        "X-Cocoon-Secret-Access": owner_unlock.json()["secret_access_token"],
    }
    invitee_headers = {
        **invitee_basic,
        "X-Cocoon-Secret-Access": invitee_unlock.json()["secret_access_token"],
    }
    assert (
        client.post(
            "/api/secret/conversations",
            json={"invitee": "secret-typing-owner@example.com"},
            headers=invitee_headers,
        ).status_code
        == 403
    )
    created = client.post(
        "/api/secret/conversations",
        json={"invitee": "secret-typing-invitee@example.com"},
        headers=owner_headers,
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]
    typing_url = f"/api/secret/conversations/{conversation_id}/typing"
    messages_url = f"/api/secret/conversations/{conversation_id}/messages"

    assert client.get(typing_url, headers=owner_basic).status_code == 401
    assert client.get(typing_url, headers=invitee_headers).status_code == 404
    assert (
        client.post(typing_url, json={"is_typing": True}, headers=invitee_headers).status_code
        == 404
    )
    assert (
        client.post(typing_url, json={"is_typing": True}, headers=owner_headers).status_code == 204
    )
    assert client.get(typing_url, headers=owner_headers).json() == {"is_typing": False}

    accepted = client.post(
        f"/api/secret/conversations/{conversation_id}/accept", headers=invitee_headers
    )
    assert accepted.status_code == 200
    assert client.get(typing_url, headers=invitee_headers).json() == {"is_typing": True}
    assert (
        client.get(f"/api/secret/conversations/{conversation_id}", headers=owner_headers).json()[
            "recipient_name"
        ]
        == "Alex"
    )
    assert (
        client.get(f"/api/secret/conversations/{conversation_id}", headers=invitee_headers).json()[
            "recipient_name"
        ]
        == "Camille"
    )

    message_id = str(uuid4())
    payload = {"body": "Un message caché", "client_message_id": message_id}
    first = client.post(messages_url, json=payload, headers=owner_headers)
    repeated = client.post(messages_url, json=payload, headers=owner_headers)
    assert first.status_code == repeated.status_code == 201
    assert first.json()["id"] == repeated.json()["id"] == message_id
    owner_messages = client.get(messages_url, headers=owner_headers).json()
    assert [item["id"] for item in owner_messages] == [message_id]
    assert owner_messages[0]["read_by_count"] == 0
    assert client.get(messages_url, headers=invitee_headers).status_code == 200
    assert client.get(messages_url, headers=owner_headers).json()[0]["read_by_count"] == 1
    assert client.get(typing_url, headers=invitee_headers).json() == {"is_typing": False}
    assert (
        client.post(
            messages_url,
            json={"body": "Texte différent", "client_message_id": message_id},
            headers=owner_headers,
        ).status_code
        == 409
    )

    assert (
        client.post(typing_url, json={"is_typing": True}, headers=owner_headers).status_code == 204
    )
    assert client.get(typing_url, headers=invitee_headers).json() == {"is_typing": True}
    assert client.post("/api/secret/lock", headers=owner_headers).status_code == 204
    assert client.get(typing_url, headers=invitee_headers).json() == {"is_typing": False}
    assert client.get(typing_url, headers=owner_headers).status_code == 401


def test_secret_access_does_not_survive_a_new_application_session(client: TestClient) -> None:
    password = "une-phrase-de-passe-solide"
    account = register(
        client,
        email="redemarrage@example.com",
        name="Noa",
        password=password,
        installation_id="install-redemarrage-33ba7a99-fbb8-4bc1-9c2e",
    )
    headers = {"Authorization": f"Bearer {account['access_token']}"}
    unlocked = client.post("/api/secret/unlock", json={"password": password}, headers=headers)
    assert unlocked.status_code == 200

    restored = client.post("/api/auth/refresh", json={"refresh_token": account["refresh_token"]})
    assert restored.status_code == 200
    restarted_headers = {
        "Authorization": f"Bearer {restored.json()['access_token']}",
        "X-Cocoon-Secret-Access": unlocked.json()["secret_access_token"],
    }
    assert client.get("/api/secret/conversations", headers=restarted_headers).status_code == 401


def test_secret_biometric_requires_password_to_enroll_and_stays_on_its_device(
    client: TestClient,
) -> None:
    password = "une-phrase-de-passe-solide"
    account = register(
        client,
        email="biometrie-secrete@example.com",
        name="Noa",
        password=password,
        installation_id="biometrie-secrete-device-one",
    )
    headers = {"Authorization": f"Bearer {account['access_token']}"}
    credential = "local-device-proof-0123456789abcdef0123456789abcdef"
    endpoint = "/api/secret/biometric/enroll"
    assert (
        client.post(
            endpoint,
            json={"password": "wrong-password", "credential": credential},
            headers=headers,
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/secret/biometric/unlock", json={"credential": credential}, headers=headers
        ).status_code
        == 401
    )
    assert (
        client.post(
            endpoint, json={"password": password, "credential": credential}, headers=headers
        ).status_code
        == 204
    )
    unlocked = client.post(
        "/api/secret/biometric/unlock", json={"credential": credential}, headers=headers
    )
    assert unlocked.status_code == 200
    assert unlocked.json()["secret_access_token"]

    second_login = client.post(
        "/api/auth/login",
        json={
            **device("biometrie-secrete-device-two"),
            "email": "biometrie-secrete@example.com",
            "password": password,
        },
    )
    assert second_login.status_code == 200
    second_headers = {"Authorization": f"Bearer {second_login.json()['access_token']}"}
    assert (
        client.post(
            "/api/secret/biometric/unlock",
            json={"credential": credential},
            headers=second_headers,
        ).status_code
        == 401
    )
    replacement = "replacement-proof-0123456789abcdef0123456789abcdef"
    assert (
        client.post(
            endpoint, json={"password": password, "credential": replacement}, headers=headers
        ).status_code
        == 204
    )
    assert (
        client.post(
            "/api/secret/biometric/unlock", json={"credential": credential}, headers=headers
        ).status_code
        == 401
    )


def test_development_biometric_unlock_does_not_require_a_password_step_up(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setenv("DEVELOPMENT_BIOMETRIC_UNLOCK_ENABLED", "true")
    get_settings.cache_clear()
    password = "une-phrase-de-passe-solide"
    account = register(
        client,
        email="biometrie@example.com",
        name="Lina",
        password=password,
        installation_id="install-biometrie-47d6676d-0691-4c74-b067",
    )
    headers = {"Authorization": f"Bearer {account['access_token']}"}
    credential = "test-development-biometric-credential-0000000000000000"

    assert (
        client.post(
            "/api/secret/development-biometric/enroll",
            json={"credential": credential},
            headers=headers,
        ).status_code
        == 204
    )
    biometric_unlock = client.post(
        "/api/secret/development-biometric/unlock",
        json={"credential": credential},
        headers=headers,
    )
    assert biometric_unlock.status_code == 200
    assert (
        client.post(
            "/api/secret/biometric/unlock", json={"credential": credential}, headers=headers
        ).status_code
        == 401
    )
    get_settings.cache_clear()
