# Prism 棱镜 v2 — Backend Session / Run / Task (DOC-07)

> **文档编号**: DOC-07  
> **版本**: 3.1  
> **日期**: 2026-04-02  
> **性质**: 实现文档 — 会话管理、Run 生命周期、任务提交/排队/推进、SSE 推送、CLI 子进程调度的完整后端链路  
> **前置依赖**: DOC-01 v3（Schema: sessions + session_queue_items + runs + messages + tool_executions）, DOC-02 v3 Task 2.1, DOC-03 v3（Harness Runtime）, DOC-06（认证体系）  
> **Phase**: 2（后端功能模块）  
> **Task 数**: 4  
> **审计关注点**:  
> - **promote 原子性保障**：当前 Run 完成后自动推进队列中下一条消息时，必须在同一个 DB 事务中完成「旧 Run 标记完成 + 队列 item 标记 promoted + 新 Run 创建 + session.blocking_run_id 更新」，避免并发场景下的重复 promote 或丢失 promote（ADR-027）
> - **Backend callback 为 sync DB 处理路径**：CLI 子进程的回调是 HTTP POST 到 Backend，Backend 收到后的处理（消息持久化 + Run 状态更新 + SSE 推送 + 队列推进）全部在同步 DB session 中完成，不使用 async ORM，与 DOC-02 ADR-001 一致
> - **harness_summary JSONB schema 定义**：`runs.harness_summary` 字段需要明确的 schema 约定（字段名、类型、含义），否则 DOC-12 的 Observability 和前端的 Harness 展示无法稳定消费（ADR-028）

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

#### 验收标准

- 会话 CRUD 正常工作（创建/列表/详情/更新/删除）
- 删除会话时级联删除所有 Run 和 Message
- 消息列表支持 `after_sequence_no` 增量查询（SSE 断线重连后拉取新消息）
- 会话列表按 `updated_at DESC` 排序，置顶会话优先
- 所有查询强制 `WHERE user_id = :current_user_id`（铁律 4）

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

#### 验收标准

- `POST /tasks` 在 session idle 时立即创建 Run 并启动子进程
- `POST /tasks` 在 session busy 时创建 queue_item 并返回 `accepted_type: "queued_query"`
- Run 完成后自动 promote 队列中下一条
- promote 操作在单个 DB 事务中原子完成
- 并发 promote 不会重复创建 Run
- 取消正在执行的 Run（kill 子进程 + 标记 cancelled）
- 取消排队消息（标记 cancelled）
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
        入队。
        
        sequence_no = 该 session 当前最大 sequence_no + 1
        检查队列大小不超过 QUEUE_MAX_SIZE
        """
        ...
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
    
    def cancel(self, run_id: str) -> None:
        """
        取消 Run。
        
        如果 status == "pending" → 直接标记 cancelled
        如果 status == "running" → kill 子进程 + 标记 cancelled + promote
        """
        ...
    
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

## Task 7.3: Callback Service 与 SSE Manager

### Part A — 设计与解释

#### 问题陈述

CLI 子进程通过 HTTP POST 向 Backend 发送回调事件。Backend 收到后需要：(1) 持久化消息到 DB；(2) 更新 Run 状态；(3) 通过 Redis pub/sub 推送 SSE 事件给前端；(4) Run 完成时触发 promote。这整条链路必须是同步 DB 处理（ADR-001），不使用 async ORM。

#### 回调 → DB → SSE 数据流

```
CLI 子进程
    │ POST /api/v1/internal/callbacks
    ▼
Backend CallbackService.handle(event)       ← sync DB Session
    ├─ text_delta → 创建/追加 Message → SSE 推送
    ├─ tool_start → 创建 ToolExecution 记录 → SSE 推送
    ├─ tool_end → 更新 ToolExecution → SSE 推送
    ├─ harness_event → 写 audit_log → SSE 推送
    ├─ run_complete → RunLifecycle.complete_and_promote() → SSE 推送
    │   └─ 如果 promote 了新 Run → 启动新子进程
    └─ run_error → RunLifecycle.fail_and_promote() → SSE 推送
```

#### 验收标准

- Callback 端点正确处理所有事件类型
- 消息持久化到 messages 表，sequence_no 自增
- SSE 推送到对应 session 的 channel
- harness_event 写入 audit_logs
- run_complete 触发 promote（原子性，复用 Task 7.2 的 RunLifecycle）
- 回调认证通过 X-Callback-Secret header

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
│   ├── callback_service.py    # 回调处理（sync DB path）
│   └── sse_manager.py         # SSE 推送（Redis pub/sub）
└── api/v1/
    └── internal.py            # 内部回调端点
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
    def __init__(self, redis_url: str):
        self._redis = redis.Redis.from_url(redis_url)
    
    def publish(self, session_id: str, event_name: str, data: dict) -> None:
        """
        发布 SSE 事件到 Redis channel。
        
        格式: {"event": event_name, "data": data}
        """
        self._redis.publish(
            f"sse:{session_id}",
            json.dumps({"event": event_name, "data": data}),
        )
    
    def subscribe(self, session_id: str):
        """
        订阅 Redis channel，返回 pubsub 对象。
        供 SSE 端点使用。
        """
        pubsub = self._redis.pubsub()
        pubsub.subscribe(f"sse:{session_id}")
        return pubsub
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

## Task 7.4: CLI 子进程调度

### Part A — 设计与解释

#### 问题陈述

Backend 需要启动和管理 CLI 子进程（`python -m prism.executor --run-id=...`）。需要实现并发控制（最多 MAX_CONCURRENT_RUNS 个同时运行）、超时管理（RUN_TIMEOUT_SECONDS）和进程清理。

#### 验收标准

- 子进程通过 `subprocess.Popen` 启动
- 同时运行的子进程数不超过 MAX_CONCURRENT_RUNS
- 超过限制时新任务进入全局等待队列
- 子进程超时后被 kill，Run 标记为 timeout
- 子进程异常退出时 Run 标记为 failed
- 子进程启动后立即回调 mark_running

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
└── services/
    └── process_manager.py     # CLI 子进程调度
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

> **文档维护说明**：本文档的 4 个 Task 完成后，Prism v2 将拥有完整的会话管理和任务执行链路：Session CRUD + 消息增量查询 + Task 提交（即时/排队）+ Run 生命周期状态机 + 原子性 promote（FOR UPDATE SKIP LOCKED）+ Callback 同步 DB 处理 + SSE 推送（Redis pub/sub）+ CLI 子进程调度（信号量并发控制 + 超时管理）。harness_summary JSONB schema 已定义并在 run_complete 回调时写入。  
> **最后更新**: 2026-04-02 | **下一步**: DOC-08 Backend IM Gateway
