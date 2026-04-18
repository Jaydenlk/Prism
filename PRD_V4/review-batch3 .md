# Prism v2 架构 Review — Batch 3: Backend 层

> **范围**: DOC-06 (Auth) / DOC-07 (Session-Run-Task) / DOC-08 (IM Gateway) / DOC-09 (MCP-Provider-Admin)
> **新增 Task 评估**: Task 9.3 (Admin 审计日志与系统管理) + Batch 2 需要 Backend 落地的协议级空洞
> **立场**: 质量优先、不砍功能、CC + Manus 双参照、4C8G 基线
> **评审者**: Claude Opus 4.7

---

## 0. 整体判断

Backend 四份文档的质量**整体好于** Agent 核心三份(DOC-03/04/05),原因是后端工作更"工程化",4.6 审计阶段对 CRUD/API/DB 这类问题更敏锐。但 Backend 层有 Batch 2 遗留的**协议级空洞必须在这里填补**,以及若干**跨进程、跨平台**的边缘 case 需要补齐。

按重要性排序,Batch 3 最严重的 5 个问题:

| # | 问题 | 影响 |
|---|---|---|
| **B3-1** | **permission="ask" 反向通信端点缺失** | Batch 2 B2-1 的后端落地。没有这个,Harness 的"人工确认"完全瘫痪 |
| **B3-2** | **子进程崩溃恢复机制缺失** | Batch 2 B-2 的后端落地。没有心跳监控 + 恢复策略,生产会出僵尸 Run |
| **B3-3** | **Callback Service 回调协议改造**(Batch 1 D3 方案 A) | 后端要从"全 HTTP 回调 + Backend 转发 SSE" 改为 "流式事件 Redis 直通 + 关键事件 HTTP" |
| **B3-4** | **DOC-07 Task 7.2 `message.sequence_no` 并发冲突未处理** | 多个回调并发 insert message,`sequence_no` 靠 `max+1` 会冲突,生产数据错乱 |
| **B3-5** | **DOC-08 IM Webhook 幂等性缺失** | 飞书/企微平台会重试,同一条消息可能收到 2-3 次,没幂等会创建多个 Run |

下面按 Part A / B / C 展开。

---

## Part A — 实现级审视

### DOC-06: Auth & User

#### A6-1. Task 6.1 JWT `access` vs `refresh` 类型校验有但不完整

代码里:
```python
if payload.get("type") != "access":
    raise HTTPException(status_code=401, detail="Invalid token type")
```

但问题:
- `/auth/refresh` 端点必须拒绝 `type="access"` 的 token(只接受 refresh)
- 文档只说 access token 的校验,refresh 那边如何校验没写
- JWT `jti`(JWT ID)字段缺失,无法做黑名单(虽然 Phase 1 说不做黑名单,但 jti 是 0 成本的未来扩展点)
- `exp` 之外没有 `nbf`(not before),极端时钟漂移场景可能出问题

**质量优先修法**:
```python
# app/core/security.py

def create_access_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({
        "sub": user_id,
        "type": "access",
        "jti": str(uuid7.create()),  # ← 新增,为将来 blacklist 预留
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
    }, settings.JWT_SECRET, algorithm="HS256")

def decode_token(token: str, secret: str, expected_type: Literal["access", "refresh"]) -> dict:
    """
    强制校验 token 类型。
    expected_type 不是可选参数,必须指定,避免遗忘。
    """
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError()
    except jwt.InvalidTokenError:
        raise TokenInvalidError()
    
    if payload.get("type") != expected_type:
        raise TokenTypeError(f"Expected {expected_type}, got {payload.get('type')}")
    
    return payload
```

所有调用点改为:`decode_token(token, secret, expected_type="access")` 或 `"refresh"`,不再靠业务代码校验 type。

#### A6-2. Task 6.1 登录速率限制缺失

注册 / 登录端点当前没有速率限制。质量优先下**必须加**,否则密码爆破很容易。

**修法**: Redis 简单速率限制中间件(Batch 1 §3.1 数据模型没有 rate_limit 表,但 Redis 即可):
```python
# app/core/rate_limit.py

class RateLimiter:
    async def check(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """
        滑动窗口速率限制。
        key 格式建议: "rl:login:{ip}" / "rl:register:{ip}"
        返回 True 表示允许,False 表示拒绝。
        """
        current = await redis.incr(key)
        if current == 1:
            await redis.expire(key, window_seconds)
        return current <= max_requests

# 端点上:
@router.post("/auth/login")
async def login(request: Request, ...):
    if not await rate_limiter.check(f"rl:login:{request.client.host}", max_requests=5, window_seconds=60):
        raise HTTPException(429, "Too many login attempts")
```

限制:
- `/auth/login`: 5 次 / 分钟 / IP
- `/auth/register`: 3 次 / 小时 / IP
- `/auth/refresh`: 30 次 / 分钟 / IP(合法场景可能频繁刷新)

#### A6-3. Task 6.1 Admin 自动创建时机有竞态

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    with SessionLocal() as db:
        AuthService(db, settings).ensure_admin()
        db.commit()
    yield
```

问题: Docker Compose 启动时 Backend 和 Postgres 的 health check 有时序。Backend 先启动,尝试连 DB 可能失败。`lifespan` 里如果 DB 不可用会 crash 整个 Backend。

**修法**: `ensure_admin` 加重试 + backoff:
```python
async def ensure_admin_with_retry(self, max_retries: int = 10, initial_delay: float = 1.0):
    for attempt in range(max_retries):
        try:
            self.ensure_admin()
            return
        except (OperationalError, ConnectionError) as e:
            if attempt == max_retries - 1:
                raise
            wait = initial_delay * (2 ** attempt)
            logger.warning(f"Admin ensure failed (attempt {attempt + 1}/{max_retries}): {e}. Retry in {wait}s")
            await asyncio.sleep(wait)
```

Docker Compose 的 `depends_on: postgres: condition: service_healthy` 可以解决大部分问题,但重试仍是质量保险。

#### A6-4. Task 6.2 邀请码泄露防护

当前邀请码是 varchar(20),如果用户错误地把邀请码粘到公开场合(GitHub / 聊天群),邀请码就泄露了。Phase 1 完全无防护。

**质量优先修法**(不改 schema,用现有字段就够):
- 注册成功时写 audit_log `invite_code.used`,记录使用 IP + User-Agent
- Admin 看到 `max_uses=10` 但 `used_count=3` 里面有 3 个 IP 来自不同国家时能察觉异常
- 邀请码默认 `max_uses=1`,不是可选项
- Admin 生成邀请码时强制设置 `expires_at`(不允许永不过期,最长 30 天),这是**硬规则**写进 schema validation

### DOC-07: Session / Run / Task

#### A7-1. Task 7.1 `messages.sequence_no` 并发 insert 冲突 (B3-4)

DOC-07 Task 7.1 的 messages 查询用 `(session_id, sequence_no)` 索引,但**生成新 sequence_no 的逻辑**文档没写。常见的 `SELECT MAX(sequence_no) + 1 FROM messages WHERE session_id = ?` 模式在**并发 callback 下会出现冲突**:

```
回调 A (text_delta): SELECT MAX(seq) → 10,准备 INSERT seq=11
回调 B (tool_start):  SELECT MAX(seq) → 10,准备 INSERT seq=11  ← 冲突
```

即使加了唯一索引 `(session_id, sequence_no)`,第二个插入会失败,需要重试,质量上 messy。

**质量优先修法 — Postgres sequence per-session**:

方案 1(推荐): Session 级计数器存 Redis,回调时 `INCR sse_seq:{session_id}`:
```python
class MessageService:
    def next_sequence_no(self, session_id: str) -> int:
        """原子递增 session 的 message sequence,Redis INCR 是原子操作"""
        return self._redis.incr(f"msg_seq:{session_id}")
```

方案 2: 用 Postgres `SELECT ... FOR UPDATE` + 事务锁 session 行,性能较差。

方案 3: 用 `SERIAL` 列但按 session 分区 —— Postgres 不原生支持,复杂。

**选方案 1**。质量优先下额外要求: Session 创建时初始化 Redis 计数器为 `SELECT MAX(seq) FROM messages WHERE session_id=?`(避免 Redis 重启后计数丢失),Session 删除时清理 Redis key。

#### A7-2. Task 7.2 Run cancel 的语义不清

```
POST /sessions/{id}/cancel
```

文档说"取消当前正在执行的 Run",但没说:
1. 取消 = kill 子进程 + 标记 cancelled?还是优雅退出(让当前 turn 跑完再停)?
2. 取消后,排队的 queue_items 怎么办?(全部 cancel,还是继续推进下一条?)
3. 子进程 kill 后,已产生的 messages 保留吗?
4. SSE 通知前端"Run 被取消"用什么事件?

**质量优先明确定义**:

```python
# app/services/run_cancel_service.py

class RunCancelService:
    """
    Run 取消的完整语义:
    
    1. Graceful(默认): 发 SIGTERM,子进程在当前 turn 结束时退出。已产生的消息保留
    2. Force(可选): 发 SIGKILL,立即终止。已产生的消息保留
    3. 取消后,当前 Session 的 queue_items 默认保留(用户可能还想执行它们)
       除非 cancel_request.also_cancel_queue=true
    4. SSE 推 "run_cancelled" 事件,data: {run_id, cancel_mode, cancelled_at}
    5. 子进程收到信号后,必须在 5s 内上报 run_error callback (reason="cancelled")
       否则 Backend 10s 后强制标记 cancelled,并 promote 下一个(或者不,看 also_cancel_queue)
    """
    
    async def cancel(
        self,
        session_id: str,
        mode: Literal["graceful", "force"] = "graceful",
        also_cancel_queue: bool = False,
    ) -> None:
        ...
```

API:
```
POST /sessions/{id}/cancel
body: {
    "mode": "graceful" | "force",
    "also_cancel_queue": false,
}
```

#### A7-3. Task 7.2 `Run.status="timeout"` 的处理链路缺失

`runs.status` 允许 `timeout`,但**谁来写 `timeout`** 文档没写。`RUN_TIMEOUT_SECONDS=600`(Batch 1 建议按 agent_type 分档),超时检测在哪?

**选项**:
- A. 子进程自己 sigalrm,超时自己 kill + 上报
- B. Backend ProcessManager 启动子进程时记 start_time,定期扫描超时
- C. Backend 和子进程双重保险(子进程先处理,Backend 兜底)

**质量优先选 C**:
- 子进程 `__main__.py` 启动时用 `signal.signal(signal.SIGALRM, ...)` 设 alarm,超时前 5s 触发,自己 `callback.run_error("timeout")` 然后 exit
- Backend `ProcessManager` 每 30s 扫描 `runs WHERE status='running' AND started_at < now() - interval '{timeout}s'`,强制 kill 子进程 + 标记 timeout + promote 队列

两者都有是因为:子进程可能卡在 API 调用上(httpx timeout 也不工作的极端 case),signal 被阻塞——这时 Backend 兜底;但大多数情况子进程自己处理更优雅。

#### A7-4. Task 7.3 回调协议改造 (B3-3)

Batch 1 决定的方案 A(Redis 直通流式 + HTTP 关键事件)必须在 DOC-07 落地。当前 Task 7.3 的设计是**全 HTTP 回调**,要重构。

**修法** — Callback Service 接收的事件类型重新分类:

```python
# 流式事件(子进程直接 Redis pub,Backend 只订阅转发,不落 DB):
STREAMING_EVENTS = {
    "text_delta",
    "tool_use_start",    # 只是提示前端"开始收工具参数"
    "tool_use_delta",    # 工具参数增量
    "heartbeat",
}

# 关键事件(HTTP 回调,Backend 落 DB + 转发 SSE):
CRITICAL_EVENTS = {
    "tool_start",        # 权限检查通过、准备执行,要持久化 ToolExecution 记录
    "tool_end",          # 工具执行完,要更新 ToolExecution + 生成 tool_result Message
    "harness_event",     # 要写 audit_logs
    "run_complete",      # 要写 runs.harness_summary + promote
    "run_error",
    "session_title",     # 要写 sessions.title
    "permission_ask",    # B3-1,见下
    "message_complete",  # ← 新增事件,当 assistant message 全部 text_delta 完成,要一次性落 DB
}
```

`message_complete` 是新事件,用于 Batch 2 §A3-2 提到的"完整消息持久化":子进程 TAOR 循环中,一个 assistant turn 的所有 text_delta 流式推完后,发送 `message_complete` 事件,携带完整 `content: list[ContentBlock]`,Backend 一次性 insert messages 表。这样 messages 表永远有完整记录。

**Redis 直通的 channel 设计**:
- 子进程 publish → `sse:{session_id}` (前端直接订阅)
- Backend SSE 端点也订阅 `sse:{session_id}` + 自己 publish 关键事件(如收到 run_complete HTTP 回调后,也转一份到 `sse:{session_id}` 推给前端)
- 子进程的 Redis 连接必须用专用账号,ACL 限制只能 `PUBLISH sse:*`,不能 SUBSCRIBE 或其他

**安全性**: 子进程拿到的 session_id 必须是自己对应 run_id 的 session_id,不能伪造。子进程启动时从 DB 读 Run,得到 session_id,之后只允许 publish 到这个 session 的 channel。代码层保证。

**回退兼容**: 如果方案 A 出问题(比如 Redis 故障),子进程应该降级到全 HTTP 模式。加一个启动参数 `--callback-mode=hybrid|http-only`。

#### A7-5. Task 7.3 Permission Ask 端点 (B3-1, Batch 2 B2-1 后端落地)

Batch 2 §A3-7 已经设计了 Redis BLPOP 阻塞协议。Backend 侧必须新增端点:

```python
# app/api/v1/sessions.py

@router.post("/sessions/{session_id}/permission-answer", response_model=ApiResponse[dict])
async def answer_permission(
    session_id: str,
    body: PermissionAnswerSchema,  # {request_id: str, decision: "allow" | "deny"}
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """
    用户对 permission_ask 请求的回答。
    
    流程:
    1. 验证 session 归属(铁律 4)
    2. 验证 permission_ask 请求仍有效(未过期)—— 从 Redis 读 "perm_req:{request_id}" 确认
    3. RPUSH 答案到 "perm_answer:{request_id}"
    4. 写 audit_log (user_id + request_id + decision)
    5. 删除 "perm_req:{request_id}"
    """
    # 1. 验证 session 归属
    session = db.query(Session).filter(
        Session.id == session_id,
        Session.user_id == user.id,
    ).first()
    if not session:
        raise HTTPException(404, "Session not found")
    
    # 2. 验证请求未过期
    req_data = redis.get(f"perm_req:{body.request_id}")
    if not req_data:
        raise HTTPException(410, "Permission request expired or already answered")
    req = json.loads(req_data)
    if req.get("session_id") != session_id:
        raise HTTPException(403, "Request does not belong to this session")
    
    # 3. 推送答案(子进程正在 BLPOP 等待)
    redis.rpush(f"perm_answer:{body.request_id}", body.decision)
    
    # 4. 审计
    audit_log_service.log(
        user_id=user.id,
        action="harness.permission_answered",
        resource_type="permission_request",
        resource_id=body.request_id,
        details={"decision": body.decision, "tool_name": req.get("tool_name")},
    )
    
    # 5. 清理
    redis.delete(f"perm_req:{body.request_id}")
    
    return {"data": {"status": "ok"}}
```

Redis key 生命周期:
- 子进程发起 ask:`SETEX perm_req:{request_id} 300 '{"session_id":...,"tool_name":...,"run_id":...}'` (5 分钟 TTL)
- 同时 `LPUSH + BLPOP perm_answer:{request_id}` 阻塞等待
- 用户答复: Backend RPUSH answer,子进程 BLPOP 返回,继续执行
- 超时: Redis key 过期,子进程 BLPOP 返回 None,视为 deny (fail-safe)

#### A7-6. Task 7.4 子进程崩溃恢复 (B3-2, Batch 2 B-2 后端落地)

Batch 2 §B-2 提到的机制要在 DOC-07 Task 7.4 ProcessManager 里完整落地:

**1. 心跳上报**: 子进程启动后,每 5s 在 Redis 写 `run:{run_id}:heartbeat` = ISO 时间戳,TTL 30s。

**2. Backend 后台任务扫描**:
```python
# app/services/crashed_run_watcher.py

class CrashedRunWatcher:
    """
    后台任务,定期扫描崩溃的 Run。
    在 FastAPI lifespan 里启动,与主进程同生命周期。
    """
    
    async def run(self):
        while not self._stopping:
            try:
                await self._scan_once()
            except Exception:
                logger.exception("Crashed run scan failed")
            await asyncio.sleep(30)  # 30s 一轮
    
    async def _scan_once(self):
        with SessionLocal() as db:
            # 查找所有 running 状态但子进程不存在或心跳超时的 Run
            running_runs = db.query(Run).filter(
                Run.status.in_(["running", "pending"]),
                Run.started_at < datetime.now(UTC) - timedelta(minutes=1),
            ).all()
            
            for run in running_runs:
                heartbeat = self._redis.get(f"run:{run.id}:heartbeat")
                if heartbeat:
                    continue  # 心跳正常
                
                # 子进程没心跳,判定为崩溃
                logger.warning(f"Detected crashed run {run.id}, cleanup")
                
                # 标记失败
                run.status = "failed"
                run.error_message = "Process crashed (no heartbeat)"
                run.finished_at = datetime.now(UTC)
                
                # 尝试读 crash.log(子进程 atexit hook 可能写了)
                crash_log_path = f"/workspace/{run.id}/crash.log"
                if os.path.exists(crash_log_path):
                    with open(crash_log_path) as f:
                        run.error_message += f"\n{f.read()[:1000]}"
                
                # promote 下一个(复用 Task 7.2 的 RunLifecycle.fail_and_promote)
                RunLifecycle(db, redis).fail_and_promote(run.id)
            
            db.commit()
```

**3. 子进程 atexit hook**:
```python
# executor/__main__.py

import atexit
import traceback

def _write_crash_log():
    """异常退出时写 crash.log,供 Backend 读取"""
    if sys.exc_info()[0] is not None:
        try:
            with open(f"/workspace/{args.run_id}/crash.log", "w") as f:
                f.write(traceback.format_exc())
        except Exception:
            pass

atexit.register(_write_crash_log)
```

**4. 用户感知**: 前端收到 `run_error` SSE(Backend 在标记 failed 时 publish),显示"任务被异常中断"。对 Coordinator 类 Run,提供"从上次中断处继续"按钮(基于 coordinator_plans 表,见 A7-7)。

#### A7-7. Task 7.2 新增 `coordinator_plans` 表(Batch 2 §A4-3)

Schema 补齐:

```sql
CREATE TABLE coordinator_plans (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),  -- 冗余,铁律 4 查询用
    plan_json JSONB NOT NULL,
    current_step_index INT NOT NULL DEFAULT 0,
    step_results JSONB NOT NULL DEFAULT '[]',
    status VARCHAR(20) NOT NULL DEFAULT 'running',  -- 'running' | 'completed' | 'failed' | 'paused'
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_coordinator_plans_run ON coordinator_plans(run_id);
CREATE INDEX idx_coordinator_plans_user_status ON coordinator_plans(user_id, status);
```

API:
```
GET    /runs/{id}/coordinator-plan          — 获取 Plan 状态(用户查看进度)
POST   /runs/{id}/coordinator-plan/resume   — 从断点恢复(创建新 Run 继承 plan)
DELETE /runs/{id}/coordinator-plan          — 放弃 Plan
```

### DOC-08: IM Gateway

#### A8-1. Task 8.1/8.2 Webhook 幂等性缺失 (B3-5)

飞书 / 企微 收到 Webhook 未按时回 200 会**重试**,最多 3 次。Prism 当前设计会把同一条消息当作 3 个新消息创建 3 个 Run。

**修法 — 基于平台消息 ID 的幂等**:

各平台都有消息唯一 ID:
- 飞书: `event_id` 或 `message_id`
- 企微: `msg_id`
- Telegram: `update_id`

```python
# app/services/im_idempotency.py

class IMIdempotencyGuard:
    """
    基于平台消息 ID 的幂等保护。
    
    Redis key: "im_idem:{channel}:{platform_msg_id}"
    TTL: 10 分钟(平台重试窗口最长约 5 分钟)
    
    首次收到消息:
      SETNX → 1 (新 key) → 继续处理
      SETNX → 0 (已存在) → 返回缓存的响应,不处理
    """
    
    async def check_and_claim(self, channel: str, platform_msg_id: str) -> bool:
        """
        True = 首次,可以处理
        False = 重复,跳过
        """
        key = f"im_idem:{channel}:{platform_msg_id}"
        return bool(await self._redis.setnx(key, "1") and await self._redis.expire(key, 600))
```

`IMGateway.route()` 的第一件事:
```python
async def route(self, msg: IMIncomingMessage):
    if not await self._idempotency.check_and_claim(msg.channel, msg.platform_msg_id):
        logger.info(f"Duplicate IM message {msg.platform_msg_id} ignored")
        return
    # 继续处理...
```

#### A8-2. Task 8.2 三平台 API 变动的处理策略模糊

Task 8.2 Part A 说"平台 API 可能随时变更,以官方文档为准,不可基于本文档推测"。这是对的,但没说**怎么检测 API 变动**。

**质量优先修法**:
- 每个适配器实现自己的 `health_check()` 方法,调用平台的"获取机器人信息"类端点
- 后台任务每 1 小时 health_check 每个启用的适配器,失败 3 次触发 admin 告警(写 audit_log + 如果配置了邮件/webhook 告警就发)
- 启动时 health_check,失败的适配器自动 disable 并 log error(不阻止 Backend 启动)

#### A8-3. Task 8.2 消息回复的 retry 策略

```
IM Adapter.send() 失败时 log error but not throw
```

质量优先下太粗暴。长消息(几千字)网络抖动导致发送失败,不能只 log 就完事,用户在 IM 里等半天什么都没有。

**修法 — 指数退避重试**:
```python
class IMAdapter(ABC):
    async def send_with_retry(
        self,
        msg: IMOutgoingMessage,
        max_retries: int = 3,
        initial_delay: float = 1.0,
    ) -> bool:
        for attempt in range(max_retries):
            try:
                success = await self.send(msg)
                if success:
                    return True
            except Exception as e:
                logger.warning(f"IM send failed (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(initial_delay * (2 ** attempt))
        # 最终失败,写 audit_log
        audit_service.log(
            user_id=msg.target_user_id,
            action="im.send_failed",
            details={"channel": self.channel_name, "msg_length": len(msg.text)},
        )
        return False
```

#### A8-4. Task 8.3 配对码 6 位数字的安全性

6 位数字 = 100 万空间。配对码 TTL 5 分钟。攻击场景:

```
同时有 100 个有效配对码(Prism 用户多的时候)
攻击者每秒尝试 100 次,每次 6 位随机数字
100 万 ÷ 100 = 1 万秒 ≈ 2.7 小时 穷举完
命中概率: 有效码 × 尝试次数 / 100 万 = 0.01 × N
N=10000 时 100% 命中某个有效码
```

虽然 Prism 自托管规模小,但质量优先下**6 位数字不够**。

**修法 — Base32 12 位**(人类可读,排除易混淆字符 0/O/1/I/L):
```python
PAIRING_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"  # 31 个字符
# 空间: 31^12 ≈ 7.87e17,爆破不可能

def generate_code() -> str:
    return "".join(secrets.choice(PAIRING_CODE_ALPHABET) for _ in range(12))
    # 例如: "K8M2XJP9QR47"
```

显示时分段: `K8M2-XJP9-QR47`,用户易读。

IM 端用户输入 `/pair K8M2-XJP9-QR47` 或 `/pair K8M2XJP9QR47`,解析时去除 `-`。

#### A8-5. Task 8.3 IM 用户第一次对话时的引导

文档说"未绑定用户发消息时回复绑定引导",但**引导内容不具体**。质量优先需要规范:

```python
BINDING_GUIDE_TEXT = """👋 你好!我是 Prism AI 助手。

要使用我,请先绑定你的 Prism 账号:

1. 打开 Prism 网页: {web_url}
2. 登录后,进入「设置 → IM 绑定」
3. 点击「生成配对码」,复制 12 位配对码
4. 在这里回复: /pair YOUR-CODE-HERE

绑定完成后就可以直接和我对话了 :)
"""
```

`{web_url}` 从 `im_channel_configs.config` 的 `web_url` 字段读取,admin 配置时设置。

### DOC-09: MCP / Provider / Admin

#### A9-1. Task 9.1 MCP Server "scope" 语义缺失(Batch 2 C-10 已铺垫)

Batch 2 §P10 指出: Agent 可以有专属 MCP Server(agent-specific)。这需要 mcp_servers 表扩展 scope 字段:

```sql
ALTER TABLE mcp_servers 
ADD COLUMN scope VARCHAR(20) NOT NULL DEFAULT 'user';
-- 'system' | 'user' | 'agent_inline'
-- system: 系统内置,所有用户共享
-- user: 用户自定义,该用户专属
-- agent_inline: Agent 定义里内联,随 Agent 加载启动、结束清理
```

`user_mcp_installs` 表不变(只针对 user scope 的 MCP)。agent_inline scope 的 MCP 不出现在安装列表,只在 Agent 运行时实例化。

#### A9-2. Task 9.1 MCP 配置的 env 敏感字段加密

```
env: JSONB NOT NULL DEFAULT '{}'
```

MCP Server 的 env 可能含敏感信息(API Key、DB 密码)。当前明文存储。

**修法**: env 里名字匹配 `*_KEY` / `*_TOKEN` / `*_SECRET` / `*_PASSWORD` 的字段自动加密(用 ENCRYPTION_KEY):

```python
SENSITIVE_KEY_PATTERNS = ["_KEY", "_TOKEN", "_SECRET", "_PASSWORD", "API_KEY"]

def encrypt_sensitive_env(env: dict, encryption_key: str) -> dict:
    result = {}
    for k, v in env.items():
        if any(pattern in k.upper() for pattern in SENSITIVE_KEY_PATTERNS):
            result[k] = "enc:" + encrypt_value(v, encryption_key)
        else:
            result[k] = v
    return result

def decrypt_sensitive_env(env: dict, encryption_key: str) -> dict:
    result = {}
    for k, v in env.items():
        if isinstance(v, str) and v.startswith("enc:"):
            result[k] = decrypt_value(v[4:], encryption_key)
        else:
            result[k] = v
    return result
```

Backend API 返回 env 时**不解密**,只返回字段名 + 是否敏感的标记,让前端知道这些字段不回显。MCP 启动时在子进程侧解密后注入环境变量。

#### A9-3. Task 9.2 `providers.is_healthy` 基于 Redis 的读取 race

```python
for p in providers:
    circuit_data = redis.get(f"harness:circuit:{p.id}")
    if circuit_data:
        p.is_healthy = False
    else:
        p.is_healthy = True
return providers
```

问题:
1. 每个 Provider 一次 Redis GET,N 个 Provider N 次调用,延迟放大
2. 这里修改了 SQLAlchemy 的 ORM 对象但**没 db.commit()**,会误导读者以为是持久化
3. `is_healthy` 这个字段既在 DB 又靠 Redis 反查,**数据源不一致**

**修法**:
1. Redis `MGET`:
```python
circuit_keys = [f"harness:circuit:{p.id}" for p in providers]
circuit_results = redis.mget(circuit_keys)
for p, circuit in zip(providers, circuit_results):
    p.is_healthy = circuit is None
```
2. 明确 `is_healthy` 是**视图字段**,不持久化回 DB。SQLAlchemy 的 `@hybrid_property` 或 Pydantic 响应 Schema 单独计算,ORM 对象不污染。
3. Schema 响应里改名 `live_health: HealthStatus` 更明确表示是实时状态,不是持久字段:
```python
class ProviderResponse(BaseModel):
    id: str
    name: str
    # ...
    live_health: Literal["healthy", "circuit_open", "unknown"]
    # healthy = Redis 无熔断记录
    # circuit_open = 有熔断记录
    # unknown = Redis 故障或无法读取
```

#### A9-4. Task 9.3 Admin 审计日志 — Part B 缺失

Task 9.3 的 Part B 直接写"待实施计划执行阶段补充",改写阶段必须补完整。这是硬漏洞。

#### A9-5. Task 9.3 审计日志导出 CSV/JSON 格式

"审计日志导出支持 CSV 和 JSON 两种格式"——但 audit_logs.details 是 JSONB,CSV 里怎么存?

**质量优先明确定义**:

CSV 导出时 `details` 字段用 JSON 字符串序列化,包在一列里。如果 details 很大会撑爆 Excel,所以:
- CSV 适合做"粗筛 + 时间线展示"的场景,details 过长时截断 500 字符并在最后标记 "... (truncated)"
- 需要完整 details 分析时用 JSON 格式导出

API:
```
GET /admin/audit-logs/export?format=csv|json&...筛选参数
→ 流式下载,Content-Type 对应
→ CSV 文件头: id,user_id,action,resource_type,resource_id,details_summary,ip_address,created_at
→ JSON 文件: {"logs": [...], "exported_at": "...", "filters": {...}}
```

导出数据量限制:单次导出不超过 10000 条,超过需要分时间段多次导出(Admin UI 提示)。

#### A9-6. Task 9.3 非功能要求: 用户删除的级联

`DELETE /admin/users/{id}` 文档说是"软删除",但 14 表的 schema 大部分用 `ON DELETE CASCADE`——**软删除和级联冲突**:

- 软删除: users.status 改 'disabled',记录保留
- 硬删除 + CASCADE: DELETE 会级联删除 sessions/runs/messages 等

文档用"禁用"这个词暗示软删除,但 schema 和其他 CASCADE 外键显示预期是硬删除。**两者选一**。

**质量优先选软删除**:
- users 表新增 `status VARCHAR(20) NOT NULL DEFAULT 'active'` (`active` | `disabled` | `deleted_pending`)
- `DELETE /admin/users/{id}` 改成 `PATCH /admin/users/{id}/status` body `{status: "disabled"}`
- 禁用后该用户登录返回 403,不能创建新 Run
- 如果真要彻底删除,走"请求删除 → 30 天冷静期 → 硬删除"流程(Admin 确认)

---

## Part B — 架构级审视

### B3-I. Backend 进程外的状态散落多处

当前 Backend 进程外的状态存储:
- **PostgreSQL**: 持久化数据
- **Redis**: SSE pub/sub、sse session cache、rate limit、熔断状态、pairing code、permission_request、heartbeat、im 幂等
- **文件系统**: `/workspace/{run_id}/` 工作目录、crash.log

Redis 的 key 命名混乱,各 module 自己起名,冲突时难发现。

**质量优先修法 — Redis namespace 约定**:

集中定义所有 Redis key 的 namespace 规则,文档化在新章节 DOC-01 §10(Harness 状态存储策略后追加):

```python
# app/core/redis_keys.py

"""Redis Key Namespace 规范

所有 Redis key 必须遵循以下命名:
    {domain}:{subdomain}:{identifier}

Domain 列表(不可新增,需改本文件):
- sse              — SSE pub/sub channels
- run              — Run 运行时状态(heartbeat, lock)
- harness          — Harness 运行时状态
- rl               — Rate limit 计数器
- im               — IM 相关(idempotency, pairing code)
- perm             — Permission 相关(ask request/answer)
- sse_ticket       — SSE 连接 ticket
- msg_seq          — Message sequence counter per session
"""

# 使用常量函数,避免字符串拼接
def sse_channel(session_id: str) -> str: return f"sse:channel:{session_id}"
def run_heartbeat(run_id: str) -> str: return f"run:heartbeat:{run_id}"
def harness_circuit(provider_id: str) -> str: return f"harness:circuit:{provider_id}"
def rate_limit(endpoint: str, ip: str) -> str: return f"rl:{endpoint}:{ip}"
def im_idempotency(channel: str, msg_id: str) -> str: return f"im:idem:{channel}:{msg_id}"
def im_pairing(code: str) -> str: return f"im:pair:{code}"
def permission_request(req_id: str) -> str: return f"perm:req:{req_id}"
def permission_answer(req_id: str) -> str: return f"perm:answer:{req_id}"
def sse_ticket(ticket: str) -> str: return f"sse_ticket:{ticket}"
def msg_sequence(session_id: str) -> str: return f"msg_seq:{session_id}"
```

所有 Redis 访问必须用这些函数,不允许裸拼字符串。Code review 时硬查。

### B3-II. 子进程的 DB 访问反常识

DOC-07 §Part A 明文:"Executor 运行时不直接访问 DB"。但实际上:

1. 子进程**启动时**必须从 DB 读 Run 配置(sync)
2. `coordinator_plans` 表(Batch 2 §A4-3 新增)需要子进程**运行时**写 step_results —— 这是新的 DB 访问
3. `audit_logs` 里 Harness 事件如果需要实时查询(比如 Obs 子系统),子进程是否要直接写 DB 还是都走回调?

**三选一策略**:
- **严格 "子进程不访问运行时 DB"** —— 所有持久化都走回调,DB 归 Backend 独占。但 coordinator_plans 每 step 都要回调一次,延迟累加
- **子进程只读运行时 DB,不写** —— coordinator_plans 读(进度查询)走 DB,写走回调。逻辑清晰
- **子进程可读写自己 Run 相关的表** —— 划定白名单(coordinator_plans, runs where id=current_run_id),其他禁止

**质量优先选第 2 种**: 子进程启动时读配置,运行时只写回调。`coordinator_plans` 的 step_results 更新通过新的回调事件 `coordinator_step_complete` 触发 Backend 写 DB。清晰、单向、可测试。

### B3-III. SSE 连接数上限和扩展性

DOC-01 §7.2 提到"心跳间隔 15 秒,防止代理层超时断开"。但没有 SSE 连接数管理:

- 多个浏览器 tab 打开同一 session → 多个 SSE 连接订阅同一 channel
- 用户闲置页面不关 tab,SSE 持续保持
- FastAPI / Uvicorn 单 worker 大约 500-1000 并发 SSE 就扛不住

**质量优先修法**:
1. **每用户最多 N 个活跃 SSE 连接**(比如 5 个),超过新连接时最老的自动断开。前端显示"已在其他窗口打开,此窗口已断连"
2. **SSE 连接的健康状态可观测**: /metrics 端点暴露 `prism_sse_connections_active`,监控 gauge
3. **优雅关闭**: Backend 关闭时给所有 SSE 连接发 `shutdown` 事件让前端主动断开重连

### B3-IV. IM 消息路由和 Session 绑定的一致性

DOC-08 §Task 8.1 原则:"Session 按 `(user_id, im_channel, im_chat_id)` 查找或创建"。含糊之处:

- 同一 IM 用户在同一群里和 Prism 聊天 → 一个 Session
- 同一 IM 用户在另一群里 → 另一个 Session
- 同一 IM 用户在私聊 → 又一个 Session
- 这些 Session 互相不知道对方存在 → 用户记忆不连贯

**质量优先**: IM Session 用 `(user_id, im_channel, im_chat_id)` 唯一确定是对的。但要加一个**共享 User Memory 层**(Batch 2 §A3-9 的 user_memories 表): 同一 user_id 的所有 Session 共享 user memory,保证跨 Session(跨群、跨平台)的用户偏好延续。

额外: Web 端和 IM 端**也应该共享 user_memories**,这样用户在 Web 端告诉 Agent "我叫小王",在 IM 端 Agent 也能记住。

### B3-V. Backend 启动依赖链

Backend 启动时的 lifespan 需要:
1. 连 Postgres → 重试
2. 跑 Alembic migration → 重试
3. 连 Redis → 重试
4. ensure_admin → 重试
5. 启动 CrashedRunWatcher 后台任务
6. 启动 IM Adapter (飞书 WebSocket、Telegram Long Polling)
7. 启动 SSE Manager (Redis subscriber)

**当前 DOC-07 没有 lifespan 顺序的完整定义**。任一环节失败怎么处理?

**质量优先修法 — lifespan 阶段化**:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 阶段 1: 依赖检查(必须全部通过,否则启动失败)
    await wait_for_postgres(timeout=60)
    await wait_for_redis(timeout=30)
    
    # 阶段 2: 数据初始化(可失败重试,失败则启动失败)
    await run_migrations()
    await ensure_admin()
    
    # 阶段 3: 后台任务启动(失败不阻止,只 log warning)
    app.state.crashed_run_watcher = asyncio.create_task(CrashedRunWatcher().run())
    
    # 阶段 4: IM 适配器启动(可选,配置启用的才启动)
    app.state.im_adapters = []
    for config in get_enabled_im_configs():
        try:
            adapter = create_im_adapter(config)
            await adapter.start()
            app.state.im_adapters.append(adapter)
        except Exception:
            logger.exception(f"Failed to start IM adapter {config.channel}")
            # 不阻止 Backend 启动,但写 audit_log
    
    logger.info("Backend ready")
    yield
    # 关闭
    for adapter in app.state.im_adapters:
        await adapter.stop()
    app.state.crashed_run_watcher.cancel()
```

---

## Part C — v3.1 新增 Task 评估

### C-1. Task 9.3 Admin 审计日志与系统管理

**定位**: Admin 管理功能补齐。

**Part A 已指出的问题**:
- A9-4 Part B 缺失,改写阶段必须补完整
- A9-5 CSV 导出 JSONB details 的处理策略
- A9-6 用户删除与 CASCADE 的语义冲突

**质量优先最终建议**:

1. **Part B 完整版起草**(改写阶段):
   - `app/services/audit_service.py` 的完整接口:`log()` / `query()` / `export()`
   - `app/api/v1/admin.py` 六个 Admin 端点的完整实现
   - Schema 完整定义 `AuditLogQuery` / `AuditLogResponse` / `SystemStatsResponse` / `UserListResponse` / `UserRoleUpdateSchema`
   - 分页、筛选、排序的 Query 参数组合穷举

2. **系统统计数据清单**:
```python
class SystemStatsResponse(BaseModel):
    users_total: int
    users_active_7d: int
    users_new_30d: int
    
    sessions_total: int
    sessions_active_now: int  # status='running'
    
    runs_total: int
    runs_completed_24h: int
    runs_failed_24h: int
    runs_timeout_24h: int
    
    tokens_used_24h: int
    tokens_used_30d: int
    cost_usd_24h: float
    cost_usd_30d: float
    
    harness_events: dict  # {"guardrail_trigger": 12, "permission_deny": 3, ...}
    
    # 系统健康
    providers_healthy: int
    providers_unhealthy: int
    mcp_servers_healthy: int
    mcp_servers_unhealthy: int
    im_adapters_healthy: int
    im_adapters_unhealthy: int
```

3. **权限边界验证**:
- 所有 `/admin/*` 端点都必须 `require_admin`(通过 DOC-06 的 dependency)
- `PATCH /admin/users/{id}/role` 禁止把**最后一个 admin** 降级为 user(否则系统永远没有 admin,需要重置 ADMIN_EMAIL 重启 — 边缘 case)
- `DELETE /admin/users/{id}`(改为 status=disabled)禁止禁用自己

---

## 总结 & 对下一批的影响

### Batch 3 发现的问题量

- **实现级**: 17 项(Part A)
- **架构级**: 5 项(Part B)
- **新 Task C-1 做法修订**: Part B 缺失 + 系统统计清单 + 权限边界

### 对 Batch 4 (Frontend) 的影响

新的前端需求点:
- **permission_ask 弹窗 UX**(A7-5 端点落地后,前端怎么展示)
- **permission_ask 的超时提示**(BLPOP timeout 后前端显示"请求已超时")
- **Run 被取消的三种模式显示**(A7-2 graceful/force + also_cancel_queue)
- **Coordinator Plan 进度 UI**(A7-7 coordinator_plans 表驱动)
- **SSE ticket 流程** (Batch 1 §3.3 落地后前端要先拿 ticket 再连 SSE)
- **多 tab 限制提示**(B3-III 一个用户最多 N 个 SSE 连接)
- **IM 绑定流程 UI**(配对码生成 + 显示 + 复制 + 引导)
- **Admin 审计日志筛选和导出**(C-1)
- **系统统计仪表盘**(C-1)

### 对 Batch 5 (Obs) 的影响

- **Redis namespace 规范**(B3-I)是 Obs 观测数据的基础
- **子进程心跳监控**(A7-6)的 metrics 暴露点
- **Provider 健康状态的 Redis → DB 同步**(A9-3)的 freshness 监控
- **IM 幂等检测的命中率**(A8-1)作为系统健康指标

---

> **下一步**: 进 Batch 4(Frontend DOC-10/11 + 2026-04-07 UI design + Task 11.5)
> **本 Batch 覆盖**: DOC-06 (27KB) + DOC-07 (48KB) + DOC-08 (24KB) + DOC-09 (16KB) + v3.1 对应部分 = ~120KB
