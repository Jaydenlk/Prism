"""
Prism v2 — Session Pydantic Schemas (DOC-07 Task 7.1)

Schemas:
  CreateSessionRequest   — POST /sessions body
  UpdateSessionRequest   — PATCH /sessions/{id} body
  SessionResponse        — full session detail (with message_count + preview)
  SessionListResponse    — compact list item (PATCH /sessions list)
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    """Body for POST /sessions."""

    title: str | None = None
    config_snapshot: dict = {}  # optional initial config (model, provider …)


class UpdateSessionRequest(BaseModel):
    """Body for PATCH /sessions/{id}. All fields are optional."""

    title: str | None = None
    is_pinned: bool | None = None
    config_snapshot: dict | None = None


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class SessionResponse(BaseModel):
    """Full session detail returned by GET /sessions/{id} and POST /sessions."""

    model_config = {"from_attributes": True}

    id: str
    title: str | None
    status: str                    # "idle" | "running" | "queued"
    blocking_run_id: str | None
    config_snapshot: dict
    is_pinned: bool
    pinned_at: datetime | None
    im_channel: str | None
    im_chat_id: str | None
    message_count: int             # computed: total messages in this session
    last_message_preview: str | None  # text_preview of the most-recent message
    created_at: datetime
    updated_at: datetime


class SessionListResponse(BaseModel):
    """Compact session representation for list endpoints."""

    model_config = {"from_attributes": True}

    id: str
    title: str | None
    status: str
    is_pinned: bool
    last_message_preview: str | None
    updated_at: datetime
