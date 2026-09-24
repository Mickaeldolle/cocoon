from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProfileResponse(BaseModel):
    display_name: str
    email: str
    birth_date: date | None
    height_cm: int | None
    weight_kg: float | None
    target_weight_kg: float | None
    weekly_training_target: int


class ProfileUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    birth_date: date | None = None
    height_cm: int | None = Field(default=None, ge=80, le=250)
    weight_kg: float | None = Field(default=None, ge=20, le=400)
    target_weight_kg: float | None = Field(default=None, ge=20, le=400)
    weekly_training_target: int = Field(default=3, ge=1, le=14)

    @field_validator("display_name")
    @classmethod
    def display_name_cannot_be_blank(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Le nom ne peut pas être vide.")
        return normalized


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    detail: str | None = Field(default=None, max_length=2000)
    due_date: date | None = None
    due_at: datetime | None = None
    reminder_at: datetime | None = None
    priority: str = Field(default="normal", pattern="^(low|normal|high)$")


class TaskUpdate(BaseModel):
    completed: bool | None = None
    due_at: datetime | None = None
    reminder_at: datetime | None = None
    priority: str | None = Field(default=None, pattern="^(low|normal|high)$")


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    detail: str | None
    due_date: date | None
    due_at: datetime | None
    reminder_at: datetime | None
    priority: str
    completed: bool
    created_at: datetime


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    status: str = Field(default="active", pattern="^(active|paused|completed)$")

    @field_validator("name")
    @classmethod
    def project_name_cannot_be_blank(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Le nom du projet ne peut pas être vide.")
        return normalized


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    status: str | None = Field(default=None, pattern="^(active|paused|completed)$")

    @field_validator("name")
    @classmethod
    def updated_project_name_cannot_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Le nom du projet ne peut pas être vide.")
        return normalized


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class GroceryCreate(BaseModel):
    label: str = Field(min_length=1, max_length=160)
    list_id: UUID | None = None

    @field_validator("label")
    @classmethod
    def label_cannot_be_blank(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("L’élément ne peut pas être vide.")
        return normalized


class GroceryUpdate(BaseModel):
    checked: bool


class GroceryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    label: str
    checked: bool
    created_at: datetime


class GroceryListCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def name_cannot_be_blank(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Le nom de la liste ne peut pas être vide.")
        return normalized


class GroceryListUpdate(BaseModel):
    archived: bool


class GroceryListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    archived: bool
    created_at: datetime


class TrainingCreate(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    training_type: str = Field(pattern="^(renforcement|course|mobilite)$")
    timing: str = Field(min_length=1, max_length=160)


class TrainingUpdate(BaseModel):
    completed: bool


class TrainingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    label: str
    training_type: str
    timing: str
    completed: bool
    created_at: datetime


class WeightCheckInCreate(BaseModel):
    weight_kg: float = Field(ge=20, le=400)
    recorded_on: date | None = None


class WeightCheckInResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    weight_kg: float
    recorded_on: date
    created_at: datetime
