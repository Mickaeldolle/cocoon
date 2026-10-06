from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.modules.neural.models import MemoryLayer, MemoryType


class MemoryResponse(BaseModel):
    id: UUID
    capture_id: UUID
    source_run_id: UUID | None
    source_message_id: UUID | None
    summary: str
    reason: str
    kind: str
    layer: MemoryLayer
    memory_type: MemoryType
    owner_type: str
    scope_type: str
    scope_id: UUID | None
    source_type: str
    confidence: int
    valid_from: datetime | None
    valid_until: datetime | None
    supersedes_id: UUID | None
    created_at: datetime
    observed_at: datetime | None = None
    state: str = "active"
    entity: str | None = None
    attribute: str | None = None
    value: str | None = None
    origin: str | None = None


class MemoryListResponse(BaseModel):
    memories: list[MemoryResponse]
    next_offset: int | None = None


class MemoryCorrectionRequest(BaseModel):
    summary: str = Field(min_length=1, max_length=240)
    memory_type: MemoryType | None = None
    layer: MemoryLayer | None = None
    confidence: int = Field(default=70, ge=0, le=100)
    scope_type: Literal["personal", "project"] | None = None
    scope_id: UUID | None = None
    entity: str | None = Field(default=None, max_length=160)
    attribute: str | None = Field(default=None, max_length=80)
    value: str | None = Field(default=None, max_length=240)
    valid_until: datetime | None = None

    @field_validator("summary")
    @classmethod
    def nonempty_summary(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Une mémoire ne peut pas être vide")
        return value

    @field_validator("valid_until")
    @classmethod
    def aware_date(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("La date de validité doit préciser son fuseau horaire")
        return value


class MemoryActionResponse(BaseModel):
    id: UUID
    state: Literal["active", "stale", "dismissed"]
