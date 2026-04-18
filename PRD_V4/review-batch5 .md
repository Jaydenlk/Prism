# Prism v2 架构 Review — Batch 5: Observability & Entropy

> **范围**: DOC-12 (Observability & Entropy),3 个 Task
> **立场**: 质量优先、Obs 前移到 Phase 1 必做、4C8G 基线、不砍功能
> **评审者**: Claude Opus 4.7

---

## 0. 整体判断

DOC-12 是最短的一份(27KB,821 行),但**承担的职责最重**——它是整个系统的**观测底座**。前面 11 份文档产出的所有 Harness 事件、工具调用、Run 状态、Compaction 触发、模型 Token 消耗,最后都要在这里汇聚成可观察、可分析、可告警的数据。

**Batch 1 决策 D5** 已明确: **Obs 在 Phase 1 就必须做到 Production-grade**,不允许"最小子集"。当前 DOC-12 的问题是:

1. **Task 数量不足**(只有 3 个),远不能覆盖"质量优先 + Phase 1 就上"所需的 Obs 范围
2. **指标定义缺失** — 只提到 `harness_summary` 聚合,没有结构化的 metrics 清单、标签规范、导出协议
3. **日志规范缺失** — 通篇不提结构化日志、日志级别、日志聚合方案
4. **Tracing 缺失** — 跨 Backend ↔ 子进程的 trace 链路完全没设计,无法定位 "Run 执行为什么这么慢"
5. **Entropy Detection 5 信号不足** — 缺 Provider 健康、Cache 命中率、permission_ask 超时率等关键信号
6. **UI 面板 = DOC-11 Task 11.4 的范围**,DOC-12 和 DOC-11 之间的接口没对清

按严重性排序,Batch 5 最严重的 5 个问题:

| # | 问题 | 影响 |
|---|---|---|
| **B5-1** | **DOC-12 只有 3 个 Task,Obs 覆盖面严重不足** | Batch 2 §B-4 点名的"Middleware/Hook/Guardrail/Compaction 耗时覆盖"全部漏掉,Phase 1 上线后无法 debug |
| **B5-2** | **Prometheus/OTel 结构化 metrics 完全缺失** | DOC-12 只有"runs.harness_summary 聚合",这是 DB 级报告,不是 metrics。没有 `/metrics` 端点就接不上监控系统 |
| **B5-3** | **跨 Backend↔子进程 trace 链路缺失** | 一次用户请求经过 Backend API → 回调 → 子进程 TAOR → 多个工具调用 → 回调 → SSE,全链路 trace 没有,"为啥慢"无法回答 |
| **B5-4** | **结构化日志规范零定义** | 通篇不提 logger.info / structlog / JSON log,4.6 写代码会用原生 print,ELK/Loki 接不上 |
| **B5-5** | **Task 12.2 的 5 信号阈值"初始估计值"不可操作** | 质量优先下,阈值必须有校准方法论(A/B 对照、历史分位数、灰度期采样),不能"上线后再说" |

---

## Part A — 实现级审视

### DOC-12: Observability & Entropy

#### A12-1. Task 12.1 TokenEstimator 接口设计被 Batch 1 §Q2 否决

**Batch 1 §Q2 已定**: 质量优先下**直接上精确 tokenizer**,不接受 Phase 2 切换。

**Task 12.1 的立场**: "Phase 1 使用 CharCountEstimator(零依赖,ms 级),Phase 2 可切换 TiktokenEstimator"。

**冲突**。质量优先推翻 "Phase 1 粗估" 的设计。

**修法**: Task 12.1 重构:
- 策略模式保留(接口存在),但**默认实现直接是精确 tokenizer**
- Anthropic 协议 Provider → `AnthropicTokenCounter`(调用官方 count_tokens endpoint 或 `anthropic.Anthropic().count_tokens()`)
- OpenAI 协议 Provider → `TiktokenEstimator`(tiktoken.encoding_for_model)
- 未知 Provider → fallback 到 `CharCountEstimator`,但要 log WARNING
- 接口签名: `estimate(text, provider_protocol, model) -> int` —— 必须带 provider 和 model 信息

**requirements.txt 强制加**:
- `tiktoken>=0.7.0`(OpenAI 协议必需)
- `anthropic>=0.40.0`(如果用 Anthropic count_tokens SDK)
- 可选: `transformers + sentencepiece`(给 MiniMax/Qwen/GLM 等国产模型用,它们的 tokenizer 在 HF Hub 上)

**注意**: 某些国产模型(MiniMax M2.7 等)可能没有公开的 tokenizer。这类场景:
- 如果 Provider 能返回 `usage.input_tokens`(大多能),**事后校正**—— 用真实 tokens / 预估 tokens 作为 calibration factor,累积平均,动态调整 CharCountEstimator 的系数
- 这个校正逻辑本身应该是 `CalibratingCharCountEstimator`,Phase 1 必做

#### A12-2. Task 12.1 ResourceMonitor 的内存阈值 1.5GB 不适配 4C8G 基线

Task 12.1 提"内存超过阈值(如 1.5GB)时告警",这是 2C2G 基线下的估算。

**Batch 1 决策**: 基线升到 4C8G。

**修法**: 阈值按相对百分比,不按绝对值:
```python
# resource_monitor.py

class ResourceMonitor:
    def __init__(self, settings):
        self._settings = settings
        # 使用百分比而非绝对值
        self._memory_warning_pct = settings.MEMORY_WARNING_PERCENT    # default 70
        self._memory_critical_pct = settings.MEMORY_CRITICAL_PERCENT  # default 85
        
        # 也保留绝对值的 fallback(某些 Docker 场景 psutil 读不到容器限制)
        self._memory_warning_mb = settings.MEMORY_WARNING_MB          # default 5500 (4C8G 的 70%)
        self._memory_critical_mb = settings.MEMORY_CRITICAL_MB        # default 6800 (4C8G 的 85%)
```

再额外加 CPU 监控 + 子进程数量监控(当前 Task 12.1 只写了内存):
```python
def check(self) -> ResourceStatus:
    return ResourceStatus(
        memory_backend_mb=...,
        memory_system_percent=...,
        cpu_backend_percent=...,      # 新增
        cpu_system_percent=...,       # 新增
        active_agents=...,            # 当前运行的子进程数
        agent_queue_depth=...,        # 等待队列深度
    )
```

#### A12-3. Task 12.2 HarnessAnalytics 缺少 Cache 命中率聚合

Batch 1 §3.5 schema 补丁加了 `cache_hit_tokens` / `cache_miss_tokens` / `cache_creation_tokens`,但 Task 12.2 的 `aggregate()` 返回结构里**没有 cache 维度**。

**修法**: `aggregate()` 返回结构新增:
```python
"cache_stats": {
    "hit_tokens_total": 12500,
    "miss_tokens_total": 8500,
    "creation_tokens_total": 3000,
    "hit_ratio": 0.595,               # hit / (hit + miss)
    "creation_cost_ratio": 0.142,     # creation / (hit + miss + creation)
    "by_provider": {
        "anthropic": {"hit_ratio": 0.72, "cost_saved_usd": 1.23},
        "openai": {"hit_ratio": 0.0},   # OpenAI 当前不支持 cache
    }
}
```

Cache 命中率是**最重要的成本优化指标**之一。CC 对 Prompt Cache 精打细算是差异化亮点之一,Prism 继承这个必须能看得见。

#### A12-4. Task 12.2 Entropy Detection 5 信号少了 3 个关键信号

**Batch 3 §C-1 已提**: Entropy 信号清单需要扩充。这里补齐 3 个:

| 新增信号 | 来源 | 阈值 | 含义 |
|---|---|---|---|
| **Provider 健康度下降** | providers.is_healthy 的近 7 天 False 占比 | > 0.1 | Provider 稳定性下滑,可能需要切 Provider 或联系厂商 |
| **Cache 命中率下降** | harness_summary.cache_stats.hit_ratio 近 7 天 vs 前 7 天 | 下降 > 20% | Prompt 装配不稳定,或 Session 生命周期过短 |
| **permission_ask 超时率上升** | audit_logs 中 permission_ask 无对应 answer 事件的比例 | > 0.3 | 用户放弃率高,UX 有问题或 ask 频率过密 |

扩充后 **8 个信号**,每个信号都必须有:
- 当前值(current window)
- 上一窗口值(previous window,用于 delta)
- 阈值(threshold)
- 严重程度(info / warning / critical)
- 建议动作(suggested_action:人类可读的建议)

#### A12-5. Task 12.2 5 信号阈值"初始估计值"校准方案缺失

Task 12.2 注释: "以下阈值为初始估计值,通过环境变量可配置,上线后根据实际数据校准。"

**质量优先下这是甩锅**。"上线后根据实际数据校准"没说:
- 谁校准?(自动 / 手动)
- 什么频率?(每周 / 每月)
- 基于什么规则?(历史分位数 p95 / 用户反馈 / 业务指标相关性)

**修法**: 加一份**阈值校准方法论**:

```python
# entropy_threshold_calibration.py

class ThresholdCalibrator:
    """
    熵检测阈值的自动校准。
    
    原理:
    - 每周扫描最近 30 天的 harness_summary
    - 计算每个信号的 p50/p90/p95/p99 分位数
    - 新阈值 = 当前阈值和 p90 的平均(防止剧烈变化)
    - 记录校准历史,允许 Admin 回滚
    
    触发:
    - 每周日凌晨 3 点自动运行一次
    - Admin API `POST /admin/entropy/recalibrate` 手动触发
    """
    
    def calibrate(self) -> CalibrationReport:
        historical = self._fetch_30_days_data()
        
        new_thresholds = {}
        for signal in SIGNALS:
            current = self._current_threshold(signal)
            p90 = self._percentile(historical[signal], 90)
            # 平滑过渡: 新阈值是当前值和 p90 的加权平均
            new_thresholds[signal] = current * 0.7 + p90 * 0.3
        
        return CalibrationReport(
            old_thresholds=self._current_thresholds(),
            new_thresholds=new_thresholds,
            data_window_days=30,
            reason="scheduled weekly calibration",
        )
```

这是 Phase 1 必须做的,不是"Phase 2 优化"。

#### A12-6. Task 12.3 `/health` 端点状态码语义不严谨

Task 12.3 说: "全部健康 200,部分警告 200(body 中 status=warning),严重问题 503"。

**问题**:
- 监控系统(K8s liveness probe / ALB health check / nagios)通常只看状态码,不解析 body
- 如果 Redis 挂但 DB 健康,返回 200 + status=warning,K8s 不会重启 Pod,但实际上 Redis 挂了所有 SSE 不通
- 严格来说,**warning 应该返回 200,但要区分 liveness 和 readiness**

**修法**: 拆成两个端点:

```python
# /health/live — Liveness: 进程活着就 200(对抗死锁/卡死)
@router.get("/health/live")
def liveness():
    return {"status": "alive"}

# /health/ready — Readiness: 所有依赖都通才 200
@router.get("/health/ready")
def readiness(db=..., redis=...):
    checks = {
        "database": _check_db(db),
        "redis": _check_redis(redis),
        "resource": _check_resource(),
        "providers": _check_default_provider(),  # 新增: 默认 Provider 是否通
    }
    all_ok = all(c["status"] == "ok" for c in checks.values())
    any_critical = any(c["status"] == "critical" for c in checks.values())
    
    if any_critical:
        return JSONResponse(status_code=503, content={"checks": checks})
    if not all_ok:
        # warning 级也返回 503,让流量切到其他实例(如果有多实例)
        # 单实例场景下,warning 不影响 serving,但不对新流量 ready
        return JSONResponse(status_code=503, content={"checks": checks})
    return {"checks": checks}

# /health/detailed — 人类可读的完整报告(需要认证)
@router.get("/health/detailed", dependencies=[Depends(require_admin)])
def detailed_health():
    # 含内存/CPU/子进程/近期错误等全部信息
    ...
```

**Liveness / Readiness 语义分离**是 K8s/Docker-compose healthcheck 的标准做法,质量优先下必须采用。

#### A12-7. Task 12.3 Docker Compose 的资源限制配置不完整

当前只有 `backend` 有 memory: 800M。

**修法**: 所有服务都要有限制,避免单服务挤占导致全局崩:

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          memory: 4G       # 4C8G 基线下 backend 可以用 4G
          cpus: '2.0'
        reservations:
          memory: 1G
          cpus: '0.5'

  postgres:
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '0.5'
        reservations:
          memory: 256M

  redis:
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: '0.2'
    command: >
      redis-server
      --maxmemory 200mb
      --maxmemory-policy allkeys-lru
      --appendonly yes
      --appendfsync everysec

  nginx:
    deploy:
      resources:
        limits:
          memory: 128M
          cpus: '0.2'
```

另外,生产环境 Redis 必须 `appendonly yes` —— 熔断器状态、session ticket、permission answer 都在 Redis,重启丢失会导致非常难查的 bug。

---

## Part B — 架构级审视

### B5-I. Obs 覆盖面:必须从 3 Task 扩展到 6-7 Task

Batch 1 §3.4 决策: **Phase 1 Obs 完整子集**,包含 Prometheus 端点、OTel trace、结构化日志、Harness 仪表盘。当前 DOC-12 的 3 个 Task 远不够。

**建议新增 Task**:

#### (新) Task 12.4 — Prometheus Metrics 导出

```python
# backend/app/metrics/__init__.py
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest

# 每个关键行为一个 metric
registry = CollectorRegistry()

# Run 级
prism_runs_total = Counter(
    'prism_runs_total',
    '总 Run 数',
    ['status', 'agent_type', 'route_mode', 'provider'],
    registry=registry,
)
prism_run_duration_seconds = Histogram(
    'prism_run_duration_seconds',
    'Run 耗时',
    ['status', 'agent_type'],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1200, 1800],
    registry=registry,
)

# TAOR 级
prism_taor_turn_duration_seconds = Histogram(
    'prism_taor_turn_duration_seconds',
    'TAOR 单轮耗时',
    ['agent_type'],
    buckets=[0.5, 1, 2, 5, 10, 30, 60],
    registry=registry,
)
prism_taor_turns_per_run = Histogram(
    'prism_taor_turns_per_run',
    '每个 Run 的轮数',
    ['agent_type'],
    buckets=[1, 3, 5, 10, 20, 30, 50],
    registry=registry,
)

# 工具级
prism_tool_executions_total = Counter(
    'prism_tool_executions_total',
    '工具调用次数',
    ['tool_name', 'is_error', 'hook_modified', 'permission_decision'],
    registry=registry,
)
prism_tool_duration_seconds = Histogram(
    'prism_tool_duration_seconds',
    '工具执行耗时',
    ['tool_name'],
    registry=registry,
)

# Harness 级
prism_harness_events_total = Counter(
    'prism_harness_events_total',
    'Harness 事件',
    ['event_type', 'agent_type'],  # guardrail_trigger / permission_deny / permission_ask / loop_detected / compaction_tier_n / circuit_break / ...
    registry=registry,
)
prism_middleware_duration_seconds = Histogram(
    'prism_middleware_duration_seconds',
    'Middleware 单次执行耗时',
    ['middleware_name', 'phase'],  # phase: pre_turn / post_turn / pre_tool_use / post_tool_use
    registry=registry,
)
prism_hook_duration_seconds = Histogram(
    'prism_hook_duration_seconds',
    'Hook handler 耗时',
    ['event_type', 'handler_type'],  # handler_type: command / http / prompt / agent
    registry=registry,
)

# Model 级
prism_model_tokens_total = Counter(
    'prism_model_tokens_total',
    'Token 消耗',
    ['provider', 'model', 'type'],  # type: input / output / cache_hit / cache_miss / cache_creation
    registry=registry,
)
prism_model_cost_usd = Counter(
    'prism_model_cost_usd',
    '成本',
    ['provider', 'model'],
    registry=registry,
)
prism_model_request_duration_seconds = Histogram(
    'prism_model_request_duration_seconds',
    '模型请求耗时(到 first token)',
    ['provider', 'model'],
    registry=registry,
)

# Permission 级(针对 B2-1 ask 协议)
prism_permission_ask_wait_seconds = Histogram(
    'prism_permission_ask_wait_seconds',
    '人工审批等待时长',
    ['tool_name'],
    buckets=[1, 5, 10, 30, 60, 120, 300],
    registry=registry,
)
prism_permission_ask_resolution_total = Counter(
    'prism_permission_ask_resolution_total',
    '人工审批结果',
    ['tool_name', 'decision'],  # allow / deny / timeout
    registry=registry,
)

# Session 级
prism_sessions_active = Gauge(
    'prism_sessions_active',
    '活跃 Session 数',
    registry=registry,
)
prism_sse_connections = Gauge(
    'prism_sse_connections',
    'SSE 连接数',
    registry=registry,
)
prism_queue_depth = Gauge(
    'prism_queue_depth',
    '任务队列深度',
    registry=registry,
)

# Provider 级
prism_provider_healthy = Gauge(
    'prism_provider_healthy',
    'Provider 健康状态(1=healthy, 0=unhealthy)',
    ['provider_id', 'provider_name'],
    registry=registry,
)
prism_provider_failover_total = Counter(
    'prism_provider_failover_total',
    'Provider 故障转移次数',
    ['from_provider', 'to_provider'],
    registry=registry,
)

# IM 级(for DOC-08)
prism_im_messages_total = Counter(
    'prism_im_messages_total',
    'IM 消息数',
    ['channel', 'direction'],  # direction: incoming / outgoing
    registry=registry,
)
prism_im_webhook_duplicates_total = Counter(
    'prism_im_webhook_duplicates_total',
    'IM Webhook 重复消息拦截数(幂等命中)',
    ['channel'],
    registry=registry,
)

# 子进程级(for B3-2 心跳)
prism_agent_subprocess_running = Gauge(
    'prism_agent_subprocess_running',
    '运行中的 Agent 子进程数',
    registry=registry,
)
prism_agent_subprocess_crashed_total = Counter(
    'prism_agent_subprocess_crashed_total',
    'Agent 子进程崩溃次数',
    ['reason'],  # timeout / oom / panic / unknown
    registry=registry,
)
prism_agent_heartbeat_stale_total = Counter(
    'prism_agent_heartbeat_stale_total',
    '心跳失效次数',
    registry=registry,
)


@router.get("/metrics")
def prometheus_metrics(user: User = Depends(require_admin)):
    """Prometheus scrape 端点,仅 admin 可访问"""
    data = generate_latest(registry)
    return Response(content=data, media_type="text/plain; version=0.0.4")
```

#### (新) Task 12.5 — OTel 分布式 Tracing

```python
# executor/tracing/__init__.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

trace.set_tracer_provider(TracerProvider())
# 支持多种 exporter: OTLP / Jaeger / Zipkin / stdout
# 默认 stdout(零配置),生产可配置 OTLP collector endpoint

tracer = trace.get_tracer("prism")

# trace 上下文在 Backend ↔ 子进程之间通过回调 header 传递
# CLI 子进程启动时从环境变量读取 trace_id,保持链路连续

# 核心 span:
#   run (root)
#     ├── taor_turn (每一轮)
#     │     ├── prompt_assembly
#     │     ├── model_request
#     │     │     └── model_streaming (events)
#     │     ├── tool_use (每个工具)
#     │     │     ├── pre_tool_use_hooks
#     │     │     ├── permission_check
#     │     │     │     └── permission_ask (if asks)
#     │     │     ├── tool_execute
#     │     │     └── post_tool_use_hooks
#     │     └── middleware_chain
#     ├── compaction (when triggered)
#     └── fork_subagent (when applicable)
#           └── (recursive: taor_turn, ...)
```

关键 trace 标签:
- `run.id` / `session.id` / `user.id`
- `agent.type` / `route.mode`
- `tool.name` / `tool.is_error`
- `provider.name` / `model.id`
- `harness.guardrail_triggered` / `harness.permission_decision`

Backend 和子进程用 W3C TraceContext 头传递,确保跨进程 trace 连续。

#### (新) Task 12.6 — 结构化日志规范

```python
# backend/app/logging/__init__.py
import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.CallsiteParameterAdder(
            parameters={
                structlog.processors.CallsiteParameter.MODULE,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            }
        ),
        structlog.processors.JSONRenderer(),  # 所有日志 JSON 输出
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

# 使用约定:
logger = structlog.get_logger()
logger.info("run.started", run_id=run_id, session_id=session_id, user_id=user_id)
logger.warning("harness.guardrail_triggered", rule_id=..., tool_name=..., action=...)
logger.error("callback.failed", event_type=..., attempt=..., error=str(e), exc_info=True)

# 自动绑定上下文(contextvars)
structlog.contextvars.bind_contextvars(run_id=run_id, session_id=session_id)
# 后续该 context 内所有 log 都自动带上 run_id / session_id
```

日志级别规范:
- `DEBUG` — 细节调试,生产环境关闭
- `INFO` — 正常业务事件(Run 启动/完成、工具执行)
- `WARNING` — 非致命异常(回调重试、熔断触发)
- `ERROR` — 致命错误(Run crash、DB 连接断)
- `CRITICAL` — 系统级故障(所有 Provider 不通)

日志事件名约定: `{domain}.{action}` 格式
- `run.started` / `run.completed` / `run.failed` / `run.crashed`
- `harness.guardrail_triggered` / `harness.hook_fired` / `harness.permission_denied`
- `tool.executed` / `tool.failed` / `tool.timeout`
- `sse.connected` / `sse.disconnected` / `sse.message_sent`

#### (新) Task 12.7 — Frontend 错误上报通道

Batch 4 §B4-I 已提。简单版:

```python
@router.post("/api/v1/frontend-errors", dependencies=[Depends(get_current_user)])
async def report_frontend_error(body: FrontendErrorPayload, user: User = Depends(...)):
    """接收前端错误上报,写入 audit_logs,action=frontend.error"""
    await audit_service.log(
        user_id=user.id,
        action="frontend.error",
        details={
            "message": body.message[:500],
            "stack": body.stack[:2000] if body.stack else None,
            "url": body.url,
            "user_agent": body.user_agent,
            "viewport": body.viewport,  # desktop / mobile
            "session_id": body.session_id,
            "run_id": body.run_id,
            "severity": body.severity,  # error / warning / info
        },
    )
    return {"data": {"ok": True}}
```

配合 Prometheus 计数:
```python
prism_frontend_errors_total = Counter(
    'prism_frontend_errors_total',
    '前端上报错误数',
    ['severity', 'viewport'],
    registry=registry,
)
```

### B5-II. DOC-12 和 DOC-11 Task 11.4 的边界不清

DOC-11 Task 11.4 说"用量仪表盘与 Admin 面板",包含:
- 汇总卡片
- Provider 饼图
- 趋势折线
- 近 10 Run 详情(含 harness_summary 摘要)
- Admin 全局统计 / 用户列表 / 邀请码 / 审计日志

DOC-12 Task 12.2 说"Harness Summary 聚合 + Entropy Detection"。

**冲突点**:
- Harness summary 的 UI 在哪?(DOC-11 Task 11.4 没有 Harness 专属面板,只有"Run 详情里带 harness_summary 摘要")
- Entropy 告警的 UI 在哪?(DOC-11 里 completely 没提)
- 用量仪表盘的指标和 DOC-12 的 metrics 是什么关系?(DOC-11 说从 `/providers/usage` 拿,DOC-12 说从 `/admin/harness/*` 拿)

**修法**: 明文分工:

| 职责 | 归属文档 | API |
|---|---|---|
| Prometheus metrics 导出 | DOC-12 Task 12.4(新) | `GET /metrics` |
| Grafana dashboard 定义 | DOC-12 Task 12.4(新) | 配置文件随 docker-compose 分发 |
| Harness 数据聚合 | DOC-12 Task 12.2 | `GET /api/v1/admin/harness/analytics` |
| Entropy 检测结果 | DOC-12 Task 12.2 | `GET /api/v1/admin/entropy/alerts` |
| 单 Run 的 harness_summary | DOC-11 Task 11.4 | `GET /runs/{id}` |
| 前端用量仪表盘 UI | DOC-11 Task 11.4 | 消费 `/admin/harness/analytics` + `/providers/usage` |
| 前端 Harness 面板 UI | DOC-11 Task 11.5(新增) | 消费 `/admin/harness/analytics` |
| 前端 Entropy 告警 UI | DOC-11 Task 11.5(新增) | 消费 `/admin/entropy/alerts` |

DOC-11 需要补一个 **Task 11.6 (Admin Observability 面板)**,和 Task 11.4 的用户用量仪表盘区分开来。

### B5-III. "2C2G 约束"已过时,全文需要改

DOC-12 开头: "内存用量监控(2C2G 约束)"。

**Batch 1 决策**: 4C8G 基线。

**修法**: DOC-12 所有"2C2G"字样改为"资源预算基线(默认 4C8G,可通过环境变量配置)",相关阈值也按 §A12-2 调整。

### B5-IV. 告警渠道完全缺失

Entropy 检测产生告警,**告警去哪了**?

Task 12.2 只说"写入 audit_logs(action: harness.entropy_alert)+ 可选通知 Admin"。

**可选通知 Admin** 是什么意思?SSE 推送?邮件?飞书消息?没有定义。

**修法**: 告警通道明文定义:

```python
# backend/app/services/alert_dispatcher.py

class AlertDispatcher:
    """
    告警分发器 — 统一告警出口
    
    告警源: EntropyDetector / ResourceMonitor / FailoverMonitor / ...
    告警目标(按严重级别):
      info    → audit_logs only
      warning → audit_logs + SSE 推给在线 admin(如果 admin 在线)
      critical → audit_logs + SSE + IM 通知(如果配置了 IM 告警通道)+ 邮件(如果配置了)
    """
    
    async def dispatch(self, alert: Alert) -> None:
        # 1. audit_logs 永远写
        await self._audit.log(...)
        
        # 2. SSE 推送(通过专属 channel: `admin-alerts:{admin_user_id}`)
        if alert.severity in ("warning", "critical"):
            await self._sse.push_to_admins(alert)
        
        # 3. critical 额外渠道
        if alert.severity == "critical":
            if self._im_alert_channel_configured:
                await self._im.send_alert(alert)
            if self._email_configured:
                await self._email.send_alert(alert)
```

IM 告警通道复用 DOC-08 的 IM Gateway(飞书/企微/TG),admin 可在 settings 里配置"把 critical 告警发到 XX 群"。

### B5-V. Grafana Dashboard 配置也要交付

Batch 1 §3.4 提到"Docker Compose 加 Grafana + Prometheus,开箱即用的仪表盘"。

**当前 DOC-12 完全没写**。

**修法**: Task 12.4(新)必须交付:
- `docker-compose.monitoring.yml` (可选叠加的 compose file)
  - `prometheus:latest`
  - `grafana:latest`
  - prometheus 配置文件(scrape 到 backend:8000/metrics)
- `monitoring/grafana/dashboards/` 目录
  - `prism-overview.json` — 总览(Runs/s、Errors/s、P95 latency、活跃 Session 数)
  - `prism-harness.json` — Harness 专属(guardrail / permission / hook 事件)
  - `prism-models.json` — Model 专属(tokens / cost / cache / provider health)
  - `prism-agents.json` — Agent 生命周期(子进程 / fork / background)
- `monitoring/grafana/provisioning/` 自动配置(datasource + dashboard 自动 import)

开箱即用的意思是 `docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up` 后,打开 `localhost:3001` 就能看到完整 Grafana 面板,不需要任何手动配置。

---

## Part C — v3.1 新增评估

DOC-12 在 v3.1 修订中**没有新增 Task**,只是小幅修补(ADR 重编号 + 窗口修复)。

我在 Part B 新增了 4 个 Task 建议(12.4 / 12.5 / 12.6 / 12.7),这些是质量优先下的**必须补齐**,不是 optional。

---

## 总结 & 对改写阶段的影响

### Batch 5 问题量

- **实现级 (Part A)**: 7 项
- **架构级 (Part B)**: 5 项(其中 B5-I 要求新增 4 个 Task)

### 对改写阶段的关键影响

1. **DOC-12 需要大幅扩充**: 从 3 Task 增加到 7 Task(TokenEstimator / Entropy / Health + Prometheus / OTel / 结构化日志 / Frontend 上报)
2. **DOC-11 要补 Task 11.6**: Admin Observability 面板,消费 DOC-12 的 API
3. **DOC-01 Schema 要加字段**: `runs.harness_version` / Observability 相关索引
4. **整个 PRD 体系都要引用结构化日志**: 每个 Task 的 Part B 不再写 `print()`,统一用 `logger = structlog.get_logger()`
5. **每个 Task 的 Part B 要加 metrics 采集点**: 涉及 middleware / hook / guardrail / model request / tool execute 的地方,必须有 prometheus_client 调用

### 对 master review 的关键输入

- **Obs 基础设施是 Phase 1 bedrock**,不能有"Phase 2 再说"的理念
- **Frontend 侧也要参与 Obs**: 错误上报、性能监控、UX 指标
- **Dashboard 和 Playbook 是 Prism 产品的一部分**,不是开发者额外的选修
- **告警通道是运营必需**,单靠 audit_logs 查不出来"最近系统有没有异常"

---

> **本 Batch 覆盖**: DOC-12 (27KB) + 新增 4 个 Task 设计建议 = ~40KB
> **下一步**: `review-master.md` — 跨 Batch 总 review + 改写优先级 + 先导文档规划
