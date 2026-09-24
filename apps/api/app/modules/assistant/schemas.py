from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AssistantTag(StrEnum):
    SCHOOL = "school"
    WORK = "work"
    ERRANDS = "errands"
    FAMILY = "family"


class AssistantKind(StrEnum):
    TASK = "task"
    REMINDER = "reminder"
    NOTE = "note"


class ThoughtOrganizationRequest(BaseModel):
    thought: str = Field(min_length=1, max_length=5000)
    tags: list[AssistantTag] = Field(default_factory=list, max_length=4)
    reference_date: date | None = None

    @field_validator("thought")
    @classmethod
    def thought_cannot_be_blank(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("La pensée ne peut pas être vide.")
        return normalized


class ThoughtOrganizationResponse(BaseModel):
    kind: AssistantKind
    title: str
    summary: str
    tags: list[AssistantTag]
    reminder_date: date | None
    mode: Literal["rules", "llm"] = "rules"


class GroceryMealPlanRequest(BaseModel):
    grocery_items: list[str] = Field(min_length=1, max_length=80)

    @field_validator("grocery_items")
    @classmethod
    def grocery_items_cannot_be_blank(cls, values: list[str]) -> list[str]:
        normalized = [" ".join(value.split()) for value in values]
        items = [value for value in normalized if value]
        if not items:
            raise ValueError("La liste de courses ne peut pas être vide.")
        return items


class MealPlanEntry(BaseModel):
    day: str
    name: str
    description: str
    uses: list[str]
    missing_items: list[str]


class GroceryMealPlanResponse(BaseModel):
    meals: list[MealPlanEntry]
    mode: Literal["rules", "llm"] = "rules"


class AssistantTurnRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)

    @field_validator("text")
    @classmethod
    def text_cannot_be_blank(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Votre message ne peut pas être vide.")
        return normalized


class VoiceTranscriptionResponse(BaseModel):
    """The editable text recovered from a short, explicitly recorded audio capture."""

    text: str = Field(min_length=1, max_length=5000)


class TaskProposalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    detail: str | None = Field(default=None, max_length=2000)
    priority: Literal["low", "normal", "high"] = "normal"
    due_date: date | None = None
    reminder_at: datetime | None = None


class GroceryProposalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=160)


class TrainingProposalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=100)
    training_type: Literal["renforcement", "course", "mobilite"] = "mobilite"
    timing: str = Field(min_length=1, max_length=160)


class NoteProposalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=240)


class CalendarEventProposalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    starts_at: datetime
    ends_at: datetime
    timezone: str = Field(default="Europe/Paris", min_length=1, max_length=64)

    @model_validator(mode="after")
    def end_must_follow_start(self) -> "CalendarEventProposalPayload":
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("Les horaires doivent indiquer un fuseau horaire.")
        if self.ends_at <= self.starts_at:
            raise ValueError("La fin doit être postérieure au début.")
        return self


class RecurringReminderProposalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    anchor_date: date
    recurrence_months: int = Field(ge=1, le=120)
    lead_days: int = Field(default=7, ge=0, le=90)
    timezone: str = Field(default="Europe/Paris", min_length=1, max_length=64)


class DeadlineReminderProposalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    due_date: date
    lead_days: int = Field(default=7, ge=0, le=90)
    timezone: str = Field(default="Europe/Paris", min_length=1, max_length=64)


ProposalPayload = Annotated[
    TaskProposalPayload
    | GroceryProposalPayload
    | TrainingProposalPayload
    | NoteProposalPayload
    | CalendarEventProposalPayload
    | RecurringReminderProposalPayload
    | DeadlineReminderProposalPayload,
    Field(discriminator=None),
]


class AssistantProposalResponse(BaseModel):
    id: UUID
    kind: Literal[
        "task",
        "grocery_item",
        "training",
        "note",
        "calendar_event",
        "recurring_reminder",
        "deadline_reminder",
    ]
    payload: dict[str, object]
    payload_version: int
    status: Literal["pending", "confirmed", "cancelled", "expired", "failed"]
    created_at: datetime


class CalendarEventResponse(BaseModel):
    id: UUID
    title: str
    starts_at: datetime
    ends_at: datetime
    timezone: str
    source: str


class CalendarEventListResponse(BaseModel):
    events: list[CalendarEventResponse]


class RecurringReminderResponse(BaseModel):
    id: UUID
    title: str
    anchor_date: date
    recurrence_months: int
    lead_days: int
    next_due_date: date
    next_reminder_at: datetime
    timezone: str
    active: bool


class RecurringReminderUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    anchor_date: date | None = None
    recurrence_months: int | None = Field(default=None, ge=1, le=120)
    lead_days: int | None = Field(default=None, ge=0, le=90)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)


class NotificationResponse(BaseModel):
    id: UUID
    title: str
    body: str
    data: dict[str, object]
    provider_status: Literal[
        "pending", "accepted", "delivered", "retrying", "failed", "receipt_failed"
    ]
    sent_at: datetime | None
    read_at: datetime | None
    created_at: datetime


class AssistantMessageResponse(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    proposals: list[AssistantProposalResponse] = Field(default_factory=list)


class AssistantTurnResponse(BaseModel):
    message: AssistantMessageResponse
    mode: Literal["rules", "llm"]


class AssistantChatResponse(BaseModel):
    """One model-backed turn for the intentionally small Cocoon agent harness."""

    message: AssistantMessageResponse
    choices: list[str] = Field(default_factory=list, max_length=3)
    remembered: list[str] = Field(default_factory=list, max_length=2)
    mode: Literal["llm"] = "llm"
    runtime: Literal["local"] = "local"


class AssistantHistoryResponse(BaseModel):
    messages: list[AssistantMessageResponse]


class AssistantBriefingResponse(BaseModel):
    heading: str
    summary: str
    tasks: list[str]
    generated_at: datetime


class DailyBriefSettings(BaseModel):
    timezone: str = Field(default="Europe/Paris", min_length=1, max_length=64)
    delivery_time: str = Field(default="08:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    enabled: bool = True
    daily_notification_quota: int = Field(default=20, ge=1, le=100)
