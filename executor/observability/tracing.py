"""
Prism v2 — Executor-side OpenTelemetry Tracing (ADR-117, DOC-12 Task 12.5)

Mirrors backend/app/observability/tracing.py but:
  - service.name = "prism-executor"
  - Receives traceparent via --otel-trace-id argv (injected by ProcessManager)
  - Continues the Backend's trace: all executor spans are children of the
    Backend "run" span, forming one distributed trace across process boundaries

W3C TraceContext cross-process flow (ADR-117):
  Backend:
    traceparent = get_traceparent()   → "00-<trace_id>-<span_id>-01"
    cmd += [f"--otel-trace-id={traceparent}"]
  Executor (__main__.py):
    ctx = init_tracing(otlp_endpoint, traceparent=args.otel_trace_id)
    with tracer.start_as_current_span("run", context=ctx, ...):
        ...

进程边界: 本模块只 import executor.* / opentelemetry.*；禁止 import backend.app.*
"""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.propagate import extract, inject
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor

# Module-level tracer — becomes real after init_tracing(); no-op before that
tracer: trace.Tracer = trace.get_tracer("prism-executor")


# ---------------------------------------------------------------------------
# Initializer — called once in executor/__main__.py before the run loop
# ---------------------------------------------------------------------------

def init_tracing(
    otlp_endpoint: str | None = None,
    traceparent: str | None = None,
    prism_env: str = "production",
) -> Context:
    """Configure the global TracerProvider for the executor subprocess.

    Args:
        otlp_endpoint: OTLP HTTP endpoint.  If falsy, a ConsoleSpanExporter is
                       used (dev-friendly stdout output).  Should be read from
                       the ``OTEL_EXPORTER_OTLP_ENDPOINT`` env var.
        traceparent:   W3C traceparent string received via ``--otel-trace-id``
                       argv.  If provided the returned Context carries the
                       parent span context so executor spans are linked to the
                       Backend trace.  If None a new root trace is started.
        prism_env:     deployment.environment label (e.g. "development").

    Returns:
        OTel Context (either extracted from traceparent or empty).  Pass this
        as the ``context=`` kwarg to the root "run" span.
    """
    global tracer  # noqa: PLW0603

    resource = Resource.create(
        {
            "service.name": "prism-executor",
            "service.version": "2.0.0",
            "deployment.environment": prism_env,
        }
    )

    provider = TracerProvider(resource=resource)

    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
        )
    else:
        # Dev/fallback: emit spans to stdout so developers can inspect them
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer("prism-executor")

    # Extract parent context from W3C traceparent (ADR-117 cross-process)
    if traceparent:
        return extract({"traceparent": traceparent})
    return Context()


# ---------------------------------------------------------------------------
# W3C TraceContext helpers — re-exported for convenience
# ---------------------------------------------------------------------------

def get_traceparent() -> str | None:
    """Return the current W3C traceparent string (for nested subprocess launches).

    Rarely needed in executor code but provided for completeness so coordinator
    forks can propagate the trace into their own child processes.
    """
    carrier: dict[str, str] = {}
    inject(carrier)
    return carrier.get("traceparent")


# ---------------------------------------------------------------------------
# Span attribute constants (ADR-117) — mirrors backend SpanAttr
# ---------------------------------------------------------------------------

class SpanAttr:
    """Canonical OTel attribute keys shared by backend and executor."""

    RUN_ID = "run.id"
    SESSION_ID = "session.id"
    USER_ID = "user.id"
    AGENT_TYPE = "agent.type"
    ROUTE_MODE = "route.mode"

    TURN_COUNT = "turn.count"
    TOKENS_ESTIMATED = "tokens.estimated"

    PROVIDER_NAME = "provider.name"
    MODEL_ID = "model.id"
    CACHE_HIT_TOKENS = "model.cache_hit_tokens"

    TOOL_NAME = "tool.name"
    TOOL_DURATION_MS = "tool.duration_ms"

    GUARDRAIL_TRIGGERED = "harness.guardrail_triggered"
    PERMISSION_DECISION = "harness.permission_decision"

    COMPACTION_TIER = "compaction.tier"
    COMPACTION_BEFORE = "compaction.before_tokens"
    COMPACTION_AFTER = "compaction.after_tokens"


class SpanName:
    """Canonical span names for the executor span tree (ADR-117)."""

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
