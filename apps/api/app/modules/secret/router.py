import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import options_to_json
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.core.config import get_settings
from app.core.database import get_session
from app.core.security import create_refresh_token, hash_refresh_token, verify_password
from app.modules.auth.dependencies import (
    AuthenticatedSecretSession,
    AuthenticatedSession,
    get_authenticated_secret_session,
    get_authenticated_session,
)
from app.modules.auth.models import (
    DevelopmentBiometricCredential,
    SecretAccessSession,
    SecretPasskey,
    SecretPasskeyChallenge,
    User,
)
from app.modules.auth.schemas import (
    DevelopmentBiometricCredentialRequest,
    SecretAccessResponse,
    SecretPasskeyCredentialRequest,
    SecretPasskeyRegistrationRequest,
    SecretPasskeyStatus,
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


def webauthn_relying_party() -> tuple[str, str] | None:
    """Use one explicitly configured web origin as the trust boundary."""
    configured = get_settings().webauthn_origin
    if not configured:
        return None
    try:
        parsed = urlsplit(configured)
    except ValueError:
        return None
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or parsed.scheme not in ("http", "https")
        or (
            parsed.scheme == "http"
            and not (get_settings().app_env == "development" and parsed.hostname == "localhost")
        )
    ):
        return None
    try:
        if parsed.port == 0:
            return None
    except ValueError:
        return None
    return f"{parsed.scheme}://{parsed.netloc.lower()}", parsed.hostname.lower()


def require_webauthn_relying_party() -> tuple[str, str]:
    relying_party = webauthn_relying_party()
    if relying_party is None:
        raise HTTPException(status_code=503, detail="Les passkeys ne sont pas configurées.")
    return relying_party


def save_passkey_challenge(
    *,
    session: Session,
    authenticated: AuthenticatedSession,
    purpose: str,
    challenge: bytes,
    origin: str,
    rp_id: str,
) -> SecretPasskeyChallenge:
    now = datetime.now(UTC)
    session.execute(
        delete(SecretPasskeyChallenge).where(
            (SecretPasskeyChallenge.expires_at <= now)
            | (
                (SecretPasskeyChallenge.user_session_id == authenticated.user_session.id)
                & (SecretPasskeyChallenge.purpose == purpose)
            )
        )
    )
    pending = SecretPasskeyChallenge(
        user_id=authenticated.user.id,
        user_session_id=authenticated.user_session.id,
        purpose=purpose,
        challenge=challenge,
        origin=origin,
        rp_id=rp_id,
        expires_at=now + timedelta(minutes=5),
    )
    session.add(pending)
    session.commit()
    return pending


def consume_passkey_challenge(
    *,
    session: Session,
    authenticated: AuthenticatedSession,
    purpose: str,
    challenge_id: UUID,
    origin: str,
    rp_id: str,
) -> bytes:
    # A committed DELETE makes even a failed ceremony one-use across API instances.
    challenge = session.execute(
        delete(SecretPasskeyChallenge)
        .where(
            SecretPasskeyChallenge.id == challenge_id,
            SecretPasskeyChallenge.user_id == authenticated.user.id,
            SecretPasskeyChallenge.user_session_id == authenticated.user_session.id,
            SecretPasskeyChallenge.purpose == purpose,
            SecretPasskeyChallenge.origin == origin,
            SecretPasskeyChallenge.rp_id == rp_id,
            SecretPasskeyChallenge.expires_at > datetime.now(UTC),
        )
        .returning(SecretPasskeyChallenge.challenge)
    ).scalar_one_or_none()
    session.commit()
    if challenge is None:
        raise HTTPException(status_code=401, detail="Vérification expirée. Réessayez.")
    return challenge


def checked_credential(credential: dict[str, Any]) -> dict[str, Any]:
    if len(json.dumps(credential)) > 32_768:
        raise HTTPException(status_code=413, detail="Réponse passkey trop volumineuse.")
    return credential


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


@router.get("/passkeys/status", response_model=SecretPasskeyStatus)
def secret_passkey_status(
    authenticated: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> SecretPasskeyStatus:
    relying_party = webauthn_relying_party()
    has_passkeys = (
        relying_party is not None
        and session.scalar(
            select(SecretPasskey.id)
            .where(
                SecretPasskey.user_id == authenticated.user.id,
                SecretPasskey.rp_id == relying_party[1],
            )
            .limit(1)
        )
        is not None
    )
    return SecretPasskeyStatus(
        available=relying_party is not None,
        has_passkeys=has_passkeys,
    )


@router.post("/passkeys/register/options")
def secret_passkey_registration_options(
    payload: SecretPasskeyRegistrationRequest,
    authenticated: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    origin, rp_id = require_webauthn_relying_party()
    if not verify_password(payload.password, authenticated.user.password_hash):
        raise HTTPException(status_code=401, detail="Vérification impossible.")
    existing = session.scalars(
        select(SecretPasskey).where(
            SecretPasskey.user_id == authenticated.user.id,
            SecretPasskey.rp_id == rp_id,
        )
    ).all()
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name="Cocoon",
        user_id=authenticated.user.id.bytes,
        user_name=authenticated.user.email,
        user_display_name=authenticated.user.display_name,
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=item.credential_id) for item in existing
        ],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    pending = save_passkey_challenge(
        session=session,
        authenticated=authenticated,
        purpose="register",
        challenge=options.challenge,
        origin=origin,
        rp_id=rp_id,
    )
    return {"challenge_id": str(pending.id), "options": json.loads(options_to_json(options))}


@router.post("/passkeys/register/verify", response_model=SecretAccessResponse)
def secret_passkey_registration_verify(
    payload: SecretPasskeyCredentialRequest,
    authenticated: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> SecretAccessResponse:
    origin, rp_id = require_webauthn_relying_party()
    challenge = consume_passkey_challenge(
        session=session,
        authenticated=authenticated,
        purpose="register",
        challenge_id=payload.challenge_id,
        origin=origin,
        rp_id=rp_id,
    )
    credential = checked_credential(payload.credential)
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            require_user_verification=True,
        )
    except Exception as error:
        raise HTTPException(status_code=401, detail="Passkey non validée.") from error
    session.add(
        SecretPasskey(
            user_id=authenticated.user.id,
            rp_id=rp_id,
            credential_id=verified.credential_id,
            public_key=verified.credential_public_key,
            sign_count=verified.sign_count,
        )
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Cette passkey est déjà enregistrée."
        ) from error
    return mint_secret_access(authenticated, session)


@router.post("/passkeys/unlock/options")
def secret_passkey_unlock_options(
    authenticated: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    origin, rp_id = require_webauthn_relying_party()
    existing = session.scalars(
        select(SecretPasskey).where(
            SecretPasskey.user_id == authenticated.user.id,
            SecretPasskey.rp_id == rp_id,
        )
    ).all()
    if not existing:
        raise HTTPException(status_code=404, detail="Aucune passkey enregistrée.")
    options = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=item.credential_id) for item in existing
        ],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    pending = save_passkey_challenge(
        session=session,
        authenticated=authenticated,
        purpose="unlock",
        challenge=options.challenge,
        origin=origin,
        rp_id=rp_id,
    )
    return {"challenge_id": str(pending.id), "options": json.loads(options_to_json(options))}


@router.post("/passkeys/unlock/verify", response_model=SecretAccessResponse)
def secret_passkey_unlock_verify(
    payload: SecretPasskeyCredentialRequest,
    authenticated: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> SecretAccessResponse:
    origin, rp_id = require_webauthn_relying_party()
    challenge = consume_passkey_challenge(
        session=session,
        authenticated=authenticated,
        purpose="unlock",
        challenge_id=payload.challenge_id,
        origin=origin,
        rp_id=rp_id,
    )
    credential = checked_credential(payload.credential)
    encoded_id = credential.get("id")
    if not isinstance(encoded_id, str) or len(encoded_id) > 2048:
        raise HTTPException(status_code=401, detail="Passkey non validée.")
    try:
        credential_id = base64url_to_bytes(encoded_id)
    except Exception as error:
        raise HTTPException(status_code=401, detail="Passkey non validée.") from error
    stored = session.scalar(
        select(SecretPasskey)
        .where(
            SecretPasskey.user_id == authenticated.user.id,
            SecretPasskey.rp_id == rp_id,
            SecretPasskey.credential_id == credential_id,
        )
        .with_for_update()
    )
    if stored is None:
        raise HTTPException(status_code=401, detail="Passkey non validée.")
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=stored.public_key,
            credential_current_sign_count=stored.sign_count,
            require_user_verification=True,
        )
    except Exception as error:
        raise HTTPException(status_code=401, detail="Passkey non validée.") from error
    if verified.credential_id != stored.credential_id:
        raise HTTPException(status_code=401, detail="Passkey non validée.")
    stored.sign_count = verified.new_sign_count
    stored.last_used_at = datetime.now(UTC)
    session.commit()
    return mint_secret_access(authenticated, session)


@router.delete("/passkeys", status_code=status.HTTP_204_NO_CONTENT)
def revoke_secret_passkeys(
    payload: SecretPasskeyRegistrationRequest,
    authenticated: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> Response:
    if not verify_password(payload.password, authenticated.user.password_hash):
        raise HTTPException(status_code=401, detail="Vérification impossible.")
    session.execute(
        delete(SecretPasskeyChallenge).where(
            SecretPasskeyChallenge.user_id == authenticated.user.id
        )
    )
    session.execute(delete(SecretPasskey).where(SecretPasskey.user_id == authenticated.user.id))
    session.execute(
        update(SecretAccessSession)
        .where(
            SecretAccessSession.user_id == authenticated.user.id,
            SecretAccessSession.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    session.add_all(
        [
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
        ]
    )
    session.commit()
    session.refresh(conversation)
    membership = session.scalar(
        select(ConversationMember).where(
            ConversationMember.conversation_id == conversation.id,
            ConversationMember.user_id == authenticated.authenticated.user.id,
        )
    )
    return conversation_response(conversation, membership)


def update_secret_invitation(
    conversation_id: UUID,
    new_status: ConversationMemberStatus,
    authenticated: AuthenticatedSecretSession,
    session: Session,
) -> ConversationResponse:
    membership = session.scalar(
        select(ConversationMember).where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id == authenticated.authenticated.user.id,
            ConversationMember.status == ConversationMemberStatus.PENDING,
            ConversationMember.is_hidden.is_(True),
        )
    )
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
