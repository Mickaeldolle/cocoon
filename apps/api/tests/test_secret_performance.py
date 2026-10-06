from uuid import UUID

from fastapi import BackgroundTasks
from sqlalchemy import event

from app.modules.auth.models import User
from app.modules.conversations.models import Conversation, ConversationMember, Message


def test_secret_list_query_counts_do_not_grow_with_result_size(client):
    password = "une-phrase-de-passe-solide"
    tokens = client.post(
        "/api/auth/register",
        json={
            "email": "performance@example.com",
            "display_name": "Performance",
            "password": password,
            "installation_id": "performance-device",
            "name": "Test",
            "platform": "web",
        },
    ).json()
    basic = {"Authorization": f"Bearer {tokens['access_token']}"}
    # The startup response carries the same fresh, allowlisted profile as /me.
    assert tokens["user"] == client.get("/api/auth/me", headers=basic).json()
    refreshed = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    tokens = refreshed.json()
    basic = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert tokens["user"] == client.get("/api/auth/me", headers=basic).json()
    unlocked = client.post("/api/secret/unlock", json={"password": password}, headers=basic)
    assert unlocked.status_code == 200
    headers = {**basic, "X-Cocoon-Secret-Access": unlocked.json()["secret_access_token"]}
    owner_id = UUID(tokens["user"]["id"])
    factory = client.app.state.test_session_factory
    with factory() as session:
        conversation = Conversation(created_by=owner_id, name="Test")
        session.add(conversation)
        session.flush()
        conversation_id = conversation.id
        session.add(
            ConversationMember(
                conversation_id=conversation_id,
                user_id=owner_id,
                is_hidden=True,
            )
        )
        session.add(Message(conversation_id=conversation_id, sender_id=owner_id, body="First"))
        session.commit()

    engine = factory.kw["bind"]
    statements = []

    def capture(_connection, _cursor, statement, _params, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    def measure(url, expected_size):
        statements.clear()
        response = client.get(url, headers=headers)
        assert response.status_code == 200
        assert len(response.json()) == expected_size
        return len(statements)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        messages_url = f"/api/secret/conversations/{conversation_id}/messages"
        initial_messages = measure(messages_url, 1)
        initial_conversations = measure("/api/secret/conversations", 1)
        with factory() as session:
            for index in range(39):
                session.add(
                    Message(
                        conversation_id=conversation_id,
                        sender_id=owner_id,
                        body=f"Message {index}",
                    )
                )
                extra = Conversation(created_by=owner_id, name=f"Conversation {index}")
                session.add(extra)
                session.flush()
                session.add(
                    ConversationMember(
                        conversation_id=extra.id,
                        user_id=owner_id,
                        is_hidden=True,
                    )
                )
            session.commit()
        assert measure(messages_url, 40) == initial_messages
        assert measure("/api/secret/conversations", 40) == initial_conversations
    finally:
        event.remove(engine, "before_cursor_execute", capture)


def test_secret_dispatch_is_deferred_until_after_response(client, monkeypatch):
    # Check task execution separately: TestClient waits for background tasks too,
    # so request elapsed time there cannot prove response-before-push ordering.
    from types import SimpleNamespace

    from app.modules.conversations.schemas import MessageCreate
    from app.modules.secret import router as secret_router

    factory = client.app.state.test_session_factory
    with factory() as session:
        user = User(
            email="deferred@example.com",
            display_name="Deferred",
            password_hash="unused",
        )
        session.add(user)
        session.flush()
        conversation = Conversation(created_by=user.id)
        session.add(conversation)
        session.flush()
        session.add(
            ConversationMember(
                conversation_id=conversation.id,
                user_id=user.id,
                is_hidden=True,
            )
        )
        session.commit()
        called = []
        monkeypatch.setattr(secret_router, "dispatch_secret_notifications", called.append)
        tasks = BackgroundTasks()
        response = secret_router.send_secret_message(
            conversation.id,
            MessageCreate(body="Hello"),
            tasks,
            SimpleNamespace(authenticated=SimpleNamespace(user=user)),
            session,
        )
        assert response.body == "Hello"
        assert called == []
        assert len(tasks.tasks) == 1
        with factory() as verification:
            assert verification.get(Message, response.id) is not None
