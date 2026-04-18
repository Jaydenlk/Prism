"""
Executor 专属 Prometheus Metrics（独立 CollectorRegistry）

独立 Registry 避免与 backend.app.observability.metrics 冲突：
- 两边注册表不同，metric 名可相同但互不干扰
- Executor 是子进程，不运行 /metrics 端点；这些 metric 供未来 Pushgateway 或 sidecar 使用

DOC-03 Task 3.1 定义的 6 条 executor-side metric：
  1. prism_tool_invocations_total{tool_name}           Counter
  2. prism_tool_duration_seconds{tool_name}            Histogram
  3. prism_tool_errors_total{tool_name, error_type}   Counter
  4. prism_harness_turn_total{agent_type, stop_reason} Counter
  5. prism_harness_compaction_total{tier}              Counter
  6. prism_callback_dlq_total{event_type}             Counter

进程边界：本模块只 import prometheus_client，禁止 import backend.app.*
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Histogram

# 独立 Registry（与 backend REGISTRY 不同，避免 duplicate metric 错误）
EXECUTOR_REGISTRY = CollectorRegistry(auto_describe=True)

# ---------------------------------------------------------------------------
# 1. 工具调用计数
# ---------------------------------------------------------------------------
prism_tool_invocations_total = Counter(
    "prism_tool_invocations_total",
    "Total tool invocations dispatched by the Executor Harness.",
    ["tool_name"],
    registry=EXECUTOR_REGISTRY,
)

# ---------------------------------------------------------------------------
# 2. 工具执行延迟
# ---------------------------------------------------------------------------
prism_tool_duration_seconds = Histogram(
    "prism_tool_duration_seconds",
    "Latency of individual tool executions in the Executor.",
    ["tool_name"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
    registry=EXECUTOR_REGISTRY,
)

# ---------------------------------------------------------------------------
# 3. 工具执行错误
# ---------------------------------------------------------------------------
prism_tool_errors_total = Counter(
    "prism_tool_errors_total",
    "Total tool execution errors, labelled by tool_name and error_type.",
    ["tool_name", "error_type"],
    registry=EXECUTOR_REGISTRY,
)

# ---------------------------------------------------------------------------
# 4. TAOR 轮次统计
# ---------------------------------------------------------------------------
prism_harness_turn_total = Counter(
    "prism_harness_turn_total",
    "Total TAOR loop turns executed, labelled by agent_type and stop_reason.",
    ["agent_type", "stop_reason"],
    registry=EXECUTOR_REGISTRY,
)

# ---------------------------------------------------------------------------
# 5. Compaction 事件
# ---------------------------------------------------------------------------
prism_harness_compaction_total = Counter(
    "prism_harness_compaction_total",
    "Total context compaction events triggered by the Executor, labelled by tier.",
    ["tier"],
    registry=EXECUTOR_REGISTRY,
)

# ---------------------------------------------------------------------------
# 6. 回调 DLQ
# ---------------------------------------------------------------------------
prism_callback_dlq_total = Counter(
    "prism_callback_dlq_total",
    "Total callback events that failed all retries and were pushed to the dead letter queue.",
    ["event_type"],
    registry=EXECUTOR_REGISTRY,
)
