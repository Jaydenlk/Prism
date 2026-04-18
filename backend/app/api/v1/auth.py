"""
Prism v2 — Authentication API Endpoints (DOC-06 Task 6.1)

Routes (all under /api/v1):
  POST /auth/register   — new user registration (requires invite code)     [public]
  POST /auth/login      — email + password login                           [public]
  POST /auth/refresh    — exchange refresh cookie for new access token      [cookie]
  POST /auth/logout     — delete refresh_token cookie                       [bearer]
  GET  /auth/me         — return current user profile                       [bearer]
  POST /auth/sse-ticket — generate one-time SSE ticket (ADR-051)           [bearer]

ADR-051: SSE ticket replaces ?token=<JWT> in query string to prevent token
         leakage into browser history / Nginx access_log / Referer headers.

ADR-052: Refresh token stored as HttpOnly + Secure + SameSite=Lax cookie;
         no DB row — signature-based validation only.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RefreshResponse,
    RegisterRequest,
    SSETicketRequest,
    TokenResponse,
    UserResponse,
)
from app.schemas.common import ApiResponse
from app.services.auth_service import AuthService
from app.services.sse_ticket_service import SSETicketService

logger = logging.getLogger(__name__)

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
    return ApiResponse(data=UserResponse.model_validate(current_user))


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

    # Redis is not yet initialised in Phase 1 — SSETicketService is wired in
    # DOC-07 Task 7.3.  Import get_redis lazily so auth endpoints not using
    # the ticket still work without Redis.
    try:
        from app.core.dependencies import get_redis
        redis_client = next(get_redis())
    except NotImplementedError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis not yet initialised; SSE tickets unavailable until DOC-07 Task 7.3",
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
