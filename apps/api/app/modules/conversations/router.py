from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.conversations.models import (
    Conversation,
    ConversationMember,
    ConversationMemberStatus,
    ConversationRole,
    Message,
)
from app.modules.conversations.schemas import (
    ConversationCreate,
    ConversationResponse,
    MessageCreate,
    MessageResponse,
)
from app.modules.conversations.service import visible_membership_or_not_found
from app.modules.realtime.service import connections

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def conversation_response(
    conversation: Conversation, membership: ConversationMember
) -> ConversationResponse:
    return ConversationResponse(
        id=conversation.id,
        name=conversation.name,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        membership_status=membership.status.value,
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
            and member.last_read_at >= message.created_at
            for member in memberships
        ),
    )


@router.get("", response_model=list[ConversationResponse])
def list_conversations(
    current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> list[ConversationResponse]:
    rows = session.execute(
        select(Conversation, ConversationMember)
        .join(ConversationMember)
        .where(
            ConversationMember.user_id == current_user.id,
            ConversationMember.is_hidden.is_(False),
            ConversationMember.status != ConversationMemberStatus.DECLINED,
        )
        .order_by(Conversation.updated_at.desc())
    ).all()
    return [conversation_response(conversation, membership) for conversation, membership in rows]


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Conversation:
    identifier = (payload.invitee or payload.member_emails[0]).strip()
    users = list(
        session.scalars(
            select(User).where(
                or_(User.email == identifier.lower(), User.display_name.ilike(identifier))
            )
        )
    )
    if len(users) != 1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable."
        )
    invited_user = users[0]

    participant_ids = {current_user.id, invited_user.id}
    if len(participant_ids) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Deux membres sont requis."
        )

    conversation = Conversation(
        name=(
            payload.name.strip()
            if payload.name and payload.name.strip()
            else invited_user.display_name
        ),
        created_by=current_user.id,
    )
    session.add(conversation)
    session.flush()
    session.add(ConversationMember(
        conversation_id=conversation.id,
        user_id=current_user.id,
        role=ConversationRole.ADMIN,
        status=ConversationMemberStatus.ACCEPTED,
    ))
    session.add(ConversationMember(
        conversation_id=conversation.id,
        user_id=invited_user.id,
        role=ConversationRole.MEMBER,
        status=ConversationMemberStatus.PENDING,
    ))
    session.commit()
    session.refresh(conversation)
    membership = session.scalar(select(ConversationMember).where(
        ConversationMember.conversation_id == conversation.id,
        ConversationMember.user_id == current_user.id,
    ))
    return conversation_response(conversation, membership)


@router.get("/{conversation_id}", response_model=ConversationResponse)
def get_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ConversationResponse:
    membership = visible_membership_or_not_found(session, conversation_id, current_user.id)
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation introuvable."
        )
    return conversation_response(conversation, membership)


def update_invitation(
    conversation_id: UUID,
    new_status: ConversationMemberStatus,
    current_user: User,
    session: Session,
) -> ConversationResponse:
    membership = session.scalar(select(ConversationMember).where(
        ConversationMember.conversation_id == conversation_id,
        ConversationMember.user_id == current_user.id,
        ConversationMember.status == ConversationMemberStatus.PENDING,
        ConversationMember.is_hidden.is_(False),
    ))
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation introuvable.")
    conversation = session.get(Conversation, conversation_id)
    membership.status = new_status
    if new_status == ConversationMemberStatus.DECLINED:
        membership.is_hidden = True
    session.commit()
    session.refresh(conversation)
    return conversation_response(conversation, membership)


@router.post("/{conversation_id}/accept", response_model=ConversationResponse)
def accept_invitation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ConversationResponse:
    return update_invitation(
        conversation_id, ConversationMemberStatus.ACCEPTED, current_user, session
    )


@router.post("/{conversation_id}/decline", response_model=ConversationResponse)
def decline_invitation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ConversationResponse:
    return update_invitation(
        conversation_id, ConversationMemberStatus.DECLINED, current_user, session
    )


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
def list_messages(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[MessageResponse]:
    membership = visible_membership_or_not_found(session, conversation_id, current_user.id)
    messages = list(
        session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .limit(100)
        )
    )
    membership.last_read_at = datetime.now(UTC)
    session.commit()
    memberships = list(
        session.scalars(
            select(ConversationMember).where(
                ConversationMember.conversation_id == conversation_id,
                ConversationMember.is_hidden.is_(False),
            )
        )
    )
    return [message_response(message, memberships) for message in messages]


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def send_message(
    conversation_id: UUID,
    payload: MessageCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MessageResponse:
    membership = visible_membership_or_not_found(session, conversation_id, current_user.id)
    message = Message(
        conversation_id=conversation_id, sender_id=current_user.id, body=payload.body.strip()
    )
    session.add(message)
    session.commit()
    session.refresh(message)
    recipients = list(
        session.scalars(
            select(ConversationMember.user_id).where(
                ConversationMember.conversation_id == conversation_id,
                ConversationMember.is_hidden.is_(False),
            )
        )
    )
    background_tasks.add_task(
        connections.broadcast,
        recipients,
        {
            "type": "message.created",
            "conversation_id": str(conversation_id),
            "message": message_response(message, [membership]).model_dump(mode="json"),
        },
    )
    return message_response(message, [membership])
