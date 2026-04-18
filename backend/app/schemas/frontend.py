"""
Prism v2 — Frontend Error Payload Schema (ADR-119, DOC-12 Task 12.7)

FrontendErrorPayload is used by POST /api/v1/frontend-errors.

Design:
  - No authentication required (allows unauthenticated errors, e.g. login page crashes)
  - IP-level rate limit handled in the endpoint (≤60/IP/min via Redis SETNX counter)
  - viewport field: raw "WxH" string, classified to mobile/tablet/desktop bucket
  - severity matches AuditLog action severity labels for Prometheus
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FrontendErrorPayload(BaseModel):
    """
    Payload reported by the frontend ErrorBoundary / window.onerror /
    unhandledrejection hooks (DOC-10 v4 ADR-095).

    Fields:
      message:    Required — short error message (max 500 chars enforced on write)
      stack:      Optional — JS stack trace (max 2000 chars enforced on write)
      name:       Optional — Error class name (e.g. "TypeError")
      url:        Optional — page URL where the error occurred
      user_agent: Optional — browser User-Agent string
      viewport:   Optional — "WIDTHxHEIGHT" string (e.g. "1440x900")
      user_id:    Optional — authenticated user UUID7 if known
      session_id: Optional — Prism session UUID7 if a chat session was active
      context:    Optional — arbitrary key-value pairs for debugging
      severity:   One of info/warning/error/critical (default: error)
      timestamp:  Optional — ISO 8601 string from the client
    """

    message: str = Field(..., description="Short error message")
    stack: str | None = Field(None, description="JS stack trace")
    name: str | None = Field(None, description="Error class name")
    url: str | None = Field(None, description="Page URL where the error occurred")
    user_agent: str | None = Field(None, description="Browser User-Agent")
    viewport: str | None = Field(
        None, description="Viewport size as 'WIDTHxHEIGHT'"
    )
    user_id: str | None = Field(None, description="Authenticated user UUID7 if known")
    session_id: str | None = Field(
        None, description="Prism session UUID7 if active"
    )
    context: dict = Field(default_factory=dict, description="Extra debug context")
    severity: Literal["info", "warning", "error", "critical"] = Field(
        "error", description="Error severity level"
    )
    timestamp: str | None = Field(
        None, description="ISO 8601 client-side timestamp"
    )
