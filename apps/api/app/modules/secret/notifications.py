from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.modules.assistant.models import NotificationOutbox
from app.modules.conversations.models import ConversationMember, ConversationMemberStatus
from app.modules.secret.models import SecretNotificationDebounce

OUTBOX_PREFIX = "secret-nudge:"


def queue_secret_nudges(
    session: Session, conversation_id: UUID, sender_id: UUID, message_id: UUID
) -> list[UUID]:
    """Persist generic alerts in the message transaction and return their IDs for direct send."""
    recipient_ids = session.scalars(
        select(ConversationMember.user_id).where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id != sender_id,
            ConversationMember.is_hidden.is_(True),
            ConversationMember.status == ConversationMemberStatus.ACCEPTED,
        )
    ).all()
    alert_ids: list[UUID] = []
    for recipient_id in recipient_ids:
        # Old deferred alerts must not arrive again after the new immediate one.
        session.execute(
            delete(SecretNotificationDebounce).where(
                SecretNotificationDebounce.user_id == recipient_id
            )
        )
        alert = NotificationOutbox(
            id=uuid4(),
            user_id=recipient_id,
            dedupe_key=f"{OUTBOX_PREFIX}{message_id}:{recipient_id}",
            title="Cocoon",
            body="Votre assistant a du nouveau pour vous.",
            data={"kind": "assistant_update"},
        )
        session.add(alert)
        alert_ids.append(alert.id)
    return alert_ids


def clear_secret_nudge(session: Session, user_id: UUID) -> None:
    session.execute(
        delete(SecretNotificationDebounce).where(SecretNotificationDebounce.user_id == user_id)
    )
    session.execute(
        update(NotificationOutbox)
        .where(
            NotificationOutbox.user_id == user_id,
            NotificationOutbox.dedupe_key.like(f"{OUTBOX_PREFIX}%"),
            NotificationOutbox.sent_at.is_(None),
            NotificationOutbox.cancelled_at.is_(None),
        )
        .values(cancelled_at=datetime.now(UTC))
    )
