from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.conversations.models import ConversationMember, ConversationMemberStatus


def visible_membership_or_not_found(
    session: Session, conversation_id: UUID, user_id: UUID
) -> ConversationMember:
    membership = session.scalar(
        select(ConversationMember).where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id == user_id,
            ConversationMember.is_hidden.is_(False),
            ConversationMember.status == ConversationMemberStatus.ACCEPTED,
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation introuvable."
        )
    return membership
