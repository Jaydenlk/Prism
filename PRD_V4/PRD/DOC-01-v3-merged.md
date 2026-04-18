# Prism 棱镜 v2 — 系统架构 (DOC-01)

> **文档编号**: DOC-01  
> **版本**: 3.1（Harness-Native 融合版）  
> **日期**: 2026-04-02  
> **性质**: 技术蓝图 — 定义所有模块共用的"骨架"，是 DOC-02 至 DOC-12 的基础  
> **前置依赖**: DOC-00 Vision and Principles v3  
> **本文档不包含代码实现，仅定义架构、数据模型和接口契约**

---

## 目录

1. [五层架构总图](#1-五层架构总图)
2. [服务拓扑](#2-服务拓扑)
3. [进程模型与 Agent 执行策略](#3-进程模型与-agent-执行策略)
4. [数据库 Schema 全量设计](#4-数据库-schema-全量设计)
5. [PrismMessage 内部消息格式](#5-prismmessage-内部消息格式)
6. [API 路由总表](#6-api-路由总表)
7. [SSE 事件协议 v2](#7-sse-事件协议-v2)
8. [目录结构](#8-目录结构)
9. [跨层通信契约](#9-跨层通信契约)
10. [Harness 状态存储策略](#10-harness-状态存储策略)
11. [部署双模](#11-部署双模)

---

## 1. 五层架构总图

从 v2 的 4 层升级为 5 层，新增 Harness Runtime 作为独立核心层（对标 CC 源码的 Layer 2 Runtime）：

```
┌──────────────────────────────────────────────────────────────────┐
│                 Layer 1: Entrypoints (入口层)                      │
│                                                                  │
│  ┌─────────┐  ┌───────────┐  ┌────────────┐  ┌───────────────┐ │
│  │ Web UI  │  │  REST API │  │ SSE Stream │  │  IM Gateway   │ │
│  │ (Next.js)│  │ (FastAPI) │  │  (Redis)   │  │ (飞书/企微/TG)│ │
│  └─────────┘  └───────────┘  └────────────┘  └───────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│                 Layer 2: Orchestration (编排层)                    │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ TaskScheduler │  │ RunLifecycle │  │ SessionQueueManager    │ │
│  │ (子进程调度)   │  │ (状态机)      │  │ (队列推进 + promote)   │ │
│  └──────────────┘  └──────────────┘  └────────────────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│          Layer 3: Harness Runtime (Harness 运行时层) ⚡新增        │
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐ │
│  │ MiddlewarePipeline│  │ HookSystem       │  │ PermissionEng │ │
│  │ (可插拔中间件链)   │  │ (21 事件 × 4 handler)│ │ (分层权限模型) │ │
│  ├──────────────────┤  ├──────────────────┤  ├───────────────┤ │
│  │ GuardrailsEngine │  │ LifecycleCtrl    │  │ CircuitBreaker│ │
│  │ (平台级+插件级)    │  │ (TAOR Loop 治理)  │  │ (熔断 + 恢复) │ │
│  └──────────────────┘  └──────────────────┘  └───────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│             Layer 4: Agent & Engine Core (Agent 引擎层)            │
│                                                                  │
│  ┌───────────────┐  ┌──────────────────┐  ┌──────────────────┐ │
│  │ QueryEngine   │  │ PromptAssembler  │  │ ToolExecution    │ │
│  │ (TAOR 主循环)  │  │ (Prompt 动态装配) │  │ Pipeline         │ │
│  ├───────────────┤  ├──────────────────┤  ├──────────────────┤ │
│  │ AgentPool     │  │ ForkManager      │  │ PluginHost       │ │
│  │ (专业化 Agent) │  │ (上下文隔离)      │  │ (Skill/Hook/MCP) │ │
│  ├───────────────┤  ├──────────────────┤  └──────────────────┘ │
│  │ ContextBudget │  │ CompactionPipe   │                       │
│  │ Manager       │  │ (4 级渐进压缩)    │                       │
│  └───────────────┘  └──────────────────┘                       │
├──────────────────────────────────────────────────────────────────┤
│              Layer 5: Infrastructure (基础设施层)                   │
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐ │
│  │ AnthropicDriver  │  │ OpenAIDriver     │  │ ProviderMgr   │ │
│  │ (Messages API)   │  │ (Chat Completions)│  │ (预设/故障转移) │ │
│  └──────────────────┘  └──────────────────┘  └───────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

**层间通信规则**：每一层只与直接相邻层通信。Layer 1 不直接调用 Layer 4，必须通过 Layer 2 + Layer 3。Layer 5 不直接向 Layer 1 推送数据，必须通过 Layer 4 → Layer 3 的回调链。

**Layer 3 与 Layer 4 的职责边界**：
- **Layer 3 Harness Runtime** 负责"治理"——决定 Agent 能做什么、不能做什么、做完之后如何验证。它是规则层。
- **Layer 4 Agent Engine** 负责"执行"——实际驱动模型对话、拼装 Prompt、调用工具、管理上下文。它是能力层。
- 类比：Layer 3 是操作系统的安全模块和进程调度器，Layer 4 是实际运行的应用程序。

---

## 2. 服务拓扑

### 2.1 生产拓扑（4 个 Docker 服务）

```
                    ┌─────────┐
         Internet ──┤  nginx  ├── :80 / :443
                    └────┬────┘
                         │
              ┌──────────┼──────────┐
              │          │          │
         /api/v1/*  /sse/*    /*（前端静态）
              │          │          │
              ▼          ▼          ▼
         ┌─────────────────────────────┐
         │         backend             │
         │     FastAPI :8000           │
         │  ┌─────────────────────┐   │
         │  │ Harness Runtime     │   │  ← Layer 3 在 Backend 进程内
         │  │ (Middleware + Hooks) │   │
         │  └─────────────────────┘   │
         │  ┌─────────────────────┐   │
         │  │  CLI 子进程 (Agent)  │   │  ← Layer 3-5 在子进程内
         │  │  按任务按需启动      │   │
         │  └─────────────────────┘   │
         └──────┬──────────┬──────────┘
                │          │
           ┌────▼────┐ ┌──▼───┐
           │postgres │ │redis │
           │  :5432  │ │:6379 │
           └─────────┘ └──────┘
```

### 2.2 服务职责

| 服务 | 技术 | 职责 | 资源预算(2C2G) |
|------|------|------|---------------|
| **nginx** | Nginx latest | 反向代理、SSL 终止、前端静态文件、SSE 透传（`X-Accel-Buffering: no`） | ~10MB |
| **backend** | FastAPI + Python 3.12 | REST API + 编排层 + Harness Runtime（API 侧） + Agent Runtime + 模型适配 + IM Gateway | ~200MB 空闲，峰值 ~600MB |
| **postgres** | PostgreSQL 16 | 所有持久化数据（含 Harness 审计轨迹） | ~100MB 空闲 |
| **redis** | Redis 7 | SSE pub/sub + Session 缓存 + Harness 运行时状态（中间件状态、熔断计数器、Loop 检测窗口） | ~30MB |

**总计空闲**: ~340MB。2GB 内存下留有充裕余量供 Agent 子进程使用。

### 2.3 与 v1 对比

| v1 | v2 | 变化 |
|----|----|----- |
| 6 服务（backend + executor + executor_manager + postgres + redis + nginx） | 4 服务 | 去掉 executor 和 executor_manager |
| Executor 独立 Docker 容器，冷启动 2-5s | CLI 子进程，启动 200-500ms | 首 token 延迟大幅降低 |
| Docker Socket 权限依赖 | 无特殊权限需求 | 安全性提升 |
| 无 Harness 层 | Harness Runtime 内建于 Backend + CLI 子进程 | Agent 可靠性质变 |

---

## 3. 进程模型与 Agent 执行策略

### 3.1 任务执行流程（含 Harness）

```
POST /api/v1/tasks
    │
    ▼
TaskScheduler.enqueue_task()                          ← Layer 2: Orchestration
    ├─ Session 空闲？
    │   YES → 创建 AgentRun → 启动 CLI 子进程
    │
    └─ Session 有 blocking_run？
        → session_queue_items.enqueue()
        → 返回 {accepted_type: "queued_query"}
        → 等待当前 Run 完成后自动 promote

CLI 子进程启动
    │
    ▼
python -m prism.executor --run-id={run_id}
    │
    ▼
AgentExecutor 初始化                                   ← Layer 3-5 初始化
    ├─ 从 DB 读取 Run 配置（model, provider, plugins, prompt）
    ├─ 初始化 Harness Runtime                          ⚡ 新增
    │   ├─ 加载 MiddlewarePipeline（注册所有中间件）
    │   ├─ 加载 HookSystem（解析 settings + plugin hooks）
    │   ├─ 初始化 PermissionEngine（平台级 + 插件级护栏）
    │   ├─ 初始化 GuardrailsEngine（声明式规则加载）
    │   ├─ 初始化 CircuitBreaker（从 Redis 恢复熔断状态）
    │   └─ 触发 SessionStart Hook
    ├─ 初始化 PromptAssembler
    ├─ 初始化 ToolExecutionPipeline（关联 Harness 的 Hook + Permission）
    ├─ 加载 Plugin Host（Skills + Hooks + MCP）
    ├─ 选择 Agent 类型（General / Planner / Research / Verifier）
    │
    ▼
QueryEngine.run() — TAOR 主循环                        ← Layer 4 执行，Layer 3 治理
    ├─ [Middleware] ContextEnrichmentMW 前处理
    ├─ 构造 System Prompt（PromptAssembler.build()）
    ├─ [Middleware] LoopDetectionMW 检查（是否重复调用相同工具+参数）
    ├─ 调用 ModelAdapter.stream()                      ← Layer 5
    ├─ 解析模型响应（text / tool_use）
    ├─ 工具调用 → [Harness] PreToolUse Hook → PermissionEngine 决策
    │   → ToolExecutionPipeline.execute()
    │   → [Harness] PostToolUse Hook → OutputValidationMW
    ├─ [Middleware] FeedbackCaptureMW 记录执行结果
    ├─ [Middleware] ObservabilityMW 写 trace
    ├─ 回调 Backend → POST /api/v1/internal/callbacks
    │   → 持久化消息 + SSE 推送 + 状态更新
    ├─ [Harness] CompactionCheck → 4 级策略触发
    ├─ 循环直到模型返回 end_turn 或达到 max_turns
    │
    ▼
Run 完成
    ├─ [Harness] 触发 SessionEnd Hook
    ├─ 最终回调（status: completed/failed）
    ├─ SessionQueueManager.promote_next()
    └─ 子进程退出
```

> **Sync/Async 分界**：Backend（FastAPI）层使用 async def 处理 HTTP 请求，DB 操作使用 SQLAlchemy 2.0 sync Session（在 async 路由中通过 `run_in_executor` 或独立线程运行同步 DB 调用）。Executor（CLI 子进程）内部使用同步执行模型（TAOR 主循环为同步 while loop），仅在 MCP 通信和模型 API 调用时使用 async。Executor 运行时**不直接访问 DB**，所有持久化通过 HTTP 回调委托给 Backend。

### 3.2 子进程隔离策略

| 隔离维度 | 措施 |
|---------|------|
| 文件系统 | 每个任务分配 `/workspace/{run_id}/`，任务结束后可选清理 |
| 用户权限 | 子进程以降权用户 `prism-executor` (uid 1001) 运行 |
| 网络 | 子进程继承 backend 容器的网络，仅可访问容器内网 + 模型 API |
| 内存 | 不做硬限制，通过 max_turns 和 context budget 间接控制 |
| 超时 | 单次 Run 最长执行时间可配置（默认 10 分钟），超时强制 kill |
| Harness 状态 | 子进程内的 Harness Runtime 独立实例，熔断状态通过 Redis 共享 |

### 3.3 并发控制

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `MAX_CONCURRENT_RUNS` | 2 | 同时运行的 Agent 子进程数上限 |
| `RUN_TIMEOUT_SECONDS` | 600 | 单次 Run 最长执行时间 |
| `QUEUE_MAX_SIZE` | 20 | 单个 Session 的排队消息上限 |
| `MAX_TURNS_PER_RUN` | 50 | 单次 Run 的 TAOR 循环上限（防失控） |
| `LOOP_DETECTION_WINDOW` | 5 | 检测重复工具调用的滑动窗口大小 |

超过并发上限时，新任务进入全局等待队列，按 FIFO 调度。

---

## 4. 数据库 Schema 全量设计

### 4.1 设计原则

- 所有主键使用 **UUIDv7**（时间有序，可排序，全局唯一）
- 所有表包含 `created_at` 和 `updated_at` 时间戳（UTC, timezone-aware）
- JSON 字段使用 PostgreSQL `JSONB` 类型
- 外键显式声明，`ON DELETE` 行为明确
- 所有涉及用户数据的查询强制 `WHERE user_id = :current_user_id`（铁律 4）
- Harness 运行时状态（高频低持久）存 Redis，Harness 审计轨迹（低频高持久）存 audit_logs

### 4.2 表清单（Phase 1，14 张表）

> Harness 状态存储策略见 §10。Phase 1 不新增专用 Harness 表，Harness 审计事件通过 `audit_logs` 表的 `action` 字段区分（如 `harness.guardrail_trigger`、`harness.hook_fire`、`harness.circuit_break`）。

#### 用户域

**users**

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | UUID v7 | PK | 用户 ID |
| email | VARCHAR(255) | UNIQUE NOT NULL | 登录邮箱 |
| username | VARCHAR(50) | UNIQUE NOT NULL | 显示名 |
| password_hash | VARCHAR(255) | NOT NULL | bcrypt hash |
| role | VARCHAR(20) | NOT NULL DEFAULT 'user' | 'admin' \| 'user' |
| avatar_url | VARCHAR(500) | NULL | 头像地址 |
| last_login_at | TIMESTAMPTZ | NULL | 最后登录时间 |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

**invite_codes**

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | UUID v7 | PK | |
| code | VARCHAR(20) | UNIQUE NOT NULL | 邀请码 |
| created_by | UUID | FK → users.id | 创建者 |
| max_uses | INT | NOT NULL DEFAULT 1 | 最大使用次数 |
| used_count | INT | NOT NULL DEFAULT 0 | 已使用次数 |
| expires_at | TIMESTAMPTZ | NULL | 过期时间，NULL 表示永不过期 |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

#### 会话域

**sessions**

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | UUID v7 | PK | Session ID |
| user_id | UUID | FK → users.id ON DELETE CASCADE | 所属用户 |
| title | VARCHAR(200) | NULL | 会话标题（可由 Agent 自动生成） |
| status | VARCHAR(20) | NOT NULL DEFAULT 'idle' | 'idle' \| 'running' \| 'queued' |
| blocking_run_id | UUID | FK → runs.id NULL | 当前正在执行的 Run |
| config_snapshot | JSONB | NOT NULL DEFAULT '{}' | 运行时配置快照（model, provider, plugins, mcp） |
| is_pinned | BOOLEAN | NOT NULL DEFAULT false | 是否置顶 |
| pinned_at | TIMESTAMPTZ | NULL | 置顶时间 |
| im_channel | VARCHAR(50) | NULL | 来源 IM 渠道（'feishu' \| 'wecom' \| 'telegram' \| NULL） |
| im_chat_id | VARCHAR(200) | NULL | IM 平台的会话标识 |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

索引：`(user_id, updated_at DESC)`, `(user_id, is_pinned, updated_at DESC)`

**session_queue_items**

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | UUID v7 | PK | |
| session_id | UUID | FK → sessions.id ON DELETE CASCADE | |
| prompt | TEXT | NOT NULL | 排队的用户消息 |
| status | VARCHAR(20) | NOT NULL DEFAULT 'queued' | 'queued' \| 'promoted' \| 'cancelled' |
| sequence_no | INT | NOT NULL | 队列内顺序号 |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

索引：`(session_id, status, sequence_no)`

#### 执行域

**runs**

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | UUID v7 | PK | Run ID |
| session_id | UUID | FK → sessions.id ON DELETE CASCADE | |
| user_id | UUID | FK → users.id | 冗余字段，避免 JOIN |
| prompt | TEXT | NOT NULL | 本次 Run 的用户输入 |
| status | VARCHAR(20) | NOT NULL DEFAULT 'pending' | 'pending' \| 'running' \| 'completed' \| 'failed' \| 'cancelled' \| 'timeout' |
| model | VARCHAR(100) | NOT NULL | 使用的模型标识 |
| provider_id | UUID | FK → providers.id | 使用的 Provider |
| schedule_mode | VARCHAR(20) | NOT NULL DEFAULT 'immediate' | 'immediate' \| 'queued' |
| error_message | TEXT | NULL | 失败时的错误信息 |
| input_tokens | INT | NULL | 输入 token 数 |
| output_tokens | INT | NULL | 输出 token 数 |
| cost_usd | DECIMAL(10,6) | NULL | 本次调用成本 |
| turn_count | INT | NULL | TAOR 循环次数 |
| harness_summary | JSONB | NULL | Harness 运行摘要（guardrail 触发次数、hook 执行次数、compaction 次数等） |

> `harness_summary` JSONB 示例：
> ```json
> {
>   "guardrail_triggers": [{"rule_id": "GR-001", "action": "block", "tool": "bash", "reason": "检测到 rm -rf"}],
>   "permission_denials": [{"tool": "file_delete", "decision": "deny"}],
>   "loop_detections": 0,
>   "compaction_level": 2,
>   "middleware_stats": {"loop_detection": {"checks": 15}, "rate_limit": {"throttled": 0}},
>   "total_tool_calls": 8,
>   "total_turns": 12
> }
> ```

| started_at | TIMESTAMPTZ | NULL | 实际开始执行时间 |
| finished_at | TIMESTAMPTZ | NULL | 执行结束时间 |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

索引：`(session_id, created_at DESC)`, `(user_id, created_at DESC)`, `(status)` WHERE status = 'pending'

> ⚡ `turn_count` 和 `harness_summary` 是新增字段。`harness_summary` 在 Run 完成时由 Harness Runtime 写入，记录本次执行的治理统计（护栏触发、Hook 执行、Compaction 触发、Loop Detection 命中等），供 Observability 和 Entropy Detection 使用。

**messages**

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | UUID v7 | PK | |
| session_id | UUID | FK → sessions.id ON DELETE CASCADE | |
| run_id | UUID | FK → runs.id ON DELETE CASCADE NULL | 系统消息可无 run_id |
| role | VARCHAR(20) | NOT NULL | 'user' \| 'assistant' \| 'tool_use' \| 'tool_result' \| 'system' |
| content | JSONB | NOT NULL | PrismMessage 格式 |
| text_preview | VARCHAR(500) | NULL | 纯文本预览（供列表显示、搜索） |
| sequence_no | INT | NOT NULL | Session 内全局顺序号 |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

索引：`(session_id, sequence_no)`, `(run_id)`

**tool_executions**

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | UUID v7 | PK | |
| session_id | UUID | FK → sessions.id ON DELETE CASCADE | |
| run_id | UUID | FK → runs.id ON DELETE CASCADE | |
| tool_name | VARCHAR(100) | NOT NULL | 工具全名（含前缀） |
| input | JSONB | NOT NULL | 工具输入参数 |
| output | JSONB | NULL | 工具输出 |
| is_error | BOOLEAN | NOT NULL DEFAULT false | 是否执行失败 |
| duration_ms | INT | NULL | 执行耗时 |
| permission_decision | VARCHAR(20) | NULL | Harness 权限决策（'allow' \| 'deny' \| 'ask'） |
| hook_modified | BOOLEAN | NOT NULL DEFAULT false | 是否被 Hook 改写了 input |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

> ⚡ `permission_decision` 和 `hook_modified` 是新增字段，记录 Harness 对该工具调用的治理决策。

#### 模型 & Provider 域

**providers**

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | UUID v7 | PK | |
| user_id | UUID | FK → users.id ON DELETE CASCADE | 所属用户（system provider 的 user_id 为 admin） |
| name | VARCHAR(100) | NOT NULL | 显示名（如 "MiniMax M2.7"） |
| protocol | VARCHAR(20) | NOT NULL | 'anthropic' \| 'openai' |
| base_url | VARCHAR(500) | NOT NULL | API 端点 |
| api_key_encrypted | TEXT | NOT NULL | AES-256 加密存储的 API Key |
| model_id | VARCHAR(100) | NOT NULL | 模型标识（如 "MiniMax-M2.7"） |
| is_default | BOOLEAN | NOT NULL DEFAULT false | 是否为该用户的默认 Provider |
| priority | INT | NOT NULL DEFAULT 0 | 故障转移优先级（0 为最高） |
| is_healthy | BOOLEAN | NOT NULL DEFAULT true | 健康状态（熔断时置 false） |
| config | JSONB | NOT NULL DEFAULT '{}' | 额外配置（max_tokens, temperature 等） |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

索引：`(user_id, is_default)`, `(user_id, priority)`

#### MCP 域

**mcp_servers**

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | UUID v7 | PK | |
| name | VARCHAR(100) | NOT NULL | MCP Server 名称 |
| description | TEXT | NULL | 说明 |
| scope | VARCHAR(20) | NOT NULL DEFAULT 'system' | 'system'（内置）\| 'user'（用户自定义） |
| command | VARCHAR(500) | NOT NULL | 启动命令 |
| args | JSONB | NOT NULL DEFAULT '[]' | 命令参数 |
| env | JSONB | NOT NULL DEFAULT '{}' | 环境变量 |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

**user_mcp_installs**

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | UUID v7 | PK | |
| user_id | UUID | FK → users.id ON DELETE CASCADE | |
| mcp_server_id | UUID | FK → mcp_servers.id ON DELETE CASCADE | |
| is_enabled | BOOLEAN | NOT NULL DEFAULT true | 是否启用 |
| config_override | JSONB | NOT NULL DEFAULT '{}' | 用户级配置覆盖 |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

唯一约束：`(user_id, mcp_server_id)`

#### IM 域

**im_bindings**

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | UUID v7 | PK | |
| user_id | UUID | FK → users.id ON DELETE CASCADE | Prism 用户 |
| channel | VARCHAR(50) | NOT NULL | 'feishu' \| 'wecom' \| 'telegram' |
| platform_user_id | VARCHAR(200) | NOT NULL | IM 平台的用户标识 |
| platform_chat_id | VARCHAR(200) | NULL | IM 平台的会话标识（群聊场景） |
| display_name | VARCHAR(100) | NULL | IM 平台显示名 |
| pairing_code | VARCHAR(10) | NULL | 配对码（绑定前临时生成） |
| paired_at | TIMESTAMPTZ | NULL | 绑定完成时间 |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

唯一约束：`(channel, platform_user_id)`

**im_channel_configs**

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | UUID v7 | PK | |
| channel | VARCHAR(50) | UNIQUE NOT NULL | 'feishu' \| 'wecom' \| 'telegram' |
| is_enabled | BOOLEAN | NOT NULL DEFAULT false | 是否启用 |
| config | JSONB | NOT NULL DEFAULT '{}' | 渠道配置（app_id, app_secret, bot_token 等） |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

#### 审计域

**audit_logs**

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | UUID v7 | PK | |
| user_id | UUID | FK → users.id NULL | 系统事件可无 user_id |
| action | VARCHAR(100) | NOT NULL | 操作类型（含 Harness 事件前缀 `harness.*`） |
| resource_type | VARCHAR(50) | NULL | 资源类型（session, run, provider, harness 等） |
| resource_id | UUID | NULL | 资源 ID |
| details | JSONB | NOT NULL DEFAULT '{}' | 操作详情 |
| ip_address | VARCHAR(45) | NULL | 来源 IP |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

索引：`(user_id, created_at DESC)`, `(action, created_at DESC)`

> ⚡ Harness 事件的 `action` 命名约定：`harness.guardrail_trigger`、`harness.hook_fire`、`harness.permission_deny`、`harness.circuit_break`、`harness.loop_detected`、`harness.compaction_trigger`。`details` JSONB 包含事件上下文（触发规则、工具名、Agent 类型等）。

### 4.3 表关系图

```
users ─────┬──── sessions ─────┬──── session_queue_items
           │         │         │
           │         └──── runs ────── messages
           │                │
           │                └──── tool_executions
           │
           ├──── invite_codes
           ├──── providers
           ├──── user_mcp_installs ──── mcp_servers
           ├──── im_bindings
           └──── audit_logs (含 harness.* 事件)

im_channel_configs (独立，全局配置)
```

---

## 5. PrismMessage 内部消息格式

Prism 内部使用统一的消息格式 `PrismMessage`，与具体模型厂商 API 解耦。两个 Driver（Anthropic / OpenAI）各自负责 `PrismMessage ↔ 厂商格式` 的双向转换。

### 5.1 PrismMessage 结构

```python
@dataclass
class PrismMessage:
    role: Literal["user", "assistant", "tool_result"]
    content: list[ContentBlock]
    
@dataclass
class TextBlock:
    type: Literal["text"] = "text"
    text: str

@dataclass
class ToolUseBlock:
    type: Literal["tool_use"] = "tool_use"
    id: str           # 工具调用 ID（UUIDv7）
    name: str          # 工具名称
    input: dict        # 工具输入参数

@dataclass
class ToolResultBlock:
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str   # 对应的 ToolUseBlock.id
    content: str       # 工具输出（纯文本或 JSON 字符串）
    is_error: bool = False

ContentBlock = TextBlock | ToolUseBlock | ToolResultBlock
```

### 5.2 数据库存储

`messages.content` 列存储 `PrismMessage.content` 序列化后的 JSONB。示例：

用户消息：
```json
[{"type": "text", "text": "帮我搜索一下 GitHub 上的 prism 项目"}]
```

Assistant 消息（含工具调用）：
```json
[
  {"type": "text", "text": "我来帮你搜索 GitHub 上的 prism 项目。"},
  {"type": "tool_use", "id": "019...", "name": "search__web_search", "input": {"query": "prism github"}}
]
```

工具结果：
```json
[
  {"type": "tool_result", "tool_use_id": "019...", "content": "{\"results\": [...]}", "is_error": false}
]
```

### 5.3 与厂商格式的映射

| PrismMessage | Anthropic Messages API | OpenAI Chat Completions |
|-------------|----------------------|------------------------|
| role: "user" | role: "user" | role: "user" |
| role: "assistant" + TextBlock | role: "assistant", content[{type:"text"}] | role: "assistant", content: string |
| role: "assistant" + ToolUseBlock | content[{type:"tool_use"}] | tool_calls[{type:"function"}] |
| role: "tool_result" | role: "user", content[{type:"tool_result"}] | role: "tool", tool_call_id: ... |

详细转换逻辑在 DOC-02 中定义。

---

## 6. API 路由总表

所有 API 以 `/api/v1` 为前缀。认证：除标注 `public` 外，所有端点需要 JWT Bearer Token。

### 6.1 认证 (DOC-06)

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | /auth/register | 注册（需邀请码） | public |
| POST | /auth/login | 登录 | public |
| POST | /auth/refresh | 刷新 token | cookie |
| POST | /auth/logout | 登出 | bearer |
| GET | /auth/me | 当前用户信息 | bearer |

### 6.2 会话 (DOC-07)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /sessions | 会话列表（分页，按 updated_at DESC） |
| POST | /sessions | 创建空会话 |
| GET | /sessions/{id} | 获取会话详情 |
| PATCH | /sessions/{id} | 更新会话（title, is_pinned, config） |
| DELETE | /sessions/{id} | 删除会话（级联删除所有消息和 Run） |
| GET | /sessions/{id}/messages | 消息列表（支持 after_message_id 增量查询） |

### 6.3 任务 (DOC-07)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /tasks | 提交任务（核心入口，创建或复用 Session → 创建 Run 或入队） |
| GET | /sessions/{id}/queue | 获取队列消息 |
| DELETE | /sessions/{id}/queue/{item_id} | 取消排队消息 |
| POST | /sessions/{id}/cancel | 取消当前正在执行的 Run |

### 6.4 Run (DOC-07)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /runs/{id} | Run 详情（含 harness_summary） |
| GET | /sessions/{id}/runs | Session 下的 Run 列表 |

### 6.5 SSE (DOC-07)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /sessions/{id}/stream?token={jwt} | SSE 事件流（JWT 通过 query param 传递） |

### 6.6 Provider (DOC-09)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /providers | 当前用户的 Provider 列表 |
| POST | /providers | 创建 Provider |
| PATCH | /providers/{id} | 更新 Provider |
| DELETE | /providers/{id} | 删除 Provider |
| GET | /providers/presets | 内置 Provider 预设列表 |
| POST | /providers/{id}/test | 测试 Provider 连通性 |

### 6.7 MCP (DOC-09)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /mcp-servers | MCP Server 列表（含 system + user） |
| POST | /mcp-servers | 创建自定义 MCP Server |
| GET | /mcp-installs | 当前用户的 MCP 安装列表 |
| POST | /mcp-installs | 安装/启用 MCP Server |
| PATCH | /mcp-installs/{id} | 更新安装配置 |
| DELETE | /mcp-installs/{id} | 卸载 MCP Server |

### 6.8 IM (DOC-08)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /im/channels | 已配置的 IM 渠道列表 |
| PATCH | /im/channels/{channel} | 更新渠道配置（admin only） |
| GET | /im/bindings | 当前用户的 IM 绑定列表 |
| POST | /im/bindings/pair | 生成配对码 |
| DELETE | /im/bindings/{id} | 解除绑定 |
| POST | /im/webhook/feishu | 飞书事件回调（public，平台验证） |
| POST | /im/webhook/wecom | 企业微信事件回调（public，平台验证） |

Telegram 使用 Long Polling 模式，不需要 Webhook 端点。

### 6.9 Admin (DOC-09)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /admin/users | 用户列表 |
| PATCH | /admin/users/{id} | 更新用户角色 |
| POST | /admin/invite-codes | 生成邀请码 |
| GET | /admin/invite-codes | 邀请码列表 |
| DELETE | /admin/invite-codes/{id} | 撤销邀请码 |
| GET | /admin/usage | 全局用量统计 |
| GET | /admin/audit-logs | 审计日志查询（含 Harness 事件筛选） |

### 6.10 Harness (DOC-12) ⚡新增

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /harness/status | Harness 运行时状态（活跃中间件、熔断器状态、护栏规则数） |
| GET | /harness/traces | Harness 审计轨迹查询（from audit_logs where action like 'harness.%'） |
| GET | /runs/{id}/harness-summary | 指定 Run 的 Harness 执行摘要 |
| GET | /harness/config | 当前有效配置（含 source_trace）— admin only |
| PATCH | /harness/config | 更新配置（写入 DB）— admin only |
| POST | /harness/config/reload | 强制重载所有配置源 — admin only |
| GET | /harness/analytics | Harness 数据聚合 — admin only |
| POST | /harness/entropy-check | 触发熵检测 — admin only |

### 6.12 Skills Market (DOC-05)

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | /skills/search | 跨源搜索 Skills（?q=...&source=...） | bearer |
| GET | /skills/installed | 已安装 Skills 列表 | bearer |
| POST | /skills/install | 安装 Skill（{package_id, source, version?}） | bearer |
| DELETE | /skills/{name} | 卸载 Skill | bearer |
| POST | /skills/{name}/update | 更新 Skill | bearer |
| GET | /skills/{name} | Skill 详情 | bearer |

### 6.11 内部接口

| 方法 | 路径 | 说明 | 调用方 |
|------|------|------|--------|
| POST | /internal/callbacks | Agent 执行回调 | CLI 子进程 |
| GET | /health | 健康检查 | Nginx / Docker |

内部接口通过 localhost-only 访问或 shared secret 验证，不经过 JWT 认证。

---

## 7. SSE 事件协议 v2

### 7.1 事件类型

| 事件名 | 触发时机 | data 格式 |
|--------|---------|----------|
| `text_delta` | Agent 输出文本增量 | `{"text": "..."}` |
| `tool_start` | 工具调用开始 | `{"tool_use_id": "...", "tool_name": "...", "input": {...}}` |
| `tool_end` | 工具调用结束 | `{"tool_use_id": "...", "output": "...", "is_error": false, "duration_ms": 123}` |
| `plan_step` | Coordinator 规划步骤 | `{"step_id": 1, "type": "research", "description": "..."}` |
| `step_start` | 步骤开始执行 | `{"step_id": 1}` |
| `step_end` | 步骤执行结束 | `{"step_id": 1, "status": "completed"}` |
| `harness_event` ⚡新增 | Harness 治理事件 | `{"type": "guardrail_trigger"\|"permission_deny"\|"permission_ask"\|"loop_detected"\|"compaction"\|"circuit_break"\|"feedback_alert"\|"middleware_action", "detail": {...}}` |
| `run_complete` | Run 正常完成 | `{"run_id": "...", "input_tokens": N, "output_tokens": N, "turn_count": N}` |
| `run_error` | Run 执行失败 | `{"run_id": "...", "error": "..."}` |
| `queue_update` | 队列状态变化 | `{"queued_count": N, "next_preview": "..."}` |
| `heartbeat` | 保活心跳（每 15 秒） | `{}` |
| `session_title` | 自动生成的会话标题 | `{"title": "..."}` |

> ⚡ `harness_event` 是新增事件，让前端能实时展示 Harness 治理动态（如"护栏拦截了一次危险操作"、"上下文已自动压缩"）。

### 7.2 SSE 连接约定

- 连接路径：`GET /api/v1/sessions/{id}/stream?token={jwt}`
- JWT 通过 query param 传递（EventSource 不支持 custom header）
- Nginx 配置：`proxy_set_header Connection ""; proxy_buffering off; X-Accel-Buffering: no;`
- 心跳间隔 15 秒，防止代理层超时断开
- 客户端使用原生 `EventSource` 自动重连

---

## 8. 目录结构

```
prism-v2/                              # 全新文件夹，不继承 v1
│
├── docker-compose.yml                 # 生产编排
├── docker-compose.dev.yml             # 开发覆盖（源码挂载热重载）
├── .env.example                       # 环境变量模板
├── .gitignore
│
├── docs/                              # 设计文档
│   ├── 00-Vision-and-Principles.md
│   ├── 01-System-Architecture.md      # 本文档
│   └── ...
│
├── backend/                           # FastAPI 后端（含 Harness Runtime + Agent Runtime）
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │       └── 001_initial_tables.py
│   └── app/
│       ├── main.py                    # FastAPI app + lifespan
│       ├── core/
│       │   ├── config.py              # Pydantic Settings
│       │   ├── database.py            # SQLAlchemy sync engine + Session
│       │   ├── security.py            # JWT + bcrypt
│       │   └── dependencies.py        # FastAPI Depends
│       ├── models/                    # SQLAlchemy ORM（14 张表）
│       │   ├── base.py                # Base + TimestampMixin
│       │   ├── user.py
│       │   ├── session.py
│       │   ├── run.py
│       │   ├── message.py
│       │   ├── provider.py
│       │   ├── mcp_server.py
│       │   ├── im.py
│       │   └── audit.py
│       ├── schemas/                   # Pydantic v2 请求/响应
│       │   ├── auth.py
│       │   ├── session.py
│       │   ├── run.py
│       │   ├── task.py
│       │   ├── message.py
│       │   ├── provider.py
│       │   ├── mcp.py
│       │   ├── im.py
│       │   ├── harness.py             # ⚡ Harness 状态/轨迹响应 Schema
│       │   └── common.py             # ApiResponse<T>, PagedResponse, ErrorResponse
│       ├── services/                  # 业务逻辑层
│       │   ├── task_service.py
│       │   ├── session_service.py
│       │   ├── run_lifecycle.py
│       │   ├── session_queue.py
│       │   ├── callback_service.py
│       │   ├── sse_manager.py
│       │   ├── provider_service.py
│       │   ├── mcp_service.py
│       │   ├── im_gateway.py         # IM 网关统一入口
│       │   ├── im_feishu.py           # 飞书适配器
│       │   ├── im_wecom.py            # 企业微信适配器
│       │   ├── im_telegram.py         # Telegram 适配器
│       │   ├── harness_query.py       # ⚡ Harness 状态/轨迹查询服务
│       │   └── audit_service.py
│       └── api/
│           └── v1/
│               ├── __init__.py
│               ├── auth.py
│               ├── sessions.py
│               ├── tasks.py
│               ├── runs.py
│               ├── providers.py
│               ├── mcp.py
│               ├── im.py
│               ├── admin.py
│               ├── harness.py         # ⚡ Harness 状态/轨迹端点
│               └── internal.py        # 内部回调接口
│
├── executor/                          # Agent 执行器（CLI 子进程入口）
│   ├── __init__.py
│   ├── __main__.py                    # python -m prism.executor 入口
│   ├── harness/                       # ⚡ Harness Runtime 核心（Layer 3）
│   │   ├── __init__.py
│   │   ├── middleware/                # 可插拔中间件
│   │   │   ├── __init__.py
│   │   │   ├── base.py               # Middleware 抽象基类
│   │   │   ├── pipeline.py           # MiddlewarePipeline 编排
│   │   │   ├── context_enrichment.py  # 上下文增强
│   │   │   ├── loop_detection.py     # 循环检测
│   │   │   ├── rate_limit.py         # 速率限制
│   │   │   ├── output_validation.py  # 输出校验
│   │   │   ├── feedback_capture.py   # 反馈采集
│   │   │   └── observability.py      # 可观测性记录
│   │   ├── guardrails/               # 护栏引擎
│   │   │   ├── __init__.py
│   │   │   ├── engine.py             # GuardrailsEngine
│   │   │   ├── rules.py              # 声明式规则定义
│   │   │   └── platform_rules.py     # 平台级内置规则
│   │   ├── hooks/                    # Hook 系统
│   │   │   ├── __init__.py
│   │   │   ├── system.py             # HookSystem（事件分发）
│   │   │   ├── handlers.py           # Handler 执行器（command/http/prompt/agent）
│   │   │   └── events.py             # 21 种事件类型定义
│   │   ├── permissions/              # 权限引擎
│   │   │   ├── __init__.py
│   │   │   └── engine.py             # PermissionEngine（分层模型）
│   │   ├── circuit_breaker.py        # 熔断器
│   │   └── lifecycle.py              # 生命周期控制器
│   ├── engine/
│   │   ├── query_engine.py            # 自研 TAOR 主循环
│   │   ├── prompt_assembler.py        # Prompt 动态装配
│   │   ├── prompt_sections.py         # 各 section 内容定义
│   │   ├── context_budget.py          # 上下文预算管理
│   │   ├── compaction.py              # ⚡ 4 级渐进式 Compaction Pipeline
│   │   └── synthesizer.py             # 多步骤结果合成
│   ├── agents/
│   │   ├── base.py                    # AgentDefinition 基类
│   │   ├── general.py                 # 通用 Agent
│   │   ├── research.py                # 研究/探索 Agent（只读）
│   │   ├── planner.py                 # 规划 Agent
│   │   └── verifier.py                # 验证 Agent
│   ├── tools/
│   │   ├── base.py                    # Tool 基类（声明式 Schema）
│   │   ├── pipeline.py                # ToolExecutionPipeline（关联 Harness）
│   │   ├── registry.py                # 工具注册表
│   │   └── builtin/                   # 内置工具
│   │       ├── web_search.py
│   │       ├── file_read.py
│   │       ├── file_write.py
│   │       ├── bash.py
│   │       └── ...
│   ├── plugins/
│   │   ├── host.py                    # PluginHost（Skill + Hook + MCP 统一管理）
│   │   ├── skill_loader.py            # Skill 三级加载
│   │   ├── hook_runner.py             # Hook 执行器（委托给 harness/hooks/）
│   │   └── mcp_client.py             # MCP stdio 客户端
│   ├── adapters/
│   │   ├── base.py                    # ModelAdapter 基类
│   │   ├── anthropic_driver.py        # Anthropic Messages API
│   │   ├── openai_driver.py           # OpenAI Chat Completions
│   │   ├── stream_parser.py           # SSE 行解析器
│   │   └── provider_manager.py        # Provider 选择 + 故障转移
│   ├── coordinator/
│   │   ├── coordinator.py             # Coordinator-Workers 编排
│   │   └── fork_manager.py            # Fork 上下文隔离
│   └── callbacks/
│       └── backend_callback.py        # 回调 Backend 内部接口
│
├── frontend/                          # Next.js 前端
│   ├── Dockerfile
│   ├── package.json
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   ├── src/
│   │   ├── app/                       # App Router
│   │   ├── components/                # UI 组件
│   │   ├── features/                  # 功能模块
│   │   ├── lib/                       # API 客户端、SSE、工具函数
│   │   ├── stores/                    # Zustand stores（少量客户端状态）
│   │   └── styles/                    # 全局样式、设计 tokens
│   └── public/
│
└── nginx/
    └── nginx.conf
```

---

## 9. 跨层通信契约

### 9.1 Backend ↔ CLI 子进程

**启动参数**：
```bash
python -m prism.executor --run-id=019... --callback-url=http://localhost:8000/api/v1/internal/callbacks --callback-secret=...
```

**回调协议**：CLI 子进程通过 HTTP POST 向 Backend 发送事件。

```python
# 回调请求体
class CallbackEvent:
    run_id: str
    event_type: str          # "text_delta" | "tool_start" | "tool_end" | "harness_event" | "run_complete" | "run_error" | ...
    data: dict               # 事件数据
    timestamp: str           # ISO 8601
    
# 认证: X-Callback-Secret header
```

Backend 收到回调后：持久化消息 → 更新 Run 状态 → SSE 推送 → 队列推进。

> ⚡ `harness_event` 是新增回调类型，Harness Runtime 通过它向 Backend 上报治理事件（护栏触发、权限拒绝、循环检测、Compaction 触发等），Backend 将其写入 audit_logs 并通过 SSE 推送给前端。

> **关键约束**：Executor（CLI 子进程）运行时**不直接访问 DB**。所有持久化、状态更新、队列推进均通过 HTTP 回调委托给 Backend。这保证了 Executor 可以独立伸缩且不会产生 DB 连接竞争。

### 9.2 Backend ↔ Redis

| 用途 | Key 格式 | 数据 |
|------|---------|------|
| SSE pub/sub | channel: `sse:{session_id}` | JSON 事件 |
| Run 状态缓存 | `run:{run_id}:status` | status string, TTL 1h |
| 速率限制 | `ratelimit:{ip}:{endpoint}` | counter, TTL 60s |
| 熔断器状态 ⚡ | `harness:circuit:{provider_id}` | `{failures: N, broken_at: ts}`, TTL 30m |
| Loop 检测窗口 ⚡ | `harness:loop:{run_id}` | recent tool calls list, TTL = run duration |
| Middleware 状态 ⚡ | `harness:mw:{run_id}:*` | 各中间件的运行时状态, TTL = run duration |

### 9.3 IM Gateway ↔ Task 提交

IM 消息经过 Gateway 标准化后，通过内部调用 `TaskService.enqueue_task()` 提交，与 Web 端 `POST /tasks` 走完全相同的 Orchestration → Harness → Agent 链路。区别仅在于：

- `session.im_channel` 和 `session.im_chat_id` 被设置
- Run 完成时，`callback_service` 除了 SSE 推送外，同时通过 IM Gateway 向对应渠道发送回复

### 9.4 Harness Runtime 内部通信 ⚡新增

```
MiddlewarePipeline
    ↕ 同步调用
HookSystem ←→ GuardrailsEngine ←→ PermissionEngine
    ↕                                    ↕
CircuitBreaker                    LifecycleController
    ↕ Redis (跨进程共享)               ↕ 回调 Backend
```

Harness 子系统之间通过 Python 函数调用通信（同一进程内），跨进程状态（如熔断器计数器）通过 Redis 共享。Harness 事件向外传递通过 Backend 回调接口。

---

## 10. Harness 状态存储策略 ⚡新增

Phase 1 遵循 KISS 原则，不新增专用 Harness 表，使用分层存储策略：

| 数据类型 | 频率 | 存储位置 | 说明 |
|---|---|---|---|
| 护栏规则定义 | 低频写，高频读 | 代码 + 配置文件 | 平台级规则硬编码在 `platform_rules.py`，插件级规则随 Plugin 声明文件加载 |
| Hook 配置 | 低频写，高频读 | 配置文件（对标 CC 的 settings.json） | `.prism/hooks.json` 或 Plugin frontmatter |
| 运行时状态（熔断器/循环检测/中间件状态） | 高频读写 | Redis（TTL 自动清理） | 子进程生命周期内有效 |
| 治理审计轨迹 | 中频写，低频读 | PostgreSQL `audit_logs` 表 | `action` 字段以 `harness.` 前缀区分 |
| Run 级 Harness 摘要 | 每次 Run 完成写一次 | PostgreSQL `runs.harness_summary` JSONB | 统计本次 Run 的治理数据 |

---

## 11. 部署双模

### 11.1 开发环境

```yaml
# docker-compose.dev.yml
services:
  backend:
    build: ./backend
    volumes:
      - ./backend:/app         # 源码挂载
      - ./executor:/app/executor  # executor 源码挂载（含 harness/）
    command: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    environment:
      - PRISM_ENV=development
      
  frontend:
    build: ./frontend
    volumes:
      - ./frontend/src:/app/src
    command: npm run dev
    ports:
      - "3000:3000"
      
  postgres:
    image: postgres:16
    volumes:
      - pgdata_dev:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: prism_dev
      
  redis:
    image: redis:7-alpine
```

开发环境无 Nginx，前端直连 Backend（Next.js dev server 自带 proxy rewrite）。

### 11.2 生产环境

```yaml
# docker-compose.yml
services:
  nginx:
    image: nginx:latest
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - frontend_static:/usr/share/nginx/html:ro  # 前端构建产物
      
  backend:
    build: ./backend
    expose:
      - "8000"
    environment:
      - PRISM_ENV=production
      
  postgres:
    image: postgres:16
    volumes:
      - pgdata:/var/lib/postgresql/data
      
  redis:
    image: redis:7-alpine
```

生产环境前端通过多阶段构建输出 standalone，由 Nginx 直接服务静态文件。

### 11.3 环境变量

```bash
# .env.example

# === 必填 ===
PRISM_ENV=production                              # development | production
DATABASE_URL=postgresql://prism:secret@postgres:5432/prism
REDIS_URL=redis://redis:6379/0
JWT_SECRET=<random-64-chars>
CALLBACK_SECRET=<random-32-chars>                 # 内部回调认证
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=<strong-password>

# === 默认 Provider（可选，也可通过 Web UI 配置）===
DEFAULT_PROVIDER_PROTOCOL=anthropic               # anthropic | openai
DEFAULT_PROVIDER_BASE_URL=https://api.minimaxi.com/anthropic
DEFAULT_PROVIDER_API_KEY=<api-key>
DEFAULT_PROVIDER_MODEL=MiniMax-M2.7

# === IM（可选）===
FEISHU_APP_ID=
FEISHU_APP_SECRET=
WECOM_CORP_ID=
WECOM_AGENT_ID=
WECOM_SECRET=
TELEGRAM_BOT_TOKEN=

# === Harness 调优 ⚡ ===
MAX_TURNS_PER_RUN=50                              # 单次 Run TAOR 循环上限
LOOP_DETECTION_WINDOW=5                           # 循环检测滑动窗口
CIRCUIT_BREAKER_THRESHOLD=3                       # 连续失败触发熔断
CIRCUIT_BREAKER_RECOVERY_SECONDS=300              # 熔断恢复探测间隔

# === 调优 ===
MAX_CONCURRENT_RUNS=2
RUN_TIMEOUT_SECONDS=600
QUEUE_MAX_SIZE=20
```

---

> **文档维护说明**：本文档定义了 Prism v2 的技术骨架。Schema 变更、API 路由变更、服务拓扑变更、Harness 子系统变更必须先更新本文档，再执行实现。  
> **最后更新**: 2026-04-02 | **下一步**: DOC-02 Model Adapter and Prompt Engine
