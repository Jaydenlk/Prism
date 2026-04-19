"""
Prism v2 — Authentication Schemas (DOC-06 Task 6.1 + multi-channel auth Task A)

Request / response models for the auth API endpoints.
All timestamps are UTC ISO-8601 strings.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, field_validator

# E.164-style phone validation (lenient: optional leading +, then digits)
_PHONE_RE = re.compile(r"^\+?[1-9]\d{1,14}$")


# ---------------------------------------------------------------------------
# Existing request schemas
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
# Multi-channel auth request schemas
# ---------------------------------------------------------------------------


class EmailMagicRequestBody(BaseModel):
    """POST /auth/email-magic/request — request a magic link."""

    email: EmailStr


class EmailMagicVerifyBody(BaseModel):
    """POST /auth/email-magic/verify — verify a magic link token."""

    challenge_id: str
    token: str


class EmailOtpRequestBody(BaseModel):
    """POST /auth/email-otp/request — request a 6-digit OTP."""

    email: EmailStr


class EmailOtpVerifyBody(BaseModel):
    """POST /auth/email-otp/verify — verify OTP by email + code."""

    email: EmailStr
    code: str

    @field_validator("code")
    @classmethod
    def code_digits(cls, v: str) -> str:
        if not re.fullmatch(r"\d{6}", v):
            raise ValueError("code must be exactly 6 digits")
        return v


class ForgotPasswordBody(BaseModel):
    """POST /auth/forgot-password — request a password-reset link."""

    email: EmailStr


class ResetPasswordBody(BaseModel):
    """POST /auth/reset-password — consume reset token + set new password."""

    challenge_id: str
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("new_password must be at least 8 characters")
        return v


class PhoneRegisterBody(BaseModel):
    """POST /auth/phone-register — register with phone + password + invite."""

    phone: str
    password: str
    invite_code: str

    @field_validator("phone")
    @classmethod
    def phone_format(cls, v: str) -> str:
        if not _PHONE_RE.match(v):
            raise ValueError("phone must be E.164 format, e.g. +8613800138000")
        return v

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


class PhoneLoginBody(BaseModel):
    """POST /auth/phone-login — login with phone + password."""

    phone: str
    password: str

    @field_validator("phone")
    @classmethod
    def phone_format(cls, v: str) -> str:
        if not _PHONE_RE.match(v):
            raise ValueError("phone must be E.164 format, e.g. +8613800138000")
        return v


# ---------------------------------------------------------------------------
# Existing response schemas
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
    """Full user profile; returned by GET /auth/me.

    `has_google` is computed from google_id field.
    `phone` and `email_verified` are safe to expose.
    """

    id: str
    email: str
    username: str
    role: str
    avatar_url: Optional[str]
    last_login_at: Optional[datetime]
    created_at: datetime
    # Multi-channel auth fields (safe to expose)
    phone: Optional[str] = None
    email_verified: bool = False
    has_google: bool = False

    model_config = {"from_attributes": True}

    @classmethod
    def from_user(cls, user: Any) -> "UserResponse":
        """Build UserResponse from a User ORM object."""
        return cls(
            id=str(user.id),
            email=user.email,
            username=user.username,
            role=user.role,
            avatar_url=getattr(user, "avatar_url", None),
            last_login_at=getattr(user, "last_login_at", None),
            created_at=user.created_at,
            phone=getattr(user, "phone", None),
            email_verified=bool(getattr(user, "email_verified", False)),
            has_google=bool(getattr(user, "google_id", None)),
        )


# ---------------------------------------------------------------------------
# Auth providers response
# ---------------------------------------------------------------------------


class AuthProvidersResponse(BaseModel):
    """GET /auth/providers — which login methods are enabled."""

    email_password: bool = True
    email_magic: bool = True
    email_otp: bool = True
    phone_password: bool = False
    google: bool = False


# ---------------------------------------------------------------------------
# Admin auth-config schemas
# ---------------------------------------------------------------------------


class AuthConfigEntry(BaseModel):
    """Single auth_config row."""

    key: str
    value_json: Any
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None

    model_config = {"from_attributes": True}


class AuthConfigPatchBody(BaseModel):
    """PATCH /admin/auth-config — update a single config entry."""

    key: str
    value_json: Any  # bool, str, int, dict — whatever the key stores
