from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refreshToken: str


class UserOut(BaseModel):
    id: str
    email: EmailStr


class AuthResponse(BaseModel):
    token: str
    refreshToken: str
    user: UserOut


class ProfileOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str | None = None
    phone: str | None = None
    phone_verified: bool = False
    address: str | None = None
    date_of_birth: date | None = None
    created_at: datetime
    updated_at: datetime


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1)
    address: str | None = None
    date_of_birth: date | None = None


class SendOtpRequest(BaseModel):
    phone: str


class VerifyOtpRequest(BaseModel):
    phone: str
    code: str = Field(min_length=6, max_length=6)
