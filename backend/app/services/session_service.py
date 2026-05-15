"""
Prism v2 — Session & Message Business Logic (DOC-07 Task 7.1)

All queries enforce user_id ownership filter (铁律 4).

Classes:
  SessionService — Session CRUD + message list
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import asc, desc, func
from sqlalchemy.orm import Session

from app.models.message import Message
from app.models.session import Session as SessionModel
from app.schemas.session import CreateSessionRequest, UpdateSessionRequest

if TYPE_CHECKING:
    pass

import structlog
logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# text_preview generator (DOC-07 Task 7.1, DOC-01 v4 §4.2 messages table rules)
# ---------------------------------------------------------------------------


def generate_text_preview(
    role: str,
    content: list[dict] | dict,
    tool_lookup: dict[str, str] | None = None,
    max_len: int = 200,
) -> str:
    """
    Generate a human-readable preview of a message.

    Rules (per DOC-01 v4 §4.2 messages table):
      - user message with tool_result_block → "[tool_result:{tool_name}] " + first text block[:200]
      - assistant message with tool_use_block → "[tool_use:{tool_name}] " + tool_input JSON[:200]
      - pure text → first text block[:200]
      - empty content → "[empty]"

    ``tool_lookup`` maps tool_use_id → tool_name (needed to resolve tool_result references).
    """
    if tool_lookup is None:
        tool_lookup = {}

    blocks: list[dict] = []
    if isinstance(content, list):
        blocks = content
    elif isinstance(content, dict):
        # Possibly a single block wrapped in a dict; normalise to list.
        blocks = [content]

    if not blocks:
        return "[empty]"

    if role == "user":
        # Check for tool_result blocks
        for block in blocks:
            if block.get("type") == "tool_result":
                tool_use_id = block.get("tool_use_id", "")
                tool_name = tool_lookup.get(tool_use_id, tool_use_id or "unknown")
                prefix = f"[tool_result:{tool_name}] "
                # Find first text content inside the tool_result or subsequent text block
                inner = block.get("content", [])
                if isinstance(inner, list):
                    for inner_block in inner:
                        if inner_block.get("type") == "text":
                            return (prefix + inner_block.get("text", ""))[:max_len]
                elif isinstance(inner, str):
                    return (prefix + inner)[:max_len]
                # Fallback: check remaining blocks for text
                for b in blocks:
                    if b.get("type") == "text":
                        return (prefix + b.get("text", ""))[:max_len]
                return prefix.rstrip()

    if role == "assistant":
        # Check for tool_use blocks
        for block in blocks:
            if block.get("type") == "tool_use":
                tool_name = block.get("name", "unknown")
                prefix = f"[tool_use:{tool_name}] "
                tool_input = block.get("input", {})
                try:
                    input_str = json.dumps(tool_input, ensure_ascii=False)
                except (TypeError, ValueError):
                    input_str = str(tool_input)
                return (prefix + input_str)[:max_len]

    # Pure text: find first text block
    for block in blocks:
        if block.get("type") == "text":
            text = block.get("text", "")
            return text[:max_len] if text else "[empty]"

    return "[empty]"


# ---------------------------------------------------------------------------
# SessionService
# ---------------------------------------------------------------------------


class SessionService:
    """Session CRUD + message list queries. All methods enforce user_id ownership."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Session CRUD
    # ------------------------------------------------------------------

    def list_sessions(
        self,
        user_id: str,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[SessionModel], int]:
        """
        Return paginated sessions for ``user_id``.

        Ordering:
          1. is_pinned=True first, ordered by pinned_at DESC
          2. remainder ordered by updated_at DESC

        Returns: (sessions, total_count)
        """
        base_q = self._db.query(SessionModel).filter(
            SessionModel.user_id == user_id
        )
        total = base_q.count()

        # Sort: pinned first, then by updated_at DESC.
        # SQLAlchemy renders NULL LAST for DESC nulls by default on Postgres.
        sessions = (
            base_q.order_by(
                desc(SessionModel.is_pinned),
                desc(SessionModel.pinned_at),
                desc(SessionModel.updated_at),
            )
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        return sessions, total

    def create_session(
        self,
        user_id: str,
        data: CreateSessionRequest,
    ) -> SessionModel:
        """Create and persist a new Session for ``user_id``."""
        session = SessionModel(
            user_id=user_id,
            title=data.title,
            status="idle",
            config_snapshot=data.config_snapshot,
            is_pinned=False,
        )
        self._db.add(session)
        self._db.commit()
        self._db.refresh(session)
        logger.info("session.created user_id=%s session_id=%s", user_id, session.id)
        return session

    def get_session(self, user_id: str, session_id: str) -> SessionModel:
        """
        Return the Session owned by ``user_id``.

        Raises 404 if the session does not exist or belongs to another user.
        """
        session = (
            self._db.query(SessionModel)
            .filter(
                SessionModel.id == session_id,
                SessionModel.user_id == user_id,
            )
            .first()
        )
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found.",
            )
        return session

    def update_session(
        self,
        user_id: str,
        session_id: str,
        data: UpdateSessionRequest,
    ) -> SessionModel:
        """
        Apply partial updates to a session.

        Pin logic:
          - is_pinned False→True: set pinned_at = now()
          - is_pinned True→False: clear pinned_at
        """
        session = self.get_session(user_id, session_id)

        if data.title is not None:
            session.title = data.title

        if data.is_pinned is not None:
            if data.is_pinned and not session.is_pinned:
                session.pinned_at = datetime.now(timezone.utc)
            elif not data.is_pinned and session.is_pinned:
                session.pinned_at = None
            session.is_pinned = data.is_pinned

        if data.config_snapshot is not None:
            session.config_snapshot = data.config_snapshot

        session.updated_at = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(session)
        return session

    def delete_session(self, user_id: str, session_id: str) -> None:
        """
        Delete the session and all child records.

        ON DELETE CASCADE in the DB handles runs, messages, queue_items.
        """
        session = self.get_session(user_id, session_id)
        self._db.delete(session)
        self._db.commit()
        logger.info("session.deleted user_id=%s session_id=%s", user_id, session_id)

    # ------------------------------------------------------------------
    # Computed fields helpers (used by API layer to build SessionResponse)
    # ------------------------------------------------------------------

    def get_message_count(self, session_id: str) -> int:
        """Return total number of messages for a session."""
        return (
            self._db.query(func.count(Message.id))
            .filter(Message.session_id == session_id)
            .scalar()
            or 0
        )

    def get_last_message_preview(self, session_id: str) -> str | None:
        """Return text_preview of the most-recent message (highest sequence_no)."""
        msg = (
            self._db.query(Message)
            .filter(Message.session_id == session_id)
            .order_by(desc(Message.sequence_no))
            .first()
        )
        return msg.text_preview if msg else None

    # ------------------------------------------------------------------
    # Message list
    # ------------------------------------------------------------------

    def list_messages(
        self,
        user_id: str,
        session_id: str,
        after_sequence_no: int | None = None,
        limit: int = 100,
    ) -> list[Message]:
        """
        Return messages for a session, optionally filtered by sequence_no.

        ``after_sequence_no``: if provided, only messages with
          sequence_no > after_sequence_no are returned (incremental / SSE
          reconnect use-case, per ADR-060).

        Ownership is verified via get_session() (铁律 4).
        """
        # Verify the session belongs to the user.
        self.get_session(user_id, session_id)

        q = self._db.query(Message).filter(Message.session_id == session_id)

        if after_sequence_no is not None:
            q = q.filter(Message.sequence_no > after_sequence_no)

        return q.order_by(asc(Message.sequence_no)).limit(limit).all()
