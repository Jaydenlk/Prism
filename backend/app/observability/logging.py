"""
Prism v2 — Structured logging initializer (ADR-118, DOC-12 Task 12.6)

Uses structlog with:
  - contextvars integration for automatic run_id / session_id / user_id binding
  - JSON renderer for machine-parseable output (Loki / CloudWatch / ELK)
  - ISO 8601 timestamps
  - Stack-trace and exception formatting
"""
from __future__ import annotations

import logging


def init_logging(level: str = "INFO") -> None:
    """Configure structlog for the entire application.

    Call once during the FastAPI lifespan startup event.  After this call,
    all code can obtain a logger via ``structlog.get_logger()`` and it will
    automatically include any context-vars set with
    ``structlog.contextvars.bind_contextvars(run_id=..., user_id=...)``.

    Args:
        level: Standard logging level string, e.g. ``"INFO"``, ``"DEBUG"``.
               Defaults to ``"INFO"``.
    """
    import structlog
    from structlog.contextvars import merge_contextvars

    # Mirror structlog level to stdlib so third-party libs (uvicorn, sqlalchemy)
    # are captured at the same level threshold.
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, level.upper(), logging.INFO),
    )

    structlog.configure(
        processors=[
            merge_contextvars,                            # inject bound context vars
            structlog.processors.add_log_level,           # add "level" key
            structlog.processors.TimeStamper(fmt="iso"),  # ISO 8601 timestamp
            structlog.processors.StackInfoRenderer(),     # render stack_info
            structlog.processors.format_exc_info,         # render exc_info
            structlog.processors.JSONRenderer(),          # final JSON output
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
