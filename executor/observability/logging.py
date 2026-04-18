"""
Prism v2 Executor — Structured logging (ADR-118, DOC-12 Task 12.6)

Executor-side mirror of backend/app/observability/logging.py.
Follows the same ADR-118 convention but runs in the child subprocess.

进程边界：本模块禁止 import backend.app.*

Public API
----------
init_logging(level, dev_mode)          — call once in executor/__main__.py
bind_run_context(run_id, session_id, user_id, agent_type, trace_id)
clear_contextvars()                    — call after each top-level operation

Logging-level convention (ADR-118):
  DEBUG    stream internals (tool_use_delta counts)
  INFO     lifecycle (run.started, run.completed, tool.invoked, callback.received)
  WARNING  degradation (callback.server_error, retrying, heartbeat.stale)
  ERROR    failures (run.failed, tool.exception)
  CRITICAL crash (subprocess.crashed, unhandled exception)
"""
from __future__ import annotations

import logging

import structlog
from structlog.contextvars import (
    bind_contextvars,
    clear_contextvars as _clear_contextvars,
    merge_contextvars,
)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

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
    emitted during the TAOR loop automatically contains run_id / session_id /
    user_id / agent_type without explicit keyword arguments.

    Args:
        run_id:      Run UUID7 (corresponds to ``runs`` table PK).
        session_id:  Session UUID7.
        user_id:     User UUID7.
        agent_type:  Agent type string (default ``"general"``).
        trace_id:    W3C traceparent string (optional, injected by OTel).
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


def clear_contextvars() -> None:
    """Remove all structlog contextvars bound in this asyncio Task."""
    _clear_contextvars()


# ---------------------------------------------------------------------------
# Core initialiser (call once in executor/__main__.py)
# ---------------------------------------------------------------------------

def init_logging(level: str = "INFO", *, dev_mode: bool = False) -> None:
    """Configure structlog for the executor subprocess.

    Mirrors backend ``init_logging()`` so that log records from the executor
    process have the same shape as backend records when shipped to a log
    aggregator.

    Args:
        level:    Standard logging level string, e.g. ``"INFO"``, ``"DEBUG"``.
                  Defaults to ``"INFO"``.
        dev_mode: When ``True``, use ``ConsoleRenderer`` (colourised, human
                  readable).  When ``False`` (default, production), use
                  ``JSONRenderer`` for machine-parseable JSON lines.
    """
    stdlib_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        level=stdlib_level,
    )

    shared_processors: list = [
        merge_contextvars,                             # inject bound context vars
        structlog.stdlib.add_log_level,                # add "level" key
        structlog.processors.TimeStamper(fmt="iso"),   # ISO 8601 timestamp
        structlog.processors.StackInfoRenderer(),      # render stack_info
        structlog.processors.format_exc_info,          # render exc_info
    ]

    if dev_mode:
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(stdlib_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
