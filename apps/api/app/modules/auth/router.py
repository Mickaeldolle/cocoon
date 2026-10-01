import json
import re
from datetime import UTC, datetime, timedelta
from secrets import token_bytes
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    verify_authentication_response,
)
from webauthn.helpers import options_to_json
from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement

from app.core.database import get_session
from app.core.security import decode_normal_access_token, hash_password
from app.modules.audit.service import (
    attempted_identity_reference,
    normalized_platform,
    note_request_details,
    note_response_details,
)
from app.modules.auth.consents import minimum_policy_version, require_active_consent
from app.modules.auth.dependencies import (
    AuthenticatedSession,
    get_authenticated_session,
    get_current_user,
)
from app.modules.auth.models import (
    Device,
    PasskeyLoginChallenge,
    SecretPasskey,
    User,
    UserConsent,
    UserSession,
)
from app.modules.auth.schemas import (
    ConsentResponse,
    ConsentUpdate,
    DeviceResponse,
    LoginRequest,
    PasskeyLoginOptionsRequest,
    PasskeyLoginVerifyRequest,
    PushTokenRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserResponse,
)
from app.modules.auth.service import authenticate, issue_session, rotate_session
from app.modules.auth.webauthn_config import checked_credential, require_webauthn_relying_party

router = APIRouter(prefix="/api/auth", tags=["auth"])
_POLICY_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def consent_response(consent: UserConsent) -> ConsentResponse:
    return ConsentResponse(
        id=consent.id,
        policy_key=consent.policy_key,
        policy_version=consent.policy_version,
        source=consent.source,
        granted_at=consent.granted_at,
        revoked_at=consent.revoked_at,
        active=consent.revoked_at is None,
    )


def mark_audit_login(request: Request, tokens: TokenPair, session: Session) -> None:
    claims = decode_normal_access_token(tokens.access_token)
    request.state.audit_user_id = UUID(claims["sub"])
    request.state.audit_session_id = UUID(claims["sid"])
    user_session = session.get(UserSession, request.state.audit_session_id)
    if user_session is not None:
        request.state.audit_device_id = user_session.device_id
        request.state.audit_platform = normalized_platform(user_session.device.platform)
    note_response_details(request, token_issued=True)


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest, request: Request, session: Session = Depends(get_session)
) -> TokenPair:
    note_request_details(request, platform=payload.platform.strip().lower())
    user = User(
        email=payload.email.lower(),
        display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password),
    )
    session.add(user)
    try:
        session.flush()
        tokens = issue_session(session, user, payload)
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Un compte existe déjà avec cet email."
        ) from error
    mark_audit_login(request, tokens, session)
    return tokens


@router.post("/login", response_model=TokenPair)
def login(
    payload: LoginRequest, request: Request, session: Session = Depends(get_session)
) -> TokenPair:
    request.state.audit_attempted_identity_ref = attempted_identity_reference(payload.email)
    note_request_details(request, platform=payload.platform.strip().lower())
    user = authenticate(session, payload.email, payload.password)
    tokens = issue_session(session, user, payload)
    session.commit()
    mark_audit_login(request, tokens, session)
    return tokens


@router.post("/passkeys/login/options")
def passkey_login_options(
    payload: PasskeyLoginOptionsRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    request.state.audit_attempted_identity_ref = attempted_identity_reference(payload.email)
    origin, rp_id = require_webauthn_relying_party()
    user = session.scalar(select(User).where(User.email == payload.email.lower(), User.is_active))
    credentials = (
        session.scalars(
            select(SecretPasskey).where(
                SecretPasskey.user_id == user.id, SecretPasskey.rp_id == rp_id
            )
        ).all()
        if user is not None
        else []
    )
    # A dummy descriptor keeps an unknown account and an account without a passkey
    # on the same browser path. Neither can complete verification.
    descriptors = [
        PublicKeyCredentialDescriptor(id=item.credential_id) for item in credentials
    ] or [PublicKeyCredentialDescriptor(id=token_bytes(32))]
    options = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=descriptors,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    now = datetime.now(UTC)
    session.execute(delete(PasskeyLoginChallenge).where(PasskeyLoginChallenge.expires_at <= now))
    pending = PasskeyLoginChallenge(
        user_id=user.id if credentials and user is not None else None,
        challenge=options.challenge,
        origin=origin,
        rp_id=rp_id,
        expires_at=now + timedelta(minutes=5),
    )
    session.add(pending)
    session.commit()
    return {"challenge_id": str(pending.id), "options": json.loads(options_to_json(options))}


@router.post("/passkeys/login/verify", response_model=TokenPair)
def passkey_login_verify(
    payload: PasskeyLoginVerifyRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> TokenPair:
    note_request_details(request, platform=payload.platform.strip().lower())
    origin, rp_id = require_webauthn_relying_party()
    if payload.platform != "web":
        raise HTTPException(status_code=400, detail="Connexion passkey réservée au navigateur.")
    consumed = session.execute(
        delete(PasskeyLoginChallenge)
        .where(
            PasskeyLoginChallenge.id == payload.challenge_id,
            PasskeyLoginChallenge.origin == origin,
            PasskeyLoginChallenge.rp_id == rp_id,
            PasskeyLoginChallenge.expires_at > datetime.now(UTC),
        )
        .returning(PasskeyLoginChallenge.user_id, PasskeyLoginChallenge.challenge)
    ).first()
    session.commit()
    if consumed is None or consumed.user_id is None:
        raise HTTPException(status_code=401, detail="Passkey non validée.")
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
            SecretPasskey.user_id == consumed.user_id,
            SecretPasskey.rp_id == rp_id,
            SecretPasskey.credential_id == credential_id,
        )
        .with_for_update()
    )
    user = session.get(User, consumed.user_id)
    if stored is None or user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Passkey non validée.")
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=consumed.challenge,
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
    tokens = issue_session(session, user, payload)
    session.commit()
    mark_audit_login(request, tokens, session)
    return tokens


@router.post("/refresh", response_model=TokenPair)
def refresh(
    payload: RefreshRequest, request: Request, session: Session = Depends(get_session)
) -> TokenPair:
    tokens = rotate_session(session, payload.refresh_token)
    session.commit()
    mark_audit_login(request, tokens, session)
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    authenticated: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> Response:
    authenticated.user_session.revoked_at = datetime.now(UTC)
    # A device token must not continue receiving the previous account's reminders
    # after logout or before another account explicitly re-registers it.
    authenticated.user_session.device.push_token = None
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.put("/push-token", status_code=status.HTTP_204_NO_CONTENT)
def register_push_token(
    payload: PushTokenRequest,
    authenticated: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> Response:
    """Associate one Expo push token with the authenticated device session only."""
    require_active_consent(session, authenticated.user.id, "notifications.push")
    authenticated.user_session.device.push_token = payload.push_token
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/devices", response_model=list[DeviceResponse])
def list_devices(
    authenticated: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> list[DeviceResponse]:
    devices = session.scalars(
        select(Device)
        .where(Device.user_id == authenticated.user.id)
        .order_by(Device.last_seen_at.desc(), Device.created_at.desc())
    )
    return [
        DeviceResponse(
            id=device.id,
            name=device.name,
            platform=device.platform,
            created_at=device.created_at,
            last_seen_at=device.last_seen_at,
            current=device.id == authenticated.user_session.device_id,
        )
        for device in devices
    ]


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_device(
    device_id: str,
    authenticated: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> Response:
    try:
        device_uuid = UUID(device_id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Appareil introuvable."
        ) from error

    device = session.scalar(
        select(Device)
        .where(Device.id == device_uuid, Device.user_id == authenticated.user.id)
        .with_for_update()
    )
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appareil introuvable.")

    now = datetime.now(UTC)
    session.query(UserSession).filter(
        UserSession.device_id == device.id,
        UserSession.user_id == authenticated.user.id,
        UserSession.revoked_at.is_(None),
    ).update({UserSession.revoked_at: now}, synchronize_session=False)
    device.push_token = None
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/consents", response_model=list[ConsentResponse])
def list_consents(
    current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> list[ConsentResponse]:
    consents = session.scalars(
        select(UserConsent)
        .where(UserConsent.user_id == current_user.id)
        .order_by(UserConsent.policy_key.asc())
    )
    return [consent_response(consent) for consent in consents]


@router.put("/consents/{policy_key}", response_model=ConsentResponse)
def grant_consent(
    policy_key: str,
    payload: ConsentUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ConsentResponse:
    if not _POLICY_KEY.fullmatch(policy_key):
        raise HTTPException(status_code=422, detail="La clé de consentement est invalide.")
    required_version = minimum_policy_version(policy_key)
    if payload.policy_version < required_version:
        raise HTTPException(
            status_code=422,
            detail="La version de consentement est obsolète.",
        )
    note_request_details(request, policy_key=policy_key, policy_version=payload.policy_version)
    consent = session.scalar(
        select(UserConsent).where(
            UserConsent.user_id == current_user.id,
            UserConsent.policy_key == policy_key,
        )
    )
    if consent is None:
        consent = UserConsent(user_id=current_user.id, policy_key=policy_key)
    consent.policy_version = payload.policy_version
    consent.source = payload.source
    consent.revoked_at = None
    session.add(consent)
    session.commit()
    session.refresh(consent)
    note_response_details(request, active=True, policy_version=consent.policy_version)
    return consent_response(consent)


@router.delete("/consents/{policy_key}", response_model=ConsentResponse)
def revoke_consent(
    policy_key: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ConsentResponse:
    consent = session.scalar(
        select(UserConsent).where(
            UserConsent.user_id == current_user.id,
            UserConsent.policy_key == policy_key,
        )
    )
    if consent is None:
        raise HTTPException(status_code=404, detail="Consentement introuvable.")
    note_request_details(request, policy_key=policy_key)
    consent.revoked_at = datetime.now(UTC)
    if policy_key == "notifications.push":
        session.query(Device).filter(Device.user_id == current_user.id).update(
            {Device.push_token: None}, synchronize_session=False
        )
    session.commit()
    session.refresh(consent)
    note_response_details(request, active=False)
    return consent_response(consent)
