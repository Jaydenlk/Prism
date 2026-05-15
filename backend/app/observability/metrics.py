"""
Prism v2 — Prometheus metrics registry (ADR-116, DOC-12 Task 12.4)

10-dimension metric coverage — 60+ indicators, all with `prism_` prefix.

Dimensions:
  1.  Run lifecycle        — 5 metrics
  2.  TAOR turns           — 4 metrics
  3.  Tool invocations     — 5 metrics
  4.  Harness governance   — 7 metrics
  5.  Model / LLM          — 5 metrics
  6.  Session              — 5 metrics
  7.  Provider health      — 4 metrics
  8.  IM gateway           — 5 metrics
  9.  Sub-process/Agent    — 5 metrics
  10. HTTP layer           — 4 metrics
  (bonus) Frontend         — 2 metrics
  (bonus) Cache            — 3 metrics
  (bonus) Auth             — 3 metrics
  (bonus) Queue            — 3 metrics
  (bonus) Config/Skill     — 3 metrics
  (bonus) Fork/Coord       — 4 metrics

Total defined: 67 unique metric names (each Counter/Histogram/Gauge = 1).
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


# ===========================================================================
# 1. Run lifecycle (5)
# ===========================================================================

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

prism_run_turn_count = Histogram(
    "prism_run_turn_count",
    "Number of TAOR turns per completed run.",
    ["agent_type"],
    buckets=(1, 2, 3, 5, 8, 13, 21, 34, 55),
    registry=REGISTRY,
)

prism_run_tokens_total = Counter(
    "prism_run_tokens_total",
    "Total tokens consumed per run, labelled by kind (input/output/cache_hit/cache_creation).",
    ["kind"],
    registry=REGISTRY,
)

prism_run_cost_usd_total = Counter(
    "prism_run_cost_usd_total",
    "Estimated USD cost of all runs, labelled by provider.",
    ["provider"],
    registry=REGISTRY,
)


# ===========================================================================
# 2. TAOR turns (4)
# ===========================================================================

prism_taor_turns_total = Counter(
    "prism_taor_turns_total",
    "Total TAOR loop turns executed, labelled by agent_type and outcome.",
    ["agent_type", "outcome"],
    registry=REGISTRY,
)

prism_turn_duration_seconds = Histogram(
    "prism_turn_duration_seconds",
    "Wall-clock duration of a single TAOR turn (Think+Act+Observe).",
    ["agent_type"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60),
    registry=REGISTRY,
)

prism_turn_stop_reason_total = Counter(
    "prism_turn_stop_reason_total",
    "Total TAOR loop terminations by stop_reason (end_turn/tool_use/max_tokens/stop_sequence).",
    ["reason"],
    registry=REGISTRY,
)

# Alias kept for DOC-03 backward compatibility
prism_harness_turn_total = Counter(
    "prism_harness_turn_total",
    "Total TAOR loop turns executed, labelled by agent_type and stop_reason (DOC-03 alias).",
    ["agent_type", "stop_reason"],
    registry=REGISTRY,
)


# ===========================================================================
# 3. Tool invocations (5)
# ===========================================================================

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

prism_tool_errors_total = Counter(
    "prism_tool_errors_total",
    "Total tool execution errors, labelled by tool_name and error_type.",
    ["tool_name", "error_type"],
    registry=REGISTRY,
)

prism_tool_truncation_total = Counter(
    "prism_tool_truncation_total",
    "Total tool output truncation events (output exceeded max_output_tokens).",
    ["tool_name"],
    registry=REGISTRY,
)

prism_tool_parallel_invocations = Gauge(
    "prism_tool_parallel_invocations",
    "Current number of tool invocations executing in parallel (asyncio.gather).",
    registry=REGISTRY,
)


# ===========================================================================
# 4. Harness governance (7)
# ===========================================================================

prism_harness_compaction_total = Counter(
    "prism_harness_compaction_total",
    "Total context compaction events, labelled by tier (1/2/4) per ADR-031.",
    ["tier"],
    registry=REGISTRY,
)

prism_harness_permission_asks_total = Counter(
    "prism_harness_permission_asks_total",
    "Total permission-ask events raised by the Harness (ADR-028 BLPOP).",
    ["decision"],
    registry=REGISTRY,
)

prism_harness_guardrail_triggers_total = Counter(
    "prism_harness_guardrail_triggers_total",
    "Total guardrail rule triggers, labelled by rule_id.",
    ["rule_id"],
    registry=REGISTRY,
)

prism_harness_hook_invocations_total = Counter(
    "prism_harness_hook_invocations_total",
    "Total hook handler invocations, labelled by event_type and handler_type.",
    ["event_type", "handler_type"],
    registry=REGISTRY,
)

prism_harness_feedback_total = Counter(
    "prism_harness_feedback_total",
    "Total feedback capture events (FeedbackCaptureMiddleware ADR-030).",
    ["event_type", "severity"],
    registry=REGISTRY,
)

prism_harness_memory_extracted_total = Counter(
    "prism_harness_memory_extracted_total",
    "Total session-end memory extractions performed by HarnessRuntime (ADR-030).",
    registry=REGISTRY,
)

prism_permission_answered_total = Counter(
    "prism_permission_answered_total",
    "Total permission-ask answers submitted via /sessions/{id}/permission-answer.",
    ["decision"],
    registry=REGISTRY,
)

# Kept from DOC-03 Task 3.1 initial definition
prism_callback_dlq_total = Counter(
    "prism_callback_dlq_total",
    "Total callback events that failed all retries and were pushed to the dead letter queue.",
    ["event_type"],
    registry=REGISTRY,
)


# ===========================================================================
# 5. Model / LLM (5)
# ===========================================================================

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

prism_model_cache_hit_ratio = Gauge(
    "prism_model_cache_hit_ratio",
    "Cache-hit token ratio for the last 5-minute window (cache_read / input_total).",
    ["provider", "model"],
    registry=REGISTRY,
)

prism_model_errors_total = Counter(
    "prism_model_errors_total",
    "Total upstream model API errors, labelled by provider, model, error_type.",
    ["provider", "model", "error_type"],
    registry=REGISTRY,
)

prism_model_stream_chunks_total = Counter(
    "prism_model_stream_chunks_total",
    "Total SSE stream chunks received from upstream model APIs.",
    ["provider", "model"],
    registry=REGISTRY,
)


# ===========================================================================
# 6. Session (5)
# ===========================================================================

prism_active_sessions = Gauge(
    "prism_active_sessions",
    "Number of sessions with at least one SSE subscriber currently connected.",
    registry=REGISTRY,
)

prism_sessions_active = Gauge(
    "prism_sessions_active",
    "Total sessions with status=active in the DB (snapshot gauge).",
    registry=REGISTRY,
)

prism_session_queue_length = Gauge(
    "prism_session_queue_length",
    "Current length of the run queue across all sessions.",
    registry=REGISTRY,
)

prism_sse_tickets_issued_total = Counter(
    "prism_sse_tickets_issued_total",
    "Total SSE one-time tickets issued (ADR-057 / ADR-051).",
    registry=REGISTRY,
)

prism_sse_connections_active = Gauge(
    "prism_sse_connections_active",
    "Current number of active SSE stream connections (MAX_CONNS=3 per session ADR-063).",
    registry=REGISTRY,
)


# ===========================================================================
# 7. Provider health (4)
# ===========================================================================

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

prism_provider_circuit_breaks_total = Counter(
    "prism_provider_circuit_breaks_total",
    "Total circuit-breaker open events, labelled by provider_id and reason.",
    ["provider_id", "reason"],
    registry=REGISTRY,
)

prism_provider_latency_seconds = Histogram(
    "prism_provider_latency_seconds",
    "End-to-end response latency per provider (includes network + LLM compute).",
    ["provider_id"],
    buckets=(0.5, 1, 2, 5, 10, 20, 40, 80),
    registry=REGISTRY,
)


# ===========================================================================
# 8. IM gateway (5)
# ===========================================================================

prism_im_messages_total = Counter(
    "prism_im_messages_total",
    "Total inbound IM messages received, labelled by platform.",
    ["platform", "status"],
    registry=REGISTRY,
)

prism_im_webhook_duplicates_total = Counter(
    "prism_im_webhook_duplicates_total",
    "Total duplicate IM webhook messages suppressed by idempotency check (ADR-070).",
    ["channel"],
    registry=REGISTRY,
)

prism_im_bindings_active = Gauge(
    "prism_im_bindings_active",
    "Total active IM bindings (paired_at IS NOT NULL) across all channels.",
    registry=REGISTRY,
)

prism_im_outbound_messages_total = Counter(
    "prism_im_outbound_messages_total",
    "Total outbound IM messages sent by Prism to external platforms.",
    ["platform", "status"],
    registry=REGISTRY,
)

prism_im_pairing_codes_total = Counter(
    "prism_im_pairing_codes_total",
    "Total IM pairing code generation events (ADR-071 binding flow).",
    ["platform"],
    registry=REGISTRY,
)


# ===========================================================================
# 9. Sub-process / Agent (5)
# ===========================================================================

prism_executor_processes_active = Gauge(
    "prism_executor_processes_active",
    "Number of executor sub-processes currently alive.",
    registry=REGISTRY,
)

prism_agent_subprocess_running = Gauge(
    "prism_agent_subprocess_running",
    "Number of agent sub-processes in running state (alias for executor_processes_active).",
    registry=REGISTRY,
)

prism_agent_heartbeat_stale_total = Counter(
    "prism_agent_heartbeat_stale_total",
    "Total agent heartbeat stale events detected by HeartbeatMonitor (ADR-065).",
    registry=REGISTRY,
)

prism_agent_subprocess_crashed_total = Counter(
    "prism_agent_subprocess_crashed_total",
    "Total agent sub-process crash events, labelled by reason.",
    ["reason"],
    registry=REGISTRY,
)

prism_agent_fork_total = Counter(
    "prism_agent_fork_total",
    "Total fork operations initiated by ForkManager (ADR-037), labelled by parent_agent_type.",
    ["parent_agent_type"],
    registry=REGISTRY,
)


# ===========================================================================
# 10. HTTP layer (4)
# ===========================================================================

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

prism_http_errors_total = Counter(
    "prism_http_errors_total",
    "Total HTTP 4xx/5xx responses, labelled by method, route, status_code.",
    ["method", "route", "status_code"],
    registry=REGISTRY,
)

prism_http_active_connections = Gauge(
    "prism_http_active_connections",
    "Current number of active HTTP connections being processed.",
    registry=REGISTRY,
)


# ===========================================================================
# 11. Frontend errors (Task 12.7 placeholder — 2)
# ===========================================================================

prism_frontend_errors_total = Counter(
    "prism_frontend_errors_total",
    "Total frontend JS errors reported via /api/v1/frontend-errors endpoint (Task 12.7).",
    ["severity", "viewport"],
    registry=REGISTRY,
)

prism_web_vitals_seconds = Histogram(
    "prism_web_vitals_seconds",
    "Web Vitals measurements (LCP/FID/CLS) reported from frontend (Task 12.7).",
    ["metric", "route"],
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 4, 10),
    registry=REGISTRY,
)


# ===========================================================================
# 12. Cache (3)
# ===========================================================================

prism_cache_hits_total = Counter(
    "prism_cache_hits_total",
    "Total Anthropic prompt cache read-hits across all model requests.",
    ["provider", "model"],
    registry=REGISTRY,
)

prism_cache_creations_total = Counter(
    "prism_cache_creations_total",
    "Total Anthropic prompt cache creation events (cache_control write).",
    ["provider", "model"],
    registry=REGISTRY,
)

prism_cache_savings_usd_total = Counter(
    "prism_cache_savings_usd_total",
    "Cumulative estimated USD saved by cache hits vs non-cached input pricing.",
    ["provider"],
    registry=REGISTRY,
)


# ===========================================================================
# 13. Auth (3)
# ===========================================================================

prism_auth_login_total = Counter(
    "prism_auth_login_total",
    "Total login attempts, labelled by outcome (success/failure).",
    ["outcome"],
    registry=REGISTRY,
)

prism_auth_token_refresh_total = Counter(
    "prism_auth_token_refresh_total",
    "Total JWT refresh token exchanges.",
    ["outcome"],
    registry=REGISTRY,
)

prism_auth_active_users = Gauge(
    "prism_auth_active_users",
    "Number of active (non-disabled) user accounts.",
    registry=REGISTRY,
)


# ===========================================================================
# 14. Queue (3)
# ===========================================================================

prism_queue_depth = Gauge(
    "prism_queue_depth",
    "Current depth of the global session run queue (session_queue_items with status=queued).",
    registry=REGISTRY,
)

prism_queue_wait_seconds = Histogram(
    "prism_queue_wait_seconds",
    "Time a run spends in the queue before promotion to running.",
    buckets=(1, 5, 10, 30, 60, 120, 300),
    registry=REGISTRY,
)

prism_queue_overflow_total = Counter(
    "prism_queue_overflow_total",
    "Total queue overflow rejections (QUEUE_MAX_SIZE=50 exceeded, ADR-061).",
    registry=REGISTRY,
)


# ===========================================================================
# 15. Config / Skill (3)
# ===========================================================================

prism_skills_loaded_total = Counter(
    "prism_skills_loaded_total",
    "Total skill load events by level (0=builtin/1=user/2=session) per ADR-043.",
    ["level"],
    registry=REGISTRY,
)

prism_skills_active = Gauge(
    "prism_skills_active",
    "Number of skills currently installed and active in skill_installs table.",
    registry=REGISTRY,
)

prism_config_reloads_total = Counter(
    "prism_config_reloads_total",
    "Total harness config reload events (HarnessConfigLoader 2-source merge ADR-033).",
    ["source"],
    registry=REGISTRY,
)


# ===========================================================================
# 16. Fork / Coordinator (4)
# ===========================================================================

prism_coordinator_plans_total = Counter(
    "prism_coordinator_plans_total",
    "Total coordinator plan executions (Coordinator.execute ADR-040).",
    ["status"],
    registry=REGISTRY,
)

prism_coordinator_plan_steps_total = Counter(
    "prism_coordinator_plan_steps_total",
    "Total individual plan step executions within coordinator runs.",
    ["agent_type", "status"],
    registry=REGISTRY,
)

prism_fork_depth_exceeded_total = Counter(
    "prism_fork_depth_exceeded_total",
    "Total ForkDepthExceeded errors raised by ForkManager (max_depth guard ADR-037).",
    registry=REGISTRY,
)

prism_fork_active = Gauge(
    "prism_fork_active",
    "Current number of active forked child agent sub-processes.",
    registry=REGISTRY,
)
