from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_refresh_token,
    verify_password,
)
from app.modules.auth.models import Device, User, UserSession
from app.modules.auth.schemas import DeviceInput, TokenPair


def _upsert_device(session: Session, user: User, device_data: DeviceInput) -> Device:
    device = session.scalar(
        select(Device).where(
            Device.user_id == user.id, Device.installation_id == device_data.installation_id
        )
    )
    now = datetime.now(UTC)
    if device is None:
        device = Device(
            user_id=user.id,
            installation_id=device_data.installation_id,
            name=device_data.name.strip(),
            platform=device_data.platform.strip().lower(),
            last_seen_at=now,
        )
        session.add(device)
        session.flush()
    else:
        device.name = device_data.name.strip()
        device.platform = device_data.platform.strip().lower()
        device.last_seen_at = now
    return device


def _issue_for_device(session: Session, user: User, device: Device) -> TokenPair:
    settings = get_settings()
    refresh_token = create_refresh_token()
    user_session = UserSession(
        user_id=user.id,
        device_id=device.id,
        refresh_token_hash=hash_refresh_token(refresh_token),
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
    )
    session.add(user_session)
    session.flush()
    return TokenPair(
        access_token=create_access_token(user_id=user.id, session_id=user_session.id),
        refresh_token=refresh_token,
    )


def issue_session(session: Session, user: User, device_data: DeviceInput) -> TokenPair:
    return _issue_for_device(session, user, _upsert_device(session, user, device_data))


def authenticate(session: Session, email: str, password: str) -> User:
    user = session.scalar(select(User).where(User.email == email.lower()))
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect.",
        )
    return user


def rotate_session(session: Session, refresh_token: str) -> TokenPair:
    now = datetime.now(UTC)
    user_session = session.scalar(
        select(UserSession)
        .where(UserSession.refresh_token_hash == hash_refresh_token(refresh_token))
        .with_for_update()
    )
    expires_at = user_session.expires_at if user_session is not None else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if (
        user_session is None
        or user_session.revoked_at is not None
        or expires_at is None
        or expires_at <= now
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session invalide ou expirée."
        )

    user_session.revoked_at = now
    return _issue_for_device(session, user_session.user, user_session.device)
