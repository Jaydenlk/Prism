"""
Prism v2 — Authentication Schemas (DOC-06 Task 6.1)

Request / response models for the auth API endpoints.
All timestamps are UTC ISO-8601 strings.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    """POST /auth/register — new user registration (requires invite code)."""

    email: EmailStr
    username: str
    password: str
    invite_code: str

    @field_validator("username")
    @classmethod
    def username_length(cls, v: str) -> str:
        if not (3 <= len(v) <= 50):
            raise ValueError("username must be between 3 and 50 characters")
        return v

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    """POST /auth/login — credential-based login."""

    email: EmailStr
    password: str


class SSETicketRequest(BaseModel):
    """POST /auth/sse-ticket — generate a one-time SSE ticket (ADR-051)."""

    session_id: str


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class TokenResponse(BaseModel):
    """Returned on successful login or register."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access_token expiry


class RefreshResponse(BaseModel):
    """Returned on POST /auth/refresh."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    """Full user profile; returned by GET /auth/me."""

    id: str
    email: str
    username: str
    role: str
    avatar_url: Optional[str]
    last_login_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}
