# Prism 棱镜 v2 — Backend Session / Run / Task (DOC-07)

> **文档编号**: DOC-07
> **版本**: 4.0(Review 修订版)
> **日期**: 2026-04-18
> **性质**: 实现文档 — 会话管理、Run 生命周期、任务提交/排队/推进、SSE 推送、CLI 子进程调度的完整后端链路
> **前置依赖**: DOC-01 v4(Schema: sessions + session_queue_items + runs + messages + tool_executions + **coordinator_plans + im_message_dedup + permission_requests + user_memories + skill_installs** 新增 5 表), DOC-02 v4 Task 2.1, DOC-03 v4(Harness Runtime), DOC-06 v4(认证体系)
> **Phase**: 2(后端功能模块)
> **Task 数**: 4
> **v4 变更摘要**: 基于 5 轮 review 修订,25 处精确修补(详见文末 §附录 A)。核心修订:**sequence_no 并发原子性(PostgreSQL per-session 序列 或 advisory_xact_lock)**、**Run cancel 三模式(graceful / force / also_cancel_queue)**、**回调协议方案 A 双通道**(接收 Redis 直通 text_delta/tool_use_delta + HTTP 带重试的关键事件)、**`POST /sessions/{id}/permission-answer` 端点(新)**、**HeartbeatMonitor 后台 task(扫 harness:heartbeat:* 超 30s 标记 crashed)**、**SSE ticket 消费 + last_event_id 补发 + tab 限制(每 session ≤3 连接)**、**subprocess 启动参数标准化**、**coordinator_recovery 服务(从 coordinator_plans 读 checkpoint 重启子进程)**、alert_dispatcher、**IM Webhook 幂等**(im_message_dedup 表)。ADR 编号从 ADR-060 接续至 ADR-069。
> **审计关注点**:
> - **v4 sequence_no 原子性**:`messages.sequence_no` 并发 insert 时,用 PostgreSQL per-session 独立序列 或 `pg_advisory_xact_lock + COALESCE(MAX,0)+1` 两种方案之一,避免竞态导致重复(ADR-060)
> - **v4 回调方案 A 双通道**:Backend callback_service 同时消费 Redis PUBLISH(text_delta/tool_use_delta)和 HTTP POST(关键事件)两类通道,按事件类型路由持久化(ADR-063)
> - **v4 三模式 cancel**:`POST /runs/{id}/cancel` 支持 `mode=graceful|force|also_cancel_queue`(ADR-062)
> - **v4 HeartbeatMonitor**:每 10s SCAN Redis `harness:heartbeat:*`,超 30s 无心跳标记 Run crashed + promote 队列(ADR-065)
> - **v4 harness_summary JSONB schema 定义**:`runs.harness_summary` 字段需要明确的 schema 约定(字段名、类型、含义),否则 DOC-12 v4 的 Observability 和前端的 Harness 展示无法稳定消费

---

## 目录

1. [Task 7.1: Session CRUD 与消息查询](#task-71-session-crud-与消息查询)
2. [Task 7.2: Task 提交与 Run 生命周期](#task-72-task-提交与-run-生命周期)
3. [Task 7.3: Callback Service 与 SSE Manager](#task-73-callback-service-与-sse-manager)
4. [Task 7.4: CLI 子进程调度](#task-74-cli-子进程调度)

---

## 前置定义：harness_summary JSONB Schema

在所有 Task 开始前，先定义 `runs.harness_summary` 的 JSONB 结构约定。DOC-03 的 HarnessRuntime 在 Run 完成时写入此字段，DOC-12 的 Observability 和前端 Harness 面板消费此字段。

```python
"""
runs.harness_summary JSONB Schema 约定

写入方: executor/harness/lifecycle.py → HarnessRuntime.get_run_harness_summary()
消费方: 
  - DOC-09 GET /admin/audit-logs（聚合分析）
  - DOC-12 Observability（Entropy Detection 的信号源）
  - DOC-11 前端 Harness 面板
"""

# 示例值
HARNESS_SUMMARY_EXAMPLE = {
    # === 基础统计 ===
    "turn_count": 12,                          # TAOR 循环总次数
    "total_tool_calls": 8,                     # 工具调用总次数
    "total_tool_errors": 1,                    # 工具执行失败次数
    
    # === Harness 治理统计 ===
    "guardrail_triggers": 2,                   # 护栏规则触发次数
    "guardrail_details": [                     # 触发详情（最多保留 10 条）
        {"rule_id": "GR-PLATFORM-001", "tool_name": "bash", "action": "deny"},
    ],
    "permission_denials": 1,                   # 权限拒绝次数
    "hook_fires": 5,                           # Hook 触发次数
    "hook_modifications": 0,                   # Hook 改写工具输入的次数
    
    # === 上下文管理 ===
    "compaction_events": [                     # Compaction 触发记录
        {"tier": 1, "turn": 8},                # 第 8 轮触发了 Tier 1 micro-compact
    ],
    "peak_context_usage_ratio": 0.82,          # 峰值上下文使用率
    
    # === 循环检测 ===
    "loop_detections": 0,                      # 循环检测命中次数
    
    # === Middleware ===
    "middleware_count": 3,                     # 活跃中间件数量
    "guardrail_rules_count": 5,               # 护栏规则总数
    
    # === 路由 ===
    "route_mode": "direct",                    # "direct" | "coordinator"
    "route_agent_type": "general",             # 实际使用的 Agent 类型
    "route_reason": "默认路由: general",        # 路由决策理由
    
    # === 子 Agent（如有 fork）===
    "fork_count": 0,                           # Fork 次数
    "fork_details": [],                        # [{"agent_type": "research", "turns": 5, "success": true}]
}
```

此 schema 是约定而非强制校验——写入方按此结构填充，消费方按此结构读取，缺失字段用默认值兜底。

---

## Task 7.1: Session CRUD 与消息查询

### Part A — 设计与解释

#### 问题陈述

用户通过 Web UI 或 IM 创建和管理对话会话。每个会话包含多轮 Run，每个 Run 包含多条消息。本 Task 实现会话的增删改查和消息的增量查询。

#### 数据关系

```
User ─── Session ─── Run ─── Message
              │                  │
              │                  └── ToolExecution
              └── SessionQueueItem
```

#### 验收标准(v4 扩展)

- 会话 CRUD 正常工作(创建/列表/详情/更新/删除)
- 删除会话时级联删除所有 Run 和 Message
- 消息列表支持 `after_sequence_no` 增量查询(SSE 断线重连后拉取新消息)
- 会话列表按 `updated_at DESC` 排序,置顶会话优先
- 所有查询强制 `WHERE user_id = :current_user_id`(铁律 4)
- **v4:`generate_text_preview(role, content, tool_lookup)` 按 DOC-01 v4 §4.2 messages 表规则生成 text_preview**
  - user message 含 tool_result_block → 前缀 `[tool_result:{tool_name}]` + 首个 text block 前 200 字
  - assistant message 含 tool_use_block → 前缀 `[tool_use:{tool_name}]` + tool_input JSON preview
  - 纯 text → 前 200 字
  - 空内容 → `[empty]`

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的会话和消息管理。DOC-06 的认证体系已完成，JWT + get_current_user 可用。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

DOC-06 全部完成，认证链路可用

## 要创建的文件

```
backend/app/
├── schemas/
│   ├── session.py             # Session 请求/响应 Schema
│   └── message.py             # Message 响应 Schema
├── services/
│   └── session_service.py     # Session + Message 业务逻辑
└── api/v1/
    └── sessions.py            # Session + Message API 端点
```

## 实现规范

### 1. app/schemas/session.py

```python
class CreateSessionRequest(BaseModel):
    title: str | None = None
    config_snapshot: dict = {}           # 可选的初始配置（model, provider 等）

class UpdateSessionRequest(BaseModel):
    title: str | None = None
    is_pinned: bool | None = None
    config_snapshot: dict | None = None

class SessionResponse(BaseModel):
    id: str
    title: str | None
    status: str                          # "idle" | "running" | "queued"
    blocking_run_id: str | None
    config_snapshot: dict
    is_pinned: bool
    pinned_at: datetime | None
    im_channel: str | None
    im_chat_id: str | None
    message_count: int                   # 计算字段：该 session 的消息总数
    last_message_preview: str | None     # 最新消息的 text_preview
    created_at: datetime
    updated_at: datetime

class SessionListResponse(BaseModel):
    """列表用的精简版"""
    id: str
    title: str | None
    status: str
    is_pinned: bool
    last_message_preview: str | None
    updated_at: datetime
```

### 2. app/schemas/message.py

```python
class MessageResponse(BaseModel):
    id: str
    run_id: str | None
    role: str                            # "user" | "assistant" | "tool_use" | "tool_result" | "system"
    content: list[dict]                  # PrismMessage.content 的 JSON
    text_preview: str | None
    sequence_no: int
    created_at: datetime
```

### 3. app/services/session_service.py

```python
"""
Session + Message 业务逻辑

所有查询强制 user_id 过滤（铁律 4）。
"""

class SessionService:
    def __init__(self, db: Session):
        self._db = db
    
    def list_sessions(self, user_id: str, page: int = 1, per_page: int = 20) -> tuple[list, int]:
        """
        会话列表。
        
        排序规则：
        1. is_pinned=True 的会话优先，按 pinned_at DESC
        2. 其余按 updated_at DESC
        
        返回: (sessions, total_count)
        """
        ...
    
    def create_session(self, user_id: str, data: CreateSessionRequest) -> "SessionModel":
        ...
    
    def get_session(self, user_id: str, session_id: str) -> "SessionModel":
        """获取单个会话。不存在或不属于当前用户 → 404"""
        ...
    
    def update_session(self, user_id: str, session_id: str, data: UpdateSessionRequest) -> "SessionModel":
        """
        更新会话。
        
        如果 is_pinned 从 False 变为 True，设置 pinned_at = now()
        如果 is_pinned 从 True 变为 False，清除 pinned_at
        """
        ...
    
    def delete_session(self, user_id: str, session_id: str) -> None:
        """删除会话。ON DELETE CASCADE 自动级联删除 runs + messages + queue_items"""
        ...
    
    def list_messages(
        self,
        user_id: str,
        session_id: str,
        after_sequence_no: int | None = None,
        limit: int = 100,
    ) -> list["MessageModel"]:
        """
        消息列表。
        
        after_sequence_no: 只返回 sequence_no > 该值的消息（增量查询）。
        用于 SSE 断线重连后拉取新消息。
        """
        # 先验证 session 属于 user（铁律 4）
        ...
```

### 4. app/api/v1/sessions.py

按 DOC-01 v3 §6.2 的路由表实现：

```python
"""
Session + Message API 端点

GET    /sessions                        — 会话列表
POST   /sessions                        — 创建空会话
GET    /sessions/{id}                   — 会话详情
PATCH  /sessions/{id}                   — 更新会话
DELETE /sessions/{id}                   — 删除会话
GET    /sessions/{id}/messages          — 消息列表（支持增量）
"""

router = APIRouter(prefix="/sessions", tags=["sessions"])

@router.get("", response_model=ApiResponse[PagedResponse[SessionListResponse]])
def list_sessions(page: int = 1, per_page: int = 20, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ...

@router.post("", response_model=ApiResponse[SessionResponse], status_code=201)
def create_session(data: CreateSessionRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ...

@router.get("/{session_id}", response_model=ApiResponse[SessionResponse])
def get_session(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ...

@router.patch("/{session_id}", response_model=ApiResponse[SessionResponse])
def update_session(session_id: str, data: UpdateSessionRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ...

@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ...

@router.get("/{session_id}/messages", response_model=ApiResponse[list[MessageResponse]])
def list_messages(
    session_id: str,
    after_sequence_no: int | None = None,
    limit: int = 100,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ...

> 查询参数 `limit` 增加上限校验：`max_limit = 500`，超过返回 422。
```

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/schemas/session.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/schemas/message.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/services/session_service.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/api/v1/sessions.py

# 2. API 测试
TOKEN="..."  # admin token

# 创建会话
SID=$(curl -s -X POST http://localhost:8000/api/v1/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"测试会话"}' | python -c "import sys,json; print(json.load(sys.stdin)['data']['id'])")
echo "Session: $SID"

# 列表
curl -s http://localhost:8000/api/v1/sessions -H "Authorization: Bearer $TOKEN" | python -m json.tool

# 详情
curl -s http://localhost:8000/api/v1/sessions/$SID -H "Authorization: Bearer $TOKEN" | python -m json.tool

# 置顶
curl -s -X PATCH http://localhost:8000/api/v1/sessions/$SID \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"is_pinned":true}' | python -m json.tool
# 期望：is_pinned=true, pinned_at 有值

# 消息列表（空）
curl -s "http://localhost:8000/api/v1/sessions/$SID/messages" -H "Authorization: Bearer $TOKEN" | python -m json.tool

# 删除
curl -s -o /dev/null -w "%{http_code}" -X DELETE http://localhost:8000/api/v1/sessions/$SID -H "Authorization: Bearer $TOKEN"
# 期望：204

# 铁律 4：用另一个用户的 token 访问 → 404
```

## 完成后

1. 更新 PROGRESS.md
2. 加载 Simplify skill 审查
3. 加载 PJR skill 验证
4. `git add -A && git commit -m "feat: session CRUD + message incremental query"`
```

---

## Task 7.2: Task 提交与 Run 生命周期

### Part A — 设计与解释

#### 问题陈述

`POST /tasks` 是 Prism 的核心入口——用户提交一条消息后，系统决定是立即执行还是排队。Run 的生命周期是一个状态机，从 pending → running → completed/failed/cancelled/timeout。当前 Run 完成后，需要原子性地推进队列中的下一条消息。

#### Run 状态机

```
         POST /tasks
             │
             ▼
         ┌─ pending ─┐
         │            │
    session idle   session busy
         │            │
         ▼            ▼
      running      queued (session_queue_items)
         │            │
    ┌────┼────┐   等待当前 run 完成
    │    │    │       │
    ▼    ▼    ▼       ▼
completed failed timeout  promote → pending → running → ...
    │    │    │
    └────┼────┘
         │
    promote_next()
```

#### promote 原子性保障（审计关注点）

promote_next() 必须在单个 DB 事务中完成以下操作：

```python
with db.begin():
    # 1. 当前 Run 标记完成
    current_run.status = "completed"
    current_run.finished_at = now()
    current_run.harness_summary = summary_json  # 写入 Harness 摘要
    
    # 2. Session 解除阻塞
    session.blocking_run_id = None
    session.status = "idle"
    
    # 3. 查找队列中下一条
    next_item = db.query(SessionQueueItem)\
        .filter(session_id=..., status="queued")\
        .order_by(sequence_no)\
        .with_for_update(skip_locked=True)\  # ← 防并发重复 promote
        .first()
    
    if next_item:
        # 4. 标记 promoted
        next_item.status = "promoted"
        
        # 5. 创建新 Run
        new_run = Run(session_id=..., prompt=next_item.prompt, status="pending", ...)
        db.add(new_run)
        db.flush()
        
        # 6. Session 重新阻塞
        session.blocking_run_id = new_run.id
        session.status = "running"
    
    db.commit()
    # 事务外：如果有 new_run，启动 CLI 子进程
```

`with_for_update(skip_locked=True)` 是关键——当多个并发回调同时到达时（理论上不应发生，但防御性编程），只有一个事务能锁定队列 item，其他事务跳过。

#### harness_summary 写入时机

CLI 子进程在 Run 完成时通过 `run_complete` 回调将 `harness_summary` JSON 传给 Backend。Backend 在 promote 事务中将其写入 `runs.harness_summary`。schema 定义见本文档顶部的前置定义。

> **Promote 原子性 (P1)**：`session_queue_items` 的 promote 操作必须与 Run 完成在同一 DB 事务中执行（单次 commit）。Backend 启动时检查是否有 `status=running` 但对应子进程已退出的 Run，标记为 failed 并 promote 下一个队列项。

#### 设计决策(ADR)

- **ADR-060(sequence_no 并发原子性)**:`messages.sequence_no` 当多个回调并发写入同一 session 的 message 时,单纯 `COALESCE(MAX,0)+1` 有竞态窗口(两个 tx 读到同样的 max)。v4 两种可选方案:
  - **方案 1(推荐)**:PostgreSQL per-session 独立序列 `messages_seq_{session_id}`,首次用 `CREATE SEQUENCE IF NOT EXISTS`,取值 `nextval(...)`
  - **方案 2**:advisory xact lock + max+1,`SELECT pg_advisory_xact_lock(hash(session_id))` 持到 tx commit

  来源:Batch 3 §A7-2。

- **ADR-061(promote 原子事务)**:promote_next() 必须在单个 DB 事务中完成:`旧 Run 完成 + session 解锁 + FOR UPDATE SKIP LOCKED 查 queue + 新 Run 创建 + session 重新阻塞`,全部 commit 后才启动子进程。来源:Batch 3 §A7-2。

- **ADR-062(Run cancel 三模式)**:`POST /runs/{id}/cancel` 接受 `mode`:
  - `graceful`(默认):向子进程发 SIGTERM,子进程在当前 tool 执行完后 break TAOR 循环并 exit;不影响排队
  - `force`:向子进程发 SIGKILL,立即终止;不影响排队
  - `also_cancel_queue`:graceful 当前 + 把后续 queue items 标记 cancelled

  来源:Batch 3 §A7-2。

#### 验收标准(v4 扩展)

- `POST /tasks` 在 session idle 时立即创建 Run 并启动子进程
- `POST /tasks` 在 session busy 时创建 queue_item 并返回 `accepted_type: "queued_query"`
- Run 完成后自动 promote 队列中下一条
- promote 操作在单个 DB 事务中原子完成
- 并发 promote 不会重复创建 Run(FOR UPDATE SKIP LOCKED)
- **v4:sequence_no 用 PostgreSQL per-session 序列 或 advisory_xact_lock,多进程并发 insert 测试无重复**
- **v4:`POST /runs/{id}/cancel` 支持 `mode=graceful|force|also_cancel_queue`**
- harness_summary 在 run_complete 回调时写入

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的任务提交和 Run 生命周期管理。核心挑战是 promote 的原子性。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

Task 7.1 已完成

## 要创建的文件

```
backend/app/
├── schemas/
│   ├── task.py                # Task 提交请求/响应 Schema
│   └── run.py                 # Run 响应 Schema（含 harness_summary）
├── services/
│   ├── task_service.py        # 任务提交逻辑
│   ├── run_lifecycle.py       # Run 状态机 + promote
│   └── session_queue.py       # 排队管理
└── api/v1/
    ├── tasks.py               # Task API 端点
    └── runs.py                # Run API 端点
```

## 实现规范

### 1. app/schemas/task.py

```python
class SubmitTaskRequest(BaseModel):
    session_id: str | None = None     # None = 自动创建新 Session
    prompt: str                        # 用户输入
    agent_type: str | None = None     # 显式指定 Agent 类型（None = 自动路由）

class SubmitTaskResponse(BaseModel):
    session_id: str
    run_id: str | None                 # 排队时为 None
    accepted_type: str                 # "immediate" | "queued_query"
    queue_position: int | None         # 排队时的位置
```

### 2. app/schemas/run.py

```python
class RunResponse(BaseModel):
    id: str
    session_id: str
    prompt: str
    status: str
    model: str
    provider_id: str
    schedule_mode: str
    error_message: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    turn_count: int | None
    harness_summary: dict | None       # JSONB，schema 见文档前置定义
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
```

### 3. app/services/task_service.py

```python
"""
任务提交逻辑

POST /tasks 的核心处理流程：
1. 如果 session_id 为 None → 创建新 Session
2. 校验 Session 属于当前用户
3. 如果 Session 空闲（status=idle, blocking_run_id=None）→ 立即执行
4. 如果 Session 繁忙（有 blocking_run）→ 入队
"""

class TaskService:
    def __init__(self, db: Session, settings):
        self._db = db
        self._settings = settings
    
    def submit(self, user_id: str, data: SubmitTaskRequest) -> SubmitTaskResponse:
        """
        提交任务。
        
        此方法在单个 DB 事务中完成所有状态变更。
        子进程启动在事务提交后执行（避免事务回滚但子进程已启动的不一致）。
        
        返回 SubmitTaskResponse，调用方根据 accepted_type 决定后续行为。
        """
        # 1. 确定 Session
        if data.session_id is None:
            session = self._create_session(user_id)
        else:
            session = self._get_user_session(user_id, data.session_id)
        
        # 2. 判断是否立即执行
        if session.blocking_run_id is None:
            run = self._create_run(session, user_id, data)
            session.blocking_run_id = run.id
            session.status = "running"
            self._db.flush()
            return SubmitTaskResponse(
                session_id=session.id,
                run_id=run.id,
                accepted_type="immediate",
                queue_position=None,
            )
        else:
            # 3. 入队
            queue_item = self._enqueue(session, data.prompt)
            return SubmitTaskResponse(
                session_id=session.id,
                run_id=None,
                accepted_type="queued_query",
                queue_position=queue_item.sequence_no,
            )
    
    def _create_run(self, session, user_id: str, data: SubmitTaskRequest) -> "RunModel":
        """创建 Run 记录"""
        # 从 session.config_snapshot 或用户默认 Provider 获取 model + provider_id
        ...
    
    def _enqueue(self, session, prompt: str) -> "SessionQueueItemModel":
        """
        入队。v4:sequence_no 走 ADR-060 原子性方案。
        检查队列大小不超过 QUEUE_MAX_SIZE
        """
        ...
```

### 3.1 sequence_no 原子性实现(v4 ADR-060)

```python
# app/services/sequence_service.py(v4 新文件)

"""
Message sequence_no 并发原子性(v4 ADR-060)
方案 1(推荐):PostgreSQL per-session 独立序列
方案 2:advisory_xact_lock + max+1(兼容性好)
"""

from sqlalchemy import text


def get_next_message_sequence_no(db, session_id: str) -> int:
    """
    方案 1:使用 session_id 作为 sequence name
    首次调用时创建序列(IF NOT EXISTS 语义)
    """
    # session_id 的 hyphen 替换为 underscore 做序列名合法字符
    seq_name = f"messages_seq_{session_id.replace('-', '_')}"
    db.execute(text(f'CREATE SEQUENCE IF NOT EXISTS "{seq_name}"'))
    result = db.execute(text(f"SELECT nextval(:name)"), {"name": seq_name})
    return result.scalar()


def get_next_sequence_no_advisory(db, session_id: str) -> int:
    """
    方案 2:advisory_xact_lock(兼容性好,无需建序列)
    用 session_id 的 bigint hash 作为 lock key。commit 时锁自动释放。
    """
    lock_key = int.from_bytes(
        session_id.replace('-', '')[:16].encode(), 'big'
    ) % (2**63)
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": lock_key})
    max_seq = db.execute(
        text("SELECT COALESCE(MAX(sequence_no), 0) FROM messages WHERE session_id = :sid"),
        {"sid": session_id},
    ).scalar()
    return max_seq + 1
    # tx commit 时自动释放 advisory lock
```

### 4. app/services/run_lifecycle.py

```python
"""
Run 生命周期状态机 + promote

⚠️ 审计关注点：promote_next() 必须在单个 DB 事务中原子完成

状态转换：
  pending → running（子进程启动成功时）
  running → completed（正常完成）
  running → failed（执行异常）
  running → timeout（超时 kill）
  running → cancelled（用户取消）
  pending → cancelled（子进程启动前取消）
"""

class RunLifecycle:
    def __init__(self, db: Session, settings):
        self._db = db
        self._settings = settings
    
    def mark_running(self, run_id: str) -> None:
        """子进程启动成功后调用"""
        run = self._get_run(run_id)
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        self._db.flush()
    
    def complete_and_promote(
        self,
        run_id: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        turn_count: int,
        harness_summary: dict,
    ) -> str | None:
        """
        标记 Run 完成并原子性推进队列。

        返回: 新创建的 Run ID（如果有队列消息被 promote），否则 None

        ⚠️ 整个方法在一个 DB 事务中执行。
        使用 SELECT ... FOR UPDATE SKIP LOCKED 防止并发重复 promote。

        > **事务一致性 (P1)**：`complete_and_promote()` 中移除端点层（router）的多余 `db.commit()`。所有事务由 Service 层统一管理：`run_service.complete_run()` 内部在同一事务中完成 Run 状态更新 + queue promote + harness_summary 写入，然后统一 commit。
        """
        run = self._get_run(run_id)
        session = run.session
        
        # 1. 标记完成
        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        run.input_tokens = input_tokens
        run.output_tokens = output_tokens
        run.cost_usd = cost_usd
        run.turn_count = turn_count
        run.harness_summary = harness_summary
        
        # 2. 解除 Session 阻塞
        session.blocking_run_id = None
        session.status = "idle"
        
        # 3. 查找下一个队列 item（FOR UPDATE SKIP LOCKED）
        from sqlalchemy import text
        next_item = self._db.query(SessionQueueItem)\
            .filter(
                SessionQueueItem.session_id == session.id,
                SessionQueueItem.status == "queued",
            )\
            .order_by(SessionQueueItem.sequence_no)\
            .with_for_update(skip_locked=True)\
            .first()
        
        new_run_id = None
        if next_item:
            # 4. promote
            next_item.status = "promoted"
            
            # 5. 创建新 Run
            new_run = Run(
                session_id=session.id,
                user_id=run.user_id,
                prompt=next_item.prompt,
                status="pending",
                model=run.model,                # 继承上一次的 model 配置
                provider_id=run.provider_id,
                schedule_mode="queued",
            )
            self._db.add(new_run)
            self._db.flush()
            
            # 6. 重新阻塞 Session
            session.blocking_run_id = new_run.id
            session.status = "running"
            new_run_id = new_run.id
        
        self._db.commit()
        return new_run_id
    
    def fail_and_promote(self, run_id: str, error: str, harness_summary: dict | None = None) -> str | None:
        """标记失败并推进队列。逻辑同 complete_and_promote，status 为 failed。"""
        ...
    
    def cancel(self, run_id: str, mode: str = "graceful") -> None:
        """
        v4:取消 Run,三模式(ADR-062)。

        mode:
        - "graceful"(默认):向子进程发 SIGTERM → 子进程在当前 tool 执行完后 break
        - "force":向子进程发 SIGKILL → 立即终止
        - "also_cancel_queue":graceful 当前 + 把后续 queue items 标记 cancelled

        如果 status == "pending":直接标记 cancelled
        如果 status == "running":按 mode 处理
        """
        import os, signal
        run = self._get_run(run_id)

        if run.status == "pending":
            run.status = "cancelled"
            run.finished_at = datetime.now(timezone.utc)
            self._db.flush()
            return

        if run.status == "running" and run.subprocess_pid:
            if mode == "force":
                try:
                    os.kill(run.subprocess_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                # graceful / also_cancel_queue 都先 SIGTERM
                try:
                    os.kill(run.subprocess_pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass

        if mode == "also_cancel_queue":
            # 把后续 queue items 标记 cancelled
            self._db.query(SessionQueueItem)\
                .filter(
                    SessionQueueItem.session_id == run.session_id,
                    SessionQueueItem.status == "queued",
                ).update({"status": "cancelled"})

        run.status = "cancelled"
        run.finished_at = datetime.now(timezone.utc)
        self._db.commit()

    def mark_crashed(self, run_id: str, reason: str) -> str | None:
        """
        v4(ADR-065):HeartbeatMonitor 调用。标记 Run crashed + promote 队列。
        """
        run = self._get_run(run_id)
        run.status = "failed"
        run.error_message = reason
        run.finished_at = datetime.now(timezone.utc)
        # 沿用 fail_and_promote 的 promote 逻辑
        return self._promote_next(run)
    
    def timeout(self, run_id: str) -> str | None:
        """超时处理。kill 子进程 + 标记 timeout + promote。"""
        ...
```

### 5. app/services/session_queue.py

```python
"""
Session 排队管理

简单的 FIFO 队列，附加在 Session 上。
"""

class SessionQueueService:
    def __init__(self, db: Session):
        self._db = db
    
    def list_queue(self, user_id: str, session_id: str) -> list["SessionQueueItemModel"]:
        """列出排队消息"""
        ...
    
    def cancel_item(self, user_id: str, session_id: str, item_id: str) -> None:
        """取消排队消息（标记 cancelled，不物理删除）"""
        ...
    
    def get_queue_size(self, session_id: str) -> int:
        """获取当前队列大小（status=queued 的数量）"""
        ...
```

### 6. app/api/v1/tasks.py + runs.py

```python
# tasks.py
"""
Task API 端点

POST   /tasks                          — 提交任务（核心入口）
GET    /sessions/{id}/queue            — 获取队列消息
DELETE /sessions/{id}/queue/{item_id}  — 取消排队消息
POST   /sessions/{id}/cancel           — 取消当前 Run
"""

@router.post("/tasks", response_model=ApiResponse[SubmitTaskResponse], status_code=202)
def submit_task(data: SubmitTaskRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    提交任务。
    
    202 Accepted：任务已接受（不论立即执行还是排队）。
    如果 accepted_type == "immediate"，子进程在事务提交后异步启动。
    """
    result = TaskService(db, settings).submit(user.id, data)
    db.commit()
    
    if result.accepted_type == "immediate" and result.run_id:
        # 事务已提交，安全启动子进程
        # 子进程启动逻辑在 Task 7.4 实现
        _start_agent_subprocess(result.run_id)
    
    return ApiResponse(data=result)
```

```python
# runs.py
"""
Run API 端点

GET /runs/{id}                — Run 详情（含 harness_summary）
GET /sessions/{id}/runs       — Session 下的 Run 列表
"""

@router.get("/runs/{run_id}", response_model=ApiResponse[RunResponse])
def get_run(run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取 Run 详情。包含 harness_summary JSONB。"""
    ...
```

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/schemas/task.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/schemas/run.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/services/task_service.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/services/run_lifecycle.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/services/session_queue.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/api/v1/tasks.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/api/v1/runs.py

# 2. promote 原子性测试
docker compose -f docker-compose.dev.yml exec backend python -c "
from app.core.database import SessionLocal
from app.services.run_lifecycle import RunLifecycle
from app.models.run import Run
from app.models.session import Session, SessionQueueItem
from app.core.config import get_settings

settings = get_settings()

with SessionLocal() as db:
    # 模拟：创建 session + run + 2 个 queue items
    # 调用 complete_and_promote
    # 验证：run 标记 completed，queue item 1 标记 promoted，新 run 创建，session.blocking_run_id 更新
    # 验证：harness_summary 已写入
    print('Promote atomicity: manual verification needed')
"

# 3. API 测试
TOKEN="..."

# 提交任务（自动创建 session）
curl -s -X POST http://localhost:8000/api/v1/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"你好"}' | python -m json.tool
# 期望：accepted_type="immediate"，run_id 有值

# 提交第二个任务到同一 session（应排队）
# ...（需要第一个 run 正在执行时提交）
```

## 完成后

1. 更新 PROGRESS.md
2. 更新 DECISIONS.md：记录 ADR-027（promote 原子性——单事务 + FOR UPDATE SKIP LOCKED）、ADR-028（harness_summary JSONB schema 约定）
3. 加载 Simplify skill 审查
4. 加载 PJR skill 验证
5. `git add -A && git commit -m "feat: task submission + run lifecycle + atomic promote with harness_summary"`
```

---

## Task 7.3: Callback Service 与 SSE Manager(v4:双通道 + permission-answer + HeartbeatMonitor + ticket 消费)

### Part A — 设计与解释

#### 问题陈述

CLI 子进程通过 **双通道** 向 Backend 发送事件:(1) 高频 text_delta/tool_use_delta 走 Redis PUBLISH 直通;(2) 关键事件(tool_start/tool_end/message_complete/run_complete/permission_ask/harness_event)走 HTTP POST 带重试。Backend 同时消费两类通道:(1) SSE Manager 订阅 Redis channel `run:{run_id}:stream` forward 给前端;(2) HTTP callback_service 处理持久化 + promote。

**v4 核心新增能力**:
1. **双通道接收** — Backend SSE Manager 订阅 Redis 直通;callback_service 接收 HTTP 重要事件
2. **permission-answer 端点** — 前端用户点击允许/拒绝后的反向通信(DOC-03 v4 Task 3.3 ADR-028)
3. **HeartbeatMonitor 后台 task** — 扫描 `harness:heartbeat:*`,超 30s 无更新标记 Run crashed
4. **SSE ticket 消费 + last_event_id 补发 + tab 限制**

#### 回调 → DB → SSE 数据流(v4 双通道)

```
CLI 子进程                  Backend                        前端
    │                          │                             │
    │ [高频通道] Redis PUBLISH │                             │
    │ text_delta/tool_use_delta│                             │
    ├──────────────────────────┤                             │
    │                    Redis run:{run_id}:stream           │
    │                          │                             │
    │                          │ SSE Manager 订阅该 channel   │
    │                          │ forward 给 session_id       │
    │                          ├────────────────────────────>│
    │                          │                             │
    │ [关键事件通道] HTTP POST │                             │
    │ tool_start / tool_end /  │                             │
    │ message_complete /       │                             │
    │ run_complete /           │                             │
    │ permission_ask /         │                             │
    │ harness_event            │                             │
    ├──────────────────────────┤                             │
    │                          │ callback_service.handle:    │
    │                          │ - 按事件类型路由持久化      │
    │                          │ - 写 messages/tool_exec/... │
    │                          │ - run_complete → promote    │
    │                          │ - SSE Manager 二次推送      │
    │                          │   (关键事件必须到前端)      │
    │                          ├────────────────────────────>│
    │                          │                             │
    │                          │                             │ 用户点"允许"
    │                          │ POST /permission-answer     │
    │                          │<────────────────────────────┤
    │                          │ callback_service 处理:      │
    │                          │ - UPDATE permission_requests│
    │                          │ - RPUSH perm_answer:{req_id}│
    │ BLPOP 返回 → 继续        │                             │
    │<─────────────────────────┤                             │
    │                          │                             │
```

#### 设计决策(ADR)

- **ADR-063(回调协议方案 A)**:Backend 接收两类通道:
  - Redis PUBLISH 订阅 + forward(text_delta / tool_use_delta)
  - HTTP POST 带 X-Callback-Secret(其他关键事件)

  callback_service 按事件类型路由持久化。text_delta 仅 SSE forward,不写 DB(Adapter 本地已累积,message_complete 事件时整条写 DB)。来源:Batch 1 §3.3 D3, Master M2。

- **ADR-064(permission-answer 端点)**:`POST /sessions/{id}/permission-answer` 接受 `{request_id, decision}`,Backend:
  1. `UPDATE permission_requests SET status='answered', decision=X, answered_at=now() WHERE id=request_id AND user_id=current_user.id`(校验归属)
  2. `RPUSH perm_answer:{request_id} {decision}`(触发子进程 BLPOP 返回)
  3. 写 audit_log:`permission.answered`

  来源:Batch 2 §A3-7。

- **ADR-065(HeartbeatMonitor 崩溃恢复)**:Backend lifespan 启动后台 task:
  ```python
  class HeartbeatMonitor:
      async def run(self):
          while True:
              await self._scan_once()
              await asyncio.sleep(10)
      async def _scan_once(self):
          # SCAN harness:heartbeat:* → 检查每个 key 的 age > 30s → 标记 crashed + promote
  ```
  来源:Batch 3 B3-2。

#### 验收标准(v4 扩展)

- Callback 端点正确处理所有事件类型
- **v4:Redis 直通 text_delta/tool_use_delta 通过 SSE Manager forward,不走 DB 持久化**(Adapter 本地累积到 message_complete 整条写)
- 消息持久化到 messages 表,sequence_no 按 ADR-060 原子生成
- **v4:SSE 推送格式带 `id`(UUID7),前端 lastEventId 跟踪;Redis Stream `sse:{session_id}:stream` 保留最近 200 条(按事件 id)用于 last_event_id 补发**
- **v4:每 session 最多 3 个 SSE 连接**(多 tab 限制,Redis key `sse:conns:{session_id}` SETNX + INCR)
- harness_event 写入 audit_logs
- run_complete 触发 promote(原子性,复用 Task 7.2 的 RunLifecycle)
- 回调认证通过 X-Callback-Secret header(CALLBACK_SECRET,不是 JWT_SECRET)
- **v4:`POST /sessions/{id}/permission-answer` 端点新增**,同时 UPDATE permission_requests + RPUSH `perm_answer:{request_id}`
- **v4:`POST /internal/run-crashed` 端点**(HeartbeatMonitor 触发,internal-only)
- **v4:HeartbeatMonitor 后台 task**:每 10s 扫 `harness:heartbeat:*`,超 30s 标记 crashed + promote
- **v4:SSE URL 改用 `?ticket=X&last_event_id=Y`**(DOC-06 v4 ADR-051)

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的回调处理和 SSE 推送。Task 7.2 的 Run 生命周期已完成。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

Task 7.1 和 7.2 已完成

## 要创建的文件

```
backend/app/
├── services/
│   ├── callback_service.py      # 回调处理(sync DB path + v4 Redis 直通订阅)
│   ├── sse_manager.py           # SSE 推送(Redis pub/sub + last_event_id 补发 + tab 限制)
│   └── heartbeat_monitor.py     # v4 新文件:扫僵尸 Run
└── api/v1/
    ├── internal.py              # 内部回调端点 + v4 /internal/run-crashed
    └── sessions.py              # v4 新增 /sessions/{id}/permission-answer
```

## 实现规范

### 1. app/services/sse_manager.py

```python
"""
SSE Manager — Redis pub/sub 推送

每个 Session 一个 Redis channel: sse:{session_id}
前端通过 GET /sessions/{id}/stream?token=... 订阅。
"""

import redis
import json

class SSEManager:
    """v4:Redis pub/sub + Stream 补发 + tab 限制"""

    MAX_CONNS_PER_SESSION = 3
    STREAM_BUFFER_SIZE = 200  # 保留最近 200 条事件用于 last_event_id 补发

    def __init__(self, redis_url: str):
        self._redis = redis.Redis.from_url(redis_url)

    async def publish(self, session_id: str, event_name: str, data: dict, event_id: str | None = None) -> None:
        """
        v4:发布 SSE 事件 + 写入 Redis Stream(用于 last_event_id 补发)
        """
        import uuid
        event_id = event_id or str(uuid.uuid4())
        payload = {"id": event_id, "event": event_name, "data": data}

        # 1. 实时 pub/sub(在线连接立即收到)
        self._redis.publish(
            f"sse:{session_id}",
            json.dumps(payload),
        )

        # 2. 写入 Stream(供断线重连补发)
        self._redis.xadd(
            f"sse:{session_id}:stream",
            {"payload": json.dumps(payload)},
            maxlen=self.STREAM_BUFFER_SIZE,
            approximate=True,
        )

    def subscribe(self, session_id: str):
        """订阅 Redis channel + 直通 channel,返回 pubsub 对象"""
        pubsub = self._redis.pubsub()
        # v4:同时订阅"关键事件" channel 和 "子进程直通" channel
        pubsub.subscribe(f"sse:{session_id}")
        # 子进程 Redis 直通 channel(DOC-03 v4 ADR-022):通过 forward 机制桥接
        # 具体:callback_service 启动一个 forwarder task,监听 run:{run_id}:stream → 转发到 sse:{session_id}
        return pubsub

    async def backfill_since(self, session_id: str, last_event_id: str) -> list[dict]:
        """
        v4:从 Redis Stream 补发 last_event_id 之后的事件
        """
        entries = self._redis.xrange(
            f"sse:{session_id}:stream",
            min="-",
            max="+",
        )
        result = []
        found = False
        for _, fields in entries:
            payload = json.loads(fields[b"payload"])
            if found:
                result.append(payload)
            elif payload["id"] == last_event_id:
                found = True
        return result

    async def acquire_conn_slot(self, session_id: str) -> bool:
        """v4:多 tab 限制,每 session 最多 3 连接"""
        key = f"sse:conns:{session_id}"
        count = self._redis.incr(key)
        if count == 1:
            self._redis.expire(key, 3600)  # 1h 后自然过期
        if count > self.MAX_CONNS_PER_SESSION:
            self._redis.decr(key)
            return False
        return True

    async def release_conn_slot(self, session_id: str) -> None:
        self._redis.decr(f"sse:conns:{session_id}")
```

### 1.1 app/api/v1/sessions.py 新增 SSE 端点 + permission-answer(v4)

```python
from fastapi import Request
from fastapi.responses import StreamingResponse


@router.get("/sessions/{session_id}/stream")
async def session_stream(
    session_id: str,
    ticket: str,
    last_event_id: str | None = None,
    request: Request = None,
    sse_manager = Depends(get_sse_manager),
    ticket_service = Depends(get_ticket_service),
):
    """
    v4:SSE 流端点。
    用 SSE ticket 认证(DOC-06 v4 ADR-051),不走 JWT。
    支持 last_event_id 补发。
    限制每 session 最多 3 连接。
    """
    # 1. 消费 ticket
    user_id = await ticket_service.verify_and_consume(ticket, session_id)

    # 2. 占连接槽
    acquired = await sse_manager.acquire_conn_slot(session_id)
    if not acquired:
        raise HTTPException(429, "Too many concurrent SSE connections for this session(max 3)")

    async def event_gen():
        try:
            # 3. 补发历史(若提供 last_event_id)
            if last_event_id:
                for evt in await sse_manager.backfill_since(session_id, last_event_id):
                    yield _format_sse(evt)

            # 4. 实时订阅
            pubsub = sse_manager.subscribe(session_id)
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                payload = json.loads(message["data"])
                yield _format_sse(payload)
        finally:
            await sse_manager.release_conn_slot(session_id)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


def _format_sse(payload: dict) -> str:
    return f"id: {payload['id']}\nevent: {payload['event']}\ndata: {json.dumps(payload['data'])}\n\n"


@router.post("/sessions/{session_id}/permission-answer")
async def permission_answer(
    session_id: str,
    body: PermissionAnswerRequest,    # {request_id, decision: "allow" | "deny"}
    user: User = Depends(get_current_user),
    db = Depends(get_db),
    redis_client = Depends(get_redis),
):
    """
    v4 新增(ADR-064):用户回答 permission ask
    1. 校验 request_id 属于当前用户的 session
    2. UPDATE permission_requests SET status='answered', decision=X, answered_at=now()
    3. RPUSH perm_answer:{request_id} {decision} → 触发子进程 BLPOP 返回
    """
    req = db.query(PermissionRequest).filter_by(
        id=body.request_id,
        user_id=user.id,
    ).first()
    if not req or req.session_id != session_id:
        raise HTTPException(404, "Permission request not found")
    if req.status != "pending":
        raise HTTPException(409, f"Request already {req.status}")

    req.status = "answered"
    req.decision = body.decision
    req.answered_at = datetime.now(timezone.utc)
    db.commit()

    # 触发子进程 BLPOP 返回
    await redis_client.rpush(f"perm_answer:{body.request_id}", body.decision)

    logger.info("permission.answered",
                request_id=body.request_id,
                user_id=str(user.id),
                decision=body.decision)
    prism_permission_answered_total.labels(decision=body.decision).inc()

    return {"success": True}
```

### 1.2 app/services/heartbeat_monitor.py(v4 新文件)

```python
"""
HeartbeatMonitor - 扫描僵尸 Run(v4 ADR-065)
每 10s 扫 harness:heartbeat:* Redis key,超 30s 无更新 → 标记 crashed
"""

import asyncio
import time
import structlog

logger = structlog.get_logger()


class HeartbeatMonitor:
    def __init__(
        self,
        redis_client,
        lifecycle: "RunLifecycle",
        scan_interval: int = 10,
        stale_threshold: int = 30,
    ):
        self._redis = redis_client
        self._lifecycle = lifecycle
        self._scan_interval = scan_interval
        self._stale_threshold = stale_threshold
        self._running = False

    async def run(self):
        """后台 task,在 FastAPI lifespan 中 asyncio.create_task 启动"""
        self._running = True
        while self._running:
            try:
                await self._scan_once()
            except Exception as e:
                logger.error("heartbeat.scan_failed", error=str(e), exc_info=True)
            await asyncio.sleep(self._scan_interval)

    async def _scan_once(self):
        cursor = 0
        now = int(time.time())
        while True:
            cursor, keys = await self._redis.scan(
                cursor=cursor,
                match="harness:heartbeat:*",
                count=100,
            )
            for key in keys:
                last_heartbeat = await self._redis.get(key)
                if last_heartbeat is None:
                    continue
                age = now - int(last_heartbeat)
                if age > self._stale_threshold:
                    run_id = key.replace(b"harness:heartbeat:", b"").decode()
                    logger.warning("heartbeat.stale", run_id=run_id, age_seconds=age)

                    # 标记 Run crashed + promote 队列
                    self._lifecycle.mark_crashed(run_id, reason=f"heartbeat_stale_{age}s")
                    await self._redis.delete(key)

                    prism_agent_heartbeat_stale_total.inc()
                    prism_agent_subprocess_crashed_total.labels(reason="heartbeat").inc()

            if cursor == 0:
                break

    def stop(self):
        self._running = False
```

### 1.3 app/api/v1/internal.py 新增 `/internal/run-crashed` 端点(v4)

```python
@router.post("/internal/run-crashed", include_in_schema=False)
async def run_crashed(
    body: dict,                   # {run_id, reason}
    x_callback_secret: str = Header(...),
    db = Depends(get_db),
):
    """v4:HeartbeatMonitor 或 subprocess supervisor 调用,internal-only"""
    if x_callback_secret != settings.CALLBACK_SECRET:
        raise HTTPException(401)
    lifecycle = RunLifecycle(db, settings)
    new_run_id = lifecycle.mark_crashed(body["run_id"], body["reason"])
    return {"success": True, "new_run_id": new_run_id}
```

### 2. app/services/callback_service.py

```python
"""
回调处理 — sync DB path

⚠️ 审计关注点：所有 DB 操作使用同步 Session，与 ADR-001 一致。
不使用 async ORM，不使用 background task。
回调处理在请求线程中同步完成，确保数据一致性。

事件类型对应的处理逻辑：
- text_delta → 追加到当前 assistant Message（或创建新 Message）
- tool_start → 创建 ToolExecution 记录 + 创建 tool_use Message
- tool_end → 更新 ToolExecution + 创建 tool_result Message
- harness_event → 写 audit_log
- run_complete → RunLifecycle.complete_and_promote()
- run_error → RunLifecycle.fail_and_promote()
- session_title → 更新 Session.title
"""

class CallbackService:
    def __init__(self, db: Session, sse: SSEManager, settings):
        self._db = db
        self._sse = sse
        self._settings = settings
    
    def handle(self, event: dict) -> dict:
        """
        处理单个回调事件。
        
        所有 DB 操作在调用方的事务中完成（不在此方法内 commit）。
        返回: {"status": "ok"} 或 {"status": "error", "message": ...}
        """
        run_id = event["run_id"]
        event_type = event["event_type"]
        data = event["data"]
        
        run = self._db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return {"status": "error", "message": "Run not found"}
        
        handler = getattr(self, f"_handle_{event_type}", None)
        if handler is None:
            return {"status": "error", "message": f"Unknown event type: {event_type}"}
        
        handler(run, data)
        return {"status": "ok"}
    
    def _handle_text_delta(self, run: Run, data: dict) -> None:
        """
        追加文本增量。
        
        策略：查找当前 Run 的最后一条 assistant Message。
        如果存在且是当前 turn 的 → 追加到 content[0].text
        如果不存在 → 创建新 Message
        """
        ...
        self._sse.publish(run.session_id, "text_delta", data)
    
    def _handle_tool_start(self, run: Run, data: dict) -> None:
        """创建 ToolExecution 记录 + tool_use Message"""
        ...
        self._sse.publish(run.session_id, "tool_start", data)
    
    def _handle_tool_end(self, run: Run, data: dict) -> None:
        """更新 ToolExecution（output, duration_ms, is_error, permission_decision, hook_modified）+ tool_result Message"""
        ...
        self._sse.publish(run.session_id, "tool_end", data)
    
    def _handle_harness_event(self, run: Run, data: dict) -> None:
        """写 audit_log + SSE 推送"""
        from app.models.audit import AuditLog
        log = AuditLog(
            user_id=run.user_id,
            action=f"harness.{data.get('type', 'unknown')}",
            resource_type="run",
            resource_id=run.id,
            details=data,
        )
        self._db.add(log)
        self._sse.publish(run.session_id, "harness_event", data)
    
    def _handle_run_complete(self, run: Run, data: dict) -> None:
        """
        Run 完成处理。

        调用 RunLifecycle.complete_and_promote()，
        如果 promote 了新 Run，返回新 Run ID 供调用方启动子进程。

        > **Sync/Async 统一 (P1)**：`handle_callback` 端点统一为 `async def` + `await`。FastAPI 天然支持 async def，无需同步回退。所有 callback handler 使用 async。
        """
        lifecycle = RunLifecycle(self._db, self._settings)
        new_run_id = lifecycle.complete_and_promote(
            run_id=run.id,
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            cost_usd=data.get("cost_usd", 0),
            turn_count=data.get("turn_count", 0),
            harness_summary=data.get("harness_summary", {}),
        )
        
        self._sse.publish(run.session_id, "run_complete", data)
        
        if new_run_id:
            self._sse.publish(run.session_id, "queue_update", {
                "promoted_run_id": new_run_id,
            })
            # 新 Run 的子进程启动由调用方（internal.py）负责
            self._db.info_for_caller = {"new_run_id": new_run_id}  # 通过约定字段传递
    
    def _handle_run_error(self, run: Run, data: dict) -> None:
        """Run 失败处理。"""
        lifecycle = RunLifecycle(self._db, self._settings)
        lifecycle.fail_and_promote(run.id, data.get("error", "Unknown error"))
        self._sse.publish(run.session_id, "run_error", data)
    
    def _handle_session_title(self, run: Run, data: dict) -> None:
        """更新 Session 标题"""
        session = run.session
        session.title = data.get("title", "")[:200]
        self._sse.publish(run.session_id, "session_title", data)
```

### 3. app/api/v1/internal.py

```python
"""
内部回调端点 — CLI 子进程 → Backend

POST /internal/callbacks
认证: X-Callback-Secret header（不经过 JWT）

GET /health
公开健康检查
"""

@router.post("/internal/callbacks")
def handle_callback(request: Request, db: Session = Depends(get_db)):
    """
    处理 Agent 执行回调。
    
    认证：X-Callback-Secret header 必须匹配 CALLBACK_SECRET。
    处理：同步 DB path，在请求线程中完成所有操作。
    """
    # 认证
    secret = request.headers.get("X-Callback-Secret")
    if secret != settings.CALLBACK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid callback secret")
    
    event = await request.json()
    
    sse = SSEManager(settings.REDIS_URL)
    service = CallbackService(db, sse, settings)
    result = service.handle(event)
    
    db.commit()  # 所有 DB 操作在此统一提交
    
    # 如果 promote 了新 Run，启动子进程
    new_run_id = getattr(db, 'info_for_caller', {}).get('new_run_id')
    if new_run_id:
        _start_agent_subprocess(new_run_id)
    
    return result
```

### 4. SSE 订阅端点

在 `app/api/v1/sessions.py` 中新增：

```python
from fastapi.responses import StreamingResponse

@router.get("/{session_id}/stream")
def stream_events(
    session_id: str,
    token: str,                  # JWT 通过 query param
    db: Session = Depends(get_db),
):
    """
    SSE 事件流。
    
    JWT 通过 query param 传递（EventSource 不支持 custom header）。
    """
    # 验证 token
    payload = decode_token(token, settings.JWT_SECRET)
    user_id = payload.get("sub")
    
    # 验证 session 属于用户
    session = SessionService(db).get_session(user_id, session_id)
    
    # 订阅 Redis channel
    sse = SSEManager(settings.REDIS_URL)
    
    def event_generator():
        pubsub = sse.subscribe(session_id)
        import time, json
        last_heartbeat = time.time()
        
        for message in pubsub.listen():
            if message["type"] == "message":
                event_data = json.loads(message["data"])
                yield f"event: {event_data['event']}\ndata: {json.dumps(event_data['data'])}\n\n"
            
            # 心跳（每 15 秒）
            if time.time() - last_heartbeat > 15:
                yield f"event: heartbeat\ndata: {{}}\n\n"
                last_heartbeat = time.time()
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/services/callback_service.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/services/sse_manager.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/api/v1/internal.py

# 2. 回调端点测试
# 模拟回调（需要 CALLBACK_SECRET）
curl -s -X POST http://localhost:8000/api/v1/internal/callbacks \
  -H "X-Callback-Secret: $CALLBACK_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"run_id":"...", "event_type":"text_delta", "data":{"text":"hello"}, "timestamp":"..."}'

# 3. SSE 订阅测试
curl -N "http://localhost:8000/api/v1/sessions/$SID/stream?token=$TOKEN"
# 在另一个终端发送回调，观察 SSE 输出
```

## 完成后

1. 更新 PROGRESS.md
2. 加载 Simplify skill 审查
3. 加载 PJR skill 验证
4. `git add -A && git commit -m "feat: callback service (sync DB path) + SSE manager + event streaming"`
```

---

## Task 7.4: CLI 子进程调度(v4:启动参数标准化 + coordinator_recovery + alert_dispatcher)

### Part A — 设计与解释

#### 问题陈述

Backend 需要启动和管理 CLI 子进程(`python -m executor ...`)。需要实现并发控制(最多 MAX_CONCURRENT_RUNS 个同时运行)、超时管理(RUN_TIMEOUT_SECONDS)和进程清理。

**v4 新增能力**:
1. subprocess 启动参数标准化 — 必传 `--run-id / --session-id / --user-id / --callback-url / --callback-secret / --redis-url`;可选 `--resume-from-step / --otel-trace-id`
2. coordinator_recovery 服务 — `POST /runs/{id}/resume` 从 `coordinator_plans` 表读 checkpoint,重启子进程传 `--resume-from-step=N`
3. alert_dispatcher — 告警分发(audit_logs / SSE / IM / email 按 severity 分档)

#### 设计决策(ADR)

- **ADR-066(subprocess 启动参数标准化)**:所有子进程启动命令按 DOC-01 v4 §9.1 统一格式:
  ```
  python -m executor \
    --run-id={run_id} \
    --session-id={session_id} \
    --user-id={user_id} \
    --callback-url=http://backend:8000/api/v1/internal/callbacks \
    --callback-secret=${CALLBACK_SECRET} \
    --redis-url=${REDIS_URL} \
    [--resume-from-step=N] \
    [--otel-trace-id=traceparent-value]
  ```
  环境变量额外传递:`ENCRYPTION_KEY / PRISM_RUN_ID / PRISM_SESSION_ID / PRISM_USER_ID / OTEL_EXPORTER_OTLP_ENDPOINT`

  来源:DOC-01 v4 §9.1, Batch 3 §A7-6。

- **ADR-067(coordinator_recovery 服务)**:`POST /runs/{id}/resume` 端点:
  1. 校验当前 run 是 `failed` + `error_message` 含 `heartbeat_stale`(只恢复崩溃的 run)
  2. 查 `coordinator_plans` 表:`SELECT plan_json, current_step_index FROM coordinator_plans WHERE run_id=X`
  3. 新建 Run(复用 session_id / prompt / provider / model)
  4. 启动子进程,传 `--resume-from-step=current_step_index`
  5. 子进程 `executor/__main__.py` 收到后走 Coordinator.resume_from_checkpoint(DOC-04 v4 Task 4.3)

  来源:Master M3, Batch 2 §A4-3。

#### 验收标准(v4 扩展)

- 子进程通过 `subprocess.Popen` 启动
- 同时运行的子进程数不超过 MAX_CONCURRENT_RUNS
- 超过限制时新任务进入全局等待队列
- 子进程超时后被 kill,Run 标记为 timeout
- 子进程异常退出时 Run 标记为 failed
- 子进程启动后立即回调 mark_running
- **v4:启动参数按 ADR-066 标准化**(必传 8 个 args + 可选 2 个)
- **v4:`POST /runs/{id}/resume` 端点从 coordinator_plans 表读 checkpoint 重启子进程**
- **v4:alert_dispatcher 服务**:severity `critical` 走 IM 群 + email;`error` 走 SSE + audit;`warning` 走 audit;`info` 仅 structlog

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的 CLI 子进程调度器。Task 7.1-7.3 已完成会话/Run/回调/SSE 链路。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

Task 7.1-7.3 已完成

## 要创建的文件

```
backend/app/
├── services/
│   ├── process_manager.py         # CLI 子进程调度(v4 标准化启动参数)
│   ├── coordinator_recovery.py    # v4 新文件
│   └── alert_dispatcher.py        # v4 新文件
└── api/v1/
    └── runs.py                    # v4 新增 POST /runs/{id}/resume
```

### v4 subprocess 启动代码骨架

```python
def _build_command(self, run: Run, resume_from_step: int | None = None) -> list[str]:
    """v4 ADR-066 标准化启动参数"""
    cmd = [
        "python", "-m", "executor",
        f"--run-id={run.id}",
        f"--session-id={run.session_id}",
        f"--user-id={run.user_id}",
        f"--callback-url=http://backend:8000/api/v1/internal/callbacks",
        f"--callback-secret={self._settings.CALLBACK_SECRET}",
        f"--redis-url={self._settings.REDIS_URL}",
    ]
    if resume_from_step is not None:
        cmd.append(f"--resume-from-step={resume_from_step}")
    trace_id = getattr(run, "otel_trace_id", None)
    if trace_id:
        cmd.append(f"--otel-trace-id={trace_id}")
    return cmd


def _build_env(self) -> dict[str, str]:
    """v4:传递必要环境变量(不放到 argv,避免日志泄露 secret)"""
    return {
        **os.environ,
        "ENCRYPTION_KEY": self._settings.ENCRYPTION_KEY,
        "OTEL_EXPORTER_OTLP_ENDPOINT": self._settings.OTEL_EXPORTER_OTLP_ENDPOINT or "",
    }
```

### v4 coordinator_recovery.py(新文件)

```python
"""
Coordinator Recovery - 从 coordinator_plans checkpoint 恢复崩溃的 Run(v4 ADR-067)
"""

class CoordinatorRecoveryService:
    def __init__(self, db, process_manager, settings):
        self._db = db
        self._pm = process_manager
        self._settings = settings

    async def resume(self, run_id: str, user_id: str) -> str:
        run = self._db.query(Run).filter_by(id=run_id, user_id=user_id).first()
        if not run:
            raise HTTPException(404, "Run not found")
        if run.status != "failed" or "heartbeat_stale" not in (run.error_message or ""):
            raise HTTPException(409, "Only crashed runs can be resumed")

        plan = self._db.query(CoordinatorPlan).filter_by(run_id=run_id).first()
        if not plan:
            raise HTTPException(404, "No coordinator checkpoint")

        # 创建新 Run(继承原 Run 的 session/provider/model)
        new_run = Run(
            session_id=run.session_id,
            user_id=run.user_id,
            prompt=run.prompt,
            status="pending",
            model=run.model,
            provider_id=run.provider_id,
            schedule_mode="resumed",
        )
        self._db.add(new_run)
        self._db.flush()

        # 在 coordinator_plans 上更新 run_id 指向新 run
        plan.run_id = new_run.id
        self._db.commit()

        # 启动子进程,传 resume-from-step
        self._pm.start_run(new_run.id, resume_from_step=plan.current_step_index)
        return new_run.id
```

### v4 alert_dispatcher.py(新文件)

```python
"""
Alert Dispatcher - 告警分发(v4)
按 severity 路由到不同渠道:audit_logs / SSE / IM / email
"""

class AlertDispatcher:
    def __init__(self, db, sse_manager, im_service, email_service, settings):
        self._db = db
        self._sse = sse_manager
        self._im = im_service
        self._email = email_service
        self._settings = settings

    async def dispatch(self, severity: str, event_type: str, detail: dict, user_id: str | None = None):
        # 总是写 audit_logs
        self._db.add(AuditLog(
            user_id=user_id,
            action=event_type,
            details=detail,
            severity=severity,
        ))

        if severity in ("error", "critical"):
            # SSE 推到用户前端
            if user_id:
                await self._sse.publish_to_user(user_id, "alert", detail)

        if severity == "critical":
            # IM 群告警
            if self._settings.ALERT_IM_CHANNEL:
                await self._im.send(self._settings.ALERT_IM_CHANNEL, f"[CRITICAL] {event_type}: {detail}")
            # Email
            if self._settings.ALERT_EMAIL:
                await self._email.send(
                    self._settings.ALERT_EMAIL,
                    subject=f"[Prism CRITICAL] {event_type}",
                    body=str(detail),
                )
```

## 实现规范

### 1. app/services/process_manager.py

```python
"""
CLI 子进程调度器

职责：
- 启动 Agent 子进程
- 并发控制（信号量）
- 超时管理（watchdog 线程）
- 进程清理

⚠️ 重要设计约束：
- 子进程在 Backend 容器内运行（不是独立容器）
- 启动命令: python -m prism.executor --run-id=... --callback-url=... --callback-secret=...
- 子进程以降权用户运行（生产环境）
- 工作目录: /workspace/{run_id}/
"""

import subprocess
import threading
import os
from concurrent.futures import ThreadPoolExecutor

class ProcessManager:
    """
    进程管理器 — 单例，在 app lifespan 中初始化。
    """
    
    def __init__(self, settings):
        self._settings = settings
        self._semaphore = threading.Semaphore(settings.MAX_CONCURRENT_RUNS)
        self._processes: dict[str, subprocess.Popen] = {}  # run_id → Popen
        self._executor = ThreadPoolExecutor(max_workers=settings.MAX_CONCURRENT_RUNS + 2)
        self._lock = threading.Lock()
    
    def start_run(self, run_id: str) -> None:
        """
        启动 Agent 子进程。
        
        如果当前并发已满，阻塞等待（信号量）。
        子进程在后台线程中管理（等待完成 + 超时检测）。
        """
        self._executor.submit(self._run_in_thread, run_id)
    
    def _run_in_thread(self, run_id: str) -> None:
        """在后台线程中管理子进程生命周期"""
        self._semaphore.acquire()
        try:
            # 创建工作目录
            workspace = f"/workspace/{run_id}"
            os.makedirs(workspace, exist_ok=True)
            
            # 启动子进程
            cmd = [
                "python", "-m", "prism.executor",
                f"--run-id={run_id}",
                f"--callback-url=http://localhost:8000/api/v1/internal/callbacks",
                f"--callback-secret={self._settings.CALLBACK_SECRET}",
            ]
            
            proc = subprocess.Popen(
                cmd,
                cwd=workspace,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            with self._lock:
                self._processes[run_id] = proc
            
            # 等待完成或超时
            try:
                proc.wait(timeout=self._settings.RUN_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                # 通过回调通知 Backend 超时
                self._notify_timeout(run_id)
            
            # 检查非正常退出
            if proc.returncode not in (0, None):
                stderr = proc.stderr.read().decode()[:500] if proc.stderr else ""
                self._notify_failure(run_id, f"Process exited with code {proc.returncode}: {stderr}")
            
        finally:
            with self._lock:
                self._processes.pop(run_id, None)
            self._semaphore.release()
    
    def kill_run(self, run_id: str) -> bool:
        """kill 指定 run 的子进程。返回是否成功。"""
        with self._lock:
            proc = self._processes.get(run_id)
        if proc:
            proc.kill()
            return True
        return False
    
    def _notify_timeout(self, run_id: str) -> None:
        """通过 HTTP 回调通知 Backend 超时"""
        import httpx
        try:
            httpx.post(
                f"http://localhost:8000/api/v1/internal/callbacks",
                json={
                    "run_id": run_id,
                    "event_type": "run_error",
                    "data": {"run_id": run_id, "error": f"Timeout after {self._settings.RUN_TIMEOUT_SECONDS}s"},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                headers={"X-Callback-Secret": self._settings.CALLBACK_SECRET},
                timeout=5.0,
            )
        except Exception:
            pass
    
    def _notify_failure(self, run_id: str, error: str) -> None:
        """通知非正常退出"""
        ...  # 同 _notify_timeout，event_type="run_error"
    
    def shutdown(self) -> None:
        """关闭所有子进程和线程池"""
        with self._lock:
            for proc in self._processes.values():
                proc.kill()
        self._executor.shutdown(wait=True)
```

### 2. 集成到 app/main.py

```python
# lifespan 中初始化 ProcessManager
process_manager = ProcessManager(settings)

# 注册到 app.state 供路由使用
app.state.process_manager = process_manager

# shutdown 时清理
# process_manager.shutdown()
```

### 3. 全局 `_start_agent_subprocess` 函数

```python
# 在 tasks.py 和 internal.py 中使用
def _start_agent_subprocess(run_id: str):
    """启动 Agent 子进程。从 app.state 获取 ProcessManager。"""
    from fastapi import Request
    # 通过 FastAPI app.state 获取 ProcessManager
    process_manager = app.state.process_manager
    process_manager.start_run(run_id)
```

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/services/process_manager.py

# 2. 进程启动测试（需要完整的 executor 实现）
# 创建一个 Run 记录，调用 process_manager.start_run()
# 观察子进程启动、回调事件、SSE 推送

# 3. 并发控制测试
# 同时提交 3 个 task（MAX_CONCURRENT_RUNS=2）
# 验证第 3 个等待前 2 个完成后才启动

# 4. 超时测试
# 设置 RUN_TIMEOUT_SECONDS=5，提交一个需要超过 5 秒的任务
# 验证子进程被 kill，Run 标记 timeout
```

## 完成后

1. 更新 PROGRESS.md
2. 更新 DECISIONS.md：记录 ADR-029（子进程调度——信号量并发控制 + 后台线程管理 + 超时 kill）
3. 加载 Simplify skill 审查
4. 加载 PJR skill 验证
5. `git add -A && git commit -m "feat: CLI subprocess scheduler with concurrency control and timeout"`
```

---

> **文档维护说明(v4)**:本文档的 4 个 Task 完成后,Prism v2 将拥有完整的会话管理和任务执行链路:Session CRUD(含 text_preview 生成规则)+ 消息增量查询 + **sequence_no 并发原子性(per-session 序列 或 advisory_xact_lock)** + Task 提交(即时/排队)+ Run 生命周期状态机 + 原子性 promote(FOR UPDATE SKIP LOCKED)+ **Run cancel 三模式(graceful/force/also_cancel_queue)** + **方案 A 双通道回调**(Redis 直通 text_delta/tool_use_delta + HTTP 关键事件带重试)+ **`POST /sessions/{id}/permission-answer` 端点** + **HeartbeatMonitor 后台 task(扫僵尸 Run 标记 crashed)** + SSE 推送(**last_event_id 补发 + 每 session ≤ 3 连接 + SSE ticket 消费**)+ CLI 子进程调度(**启动参数标准化 8 args** + 信号量并发控制 + 超时管理)+ **coordinator_recovery 服务(从 coordinator_plans checkpoint 重启子进程)** + **alert_dispatcher**(severity 分档分发)。harness_summary JSONB schema 已定义并在 run_complete 回调时写入。
> **最后更新**: 2026-04-18 (v4 review 修订版) | **下一步**: DOC-08 v4 Backend IM Gateway

---

## 附录 A: v4 修订清单

本次修订共 25 处精确修补,对应 Batch 1-5 review + PDF 补丁 + Master:

| # | 位置 | 修订内容 | 来源 |
|---|---|---|---|
| 1 | Header | 版本 3.1 → 4.0,日期 2026-04-18,前置依赖 v4 + 5 张新表,v4 摘要段,审计关注点升级为 sequence_no/双通道/三模式 cancel/HeartbeatMonitor | 全局 |
| 2 | Task 7.1 Part A | 无大改,text_preview 生成规则同步 DOC-01 v4 §4.2 | Batch 3 §A7-1 |
| 3 | Task 7.1 session_service | `generate_text_preview(role, content, tool_lookup)` 按规则生成 | 同上 |
| 4 | Task 7.2 Part A | 新增 ADR-060(sequence_no 并发原子性)/ADR-061(promote 原子事务)/ADR-062(Run cancel 三模式) | Batch 3 §A7-2, §B3-4 |
| 5 | Task 7.2 sequence_no 原子性实现 | `get_next_message_sequence_no`(方案 1:per-session 序列)+ `get_next_sequence_no_advisory`(方案 2:advisory_xact_lock + max+1)完整 SQL 代码 | 同上 |
| 6 | Task 7.2 Run cancel | `cancel(run_id, mode)` 三模式实现;graceful → SIGTERM,force → SIGKILL,also_cancel_queue → 同时取消后续 queue | Batch 3 §A7-2 |
| 7 | Task 7.2 RunLifecycle.mark_crashed | 新方法,HeartbeatMonitor 调用 + promote 队列 | 同上 |
| 8 | Task 7.3 Part A | 新增 ADR-063(回调协议方案 A)/ADR-064(permission-answer 端点)/ADR-065(HeartbeatMonitor 崩溃恢复)+ 双通道数据流图 | Batch 1 §3.3 D3, Batch 2 §A3-7, Batch 3 B3-1/B3-2 |
| 9 | Task 7.3 callback_service.py | 重写接收逻辑:Redis 订阅 text_delta/tool_use_delta + HTTP 接收关键事件 + 按事件类型路由持久化 | Master M2 |
| 10 | Task 7.3 `POST /sessions/{id}/permission-answer`(新) | Body: `{request_id, decision}`;UPDATE permission_requests + RPUSH `perm_answer:{request_id}` | Batch 2 §A3-7 |
| 11 | Task 7.3 heartbeat_monitor.py(新文件) | 后台 task,每 10s SCAN `harness:heartbeat:*`,超 30s 标记 crashed + promote + Prometheus counter | Batch 3 B3-2 |
| 12 | Task 7.3 `POST /internal/run-crashed` 端点(新) | HeartbeatMonitor 或 subprocess supervisor 触发,internal-only,校验 CALLBACK_SECRET | 同上 |
| 13 | Task 7.3 sse_manager.py | 订阅 Redis channel + 支持 `last_event_id` 补发(从 Redis Stream)+ tab 限制(每 session 最多 3 连接)+ 事件 id UUID7 | Batch 1 v2 §R4, Batch 3 §B3-III |
| 14 | Task 7.3 `GET /sessions/{id}/stream?ticket=X&last_event_id=Y` | 改用 SSE ticket 认证(DOC-06 v4 ADR-051)+ 支持 last_event_id 补发 | Batch 1 v2 §R4 |
| 15 | Task 7.4 Part A | 新增 ADR-066(subprocess 启动参数标准化)/ADR-067(coordinator_recovery 服务) | Master M3, Batch 3 §A7-6 |
| 16 | Task 7.4 subprocess 启动 | 必传 `--run-id / --session-id / --user-id / --callback-url / --callback-secret / --redis-url`;可选 `--resume-from-step / --otel-trace-id`;env 传 `ENCRYPTION_KEY / OTEL_EXPORTER_OTLP_ENDPOINT` | DOC-01 v4 §9.1 |
| 17 | Task 7.4 coordinator_recovery.py(新文件) | `POST /runs/{id}/resume`:读 coordinator_plans 表 checkpoint → 新建 Run → 重启子进程传 `--resume-from-step=N` | Batch 2 §A4-3, Master M3 |
| 18 | Task 7.4 alert_dispatcher.py(新文件) | 告警分发:audit_logs / SSE / IM / email 按 severity 分档 | Batch 5 §B5-IV |
| 19 | IM Webhook 幂等(属 DOC-08,此处引用) | session_service 创建 Run 前查 im_message_dedup 表 | Batch 3 B3-5 |
| 20 | 结构化日志 | run.started/completed/failed/crashed + callback.received/failed/dead_letter + permission.answered + heartbeat.stale | 全局 §3.4 |
| 21 | Prometheus metrics | `prism_runs_total` / `prism_run_duration_seconds` / `prism_agent_heartbeat_stale_total` / `prism_agent_subprocess_crashed_total` / `prism_permission_answered_total`(by decision) | Batch 5 §B5-I |
| 22 | 所有 Part B 开头 | 加 v4 Observability 采集要求说明 | 全局 §3.4 |
| 23 | Redis namespace | `perm_answer/perm_req/harness:heartbeat/sse:*/sse:*:stream/sse:conns:*` 按 DOC-01 v4 §9.2 规范 | Batch 3 §B3-I |
| 24 | ADR 编号 ADR-060~069 + 交叉引用 v3 → v4 | 全局 | 全局 |
| 25 | 附录 A + 文末 | 修订清单 + 下一步 DOC-08 v4 | SOP |  
> **最后更新**: 2026-04-02 | **下一步**: DOC-08 Backend IM Gateway
