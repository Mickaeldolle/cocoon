from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import decode_normal_access_token, hash_refresh_token
from app.modules.auth.models import SecretAccessSession, User, UserSession

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedSession:
    user: User
    user_session: UserSession


@dataclass(frozen=True)
class AuthenticatedSecretSession:
    authenticated: AuthenticatedSession
    secret_session: SecretAccessSession


def get_authenticated_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> AuthenticatedSession:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_normal_access_token(credentials.credentials)
    try:
        user_id = UUID(payload["sub"])
        session_id = UUID(payload["sid"])
    except (KeyError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session invalide."
        ) from error

    user_session = session.get(UserSession, session_id)
    user = session.get(User, user_id)
    if (
        user_session is None
        or user is None
        or user_session.user_id != user.id
        or user_session.revoked_at is not None
        or not user.is_active
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session invalide.")
    return AuthenticatedSession(user=user, user_session=user_session)


def get_current_user(
    authenticated: AuthenticatedSession = Depends(get_authenticated_session),
) -> User:
    return authenticated.user


def get_authenticated_secret_session(
    authenticated: AuthenticatedSession = Depends(get_authenticated_session),
    secret_access_token: str | None = Header(default=None, alias="X-Cocoon-Secret-Access"),
    session: Session = Depends(get_session),
) -> AuthenticatedSecretSession:
    """Require an opaque, short-lived secret token bound to the normal session."""
    if not secret_access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Accès renforcé requis."
        )

    secret_session = session.scalar(
        select(SecretAccessSession).where(
            SecretAccessSession.token_hash == hash_refresh_token(secret_access_token)
        )
    )
    expires_at = secret_session.expires_at if secret_session is not None else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if (
        secret_session is None
        or secret_session.user_id != authenticated.user.id
        or secret_session.user_session_id != authenticated.user_session.id
        or secret_session.revoked_at is not None
        or expires_at is None
        or expires_at <= datetime.now(UTC)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Accès renforcé expiré."
        )
    return AuthenticatedSecretSession(authenticated=authenticated, secret_session=secret_session)


def require_superadmin(current_user: User = Depends(get_current_user)) -> User:
    """Allow access only to explicitly privileged administrative endpoints."""
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Accès administrateur requis."
        )
    return current_user
