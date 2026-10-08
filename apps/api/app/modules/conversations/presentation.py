"""Shared conversation response mapping without route-module dependencies."""

from datetime import UTC
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.conversations.models import (
    Conversation,
    ConversationMember,
    ConversationMemberStatus,
    Message,
)
from app.modules.conversations.schemas import ConversationResponse, MessageResponse


def conversation_response(
    conversation: Conversation, membership: ConversationMember, recipient_name: str | None = None
) -> ConversationResponse:
    return ConversationResponse(
        id=conversation.id,
        name=conversation.name,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        membership_status=membership.status.value,
        recipient_name=recipient_name,
    )


def conversation_recipient_name(
    session: Session, conversation_id: UUID, user_id: UUID, *, hidden: bool
) -> str | None:
    return session.scalar(
        select(User.display_name)
        .join(ConversationMember, ConversationMember.user_id == User.id)
        .where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id != user_id,
            ConversationMember.is_hidden.is_(hidden),
            ConversationMember.status == ConversationMemberStatus.ACCEPTED,
        )
        .limit(1)
    )


def message_response(message: Message, memberships: list[ConversationMember]) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        sender_id=message.sender_id,
        body=message.body,
        created_at=message.created_at,
        read_by_count=sum(
            member.user_id != message.sender_id
            and member.last_read_at is not None
            # SQLite returns naive timestamps; PostgreSQL retains UTC offsets.
            and member.last_read_at.replace(tzinfo=member.last_read_at.tzinfo or UTC)
            >= message.created_at.replace(tzinfo=message.created_at.tzinfo or UTC)
            for member in memberships
        ),
    )


def same_client_message(
    message: Message | None, conversation_id: UUID, sender_id: UUID, body: str
) -> bool:
    return (
        message is not None
        and message.conversation_id == conversation_id
        and message.sender_id == sender_id
        and message.body == body
    )
