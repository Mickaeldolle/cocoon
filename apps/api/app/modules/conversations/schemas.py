from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConversationCreate(BaseModel):
    invitee: str | None = Field(default=None, min_length=1, max_length=320)
    member_emails: list[str] | None = Field(default=None, min_length=1, max_length=1)
    name: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def has_one_invitee(self) -> "ConversationCreate":
        if bool(self.invitee) == bool(self.member_emails):
            raise ValueError("Indiquez un pseudo ou une adresse email.")
        return self


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str | None
    created_at: datetime
    updated_at: datetime
    membership_status: str = "accepted"


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sender_id: UUID
    body: str
    created_at: datetime
    read_by_count: int = 0
