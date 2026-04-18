"""
Prism v2 — Audit Log Schemas (DOC-09 Task 9.3)

Request/response models for admin audit-log query and export.

ADR-084: action field supports prefix matching (e.g. "harness." matches all
         Harness events; "harness.guardrail_" matches guardrail events only).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AuditLogQuery(BaseModel):
    """Query parameters for GET /admin/audit-logs.

    action supports prefix matching: "harness." matches all harness.* events.
    """

    action: Optional[str] = Field(
        default=None,
        description="Prefix filter, e.g. 'harness.' or 'harness.guardrail_'",
    )
    user_id: Optional[str] = Field(default=None, description="Filter by user_id")
    severity: Optional[str] = Field(
        default=None, description="Filter by severity (info/warning/error/critical)"
    )
    start_time: Optional[datetime] = Field(
        default=None, description="Lower bound on created_at (inclusive)"
    )
    end_time: Optional[datetime] = Field(
        default=None, description="Upper bound on created_at (inclusive)"
    )
    page: int = Field(default=1, ge=1, description="1-based page number")
    page_size: int = Field(default=50, ge=1, le=200, description="Max 200 per page")


class AuditLogResponse(BaseModel):
    """Single audit log entry returned by the query API."""

    id: str
    user_id: Optional[str]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    severity: str
    details: dict
    ip_address: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
