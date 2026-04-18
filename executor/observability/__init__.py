"""Executor 专属可观测性模块（独立 Registry，避免与 backend 冲突）"""

from executor.observability.tracing import (  # noqa: F401
    SpanAttr,
    SpanName,
    get_traceparent,
    init_tracing,
    tracer,
)

