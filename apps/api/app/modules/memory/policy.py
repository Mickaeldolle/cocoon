"""Read access is consent-gated; managing/forgetting stored memories stays possible."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.consents import minimum_policy_version
from app.modules.auth.models import User, UserConsent


def memory_allowed(session: Session, user_id: UUID) -> bool:
    return bool(
        session.scalar(
            select(UserConsent.id)
            .join(User, User.id == UserConsent.user_id)
            .where(
                User.id == user_id,
                User.is_active.is_(True),
                User.enable_assistant.is_(True),
                UserConsent.policy_key == "assistant.memory",
                UserConsent.policy_version >= minimum_policy_version("assistant.memory"),
                UserConsent.revoked_at.is_(None),
            )
            .limit(1)
        )
    )
