"""
Prism v2 — Frontend Error Reporting Endpoint (ADR-119, DOC-12 Task 12.7)

Route:
  POST /api/v1/frontend-errors   — receive JS error payload from the browser

Design decisions (ADR-119):
  - No authentication required: allows unauthenticated errors (e.g. login page
    crashes, network errors before JWT is issued).
  - IP-level rate limit: ≤60 requests/IP/minute via Redis SETNX counter with
    60-second TTL.  Returns 429 on exceed.
  - Payload size: message truncated to 500 chars; stack truncated to 2000 chars
    before writing to audit_logs.
  - Writes AuditLog(action="frontend.error", severity=payload.severity).
  - Increments prism_frontend_errors_total{severity, viewport} Prometheus counter.
  - Logs via structlog at appropriate level (error/warning/info/critical).
  - viewport is classified into mobile(<640) / tablet(<1024) / desktop(≥1024) /
    unknown (missing or unparseable).

Frontend integration (NOT in scope for this Task):
  - DOC-10 Task 10.3 (apiClient + ErrorBoundary) is responsible for calling
    this endpoint from the browser.
  - This Task only implements the Backend receiving endpoint.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_redis
from app.models.audit import AuditLog
from app.observability.metrics import prism_frontend_errors_total
from app.schemas.frontend import FrontendErrorPayload

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["observability"])

# ---------------------------------------------------------------------------
# Constants (ADR-119)
# ---------------------------------------------------------------------------

_RATE_LIMIT_MAX: int = 60          # requests per window
_RATE_LIMIT_WINDOW_SECS: int = 60  # window size in seconds
_RATE_LIMIT_KEY_PREFIX: str = "fe_err_rl:"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _classify_viewport(v: str | None) -> str:
    """Classify a 'WIDTHxHEIGHT' viewport string into a named bucket.

    Returns:
      "mobile"  — width < 640
      "tablet"  — 640 ≤ width < 1024
      "desktop" — width ≥ 1024
      "unknown" — missing or unparseable
    """
    if not v:
        return "unknown"
    try:
        w = int(v.split("x")[0])
        if w < 640:
            return "mobile"
        if w < 1024:
            return "tablet"
        return "desktop"
    except Exception:
        return "unknown"


def _get_client_ip(request: Request) -> str:
    """Extract the real client IP, respecting X-Forwarded-For from nginx."""
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/frontend-errors",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Report a frontend JavaScript error",
    description=(
        "Accepts a FrontendErrorPayload from the browser, stores it in "
        "audit_logs (action=frontend.error), increments the "
        "prism_frontend_errors_total Prometheus counter, and logs via "
        "structlog.  No authentication required (ADR-119).  IP rate-limited "
        "to 60 req/min to prevent abuse."
    ),
)
async def report_frontend_error(
    payload: FrontendErrorPayload,
    request: Request,
    db: Session = Depends(get_db),
    redis=Depends(get_redis),
) -> None:
    """
    Receive a frontend error report and persist it.

    Steps:
      1. Extract client IP and check rate limit (Redis SETNX counter).
      2. Classify viewport string into bucket.
      3. Write AuditLog row (action="frontend.error").
      4. Increment Prometheus counter.
      5. Emit structlog event at severity-appropriate level.
    """
    # ------------------------------------------------------------------
    # 1. IP rate limit (ADR-119)
    # ------------------------------------------------------------------
    client_ip = _get_client_ip(request)
    rate_key = f"{_RATE_LIMIT_KEY_PREFIX}{client_ip}"

    try:
        current: bytes | None = await redis.get(rate_key)
        count = int(current) if current else 0

        if count >= _RATE_LIMIT_MAX:
            logger.warning(
                "frontend.error.rate_limited",
                client_ip=client_ip,
                count=count,
                limit=_RATE_LIMIT_MAX,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Rate limit exceeded: max {_RATE_LIMIT_MAX} frontend "
                    f"error reports per {_RATE_LIMIT_WINDOW_SECS}s per IP."
                ),
            )

        # Increment; set TTL only on first request in window (SETNX pattern)
        pipe = redis.pipeline()
        pipe.incr(rate_key)
        pipe.expire(rate_key, _RATE_LIMIT_WINDOW_SECS, nx=True)
        await pipe.execute()

    except HTTPException:
        raise
    except Exception as exc:  # Redis unavailable — degrade gracefully
        logger.warning(
            "frontend.error.rate_limit_unavailable",
            error=str(exc),
            client_ip=client_ip,
        )
        # Continue without rate-limit enforcement when Redis is down

    # ------------------------------------------------------------------
    # 2. Classify viewport
    # ------------------------------------------------------------------
    viewport_bucket = _classify_viewport(payload.viewport)

    # ------------------------------------------------------------------
    # 3. Write AuditLog
    # ------------------------------------------------------------------
    audit_entry = AuditLog(
        user_id=payload.user_id,
        action="frontend.error",
        resource_type="frontend",
        resource_id=payload.session_id,
        details={
            "message": (payload.message or "")[:500],
            "stack": (payload.stack or "")[:2000],
            "name": payload.name,
            "url": payload.url,
            "viewport": payload.viewport,
            "viewport_bucket": viewport_bucket,
            "severity": payload.severity,
            "context": payload.context,
            "timestamp": payload.timestamp,
        },
        ip_address=client_ip,
        created_at=datetime.now(tz=timezone.utc),
    )
    db.add(audit_entry)
    db.commit()

    # ------------------------------------------------------------------
    # 4. Prometheus counter
    # ------------------------------------------------------------------
    prism_frontend_errors_total.labels(
        severity=payload.severity,
        viewport=viewport_bucket,
    ).inc()

    # ------------------------------------------------------------------
    # 5. Structlog event (severity-appropriate level)
    # ------------------------------------------------------------------
    log_extra = {
        "severity": payload.severity,
        "viewport": viewport_bucket,
        "url": payload.url,
        "user_id": payload.user_id,
        "session_id": payload.session_id,
        "error_name": payload.name,
        "client_ip": client_ip,
    }

    if payload.severity == "critical":
        logger.critical("frontend.error.reported", **log_extra)
    elif payload.severity == "error":
        logger.error("frontend.error.reported", **log_extra)
    elif payload.severity == "warning":
        logger.warning("frontend.error.reported", **log_extra)
    else:
        logger.info("frontend.error.reported", **log_extra)
