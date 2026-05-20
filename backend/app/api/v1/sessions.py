"""
Prism v2 — Session & Message API Endpoints (DOC-07 Task 7.1 + 7.3)

Routes (all under /api/v1):
  GET    /sessions                          — paginated session list (pinned first)
  POST   /sessions                          — create a new empty session
  GET    /sessions/{session_id}             — session detail
  PATCH  /sessions/{session_id}             — update session (title / pin / config)
  DELETE /sessions/{session_id}             — delete session (cascades runs + messages)
  GET    /sessions/{session_id}/messages    — message list (supports incremental query)

  (v4 Task 7.3):
  GET    /sessions/{session_id}/stream      — SSE event stream (ticket auth + last_event_id)
  POST   /sessions/{session_id}/permission-answer — 用户回答 permission ask (ADR-064)

Incremental message query (ADR-060):
  ?after_sequence_no=N  — returns only messages with sequence_no > N
  ?limit=N              — max items to return (1–500, default 100)

SSE (ADR-063 / ADR-057):
  ?ticket=X             — 一次性 SSE ticket（不走 JWT，防 URL 泄漏）
  ?last_event_id=Y      — 断线重连补发 Y 之后的事件

Permission answer (ADR-064):
  校验 request_id 归属 → UPDATE permission_requests → RPUSH perm_answer:{request_id}

Ownership:
  All routes enforce user_id ownership via SessionService.get_session()
  which raises 404 for missing or foreign sessions (铁律 4).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.permission_request import PermissionRequest
from app.models.user import User
from app.schemas.common import ApiResponse, PagedResponse
from app.schemas.message import MessageResponse
from app.schemas.session import (
    CreateSessionRequest,
    SessionListResponse,
    SessionResponse,
    UpdateSessionRequest,
)
from app.services.session_service import SessionService
from app.services.sse_manager import SSEManager

import structlog
logger = structlog.get_logger()

router = APIRouter(prefix="/sessions", tags=["sessions"])

_MAX_MESSAGES_LIMIT = 500


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_session_response(
    svc: SessionService,
    session,  # SessionModel ORM instance
) -> SessionResponse:
    """
    Construct a full SessionResponse including computed fields
    (message_count, last_message_preview).
    """
    return SessionResponse(
        id=session.id,
        title=session.title,
        status=session.status,
        blocking_run_id=session.blocking_run_id,
        config_snapshot=session.config_snapshot or {},
        is_pinned=session.is_pinned,
        pinned_at=session.pinned_at,
        im_channel=session.im_channel,
        im_chat_id=session.im_chat_id,
        message_count=svc.get_message_count(session.id),
        last_message_preview=svc.get_last_message_preview(session.id),
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


# ---------------------------------------------------------------------------
# Session endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=ApiResponse[PagedResponse[SessionListResponse]])
def list_sessions(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> ApiResponse[PagedResponse[SessionListResponse]]:
    """
    Return the current user's sessions, pinned first, then by updated_at DESC.
    """
    svc = SessionService(db)
    sessions, total = svc.list_sessions(user.id, page=page, per_page=per_page)

    items = [
        SessionListResponse(
            id=s.id,
            title=s.title,
            status=s.status,
            is_pinned=s.is_pinned,
            last_message_preview=svc.get_last_message_preview(s.id),
            updated_at=s.updated_at,
        )
        for s in sessions
    ]

    paged = PagedResponse.from_query(items, total=total, page=page, per_page=per_page)
    return ApiResponse(data=paged)


@router.post("", response_model=ApiResponse[SessionResponse], status_code=201)
def create_session(
    data: CreateSessionRequest,
    user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> ApiResponse[SessionResponse]:
    """Create a new empty session for the current user."""
    svc = SessionService(db)
    session = svc.create_session(user.id, data)
    return ApiResponse(data=_build_session_response(svc, session))


@router.get("/{session_id}", response_model=ApiResponse[SessionResponse])
def get_session(
    session_id: str,
    user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> ApiResponse[SessionResponse]:
    """Return full detail for a single session owned by the current user."""
    svc = SessionService(db)
    session = svc.get_session(user.id, session_id)
    return ApiResponse(data=_build_session_response(svc, session))


@router.patch("/{session_id}", response_model=ApiResponse[SessionResponse])
def update_session(
    session_id: str,
    data: UpdateSessionRequest,
    user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> ApiResponse[SessionResponse]:
    """
    Update a session's title, pin state, or config_snapshot.

    Pinning rules:
      - False → True: sets pinned_at = now()
      - True → False: clears pinned_at
    """
    svc = SessionService(db)
    session = svc.update_session(user.id, session_id, data)
    return ApiResponse(data=_build_session_response(svc, session))


@router.delete("/{session_id}", status_code=204)
def delete_session(
    session_id: str,
    user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> None:
    """
    Delete a session and all its runs, messages, and queue items.

    ON DELETE CASCADE in the DB handles child records automatically.
    """
    svc = SessionService(db)
    svc.delete_session(user.id, session_id)
    # 204 No Content — no return body.


# ---------------------------------------------------------------------------
# Message endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/{session_id}/messages",
    response_model=ApiResponse[list[MessageResponse]],
)
def list_messages(
    session_id: str,
    after_sequence_no: Annotated[int | None, Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_MESSAGES_LIMIT)] = 100,
    user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> ApiResponse[list[MessageResponse]]:
    """
    Return messages for a session, ordered by sequence_no ASC.

    Incremental mode (SSE reconnect):
      ?after_sequence_no=N  — returns only messages with sequence_no > N.

    Limit is capped at 500 (?limit > 500 returns 422).
    """
    svc = SessionService(db)
    messages = svc.list_messages(
        user.id,
        session_id=session_id,
        after_sequence_no=after_sequence_no,
        limit=limit,
    )

    items = [
        MessageResponse(
            id=m.id,
            run_id=m.run_id,
            role=m.role,
            content=m.content if isinstance(m.content, list) else [m.content],
            text_preview=m.text_preview,
            sequence_no=m.sequence_no,
            created_at=m.created_at,
        )
        for m in messages
    ]

    return ApiResponse(data=items)


# ---------------------------------------------------------------------------
# v4 Task 7.3: SSE event stream (ADR-063 / ADR-057)
# ---------------------------------------------------------------------------

def _format_sse(payload: dict[str, Any]) -> str:
    """格式化单条 SSE 事件为 text/event-stream 协议格式。"""
    event_id = payload.get("id", "")
    event_name = payload.get("event", "message")
    data = payload.get("data", {})
    return f"id: {event_id}\nevent: {event_name}\ndata: {json.dumps(data)}\n\n"


@router.get("/{session_id}/stream")
async def session_stream(
    session_id: str,
    ticket: str = Query(..., description="一次性 SSE ticket（DOC-06 ADR-057）"),
    last_event_id: str | None = Query(
        None, description="断线重连时补发此 ID 之后的事件"
    ),
    db: Annotated[Session, Depends(get_db)] = None,
) -> StreamingResponse:
    """
    v4 SSE 事件流端点（ADR-063 + ADR-057）。

    认证：用 SSE ticket（一次性，60s TTL），不走 JWT Bearer。
    断线重连：通过 last_event_id 从 Redis Stream 补发历史事件。
    Tab 限制：每 session 最多 3 个并发 SSE 连接（ADR-063）。

    SSE 事件格式：
      id: {event_uuid}
      event: {event_name}
      data: {json}
    """
    # 1. 消费 ticket（atomic GETDEL，防重放）
    from app.services.sse_ticket_service import SSETicketService
    import redis.asyncio as aioredis

    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=False)
    ticket_svc = SSETicketService(redis_client, settings)

    try:
        user_id = await ticket_svc.verify_and_consume(ticket, session_id)
    except HTTPException:
        raise
    finally:
        # 消费后立即关闭 ticket 验证专用连接（SSEManager 自己管理连接）
        await redis_client.aclose()

    # 2. 校验 session 归属（铁律 4）
    svc = SessionService(db)
    svc.get_session(user_id, session_id)  # 不存在/不归属 → 404

    # 3. 占连接槽（多 tab 限制）
    sse = SSEManager(settings.REDIS_URL)
    acquired = await sse.acquire_conn_slot(session_id)
    if not acquired:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many concurrent SSE connections for this session (max 3)",
        )

    async def event_gen():
        """异步 SSE 事件生成器。"""
        try:
            # 4. 补发历史事件（若提供 last_event_id）
            if last_event_id:
                backfill = await sse.backfill_since(session_id, last_event_id)
                for evt in backfill:
                    yield _format_sse(evt)

            # 5. 实时订阅 Redis pub/sub
            pubsub = await sse.start_subscribe_async(session_id)
            try:
                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    raw = message.get("data", b"")
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8", errors="replace")
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    yield _format_sse(payload)
            finally:
                await pubsub.unsubscribe(f"sse:{session_id}")
                await pubsub.aclose()
        finally:
            await sse.release_conn_slot(session_id)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# v4 Task 7.3: permission-answer 端点 (ADR-064)
# ---------------------------------------------------------------------------

class PermissionAnswerRequest(BaseModel):
    """前端用户回答 permission ask 请求体。"""

    request_id: str
    decision: str  # "allow" | "deny"

    @field_validator("decision")
    @classmethod
    def decision_must_be_valid(cls, v: str) -> str:
        if v not in ("allow", "deny"):
            raise ValueError("decision must be 'allow' or 'deny'")
        return v


@router.post(
    "/{session_id}/permission-answer",
    status_code=200,
)
async def permission_answer(
    session_id: str,
    body: PermissionAnswerRequest,
    user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> dict[str, Any]:
    """
    v4 新增（ADR-064）：用户回答 permission ask。

    流程：
      1. 校验 request_id 属于当前用户的 session（铁律 4）
      2. UPDATE permission_requests SET status='answered', decision=X, answered_at=now()
      3. RPUSH perm_answer:{request_id} {decision} → 触发子进程 BLPOP 返回
      4. 写 audit_log: permission.answered

    Redis key 格式（ADR-028 固定）：perm_answer:{request_id}
    """
    import redis.asyncio as aioredis

    # 校验 session 归属（铁律 4）
    svc = SessionService(db)
    svc.get_session(user.id, session_id)

    # 查找 permission_request（校验归属）
    req: PermissionRequest | None = (
        db.query(PermissionRequest)
        .filter(
            PermissionRequest.request_id == body.request_id,
            PermissionRequest.user_id == user.id,
        )
        .first()
    )
    if req is None or req.run.session_id != session_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission request not found",
        )
    if req.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Permission request already {req.status}",
        )

    # 更新 permission_requests
    req.status = "answered"
    req.decision = body.decision
    req.answered_at = datetime.now(timezone.utc)
    db.flush()

    # 写 audit_log
    from app.models.audit import AuditLog
    log = AuditLog(
        user_id=str(user.id),
        action="permission.answered",
        resource_type="permission_request",
        resource_id=req.id,
        details={"request_id": body.request_id, "decision": body.decision},
        created_at=datetime.now(timezone.utc),
    )
    db.add(log)
    db.commit()

    # RPUSH perm_answer:{request_id} {decision}（key 格式 ADR-028 固定，不可变）
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await redis_client.rpush(f"perm_answer:{body.request_id}", body.decision)
    finally:
        await redis_client.aclose()

    logger.info(
        "permission.answered",
        request_id=body.request_id,
        user_id=str(user.id),
        decision=body.decision,
    )

    return {"success": True}


# ---------------------------------------------------------------------------
# v4 Task 7.3: question-answer 端点
# ---------------------------------------------------------------------------

class QuestionAnswerRequest(BaseModel):
    """前端用户回答 question ask 请求体。"""

    request_id: str
    answers: dict


@router.post(
    "/{session_id}/question-answer",
    status_code=200,
)
async def question_answer(
    session_id: str,
    body: QuestionAnswerRequest,
    user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> dict[str, Any]:
    """
    用户回答 question ask。

    流程：
      1. 校验 session 归属（铁律 4）
      2. RPUSH ask:question:{request_id} {answers_json} → 触发子进程 BLPOP 返回

    Redis key 格式：ask:question:{request_id}
    """
    import redis.asyncio as aioredis

    svc = SessionService(db)
    svc.get_session(user.id, session_id)

    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await redis_client.rpush(
            f"ask:question:{body.request_id}",
            json.dumps(body.answers),
        )
    finally:
        await redis_client.aclose()

    logger.info(
        "question.answered",
        request_id=body.request_id,
        user_id=str(user.id),
    )

    return {"success": True}


# ---------------------------------------------------------------------------
# Fork endpoint
# ---------------------------------------------------------------------------


@router.post("/{session_id}/fork", response_model=ApiResponse[SessionResponse], status_code=201)
def fork_session(
    session_id: str,
    user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> ApiResponse[SessionResponse]:
    from app.models.message import Message
    from app.models.base import generate_uuid
    from app.models.session import Session as SessionModel

    svc = SessionService(db)
    source = svc.get_session(user.id, session_id)

    forked = SessionModel(
        user_id=user.id,
        title=f"{source.title} (fork)" if source.title else "Forked session",
        status="idle",
        config_snapshot=dict(source.config_snapshot or {}),
        is_pinned=False,
    )
    db.add(forked)
    db.flush()

    source_messages = (
        db.query(Message)
        .filter(Message.session_id == source.id)
        .order_by(Message.sequence_no)
        .all()
    )
    for m in source_messages:
        db.add(Message(
            id=generate_uuid(),
            session_id=forked.id,
            run_id=None,
            role=m.role,
            content=m.content,
            text_preview=m.text_preview,
            sequence_no=m.sequence_no,
            is_skill_context=m.is_skill_context,
            skill_name=m.skill_name,
            created_at=m.created_at,
        ))

    db.commit()
    db.refresh(forked)

    logger.info("session.forked", source_id=session_id, forked_id=forked.id, user_id=str(user.id))
    return ApiResponse(data=_build_session_response(svc, forked))
