"""Versioned consent policies understood by the MVP."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models import UserConsent

# The registry is deliberately small and explicit. Unknown policy names must
# not become an accidental permission surface just because a client invented a key.
CONSENT_POLICY_VERSIONS: dict[str, int] = {
    "assistant.memory": 1,
    "assistant.projects": 1,
    "assistant.voice": 1,
    "notifications.push": 1,
}


def minimum_policy_version(policy_key: str) -> int:
    try:
        return CONSENT_POLICY_VERSIONS[policy_key]
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cette politique de consentement n’est pas reconnue.",
        ) from error


def require_active_consent(
    session: Session, user_id: UUID, policy_key: str, *, version: int | None = None
) -> UserConsent:
    required_version = version or minimum_policy_version(policy_key)
    consent = session.scalar(
        select(UserConsent).where(
            UserConsent.user_id == user_id,
            UserConsent.policy_key == policy_key,
            UserConsent.policy_version >= required_version,
            UserConsent.revoked_at.is_(None),
        )
    )
    if consent is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Le consentement requis est absent ou révoqué.",
        )
    return consent
