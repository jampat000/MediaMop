"""Pydantic schemas for auth JSON API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from mediamop.platform.auth.password import MIN_PASSWORD_LENGTH


class CsrfOut(BaseModel):
    csrf_token: str = Field(..., description="Send on unsafe requests (header X-CSRF-Token or body).")


class LoginIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1)
    csrf_token: str = Field(..., min_length=1)


class UserPublic(BaseModel):
    id: int
    username: str
    role: str


class LoginOut(BaseModel):
    user: UserPublic


class LogoutIn(BaseModel):
    """Optional body CSRF fallback when header is awkward for a client."""

    csrf_token: str | None = None


class MeOut(BaseModel):
    user: UserPublic


class BootstrapStatusOut(BaseModel):
    """Whether first-run bootstrap may create the initial ``admin`` user."""

    bootstrap_allowed: bool
    reason: str


class BootstrapIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, max_length=512)
    csrf_token: str = Field(..., min_length=1)


class BootstrapOut(BaseModel):
    message: str
    username: str


class ChangePasswordIn(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, max_length=512)
    csrf_token: str = Field(..., min_length=1)


class ChangePasswordOut(BaseModel):
    message: str
