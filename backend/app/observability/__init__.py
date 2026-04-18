"""Backend observability package — metrics, logging, tracing."""

from app.observability.tracing import (  # noqa: F401
    SpanAttr,
    SpanName,
    extract_traceparent,
    get_traceparent,
    init_tracing,
    tracer,
)
