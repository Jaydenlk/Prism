"""
Prism v2 — Admin API Endpoints (DOC-06 Task 6.2)

All routes require the 'admin' role (via require_admin dependency).

Routes (all under /api/v1):
  GET    /admin/users              — paginated user list
  PATCH  /admin/users/{user_id}    — update user role (cannot demote self)
  POST   /admin/invite-codes       — generate a new invite code
  GET    /admin/invite-codes       — list all invite codes
  DELETE /admin/invite-codes/{id}  — revoke an invite code
  GET    /admin/usage              — global usage statistics
  GET    /admin/audit-logs         — paginated audit log query

ADR-059: Admin endpoints are guarded at router level using FastAPI
         router-level dependencies so every route inherits require_admin
         without repeating the dependency in each function signature.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.models.audit import AuditLog
from app.models.run import Run
from app.models.user import User, InviteCode
from app.schemas.common import ApiResponse, PagedResponse
from app.schemas.invite import CreateInviteCodeRequest, InviteCodeResponse
from app.schemas.user import UpdateUserRoleRequest, UserListResponse
from app.services.invite_service import InviteService

logger = logging.getLogger(__name__)

# All admin routes require admin role at router level (ADR-059)
router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _user_to_response(user: User) -> UserListResponse:
    return UserListResponse(
        id=str(user.id),
        email=user.email,
        username=user.username,
        role=user.role,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


# ---------------------------------------------------------------------------
# GET /admin/users
# ---------------------------------------------------------------------------


@router.get("/users", response_model=ApiResponse[list[UserListResponse]])
def list_users(
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[UserListResponse]]:
    """Return all users ordered by creation date (newest first).

    Admin-only. Returns full user list without pagination for Phase 1
    (user counts are expected to be small in self-hosted deployments).
    """
    users = db.query(User).order_by(User.created_at.desc()).all()
    return ApiResponse(data=[_user_to_response(u) for u in users])


# ---------------------------------------------------------------------------
# PATCH /admin/users/{user_id}
# ---------------------------------------------------------------------------


@router.patch(
    "/users/{user_id}",
    response_model=ApiResponse[UserListResponse],
)
def update_user_role(
    user_id: str,
    data: UpdateUserRoleRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[UserListResponse]:
    """Update a user's role (admin ↔ user).

    Self-demotion is blocked: an admin cannot change their own role to
    prevent accidentally locking out all admins.

    Error codes:
      - 400: attempting to modify own role
      - 404: user not found
    """
    if user_id == str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot modify your own role",
        )

    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    old_role = target.role
    target.role = data.role
    db.commit()

    logger.info(
        "admin.user.role_changed",
        extra={
            "admin_id": str(current_user.id),
            "target_user_id": user_id,
            "old_role": old_role,
            "new_role": data.role,
        },
    )

    return ApiResponse(data=_user_to_response(target))


# ---------------------------------------------------------------------------
# POST /admin/invite-codes
# ---------------------------------------------------------------------------


@router.post(
    "/invite-codes",
    response_model=ApiResponse[InviteCodeResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_invite_code(
    data: CreateInviteCodeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[InviteCodeResponse]:
    """Generate a new invite code.

    ``max_uses`` defaults to 1; ``expires_at`` = None means never-expiring.
    The code is returned in plain-text (PRISM-XXXXXXXX format) — it is not
    hashed because admins need to share it with invitees.
    """
    svc = InviteService(db)
    invite = svc.create(created_by=str(current_user.id), data=data)
    db.commit()

    logger.info(
        "admin.invite_code.created",
        extra={
            "admin_id": str(current_user.id),
            "invite_id": invite.id,
            "code_prefix": invite.code[:10],
            "max_uses": invite.max_uses,
        },
    )

    return ApiResponse(data=InviteCodeResponse.from_orm_model(invite))


# ---------------------------------------------------------------------------
# GET /admin/invite-codes
# ---------------------------------------------------------------------------


@router.get("/invite-codes", response_model=ApiResponse[list[InviteCodeResponse]])
def list_invite_codes(
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[InviteCodeResponse]]:
    """Return all invite codes, newest first, with computed is_valid field."""
    svc = InviteService(db)
    invites = svc.list_all()
    return ApiResponse(
        data=[InviteCodeResponse.from_orm_model(inv) for inv in invites]
    )


# ---------------------------------------------------------------------------
# DELETE /admin/invite-codes/{invite_id}
# ---------------------------------------------------------------------------


@router.delete("/invite-codes/{invite_id}")
def revoke_invite_code(
    invite_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    """Revoke an invite code by setting max_uses = used_count.

    After revocation the code is still visible in the list but is_valid=False.
    Raises 404 if the invite_id does not exist.
    """
    svc = InviteService(db)
    invite = svc.revoke(invite_id)
    db.commit()

    logger.info(
        "admin.invite_code.revoked",
        extra={"invite_id": invite_id, "code_prefix": invite.code[:10]},
    )

    return ApiResponse(data={"message": "Invite code revoked", "invite_id": invite_id})


# ---------------------------------------------------------------------------
# GET /admin/usage
# ---------------------------------------------------------------------------


@router.get("/usage", response_model=ApiResponse[dict])
def get_usage(
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    """Return global usage statistics aggregated from the runs table.

    Includes:
      - total_runs, total_input_tokens, total_output_tokens, total_cost_usd
      - per_provider breakdown (provider_id → token/cost totals)
      - daily trend for the last 30 days (date → {runs, input_tokens, output_tokens})
    """
    # --- Totals -----------------------------------------------------------
    totals = db.query(
        func.count(Run.id).label("total_runs"),
        func.coalesce(func.sum(Run.input_tokens), 0).label("total_input_tokens"),
        func.coalesce(func.sum(Run.output_tokens), 0).label("total_output_tokens"),
        func.coalesce(func.sum(Run.cost_usd), 0).label("total_cost_usd"),
    ).one()

    # --- Per-provider breakdown -------------------------------------------
    provider_rows = db.query(
        Run.provider_id,
        func.count(Run.id).label("runs"),
        func.coalesce(func.sum(Run.input_tokens), 0).label("input_tokens"),
        func.coalesce(func.sum(Run.output_tokens), 0).label("output_tokens"),
        func.coalesce(func.sum(Run.cost_usd), 0).label("cost_usd"),
    ).group_by(Run.provider_id).all()

    per_provider = [
        {
            "provider_id": row.provider_id,
            "runs": row.runs,
            "input_tokens": int(row.input_tokens),
            "output_tokens": int(row.output_tokens),
            "cost_usd": float(row.cost_usd),
        }
        for row in provider_rows
    ]

    # --- Daily trend (last 30 days) ---------------------------------------
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    daily_rows = db.query(
        func.date(Run.created_at).label("date"),
        func.count(Run.id).label("runs"),
        func.coalesce(func.sum(Run.input_tokens), 0).label("input_tokens"),
        func.coalesce(func.sum(Run.output_tokens), 0).label("output_tokens"),
    ).filter(
        Run.created_at >= thirty_days_ago
    ).group_by(
        func.date(Run.created_at)
    ).order_by(
        func.date(Run.created_at)
    ).all()

    daily_trend = [
        {
            "date": str(row.date),
            "runs": row.runs,
            "input_tokens": int(row.input_tokens),
            "output_tokens": int(row.output_tokens),
        }
        for row in daily_rows
    ]

    return ApiResponse(
        data={
            "total_runs": totals.total_runs,
            "total_input_tokens": int(totals.total_input_tokens),
            "total_output_tokens": int(totals.total_output_tokens),
            "total_cost_usd": float(totals.total_cost_usd),
            "per_provider": per_provider,
            "daily_trend_30d": daily_trend,
        }
    )


# ---------------------------------------------------------------------------
# GET /admin/audit-logs
# ---------------------------------------------------------------------------


@router.get("/audit-logs", response_model=ApiResponse[PagedResponse[dict]])
def get_audit_logs(
    db: Annotated[Session, Depends(get_db)],
    action: Optional[str] = Query(
        default=None,
        description="Prefix filter, e.g. 'harness.' to get all harness events",
    ),
    user_id: Optional[str] = Query(default=None, description="Filter by user_id"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
) -> ApiResponse[PagedResponse[dict]]:
    """Return paginated audit logs with optional filters.

    Supports:
      - action prefix filter (LIKE 'harness.%')
      - user_id exact filter
      - page / per_page pagination
    """
    query = db.query(AuditLog).order_by(AuditLog.created_at.desc())

    if action:
        query = query.filter(AuditLog.action.like(f"{action}%"))

    if user_id:
        query = query.filter(AuditLog.user_id == user_id)

    total: int = query.count()
    offset = (page - 1) * per_page
    rows = query.offset(offset).limit(per_page).all()

    items = [
        {
            "id": str(log.id),
            "user_id": str(log.user_id) if log.user_id else None,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": str(log.resource_id) if log.resource_id else None,
            "details": log.details,
            "ip_address": log.ip_address,
            "created_at": log.created_at.isoformat(),
        }
        for log in rows
    ]

    return ApiResponse(
        data=PagedResponse.from_query(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
        )
    )
