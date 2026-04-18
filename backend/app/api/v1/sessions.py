"""
Prism v2 — Session & Message API Endpoints (DOC-07 Task 7.1)

Routes (all under /api/v1):
  GET    /sessions                     — paginated session list (pinned first)
  POST   /sessions                     — create a new empty session
  GET    /sessions/{session_id}        — session detail
  PATCH  /sessions/{session_id}        — update session (title / pin / config)
  DELETE /sessions/{session_id}        — delete session (cascades runs + messages)
  GET    /sessions/{session_id}/messages — message list (supports incremental query)

Incremental message query (ADR-060):
  ?after_sequence_no=N  — returns only messages with sequence_no > N
  ?limit=N              — max items to return (1–500, default 100)

Ownership:
  All routes enforce user_id ownership via SessionService.get_session()
  which raises 404 for missing or foreign sessions (铁律 4).
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
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

logger = logging.getLogger(__name__)

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
