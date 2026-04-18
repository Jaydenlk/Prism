"""
Prism v2 — Prometheus metrics registry (ADR-116, DOC-12 Task 12.4)

Defines a shared CollectorRegistry and the core Prism metrics.
Full 60+ metric implementation is tracked in DOC-12 Task 12.4; this module
provides the 10-dimension skeleton so that app startup and /metrics work
from day one.

Dimensions covered here (subset):
  1. Run lifecycle    — prism_runs_total, prism_run_duration_seconds
  2. TAOR turns       — prism_taor_turns_total
  3. Tool invocation  — prism_tool_invocations_total, prism_tool_duration_seconds
  4. Harness          — prism_harness_compaction_total, prism_harness_permission_asks_total
  5. Model / LLM      — prism_model_tokens_total, prism_model_request_duration_seconds
  6. Provider health  — prism_provider_healthy, prism_provider_failover_total
  7. Session          — prism_active_sessions
  8. IM               — prism_im_messages_total
  9. Sub-process      — prism_executor_processes_active
 10. HTTP             — prism_http_requests_total, prism_http_request_duration_seconds
"""
from __future__ import annotations

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
)

# ---------------------------------------------------------------------------
# Shared registry — used by /metrics endpoint and Executor sidecar
# ---------------------------------------------------------------------------
REGISTRY = CollectorRegistry(auto_describe=True)

# ---------------------------------------------------------------------------
# 1. Run lifecycle
# ---------------------------------------------------------------------------
prism_runs_total = Counter(
    "prism_runs_total",
    "Total number of agent runs created, labelled by final status and agent_type.",
    ["status", "agent_type"],
    registry=REGISTRY,
)

prism_run_duration_seconds = Histogram(
    "prism_run_duration_seconds",
    "Wall-clock duration of an agent run from creation to terminal state.",
    ["agent_type"],
    buckets=(1, 5, 10, 30, 60, 180, 600, 1800),
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# 2. TAOR turns
# ---------------------------------------------------------------------------
prism_taor_turns_total = Counter(
    "prism_taor_turns_total",
    "Total TAOR loop turns executed, labelled by agent_type and outcome.",
    ["agent_type", "outcome"],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# 3. Tool invocations
# ---------------------------------------------------------------------------
prism_tool_invocations_total = Counter(
    "prism_tool_invocations_total",
    "Total tool invocations dispatched by the Harness.",
    ["tool_name", "status"],
    registry=REGISTRY,
)

prism_tool_duration_seconds = Histogram(
    "prism_tool_duration_seconds",
    "Latency of individual tool executions.",
    ["tool_name"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# 4. Harness governance
# ---------------------------------------------------------------------------
prism_harness_compaction_total = Counter(
    "prism_harness_compaction_total",
    "Total context compaction events, labelled by tier (0-3).",
    ["tier"],
    registry=REGISTRY,
)

prism_harness_permission_asks_total = Counter(
    "prism_harness_permission_asks_total",
    "Total permission-ask events raised by the Harness.",
    ["decision"],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# 5. Model / LLM usage
# ---------------------------------------------------------------------------
prism_model_tokens_total = Counter(
    "prism_model_tokens_total",
    "Total tokens consumed, labelled by token_type (input/output/cache_read/cache_write).",
    ["provider", "model", "token_type"],
    registry=REGISTRY,
)

prism_model_request_duration_seconds = Histogram(
    "prism_model_request_duration_seconds",
    "Latency of upstream model API requests (time-to-first-token for streaming).",
    ["provider", "model"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# 6. Provider health
# ---------------------------------------------------------------------------
prism_provider_healthy = Gauge(
    "prism_provider_healthy",
    "1 if the provider circuit-breaker is closed (healthy), 0 if open.",
    ["provider_id"],
    registry=REGISTRY,
)

prism_provider_failover_total = Counter(
    "prism_provider_failover_total",
    "Total provider failover events triggered by the circuit-breaker.",
    ["from_provider", "to_provider"],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# 7. Sessions
# ---------------------------------------------------------------------------
prism_active_sessions = Gauge(
    "prism_active_sessions",
    "Number of sessions with at least one SSE subscriber currently connected.",
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# 8. IM gateway
# ---------------------------------------------------------------------------
prism_im_messages_total = Counter(
    "prism_im_messages_total",
    "Total inbound IM messages received, labelled by platform.",
    ["platform", "status"],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# 9. Executor sub-processes
# ---------------------------------------------------------------------------
prism_executor_processes_active = Gauge(
    "prism_executor_processes_active",
    "Number of executor sub-processes currently alive.",
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# 10. HTTP layer
# ---------------------------------------------------------------------------
prism_http_requests_total = Counter(
    "prism_http_requests_total",
    "Total HTTP requests handled by the backend, labelled by method, route, status_code.",
    ["method", "route", "status_code"],
    registry=REGISTRY,
)

prism_http_request_duration_seconds = Histogram(
    "prism_http_request_duration_seconds",
    "HTTP request processing latency.",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
    registry=REGISTRY,
)
