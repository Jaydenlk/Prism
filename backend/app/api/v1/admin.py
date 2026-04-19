"""
Prism v2 — Admin API Endpoints (DOC-06 Task 6.2 + DOC-09 Task 9.3 + DOC-12 Task 12.8)

All routes require the 'admin' role (via require_admin dependency at router
level — ADR-059 / ADR-083).

Routes (all under /api/v1):
  GET    /admin/users                    — paginated user list with search
  PATCH  /admin/users/{user_id}/role     — change user role (ADR-083 last-admin guard)
  DELETE /admin/users/{user_id}          — disable user (ADR-083 no-self guard)
  POST   /admin/invite-codes             — generate a new invite code
  GET    /admin/invite-codes             — list all invite codes
  DELETE /admin/invite-codes/{id}        — revoke an invite code
  GET    /admin/usage                    — global usage statistics (legacy)
  GET    /admin/audit-logs               — paginated audit log query (ADR-084)
  GET    /admin/audit-logs/export        — export audit logs (CSV)
  GET    /admin/stats/dashboard          — system stats dashboard (ADR-085)
  GET    /admin/alerts/config            — get current alert dispatcher config (ADR-120)
  PATCH  /admin/alerts/config            — update alert dispatcher config (ADR-120)

ADR-083: Admin permission boundaries
  1. Cannot demote the last admin (409)
  2. Cannot disable yourself (409)

ADR-084: audit-logs action param supports prefix matching (harness. etc.)

ADR-085: stats/dashboard returns SystemStatsResponse via AdminStatsService

ADR-120: AlertDispatcher severity routing; admin configures ALERT_IM_CHANNEL / ALERT_EMAIL
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user, get_redis, get_settings_dep, require_admin
from app.models.audit import AuditLog
from app.models.run import Run
from app.models.user import User, InviteCode
from app.schemas.admin import SystemStatsResponse
from app.schemas.audit import AuditLogQuery, AuditLogResponse
from app.schemas.common import ApiResponse, PagedResponse
from app.schemas.invite import CreateInviteCodeRequest, InviteCodeResponse
from app.schemas.user import UpdateUserRoleRequest, UserListResponse
from app.services.admin_stats_service import AdminStatsService
from app.services.audit_service import AuditService
from app.services.invite_service import InviteService

import structlog
logger = structlog.get_logger()

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
# GET /admin/users  (v4: pagination + search)
# ---------------------------------------------------------------------------


@router.get("/users", response_model=ApiResponse[PagedResponse[UserListResponse]])
def list_users(
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(default=1, ge=1, description="1-based page number"),
    page_size: int = Query(default=50, ge=1, le=200, description="Max 200 per page"),
    search: Optional[str] = Query(
        default=None,
        description="Partial match on email or username (case-insensitive)",
    ),
) -> ApiResponse[PagedResponse[UserListResponse]]:
    """Return paginated users, optionally filtered by email/username search.

    Admin-only.
    """
    q = db.query(User)
    if search:
        q = q.filter(
            or_(
                User.email.ilike(f"%{search}%"),
                User.username.ilike(f"%{search}%"),
            )
        )

    total: int = q.count()
    rows = (
        q.order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return ApiResponse(
        data=PagedResponse.from_query(
            items=[_user_to_response(u) for u in rows],
            total=total,
            page=page,
            per_page=page_size,
        )
    )


# ---------------------------------------------------------------------------
# PATCH /admin/users/{user_id}/role  (v4: last-admin guard ADR-083)
# ---------------------------------------------------------------------------


@router.patch(
    "/users/{user_id}/role",
    response_model=ApiResponse[UserListResponse],
)
def change_user_role(
    user_id: str,
    data: UpdateUserRoleRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[UserListResponse]:
    """Change a user's role.

    ADR-083 guards:
    - Cannot modify own role (400)
    - Cannot demote the last remaining active admin (409)
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

    # ADR-083: last-admin guard
    if target.role == "admin" and data.role != "admin":
        admin_count = (
            db.query(User)
            .filter(User.role == "admin", User.is_active.is_(True))
            .count()
        )
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot demote the last admin",
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
# Legacy PATCH /admin/users/{user_id} (kept for backward-compat — Task 6.2)
# ---------------------------------------------------------------------------


@router.patch(
    "/users/{user_id}",
    response_model=ApiResponse[UserListResponse],
    deprecated=True,
    summary="[Deprecated] Use PATCH /admin/users/{user_id}/role instead",
)
def update_user_role(
    user_id: str,
    data: UpdateUserRoleRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[UserListResponse]:
    """Kept for backward-compatibility.  Delegates to change_user_role logic."""
    return change_user_role(user_id, data, current_user, db)


# ---------------------------------------------------------------------------
# DELETE /admin/users/{user_id}  (v4: soft disable + no-self guard ADR-083)
# ---------------------------------------------------------------------------


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def disable_user(
    user_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Soft-disable a user (set is_active = False).

    ADR-083: cannot disable yourself (409).
    Raises 404 if user not found.
    """
    if str(current_user.id) == user_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot disable yourself",
        )

    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    target.is_active = False  # type: ignore[attr-defined]
    db.commit()

    logger.info(
        "admin.user.disabled",
        extra={
            "admin_id": str(current_user.id),
            "target_user_id": user_id,
        },
    )


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
# GET /admin/usage  (legacy global usage stats)
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
# GET /admin/audit-logs  (v4: severity + time range filters, ADR-084)
# ---------------------------------------------------------------------------


@router.get("/audit-logs", response_model=ApiResponse[PagedResponse[AuditLogResponse]])
def get_audit_logs(
    db: Annotated[Session, Depends(get_db)],
    action: Optional[str] = Query(
        default=None,
        description="Prefix filter, e.g. 'harness.' to get all harness events",
    ),
    user_id: Optional[str] = Query(default=None, description="Filter by user_id"),
    severity: Optional[str] = Query(
        default=None, description="Filter by severity (info/warning/error/critical)"
    ),
    start_time: Optional[datetime] = Query(
        default=None, description="Lower bound on created_at"
    ),
    end_time: Optional[datetime] = Query(
        default=None, description="Upper bound on created_at"
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> ApiResponse[PagedResponse[AuditLogResponse]]:
    """Return paginated audit logs with optional filters (ADR-084).

    Supports:
      - action prefix filter (LIKE 'harness.%')
      - user_id exact filter
      - severity filter (against details->>'severity')
      - start_time / end_time range filter
      - page / page_size pagination
    """
    q = AuditLogQuery(
        action=action,
        user_id=user_id,
        severity=severity,
        start_time=start_time,
        end_time=end_time,
        page=page,
        page_size=page_size,
    )
    svc = AuditService(db)
    rows, total = svc.query(q)

    items = [
        AuditLogResponse(
            id=str(log.id),
            user_id=str(log.user_id) if log.user_id else None,
            action=log.action,
            resource_type=log.resource_type,
            resource_id=str(log.resource_id) if log.resource_id else None,
            severity=(log.details or {}).get("severity", "info"),
            details=log.details or {},
            ip_address=log.ip_address,
            created_at=log.created_at,
        )
        for log in rows
    ]

    return ApiResponse(
        data=PagedResponse.from_query(
            items=items,
            total=total,
            page=q.page,
            per_page=q.page_size,
        )
    )


# ---------------------------------------------------------------------------
# GET /admin/audit-logs/export  (CSV only in Phase 1)
# ---------------------------------------------------------------------------


@router.get("/audit-logs/export")
def export_audit_logs(
    db: Annotated[Session, Depends(get_db)],
    fmt: str = Query(
        default="csv",
        alias="format",
        description="Export format: 'csv' (only csv supported in Phase 1)",
    ),
    action: Optional[str] = Query(default=None),
    user_id: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    start_time: Optional[datetime] = Query(default=None),
    end_time: Optional[datetime] = Query(default=None),
) -> Response:
    """Export audit logs as CSV (max 10 000 rows).

    Raises 400 if result set exceeds 10 000 rows — narrow the filter.
    """
    if fmt != "csv":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only 'csv' format is supported in Phase 1",
        )

    q = AuditLogQuery(
        action=action,
        user_id=user_id,
        severity=severity,
        start_time=start_time,
        end_time=end_time,
        page=1,
        page_size=200,  # page_size used for count only; export uses its own limit
    )
    svc = AuditService(db)
    content = svc.export_csv(q)

    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit_logs.csv"'},
    )


# ---------------------------------------------------------------------------
# GET /admin/stats/dashboard  (ADR-085)
# ---------------------------------------------------------------------------


@router.get("/stats/dashboard", response_model=SystemStatsResponse)
async def get_dashboard(
    db: Annotated[Session, Depends(get_db)],
    redis_client=Depends(get_redis),
    settings=Depends(get_settings_dep),
) -> SystemStatsResponse:
    """Return system-wide statistics for the admin dashboard (ADR-085).

    Includes:
      - 24h / 7d runs and cost
      - estimated cache savings (7d)
      - harness event distribution (24h)
      - active session / user counts
      - component health (Redis, PostgreSQL, Providers)
    """
    svc = AdminStatsService(db, redis_client, settings)
    return await svc.get_dashboard()


# ---------------------------------------------------------------------------
# Alert Dispatcher Config  (ADR-120 — DOC-12 Task 12.8)
# ---------------------------------------------------------------------------


class AlertConfigRequest(BaseModel):
    """
    PATCH /admin/alerts/config 请求体（ADR-120）。

    所有字段可选：仅传入需要更新的字段。
    Phase 1：更新写入进程内存（Settings 对象），重启后恢复 .env 值。
    """

    alert_im_channel: Optional[str] = None
    """IM 群告警频道，格式 '{platform}:{chat_id}'，如 'feishu:oc_xxx'。空字符串 = 禁用。"""

    alert_email: Optional[str] = None
    """告警收件人 email（逗号分隔多个）。空字符串 = 禁用。"""

    smtp_host: Optional[str] = None
    """SMTP 服务器地址。空字符串 = 禁用 email 告警。"""

    smtp_port: Optional[int] = None
    """SMTP 端口（默认 587，STARTTLS）。"""

    smtp_user: Optional[str] = None
    """SMTP 用户名。"""

    smtp_from: Optional[str] = None
    """发件人地址（默认 noreply@prism.local）。"""

    prism_base_url: Optional[str] = None
    """Prism 前端 base URL，用于生成 IM 消息中的告警详情链接。"""


class AlertConfigResponse(BaseModel):
    """GET /admin/alerts/config 返回体（ADR-120）。"""

    alert_im_channel: str
    alert_email: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_from: str
    prism_base_url: str


@router.get("/alerts/config", response_model=ApiResponse[AlertConfigResponse])
def get_alert_config(
    settings=Depends(get_settings_dep),
) -> ApiResponse[AlertConfigResponse]:
    """Return current AlertDispatcher configuration (ADR-120).

    Reflects the in-memory Settings values. Sensitive fields (SMTP_PASSWORD)
    are not returned.
    """
    return ApiResponse(
        data=AlertConfigResponse(
            alert_im_channel=settings.ALERT_IM_CHANNEL,
            alert_email=settings.ALERT_EMAIL,
            smtp_host=settings.SMTP_HOST,
            smtp_port=settings.SMTP_PORT,
            smtp_user=settings.SMTP_USER,
            smtp_from=settings.SMTP_FROM,
            prism_base_url=settings.PRISM_BASE_URL,
        )
    )


@router.patch("/alerts/config", response_model=ApiResponse[AlertConfigResponse])
def update_alert_config(
    body: AlertConfigRequest,
    settings=Depends(get_settings_dep),
) -> ApiResponse[AlertConfigResponse]:
    """Update AlertDispatcher configuration at runtime (ADR-120).

    Phase 1 strategy:
      - Applies changes to the in-memory Settings object immediately.
      - Changes are NOT persisted to .env — they reset on restart.
      - For permanent changes, update environment variables / .env and restart.

    Only provided (non-None) fields are updated.
    """
    _FIELD_MAP = {
        "alert_im_channel": "ALERT_IM_CHANNEL",
        "alert_email": "ALERT_EMAIL",
        "smtp_host": "SMTP_HOST",
        "smtp_port": "SMTP_PORT",
        "smtp_user": "SMTP_USER",
        "smtp_from": "SMTP_FROM",
        "prism_base_url": "PRISM_BASE_URL",
    }

    updated: list[str] = []
    for field_name, settings_attr in _FIELD_MAP.items():
        value = getattr(body, field_name, None)
        if value is not None:
            object.__setattr__(settings, settings_attr, value)
            updated.append(settings_attr)

    logger.info(
        "admin.alert_config.updated",
        extra={"updated_fields": updated},
    )

    return ApiResponse(
        data=AlertConfigResponse(
            alert_im_channel=settings.ALERT_IM_CHANNEL,
            alert_email=settings.ALERT_EMAIL,
            smtp_host=settings.SMTP_HOST,
            smtp_port=settings.SMTP_PORT,
            smtp_user=settings.SMTP_USER,
            smtp_from=settings.SMTP_FROM,
            prism_base_url=settings.PRISM_BASE_URL,
        )
    )
