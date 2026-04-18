"""Backend observability package — metrics, logging, tracing."""

from app.observability.logging import (  # noqa: F401
    StructlogRequestMiddleware,
    bind_request_context,
    bind_run_context,
    clear_contextvars,
    init_logging,
)
from app.observability.tracing import (  # noqa: F401
    SpanAttr,
    SpanName,
    extract_traceparent,
    get_traceparent,
    init_tracing,
    tracer,
)
