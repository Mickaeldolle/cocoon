from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class CaptureCreate(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    timezone: str = Field(default="Europe/Paris", min_length=1, max_length=64)


class ProposalResponse(BaseModel):
    id: UUID
    capability: str
    payload: dict[str, object]
    payload_version: int
    reason: str
    status: str
    confirmed_at: datetime | None = None
    label: str | None = None


class CaptureResponse(BaseModel):
    id: UUID
    run_id: UUID
    summary: str
    clarification: str | None = None
    proposals: list[ProposalResponse]
    mode: Literal["rules", "llm"]


class CaptureRunEventResponse(BaseModel):
    sequence: int
    event_type: str
    payload: dict[str, object]
    created_at: datetime


class CaptureRunResponse(BaseModel):
    id: UUID
    capture_id: UUID
    status: str
    attempt: int
    error_code: str | None = None
    created_at: datetime
    finished_at: datetime | None = None
    events: list[CaptureRunEventResponse]


class CaptureStreamEvent(BaseModel):
    type: Literal["progress", "fragment", "complete", "error"]
    stage: str | None = None
    text: str | None = None
    capture: CaptureResponse | None = None
    detail: str | None = None


class HomeSignal(BaseModel):
    id: UUID
    kind: str
    title: str
    reason: str
    source: str
    proposal_id: UUID | None = None
    payload_version: int | None = None


class HomeResponse(BaseModel):
    signals: list[HomeSignal]
