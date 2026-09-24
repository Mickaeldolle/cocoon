from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.family_spaces.models import FamilyRole, FamilySpaceMember


def membership_or_not_found(
    session: Session, family_space_id: UUID, user_id: UUID
) -> FamilySpaceMember:
    membership = session.scalar(
        select(FamilySpaceMember).where(
            FamilySpaceMember.family_space_id == family_space_id,
            FamilySpaceMember.user_id == user_id,
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Espace familial introuvable."
        )
    return membership


def require_manager(membership: FamilySpaceMember) -> None:
    if membership.role not in {FamilyRole.OWNER, FamilyRole.ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Droits insuffisants.")
