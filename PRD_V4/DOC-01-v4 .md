# Prism 棱镜 v2 — 系统架构 (DOC-01)

> **文档编号**: DOC-01
> **版本**: 4.0(Review 修订版)
> **日期**: 2026-04-18
> **性质**: 技术蓝图 — 定义所有模块共用的"骨架",是 DOC-02 至 DOC-12 的基础
> **前置依赖**: DOC-00 Vision and Principles v4
> **本文档不包含代码实现,仅定义架构、数据模型和接口契约**
> **v4 变更摘要**: 基于 5 轮跨 Batch review 修订,共 30 处精确修补(见文末 §附录 A)。原文结构、章节编号、章节内容 99% 保留,仅在 review 发现问题的具体位置做补丁式修订

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

> **Harness 单实例架构(v4 明确)**：Layer 3 Harness Runtime **只存在于 Agent 执行的子进程中**。Backend 进程不持有 Harness 实例,不运行 Middleware/Hook/Permission/Guardrail 逻辑。这消除了"Backend vs 子进程两份 Harness 规则可能不一致"的架构隐患。Backend 的角色是:API 接入 + 编排 + 回调接收 + SSE 转发;Harness 规则的版本化、加载、执行全部在子进程内完成。

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
         │  │ API + Orchestration │   │  ← Layer 1-2 在 Backend 进程内
         │  │ (不持有 Harness 实例) │   │
         │  └─────────────────────┘   │
         │  ┌─────────────────────┐   │
         │  │  CLI 子进程 (Agent)  │   │  ← Layer 3 Harness + Layer 4-5 在子进程内
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

| 服务 | 技术 | 职责 | 资源预算(4C8G 基线) |
|------|------|------|---------------------|
| **nginx** | Nginx latest | 反向代理、SSL 终止、前端静态文件、SSE 透传（`X-Accel-Buffering: no`） | ~10MB / 0.1 CPU |
| **backend** | FastAPI + Python 3.12 | REST API + 编排层 + 模型适配 + IM Gateway + 回调接收(**不含 Harness 实例,Harness 在子进程**) | ~200MB 空闲、峰值 ~1GB / 1-2 CPU |
| **postgres** | PostgreSQL 16 | 所有持久化数据(含 Harness 审计轨迹 + Coordinator Plan 检查点) | ~100MB 空闲 / 0.3 CPU |
| **redis** | Redis 7 | SSE pub/sub + Session 缓存 + Harness 运行时状态(熔断计数器、Loop 检测窗口、SSE ticket、permission-ask answer 通道、心跳) | ~30MB / 0.1 CPU |
| **CLI 子进程** | Python subprocess | Agent 执行 + Harness Runtime + Agent Engine + 模型 API 调用 | ~300MB/个 / 0.5-1 CPU per run |

**总计空闲**: ~340MB + ~300MB/并发 Run。

**资源预算推荐档**:

| 配置 | MAX_CONCURRENT_RUNS | 场景 |
|---|---:|---|
| 2C2G | 1 | 本地开发 / 小团队轻量使用(fallback 模式) |
| **4C8G** | **3** | **推荐生产基线(云端主部署 / 稳定本地)** |
| 8C16G | 6 | 大团队(接近 20 人) |

Prism 的服务拓扑优化目标是 4C8G,**2C2G 可降级跑但并发能力受限**(1 个 Run,Coordinator 模式响应会慢)。

### 2.3 与 v1 对比

| v1 | v2 | 变化 |
|----|----|----- |
| 6 服务（backend + executor + executor_manager + postgres + redis + nginx） | 4 服务 | 去掉 executor 和 executor_manager |
| Executor 独立 Docker 容器，冷启动 2-5s | CLI 子进程，启动 200-500ms | 首 token 延迟大幅降低 |
| Docker Socket 权限依赖 | 无特殊权限需求 | 安全性提升 |
| 无 Harness 层 | Harness Runtime 单实例内建于 CLI 子进程(Backend 不持有) | Agent 可靠性质变,架构边界清晰 |

---

## 3. 进程模型与 Agent 执行策略

### 3.1 任务执行流程（含 Harness）

```
POST /api/v1/tasks
    │
    ▼
TaskScheduler.enqueue_task()                          ← Layer 2: Orchestration(Backend 进程内)
    ├─ Session 空闲？
    │   YES → 创建 AgentRun → 启动 CLI 子进程
    │
    └─ Session 有 blocking_run？
        → session_queue_items.enqueue()
        → 返回 {accepted_type: "queued_query"}
        → 等待当前 Run 完成后自动 promote

[并行] 前端建立 SSE 连接
    ├─ POST /api/v1/auth/sse-ticket (携带 session_id)
    ├─ 得到 60s 一次性 ticket
    └─ GET /api/v1/sessions/{id}/stream?ticket={ticket}
        → Backend 校验 + DEL ticket → 建立 SSE 连接
        → Backend SUBSCRIBE Redis channel `sse:{session_id}`

CLI 子进程启动(Backend 通过 subprocess 启动,传递回调密钥)
    │
    ▼
python -m prism.executor --run-id={run_id}
    │
    ├─ [心跳] 每 5s 写入 Redis `harness:heartbeat:{run_id}` 当前时间戳
    │   (Backend HeartbeatMonitor 每 10s 扫描,超过 30s 无心跳 → 标记 crashed)
    │
    ▼
AgentExecutor 初始化                                   ← Layer 3-5 初始化(子进程内)
    ├─ 从 DB 读取 Run 配置（model, provider, plugins, prompt）
    ├─ 初始化 Harness Runtime(仅此处,Backend 不持有)
    │   ├─ 加载 MiddlewarePipeline(4 钩点: pre_turn / pre_tool_use / post_tool_use / post_turn)
    │   ├─ 加载 HookSystem(解析 harness_config.yaml + Plugin frontmatter)
    │   ├─ 初始化 PermissionEngine(平台级 + 插件级护栏 + Redis BLPOP ask 协议)
    │   ├─ 初始化 GuardrailsEngine(声明式规则加载)
    │   ├─ 初始化 CircuitBreaker(从 Redis 恢复熔断状态)
    │   └─ 触发 SessionStart Hook
    ├─ 初始化 PromptAssembler(对齐 CC 的 10+ section getter 粒度)
    ├─ 初始化 ToolExecutionPipeline(关联 Harness 的 Hook + Permission)
    ├─ 加载 Plugin Host(Skills + Hooks + MCP,含 agent-scoped MCP + frontmatter skills)
    ├─ 选择 Agent 类型(General / Planner / Research / Verifier / Coordinator / PluginBuilder)
    │
    ▼
QueryEngine.run() — TAOR 主循环                        ← Layer 4 执行,Layer 3 治理
    ├─ [Middleware] pre_turn 钩点(Context Enrichment / Loop Detection 状态检查)
    ├─ 构造 System Prompt(PromptAssembler.build())
    ├─ 调用 ModelAdapter.stream()                      ← Layer 5
    │   ├─ text_delta 事件: 子进程 PUBLISH Redis `sse:{session_id}` (不经 Backend)
    │   │   Backend 已订阅该 channel,直接 forward 到 SSE 客户端
    │   └─ tool_use_delta 事件: 同上
    ├─ 解析模型响应(text / tool_use)
    ├─ 工具调用(无依赖工具并行: asyncio.gather):
    │   ├─ [Middleware] pre_tool_use 钩点
    │   ├─ [Harness] PreToolUse Hook → PermissionEngine 决策
    │   │   ├─ allow → 继续执行
    │   │   ├─ deny → 返回错误到 messages
    │   │   └─ ask → 通过 Redis BLPOP 等待用户回答(超时 300s fail-safe deny)
    │   │       子进程 PUBLISH `harness_event{type:permission_ask,request_id:X}`
    │   │       Backend 转发 SSE → 前端弹窗 → 用户点击
    │   │       Backend POST /sessions/{id}/permission-answer body={request_id, decision}
    │   │       Backend RPUSH `perm_answer:{request_id}` decision
    │   │       子进程 BLPOP 返回 → 继续
    │   ├─ ToolExecutionPipeline.execute()
    │   ├─ [Harness] PostToolUse Hook
    │   └─ [Middleware] post_tool_use 钩点(Output Validation / Feedback Capture)
    ├─ 回调 Backend 关键事件(tool_end / harness_event / compaction 触发):
    │   POST /api/v1/internal/callbacks(HTTP,带重试,关键事件不丢)
    ├─ [Harness] Compaction Check → 4 级策略触发(按回合组为原子单元裁剪)
    ├─ [Middleware] post_turn 钩点
    ├─ 循环直到模型返回 end_turn 或达到 max_turns(按 agent_type 分档)
    │
    ▼
Run 完成
    ├─ [Harness] 触发 SessionEnd Hook
    ├─ 子进程计算 run_harness_summary → POST /internal/callbacks 一次性全量持久化完整 assistant messages + harness_summary
    ├─ 子进程 DEL `harness:heartbeat:{run_id}`
    ├─ SessionQueueManager.promote_next()(原子事务)
    └─ 子进程退出
```

> **Sync/Async 分界**:Backend(FastAPI)层使用 async def 处理 HTTP 请求,DB 操作使用 SQLAlchemy 2.0 sync Session(在 async 路由中通过 `run_in_executor` 或独立线程运行同步 DB 调用)。Executor(CLI 子进程)内部使用同步执行模型(TAOR 主循环为同步 while loop),仅在 MCP 通信和模型 API 调用时使用 async。Executor 运行时**不直接访问 DB**,所有持久化通过 HTTP 回调委托给 Backend。

> **回调协议(方案 A 直通)**:流式事件(text_delta / tool_use_delta)通过 Redis pub/sub 直通前端,不经 Backend;关键事件(tool_end / run_complete / run_error / harness_event)通过 HTTP 回调保证可靠性,支持 3 次重试 + 本地 dead letter queue。详见 §9.1。

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
| `MAX_CONCURRENT_RUNS` | 3 (4C8G) / 1 (2C2G) / 6 (8C16G) | 同时运行的 Agent 子进程数上限,按硬件档次自动设定 |
| `RUN_TIMEOUT_SECONDS` | 按 agent_type 分档 | general: 600 / research: 900 / planner: 300 / verifier: 600 / coordinator: 1800 / plugin_builder: 1200 |
| `QUEUE_MAX_SIZE` | 20 | 单个 Session 的排队消息上限 |
| `MAX_TURNS_PER_RUN` | 按 agent_type 分档 | general: 50 / research: 30 / planner: 15 / verifier: 30 / coordinator: 100 / plugin_builder: 50 |
| `LOOP_DETECTION_WINDOW` | 5 | 检测重复工具调用的滑动窗口大小 |
| `HEARTBEAT_INTERVAL_SECONDS` | 5 | 子进程向 Redis 写心跳的间隔 |
| `HEARTBEAT_STALE_SECONDS` | 30 | Backend 标记 Run 为 crashed 的阈值 |
| `PERMISSION_ASK_TIMEOUT_SECONDS` | 300 | 用户未回答则 fail-safe deny |
| `SSE_TICKET_TTL_SECONDS` | 60 | SSE 连接 ticket 过期时间 |
| `FORK_MAX_DEPTH` | 2 | Fork 嵌套深度上限,防无限递归 |
| `FORK_TIMEOUT_SECONDS` | 300 | 单次 Fork 子 Agent 超时 |

超过并发上限时,新任务进入全局等待队列,按 FIFO 调度。超时强制 kill + 标记 Run 为 timeout + promote 队列下一条。

---

## 4. 数据库 Schema 全量设计

### 4.1 设计原则

- 所有主键使用 **UUIDv7**（时间有序，可排序，全局唯一）
- 所有表包含 `created_at` 和 `updated_at` 时间戳（UTC, timezone-aware）
- JSON 字段使用 PostgreSQL `JSONB` 类型
- 外键显式声明，`ON DELETE` 行为明确
- 所有涉及用户数据的查询强制 `WHERE user_id = :current_user_id`（铁律 4）
- Harness 运行时状态（高频低持久）存 Redis，Harness 审计轨迹（低频高持久）存 audit_logs

### 4.2 表清单（Phase 1，19 张表）

> Harness 状态存储策略见 §10。Phase 1 新增 5 张表(相对 v3 的 14 张):`skill_installs`(Skills Market) + `coordinator_plans`(崩溃恢复) + `permission_requests`(ask 协议持久化) + `im_message_dedup`(IM 幂等) + `user_memories`(Memory Layer)。Harness 审计事件仍通过 `audit_logs` 表的 `action` 字段区分(如 `harness.guardrail_trigger`、`harness.hook_fire`、`harness.circuit_break`、`harness.permission_ask`)。

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
| cache_hit_tokens | INT | NULL | Prompt Cache 命中的 token 数(Anthropic) |
| cache_miss_tokens | INT | NULL | Cache miss 的 token 数 |
| cache_creation_tokens | INT | NULL | Cache 创建消耗的 token 数 |
| cost_usd | DECIMAL(10,6) | NULL | 本次调用成本 |
| turn_count | INT | NULL | TAOR 循环次数 |
| agent_type | VARCHAR(50) | NULL | 本 Run 使用的 Agent 类型(general/research/planner/verifier/coordinator/plugin_builder) |
| run_mode | VARCHAR(20) | NOT NULL DEFAULT 'foreground' | 'foreground' / 'background' / 'fork'(Phase 2 扩展背景 Agent 时启用) |
| parent_run_id | UUID | FK → runs.id NULL | fork 或 background 模式的父 Run;foreground 模式为 NULL |
| harness_version | VARCHAR(20) | NULL | Harness 代码 + 配置的 hash(生产问题复现用) |
| harness_summary | JSONB | NULL | Harness 运行摘要(guardrail 触发次数、hook 执行次数、compaction 次数等) |

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
| text_preview | VARCHAR(500) | NULL | 纯文本预览(供列表显示、搜索) |
| sequence_no | INT | NOT NULL | Session 内全局顺序号 |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

索引:`(session_id, sequence_no)`, `(run_id)`

> **sequence_no 并发原子性(v4 新增规范)**:不得使用 `max(sequence_no)+1` 计算,并发回调会冲突。使用 PostgreSQL 序列或 advisory lock:
> ```sql
> -- 方案: per-session 序列(推荐)
> SELECT nextval('messages_seq_' || session_id_hash) ;
> -- 或 pg_advisory_xact_lock(session_id_bigint) 后再 max+1
> ```
> DOC-07 Task 7.2/7.3 详细实现。

> **text_preview 生成规则(v4 新增规范)**:按 role 和 content 类型生成:
> - role=user: content 首 500 字符
> - role=assistant 纯 text: 所有 text block 拼接首 500 字符
> - role=assistant 含 tool_use: `"调用 {tool_name}: {input JSON 首 60 字符}"`
> - role=tool_result: `"{tool_name} 结果: {output 首 80 字符}"`(tool_name 从对应 tool_use_id JOIN)
> - role=tool_result + is_error=true: `"⚠ {tool_name} 失败: {error 首 60 字符}"`
>
> 规则在 DOC-07 `session_service.py` 里实现为 `generate_text_preview(role, content, tool_lookup)` 函数。

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
| scope | VARCHAR(20) | NOT NULL DEFAULT 'user' | 'system'(全局预设,无 user_id) / 'user'(用户私有) |
| user_id | UUID | FK → users.id ON DELETE CASCADE NULL | scope='user' 时 NOT NULL,'system' 时 NULL |
| name | VARCHAR(100) | NOT NULL | 显示名(如 "MiniMax M2.7") |
| protocol | VARCHAR(20) | NOT NULL | 'anthropic' \| 'openai' |
| base_url | VARCHAR(500) | NOT NULL | API 端点 |
| api_key_encrypted | TEXT | NOT NULL | AES-256-GCM 加密存储的 API Key(使用 `ENCRYPTION_KEY` 而非 `JWT_SECRET`,见 DOC-06) |
| model_id | VARCHAR(100) | NOT NULL | 模型标识(如 "MiniMax-M2.7") |
| is_default | BOOLEAN | NOT NULL DEFAULT false | 是否为该用户的默认 Provider |
| priority | INT | NOT NULL DEFAULT 0 | 故障转移优先级(0 为最高) |
| is_healthy | BOOLEAN | NOT NULL DEFAULT true | 健康状态(熔断时置 false) |
| config | JSONB | NOT NULL DEFAULT '{}' | 额外配置(max_tokens, temperature, **capabilities** 等) |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

CHECK 约束:`(scope='system' AND user_id IS NULL) OR (scope='user' AND user_id IS NOT NULL)`

索引:`(scope, user_id, is_default)`, `(scope, user_id, priority)`

> **capabilities 强制字段(v4 新增)**:`config` JSONB 必须包含 `capabilities` 对象,应用层校验,缺失则拒绝保存:
> ```json
> {
>   "capabilities": {
>     "prompt_cache": true,
>     "streaming_tools": true,
>     "extended_thinking": false,
>     "vision": false
>   }
> }
> ```
> 内置预设(scope='system')在 Provider Manager 启动时写明;用户自定义(scope='user')通过 `POST /providers/{id}/test` 探测确认。详见 DOC-02 Task 2.3 和 DOC-09 Task 9.2。

> **v3 → v4 迁移**:删除 v3 的 `user_id=admin` hack(system provider 伪装成 admin 用户拥有)。scope='system' 的 provider 是全局共享,不属于任何用户。

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
| platform_chat_id | VARCHAR(200) | NOT NULL DEFAULT '' | IM 平台的会话标识(单聊时为空串,群聊时为群 ID) |
| display_name | VARCHAR(100) | NULL | IM 平台显示名 |
| pairing_code | VARCHAR(10) | NULL | 配对码(绑定前临时生成) |
| paired_at | TIMESTAMPTZ | NULL | 绑定完成时间 |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

唯一约束:`(channel, platform_user_id, platform_chat_id)` — 同一用户在同一 channel 的多个群聊可以有多条绑定;单聊每个 (channel, user) 只能一条(通过 platform_chat_id='' 标识)

> **v3 → v4 修订**:v3 的唯一约束 `(channel, platform_user_id)` 错误地假设一个用户在一个 channel 只有一个会话上下文,实际上用户可能在多个群聊里都 @机器人。v4 改为三元组唯一,单聊用空串作 platform_chat_id。

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

> ⚡ Harness 事件的 `action` 命名约定：`harness.guardrail_trigger`、`harness.hook_fire`、`harness.permission_deny`、`harness.permission_ask`、`harness.circuit_break`、`harness.loop_detected`、`harness.compaction_trigger`、`harness.entropy_alert`。`details` JSONB 包含事件上下文（触发规则、工具名、Agent 类型等）。

#### 插件 & Skill 域 (v4 新增)

**skill_installs**(对应 §6.12 Skills Market API,Batch 1 §R7)

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | UUID v7 | PK | |
| user_id | UUID | FK → users.id ON DELETE CASCADE | 所属用户 |
| skill_name | VARCHAR(200) | NOT NULL | 含 namespace,如 "community/obra/superpowers" |
| source | VARCHAR(50) | NOT NULL | 'local' / 'github' / 'manus' / 'npm' / 'cc_compat' |
| source_url | VARCHAR(500) | NULL | 来源 URL(GitHub repo / npm package / Manus ID 等) |
| version | VARCHAR(50) | NOT NULL | 语义化版本 |
| installed_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| metadata | JSONB | NOT NULL DEFAULT '{}' | SKILL.md frontmatter 缓存 + 多源聚合的元信息 |

唯一约束:`(user_id, skill_name)`
索引:`(user_id, installed_at DESC)`

#### 执行恢复域 (v4 新增)

**coordinator_plans**(Coordinator 子进程崩溃恢复,Batch 2 §A4-3)

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | UUID v7 | PK | |
| run_id | UUID | FK → runs.id ON DELETE CASCADE | 对应的 Run |
| plan_json | JSONB | NOT NULL | 完整 Plan 结构 |
| current_step_index | INT | NOT NULL DEFAULT 0 | 当前执行到的 step |
| step_results | JSONB | NOT NULL DEFAULT '[]' | 已完成 step 的结果累积 |
| status | VARCHAR(20) | NOT NULL DEFAULT 'running' | 'running' / 'completed' / 'failed' / 'paused' |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

索引:`(run_id)`, `(status, updated_at DESC)`

> Coordinator 在每个 step 开始/完成时 checkpoint,子进程重启后可从 current_step_index 恢复。Backend 提供 `POST /runs/{id}/resume` 接口。

**permission_requests**(permission ask 协议的可选持久化,Batch 2 §A3-7)

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | UUID v7 | PK | |
| request_id | VARCHAR(36) | UNIQUE NOT NULL | 子进程生成,用于匹配 Redis BLPOP key |
| run_id | UUID | FK → runs.id ON DELETE CASCADE | |
| user_id | UUID | FK → users.id | 冗余,避免 JOIN |
| tool_name | VARCHAR(100) | NOT NULL | 请求权限的工具 |
| tool_input | JSONB | NOT NULL | 工具输入参数 |
| reason | TEXT | NOT NULL | 请求理由(给用户看) |
| status | VARCHAR(20) | NOT NULL DEFAULT 'pending' | 'pending' / 'allow' / 'deny' / 'timeout' |
| requested_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| answered_at | TIMESTAMPTZ | NULL | 用户回答时间(若有) |
| timeout_at | TIMESTAMPTZ | NOT NULL | 超时 fail-safe deny 时间 |

索引:`(run_id, status)`, `(status, timeout_at)`

> **与 Redis BLPOP 协议的关系**:Redis 负责实时阻塞通信(快),DB 负责审计和超时清理(全)。Backend `POST /sessions/{id}/permission-answer` 接口同时:1) RPUSH 到 Redis channel 让子进程 BLPOP 返回,2) UPDATE 本表 status 字段。详见 DOC-07 Task 7.3 + DOC-03 Task 3.3。

#### IM 幂等域 (v4 新增)

**im_message_dedup**(IM webhook 幂等,Batch 3 B3-5)

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | UUID v7 | PK | |
| channel | VARCHAR(50) | NOT NULL | IM 渠道 |
| platform_message_id | VARCHAR(200) | NOT NULL | 平台的消息 ID(飞书 event_id / 企微 MsgId / TG message_id) |
| received_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | 首次收到时间 |
| session_id | UUID | FK → sessions.id NULL | 对应的 Prism session(如已处理) |

唯一约束:`(channel, platform_message_id)`
索引:`(received_at)` — 供定期清理旧记录

> **幂等策略**:IM Gateway 收到消息先查本表,命中则直接 ignore(平台重试);未命中则插入并继续处理。插入失败(UNIQUE 冲突)也 ignore。定期任务清理 7 天前的记录。
> **Phase 1 优化**:也可用 Redis `SETNX im:dedup:{channel}:{msg_id} 1 EX 604800` 代替本表(更快,但重启丢数据);Phase 1 两种实现均可,DOC-08 Task 8.1 最终选择。

#### Memory 域 (v4 新增)

**user_memories**(6 层 Memory 中的 Layer 2 用户级,Batch 2 §A3-9)

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| id | UUID v7 | PK | |
| user_id | UUID | FK → users.id ON DELETE CASCADE | |
| memory_text | TEXT | NOT NULL | 用户级偏好/历史摘要 |
| version | INT | NOT NULL DEFAULT 1 | 版本号(每次更新 +1) |
| updated_by | VARCHAR(20) | NOT NULL | 'auto'(SessionEnd Hook 自动提炼) / 'manual'(用户手动编辑) |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

唯一约束:`(user_id)` — 每用户一条 user memory,历史通过 version + audit_logs 追溯

> SessionEnd Hook 提炼本 session 的用户偏好 → merge 到 user_memories。需要 LLM 调用(走用户 default Provider)。DOC-03 Task 3.5 实现。

### 4.3 表关系图

```
users ─────┬──── sessions ─────┬──── session_queue_items
           │         │         │
           │         └──── runs ────┬──── messages
           │                │       ├──── tool_executions
           │                │       ├──── coordinator_plans (v4 新增)
           │                │       └──── permission_requests (v4 新增)
           │
           ├──── invite_codes
           ├──── providers (scope='system' | 'user',v4 修订)
           ├──── user_mcp_installs ──── mcp_servers
           ├──── skill_installs (v4 新增)
           ├──── im_bindings (唯一约束修订,v4)
           ├──── user_memories (v4 新增)
           └──── audit_logs (含 harness.* 事件)

独立表(无 user_id 关联):
  im_channel_configs  — 全局 IM 渠道配置
  im_message_dedup    — IM 幂等去重 (v4 新增)
```

---

## 5. PrismMessage 内部消息格式

Prism 内部使用统一的消息格式 `PrismMessage`，与具体模型厂商 API 解耦。两个 Driver（Anthropic / OpenAI）各自负责 `PrismMessage ↔ 厂商格式` 的双向转换。

### 5.1 PrismMessage 结构

> **v4 修订(Batch 2 §A3-2)**:canonical 格式对齐 Anthropic,`role` 只有 `user` / `assistant` 两种。工具结果通过 `ToolResultBlock` 作为 user message 的 content 出现(Anthropic 原生语义)。OpenAIDriver 在发送给 OpenAI 时负责把含 tool_result 的 user message 拆成多条 `role=tool` 消息(拆分逻辑在 Driver 底层)。

```python
@dataclass
class PrismMessage:
    role: Literal["user", "assistant"]   # 只有 2 种 role(v4 修订)
    content: list[ContentBlock]          # TextBlock | ToolUseBlock | ToolResultBlock
    is_skill_context: bool = False        # v4 新增:标记本消息是 Skill Level 2 注入(Compaction 优先保留)
    skill_name: str | None = None          # v4 新增:若 is_skill_context=True,记录 Skill 名称

@dataclass
class TextBlock:
    type: Literal["text"] = "text"
    text: str

@dataclass
class ToolUseBlock:
    type: Literal["tool_use"] = "tool_use"
    id: str           # 工具调用 ID(UUIDv7)
    name: str          # 工具名称
    input: dict        # 工具输入参数

@dataclass
class ToolResultBlock:
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str   # 对应的 ToolUseBlock.id
    content: str       # 工具输出(纯文本或 JSON 字符串)
    is_error: bool = False

ContentBlock = TextBlock | ToolUseBlock | ToolResultBlock
```

**为什么选 Anthropic 做 canonical**:表达能力更强(block-based),多个 tool_result 可以在一条 user message 里;OpenAI 是扁平 list,需要展开成多条消息。统一用 Anthropic 语义后,`messages[]` 长度在两个 Provider 下一致,Compaction 行为一致。

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
| POST | /auth/sse-ticket | 换取一次性 SSE ticket(60s 过期,绑定 session_id,v4 新增) | bearer |

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
| POST | /sessions/{id}/cancel | 取消当前正在执行的 Run(支持 mode=graceful/force) |
| POST | /sessions/{id}/permission-answer | 回答 Harness permission ask 请求(v4 新增,body: {request_id, decision: allow/deny}) |

### 6.4 Run (DOC-07)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /runs/{id} | Run 详情（含 harness_summary） |
| GET | /sessions/{id}/runs | Session 下的 Run 列表 |
| POST | /runs/{id}/resume | Coordinator 模式 Run 从上次 checkpoint 恢复(v4 新增,用于子进程崩溃后重启) |

### 6.5 SSE (DOC-07)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /sessions/{id}/stream?ticket={ticket}&last_event_id={id} | SSE 事件流(ticket 通过 `POST /auth/sse-ticket` 换取,v4 修订;last_event_id 可选用于断线重连补发) |

> **v3 → v4 变更**:v3 通过 URL query 传 JWT,泄露在日志/history/referer 中。v4 改用一次性 ticket(60s 过期,绑定 session_id,用后即焚)。详见 §7.2 + DOC-06 Task 6.1 + DOC-07 Task 7.3。

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
| GET | /harness/status | Harness 运行时状态(活跃中间件、熔断器状态、护栏规则数) |
| GET | /harness/traces | Harness 审计轨迹查询(from audit_logs where action like 'harness.%') |
| GET | /runs/{id}/harness-summary | 指定 Run 的 Harness 执行摘要 |
| GET | /harness/config | 当前有效配置(含 source_trace)— admin only |
| PATCH | /harness/config | 更新配置(写入 DB,需重启子进程生效)— admin only |
| POST | /harness/config/reload | 强制重载所有配置源 — admin only |
| GET | /harness/analytics | Harness 数据聚合 — admin only |
| POST | /harness/entropy-check | 触发熵检测 — admin only |

### 6.11 Skills Market (DOC-05)

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | /skills/search | 跨源搜索 Skills(?q=...&source=...) | bearer |
| GET | /skills/installed | 已安装 Skills 列表 | bearer |
| POST | /skills/install | 安装 Skill({package_id, source, version?}) | bearer |
| DELETE | /skills/{name} | 卸载 Skill | bearer |
| POST | /skills/{name}/update | 更新 Skill | bearer |
| GET | /skills/{name} | Skill 详情 | bearer |

### 6.12 内部接口

| 方法 | 路径 | 说明 | 调用方 |
|------|------|------|--------|
| POST | /internal/callbacks | Agent 执行回调(关键事件,Redis 直通事件不走此) | CLI 子进程 |
| POST | /internal/run-crashed | v4 新增:HeartbeatMonitor 标记 Run crashed 的通知(internal-only) | Backend HeartbeatMonitor |
| GET | /metrics | Prometheus scrape 端点(暴露 backend 指标,v4 新增) | Prometheus server |
| GET | /health/live | Liveness 探针(进程活着就 200,v4 拆分) | Nginx / Docker |
| GET | /health/ready | Readiness 探针(所有依赖通才 200,v4 拆分) | Nginx / Docker / K8s |
| GET | /health/detailed | 详细健康报告(含内存/CPU/子进程,admin only,v4 新增) | 运维人员 |

内部接口通过 localhost-only 访问或 shared secret(`CALLBACK_SECRET`)验证,不经过 JWT 认证。

---

## 7. SSE 事件协议 v2

### 7.1 事件类型

| 事件名 | 触发时机 | data 格式 |
|--------|---------|----------|
| `text_delta` | Agent 输出文本增量(Redis 直通) | `{"text": "...", "message_id": "..."}` |
| `tool_use_delta` | 工具参数流式增量(Redis 直通,v4 新增) | `{"tool_use_id": "...", "partial_json": "..."}` |
| `tool_start` | 工具调用开始(HTTP 回调) | `{"tool_use_id": "...", "tool_name": "...", "input": {...}}` |
| `tool_end` | 工具调用结束(HTTP 回调) | `{"tool_use_id": "...", "output": "...", "is_error": false, "duration_ms": 123}` |
| `message_complete` | 一条 assistant message 完整结束(HTTP 回调,v4 新增) | `{"message_id": "...", "sequence_no": N, "content": [...]}` |
| `plan_step` | Coordinator 规划步骤 | `{"step_id": 1, "type": "research", "description": "..."}` |
| `step_start` | 步骤开始执行 | `{"step_id": 1}` |
| `step_end` | 步骤执行结束 | `{"step_id": 1, "status": "completed"}` |
| `coordinator_plan_update` | Coordinator Plan checkpoint 更新(v4 新增) | `{"plan_id": "...", "current_step": N, "total_steps": M}` |
| `permission_ask` | Harness 请求用户确认(v4 新增) | `{"request_id": "...", "tool_name": "...", "tool_input": {...}, "reason": "...", "timeout_at": "..."}` |
| `permission_answered` | 用户已回答,继续执行(v4 新增) | `{"request_id": "...", "decision": "allow\|deny"}` |
| `compaction_in_progress` | Compaction 正在执行(v4 新增) | `{"tier": N, "before_tokens": N, "after_tokens": N}` |
| `harness_event` | Harness 治理事件(非 ask/compaction 的其他事件) | `{"type": "guardrail_trigger\|permission_deny\|loop_detected\|circuit_break\|feedback_alert\|middleware_action", "detail": {...}}` |
| `run_complete` | Run 正常完成 | `{"run_id": "...", "input_tokens": N, "output_tokens": N, "cache_hit_tokens": N, "turn_count": N}` |
| `run_error` | Run 执行失败 | `{"run_id": "...", "error": "..."}` |
| `run_crashed` | 子进程崩溃,Run 被自动标记 failed(v4 新增) | `{"run_id": "...", "reason": "heartbeat_stale\|oom\|panic", "can_resume": true\|false}` |
| `queue_update` | 队列状态变化 | `{"queued_count": N, "next_preview": "..."}` |
| `heartbeat` | 保活心跳(每 15 秒) | `{}` |
| `session_title` | 自动生成的会话标题 | `{"title": "..."}` |

> **事件传递路径分两种(v4 新增说明)**:
> 1. **Redis 直通事件**(`text_delta` / `tool_use_delta`):子进程直接 PUBLISH 到 Redis `sse:{session_id}` channel,Backend SUBSCRIBE 后直接 forward 给 SSE 客户端。零持久化,最低延迟。
> 2. **HTTP 回调事件**(其他所有):子进程 POST /internal/callbacks,Backend 先持久化(写 messages / audit_logs / runs.harness_summary),然后通过 Redis pub 给 SSE 客户端。保证可靠性。

### 7.2 SSE 连接约定

- 连接路径:`GET /api/v1/sessions/{id}/stream?ticket={ticket}&last_event_id={optional}`
- **Ticket 握手协议**(v4):
  1. 前端 `POST /api/v1/auth/sse-ticket` body=`{session_id}` (Bearer JWT)
  2. Backend 验证 JWT 和 session 归属 → 生成 60s 过期 ticket → 返回 `{ticket: "..."}`
  3. 前端 `new EventSource("/api/v1/sessions/{id}/stream?ticket=...")`
  4. Backend 校验 ticket(session_id 必须匹配) + DEL ticket(一次性) → 建立 SSE
- **断线重连**:`EventSource` 自动重连时附带 `Last-Event-ID` header(浏览器原生),Backend 从 Redis Stream 补发该 ID 之后的事件。客户端重连前先调 `/auth/sse-ticket` 拿新 ticket。
- **状态机**(v4 新增,前端 `useSSE` hook 实现):
  ```
  idle → connecting → open ─┬─ error → reconnecting (exponential backoff) → connecting
                             └─ close(客户端主动)
  ```
- Nginx 配置:`proxy_set_header Connection ""; proxy_buffering off; X-Accel-Buffering: no;` + `proxy_read_timeout 3600s`
- 心跳间隔 15 秒,防止代理层超时断开
- **tab 限制**:每个 (user_id, session_id) 最多 3 个并发 SSE 连接;超过则拒绝新连接(避免多 tab 重复订阅消耗资源)

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
│       │   ├── callback_service.py     # 关键事件 HTTP 回调接收
│       │   ├── sse_manager.py          # SSE 订阅 Redis 转发
│       │   ├── sse_ticket_service.py   # v4 新增:SSE 一次性 ticket 生成/校验
│       │   ├── permission_ask_service.py  # v4 新增:permission ask 协议的 Backend 侧
│       │   ├── heartbeat_monitor.py    # v4 新增:子进程心跳监控 + 崩溃标记
│       │   ├── alert_dispatcher.py     # v4 新增:告警分发(audit/SSE/IM/email)
│       │   ├── provider_service.py
│       │   ├── mcp_service.py
│       │   ├── skill_install_service.py  # v4 新增:Skills Market 安装管理
│       │   ├── coordinator_recovery.py  # v4 新增:Coordinator Plan 崩溃恢复
│       │   ├── im_gateway.py           # IM 网关统一入口
│       │   ├── im_feishu.py            # 飞书适配器
│       │   ├── im_wecom.py             # 企业微信适配器
│       │   ├── im_telegram.py          # Telegram 适配器
│       │   ├── im_dedup.py             # v4 新增:IM webhook 幂等去重
│       │   ├── harness_query.py        # Harness 状态/轨迹查询服务
│       │   └── audit_service.py
│       ├── metrics/                    # v4 新增:Prometheus 指标
│       │   ├── __init__.py             # CollectorRegistry + 所有 Counter/Histogram/Gauge 定义
│       │   └── endpoint.py             # /metrics 端点实现
│       ├── logging/                    # v4 新增:结构化日志
│       │   └── __init__.py             # structlog 配置(JSON 输出 + contextvars)
│       └── api/
│           └── v1/
│               ├── __init__.py
│               ├── auth.py             # 含 /auth/sse-ticket (v4 新增)
│               ├── sessions.py         # 含 /permission-answer (v4 新增)
│               ├── tasks.py
│               ├── runs.py             # 含 /resume (v4 新增)
│               ├── providers.py
│               ├── mcp.py
│               ├── skills.py           # v4 新增:Skills Market API
│               ├── im.py
│               ├── admin.py
│               ├── harness.py          # Harness 状态/轨迹端点
│               ├── health.py           # v4 新增:/health/live, /ready, /detailed
│               └── internal.py         # 内部回调接口 + /run-crashed (v4 新增)
│
├── executor/                          # Agent 执行器（CLI 子进程入口）
│   ├── __init__.py
│   ├── __main__.py                    # python -m prism.executor 入口
│   ├── harness/                       # ⚡ Harness Runtime 核心（Layer 3，仅子进程持有）
│   │   ├── __init__.py
│   │   ├── middleware/                # 可插拔中间件(4 钩点: pre_turn/pre_tool_use/post_tool_use/post_turn)
│   │   │   ├── __init__.py
│   │   │   ├── base.py               # Middleware 抽象基类
│   │   │   ├── pipeline.py           # MiddlewarePipeline 编排
│   │   │   ├── context_enrichment.py  # 上下文增强
│   │   │   ├── loop_detection.py     # 循环检测
│   │   │   ├── rate_limit.py         # 速率限制
│   │   │   ├── output_validation.py  # 输出校验
│   │   │   ├── feedback_capture.py   # 反馈采集
│   │   │   └── observability.py      # 可观测性记录(写 metrics + trace span)
│   │   ├── guardrails/               # 护栏引擎
│   │   │   ├── __init__.py
│   │   │   ├── engine.py             # GuardrailsEngine
│   │   │   ├── rules.py              # 声明式规则定义
│   │   │   └── platform_rules.py     # 平台级内置规则
│   │   ├── hooks/                    # Hook 系统
│   │   │   ├── __init__.py
│   │   │   ├── system.py             # HookSystem(事件分发)
│   │   │   ├── handlers.py           # Handler 执行器(command/http/prompt/agent)
│   │   │   ├── events.py             # 21 种事件类型定义
│   │   │   └── decision.py           # v4 新增:HookDecision dataclass(11 字段)+ merge 规则
│   │   ├── permissions/              # 权限引擎
│   │   │   ├── __init__.py
│   │   │   ├── engine.py             # PermissionEngine(分层模型)
│   │   │   └── ask_protocol.py       # v4 新增:Redis BLPOP ask 协议实现
│   │   ├── circuit_breaker.py        # 熔断器
│   │   ├── heartbeat.py              # v4 新增:子进程心跳写入 Redis
│   │   └── lifecycle.py              # 生命周期控制器
│   ├── logging/                      # v4 新增:子进程结构化日志
│   │   └── __init__.py               # structlog 配置,通过 stdio 输出让 Backend 收集
│   ├── tracing/                      # v4 新增:OTel trace 传递
│   │   └── __init__.py               # 从 ENV 读 trace_id,创建 span 上下文
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

**启动参数**:
```bash
python -m prism.executor \
  --run-id=019... \
  --callback-url=http://localhost:8000/api/v1/internal/callbacks \
  --callback-secret=...        # CALLBACK_SECRET,HMAC 签名
```

其他必要参数(通过环境变量传递):
- `REDIS_URL`:子进程直连 Redis 用于流式事件 publish + 心跳 + permission ask BLPOP
- `ENCRYPTION_KEY`:解密 Provider API key
- `PRISM_RUN_ID` / `PRISM_SESSION_ID` / `PRISM_USER_ID`:供 Plugin 变量替换用
- `OTEL_TRACE_ID`(可选):继承父 trace 上下文

**回调协议(方案 A:Redis 流式直通 + HTTP 关键事件)**

v4 将回调从 "全 HTTP 回调" 重构为两条通道:

**通道 1 — Redis 流式直通**(低延迟事件,不经 Backend 进程):
- 子进程 PUBLISH 到 `sse:{session_id}` channel
- Backend `sse_manager.py` SUBSCRIBE 后直接 forward 给 SSE 客户端
- 事件:`text_delta` / `tool_use_delta`
- 目的:text streaming 不阻塞在 Backend 转发,最小化首 token 延迟
- 持久化:这些事件**不持久化**,只做流式展示。完整 assistant message 在 `message_complete` 时一次性持久化
- 同时 RPUSH 到 `sse:{session_id}:stream` Redis Stream(供断线重连用 last_event_id 补发)

**通道 2 — HTTP 关键事件回调**(可靠性保证):
```python
# 回调请求体(通道 2)
class CallbackEvent:
    run_id: str
    event_type: str          # "tool_start" / "tool_end" / "message_complete" /
                             # "harness_event" / "permission_ask" / "permission_answered" /
                             # "compaction_in_progress" / "coordinator_plan_update" /
                             # "run_complete" / "run_error" / "session_title"
    data: dict               # 事件数据
    timestamp: str           # ISO 8601
    event_id: str            # 幂等 key(UUIDv7)
    sequence_no: int          # 全局序号,重连补发用

# 认证: X-Callback-Secret HMAC 头
# 重试: 子进程失败重试 3 次(指数退避 1s/2s/4s)
# Dead letter: 3 次失败后写入子进程本地 /tmp/dead_letter_{run_id}.jsonl
```

**回调事件分类表**:

| 事件 | 通道 | 持久化 | 原因 |
|---|---|---|---|
| text_delta | Redis 直通 | 否 | 纯 UI 流式,高频(每 10-100 tokens) |
| tool_use_delta | Redis 直通 | 否 | 纯 UI 流式,展示工具参数生成 |
| tool_start | HTTP | 写 tool_executions | 工具执行关键事件,要审计 |
| tool_end | HTTP | 更新 tool_executions | 同上 |
| message_complete | HTTP | 写 messages(一次性全量) | 持久化完整 assistant message |
| harness_event | HTTP | 写 audit_logs | 治理事件,审计用 |
| permission_ask | HTTP | 写 permission_requests | 需要用户回答,持久化 |
| permission_answered | HTTP | 更新 permission_requests | 用户回答 |
| compaction_in_progress | HTTP | 写 audit_logs | 低频事件 |
| coordinator_plan_update | HTTP | 更新 coordinator_plans | checkpoint 用 |
| run_complete | HTTP | 更新 runs + 写 harness_summary | Run 生命周期关键 |
| run_error | HTTP | 更新 runs | 同上 |
| session_title | HTTP | 更新 sessions.title | 低频,自动生成 |

> **关键约束**:Executor(CLI 子进程)运行时**不直接访问 DB**。所有持久化通过通道 2 的 HTTP 回调委托给 Backend。这保证了 Executor 可以独立伸缩且不会产生 DB 连接竞争。通道 1 的 Redis 直通不涉及持久化,纯粹做流式展示 fan-out。

### 9.2 Backend ↔ Redis

| 用途 | Key 格式 | 数据 | TTL |
|------|---------|------|---|
| SSE pub/sub channel | `sse:{session_id}` | JSON 事件(text_delta / tool_delta 直通 + 其他事件 Backend pub) | N/A(channel) |
| SSE 事件 Stream(断线补发) | `sse:{session_id}:stream` | Redis Stream,事件按 event_id + sequence_no 存 | 1h |
| SSE ticket | `sse_ticket:{token}` | `{user_id, session_id}`,一次性消费 | 60s |
| Run 状态缓存 | `run:{run_id}:status` | status string | 1h |
| 速率限制 | `ratelimit:{ip}:{endpoint}` | counter | 60s |
| 熔断器状态(跨进程共享) | `harness:circuit:{provider_id}` | `{failures: N, broken_at: ts}` | 30m |
| Loop 检测窗口 | `harness:loop:{run_id}` | recent tool calls list | = run duration |
| Middleware 运行时状态 | `harness:mw:{run_id}:*` | 各中间件的运行时状态 | = run duration |
| **子进程心跳** (v4 新增) | `harness:heartbeat:{run_id}` | 最后心跳 timestamp | 60s(每 5s 子进程刷新) |
| **Permission ask 等待队列** (v4 新增) | `perm_answer:{request_id}` | 用户回答 `allow` / `deny`(子进程 BLPOP) | 300s(timeout fail-safe deny) |
| **Permission ask 请求状态** (v4 新增) | `perm_req:{request_id}` | 请求详情 JSON(查询用) | 300s |
| IM webhook 幂等(若走 Redis) | `im:dedup:{channel}:{msg_id}` | "1" | 7d |
| Coordinator Plan 最新快照(供快速查询) | `coord_plan:{run_id}` | Plan JSON | = run duration |

**Redis Key 命名空间规范**(v4 新增):
- `sse:*` — SSE 相关
- `harness:*` — Harness 子系统内部状态
- `perm_*` — Permission ask 协议
- `run:*` — Run 生命周期
- `ratelimit:*` — 速率限制
- `im:*` — IM Gateway
- `coord_*` — Coordinator

**Redis 权限隔离**(生产建议):用 Redis ACL 创建两个用户:
- `prism_backend`(Backend 使用)— 全 key 读写
- `prism_executor`(子进程使用)— 只能写 `sse:*` / `harness:*` / `perm_*` / `coord_*`,禁止读其他 key

> Phase 1 可不强制 ACL(单机信任环境),Phase 2 或多用户场景启用。

### 9.3 IM Gateway ↔ Task 提交

IM 消息经过 Gateway 标准化后，通过内部调用 `TaskService.enqueue_task()` 提交，与 Web 端 `POST /tasks` 走完全相同的 Orchestration → Harness → Agent 链路。区别仅在于：

- `session.im_channel` 和 `session.im_chat_id` 被设置
- Run 完成时，`callback_service` 除了 SSE 推送外，同时通过 IM Gateway 向对应渠道发送回复

### 9.4 Harness Runtime 内部通信(子进程内)

```
子进程内(同一 Python 进程,函数调用):

MiddlewarePipeline (4 钩点)
    ↕
HookSystem ↔ GuardrailsEngine ↔ PermissionEngine
    ↕                                ↕
CircuitBreaker                LifecycleController
    ↕                                ↕
    └──────────────→ Redis ←─────────┘
                    (跨进程共享:熔断器状态 / permission ask 通道 / 心跳)

子进程 ↔ Backend:
    通道 1 — Redis pub/sub(text_delta / tool_use_delta 直通)
    通道 2 — HTTP 回调(关键事件,见 §9.1)
```

**重点(v4 强调)**:
- Harness 子系统之间通过 Python 函数调用通信(**同一子进程内,无跨进程**)
- 跨进程状态(熔断器计数器 / permission ask answer / 心跳)通过 Redis 共享
- Harness 事件向外传递通过 §9.1 的两条通道
- **Backend 进程内不运行 Harness 逻辑**(架构底线)

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

## 11. 部署模式

Prism v2 的部署形态对应 DOC-00 §2.5 定义的**云端主 + 本地 fallback 双模态**。同一份代码,同一份 Docker Compose,**配置差异仅在 `.env`**。

### 11.1 开发环境(单机 dev)

```yaml
# docker-compose.dev.yml
services:
  backend:
    build: ./backend
    volumes:
      - ./backend:/app         # 源码挂载
      - ./executor:/app/executor  # executor 源码挂载(含 harness/)
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

开发环境无 Nginx,前端直连 Backend(Next.js dev server 自带 proxy rewrite)。

### 11.2 生产环境 — 云端主部署

目标机:VPS / 自有服务器,4C8G 推荐,用户从公网/内网访问。

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
    deploy:
      resources:
        limits:
          memory: 128M
          cpus: '0.2'

  backend:
    build: ./backend
    expose:
      - "8000"
    environment:
      - PRISM_ENV=production
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    deploy:
      resources:
        limits:
          memory: 4G       # 4C8G 基线下 backend 上限
          cpus: '2.0'
        reservations:
          memory: 1G
          cpus: '0.5'
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health/live"]
      interval: 30s
      timeout: 5s
      retries: 3
      
  postgres:
    image: postgres:16
    volumes:
      - pgdata:/var/lib/postgresql/data
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '0.5'
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U prism"]
      interval: 10s
      
  redis:
    image: redis:7-alpine
    command: >
      redis-server
      --maxmemory 200mb
      --maxmemory-policy allkeys-lru
      --appendonly yes
      --appendfsync everysec
    volumes:
      - redisdata:/data
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: '0.2'
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s

volumes:
  pgdata:
  redisdata:
  frontend_static:
```

生产环境前端通过多阶段构建输出 standalone,由 Nginx 直接服务静态文件。Redis `appendonly yes` 保证熔断状态、permission ask answer、SSE ticket 重启不丢。

### 11.2.1 Monitoring 叠加(v4 新增,开箱 Grafana)

```yaml
# docker-compose.monitoring.yml (可选叠加)
services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
    ports:
      - "9090:9090"
    depends_on:
      - backend
      
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3001:3000"
    volumes:
      - ./monitoring/grafana/dashboards:/var/lib/grafana/dashboards:ro
      - ./monitoring/grafana/provisioning:/etc/grafana/provisioning:ro
      - grafana_data:/var/lib/grafana

volumes:
  grafana_data:
```

启动: `docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d`
访问: `http://<host>:3001` — Grafana 开箱 4 套 dashboard(overview / harness / models / agents),见 DOC-12 Task 12.4。

### 11.3 本地 fallback 部署

**同一份 docker-compose.yml**,只差 `.env` 和降级 resource limits。

场景: 服务器宕机时的降级;成员想独立测试插件;离线/弱网场景。

推荐档 `2C2G`(最小运行画像):
- 只启动 4 个核心服务(backend / postgres / redis / nginx),不加 monitoring 叠加
- `MAX_CONCURRENT_RUNS=1`
- backend memory limit 降为 1.5G
- 功能完整不阉割,只是并发能力受限

**数据不跨环境**:云端和本地是两个独立实例,会话/历史/Skill 各自管理。需要跨环境迁移走 DOC-07 Task 7.x 的 export/import 接口。

### 11.4 环境变量

```bash
# .env.example

# === 必填(所有三个密钥必须彼此独立,至少 32 字符)===
PRISM_ENV=production                              # development | production
DATABASE_URL=postgresql://prism:secret@postgres:5432/prism
REDIS_URL=redis://redis:6379/0

# 三密钥独立(v4):启动时强制校验,互相不同
JWT_SECRET=<random-64-chars>                      # JWT 签名
CALLBACK_SECRET=<random-64-chars>                 # 子进程回调 Backend 的 HMAC
ENCRYPTION_KEY=<random-64-chars>                  # AES-256-GCM 加密 Provider API Key(独立于 JWT)

ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=<strong-password>

# === 默认 Provider(可选,也可通过 Web UI 配置)===
DEFAULT_PROVIDER_PROTOCOL=anthropic               # anthropic | openai
DEFAULT_PROVIDER_BASE_URL=https://api.minimaxi.com/anthropic
DEFAULT_PROVIDER_API_KEY=<api-key>
DEFAULT_PROVIDER_MODEL=MiniMax-M2.7

# === IM(可选)===
FEISHU_APP_ID=
FEISHU_APP_SECRET=
WECOM_CORP_ID=
WECOM_AGENT_ID=
WECOM_SECRET=
TELEGRAM_BOT_TOKEN=

# === Harness 调优 ===
# MAX_TURNS / RUN_TIMEOUT 按 agent_type 分档,JSON 格式配置
MAX_TURNS_BY_AGENT='{"general":50,"research":30,"planner":15,"verifier":30,"coordinator":100,"plugin_builder":50}'
RUN_TIMEOUT_BY_AGENT='{"general":600,"research":900,"planner":300,"verifier":600,"coordinator":1800,"plugin_builder":1200}'

LOOP_DETECTION_WINDOW=5                           # 循环检测滑动窗口
CIRCUIT_BREAKER_THRESHOLD=3                       # 连续失败触发熔断
CIRCUIT_BREAKER_RECOVERY_SECONDS=300              # 熔断恢复探测间隔

# === v4 新增:子进程监控 ===
HEARTBEAT_INTERVAL_SECONDS=5                      # 子进程心跳写 Redis 间隔
HEARTBEAT_STALE_SECONDS=30                        # Backend 标记 Run crashed 的阈值
PERMISSION_ASK_TIMEOUT_SECONDS=300                # permission ask 超时 fail-safe deny
SSE_TICKET_TTL_SECONDS=60                         # SSE ticket 过期时间
SSE_MAX_CONNECTIONS_PER_SESSION=3                 # 单个 session 最多 SSE 连接数(防多 tab)

# === v4 新增:Fork ===
FORK_MAX_DEPTH=2                                  # Fork 嵌套上限
FORK_TIMEOUT_SECONDS=300                          # 单次 Fork 超时

# === 资源/并发(按硬件基线配置)===
# 4C8G 推荐:
MAX_CONCURRENT_RUNS=3
QUEUE_MAX_SIZE=20

# 2C2G 降级(本地 fallback 场景):
# MAX_CONCURRENT_RUNS=1
# QUEUE_MAX_SIZE=10

# === v4 新增:资源监控 ===
RESOURCE_MONITOR_INTERVAL=60                      # 监控扫描间隔(秒)
MEMORY_WARNING_PERCENT=70                         # 警告阈值(%)
MEMORY_CRITICAL_PERCENT=85                        # 严重阈值(%)

# === v4 新增:可观测性 ===
OTEL_EXPORTER=stdout                              # stdout | otlp
OTEL_EXPORTER_OTLP_ENDPOINT=                      # 若 OTEL_EXPORTER=otlp,填 collector 地址
PROMETHEUS_ENABLED=true                           # 是否暴露 /metrics

# === v4 新增:Entropy Detection ===
ENTROPY_CHECK_ENABLED=true
ENTROPY_CHECK_CRON=0 3 * * 0                      # 每周日 03:00 跑一次
ENTROPY_THRESHOLD_GUARDRAIL_RATE=0.3              # 护栏触发率告警阈值
ENTROPY_THRESHOLD_TOOL_ERROR_RATE=0.2
ENTROPY_THRESHOLD_COMPACTION_RATE=0.2
ENTROPY_THRESHOLD_TURN_GROWTH=0.5
ENTROPY_AUTO_CALIBRATE=true                       # 每周自动校准阈值
```

**启动时校验**(Backend `lifespan` 启动钩子):

```python
# backend/app/core/config.py
def validate_secrets(settings):
    for name, value in [
        ("JWT_SECRET", settings.JWT_SECRET),
        ("CALLBACK_SECRET", settings.CALLBACK_SECRET),
        ("ENCRYPTION_KEY", settings.ENCRYPTION_KEY),
    ]:
        if len(value) < 32:
            raise ValueError(f"{name} must be at least 32 characters")
    
    secrets = {settings.JWT_SECRET, settings.CALLBACK_SECRET, settings.ENCRYPTION_KEY}
    if len(secrets) != 3:
        raise ValueError("JWT_SECRET, CALLBACK_SECRET, ENCRYPTION_KEY must be 3 different values")
```

任何一个校验失败,Backend 拒绝启动,打印明确错误。

---

## 附录 A: v4 修订清单

本次修订共 30 处精确修补,对应 Batch 1-5 review + PDF 补丁 + Master review + 用户第 11 轮反馈:

| # | 位置 | 修订内容 | 来源 |
|---|---|---|---|
| 1 | Header | 版本 3.1 → 4.0,v4 变更摘要 | — |
| 2 | §1 Layer 3 职责边界 | 补充"Harness 单实例架构(仅子进程)"说明 | Master M1 / Batch 1 R2 |
| 3 | §2.1 拓扑图 | Backend 进程内不再画 Harness Runtime | 同上 |
| 4 | §2.2 服务职责表 | 资源预算从 2C2G 升到 4C8G 基线 + 3 档推荐 + 子进程行 | Batch 1 §0 / 用户第 11 轮 |
| 5 | §2.3 v1 对比最后一行 | Harness 位置修订 | Master M1 |
| 6 | §3.1 任务执行流程 | 重写:SSE ticket 握手 / 心跳 / permission ask Redis BLPOP / 回调协议方案 A | Batch 2 §A3-7 / Batch 3 B3-1/2/3 / Batch 1 §R4 |
| 7 | §3.3 并发控制表 | MAX_CONCURRENT_RUNS 按硬件分档 / RUN_TIMEOUT 按 agent_type 分档 / 新增 HEARTBEAT / PERMISSION_ASK_TIMEOUT / SSE_TICKET_TTL / FORK_MAX_DEPTH 参数 | Batch 2 §A4-2 / Batch 3 B3-2 |
| 8 | §4.2 表清单标题 | 14 张 → 19 张,列出新增 5 张表 | Master M4 |
| 9 | §4 runs 表 | 加 cache_hit_tokens / cache_miss_tokens / cache_creation_tokens / agent_type / run_mode / parent_run_id / harness_version 字段 | Batch 1 §3.5 / PDF 补丁 P8 |
| 10 | §4 messages 表 | sequence_no 并发原子性 + text_preview 生成规则明文化 | Batch 3 B3-4 |
| 11 | §4 providers 表 | 增加 scope 字段 + 删 user_id=admin hack + capabilities 强制字段 | Batch 1 v2 §Q4 / Batch 3 §A9-3 |
| 12 | §4 im_bindings 表 | 唯一约束改为三元组 `(channel, platform_user_id, platform_chat_id)` | Batch 3 §B3-IV |
| 13 | §4 新增 skill_installs 表 | Skills Market 持久化 | Batch 1 §R7 |
| 14 | §4 新增 coordinator_plans 表 | Coordinator 崩溃恢复 checkpoint | Batch 2 §A4-3 / Master M3 |
| 15 | §4 新增 permission_requests 表 | permission ask 协议持久化 + 超时清理 | Batch 2 §A3-7 |
| 16 | §4 新增 im_message_dedup 表 | IM webhook 幂等 | Batch 3 B3-5 |
| 17 | §4 新增 user_memories 表 | Memory Layer 2 用户级 | Batch 2 §A3-9 |
| 18 | §4.3 表关系图 | 更新为 19 张表 | 同 #8 |
| 19 | §5.1 PrismMessage | role 简化为 user/assistant,tool_result 作为 content;加 is_skill_context 标记 | Batch 2 §A3-2 |
| 20 | §6.1 认证 | 加 POST /auth/sse-ticket | Batch 1 v2 §R4 |
| 21 | §6.3 任务 | 加 POST /sessions/{id}/permission-answer | Batch 2 §A3-7 / Batch 3 B3-1 |
| 22 | §6.4 Run | 加 POST /runs/{id}/resume(Coordinator 恢复) | Master M3 |
| 23 | §6.5 SSE | 改用 ticket + last_event_id 重连参数 | Batch 1 v2 §R4 |
| 24 | §6.10/6.11/6.12 | 理顺编号 + 加 /metrics / /health/live /ready /detailed / /run-crashed | Batch 5 §A12-6 / Batch 3 §A7-6 |
| 25 | §7.1 SSE 事件类型 | 新增 tool_use_delta / message_complete / coordinator_plan_update / permission_ask / permission_answered / compaction_in_progress / run_crashed 事件 + 通道分类表 | Batch 2 §A3-7 / Batch 3 B3-3 / Batch 4 §B4-3 |
| 26 | §7.2 SSE 连接约定 | ticket 握手协议 + 状态机 + last_event_id 重连 + tab 限制 | Batch 1 v2 §R4 / Batch 3 §B3-III / Batch 4 §B4-4 |
| 27 | §8 目录结构 | 补齐 Backend 新增 services(sse_ticket/permission_ask/heartbeat/alert_dispatcher/skill_install/coordinator_recovery/im_dedup)+ metrics/ + logging/ + api/v1/skills.py + api/v1/health.py;子进程新增 harness/permissions/ask_protocol.py + harness/heartbeat.py + logging/ + tracing/ + hooks/decision.py | 全批次 |
| 28 | §9.1 回调协议 | 方案 A 重写:Redis 流式直通 + HTTP 关键事件 + 回调事件分类表 | Batch 1 §3.3 D3 / Master M2 |
| 29 | §9.2 Redis 表 | 加 SSE ticket / stream / permission / heartbeat / coord_plan + 命名空间规范 + ACL 隔离建议 | Batch 1 v2 §R4 / Batch 3 §B3-I |
| 30 | §9.4 Harness 内部通信 | 反映单实例事实 + 跨进程 Redis 通道 + Backend 不持有 | Master M1 |
| 31 | §11 部署模式 | 重命名 + 双模态(云端主 + 本地 fallback)+ healthcheck / resource limits + monitoring 叠加 | 用户第 11 轮 + Batch 5 §B5-V |
| 32 | §11.4 环境变量 | 三密钥独立 + 启动校验 + 按 agent_type 分档 timeout + 子进程监控变量 + OTel / Prometheus / Entropy 变量 | Batch 1 v2 §3.6 / Batch 2 §A4-2 / Batch 5 全 |

---

> **文档维护说明**:本文档定义了 Prism v2 的技术骨架。Schema 变更、API 路由变更、服务拓扑变更、Harness 子系统变更必须先更新本文档,再执行实现。
> **最后更新**: 2026-04-18 (v4 review 修订版) | **下一步**: DOC-02 Model Adapter and Prompt Engine
