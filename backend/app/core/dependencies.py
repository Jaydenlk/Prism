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

def get_redis():
    """
    Yield a Redis client.

    NOT YET IMPLEMENTED.
    Redis connection pool initialisation is deferred to DOC-03 / DOC-07
    (TaskScheduler + IM Gateway tasks) where the full pub/sub lifecycle is
    defined.  Importing this dependency before that wiring is complete will
    raise NotImplementedError.
    """
    raise NotImplementedError(
        "get_redis() is not yet initialised. "
        "Redis client setup is implemented in DOC-03 Task 3.1 / DOC-07 Task 7.1. "
        "Do not call this dependency until that Task is complete."
    )
    yield  # pragma: no cover — generator shape required by FastAPI


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

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

    user: User | None = db.get(User, user_id)
    if user is None:
        raise credentials_exc
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
