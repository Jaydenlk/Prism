"""
Prism v2 — Structured logging initializer (ADR-118, DOC-12 Task 12.6)

Uses structlog with:
  - contextvars integration for automatic run_id / session_id / user_id binding
  - JSON renderer (production) / ConsoleRenderer (development)
  - ISO 8601 timestamps
  - Stack-trace and exception formatting
  - {domain}.{action} event name convention

Public API
----------
init_logging(level, dev_mode)          — call once in FastAPI lifespan
bind_request_context(request_id, user_id)  — call in HTTP middleware
clear_contextvars()                    — call after each request
bind_run_context(run_id, session_id, user_id, agent_type)  — QueryEngine
StructlogRequestMiddleware             — Starlette ASGI middleware

Logging-level convention (ADR-118):
  DEBUG    stream internals (message_complete counts, not text_delta)
  INFO     lifecycle (run.started / run.completed / tool.invoked / callback.received)
  WARNING  degradation (callback.server_error, retrying, heartbeat.stale)
  ERROR    failures (run.failed / tool.exception)
  CRITICAL crash (subprocess.crashed, unhandled exception)
"""
from __future__ import annotations

import logging
import uuid
from typing import Awaitable, Callable

import structlog
from structlog.contextvars import (
    bind_contextvars,
    clear_contextvars as _clear_contextvars,
    merge_contextvars,
)
from app.observability.masking import structlog_masker


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def bind_request_context(
    *,
    request_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """Bind HTTP-request-level fields to the structlog contextvars store.

    Must be called inside the ASGI request scope (i.e. inside middleware or
    a route handler).  The values are automatically injected into every log
    record emitted during the same asyncio Task.

    Args:
        request_id: Unique identifier for this HTTP request (UUID4 string).
                    Generated automatically if *None*.
        user_id:    Authenticated user UUID7 extracted from the JWT token.
                    May be ``None`` for unauthenticated endpoints.
    """
    ctx: dict[str, str] = {
        "request_id": request_id or str(uuid.uuid4()),
    }
    if user_id is not None:
        ctx["user_id"] = user_id
    bind_contextvars(**ctx)


def clear_contextvars() -> None:
    """Remove all structlog contextvars bound in this asyncio Task.

    Call once per HTTP request (in the *finally* block of the middleware)
    to prevent context leakage between concurrent requests.
    """
    _clear_contextvars()


def bind_run_context(
    *,
    run_id: str,
    session_id: str,
    user_id: str,
    agent_type: str = "general",
    trace_id: str | None = None,
) -> None:
    """Bind executor-run-level fields to structlog contextvars.

    Call at the start of ``QueryEngine.run()`` so that every log record
    emitted during the run automatically contains run_id / session_id /
    user_id / agent_type without explicit keyword arguments.

    Args:
        run_id:      Run UUID7 (corresponds to ``runs`` table PK).
        session_id:  Session UUID7.
        user_id:     User UUID7.
        agent_type:  Agent type string (default ``"general"``).
        trace_id:    W3C traceparent string (optional, from OTel context).
    """
    ctx: dict[str, str] = {
        "run_id": run_id,
        "session_id": session_id,
        "user_id": user_id,
        "agent_type": agent_type,
    }
    if trace_id is not None:
        ctx["trace_id"] = trace_id
    bind_contextvars(**ctx)


# ---------------------------------------------------------------------------
# FastAPI / Starlette ASGI middleware
# ---------------------------------------------------------------------------

class StructlogRequestMiddleware:
    """Starlette pure-ASGI middleware that binds per-request structlog context.

    Injects ``request_id`` (UUID4, generated per request) and ``user_id``
    (extracted from the JWT ``sub`` claim via the ``X-User-Id`` internal
    header set by the auth layer, or ``None`` for unauthenticated requests).

    Clears all contextvars after the response is sent so that the next
    request on the same asyncio Task gets a clean slate.
    """

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict,
        receive: Callable[..., Awaitable[dict]],
        send: Callable[..., Awaitable[None]],
    ) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Extract optional user_id from internal header (set downstream by deps)
        # We cannot read the JWT here (no DB), so we rely on the request path.
        # user_id will be None for unauthenticated requests; auth endpoints will
        # emit their own bind_contextvars(user_id=...) after token validation.
        headers: dict[bytes, bytes] = dict(scope.get("headers", []))
        raw_user_id = headers.get(b"x-prism-user-id")
        user_id = raw_user_id.decode() if raw_user_id else None

        request_id = str(uuid.uuid4())
        _clear_contextvars()  # ensure clean state for this task
        bind_request_context(request_id=request_id, user_id=user_id)

        log = structlog.get_logger("prism.http")
        method = scope.get("method", "?")
        path = scope.get("path", "?")
        log.debug(
            "http.request.started",
            method=method,
            path=path,
        )

        try:
            await self.app(scope, receive, send)
        finally:
            _clear_contextvars()


# ---------------------------------------------------------------------------
# Core initialiser (call once during lifespan startup)
# ---------------------------------------------------------------------------

def init_logging(level: str = "INFO", *, dev_mode: bool = False) -> None:
    """Configure structlog for the entire application.

    Call once during the FastAPI lifespan startup event.  After this call,
    all code can obtain a logger via ``structlog.get_logger()`` and every
    log record will automatically include any context set with
    ``bind_request_context()`` or ``bind_run_context()``.

    Args:
        level:    Standard logging level string, e.g. ``"INFO"``, ``"DEBUG"``.
                  Defaults to ``"INFO"``.
        dev_mode: When ``True``, use structlog's colourised ``ConsoleRenderer``
                  for human-readable terminal output.  When ``False`` (default,
                  production), use ``JSONRenderer`` for machine-parseable JSON.
    """
    stdlib_level = getattr(logging, level.upper(), logging.INFO)

    # Mirror structlog level to stdlib so third-party libs (uvicorn, SQLAlchemy)
    # are captured at the same threshold.
    logging.basicConfig(
        format="%(message)s",
        level=stdlib_level,
    )

    # Shared processors (applied regardless of renderer)
    shared_processors: list = [
        merge_contextvars,                             # inject bound context vars
        structlog_masker,                              # redact secrets before rendering
        structlog.stdlib.add_log_level,                # add "level" key
        structlog.processors.TimeStamper(fmt="iso"),   # ISO 8601 timestamp
        structlog.processors.StackInfoRenderer(),      # render stack_info
        structlog.processors.format_exc_info,          # render exc_info
    ]

    if dev_mode:
        # Human-readable colourised output for local development
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # Machine-parseable JSON for Loki / CloudWatch / ELK
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(stdlib_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
