"""
Prism v2 — Audit Service (DOC-09 Task 9.3)

Provides query and CSV export for audit_logs table.

ADR-084: action query parameter supports prefix matching so callers can
         filter on "harness." to get all Harness events, or on a more
         specific prefix like "harness.guardrail_" for guardrail events only.

Export cap: CSV export is limited to 10 000 rows; if the filtered result
exceeds this limit, the service raises HTTP 400 with an instructive message
so the caller can narrow the filter or paginate manually.
"""
from __future__ import annotations

import csv
import io
import json
import logging
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.schemas.audit import AuditLogQuery, AuditLogResponse

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_EXPORT_ROW_LIMIT = 10_000


class AuditService:
    """Query and export audit log entries."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _base_query(self, q: AuditLogQuery):
        """Build a filtered SQLAlchemy query from AuditLogQuery params."""
        stmt = self._db.query(AuditLog)

        if q.action:
            # ADR-084: prefix matching — LIKE 'harness.%'
            stmt = stmt.filter(AuditLog.action.like(f"{q.action}%"))

        if q.user_id:
            stmt = stmt.filter(AuditLog.user_id == q.user_id)

        # severity is stored in `details` or a dedicated column depending on
        # the model. The current AuditLog model (DOC-01 v4) does not have a
        # top-level severity column; it lives in the JSONB details field.
        # We filter on details->>'severity' when provided.
        if q.severity:
            stmt = stmt.filter(
                AuditLog.details["severity"].as_string() == q.severity
            )

        if q.start_time:
            stmt = stmt.filter(AuditLog.created_at >= q.start_time)

        if q.end_time:
            stmt = stmt.filter(AuditLog.created_at <= q.end_time)

        return stmt

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def query(self, q: AuditLogQuery) -> tuple[list[AuditLog], int]:
        """Return a page of audit logs and the total match count.

        Returns:
          (rows, total) — rows is a list of AuditLog ORM objects for the
          requested page; total is the count of all matching rows.
        """
        stmt = self._base_query(q)
        total: int = stmt.count()
        rows = (
            stmt.order_by(AuditLog.created_at.desc())
            .offset((q.page - 1) * q.page_size)
            .limit(min(q.page_size, 200))
            .all()
        )
        return rows, total

    def export_csv(self, q: AuditLogQuery) -> bytes:
        """Export matching audit logs as CSV bytes (UTF-8 BOM for Excel).

        Raises HTTP 400 if the filtered result set exceeds 10 000 rows.
        """
        stmt = self._base_query(q)
        total: int = stmt.count()

        if total > _EXPORT_ROW_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Export would return {total} rows which exceeds the "
                    f"{_EXPORT_ROW_LIMIT}-row limit. Narrow the filter or use pagination."
                ),
            )

        # Use a large page_size to fetch all matching rows
        rows = stmt.order_by(AuditLog.created_at.desc()).limit(_EXPORT_ROW_LIMIT).all()

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            ["id", "user_id", "action", "resource_type", "resource_id",
             "severity", "ip_address", "created_at", "details"]
        )
        for r in rows:
            severity = (r.details or {}).get("severity", "info")
            writer.writerow([
                r.id,
                r.user_id,
                r.action,
                r.resource_type,
                r.resource_id,
                severity,
                r.ip_address,
                r.created_at.isoformat() if r.created_at else "",
                json.dumps(r.details or {}),
            ])

        logger.info(
            "admin.audit_logs.exported",
            extra={"row_count": len(rows), "format": "csv"},
        )
        return buf.getvalue().encode("utf-8-sig")  # BOM for Excel compat
