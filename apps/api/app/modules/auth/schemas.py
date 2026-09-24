from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class DeviceInput(BaseModel):
    installation_id: str = Field(min_length=12, max_length=128)
    name: str = Field(min_length=1, max_length=100)
    platform: str = Field(min_length=1, max_length=32)


class RegisterRequest(DeviceInput):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=256)


class LoginRequest(DeviceInput):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=512)


class PushTokenRequest(BaseModel):
    push_token: str = Field(
        min_length=10,
        max_length=256,
        pattern=r"^(?:Expo|Exponent)PushToken\[[^\]\r\n]+\]$",
    )


class DeviceResponse(BaseModel):
    id: UUID
    name: str
    platform: str
    created_at: datetime
    last_seen_at: datetime
    current: bool


class ConsentUpdate(BaseModel):
    policy_version: int = Field(ge=1, le=1000)
    source: str = Field(default="mobile", min_length=1, max_length=32)


class ConsentResponse(BaseModel):
    id: UUID
    policy_key: str
    policy_version: int
    source: str
    granted_at: datetime
    revoked_at: datetime | None
    active: bool


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class SecretUnlockRequest(BaseModel):
    password: str = Field(min_length=8, max_length=256)


class DevelopmentBiometricCredentialRequest(BaseModel):
    credential: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class SecretAccessResponse(BaseModel):
    secret_access_token: str
    expires_at: datetime


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    display_name: str
    is_superadmin: bool
    created_at: datetime
