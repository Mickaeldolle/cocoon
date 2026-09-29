from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.modules.auth.models import User
from app.modules.realtime.router import typing_recipients


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
    response = client.post("/api/auth/register", json=registration(email, installation))
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
    assert (
        client.get(f"/api/conversations/{conversation_id}", headers=recipient).json()[
            "recipient_name"
        ]
        == "Sender-Isolation"
    )
    assert (
        client.get(f"/api/conversations/{conversation_id}", headers=sender).json()["recipient_name"]
        == "Recipient-Isolation"
    )
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


def test_message_retry_with_same_client_id_does_not_duplicate(client: TestClient) -> None:
    sender = headers(client, "retry-sender@example.com", "retry-sender-device")
    headers(client, "retry-recipient@example.com", "retry-recipient-device")
    conversation = client.post(
        "/api/conversations",
        headers=sender,
        json={"invitee": "retry-recipient@example.com"},
    ).json()
    path = f"/api/conversations/{conversation['id']}/messages"
    payload = {"body": "Message de test", "client_message_id": str(uuid4())}
    first = client.post(path, headers=sender, json=payload)
    retry = client.post(path, headers=sender, json=payload)
    assert first.status_code == retry.status_code == 201
    assert first.json()["id"] == retry.json()["id"]
    assert len(client.get(path, headers=sender).json()) == 1
    conflict = client.post(path, headers=sender, json={**payload, "body": "Autre texte"})
    assert conflict.status_code == 409


def test_pending_invitee_does_not_receive_message_event(client: TestClient) -> None:
    sender = headers(client, "pending-sender@example.com", "pending-sender-device")
    recipient = headers(client, "pending-recipient@example.com", "pending-recipient-device")
    conversation = client.post(
        "/api/conversations",
        headers=sender,
        json={"invitee": "pending-recipient@example.com"},
    ).json()
    ticket = client.post("/api/realtime/ticket", headers=recipient).json()["ticket"]
    with client.websocket_connect("/api/ws") as socket:
        socket.send_json({"type": "authenticate", "ticket": ticket})
        assert socket.receive_json() == {"type": "authenticated"}
        sent = client.post(
            f"/api/conversations/{conversation['id']}/messages",
            headers=sender,
            json={"body": "Visible après acceptation"},
        )
        assert sent.status_code == 201
        socket.send_json({"type": "ping"})
        assert socket.receive_json() == {"type": "pong"}


def test_typing_event_requires_accepted_visible_membership(client: TestClient) -> None:
    sender = headers(client, "typing-sender@example.com", "typing-sender-device")
    recipient = headers(client, "typing-recipient@example.com", "typing-recipient-device")
    headers(client, "typing-outsider@example.com", "typing-outsider-device")
    conversation = client.post(
        "/api/conversations",
        headers=sender,
        json={"invitee": "typing-recipient@example.com"},
    ).json()
    conversation_id = conversation["id"]
    with client.app.state.test_session_factory() as session:
        sender_id = session.scalar(select(User.id).where(User.email == "typing-sender@example.com"))
        recipient_id = session.scalar(
            select(User.id).where(User.email == "typing-recipient@example.com")
        )
        outsider_id = session.scalar(
            select(User.id).where(User.email == "typing-outsider@example.com")
        )
        assert typing_recipients(session, UUID(conversation_id), sender_id) == []
        assert typing_recipients(session, UUID(conversation_id), outsider_id) == []
    assert (
        client.post(f"/api/conversations/{conversation_id}/accept", headers=recipient).status_code
        == 200
    )
    with client.app.state.test_session_factory() as session:
        assert typing_recipients(session, UUID(conversation_id), sender_id) == [recipient_id]

    def ticket(auth_headers: dict[str, str]) -> str:
        response = client.post("/api/realtime/ticket", headers=auth_headers)
        assert response.status_code == 201
        return response.json()["ticket"]

    with (
        client.websocket_connect("/api/ws") as sender_socket,
        client.websocket_connect("/api/ws") as recipient_socket,
    ):
        for socket, auth_headers in (
            (sender_socket, sender),
            (recipient_socket, recipient),
        ):
            socket.send_json({"type": "authenticate", "ticket": ticket(auth_headers)})
            assert socket.receive_json() == {"type": "authenticated"}
        sender_socket.send_json(
            {"type": "conversation.typing", "conversation_id": conversation_id, "is_typing": True}
        )
        event = recipient_socket.receive_json()
        assert event["type"] == "conversation.typing"
        assert event["conversation_id"] == conversation_id
        assert event["is_typing"] is True
