"""
Prism v2 — FastAPI Shared Dependencies

All FastAPI route dependencies live here so routes stay thin.

Dependency graph
----------------
get_settings()   → cached Settings singleton (no DB)
get_db()         → re-exported from database.py (yields Session)
get_redis()      → placeholder — Redis client init is DOC-03 / DOC-07
get_current_user → parses Bearer JWT, looks up User row
require_admin    → wraps get_current_user, checks role == 'admin'
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import decode_token

if TYPE_CHECKING:
    from app.models.user import User

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def get_settings_dep() -> Settings:
    """Return the cached Settings singleton."""
    return get_settings()


# ---------------------------------------------------------------------------
# Database session (re-exported for convenience)
# ---------------------------------------------------------------------------

# ``get_db`` is already defined in database.py; re-export so callers only
# need to import from dependencies.
__all__ = [
    "get_db",
    "get_redis",
    "get_settings_dep",
    "get_current_user",
    "require_admin",
]

# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------

async def get_redis():
    """
    Yield an async Redis client (redis.asyncio.Redis).

    DOC-07 Task 7.3: Redis 依赖正式实装。
    使用 from_url() 连接 settings.REDIS_URL，每次请求创建独立连接并在结束后关闭。

    调用方：
      - SSE ticket verify / consume (SSETicketService)
      - permission-answer RPUSH (sessions.py)
      - HeartbeatMonitor 使用独立连接，不经过此依赖
    """
    import redis.asyncio as aioredis

    from app.core.config import settings as _settings

    client = aioredis.from_url(_settings.REDIS_URL, decode_responses=False)
    try:
        yield client
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

_sync_redis = None


def _get_sync_redis():
    global _sync_redis
    if _sync_redis is None:
        import redis as _redis_lib
        _sync_redis = _redis_lib.from_url(get_settings().REDIS_URL, decode_responses=False)
    return _sync_redis


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> "User":
    """
    Decode the Bearer JWT and return the corresponding User ORM row.

    Raises 401 if the token is missing, expired, or the user no longer exists.
    """
    from app.models.user import User  # local import avoids circular imports

    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        # Reject refresh tokens used as access tokens (ADR-052)
        if payload.get("type") != "access":
            raise credentials_exc
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exc
    except HTTPException:
        raise
    except Exception:
        raise credentials_exc

    # Check token blacklist (logout revocation)
    jti: str | None = payload.get("jti")
    if jti:
        _blacklisted = False
        try:
            _blacklisted = bool(_get_sync_redis().get(f"blacklist:{jti}"))
        except Exception:
            pass
        if _blacklisted:
            raise credentials_exc

    user: User | None = db.get(User, user_id)
    if user is None:
        raise credentials_exc
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is disabled",
        )
    return user


def require_admin(
    current_user: Annotated["User", Depends(get_current_user)],
) -> "User":
    """
    Verify the authenticated user holds the 'admin' role.

    Full RBAC is implemented in DOC-06 Task 6.1.  Until that Task is
    complete this dependency performs a simple role-string check.

    Raises 403 if the user is not an admin.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required.",
        )
    return current_user
