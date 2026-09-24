from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.main import app
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
    get_settings.cache_clear()
