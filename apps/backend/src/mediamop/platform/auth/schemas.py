"""Pydantic schemas for auth JSON API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from mediamop.platform.auth.password import MIN_PASSWORD_LENGTH


class CsrfOut(BaseModel):
    csrf_token: str = Field(..., description="Send on unsafe requests (header X-CSRF-Token or body).")


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1)
    csrf_token: str = Field(..., min_length=1)
    trusted_device: bool = False


class UserPublic(BaseModel):
    id: int
    username: str
    role: str


class LoginOut(BaseModel):
    user: UserPublic


class LogoutIn(BaseModel):
    """Optional body CSRF fallback when header is awkward for a client."""

    model_config = ConfigDict(extra="forbid")

    csrf_token: str | None = None


class MeOut(BaseModel):
    user: UserPublic


class CurrentSessionOut(BaseModel):
    session_id: str = ""
    client_label: str = "Browser session"
    current: bool = True
    trusted_device: bool
    created_at: datetime
    last_seen_at: datetime
    absolute_expires_at: datetime
    idle_timeout_minutes: int = Field(ge=1)
    absolute_timeout_days: int = Field(ge=1)


class SessionOut(CurrentSessionOut):
    """Safe session inventory entry; never includes the cookie or token hash."""

    current: bool = False


class SessionsOut(BaseModel):
    items: list[SessionOut]


class SessionActionOut(BaseModel):
    message: str
    revoked_count: int = Field(default=0, ge=0)


class BootstrapStatusOut(BaseModel):
    """Whether first-run bootstrap may create the initial ``admin`` user."""

    bootstrap_allowed: bool
    reason: str


class BootstrapIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, max_length=512)
    csrf_token: str = Field(..., min_length=1)


class BootstrapOut(BaseModel):
    message: str
    username: str


class ChangePasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, max_length=512)
    csrf_token: str = Field(..., min_length=1)


class ChangePasswordOut(BaseModel):
    message: str
