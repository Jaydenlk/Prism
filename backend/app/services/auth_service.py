"""
Prism v2 — Authentication Service (DOC-06 Task 6.1, ADR-050/051/052)

Responsibilities:
  - register()      : validate invite code → create user → consume code → issue tokens
  - login()         : validate password → update last_login_at → issue tokens
  - refresh()       : verify refresh JWT → issue new access token
  - ensure_admin()  : idempotent bootstrap of the admin user from env vars
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
    decode_token,
)
from app.models.audit import AuditLog
from app.models.user import InviteCode, User
from app.models.base import generate_uuid
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services.user_service import UserService

import structlog
logger = structlog.get_logger()


class AuthService:
    """Implements the full auth lifecycle for Prism v2."""

    def __init__(self, db: Session, settings: Settings) -> None:
        self._db = db
        self._settings = settings

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, data: RegisterRequest) -> tuple[User, str, str]:
        """Register a new user gated by an invite code.

        Returns:
            (user, access_token, refresh_token)

        Raises:
            HTTPException 400: invite code invalid / expired / exhausted
            HTTPException 409: email or username already taken
        """
        svc = UserService(self._db)

        # --- Uniqueness checks --------------------------------------------
        if svc.get_by_email(str(data.email)) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )
        if svc.get_by_username(data.username) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already taken",
            )

        # --- Invite code validation ----------------------------------------
        invite = (
            self._db.query(InviteCode)
            .filter(InviteCode.code == data.invite_code)
            .first()
        )
        if invite is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid invite code",
            )
        now = datetime.now(timezone.utc)
        if invite.expires_at is not None and invite.expires_at < now:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invite code has expired",
            )
        if invite.used_count >= invite.max_uses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invite code has reached its maximum usage limit",
            )

        # --- Create user --------------------------------------------------
        user = User(
            email=str(data.email),
            username=data.username,
            password_hash=hash_password(data.password),
            role="user",
        )
        self._db.add(user)
        self._db.flush()  # get user.id before consuming invite

        # --- Consume invite code ------------------------------------------
        invite.used_count += 1
        self._db.flush()

        # --- Audit log ----------------------------------------------------
        self._write_audit(
            user_id=user.id,
            action="user.register",
            resource_type="user",
            resource_id=user.id,
            details={"invite_code_id": invite.id},
        )

        # --- Issue tokens -------------------------------------------------
        access_token = create_access_token(user.id)
        refresh_token = create_refresh_token(user.id)

        return user, access_token, refresh_token

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def login(self, data: LoginRequest) -> tuple[User, str, str]:
        """Authenticate a user by email + password.

        Returns:
            (user, access_token, refresh_token)

        Raises:
            HTTPException 401: invalid credentials (email or password wrong)
        """
        svc = UserService(self._db)
        user = svc.get_by_email(str(data.email))

        # Unified error — do not distinguish "no such user" from "wrong password"
        _invalid = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
        )

        if user is None:
            raise _invalid
        if not verify_password(data.password, user.password_hash):
            raise _invalid
        if getattr(user, "is_active", True) is False:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="账户已被禁用，请联系管理员",
            )

        # Update last_login_at
        user.last_login_at = datetime.now(timezone.utc)
        self._db.flush()

        # Audit
        self._write_audit(
            user_id=user.id,
            action="user.login",
            resource_type="user",
            resource_id=user.id,
        )

        access_token = create_access_token(user.id)
        refresh_token = create_refresh_token(user.id)

        return user, access_token, refresh_token

    # ------------------------------------------------------------------
    # Token refresh
    # ------------------------------------------------------------------

    def refresh(self, refresh_token: str) -> str:
        """Exchange a valid refresh JWT for a new access token.

        Returns:
            New access_token string

        Raises:
            HTTPException 401: token invalid / expired / wrong type
        """
        try:
            payload = decode_token(refresh_token)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )

        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token type must be 'refresh'",
            )

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Malformed refresh token",
            )

        user = UserService(self._db).get_by_id(user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User no longer exists",
            )

        return create_access_token(user.id)

    # ------------------------------------------------------------------
    # Admin bootstrap
    # ------------------------------------------------------------------

    def ensure_admin(self) -> None:
        """Idempotently create the admin user from ADMIN_EMAIL / ADMIN_PASSWORD.

        Called once during lifespan startup.  If the admin already exists,
        this is a no-op.  The admin account does not require an invite code.
        """
        svc = UserService(self._db)
        existing = svc.get_by_email(self._settings.ADMIN_EMAIL)
        if existing is not None:
            logger.debug(
                "auth.admin_bootstrap.skipped",
                extra={"email": self._settings.ADMIN_EMAIL},
            )
            return

        admin = User(
            email=self._settings.ADMIN_EMAIL,
            username="admin",
            password_hash=hash_password(self._settings.ADMIN_PASSWORD),
            role="admin",
        )
        self._db.add(admin)
        self._db.flush()

        self._write_audit(
            user_id=admin.id,
            action="user.admin_bootstrap",
            resource_type="user",
            resource_id=admin.id,
            details={"email": self._settings.ADMIN_EMAIL},
        )

        logger.info(
            "auth.admin_bootstrap.created",
            extra={"email": self._settings.ADMIN_EMAIL},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_audit(
        self,
        *,
        action: str,
        user_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        details: dict | None = None,
        ip_address: str | None = None,
    ) -> None:
        entry = AuditLog(
            id=generate_uuid(),
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            ip_address=ip_address,
            created_at=datetime.now(timezone.utc),
        )
        self._db.add(entry)
        self._db.flush()
