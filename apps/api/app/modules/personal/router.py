from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.personal.models import (
    GroceryItem,
    GroceryList,
    PersonalProject,
    PersonalTask,
    TrainingSession,
    UserProfile,
    WeightCheckIn,
)
from app.modules.personal.schemas import (
    GroceryCreate,
    GroceryListCreate,
    GroceryListResponse,
    GroceryListUpdate,
    GroceryResponse,
    GroceryUpdate,
    ProfileResponse,
    ProfileUpdate,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
    TrainingCreate,
    TrainingResponse,
    TrainingUpdate,
    WeightCheckInCreate,
    WeightCheckInResponse,
)

router = APIRouter(prefix="/api/personal", tags=["personal"])


def owned_or_not_found(session: Session, model: type[Any], item_id: UUID, user_id: UUID):
    """Resolve a personal resource with ownership in the initial SQL predicate."""
    item = session.scalar(select(model).where(model.id == item_id, model.user_id == user_id))
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Élément introuvable.")
    return item


@router.get("/profile", response_model=ProfileResponse)
def get_profile(
    current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    profile = session.get(UserProfile, current_user.id)
    return ProfileResponse(
        display_name=current_user.display_name,
        email=current_user.email,
        birth_date=profile.birth_date if profile else None,
        height_cm=profile.height_cm if profile else None,
        weight_kg=float(profile.weight_kg) if profile and profile.weight_kg is not None else None,
        target_weight_kg=(
            float(profile.target_weight_kg)
            if profile and profile.target_weight_kg is not None
            else None
        ),
        weekly_training_target=profile.weekly_training_target if profile else 3,
    )


@router.put("/profile", response_model=ProfileResponse)
def update_profile(
    payload: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    profile = session.get(UserProfile, current_user.id) or UserProfile(user_id=current_user.id)
    current_user.display_name = payload.display_name
    profile.birth_date = payload.birth_date
    profile.height_cm = payload.height_cm
    profile.weight_kg = payload.weight_kg
    profile.target_weight_kg = payload.target_weight_kg
    profile.weekly_training_target = payload.weekly_training_target
    session.add(profile)
    session.commit()
    return get_profile(current_user, session)


@router.get("/tasks", response_model=list[TaskResponse])
def list_tasks(
    current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    return list(
        session.scalars(
            select(PersonalTask)
            .where(PersonalTask.user_id == current_user.id)
            .order_by(
                PersonalTask.completed.asc(),
                PersonalTask.due_date.asc(),
                PersonalTask.created_at.desc(),
            )
        )
    )


@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    item = PersonalTask(
        user_id=current_user.id,
        title=payload.title.strip(),
        detail=payload.detail,
        due_date=payload.due_date,
        due_at=payload.due_at,
        reminder_at=payload.reminder_at,
        priority=payload.priority,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.patch("/tasks/{item_id}", response_model=TaskResponse)
def update_task(
    item_id: UUID,
    payload: TaskUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    item = owned_or_not_found(session, PersonalTask, item_id, current_user.id)
    if payload.completed is not None:
        item.completed = payload.completed
    if "due_at" in payload.model_fields_set:
        item.due_at = payload.due_at
    if "reminder_at" in payload.model_fields_set:
        item.reminder_at = payload.reminder_at
    if payload.priority is not None:
        item.priority = payload.priority
    session.commit()
    session.refresh(item)
    return item


@router.get("/projects", response_model=list[ProjectResponse])
def list_projects(
    current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    return list(
        session.scalars(
            select(PersonalProject)
            .where(PersonalProject.user_id == current_user.id)
            .order_by(PersonalProject.status.asc(), PersonalProject.updated_at.desc())
        )
    )


@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    item = PersonalProject(
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        status=payload.status,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.patch("/projects/{item_id}", response_model=ProjectResponse)
def update_project(
    item_id: UUID,
    payload: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    item = owned_or_not_found(session, PersonalProject, item_id, current_user.id)
    if payload.name is not None:
        item.name = payload.name
    if "description" in payload.model_fields_set:
        item.description = payload.description
    if payload.status is not None:
        item.status = payload.status
    session.commit()
    session.refresh(item)
    return item


@router.get("/groceries", response_model=list[GroceryResponse])
def list_groceries(
    current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    return list(
        session.scalars(
            select(GroceryItem)
            .where(GroceryItem.user_id == current_user.id)
            .order_by(GroceryItem.checked.asc(), GroceryItem.created_at.asc())
        )
    )


@router.post("/groceries", response_model=GroceryResponse, status_code=status.HTTP_201_CREATED)
def create_grocery(
    payload: GroceryCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if payload.list_id is not None:
        owned_or_not_found(session, GroceryList, payload.list_id, current_user.id)
    item = GroceryItem(user_id=current_user.id, label=payload.label, list_id=payload.list_id)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.get("/grocery-lists", response_model=list[GroceryListResponse])
def list_grocery_lists(
    current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    return list(
        session.scalars(
            select(GroceryList)
            .where(GroceryList.user_id == current_user.id)
            .order_by(GroceryList.archived.asc(), GroceryList.created_at.desc())
        )
    )


@router.post(
    "/grocery-lists", response_model=GroceryListResponse, status_code=status.HTTP_201_CREATED
)
def create_grocery_list(
    payload: GroceryListCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    item = GroceryList(user_id=current_user.id, name=payload.name)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.patch("/grocery-lists/{item_id}", response_model=GroceryListResponse)
def update_grocery_list(
    item_id: UUID,
    payload: GroceryListUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    item = owned_or_not_found(session, GroceryList, item_id, current_user.id)
    item.archived = payload.archived
    session.commit()
    session.refresh(item)
    return item


@router.patch("/groceries/{item_id}", response_model=GroceryResponse)
def update_grocery(
    item_id: UUID,
    payload: GroceryUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    item = owned_or_not_found(session, GroceryItem, item_id, current_user.id)
    item.checked = payload.checked
    session.commit()
    session.refresh(item)
    return item


@router.get("/trainings", response_model=list[TrainingResponse])
def list_trainings(
    current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    return list(
        session.scalars(
            select(TrainingSession)
            .where(TrainingSession.user_id == current_user.id)
            .order_by(TrainingSession.completed.asc(), TrainingSession.created_at.desc())
        )
    )


@router.post("/trainings", response_model=TrainingResponse, status_code=status.HTTP_201_CREATED)
def create_training(
    payload: TrainingCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    item = TrainingSession(
        user_id=current_user.id,
        label=payload.label.strip(),
        training_type=payload.training_type,
        timing=payload.timing.strip(),
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.patch("/trainings/{item_id}", response_model=TrainingResponse)
def update_training(
    item_id: UUID,
    payload: TrainingUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    item = owned_or_not_found(session, TrainingSession, item_id, current_user.id)
    item.completed = payload.completed
    session.commit()
    session.refresh(item)
    return item


@router.get("/weight-check-ins", response_model=list[WeightCheckInResponse])
def list_weight_check_ins(
    current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    return list(
        session.scalars(
            select(WeightCheckIn)
            .where(WeightCheckIn.user_id == current_user.id)
            .order_by(WeightCheckIn.recorded_on.desc(), WeightCheckIn.created_at.desc())
        )
    )


@router.post(
    "/weight-check-ins", response_model=WeightCheckInResponse, status_code=status.HTTP_201_CREATED
)
def create_weight_check_in(
    payload: WeightCheckInCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    item = WeightCheckIn(
        user_id=current_user.id,
        weight_kg=payload.weight_kg,
        recorded_on=payload.recorded_on or date.today(),
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item
