from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.modules.assistant.models import NotificationOutbox
from app.modules.auth.models import User
from app.modules.conversations.models import ConversationMember, ConversationMemberStatus
from app.modules.secret.models import SecretNotificationDebounce

DEBOUNCE_MINUTES = 10
OUTBOX_PREFIX = "secret-nudge:"


def schedule_secret_nudges(session: Session, conversation_id: UUID, sender_id: UUID) -> None:
    now = datetime.now(UTC)
    recipient_ids = session.scalars(
        select(ConversationMember.user_id).where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id != sender_id,
            ConversationMember.is_hidden.is_(True),
            ConversationMember.status == ConversationMemberStatus.ACCEPTED,
        )
    ).all()
    for recipient_id in recipient_ids:
        # Serializes the first insert and subsequent resets for this recipient on PostgreSQL.
        session.scalar(select(User.id).where(User.id == recipient_id).with_for_update())
        pending = session.get(SecretNotificationDebounce, recipient_id)
        if pending is None:
            session.add(
                SecretNotificationDebounce(
                    user_id=recipient_id,
                    due_at=now + timedelta(minutes=DEBOUNCE_MINUTES),
                    updated_at=now,
                )
            )
        else:
            pending.due_at = now + timedelta(minutes=DEBOUNCE_MINUTES)
            pending.updated_at = now
        session.execute(
            update(NotificationOutbox)
            .where(
                NotificationOutbox.user_id == recipient_id,
                NotificationOutbox.dedupe_key.like(f"{OUTBOX_PREFIX}%"),
                NotificationOutbox.sent_at.is_(None),
                NotificationOutbox.cancelled_at.is_(None),
            )
            .values(cancelled_at=now)
        )


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
