# Prism v2 架构 Review — Batch 2: Agent 核心层

> **范围**: DOC-03 (Agent Runtime + Harness Core) / DOC-04 (Orchestration) / DOC-05 (Plugin Ecosystem)
> **新增 Task 评估**: Task 3.6 / 4.5 / 5.5 / 5.6 / 5.7
> **立场**: 质量优先、不砍功能、追求"更合理更好维护"的内部优解
> **评审者**: Claude Opus 4.7

---

## 0. 整体判断

DOC-03/04/05 三份合起来定义了 Prism 的**技术心脏**。三份文档的共同特征是:**设计野心非常大,设计深度不均匀**——架构图画得到位,接口签名写得规范,但**关键语义**(比如 "ask" 权限的反向通信、Compaction 的 fallback、Fork 的 cache 一致性、HookDecision 的合并冲突)**一律模糊化**,靠"后续实现时决定"搪塞。这在 Phase 1 就进 Production-grade 的质量立场下是**不可接受**的。

按重要性排序,Batch 2 最严重的 5 个问题:

| # | 问题 | 影响 |
|---|---|---|
| **B2-1** | **`permission="ask"` 的反向通信协议未定义** | "人工确认"整个功能无法实现,或者实现了但全是 hack |
| **B2-2** | **Compaction 的 tool_use↔tool_result 配对保护算法未定义** | 上线后的经典 Anthropic API 报错 "tool_result missing corresponding tool_use",找 bug 找到怀疑人生 |
| **B2-3** | **Task 3.1 工具调用串行执行** | 模型并行 tool_use 时被强制串行,质量优先下是性能缺陷 |
| **B2-4** | **Task 4.5 PluginBuilder 硬编码 5 轮对话** | 违反 P5 配置驱动,把次数等同于质量,并用 platform_level Guardrail 锁死,违反设计哲学 |
| **B2-5** | **Task 3.6 HarnessConfigManager 4 源合并** | 配置优先级、变更路径、source_trace 全在注释里,运维噩梦 |

下面按 Part A / B / C 展开。

---

## Part A — 实现级审视(替代 4.6 AUDIT)

### DOC-03: Agent Runtime & Harness Core

#### A3-1. Task 3.1 TAOR — 工具调用串行化(B2-3)

`QueryEngine._execute_tools()`:
```python
for block in tool_use_blocks:
    start = time.monotonic()
    await self._callback.tool_start(...)
    result = await self._pipeline.execute(...)
    await self._callback.tool_end(...)
    tool_results.append(result)
```

问题:模型在一个 turn 可以返回多个独立 `tool_use`(Anthropic 显式支持 parallel tool use,OpenAI 通过 `parallel_tool_calls=true`)。当前用 for 循环串行 `await`,3 个独立的 `web_search` 会跑 3× 延迟。

**修法**: 用 `asyncio.gather()` 并行,保留顺序:
```python
async def _execute_single(block):
    start = time.monotonic()
    await self._callback.tool_start(...)
    result = await self._pipeline.execute(...)
    await self._callback.tool_end(...)
    return result

tool_results = await asyncio.gather(
    *(_execute_single(b) for b in tool_use_blocks),
    return_exceptions=False  # 单个失败不影响其他
)
```

注意:`tool_results` 的顺序必须和 `tool_use_blocks` 一致(asyncio.gather 保证这点)。回调的 `tool_start/tool_end` 并行发出,前端 UI 要能同时显示多个工具卡片(Batch 4 讨论前端如何呈现)。

**质量优先追加**: 工具间有依赖关系(比如 tool B 的输入用 tool A 的输出)时不能并行。需要 Agent 在一个 turn 内只输出无依赖 tool_use,有依赖的拆到下一 turn。这是模型侧行为,但需要在 Prompt 里显式说明——`tool_grammar_section` 里"没有依赖的工具调用应当并行"这句话应该更强硬:"**有依赖的工具调用必须分 turn 输出,不要在同一 turn 返回依赖链**"。

#### A3-2. Task 3.1 `PrismMessage(role="tool_result")` 统一抽象的代价

代码里:
```python
self._messages.append(PrismMessage(
    role="tool_result",
    content=tool_results,  # 多个 ToolResultBlock 打包进一条消息
))
```

问题:Prism 自创了 `role="tool_result"`,但两大协议都没有这个 role:
- Anthropic: tool_result 在 user message 的 content 里
- OpenAI: N 条独立 role="tool" 消息

Driver 层要做:"一条 PrismMessage(role=tool_result) → Anthropic user message(含 tool_result blocks)/ OpenAI N 条 tool messages"。这个转换在 DOC-02 里提过(§5.3 表格),但实现起来:

- Anthropic 方向还行,PrismMessage 的 content list 直接塞进 Anthropic user.content
- OpenAI 方向必须拆开:`PrismMessage.content[0]` → 第一条 tool message,`content[1]` → 第二条...

**代价**: 消息数量在 Anthropic 和 OpenAI 之间不一致,`messages[]` 长度不同,导致 **Compaction 按消息数裁剪时行为不一致**,同一 Run 在不同 Provider 下 compaction 触发时机差异很大。

**修法**: 改成 Anthropic 原生语义。`PrismMessage.role` 只有 `user` / `assistant`,tool_result 作为 user message 的 content block:

```python
@dataclass
class PrismMessage:
    role: Literal["user", "assistant"]  # 只有 2 种
    content: list[ContentBlock]  # TextBlock | ToolUseBlock | ToolResultBlock

# 工具结果追加时:
tool_result_msg = PrismMessage(
    role="user",  # tool_result 在 user message 里
    content=[ToolResultBlock(...), ToolResultBlock(...)],
)
```

OpenAIDriver 负责在发送给 OpenAI 时"把 user message 里的 tool_result content 拆成 N 条 tool role"——拆分逻辑放在 Driver 底层,上层统一用 Anthropic 语义。这符合 §9.1 原则"双协议之一做 canonical"(选 Anthropic 做 canonical 因为它表达能力更强)。

#### A3-3. Task 3.1 Compaction 破坏 tool_use↔tool_result 配对(B2-2)

`ContextBudgetManager.compress_history()` 注释说"保留所有 tool_use / tool_result 对(不破坏工具调用链)",但**没给算法**。

这个问题在 Anthropic API 会表现为:
```
400 Bad Request
messages.3.content.0.tool_result: no corresponding tool_use found
```

原因:compaction 删除了前面某条 assistant message 的 tool_use block,但保留了后面对应的 tool_result block(反之亦然)。Anthropic 严格要求配对。

**修法**: 写明 compaction 的单元不是"消息",而是"回合组"(turn group):

```
回合组 = 1 条 assistant message(含 text + tool_use)+ 1 条 user message(仅含 tool_result,如有)

compact 的原子单元是回合组,删除必须整组删除:
- 要么保留完整回合(assistant message + 对应 user tool_result message)
- 要么删除完整回合(同时删 assistant 和 user tool_result)

这样配对永远不破坏。
```

ContextBudgetManager 的 compress_history 签名改为:
```python
def compress_history(self, messages: list[PrismMessage]) -> list[PrismMessage]:
    """按回合组裁剪,保留 tool_use↔tool_result 配对完整性"""
    turn_groups = self._group_into_turns(messages)
    # 从最旧的 turn 开始删除,直到满足目标 token 数
    ...
```

**验收必须加的测试**: 构造一个含多个 tool_use/tool_result 对的对话,执行 compact,断言结果中所有 tool_use 都能找到对应 tool_result(或同时消失)。

#### A3-4. Task 3.1 BackendCallback 错误静默吞

```python
try:
    await self._client.post(...)
except Exception:
    pass  # 回调失败不应影响 Agent 执行
```

质量优先下这是反模式。回调失败意味着:
- text_delta 丢失 → 前端流式显示断裂
- tool_end 丢失 → DB 里 tool_executions 表缺记录
- run_complete 丢失 → runs.status 永远 running,promote 队列卡死
- harness_event 丢失 → 审计合规失败

**修法**:
```python
async def emit(self, event_type: str, data: dict) -> None:
    """短期重试 + 关键事件不丢"""
    CRITICAL_EVENTS = {"tool_end", "run_complete", "run_error", "harness_event"}
    max_retries = 3 if event_type in CRITICAL_EVENTS else 1
    backoff = [0.1, 0.5, 2.0]
    
    for attempt in range(max_retries):
        try:
            resp = await self._client.post(...)
            resp.raise_for_status()
            return
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(backoff[attempt])
                continue
            # 最后一次失败
            logger.error(f"Callback failed after retries: event={event_type}", exc_info=True)
            if event_type in CRITICAL_EVENTS:
                # 关键事件失败要进本地 dead letter queue
                await self._dead_letter.append(payload)
```

**配合 D3 决策 A(Redis 直通)**: `text_delta` / `tool_use_start/delta` 这些流式事件走 Redis pub/sub(best effort),关键事件走 HTTP(有重试)。这样重试逻辑只用在真正需要可靠性的事件上。

#### A3-5. Task 3.2 Middleware 钩点不足

当前只有 `pre_turn` / `post_turn`。但 TAOR 循环里关键节点其实有 4 个:
```
turn 开始 ─ pre_turn
  ├─ 构造 prompt
  ├─ 调用模型(流式)
  ├─ 解析 tool_use
  │   └─ 每个 tool_use:
  │       ├─ pre_tool_use    ← 缺失
  │       ├─ 执行工具
  │       └─ post_tool_use   ← 缺失
  └─ 更新 messages
turn 结束 ─ post_turn
```

当前设计把 pre_tool_use / post_tool_use 留给 Hook System(Task 3.3),Middleware 只做 turn 级。但 Middleware 和 Hook 职责不同:
- **Middleware** = 框架级基础设施(Loop Detection, Rate Limit, Observability)
- **Hook** = 用户/插件定义的钩子

**Loop Detection 这种需要 per-tool-call 视角的 Middleware 当前被迫放在 post_turn**,只能事后检测而非 pre 拦截,失去了"检测到循环立刻 break"的机会。

**修法**: 4 钩点完整暴露给 Middleware:
```python
class Middleware(ABC):
    async def pre_turn(self, ctx: TurnContext) -> None: pass
    async def pre_tool_use(self, ctx: TurnContext, tool_use: ToolUseBlock) -> None: pass
    async def post_tool_use(self, ctx: TurnContext, tool_use: ToolUseBlock, result: ToolResultBlock) -> None: pass
    async def post_turn(self, ctx: TurnContext) -> None: pass
```

Hook System 和 Middleware 并存,两者在同一钩点都执行(Middleware 先,Hook 后,因为 Middleware 是框架级,Hook 是插件级)。

#### A3-6. Task 3.3 HookSystem 决策合并规则模糊

文档:
> 任何一个 handler 返回 deny → 最终 deny
> 只要有 updated_input → 使用最后一个
> additional_context 拼接

问题:
1. **permission 三态合并**: handler A 返回 `allow`,handler B 返回 `ask`,最终应该是 `ask` 还是 `allow`?文档只定义 deny 胜出,allow vs ask 没说
2. **updated_input 冲突**: handler A 把 `{"path": "/tmp/a"}` 改成 `{"path": "/safe/a"}`,handler B 把 `{"path": "/tmp/a"}` 改成 `{"path": "/backup/a"}` —— 谁胜出?"使用最后一个"意味着 Hook 注册顺序是语义,但注册顺序是运维行为(插件加载顺序),这是隐性耦合
3. **updated_input + 语义冲突**: handler A 把 path 改安全,handler B 返回 deny —— input 改了但又 deny?当前逻辑"只要有 deny 就 deny",但改过的 input 怎么办?如果 deny 胜出,改 input 白做了,如果 input 应用了再 deny,语义混乱

**修法**: 明文三原则:

```python
def merge_decisions(decisions: list[HookDecision]) -> HookDecision:
    """
    合并规则(明文定义,不靠注释):
    
    1. permission 严格度顺序: deny > ask > allow(任一个 deny 就 deny,否则任一个 ask 就 ask,全 allow 才 allow)
    2. updated_input 不允许多 handler 同时改 —— 检测到冲突则 abort 并 log(决策模糊,拒绝猜)
    3. additional_context 按 handler 注册顺序拼接,去重
    4. prevent_continuation 任一 True 即 True
    """
    # 1. permission
    perms = [d.permission_decision for d in decisions if d.permission_decision]
    if "deny" in perms:
        final_perm = "deny"
    elif "ask" in perms:
        final_perm = "ask"
    elif perms:
        final_perm = "allow"
    else:
        final_perm = None
    
    # 2. updated_input 冲突检测
    updated_inputs = [d.updated_input for d in decisions if d.updated_input]
    if len(updated_inputs) > 1:
        raise HookConflictError(
            f"Multiple handlers attempted to update input: {[d.handler_name for d in decisions if d.updated_input]}"
        )
    final_input = updated_inputs[0] if updated_inputs else None
    
    # 3. additional_context 去重拼接
    contexts = []
    for d in decisions:
        if d.additional_context and d.additional_context not in contexts:
            contexts.append(d.additional_context)
    final_context = "\n".join(contexts)
    
    # 4. prevent_continuation OR
    final_prevent = any(d.prevent_continuation for d in decisions)
    
    return HookDecision(
        permission_decision=final_perm,
        updated_input=final_input,
        additional_context=final_context,
        prevent_continuation=final_prevent,
    )
```

**质量优先**: "冲突 abort" 是质量选择——当两个 handler 对同一 input 有不同改写意图时,是真实的**需求冲突**,应该让用户/开发者看见,而不是系统猜一个。

#### A3-7. Task 3.3 "ask" 权限反向通信协议未定义(B2-1)

`HookDecision.permission_decision = "ask"` 的实际语义是:
1. 子进程 Agent 的 TAOR 循环需要**暂停**
2. 给用户展示"Agent 想做 XX,是否允许?"
3. 等待用户点击"允许 / 拒绝"
4. 子进程继续

当前架构**完全没有反向通信路径**:
- 子进程 → Backend: HTTP 回调(单向)
- Backend → 子进程: **没有**

那 "ask" 怎么实现?文档没写。

**可能的三种实现**(质量优先下必须选一种并写进 PRD):

**方案 X(Redis blocking list)**:
```
子进程: publish harness_event{"type":"permission_ask","request_id":X}
       → BLPOP "perm_answer:{request_id}" TIMEOUT=300  # 阻塞等待
Backend: 收到 harness_event → SSE 推前端 → 用户点击
       → API POST /sessions/{id}/permission-answer body={request_id, decision}
       → RPUSH "perm_answer:{request_id}" decision
子进程: BLPOP 返回 decision,继续
```

**方案 Y(轮询 DB)**:
```
子进程: 写入 permission_requests 表,status=pending
       → 循环 SELECT status,sleep 500ms,直到 status != pending
Backend: 前端 API 改 status=allowed/denied
子进程: 读到非 pending,继续
```

**方案 Z(WebSocket 双向)**:
```
子进程: WebSocket 发 ask → Backend → SSE 推前端
用户回答 → Backend WebSocket 推回子进程
```

**我的推荐: 方案 X**,理由:
- Redis 已经在技术栈里(本来就用于 SSE pub/sub)
- BLPOP 是 Redis 原生阻塞操作,实现最简单
- timeout 机制天然支持(超过 5 分钟自动 deny + fallback)
- 不需要引入 WebSocket 的复杂度
- 不需要轮询 DB 的性能开销

**PRD 必须补的内容**: Task 3.3 明文定义方案 X 的协议:

```python
# executor/harness/permissions/ask_protocol.py

class PermissionAskProtocol:
    async def ask_user(
        self,
        tool_name: str,
        tool_input: dict,
        reason: str,
        run_id: str,
        timeout: int = 300,
    ) -> Literal["allow", "deny"]:
        """
        向用户请求权限确认。
        阻塞等待直到:
        - 用户通过 Web UI 回答 → 返回 'allow' / 'deny'
        - 超过 timeout → 返回 'deny'(fail-safe)
        """
        request_id = str(uuid7.create())
        answer_key = f"perm_answer:{request_id}"
        
        # 1. 通过回调上报 ask 事件(Backend 转 SSE)
        await self._callback.harness_event("permission_ask", {
            "request_id": request_id,
            "tool_name": tool_name,
            "tool_input": tool_input,
            "reason": reason,
            "timeout": timeout,
        })
        
        # 2. Redis BLPOP 阻塞等待回答
        try:
            result = await self._redis.blpop(answer_key, timeout=timeout)
            if result is None:
                return "deny"  # timeout fail-safe
            _, answer = result
            return answer.decode() if isinstance(answer, bytes) else answer
        except Exception:
            return "deny"
```

Backend 侧新增 API `POST /sessions/{id}/permission-answer`:
```python
@router.post("/sessions/{session_id}/permission-answer")
async def answer_permission(
    session_id: str,
    body: PermissionAnswerSchema,  # {request_id, decision}
    user: User = Depends(get_current_user),
):
    # 校验 session 归属
    # RPUSH "perm_answer:{request_id}" decision
    await redis.rpush(f"perm_answer:{body.request_id}", body.decision)
    return {"data": {"ok": True}}
```

前端 SSE 收到 `harness_event{type:permission_ask}` → 弹窗 → 用户点击 → POST API → 子进程继续。

**这是 B2-1 的完整修复。Task 3.3 必须包含这一整段设计。**

#### A3-8. Task 3.5 Tier 2 auto-compact 的 Provider 和 fallback 未定义

Tier 2 要调模型生成摘要。文档没说:
- 用哪个 Provider?(当前 Run 的 Provider 成本最高;如果用 cheap Provider,用户没配怎么办)
- 压缩失败怎么办?(用同一 Provider 失败时;用户的 default Provider 都不通时)
- 压缩耗时期间模型 API 是占用当前 Run 的速率配额的,用户感知到"卡住"

**修法**:

```python
# 明文决策:Tier 2 使用当前 Run 的 Provider(不引入额外 Provider 概念)
# 压缩请求的 system prompt 独立,messages 是"请总结以下对话历史":

compact_system = "你是一个对话历史摘要助手。以下是一段 AI Agent 的对话历史..."
compact_messages = [
    {"role": "user", "content": f"请将以下对话压缩为 500 字的摘要,保留关键决策、工具调用和结论:\n\n{serialize_history(messages)}"}
]
response = await adapter.complete(
    messages=compact_messages,
    system_prompt=compact_system,
    tools=None,
    max_tokens=1024,
)

# Fallback 链:
# Tier 2 尝试压缩 → 失败 3 次 → 降级到 Tier 3(session memory 提取关键信息) 
# → Tier 3 也失败 → Tier 4(reactive truncation,直接删最旧 50%)
# → Tier 4 压缩后仍超限 → run_error("Context overflow, cannot compact further")
```

SSE 需要额外事件 `compaction_in_progress` / `compaction_complete`,让前端 UI 显示"正在压缩历史,请稍候..."。用户体验加分。

#### A3-9. Task 3.5 User Memory 持久化位置未定

"User memory — 用户级偏好/历史" 存哪?DOC-01 的 14 张表没有 user_memory 表,users 表也没 memory 字段。

**修法**: Batch 1 的 schema 补丁已提数据模型漏洞,这里具体补:

```sql
-- 方案(选一):
-- A. users 表加 memory TEXT NULL 字段(简单)
-- B. 新增 user_memories 表(可扩展,支持版本/摘要/手动编辑)

-- 推荐 B:
CREATE TABLE user_memories (
    id UUIDv7 PK,
    user_id UUID FK → users.id ON DELETE CASCADE,
    memory_text TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now(),
    updated_by VARCHAR(20) NOT NULL,  -- 'auto' | 'manual'
    version INT NOT NULL DEFAULT 1,
    UNIQUE(user_id)
);
```

User memory 的写入时机:SessionEnd Hook 里,提取本 session 的关键信息(用户偏好、常用工具、术语)→ merge 到 user_memories。这需要 LLM 调用,走和 Tier 2 相同的 Provider。

#### A3-10. Task 3.6 HarnessConfigManager 问题汇总(B2-5,已在 Batch 1 提,Batch 2 具体修)

| 问题 | Batch 2 修法 |
|---|---|
| 4 源合并 | 砍到 2 源: `platform_rules.py` + `harness_config.yaml`。删除 DB 存储和 `PATCH /harness/config` API。Plugin 注入的规则在**插件加载时写入 yaml 的 plugin section**,而不是独立第 4 源。 |
| 4 种变更路径 | 留 2 种: watchdog 本地监听 + Redis pub 跨子进程通知。删除 API 触发 reload。 |
| turn 粒度原子切换 | Config Version Counter: `self._config_version: int`,每次 reload 递增。QueryEngine 每 turn 开始调 `config.get_effective_config()`,内部对比 version,变了就 refetch。不需要 pub/sub 异步监听主循环。 |
| Plugin 卸载时规则移除的一致性 | Plugin 卸载时不立即改 yaml,而是标记 `.prism/plugins/{name}/disabled`,yaml 加载时跳过 disabled 的 plugin section。这样正在跑的 Run 下一 turn 看到新配置。 |
| source_trace 弱类型 dict | 改为 dataclass: `Source(type: Literal["platform", "file", "plugin"], origin: str)`。 |
| 平台级规则覆盖 | 平台级 `GuardrailRule.platform_level=True` 不可被任何 yaml/plugin 规则覆盖。yaml 解析时如果发现有和 platform 同 id 的规则,raise error 不加载。 |

### DOC-04: Agent Orchestration

#### A4-1. Task 4.1 `allowed_tools` 硬编码白名单与 MCP 动态不兼容

`AgentDefinition.allowed_tools: list[str]` 是静态字符串列表,定义时不知道将来会加载哪些 MCP 工具。

场景:用户给 Research Agent 加了一个 MCP 工具 `mcp__database__query`,但 Research 应该 read-only——这个 query 是读还是写?静态白名单管不了。

**修法 — capability-based 白名单**:

```python
# 工具声明时带 capability 标签:
class BaseTool:
    @property
    def capability_tags(self) -> set[str]:
        """能力标签: 'readonly', 'writable', 'destructive', 'network', 'mcp'"""
        return set()

# Agent 声明时用 capability 过滤:
class AgentDefinition:
    allowed_capabilities: set[str]  # 只能用带这些标签的工具
    denied_capabilities: set[str]   # 绝对不能用带这些标签的工具

RESEARCH = AgentDefinition(
    name="research",
    allowed_capabilities={"readonly"},
    denied_capabilities={"writable", "destructive"},
    ...
)

# ToolRegistry 过滤:
def filter_for_agent(self, agent_def: AgentDefinition) -> list[ToolDefinition]:
    return [
        t.to_definition() for t in self._tools.values()
        if t.capability_tags & agent_def.allowed_capabilities
        and not (t.capability_tags & agent_def.denied_capabilities)
    ]
```

MCP 工具注册时由 MCP Server 声明 capability tags(通过 MCP 协议的自定义 metadata,或 Prism 约定的 env 变量),如未声明则默认 `unknown`(Research Agent 看不到,General 可见)。

#### A4-2. Task 4.2 Fork 的"字节级 cache 一致"是伪命题

文档说"Fork 的 PromptAssembler 静态前缀与父 Agent 字节级一致(cache 共享)"。

问题:静态 prefix 包含 `session_guidance_section(agent_type, ...)`,不同 agent_type 这段不同,所以:
- 父 Agent = General,子 Agent = Research → static prefix 不同 → cache miss
- 父子都是 General → static prefix 相同 → cache hit

**字节级一致**只发生在 Fork **同类型** Agent 时。但常见 Fork 场景恰恰是 **General Fork Research 做探索**,cache miss。

**修法**:
1. 文档修正:明确"cache 共享仅在父子同 agent_type 时成立"
2. 架构优化:把 `session_guidance_section` 从静态部分移到动态部分,让静态 prefix 与 agent_type 无关

第 2 条更好,因为它让 cache hit 率真正提高。代价:session_guidance 本来希望被缓存(它相对稳定),现在每次请求重发——但 guidance 文本只有几百 tokens,不缓存损失很小,换来跨 agent_type fork cache 命中,收益更大。

#### A4-3. Task 4.3 Coordinator Plan 持久化缺失

Coordinator 模式按 Plan 顺序 fork step。如果子进程崩溃/Backend 重启,Plan 状态丢失,整个 Run 只能从头再来。

**修法**: 新增 `coordinator_plans` 表:
```sql
CREATE TABLE coordinator_plans (
    id UUIDv7 PK,
    run_id UUID FK → runs.id ON DELETE CASCADE,
    plan_json JSONB NOT NULL,  -- 完整 Plan
    current_step_index INT NOT NULL DEFAULT 0,
    step_results JSONB NOT NULL DEFAULT '[]',  -- 每 step 完成的结果
    status VARCHAR(20) NOT NULL DEFAULT 'running',  -- 'running' | 'completed' | 'failed' | 'paused'
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
```

Coordinator 在每个 step 开始/完成时 checkpoint,子进程重启后可从 current_step_index 恢复。需要 Backend 提供 `GET /runs/{id}/coordinator-plan` 和 `POST /runs/{id}/coordinator-plan/resume` 接口。

#### A4-4. Task 4.4 TaskRouter 正则匹配脆弱(AUDIT P2-4 已提,v3.1 修订不彻底)

v3.1 只加了英文关键词,但正则本身的脆弱性没解决:
- `"先.*然后.*最后"` 单行正则,跨行消息匹配失败
- `"帮我查"` 匹配 "帮我查代码" 被误判为 research
- 新增的 `PLUGIN_BUILDER_PATTERNS` 的 `r"(帮我|请).{0,10}(做|弄|写|建).{0,10}(插件|plugin|skill)"` 会匹配"帮我做这个 skill 的文档更新"(不是创建)

**质量优先修法**: 放弃纯正则,采用**双层路由**:
```
用户 prompt
    ├─ Level 1: 快速关键词匹配(当前实现,ms 级)
    │   ├─ 匹配到高置信模式 → 使用该路由
    │   └─ 未匹配或匹配置信度低 → Level 2
    └─ Level 2: LLM 分类(500ms 级)
        ├─ 使用 cheap Provider(Haiku / DeepSeek / Qwen-mini)
        ├─ 单次调用,max_tokens=50,返回 JSON {agent_type, confidence, reason}
        └─ 写入 audit_logs(路由决策可追溯)
```

Level 2 是质量改进——关键词永远覆盖不全用户表达,LLM 分类可以读懂"这个任务需要多步骤"这种语义。`cheap Provider` 可以用用户的 default Provider 的"mini" 型号(比如 DeepSeek-V3 作为主 Provider,DeepSeek-V3-mini 作为路由分类器)。

用户可以在 `providers.config` 里声明 `router_model_override` 字段,让用户选便宜型号;未配置则用 default provider。

### DOC-05: Plugin Ecosystem

#### A5-1. Task 5.1 Level 2 Skill 注入时机不清

"模型调用 Skill → 完整内容注入当前 turn 上下文" —— 但当前 turn 的 prompt 已经发出去了,"注入"只能影响下一 turn。

**修法**: 明文三步:

```
Turn N: 模型返回包含 Skill 触发意图(比如工具调用 `skill_invoke(name="financial-analysis")`)
Turn N 结束:
  - ToolExecutionPipeline 执行 skill_invoke 返回"已加载 Skill 内容"
  - PluginHost 在 messages[] 追加一条 user message:"以下是 financial-analysis Skill 的完整内容:\n\n{SKILL.md body}"
Turn N+1: 模型看到新增的 system context,按 Skill 指导执行
```

Skill 内容作为 user message 而非 system prompt(因为 system 只在每次请求时拼接,改了之后无法 cache)。作为 messages 里的一条 user 消息,保留在历史中,后续 turn 都能看到。

**Compaction 兼容性**: Skill message 可能很长(几千 tokens),需要特殊标记:

```python
@dataclass
class PrismMessage:
    role: Literal["user", "assistant"]
    content: list[ContentBlock]
    is_skill_context: bool = False  # ← 新增
    skill_name: str | None = None
```

Compaction 优先保留 `is_skill_context=True` 的消息(Skill 加载过,不能随便删),除非整个 Skill 的用处已经结束(可以 Tier 3 session memory 提取替代)。

#### A5-2. Task 5.2 MCP 卸载 + Skill 卸载的 cache 失效

v3.1 修复了加载时的 `invalidate_static_cache()`,但**卸载同样需要**。文档没写。

**修法**: PluginHost 的每个 mutation 方法(load / unload / enable / disable)都调用 `PromptAssembler.invalidate_static_cache()`。这是质量优先下的不变式:**任何改变工具列表的操作必须触发 cache 失效**,不能漏。

#### A5-3. Task 5.3 命名空间分隔符不统一

Plugin 用 `plugin:resource`(冒号),MCP 用 `mcp__server__tool`(双下划线)。代码里到处需要识别"这个工具名属于哪种"。

**修法**: 统一分隔符。选 `__`(双下划线)因为:
- CC 的 MCP 工具已用 `__`,兼容层需要保留
- `:` 在 URL 和 shell 命令里是保留字符,多处需要转义
- `__` 在合法标识符里允许,不冲突

Plugin 资源命名: `plugin__name__resource`(三段式),和 MCP 的 `mcp__server__tool` 结构一致。前缀 `plugin__` vs `mcp__` 区分来源。

---

## Part B — 架构级审视(跨 Task、跨文档)

### B-1. Task 间依赖不是"松耦合"是"顺序锁死"

AUDIT P1-7 提到"Task 间最小可行依赖",v3.1 画了依赖图:
```
3.1 → 3.2 → (3.3 + 3.4 并行) → 3.5 → 3.6
```

但实际上 Task 3.1 的代码里全是 `HARNESS_INTEGRATION_POINT` 注释,Task 3.2 要修改 `executor/engine/query_engine.py` 加 `__init__` 参数,Task 3.3 要修改 `executor/tools/pipeline.py` 加 Hook 集成点,Task 3.4 要修改 `executor/harness/lifecycle.py`... **每个后续 Task 都要改前面 Task 的代码**,实际是**紧耦合的顺序依赖**,不是"可并行"。

一旦 Task 3.1 的 `QueryEngine.run()` 接口设计不合理(比如 Middleware 钩点只有 2 个,就像 §A3-5 提到的),Task 3.2/3.3/3.4 全部返工。

**质量优先修法**: 在 Task 3.1 就把**完整的扩展点接口**设计好,后续 Task 只"填充实现"不"改接口":

```python
# Task 3.1 版的 QueryEngine(预留全部扩展点,而不是 HARNESS_INTEGRATION_POINT 注释):

class QueryEngine:
    def __init__(
        self,
        adapter: ModelAdapter,
        assembler: PromptAssembler,
        pipeline: ToolExecutionPipeline,
        budget: ContextBudgetManager,
        callback: BackendCallback,
        max_turns: int,
        # 扩展点 — Task 3.2-3.6 填充,Task 3.1 默认 noop
        middleware: MiddlewarePipeline | None = None,
        hook_system: HookSystem | None = None,
        permission_engine: PermissionEngine | None = None,
        compaction_pipeline: CompactionPipeline | None = None,
        config_manager: HarnessConfigManager | None = None,
    ):
        ...
```

Task 3.2-3.6 都是"注入具体组件",不改 QueryEngine 签名。这才是真正的"可并行"。

### B-2. 子进程崩溃的恢复策略全线缺失

横跨 DOC-03/04 的一个系统性空白:**没有考虑子进程崩溃**。

假设场景:
- 用户发起 Coordinator 任务,Plan 10 step,执行到第 4 step 子进程 OOM 被 kill
- Backend 怎么知道?怎么更新 runs.status?在队列里还有用户排队的消息,要 promote 吗?
- Plan 的前 3 step 结果保留了吗?(Batch 2 §A4-3 提了 coordinator_plans 表,但 DOC-04 里没)
- 用户看到什么?前端应该显示"任务失败"还是"任务被中断可恢复"?

**质量优先必须补的机制**:

1. **心跳机制**: 子进程每 5s 向 Redis `run:{run_id}:heartbeat` 写一次时间戳。Backend 有个后台任务每 10s 扫所有 `running` 状态的 run,心跳超过 30s 的标记为 `failed (crashed)`。
2. **Postmortem 回调**: Backend 发现 run 失败时,尝试读取 `/workspace/{run_id}/crash.log`(子进程退出前应写入),合并到 `runs.error_message`。
3. **用户可恢复**: 对于 Coordinator 类 Run,前端显示"任务被中断,已完成 3/10 steps,[继续] [放弃]"按钮。继续则从 coordinator_plans.current_step_index+1 开始新 Run。
4. **超时强 kill**: DOC-01 §3.3 提到 `RUN_TIMEOUT_SECONDS=600`,但 Coordinator 任务可能远超 10min。需要按 agent_type 分档(Batch 1 §3.7 已提)+ Plan 级 timeout(而不是整个 Run 级)。

### B-3. "Rippable 可撕裂架构"(P7)在 Task 3.6 的实现反而变复杂

P7 说"模型能力升级时,补偿性 middleware 可快速移除"。Task 3.6 想通过 HarnessConfigManager 实现运行时 toggle_middleware(name, enabled) —— 听起来符合 P7。

但实际上 P7 的**原意**是:"代码组织上,每个 middleware 独立模块,删除一个不影响其他"。Task 3.6 把它理解成"运行时可开关",这是**过度实现**。

**Build to Delete** 的真正姿势是:
- 每个 middleware 是独立文件
- 启动时从 yaml 读 `middlewares: {name: enabled, ...}`,注册进 pipeline
- 想移除某 middleware → 改 yaml + 重启服务
- 不需要运行时热开关(这是生产系统诉求,自己用的工具重启不是问题)

Task 3.6 的 `toggle_middleware()` 运行时开关加上"跨 CLI 子进程 Redis pub/sub 通知 + turn 粒度原子切换",复杂度爆炸却没带来真实价值。质量优先下建议删掉这个功能。

### B-4. Observability 数据采集覆盖面不足

虽然 Batch 1 §3.4 决定 Obs 前移到 Phase 1,但 DOC-03 的 Obs 设计只有:
- `ObservabilityMiddleware.post_turn` 上报 `turn_complete`(含 duration_ms, tool_call_count)
- `FeedbackCaptureMiddleware` 上报失败事件
- `runs.harness_summary` JSONB 里塞统计

漏掉:
- **每个 Middleware 自己的执行时长**(Middleware 是框架层,自身性能必须可见,否则"Middleware 堆多了慢了"根本查不到)
- **每个 Hook handler 的执行时长**(CC 的 command handler 可能慢,需要 P99 数据)
- **Prompt Cache 命中率**(Batch 1 §3.5 schema 已加 cache tokens 字段,但上报链路没接上)
- **每个 Guardrail 规则的触发次数和耗时**
- **4 级 Compaction 各级触发次数和耗时**

**修法**: Phase 1 的 Obs 采集清单明文写在 DOC-12(Batch 5 展开),但 DOC-03 里每个子系统都要有 **"每次调用记录 duration 到 metrics"** 的规范条款。Prometheus 风格:

```python
# 每个 Middleware 都应该这样:
async def pre_turn(self, ctx):
    start = time.perf_counter()
    try:
        await self._do_pre_turn(ctx)
    finally:
        duration = time.perf_counter() - start
        metrics.middleware_duration.labels(name=self.name, phase="pre_turn").observe(duration)
```

### B-5. Skill 安装后的"下次 Run 才生效"语义需要明说

Task 5.6 Agent Tool `skill_manage` 让 Agent 装 Skill。但装好的 Skill 什么时候被模型"看见"?
- 立即:PluginHost.load → 触发 static_cache.invalidate → **下一 turn** 的 prompt 里模型能看到新 Skill 的描述
- 下次 Session:Skill 信息持久化到 DB,当前 Run 不重载工具列表

文档没说哪种。两种差异很大:
- **立即生效**: 用户体验好("我刚装的插件马上能用"),但增加当前 Run 上下文占用,模型也可能被多出来的工具列表搞混
- **下次生效**: 干净,但用户要手动新开对话才用得上新 Skill

**质量优先**: 选"下次 Session 生效"。Agent 装 Skill 的使用场景本来就不高频,绝大多数用户是去 UI 商店装,不在对话里装。Agent Tool 的 `action=install` 完成后明确告诉用户"已安装,请新开会话后使用",简单明了,避免复杂边缘。

---

## Part C — v3.1 新增 Task 评估

### C-1. Task 3.6 Harness 动态更新

**定位**: 底层固化 + 垂类热更新,声称实现 P7 可撕裂原则。

**Part A/B 已指出的问题**: 
- 4 源合并 → 建议砍到 2 源
- 4 种变更路径 → 建议砍到 2 种
- turn 粒度原子切换机制 → 用 Config Version Counter
- Plugin 卸载一致性 → 用 disabled 标记而非立即变更
- ADR-030 的 `toggle_middleware` 运行时开关过度实现,建议删

**质量优先最终建议**:

```python
# 简化后的 HarnessConfigManager

class HarnessConfigManager:
    """
    两源合并:
    - platform_rules.py (代码级铁律,不可覆盖)
    - harness_config.yaml (运维配置,可 reload)
    
    Plugin 注入: 插件声明的 guardrail/permission 规则在 PluginHost 加载时
    merge 进 yaml 解析结果(插件是 yaml 的"扩展视图",不是独立源)
    
    热更新触发:
    - watchdog 监听 yaml 文件变更
    - PluginHost load/unload 时主动触发 reload
    - 不提供 HTTP API 改配置(自己用的工具,改 yaml + 自动 reload 足够)
    
    子进程感知:
    - Redis pub channel "harness:config_reload" 广播 version
    - 子进程每 turn 开始时对比 version,变了就 refetch
    """
    
    def __init__(self, yaml_path, platform_rules, redis, plugin_host):
        self._yaml_path = yaml_path
        self._platform_rules = platform_rules
        self._redis = redis
        self._plugin_host = plugin_host
        self._effective: EffectiveConfig | None = None
        self._version: int = 0
        self._setup_watchdog()
    
    def reload(self) -> EffectiveConfig:
        """合并 platform + yaml + plugin overrides(插件已加载的)"""
        yaml_config = self._parse_yaml(self._yaml_path)
        plugin_overrides = self._plugin_host.collect_harness_overrides()
        
        merged = self._merge(self._platform_rules, yaml_config, plugin_overrides)
        self._validate_no_platform_override(merged)  # 平台级规则不可被覆盖
        
        self._effective = merged
        self._version += 1
        self._redis.publish("harness:config_reload", str(self._version))
        return merged
    
    def get_effective_config(self, last_known_version: int = -1) -> EffectiveConfig:
        """子进程调用,带 version 查询避免不必要的锁竞争"""
        if last_known_version >= self._version:
            return self._effective  # 未变
        return self.reload() if self._effective is None else self._effective
```

API 端点:
- `GET /harness/config` 保留(查看当前有效配置 + source_trace)
- `POST /harness/config/reload` 保留(admin 强制 reload,比如改了 yaml 但 watchdog 没触发)
- `PATCH /harness/config` **删除**

### C-2. Task 4.5 PluginBuilder Agent

**定位**: 专用插件创建 Agent + Harness 双保险强制多轮对话。

**Part A/B 已指出的问题**:
- 硬编码 5 轮轮数门控违反 P5 配置驱动
- 把"次数"等同于"质量"
- GR-PLUGIN-CREATE-001 platform_level=True 过度刚性
- 检测逻辑脆弱(关键词匹配路径)

**质量优先最终建议**:

1. **轮数门控从 Middleware 改为 Prompt 引导**:
   ```python
   PLUGIN_BUILDER.behavior_constraints = [
       "插件创建是严肃过程,不可一键生成",
       "必须通过多轮对话充分收集需求",
       "进入设计阶段前,你必须自评:'是否已经清楚目标用户、核心场景、工具需求、边界情况、安全合规?' 任一未清楚继续提问"
   ]
   ```
   Agent 自己判断需求收集是否充分,而非系统硬卡轮数。

2. **Middleware 改为"需求完整度打分"**:
   ```python
   class PluginBuilderQualityGate(Middleware):
       """基于产物质量的门控,不是基于次数"""
       
       REQUIRED_SLOTS = [
           "target_users",      # 目标用户
           "core_scenarios",    # 核心场景  
           "tool_needs",        # 工具需求
           "boundary_cases",    # 边界情况
           "compliance",        # 合规要求
       ]
       
       async def pre_turn(self, ctx):
           if ctx.agent_type != "plugin_builder":
               return
           phase = ctx.metadata.get("plugin_build_phase", 1)
           
           if phase == 1:  # 需求收集阶段
               filled_slots = self._extract_filled_slots(ctx.messages)
               missing = [s for s in self.REQUIRED_SLOTS if s not in filled_slots]
               
               if missing:
                   ctx.inject_constraint(
                       f"以下需求维度尚未充分收集: {', '.join(missing)}。"
                       f"请在下一轮针对这些维度提问,每轮最多 5 个问题。"
                   )
                   # 不强制轮数,但 slots 填满才能进入 phase 2
               else:
                   ctx.metadata["ready_for_phase_2"] = True
   ```

   `_extract_filled_slots` 可以是规则提取(关键词)或 LLM 抽取(更准确)。这是基于**产物完整度**的质量门控,不是基于**次数**。

3. **GR-PLUGIN-CREATE-001 降级为可配置规则**:
   - 默认启用,写在 harness_config.yaml 的 `custom_rules` 段(而非 platform_rules.py)
   - `platform_level=False`,管理员可在特殊场景下 disable
   - 检测改为精确路径匹配:`path.startswith(".prism/plugins/")` 且 `path.endswith(("plugin.yaml", "SKILL.md"))`
   - 即使命中,也给用户选择"继续"(通过 ask 权限),不是 hard block

4. **REQUIRED_SLOTS 可配置**:
   yaml 里:
   ```yaml
   plugin_builder:
     required_slots:
       - target_users
       - core_scenarios
       - tool_needs
       - boundary_cases
       - compliance
     max_rounds_hint: 8  # 建议上限,提示 Agent 不要无限提问
   ```
   这样垂类插件可以定制 slot 清单(金融插件增加 regulatory 维度,医疗插件增加 privacy 维度)。

### C-3. Task 5.5 Skills Registry 多源聚合

**定位**: Local + npm + Manus + GitHub 四源搜索 + 安装。

**Part A 已指出的问题**:
- 4 源语义不清(尤其 npm 的 Skill 解包规则、Manus API 真实性)
- Local 双目录(`.skills/` + `.prism/skills/`)职责模糊

**质量优先最终建议**:

1. **Phase 1 只上 2 源**: Local + GitHub
   - Local: 用户手动放置或 UI/CLI 已安装,目录统一为 `.prism/skills/`
   - GitHub: 使用 `git clone --depth 1`(而非 GitHub API,GH API 有 rate limit)
2. **Phase 2 根据真实需求加源**:
   - 有用户说"我有一个私有 npm registry 装 Skills" → 加 npm
   - Manus 真的出了 Skills Market API → 加 Manus
3. **Local 目录统一**:
   - `.prism/skills/{skill_name}/` 是唯一 Local 路径
   - 每个 skill 目录下 `install_info.json` 记录 `source`(`manual` / `github` / `npm`...)、`installed_at`、`source_url`
   - CC 兼容的 `.skills/` 目录通过 symlink 到 `.prism/skills/`(或扫描时合并)
4. **去重策略明文**:
   ```
   搜索结果按 (name + source) 唯一
   同 name 不同 source 都显示,用户看到"有 3 个叫 web-researcher 的:
     - @manus/web-researcher (来自 Manus 官方,1.2k 装机)
     - github:obra/web-researcher (来自 GitHub,Star 3.4k)
     - npm:@community/web-researcher (来自 npm,最后更新 6 个月前)"
   用户自己选装哪个
   ```
   不偷偷"去重",让用户做决策。

### C-4. Task 5.6 Skills CLI & Agent Tool

**定位**: `prism skills` CLI + `skill_manage` Agent Tool。

**Part A 已指出的问题**:
- Agent 自装 Skill 扩大安全面
- General 和 PluginBuilder 可用,但 PluginBuilder 装 Skill 的场景不自然

**质量优先最终建议**:

1. **Agent Tool 砍到只保留 `search`**:
   - Agent 能搜 Skill 是有用的(比如用户问"有没有金融 Skill?" Agent 搜一下报告)
   - Install/uninstall/update 一律走 UI 或 CLI,人执行
   - `skill_manage` 改名 `skill_search`,input_schema 只保留 search 相关字段
2. **CLI 正交**: `prism skills` CLI 完整保留,作为运维/自动化入口
3. **安全审计**: 即使是 search,每次调用也写 audit_logs,记录 user_id + run_id + query。防止 Agent 被用户诱导搜某些敏感关键词(这是质量优先下的偏执,但多一层保险)

### C-5. Task 5.7 CC 插件格式兼容层

**定位**: CCPluginAdapter 统一检测 + 转换 CC plugin.json / Prism plugin.yaml。

**Part A 已指出的问题**:
- `export_to_cc()` 静默丢弃 prism 扩展字段

**质量优先最终建议**:

1. **export_to_cc 返回 ConversionReport**:
   ```python
   @dataclass
   class ConversionReport:
       output_path: str
       dropped_fields: list[str]  # 丢失的 prism 扩展字段
       warnings: list[str]        # 警告(如 harness_overrides 无法映射)
       cc_compatible: bool        # 导出结果是否通过 CC 格式校验
   
   def export_to_cc(self, config, output_dir) -> ConversionReport:
       ...
   ```
   CLI `prism plugin export --to-cc` 执行后打印 report,用户可见丢失了什么。
2. **plugin.yaml schema 严格化**:
   - 提供 JSON Schema 定义 plugin.yaml
   - 加载时验证,不符合 schema 报错不加载
   - 这避免了 plugin.yaml 随意扩展字段导致的 CC-Prism 互操作陷阱
3. **`prism plugin validate --cc-compat` 命令**:
   - 检查一个 Prism 插件转到 CC 时会丢哪些字段
   - 输出报告让开发者在发布前知情
4. **版本兼容矩阵**:
   - plugin.yaml 加 `compat: {cc_min_version: "1.0", prism_min_version: "2.0"}`
   - 加载时校验当前 CC/Prism 版本是否满足
5. **CC 原生格式 `plugin.json` 的 Schema 随 CC 版本变化**:
   - Prism 的 CCPluginAdapter 必须声明"支持 CC plugin.json schema 版本 X.Y"
   - 遇到未知字段时 warn 但不 fail
   - 每次 CC 泄露新版本(比如 v2.2.x 时),Prism 发 patch release 更新 adapter

---

## 总结 & 对下一批的影响

### Batch 2 发现的问题总量

- **实现级**: 22 项(Part A)
- **架构级**: 5 项(Part B)
- **新 Task 做法偏差**: 每个新 Task 都有 2-4 项修订(Part C)

### 对 Batch 3 (Backend) 的影响

- **B2-1 permission="ask" 反向通信协议**必须在 DOC-07 Backend 里实现,新增 `POST /sessions/{id}/permission-answer` 端点 + Redis BLPOP 约定
- **B-2 子进程崩溃恢复**需要 Backend 心跳监控任务 + `coordinator_plans` 表
- **A4-3 coordinator_plans 表** 加进 DOC-01 schema + DOC-07 Service
- **回调接口重构**(Batch 1 决策 D3 方案 A)要在 DOC-07 具体设计

### 对 Batch 4 (Frontend) 的影响

- **permission_ask 事件** 前端 UI 弹窗设计(Batch 4 会专门审)
- **并行 tool_use 卡片**呈现(A3-1)
- **Coordinator Plan 进度可视化**(A4-3)
- **Compaction 进行中提示**(A3-8)

### 对 Batch 5 (Obs) 的影响

- **B-4 Obs 数据覆盖面**的完整指标清单在 DOC-12 定义
- **User Memory 写入时机**涉及 LLM 调用,成本追踪要覆盖到

---

> **下一步**: 进 Batch 3(Backend DOC-06/07/08/09 + Task 9.3)
> **本 Batch 覆盖**: DOC-03 (80KB) + DOC-04 (56KB) + DOC-05 (63KB) + v3.1 对应部分 = ~230KB
