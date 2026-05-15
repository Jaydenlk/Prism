"""
Prism v2 — Authentication API Endpoints (DOC-06 Task 6.1 + multi-channel auth Task A+B)

Routes (all under /api/v1):
  POST /auth/register              — new user registration (requires invite code)  [public]
  POST /auth/login                 — email + password login                        [public]
  POST /auth/refresh               — exchange refresh cookie for new access token   [cookie]
  POST /auth/logout                — delete refresh_token cookie                    [bearer]
  GET  /auth/me                    — return current user profile                    [bearer]
  POST /auth/sse-ticket            — generate one-time SSE ticket (ADR-051)        [bearer]

  GET  /auth/providers             — which login methods are enabled (public)      [public]
  POST /auth/email-magic/request   — send magic link email                         [public]
  POST /auth/email-magic/verify    — verify magic link token → TokenResponse       [public]
  POST /auth/email-otp/request     — send 6-digit OTP email                       [public]
  POST /auth/email-otp/verify      — verify OTP → TokenResponse                   [public]
  POST /auth/forgot-password       — send password-reset link                      [public]
  POST /auth/reset-password        — consume reset token + set new password        [public]
  POST /auth/phone-register        — register with phone + password + invite       [public]
  POST /auth/phone-login           — login with phone + password                   [public]

  GET  /auth/google/authorize      — redirect to Google consent screen             [public]
  GET  /auth/google/callback       — handle Google OAuth callback                  [public]
  POST /auth/google/complete       — finish OAuth signup with invite code           [public]

ADR-051: SSE ticket replaces ?token=<JWT> in query string to prevent token
         leakage into browser history / Nginx access_log / Referer headers.

ADR-052: Refresh token stored as HttpOnly + Secure + SameSite=Lax cookie;
         no DB row — signature-based validation only.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, get_redis
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models.audit import AuditLog
from app.models.base import generate_uuid
from app.models.user import InviteCode, User
from app.schemas.auth import (
    AuthProvidersResponse,
    ChangePasswordBody,
    EmailMagicRequestBody,
    EmailMagicVerifyBody,
    EmailOtpRequestBody,
    EmailOtpVerifyBody,
    ForgotPasswordBody,
    GoogleCompleteBody,
    LoginRequest,
    PhoneLoginBody,
    PhoneRegisterBody,
    RefreshResponse,
    RegisterRequest,
    ResetPasswordBody,
    SSETicketRequest,
    TokenResponse,
    UserResponse,
)
from app.schemas.common import ApiResponse
from app.services.auth_challenge_service import AuthChallengeService
from app.services.auth_config_service import AuthConfigService
from app.services.auth_service import AuthService
from app.services.email_service import EmailService
from app.services.google_oauth_service import GoogleOAuthService
from app.services.sse_ticket_service import SSETicketService

import structlog
logger = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["auth"])

# Cookie name and path constants (ADR-052)
_REFRESH_COOKIE = "refresh_token"
_REFRESH_COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Attach the refresh_token HttpOnly cookie to *response* (ADR-052)."""
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        path=_REFRESH_COOKIE_PATH,
    )


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------


@router.post(
    "/register",
    response_model=ApiResponse[TokenResponse],
    status_code=status.HTTP_201_CREATED,
)
def register(
    data: RegisterRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[TokenResponse]:
    """Register a new user (requires a valid invite code).

    On success:
      - Sets refresh_token HttpOnly cookie
      - Returns access_token in response body

    Error codes:
      - 400: invite code invalid / expired / exhausted
      - 409: email or username already registered
      - 422: validation error
    """
    svc = AuthService(db, settings)
    user, access_token, refresh_token = svc.register(data)
    db.commit()

    _set_refresh_cookie(response, refresh_token)

    return ApiResponse(
        data=TokenResponse(
            access_token=access_token,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    )


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------


@router.post("/login", response_model=ApiResponse[TokenResponse])
def login(
    data: LoginRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[TokenResponse]:
    """Authenticate with email + password.

    On success sets the refresh_token HttpOnly cookie and returns an
    access_token in the response body.
    """
    svc = AuthService(db, settings)
    user, access_token, refresh_token = svc.login(data)
    db.commit()

    _set_refresh_cookie(response, refresh_token)

    return ApiResponse(
        data=TokenResponse(
            access_token=access_token,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    )


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------


@router.post("/refresh", response_model=ApiResponse[RefreshResponse])
def refresh(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[RefreshResponse]:
    """Exchange a refresh_token cookie for a new access token.

    The refresh_token is read from the HttpOnly cookie set at login.
    Returns 401 if the cookie is absent or the token is invalid/expired.
    """
    refresh_token = request.cookies.get(_REFRESH_COOKIE)
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token cookie",
        )

    svc = AuthService(db, settings)
    access_token = svc.refresh(refresh_token)

    return ApiResponse(
        data=RefreshResponse(
            access_token=access_token,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    )


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------


@router.post("/logout")
def logout(
    response: Response,
    _user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[dict]:
    """Log out the current user by deleting the refresh_token cookie.

    Phase 1 does not implement a token blacklist — the access_token remains
    valid until its short TTL (15 min default) expires.
    """
    response.delete_cookie(key=_REFRESH_COOKIE, path=_REFRESH_COOKIE_PATH)
    return ApiResponse(data={"message": "logged out"})


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------


@router.get("/me", response_model=ApiResponse[UserResponse])
def me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[UserResponse]:
    """Return the authenticated user's profile."""
    return ApiResponse(data=UserResponse.from_user(current_user))


# ---------------------------------------------------------------------------
# POST /auth/sse-ticket  (ADR-051: SSE one-time ticket)
# ---------------------------------------------------------------------------


@router.post("/sse-ticket")
async def create_sse_ticket(
    body: SSETicketRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    """Generate a one-time SSE ticket bound to the current user and session.

    Flow (ADR-051):
      1. Client calls POST /auth/sse-ticket {session_id}
      2. Backend verifies session belongs to current user
      3. Backend generates uuid4 ticket, stores in Redis with SETEX 60s
      4. Client opens EventSource with ?ticket=<ticket> instead of ?token=<JWT>
      5. SSE handler consumes ticket atomically via GETDEL (DOC-07 Task 7.3)

    Returns:
      {"ticket": "<uuid4>", "expires_at": "<ISO-8601 UTC>"}
    """
    from app.models.session import Session as PrismSession

    # Verify the session_id belongs to the current user
    session = (
        db.query(PrismSession)
        .filter(
            PrismSession.id == body.session_id,
            PrismSession.user_id == current_user.id,
        )
        .first()
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or does not belong to current user",
        )

    from app.core.dependencies import get_redis
    redis_client = None
    try:
        async for r in get_redis():
            redis_client = r
            break
    except NotImplementedError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis not initialised; SSE tickets unavailable.",
        )
    if redis_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis not initialised; SSE tickets unavailable.",
        )

    ticket_svc = SSETicketService(redis_client, settings)
    result = await ticket_svc.generate_ticket(
        user_id=str(current_user.id),
        session_id=body.session_id,
    )

    logger.info(
        "auth.sse_ticket.issued",
        extra={
            "user_id": str(current_user.id),
            "session_id": body.session_id,
            "ticket_prefix": result["ticket"][:8],
        },
    )

    return ApiResponse(data=result)


# ===========================================================================
# Multi-channel auth endpoints (Task A)
# ===========================================================================


# ---------------------------------------------------------------------------
# Helper: issue tokens + set cookie + write audit log
# ---------------------------------------------------------------------------


def _issue_tokens_response(
    response: Response,
    user: User,
    db: Session,
    action: str = "user.login",
) -> ApiResponse[TokenResponse]:
    """Issue access + refresh tokens, set cookie, write audit log, return response."""
    # Mark last_login_at
    user.last_login_at = datetime.now(timezone.utc)

    # Audit log
    audit = AuditLog(
        id=generate_uuid(),
        user_id=user.id,
        action=action,
        resource_type="user",
        resource_id=user.id,
        details={},
        created_at=datetime.now(timezone.utc),
    )
    db.add(audit)
    db.flush()

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    _set_refresh_cookie(response, refresh_token)

    return ApiResponse(
        data=TokenResponse(
            access_token=access_token,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    )


def _validate_invite(invite_code: str, db: Session) -> InviteCode:
    """Validate an invite code and return the InviteCode row.

    Raises HTTPException 400 if invalid/expired/exhausted.
    """
    invite = db.query(InviteCode).filter(InviteCode.code == invite_code).first()
    if invite is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid invite code")
    now = datetime.now(timezone.utc)
    if invite.expires_at is not None and invite.expires_at < now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite code has expired")
    if invite.used_count >= invite.max_uses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invite code has reached its maximum usage limit",
        )
    return invite


# ---------------------------------------------------------------------------
# GET /auth/providers
# ---------------------------------------------------------------------------


@router.get("/providers", response_model=ApiResponse[AuthProvidersResponse])
def get_providers(
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[AuthProvidersResponse]:
    """Return which auth methods are enabled (public endpoint).

    Frontend uses this to decide which login buttons to show.
    """
    cfg_svc = AuthConfigService(db)
    phone_enabled = cfg_svc.is_phone_registration_allowed()
    # Google OAuth availability: both client_id AND client_secret must be set
    google_svc = GoogleOAuthService(settings, redis_client=None)
    google_enabled = google_svc.is_configured()
    # Dev-only: surface default admin creds to enable one-click fill on LoginScreen.
    # PRISM_ENV defaults to "development"; production deployments must set "production".
    dev_admin = None
    if settings.PRISM_ENV != "production":
        from app.schemas.auth import DevDefaultAdmin
        dev_admin = DevDefaultAdmin(
            email=settings.ADMIN_EMAIL, password=settings.ADMIN_PASSWORD
        )
    return ApiResponse(
        data=AuthProvidersResponse(
            email_password=True,
            email_magic=True,
            email_otp=True,
            phone_password=phone_enabled,
            google=google_enabled,
            dev_default_admin=dev_admin,
        )
    )


# ---------------------------------------------------------------------------
# POST /auth/email-magic/request
# ---------------------------------------------------------------------------


@router.post(
    "/email-magic/request",
    status_code=status.HTTP_202_ACCEPTED,
)
async def email_magic_request(
    body: EmailMagicRequestBody,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Send a magic-link login email.

    Always returns 202 — does not reveal whether the email is registered
    (prevents user enumeration).
    """
    email = str(body.email)
    user = db.query(User).filter(User.email == email).first()

    if user is not None:
        # Get Redis
        redis_client = None
        async for r in get_redis():
            redis_client = r
            break
        if redis_client is None:
            logger.warning("auth.magic.redis_unavailable", email=email)
            return {"message": "If your email is registered, a magic link has been sent"}

        challenge_svc = AuthChallengeService(redis_client)
        result = await challenge_svc.create_challenge(
            challenge_type="magic_link_email",
            identifier=email,
            user_id=str(user.id),
        )

        base_url = settings.PRISM_BASE_URL or "http://localhost:8080"
        magic_url = (
            f"{base_url}/auth/magic"
            f"?challenge_id={result['challenge_id']}&token={result['token']}"
        )

        email_svc = EmailService(settings)
        email_svc.send(
            to=email,
            subject="Prism 登录链接",
            body=f"点此登录 Prism（15分钟内有效）:\n\n{magic_url}\n\n如非本人操作请忽略此邮件。",
        )

        logger.info(
            "auth.magic.requested",
            user_id=str(user.id),
            challenge_id=result["challenge_id"],
        )

    return {"message": "If your email is registered, a magic link has been sent"}


# ---------------------------------------------------------------------------
# POST /auth/email-magic/verify
# ---------------------------------------------------------------------------


@router.post("/email-magic/verify", response_model=ApiResponse[TokenResponse])
async def email_magic_verify(
    body: EmailMagicVerifyBody,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[TokenResponse]:
    """Verify a magic-link token and issue JWT tokens."""
    redis_client = None
    async for r in get_redis():
        redis_client = r
        break
    if redis_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable",
        )

    challenge_svc = AuthChallengeService(redis_client)
    try:
        payload = await challenge_svc.verify_challenge(
            challenge_type="magic_link_email",
            challenge_id=body.challenge_id,
            token=body.token,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid challenge: missing user_id",
        )

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled",
        )

    # Mark email as verified on successful magic-link login
    user.email_verified = True

    resp = _issue_tokens_response(response, user, db, action="user.login.magic")
    db.commit()
    return resp


# ---------------------------------------------------------------------------
# POST /auth/email-otp/request
# ---------------------------------------------------------------------------


@router.post(
    "/email-otp/request",
    status_code=status.HTTP_202_ACCEPTED,
)
async def email_otp_request(
    body: EmailOtpRequestBody,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Send a 6-digit OTP to the given email.

    Always returns 202 (no user enumeration).
    """
    email = str(body.email)
    user = db.query(User).filter(User.email == email).first()

    if user is not None:
        redis_client = None
        async for r in get_redis():
            redis_client = r
            break
        if redis_client is None:
            logger.warning("auth.otp.redis_unavailable", email=email)
            return {"message": "If your email is registered, an OTP has been sent"}

        challenge_svc = AuthChallengeService(redis_client)
        result = await challenge_svc.create_otp_challenge(
            challenge_type="otp_email",
            identifier=email,
            user_id=str(user.id),
        )

        email_svc = EmailService(settings)
        email_svc.send(
            to=email,
            subject="Prism 验证码",
            body=f"您的 Prism 登录验证码是：{result['code']}\n\n15分钟内有效，请勿泄露给他人。",
        )

        logger.info(
            "auth.otp.requested",
            user_id=str(user.id),
            challenge_id=result["challenge_id"],
        )

    return {"message": "If your email is registered, an OTP has been sent"}


# ---------------------------------------------------------------------------
# POST /auth/email-otp/verify
# ---------------------------------------------------------------------------


@router.post("/email-otp/verify", response_model=ApiResponse[TokenResponse])
async def email_otp_verify(
    body: EmailOtpVerifyBody,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[TokenResponse]:
    """Verify email OTP and issue JWT tokens."""
    redis_client = None
    async for r in get_redis():
        redis_client = r
        break
    if redis_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable",
        )

    challenge_svc = AuthChallengeService(redis_client)
    try:
        payload = await challenge_svc.verify_otp(
            challenge_type="otp_email",
            identifier=str(body.email),
            code=body.code,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid challenge: missing user_id",
        )

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled",
        )

    # Mark email as verified on successful OTP login
    user.email_verified = True

    resp = _issue_tokens_response(response, user, db, action="user.login.otp")
    db.commit()
    return resp


# ---------------------------------------------------------------------------
# POST /auth/forgot-password
# ---------------------------------------------------------------------------


@router.post(
    "/forgot-password",
    status_code=status.HTTP_202_ACCEPTED,
)
async def forgot_password(
    body: ForgotPasswordBody,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Request a password-reset link email.

    Always returns 202 (no user enumeration).
    """
    email = str(body.email)
    user = db.query(User).filter(User.email == email).first()

    if user is not None:
        redis_client = None
        async for r in get_redis():
            redis_client = r
            break
        if redis_client is None:
            logger.warning("auth.forgot_password.redis_unavailable", email=email)
            return {"message": "If your email is registered, a reset link has been sent"}

        challenge_svc = AuthChallengeService(redis_client)
        result = await challenge_svc.create_challenge(
            challenge_type="password_reset_email",
            identifier=email,
            user_id=str(user.id),
        )

        base_url = settings.PRISM_BASE_URL or "http://localhost:8080"
        reset_url = (
            f"{base_url}/auth/reset-password"
            f"?challenge_id={result['challenge_id']}&token={result['token']}"
        )

        email_svc = EmailService(settings)
        email_svc.send(
            to=email,
            subject="Prism 重置密码",
            body=(
                f"点击以下链接重置您的 Prism 密码（15分钟内有效）:\n\n{reset_url}\n\n"
                "如非本人操作请忽略此邮件，您的账户仍然安全。"
            ),
        )

        logger.info(
            "auth.forgot_password.requested",
            user_id=str(user.id),
            challenge_id=result["challenge_id"],
        )

    return {"message": "If your email is registered, a reset link has been sent"}


# ---------------------------------------------------------------------------
# POST /auth/reset-password
# ---------------------------------------------------------------------------


@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordBody,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    """Consume a password-reset token and update the user's password."""
    redis_client = None
    async for r in get_redis():
        redis_client = r
        break
    if redis_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable",
        )

    challenge_svc = AuthChallengeService(redis_client)
    try:
        payload = await challenge_svc.verify_challenge(
            challenge_type="password_reset_email",
            challenge_id=body.challenge_id,
            token=body.token,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid challenge",
        )

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled",
        )

    user.password_hash = hash_password(body.new_password)
    db.commit()

    logger.info("auth.password.reset", user_id=user_id)

    return ApiResponse(data={"message": "Password reset successfully"})


# ---------------------------------------------------------------------------
# POST /auth/change-password
# ---------------------------------------------------------------------------


@router.post("/change-password")
def change_password(
    body: ChangePasswordBody,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    """Change password for the authenticated user."""
    if not current_user.password_hash or not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前密码错误",
        )

    current_user.password_hash = hash_password(body.new_password)
    db.commit()

    logger.info("auth.password.changed", user_id=str(current_user.id))

    return ApiResponse(data={"message": "Password changed successfully"})


# ---------------------------------------------------------------------------
# POST /auth/phone-register
# ---------------------------------------------------------------------------


@router.post(
    "/phone-register",
    response_model=ApiResponse[TokenResponse],
    status_code=status.HTTP_201_CREATED,
)
def phone_register(
    body: PhoneRegisterBody,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[TokenResponse]:
    """Register a new user with phone + password + invite code.

    Username is auto-generated as 'u_' + random hex (collision-retried once).
    password_hash stays NOT NULL (spec §2.3).
    """
    # Check phone registration is allowed
    cfg_svc = AuthConfigService(db)
    if not cfg_svc.is_phone_registration_allowed():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Phone registration is not enabled",
        )

    # Check phone uniqueness
    existing = db.query(User).filter(User.phone == body.phone).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Phone number already registered",
        )

    # Validate invite
    invite = _validate_invite(body.invite_code, db)

    # Auto-generate username: u_{hex8}, retry once on collision
    def _gen_username() -> str:
        return "u_" + secrets.token_hex(4)

    username = _gen_username()
    if db.query(User).filter(User.username == username).first() is not None:
        username = _gen_username()

    user = User(
        email=f"phone_{body.phone.lstrip('+').replace(' ', '')}@phone.prism.local",
        username=username,
        password_hash=hash_password(body.password),
        role="user",
        phone=body.phone,
    )
    db.add(user)
    db.flush()

    # Consume invite
    invite.used_count += 1
    db.flush()

    # Audit
    audit = AuditLog(
        id=generate_uuid(),
        user_id=user.id,
        action="user.register.phone",
        resource_type="user",
        resource_id=user.id,
        details={"invite_code_id": invite.id, "phone": body.phone},
        created_at=datetime.now(timezone.utc),
    )
    db.add(audit)

    resp = _issue_tokens_response(response, user, db, action="user.login.phone")
    db.commit()

    logger.info("auth.phone.registered", user_id=user.id, phone=body.phone)

    return resp


# ---------------------------------------------------------------------------
# POST /auth/phone-login
# ---------------------------------------------------------------------------


@router.post("/phone-login", response_model=ApiResponse[TokenResponse])
def phone_login(
    body: PhoneLoginBody,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[TokenResponse]:
    """Authenticate with phone + password."""
    _invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="手机号或密码错误",
    )

    user = db.query(User).filter(User.phone == body.phone).first()
    if user is None:
        raise _invalid
    if not verify_password(body.password, user.password_hash):
        raise _invalid
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用，请联系管理员",
        )

    resp = _issue_tokens_response(response, user, db, action="user.login.phone")
    db.commit()

    logger.info("auth.phone.login", user_id=user.id)

    return resp


# ===========================================================================
# Google OAuth endpoints (Task B)
# ===========================================================================

_OAUTH_PENDING_KEY_PREFIX = "auth:oauth_pending:"
_OAUTH_PENDING_TTL = 600  # 10 minutes


async def _get_redis_client():
    """Retrieve async Redis client or raise 503."""
    redis_client = None
    async for r in get_redis():
        redis_client = r
        break
    if redis_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis unavailable",
        )
    return redis_client


# ---------------------------------------------------------------------------
# GET /auth/google/authorize
# ---------------------------------------------------------------------------


@router.get("/google/authorize")
async def google_authorize(
    next: str = Query(default="", alias="next"),
) -> RedirectResponse:
    """Redirect the user to Google's consent screen.

    Query params:
      next  — optional URL to redirect to after login (carried through state)

    Responses:
      302  — redirect to Google consent URL
      503  — Google OAuth not configured
    """
    google_svc = GoogleOAuthService(settings, redis_client=None)
    if not google_svc.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth 未配置",
        )

    redis_client = await _get_redis_client()
    google_svc = GoogleOAuthService(settings, redis_client=redis_client)
    authorize_url, _state = await google_svc.build_authorize_url(next_url=next)

    logger.info("auth.google.authorize_redirecting")
    return RedirectResponse(url=authorize_url, status_code=302)


# ---------------------------------------------------------------------------
# GET /auth/google/callback
# ---------------------------------------------------------------------------


@router.get("/google/callback")
async def google_callback(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
) -> RedirectResponse:
    """Handle Google OAuth callback.

    Google redirects here with ?code=...&state=... (success) or ?error=... (denied).

    Branching after code exchange:
      Case 1 — user with matching google_id found → login directly
      Case 2 — user with matching email (no google_id) → merge account → login
      Case 3a — new email, allow_oauth_signup_without_invite=True → auto-create → login
      Case 3b — new email, invite required → store pending token → redirect frontend
    """
    import json as _json

    frontend_base = settings.FRONTEND_BASE_URL

    # Error from Google (e.g. user cancelled)
    if error:
        logger.warning("auth.google.callback_error", error=error)
        return RedirectResponse(
            url=f"{frontend_base}/Prism.html?auth_error={error}",
            status_code=302,
        )

    # Missing code or state
    if not code or not state:
        return RedirectResponse(
            url=f"{frontend_base}/Prism.html?auth_error=missing_code_or_state",
            status_code=302,
        )

    # Validate CSRF state (GETDEL — consume atomically)
    redis_client = await _get_redis_client()
    google_svc = GoogleOAuthService(settings, redis_client=redis_client)

    state_payload = await google_svc.consume_state(state)
    if state_payload is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSRF 校验失败：state 无效或已过期",
        )

    # Exchange authorization code for id_token + claims
    try:
        google_info = await google_svc.exchange_code(code)
    except ValueError as exc:
        logger.warning("auth.google.exchange_failed", error=str(exc))
        return RedirectResponse(
            url=f"{frontend_base}/Prism.html?auth_error=token_exchange_failed",
            status_code=302,
        )

    google_id: str = google_info["google_id"]
    email: str = google_info["email"]
    email_verified: bool = google_info["email_verified"]
    name: str = google_info.get("name", "")

    # --- Case 1: existing user with matching google_id ---
    user = db.query(User).filter(User.google_id == google_id).first()
    if user is not None:
        if not user.is_active:
            return RedirectResponse(
                url=f"{frontend_base}/Prism.html?auth_error=account_disabled",
                status_code=302,
            )
        redirect_resp = RedirectResponse(
            url=f"{frontend_base}/Prism.html#access_token="
                + _build_login_hash(user, db),
            status_code=302,
        )
        _set_refresh_cookie(redirect_resp, create_refresh_token(user.id))
        _write_audit(db, user.id, "user.login.google")
        db.commit()
        logger.info("auth.google.login.existing", user_id=user.id)
        return redirect_resp

    # --- Case 2: user exists by email but no google_id ---
    user = db.query(User).filter(User.email == email).first()
    if user is not None:
        # Gate account merge on email_verified to prevent takeover
        if not email_verified:
            return RedirectResponse(
                url=f"{frontend_base}/Prism.html?auth_error=email_not_verified",
                status_code=302,
            )
        if not user.is_active:
            return RedirectResponse(
                url=f"{frontend_base}/Prism.html?auth_error=account_disabled",
                status_code=302,
            )
        # Merge: set google_id + email_verified
        user.google_id = google_id
        user.email_verified = True
        db.flush()

        redirect_resp = RedirectResponse(
            url=f"{frontend_base}/Prism.html#access_token="
                + _build_login_hash(user, db),
            status_code=302,
        )
        _set_refresh_cookie(redirect_resp, create_refresh_token(user.id))
        _write_audit(db, user.id, "user.login.google.merge")
        db.commit()
        logger.info("auth.google.login.merged", user_id=user.id)
        return redirect_resp

    # --- Case 3: brand-new email ---
    cfg_svc = AuthConfigService(db)
    allow_signup = cfg_svc.is_oauth_signup_without_invite()

    if allow_signup:
        # Case 3a: auto-create user
        username = _generate_unique_username(email, db)
        new_user = User(
            email=email,
            username=username,
            password_hash=secrets.token_hex(32),  # unusable random hash (spec §2.3)
            role="user",
            google_id=google_id,
            email_verified=email_verified,
        )
        db.add(new_user)
        db.flush()

        redirect_resp = RedirectResponse(
            url=f"{frontend_base}/Prism.html#access_token="
                + _build_login_hash(new_user, db),
            status_code=302,
        )
        _set_refresh_cookie(redirect_resp, create_refresh_token(new_user.id))
        _write_audit(db, new_user.id, "user.register.google")
        db.commit()
        logger.info("auth.google.register.auto", user_id=new_user.id)
        return redirect_resp

    else:
        # Case 3b: invite required — store pending token, redirect frontend
        tmp_token = secrets.token_urlsafe(32)
        pending_data = _json.dumps({
            "google_id": google_id,
            "email": email,
            "email_verified": email_verified,
            "name": name,
        })
        await redis_client.setex(
            f"{_OAUTH_PENDING_KEY_PREFIX}{tmp_token}",
            _OAUTH_PENDING_TTL,
            pending_data,
        )

        # Audit (user_id=None — not yet created)
        _write_audit(db, None, "user.oauth.pending", details={"google_id": google_id, "email": email})
        db.commit()

        logger.info("auth.google.pending", email_domain=email.split("@")[-1])
        return RedirectResponse(
            url=f"{frontend_base}/Prism.html?auth_pending={tmp_token}",
            status_code=302,
        )


# ---------------------------------------------------------------------------
# POST /auth/google/complete
# ---------------------------------------------------------------------------


@router.post("/google/complete", response_model=ApiResponse[TokenResponse])
async def google_complete(
    body: GoogleCompleteBody,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[TokenResponse]:
    """Complete Google OAuth signup when an invite code is required.

    Flow:
      1. GETDEL auth:oauth_pending:{tmp_token} from Redis
      2. Validate invite code (same as register flow)
      3. Create user (google_id + email + email_verified=True)
      4. Consume invite + write audit
      5. Return TokenResponse + set refresh cookie
    """
    import json as _json

    redis_client = await _get_redis_client()

    # GETDEL the pending token
    pending_key = f"{_OAUTH_PENDING_KEY_PREFIX}{body.tmp_token}"
    raw = await redis_client.getdel(pending_key)
    if raw is None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="链接已失效，请重新使用 Google 登录",
        )

    try:
        google_info: dict = _json.loads(raw)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="链接已失效（数据损坏），请重新使用 Google 登录",
        )

    google_id: str = google_info["google_id"]
    email: str = google_info["email"]
    email_verified: bool = google_info.get("email_verified", False)

    # Validate invite code
    invite = _validate_invite(body.invite_code, db)

    # Uniqueness guard (race condition: another request may have registered same email)
    if db.query(User).filter(User.email == email).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该邮箱已注册，请直接登录",
        )
    if db.query(User).filter(User.google_id == google_id).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该 Google 账号已绑定其他用户，请直接登录",
        )

    username = _generate_unique_username(email, db)
    new_user = User(
        email=email,
        username=username,
        password_hash=secrets.token_hex(32),  # unusable random hash (spec §2.3)
        role="user",
        google_id=google_id,
        email_verified=email_verified,
    )
    db.add(new_user)
    db.flush()

    # Consume invite
    invite.used_count += 1
    db.flush()

    # Audit
    _write_audit(
        db,
        new_user.id,
        "user.register.google.invite",
        details={"invite_code_id": invite.id},
    )

    resp = _issue_tokens_response(response, new_user, db, action="user.login.google")
    db.commit()

    logger.info("auth.google.complete", user_id=new_user.id)
    return resp


# ---------------------------------------------------------------------------
# Google OAuth helper utilities
# ---------------------------------------------------------------------------


def _build_login_hash(user: User, db: Session) -> str:
    """Build the access_token fragment for the redirect URL.

    Returns the URL-encoded fragment string (just the token value).
    Hash-based redirect avoids access_token appearing in server logs.
    """
    access_token = create_access_token(user.id)
    # Append expires_in for the frontend
    expires_in = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    return f"{access_token}&expires_in={expires_in}"


def _write_audit(
    db: Session,
    user_id: Optional[str],
    action: str,
    details: Optional[dict] = None,
) -> None:
    """Insert an AuditLog row (user_id may be None for pre-registration events)."""
    audit = AuditLog(
        id=generate_uuid(),
        user_id=user_id,
        action=action,
        resource_type="user",
        resource_id=user_id,
        details=details or {},
        created_at=datetime.now(timezone.utc),
    )
    db.add(audit)
    db.flush()


def _generate_unique_username(email: str, db: Session) -> str:
    """Derive a username from the email local-part; retry once on collision."""
    local_part = email.split("@")[0]
    # Sanitise: keep only alphanum + underscore, cap at 40 chars
    import re as _re
    base = _re.sub(r"[^a-zA-Z0-9_]", "_", local_part)[:40] or "user"

    if db.query(User).filter(User.username == base).first() is None:
        return base

    # Collision — append short random suffix
    candidate = f"{base[:34]}_{secrets.token_hex(3)}"
    if db.query(User).filter(User.username == candidate).first() is None:
        return candidate

    # Second collision (very unlikely) — full random
    return f"u_{secrets.token_hex(6)}"
