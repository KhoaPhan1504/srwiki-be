import warnings
from datetime import date, datetime
from typing import Annotated, Literal

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


RoleName = Literal["super_admin", "admin", "member"]


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
    role: RoleName
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
    role: RoleName
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
    role: RoleName
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


class AdminOut(CamelModel):
    id: str
    email: EmailStr
    full_name: str | None = None
    role: RoleName
    address: str | None = None
    date_of_birth: date | None = None
    created_at: datetime
    updated_at: datetime


class AdminListResponse(CamelModel):
    items: list[AdminOut]
    total: int
    page: int
    page_size: int


class AdminCreateRequest(CamelModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)
    address: str | None = None
    date_of_birth: date | None = None


class AdminUpdateRequest(CamelModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1)
    address: str | None = None
    date_of_birth: date | None = None


class SavedRequestOut(CamelModel):
    id: str
    collection_id: str
    name: str
    method: str
    url: str
    query_params: list[dict]
    headers: list[dict]
    body: str
    body_type: str
    body_fields: list[dict]
    auth: dict
    created_at: datetime
    updated_at: datetime


class CollectionOut(CamelModel):
    id: str
    name: str
    created_at: datetime
    requests: list[SavedRequestOut]


class CollectionCreateRequest(CamelModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)


class CollectionUpdateRequest(CamelModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)


RestHttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
RestBodyType = Literal["raw", "urlEncoded", "formData"]


class SavedRequestCreateRequest(CamelModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    method: RestHttpMethod
    url: str = Field(min_length=1)
    query_params: list[dict] = Field(default_factory=list)
    headers: list[dict] = Field(default_factory=list)
    body: str = ""
    body_type: RestBodyType = "raw"
    body_fields: list[dict] = Field(default_factory=list)
    auth: dict = Field(default_factory=lambda: {"type": "none"})


class SavedRequestUpdateRequest(CamelModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    method: RestHttpMethod | None = None
    url: str | None = None
    query_params: list[dict] | None = None
    headers: list[dict] | None = None
    body: str | None = None
    body_type: RestBodyType | None = None
    body_fields: list[dict] | None = None
    auth: dict | None = None


class EnvironmentOut(CamelModel):
    id: str
    name: str
    variables: list[dict]
    created_at: datetime
    updated_at: datetime


class EnvironmentCreateRequest(CamelModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    variables: list[dict] = Field(default_factory=list)


class EnvironmentUpdateRequest(CamelModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    variables: list[dict] | None = None


class GlobalVariablesOut(CamelModel):
    variables: list[dict]


class GlobalVariablesUpdateRequest(CamelModel):
    model_config = ConfigDict(extra="forbid")
    variables: list[dict]


class HeaderInspectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1, max_length=2048)


class HeaderEntryOut(CamelModel):
    name: str
    value: str


class HeaderInspectionResponse(CamelModel):
    status_code: int
    reason_phrase: str
    headers: list[HeaderEntryOut]
    final_url: str
    redirect_count: int
    duration_ms: float
    http_version: str


class UserMessage(CamelModel):
    role: Literal["user"] = "user"
    content: str


class AssistantReplyTurn(CamelModel):
    type: Literal["reply"] = "reply"
    content: str


class AssistantToolCallTurn(CamelModel):
    type: Literal["tool_call"] = "tool_call"
    tool_call_id: str
    tool_name: str
    tool_input: dict
    provider_data: str | None = None


AssistantTurn = Annotated[
    AssistantReplyTurn | AssistantToolCallTurn,
    Field(discriminator="type"),
]


class AssistantMessage(CamelModel):
    role: Literal["assistant"] = "assistant"
    turns: list[AssistantTurn] = Field(min_length=1)
    model: str | None = None


class ToolDescriptor(CamelModel):
    name: str
    description: str
    input_schema: dict


class ToolResultMessage(CamelModel):
    role: Literal["tool_result"] = "tool_result"
    tool_call_id: str
    result: dict


ChatMessage = Annotated[
    UserMessage | AssistantMessage | ToolResultMessage,
    Field(discriminator="role"),
]


class AiChatRequest(CamelModel):
    messages: list[ChatMessage] = Field(min_length=1)
    tools: list[ToolDescriptor] = Field(default_factory=list)
    model: str


class AiChatResponse(CamelModel):
    turns: list[AssistantTurn] = Field(min_length=1)


class ModelOut(CamelModel):
    id: str
    label: str
    provider: str


class ModelsResponse(CamelModel):
    models: list[ModelOut]


class ConversationSummary(CamelModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationCreateRequest(CamelModel):
    title: str = Field(default="New conversation", min_length=1, max_length=200)


class ConversationRenameRequest(CamelModel):
    title: str = Field(min_length=1, max_length=200)


class ConversationMessageOut(CamelModel):
    id: str
    payload: ChatMessage
    created_at: datetime


class ConversationDetail(CamelModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[ConversationMessageOut]


class AppendMessagesRequest(CamelModel):
    messages: list[ChatMessage] = Field(min_length=1)


class AppendMessagesResponse(CamelModel):
    messages: list[ConversationMessageOut]


class WeatherRequest(CamelModel):
    mode: Literal["current", "forecast"]
    city: str = Field(min_length=1)


class CurrentWeatherOut(CamelModel):
    mode: Literal["current"] = "current"
    city: str
    country: str
    temperature_c: float
    feels_like_c: float
    description: str
    humidity_percent: int
    wind_speed_ms: float


class DailyForecastOut(CamelModel):
    date: str
    min_temperature_c: float
    max_temperature_c: float
    description: str


class ForecastOut(CamelModel):
    mode: Literal["forecast"] = "forecast"
    city: str
    country: str
    days: list[DailyForecastOut]
