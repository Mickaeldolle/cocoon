from fastapi.testclient import TestClient


def registration(email: str, installation: str) -> dict[str, str]:
    return {
        "email": email,
        "password": "A-strong-password-123",
        "display_name": email.split("@")[0].title(),
        "installation_id": installation,
        "name": "Test device",
        "platform": "ios",
    }


def headers(client: TestClient, email: str, installation: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/register", json=registration(email, installation)
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_family_space_is_visible_only_to_members(client: TestClient) -> None:
    owner = headers(client, "owner-isolation@example.com", "owner-isolation-device")
    member = headers(client, "member-isolation@example.com", "member-isolation-device")
    outsider = headers(client, "outsider-isolation@example.com", "outsider-isolation-device")

    created = client.post(
        "/api/family-spaces",
        headers=owner,
        json={"name": "Famille isolation", "description": "test"},
    )
    assert created.status_code == 201
    space_id = created.json()["id"]

    added = client.post(
        f"/api/family-spaces/{space_id}/members",
        headers=owner,
        json={"email": "member-isolation@example.com", "role": "MEMBER"},
    )
    assert added.status_code == 204
    assert client.get(f"/api/family-spaces/{space_id}", headers=member).status_code == 200
    assert client.get(f"/api/family-spaces/{space_id}", headers=outsider).status_code == 404


def test_conversation_messages_require_membership(client: TestClient) -> None:
    sender = headers(client, "sender-isolation@example.com", "sender-isolation-device")
    recipient = headers(client, "recipient-isolation@example.com", "recipient-isolation-device")
    outsider = headers(client, "outsider-conversation@example.com", "outsider-conversation-device")

    created = client.post(
        "/api/conversations",
        headers=sender,
        json={"member_emails": ["recipient-isolation@example.com"], "name": "Privée"},
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    sent = client.post(
        f"/api/conversations/{conversation_id}/messages",
        headers=sender,
        json={"body": "Message de test"},
    )
    assert sent.status_code == 201
    pending = client.get("/api/conversations", headers=recipient)
    assert pending.status_code == 200
    assert pending.json()[0]["membership_status"] == "pending"
    accepted = client.post(f"/api/conversations/{conversation_id}/accept", headers=recipient)
    assert accepted.status_code == 200
    assert client.get(f"/api/conversations/{conversation_id}", headers=recipient).status_code == 200
    assert (
        client.get(f"/api/conversations/{conversation_id}/messages", headers=recipient).status_code
        == 200
    )
    assert client.get(f"/api/conversations/{conversation_id}", headers=outsider).status_code == 404
    assert (
        client.get(f"/api/conversations/{conversation_id}/messages", headers=outsider).status_code
        == 404
    )


def test_conversation_invitation_accepts_display_name_and_defaults_name(client: TestClient) -> None:
    sender = headers(client, "sender-name@example.com", "sender-name-device")
    recipient = headers(client, "recipient-name@example.com", "recipient-name-device")
    created = client.post(
        "/api/conversations",
        headers=sender,
        json={"invitee": "Recipient-Name"},
    )
    assert created.status_code == 201
    assert created.json()["name"] == "Recipient-Name"
    listed = client.get("/api/conversations", headers=recipient)
    assert listed.json()[0]["membership_status"] == "pending"
