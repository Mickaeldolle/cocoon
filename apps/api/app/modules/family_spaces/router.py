from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.family_spaces.models import FamilyRole, FamilySpace, FamilySpaceMember
from app.modules.family_spaces.schemas import (
    AddMemberRequest,
    FamilySpaceCreate,
    FamilySpaceResponse,
)
from app.modules.family_spaces.service import membership_or_not_found, require_manager

router = APIRouter(prefix="/api/family-spaces", tags=["family spaces"])


def as_response(space: FamilySpace, membership: FamilySpaceMember) -> FamilySpaceResponse:
    return FamilySpaceResponse(
        id=space.id,
        name=space.name,
        description=space.description,
        avatar_key=space.avatar_key,
        created_at=space.created_at,
        updated_at=space.updated_at,
        role=membership.role,
    )


@router.get("", response_model=list[FamilySpaceResponse])
def list_spaces(
    current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> list[FamilySpaceResponse]:
    rows = session.execute(
        select(FamilySpace, FamilySpaceMember)
        .join(FamilySpaceMember, FamilySpaceMember.family_space_id == FamilySpace.id)
        .where(FamilySpaceMember.user_id == current_user.id)
        .order_by(FamilySpace.created_at.desc())
    ).all()
    return [as_response(space, membership) for space, membership in rows]


@router.post("", response_model=FamilySpaceResponse, status_code=status.HTTP_201_CREATED)
def create_space(
    payload: FamilySpaceCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> FamilySpaceResponse:
    space = FamilySpace(
        name=payload.name.strip(), description=payload.description, created_by=current_user.id
    )
    session.add(space)
    session.flush()
    membership = FamilySpaceMember(
        family_space_id=space.id, user_id=current_user.id, role=FamilyRole.OWNER
    )
    session.add(membership)
    session.commit()
    session.refresh(space)
    return as_response(space, membership)


@router.get("/{family_space_id}", response_model=FamilySpaceResponse)
def get_space(
    family_space_id: UUID,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> FamilySpaceResponse:
    membership = membership_or_not_found(session, family_space_id, current_user.id)
    space = session.get(FamilySpace, family_space_id)
    if space is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Espace familial introuvable."
        )
    return as_response(space, membership)


@router.post("/{family_space_id}/members", status_code=status.HTTP_204_NO_CONTENT)
def add_member(
    family_space_id: UUID,
    payload: AddMemberRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    require_manager(membership_or_not_found(session, family_space_id, current_user.id))
    invited_user = session.scalar(select(User).where(User.email == payload.email.lower()))
    if invited_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable."
        )
    session.add(
        FamilySpaceMember(
            family_space_id=family_space_id, user_id=invited_user.id, role=payload.role
        )
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Ce membre appartient déjà à cet espace."
        ) from error
