"""
Prism v2 — OpenTelemetry Tracing initializer (ADR-117, DOC-12 Task 12.5)

Implements:
  - TracerProvider with OTLP/stdout exporter (graceful degradation)
  - W3C TraceContext propagation: extract/inject helpers for cross-process trace
  - Core span tree: run / taor_turn / prompt_assembly / model_request /
                    tool_use / middleware_chain / compaction
  - Mandatory attributes per ADR-117 spec

Environment variables consumed (set in backend/core/config.py Settings):
  OTEL_EXPORTER_OTLP_ENDPOINT   — if non-empty, use OTLP HTTP; else stdout (dev)
  OTEL_SERVICE_NAME             — service.name resource attribute (default: prism-backend)

FastAPI / httpx / asyncpg auto-instrumentation is set up inside init_tracing().

进程边界: 本模块只在 backend 进程内使用。executor 有独立的 tracing.py。
禁止 import executor.*。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.propagate import extract, inject
from opentelemetry.propagators.textmap import CarrierT
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor

if TYPE_CHECKING:
    from app.core.config import Settings

# Module-level tracer — initialised by init_tracing(); safe to reference before
# init_tracing() is called but will produce no-op spans until a real provider
# is installed.
tracer: trace.Tracer = trace.get_tracer("prism-backend")


# ---------------------------------------------------------------------------
# Initializer — called once during FastAPI lifespan startup
# ---------------------------------------------------------------------------

def init_tracing(settings: "Settings") -> trace.Tracer:
    """Configure the global OpenTelemetry TracerProvider.

    If ``settings.OTEL_EXPORTER_OTLP_ENDPOINT`` is set, spans are exported to
    that OTLP HTTP endpoint (Jaeger / Tempo / Honeycomb / cloud).
    Otherwise a ConsoleSpanExporter is used so developers see traces on stdout
    without any infrastructure.

    Auto-instruments FastAPI and httpx when the corresponding
    opentelemetry-instrumentation-* packages are installed (best-effort; missing
    packages are silently skipped so the application still starts).

    Returns the module-level ``tracer`` configured for "prism-backend".
    """
    global tracer  # noqa: PLW0603

    resource = Resource.create(
        {
            "service.name": settings.OTEL_SERVICE_NAME or "prism-backend",
            "service.version": "2.0.0",
            "deployment.environment": settings.PRISM_ENV,
        }
    )

    provider = TracerProvider(resource=resource)

    if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
            )
        )
    else:
        # Dev-friendly: print spans to stdout (no external service required)
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer("prism-backend")

    # --- Best-effort auto-instrumentation -----------------------------------
    _try_instrument_fastapi()
    _try_instrument_httpx()

    return tracer


# ---------------------------------------------------------------------------
# W3C TraceContext — cross-process propagation helpers (ADR-117)
# ---------------------------------------------------------------------------

def get_traceparent() -> str | None:
    """Extract the W3C traceparent header value from the current active span.

    Used by ProcessManager._build_command() to inject the traceparent into
    the ``--otel-trace-id`` argv of the executor subprocess, continuing the
    same distributed trace in the child process.

    Returns None if there is no active span (tracing not initialised / no run).
    """
    carrier: dict[str, str] = {}
    inject(carrier)          # W3C TraceContext: populates "traceparent" key
    return carrier.get("traceparent")


def extract_traceparent(traceparent: str) -> Context:
    """Parse a W3C traceparent string into an OTel Context.

    Used by the executor subprocess on startup:
        ctx = extract_traceparent(args.otel_trace_id)
        with tracer.start_as_current_span("run", context=ctx, ...):
            ...

    This continues the Backend's trace so all executor spans appear as children
    of the same root run span.

    Args:
        traceparent: W3C traceparent string, e.g.
                     "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

    Returns:
        OTel Context with the span context derived from the traceparent.
    """
    return extract({"traceparent": traceparent})


# ---------------------------------------------------------------------------
# Span attribute constants (ADR-117)
# ---------------------------------------------------------------------------

class SpanAttr:
    """Canonical OTel attribute keys used across backend and executor.

    Keeping them in one place prevents typos and makes attribute name
    changes trivially searchable.
    """

    # Run-level (set on the root "run" span)
    RUN_ID = "run.id"
    SESSION_ID = "session.id"
    USER_ID = "user.id"
    AGENT_TYPE = "agent.type"
    ROUTE_MODE = "route.mode"

    # TAOR turn level
    TURN_COUNT = "turn.count"
    TOKENS_ESTIMATED = "tokens.estimated"

    # Model request
    PROVIDER_NAME = "provider.name"
    MODEL_ID = "model.id"
    CACHE_HIT_TOKENS = "model.cache_hit_tokens"

    # Tool use
    TOOL_NAME = "tool.name"
    TOOL_DURATION_MS = "tool.duration_ms"

    # Harness governance
    GUARDRAIL_TRIGGERED = "harness.guardrail_triggered"
    PERMISSION_DECISION = "harness.permission_decision"

    # Compaction
    COMPACTION_TIER = "compaction.tier"
    COMPACTION_BEFORE = "compaction.before_tokens"
    COMPACTION_AFTER = "compaction.after_tokens"


# ---------------------------------------------------------------------------
# Span name constants
# ---------------------------------------------------------------------------

class SpanName:
    """Canonical span names for the core span tree (ADR-117 §核心 span 树结构)."""

    RUN = "run"
    TAOR_TURN = "taor_turn"
    PROMPT_ASSEMBLY = "prompt_assembly"
    MODEL_REQUEST = "model_request"
    TOOL_USE = "tool_use"
    HOOK_PRE_TOOL_USE = "hook.pre_tool_use"
    PERMISSION_CHECK = "permission.check"
    TOOL_EXECUTE = "tool.execute"
    MIDDLEWARE_CHAIN = "middleware_chain"
    COMPACTION = "compaction"


# ---------------------------------------------------------------------------
# Best-effort auto-instrumentation helpers
# ---------------------------------------------------------------------------

def _try_instrument_fastapi() -> None:
    """Instrument FastAPI with OTel if the package is installed."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore[import]

        FastAPIInstrumentor().instrument()
    except ImportError:
        pass  # opentelemetry-instrumentation-fastapi not installed — skip


def _try_instrument_httpx() -> None:
    """Instrument httpx with OTel if the package is installed."""
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor  # type: ignore[import]

        HTTPXClientInstrumentor().instrument()
    except ImportError:
        pass  # opentelemetry-instrumentation-httpx not installed — skip
