from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

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


class MemoryListResponse(BaseModel):
    memories: list[MemoryResponse]


class MemoryCorrectionRequest(BaseModel):
    summary: str = Field(min_length=1, max_length=240)
    memory_type: MemoryType | None = None
    layer: MemoryLayer | None = None
    confidence: int = Field(default=70, ge=0, le=100)


class MemoryActionResponse(BaseModel):
    id: UUID
    state: Literal["active", "stale", "dismissed"]
