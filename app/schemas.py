from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

EventStatus = Literal["new", "handled", "false_positive"]


class StaffRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    invite_code: str = Field(max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class DeviceLogin(BaseModel):
    device_token: str = Field(max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Literal["staff", "device"]


class DeviceRegister(BaseModel):
    pairing_code: str = Field(max_length=32)
    location: str = Field(min_length=1, max_length=120)


class DeviceRegisterResponse(BaseModel):
    device_id: str
    device_token: str  # показывается один раз; в БД хранится только хэш
    access_token: str
    location: str


class PairingCodeOut(BaseModel):
    code: str
    expires_at: datetime


class DeviceOut(BaseModel):
    id: str
    location: str
    is_active: bool
    is_listening: bool
    online: bool
    last_seen: datetime | None


class DevicePatch(BaseModel):
    is_active: bool | None = None
    location: str | None = Field(default=None, min_length=1, max_length=120)


class HeartbeatIn(BaseModel):
    listening: bool


class TriggerOut(BaseModel):
    phrase: str
    category: str


class DeviceConfig(BaseModel):
    triggers: list[TriggerOut]
    min_confidence: float
    cooldown_seconds: int


class EventIn(BaseModel):
    """Единственное, что устройство может передать на сервер.

    extra="forbid": любое лишнее поле (text, transcript, audio...) отклоняется с 422.
    """

    model_config = ConfigDict(extra="forbid")

    device_id: str | None = None
    trigger_word: str = Field(max_length=64)
    confidence: float = Field(ge=0, le=1)
    timestamp: datetime | None = None


class EventCreated(BaseModel):
    id: int
    deduplicated: bool = False


class EventPatch(BaseModel):
    status: EventStatus


class EventOut(BaseModel):
    id: int
    device_id: str
    device_location: str
    occurred_at: datetime
    trigger_word: str
    category: str
    confidence: float
    status: EventStatus
    handled_by_email: str | None = None
    handled_at: datetime | None = None


class AuditOut(BaseModel):
    id: int
    user_email: str
    action: str
    details: str | None
    ip: str | None
    created_at: datetime


class PushKeys(BaseModel):
    p256dh: str = Field(max_length=255)
    auth: str = Field(max_length=255)


class PushSubscribeIn(BaseModel):
    endpoint: str = Field(max_length=2048)
    keys: PushKeys


class PushUnsubscribeIn(BaseModel):
    endpoint: str = Field(max_length=2048)