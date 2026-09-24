from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_session
from app.core.security import create_refresh_token, hash_refresh_token, verify_password
from app.modules.auth.dependencies import (
    AuthenticatedSecretSession,
    AuthenticatedSession,
    get_authenticated_secret_session,
    get_authenticated_session,
)
from app.modules.auth.models import DevelopmentBiometricCredential, SecretAccessSession, User
from app.modules.auth.schemas import (
    DevelopmentBiometricCredentialRequest,
    SecretAccessResponse,
    SecretUnlockRequest,
)
from app.modules.conversations.models import (
    Conversation,
    ConversationMember,
    ConversationMemberStatus,
    ConversationRole,
    Message,
)
from app.modules.conversations.router import conversation_response, message_response
from app.modules.conversations.schemas import (
    ConversationCreate,
    ConversationResponse,
    MessageCreate,
    MessageResponse,
)

router = APIRouter(prefix="/api/secret", tags=["secret"])


def require_development_biometric_unlock() -> None:
    settings = get_settings()
    if settings.app_env != "development" or not settings.development_biometric_unlock_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fonctionnalité indisponible.",
        )


def mint_secret_access(
    authenticated: AuthenticatedSession, session: Session
) -> SecretAccessResponse:
    """Create a short-lived opaque secret token after an accepted step-up proof."""
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=get_settings().secret_access_minutes)
    session.execute(
        update(SecretAccessSession)
        .where(
            SecretAccessSession.user_session_id == authenticated.user_session.id,
            SecretAccessSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    token = create_refresh_token()
    session.add(
        SecretAccessSession(
            user_id=authenticated.user.id,
            user_session_id=authenticated.user_session.id,
            token_hash=hash_refresh_token(token),
            expires_at=expires_at,
        )
    )
    session.commit()
    return SecretAccessResponse(secret_access_token=token, expires_at=expires_at)


def secret_membership_or_not_found(
    session: Session, conversation_id: UUID, user_id: UUID
) -> ConversationMember:
    membership = session.scalar(
        select(ConversationMember).where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id == user_id,
            ConversationMember.is_hidden.is_(True),
            ConversationMember.status == ConversationMemberStatus.ACCEPTED,
        )
    )
    if membership is None:
        # Keep membership and hidden-state information indistinguishable to callers.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation introuvable."
        )
    return membership


@router.post("/unlock", response_model=SecretAccessResponse)
def unlock_secret_access(
    payload: SecretUnlockRequest,
    authenticated: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> SecretAccessResponse:
    """Step up with the account secret and mint one in-memory-only opaque token."""
    if not verify_password(payload.password, authenticated.user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Vérification impossible.",
        )

    return mint_secret_access(authenticated, session)


@router.post("/development-biometric/enroll", status_code=status.HTTP_204_NO_CONTENT)
def enroll_development_biometric(
    payload: DevelopmentBiometricCredentialRequest,
    authenticated: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> Response:
    """Register an Expo Go-only development credential for the signed-in device.

    A real passkey registration must verify a WebAuthn attestation. This local
    development adapter deliberately never exists outside ``development``.
    """
    require_development_biometric_unlock()
    credential = session.scalar(
        select(DevelopmentBiometricCredential).where(
            DevelopmentBiometricCredential.user_id == authenticated.user.id,
            DevelopmentBiometricCredential.device_id == authenticated.user_session.device_id,
        )
    )
    credential_hash = hash_refresh_token(payload.credential)
    if credential is None:
        session.add(
            DevelopmentBiometricCredential(
                user_id=authenticated.user.id,
                device_id=authenticated.user_session.device_id,
                credential_hash=credential_hash,
            )
        )
    else:
        credential.credential_hash = credential_hash
        credential.revoked_at = None
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/development-biometric/unlock", response_model=SecretAccessResponse)
def unlock_with_development_biometric(
    payload: DevelopmentBiometricCredentialRequest,
    authenticated: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> SecretAccessResponse:
    """Issue secret access only after proof possession released by native biometrics.

    This route exists solely for local Expo Go development. Production uses a
    signed WebAuthn assertion from a passkey instead.
    """
    require_development_biometric_unlock()
    credential = session.scalar(
        select(DevelopmentBiometricCredential).where(
            DevelopmentBiometricCredential.user_id == authenticated.user.id,
            DevelopmentBiometricCredential.device_id == authenticated.user_session.device_id,
            DevelopmentBiometricCredential.credential_hash
            == hash_refresh_token(payload.credential),
            DevelopmentBiometricCredential.revoked_at.is_(None),
        )
    )
    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Vérification impossible.",
        )
    return mint_secret_access(authenticated, session)


@router.post("/lock", status_code=status.HTTP_204_NO_CONTENT)
def lock_secret_access(
    authenticated: AuthenticatedSecretSession = Depends(get_authenticated_secret_session),
    session: Session = Depends(get_session),
) -> Response:
    authenticated.secret_session.revoked_at = datetime.now(UTC)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/conversations", response_model=list[ConversationResponse])
def list_secret_conversations(
    authenticated: AuthenticatedSecretSession = Depends(get_authenticated_secret_session),
    session: Session = Depends(get_session),
) -> list[ConversationResponse]:
    rows = session.execute(
        select(Conversation, ConversationMember)
        .join(ConversationMember)
        .where(
            ConversationMember.user_id == authenticated.authenticated.user.id,
            ConversationMember.is_hidden.is_(True),
            ConversationMember.status != ConversationMemberStatus.DECLINED,
        )
        .order_by(Conversation.updated_at.desc())
    ).all()
    return [conversation_response(conversation, membership) for conversation, membership in rows]


@router.post(
    "/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED
)
def create_secret_conversation(
    payload: ConversationCreate,
    authenticated: AuthenticatedSecretSession = Depends(get_authenticated_secret_session),
    session: Session = Depends(get_session),
) -> ConversationResponse:
    identifier = (payload.invitee or payload.member_emails[0]).strip()
    invited_user = session.scalar(
        select(User).where(
            (User.email == identifier.lower()) | (User.display_name.ilike(identifier))
        )
    )
    if invited_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable."
        )
    if invited_user.id == authenticated.authenticated.user.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Deux membres sont requis.",
        )
    conversation = Conversation(
        name=(
            payload.name.strip()
            if payload.name and payload.name.strip()
            else invited_user.display_name
        ),
        created_by=authenticated.authenticated.user.id,
    )
    session.add(conversation)
    session.flush()
    session.add_all([
        ConversationMember(
            conversation_id=conversation.id,
            user_id=authenticated.authenticated.user.id,
            role=ConversationRole.ADMIN,
            status=ConversationMemberStatus.ACCEPTED,
            is_hidden=True,
        ),
        ConversationMember(
            conversation_id=conversation.id,
            user_id=invited_user.id,
            role=ConversationRole.MEMBER,
            status=ConversationMemberStatus.PENDING,
            is_hidden=True,
        ),
    ])
    session.commit()
    session.refresh(conversation)
    membership = session.scalar(select(ConversationMember).where(
        ConversationMember.conversation_id == conversation.id,
        ConversationMember.user_id == authenticated.authenticated.user.id,
    ))
    return conversation_response(conversation, membership)


def update_secret_invitation(
    conversation_id: UUID,
    new_status: ConversationMemberStatus,
    authenticated: AuthenticatedSecretSession,
    session: Session,
) -> ConversationResponse:
    membership = session.scalar(select(ConversationMember).where(
        ConversationMember.conversation_id == conversation_id,
        ConversationMember.user_id == authenticated.authenticated.user.id,
        ConversationMember.status == ConversationMemberStatus.PENDING,
        ConversationMember.is_hidden.is_(True),
    ))
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation introuvable.")
    conversation = session.get(Conversation, conversation_id)
    membership.status = new_status
    if new_status == ConversationMemberStatus.DECLINED:
        membership.is_hidden = False
    session.commit()
    session.refresh(conversation)
    return conversation_response(conversation, membership)


@router.post("/conversations/{conversation_id}/accept", response_model=ConversationResponse)
def accept_secret_invitation(
    conversation_id: UUID,
    authenticated: AuthenticatedSecretSession = Depends(get_authenticated_secret_session),
    session: Session = Depends(get_session),
) -> ConversationResponse:
    return update_secret_invitation(
        conversation_id, ConversationMemberStatus.ACCEPTED, authenticated, session
    )


@router.post("/conversations/{conversation_id}/decline", response_model=ConversationResponse)
def decline_secret_invitation(
    conversation_id: UUID,
    authenticated: AuthenticatedSecretSession = Depends(get_authenticated_secret_session),
    session: Session = Depends(get_session),
) -> ConversationResponse:
    return update_secret_invitation(
        conversation_id, ConversationMemberStatus.DECLINED, authenticated, session
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
def get_secret_conversation(
    conversation_id: UUID,
    authenticated: AuthenticatedSecretSession = Depends(get_authenticated_secret_session),
    session: Session = Depends(get_session),
) -> Conversation:
    secret_membership_or_not_found(session, conversation_id, authenticated.authenticated.user.id)
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation introuvable."
        )
    return conversation


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
def list_secret_messages(
    conversation_id: UUID,
    authenticated: AuthenticatedSecretSession = Depends(get_authenticated_secret_session),
    session: Session = Depends(get_session),
) -> list[MessageResponse]:
    membership = secret_membership_or_not_found(
        session, conversation_id, authenticated.authenticated.user.id
    )
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
    # Do not expose other members' activity as a side channel from this access surface.
    return [message_response(message, [membership]) for message in messages]


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def send_secret_message(
    conversation_id: UUID,
    payload: MessageCreate,
    authenticated: AuthenticatedSecretSession = Depends(get_authenticated_secret_session),
    session: Session = Depends(get_session),
) -> MessageResponse:
    membership = secret_membership_or_not_found(
        session, conversation_id, authenticated.authenticated.user.id
    )
    message = Message(
        conversation_id=conversation_id,
        sender_id=authenticated.authenticated.user.id,
        body=payload.body.strip(),
    )
    session.add(message)
    session.commit()
    session.refresh(message)
    # Secret conversations intentionally have no realtime broadcast or notification in this phase.
    return message_response(message, [membership])
