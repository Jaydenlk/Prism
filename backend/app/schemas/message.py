"""
Prism v2 — Message Pydantic Schemas (DOC-07 Task 7.1)

Schemas:
  MessageResponse — GET /sessions/{id}/messages item
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class MessageResponse(BaseModel):
    """One message in a session's message list."""

    model_config = {"from_attributes": True}

    id: str
    run_id: str | None
    role: str                # "user" | "assistant" | "tool_use" | "tool_result" | "system"
    content: list[dict]      # PrismMessage.content JSON (list of block dicts)
    text_preview: str | None
    sequence_no: int
    created_at: datetime
