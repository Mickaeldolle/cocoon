import re
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import hash_password
from app.modules.auth.consents import minimum_policy_version, require_active_consent
from app.modules.auth.dependencies import (
    AuthenticatedSession,
    get_authenticated_session,
    get_current_user,
)
from app.modules.auth.models import Device, User, UserConsent, UserSession
from app.modules.auth.schemas import (
    ConsentResponse,
    ConsentUpdate,
    DeviceResponse,
    LoginRequest,
    PushTokenRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserResponse,
)
from app.modules.auth.service import authenticate, issue_session, rotate_session

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


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, session: Session = Depends(get_session)) -> TokenPair:
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
    return tokens


@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, session: Session = Depends(get_session)) -> TokenPair:
    user = authenticate(session, payload.email, payload.password)
    tokens = issue_session(session, user, payload)
    session.commit()
    return tokens


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, session: Session = Depends(get_session)) -> TokenPair:
    tokens = rotate_session(session, payload.refresh_token)
    session.commit()
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
    return consent_response(consent)


@router.delete("/consents/{policy_key}", response_model=ConsentResponse)
def revoke_consent(
    policy_key: str,
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
    consent.revoked_at = datetime.now(UTC)
    if policy_key == "notifications.push":
        session.query(Device).filter(Device.user_id == current_user.id).update(
            {Device.push_token: None}, synchronize_session=False
        )
    session.commit()
    session.refresh(consent)
    return consent_response(consent)
