import warnings
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pydantic.alias_generators import to_camel
from pydantic.warnings import UnsupportedFieldAttributeWarning

# FastAPI 0.115.x rebuilds each field as its own FieldInfo when flattening a
# CamelModel-based request body for its internal TypeAdapter/OpenAPI schema
# generation step. That rebuild re-presents the alias already produced by
# alias_generator as if it had been passed to Field() directly, which trips
# this warning for every field on every request — confirmed harmless (request
# parsing and response serialization both behave correctly) via a minimal
# repro; this is a known FastAPI/Pydantic interop wrinkle, not a bug here.
warnings.filterwarnings("ignore", category=UnsupportedFieldAttributeWarning)


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class RegisterRequest(CamelModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refreshToken: str


class UserOut(CamelModel):
    id: str
    email: EmailStr
    role: Literal["admin", "member"]
    membership_tier: Literal["regular", "vip"] | None = None


class AuthResponse(BaseModel):
    token: str
    refreshToken: str
    user: UserOut


class ProfileOut(CamelModel):
    id: str
    email: EmailStr
    full_name: str | None = None
    phone: str | None = None
    phone_verified: bool = False
    address: str | None = None
    date_of_birth: date | None = None
    avatar_url: str | None = None
    bio: str | None = None
    role: Literal["admin", "member"]
    membership_tier: Literal["regular", "vip"] | None = None
    created_at: datetime
    updated_at: datetime


class ProfileUpdateRequest(CamelModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1)
    address: str | None = None
    date_of_birth: date | None = None
    bio: str | None = None


class SendOtpRequest(BaseModel):
    phone: str


class SendOtpResponse(CamelModel):
    message: str
    debug_otp: str | None = None


class VerifyOtpRequest(BaseModel):
    phone: str
    code: str = Field(min_length=6, max_length=6)


class SettingsOut(CamelModel):
    language: str
    timezone: str
    theme: Literal["light", "dark", "system"]
    email_notifications: bool


class SettingsUpdateRequest(CamelModel):
    model_config = ConfigDict(extra="forbid")

    language: str | None = None
    timezone: str | None = None
    theme: Literal["light", "dark", "system"] | None = None
    email_notifications: bool | None = None


class NotificationOut(CamelModel):
    id: str
    type: str
    title: str
    message: str
    metadata: dict
    read_at: datetime | None = None
    created_at: datetime


class MarkAllReadResponse(CamelModel):
    marked_count: int


class MemberOut(CamelModel):
    id: str
    email: EmailStr
    full_name: str | None = None
    role: Literal["admin", "member"]
    membership_tier: Literal["regular", "vip"] | None = None
    address: str | None = None
    date_of_birth: date | None = None
    created_at: datetime
    updated_at: datetime


class MemberListResponse(CamelModel):
    items: list[MemberOut]
    total: int
    page: int
    page_size: int


class MemberCreateRequest(CamelModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)
    address: str | None = None
    date_of_birth: date | None = None


class MemberUpdateRequest(CamelModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1)
    address: str | None = None
    date_of_birth: date | None = None
    membership_tier: Literal["regular", "vip"] | None = None
