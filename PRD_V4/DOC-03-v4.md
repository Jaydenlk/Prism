# Prism 棱镜 v2 — Agent Runtime & Harness Core (DOC-03)

> **文档编号**: DOC-03
> **版本**: 4.0(Review 修订版)
> **日期**: 2026-04-18
> **性质**: 实现文档 — Prism 最核心的两层:Harness Runtime(Layer 3)+ Agent Engine Core(Layer 4)
> **前置依赖**: DOC-00 v4, DOC-01 v4, DOC-02 v4(Task 2.1-2.4 全部完成)
> **Phase**: 1(Agent 核心)
> **Task 数**: 6
> **v4 变更摘要**: 基于 5 轮 review 修订,35 处精确修补(详见文末 §附录 A)。原文结构、Task 编号、Part A/B 格式 99% 保留。核心修订:回调协议方案 A 双通道(Redis 直通 + HTTP 带重试)、工具并行 gather、心跳子进程、permission ask Redis BLPOP 协议、Middleware 4 钩点升级、HookDecision 11 字段、Compaction 4 级按回合组原子裁剪、Harness 配置 2 源化并删除 PATCH 运行时 API。ADR 编号从 ADR-020 接续至 ADR-030。

---

## 目录

1. [Task 3.1: TAOR 主循环与 ToolExecutionPipeline](#task-31-taor-主循环与-toolexecutionpipeline)
2. [Task 3.2: Middleware Pipeline](#task-32-middleware-pipeline)
3. [Task 3.3: Hook System 与 Permission Engine](#task-33-hook-system-与-permission-engine)
4. [Task 3.4: Guardrails Engine 与 Feedback Loop](#task-34-guardrails-engine-与-feedback-loop)
5. [Task 3.5: 4 级 Compaction Pipeline 与 6 层 Memory](#task-35-4-级-compaction-pipeline-与-6-层-memory)
6. [Task 3.6: Harness 垂类配置动态更新](#task-36-harness-垂类配置动态更新)

---

## Task 间最小可行依赖

```
Task 3.1 (TAOR 主循环)
  └─► Task 3.2 (Middleware Pipeline) — 依赖 TAOR 的 pre_turn/post_turn 钩点
        └─► Task 3.3 (Hook System) — 依赖 Middleware 的事件分发
        └─► Task 3.4 (Guardrails) — 依赖 Middleware 的 pre/post 拦截点
              └─► Task 3.5 (Compaction) — 依赖 Guardrails 的上下文评估
                    └─► Task 3.6 (Harness 动态更新) — 依赖所有子系统的运行时接口
```

> 最小可行路径：3.1 → 3.2 → (3.3 + 3.4 并行) → 3.5 → 3.6

---

## Task 3.1: TAOR 主循环与 ToolExecutionPipeline

### Part A — 设计与解释

#### 问题陈述

Prism v2 的核心运行时是一个 Model-Driven 的自主循环——模型决定下一步做什么，Runtime 只负责执行和治理。CC 源码的 `query.ts` 揭示了这种"哑循环"模式：`while(true)` 循环中，模型返回 `tool_use` 就执行工具并把结果追加到 messages，返回 `end_turn` 就退出。所有智能在模型端，所有治理在 Harness 端。

Prism v1 把这个能力外包给 `claude_agent_sdk`，导致无法控制循环行为、无法插入 Hook、无法做上下文管理。现在需要自研这个核心循环。

#### CC 架构映射

| CC 组件 | Prism 对应 | 说明 |
|---------|-----------|------|
| `query.ts` while(true) | `QueryEngine.run()` | TAOR 主循环 |
| `QueryEngine.ts` submitMessage | `QueryEngine._submit_turn()` | 单轮提交 |
| `Tool.ts` + runTools() | `ToolExecutionPipeline` | 工具执行 Pipeline |
| `src/tools/` 45+ tools | `executor/tools/builtin/` | 内置工具 |
| stop_reason 判断 | `_should_continue()` | 循环终止条件 |
| maxTurns cap | `MAX_TURNS_PER_RUN` | 防失控上限 |

#### 数据流

```
用户 Prompt
    ↓
QueryEngine.run()
    ↓
┌─────────── TAOR Loop ──────────────────────────────────┐
│ 1. PromptAssembler.build() → system_prompt              │
│ 2. ModelAdapter.stream(messages, system_prompt, tools)   │
│ 3. 解析 StreamEvent：                                    │
│    ├─ text_delta → 累积文本，回调 Backend                 │
│    ├─ tool_use_start/delta/end → 收集工具调用             │
│    └─ message_end → 获取 stop_reason + usage             │
│ 4. 如果 stop_reason == "tool_use"：                      │
│    ├─ 对每个 ToolUseBlock：                               │
│    │   ├─ [Harness] PreToolUse Hook                      │
│    │   ├─ [Harness] PermissionEngine.check()             │
│    │   ├─ ToolExecutionPipeline.execute()                │
│    │   ├─ [Harness] PostToolUse Hook                     │
│    │   └─ ContextBudgetManager.truncate_tool_result()    │
│    ├─ 将 ToolResultBlock 追加到 messages                  │
│    ├─ 回调 Backend（tool_start / tool_end）               │
│    ├─ [Harness] CompactionCheck                          │
│    └─ turn_count++ → 继续循环                             │
│ 5. 如果 stop_reason == "end_turn" 或 "max_tokens"：      │
│    └─ 退出循环                                            │
│ 6. 如果 turn_count >= MAX_TURNS_PER_RUN：                │
│    └─ 强制退出，回调 run_error("max turns exceeded")      │
└─────────────────────────────────────────────────────────┘
```

#### 验收标准(v4 扩展)

- QueryEngine 能驱动完整的对话循环(纯文本 + 工具调用 + 多轮)
- 工具调用走 ToolExecutionPipeline(Schema 校验 → 执行 → 结果截断)
- **v4:同一轮内的多个工具通过 `asyncio.gather` 并行执行**(无依赖时),验证并行时序:两个 sleep 5s 的工具总耗时 <10s
- 每轮通过**双通道回调**向 Backend 上报事件:高频 text_delta/tool_use_delta 走 Redis PUBLISH 直通 → SSE(亚秒级);关键事件 tool_start/tool_end/message_complete/run_complete/run_error 走 HTTP POST 带 3 次指数退避重试,失败入 dead letter queue
- **v4:子进程启动时在 `asyncio.create_task` 中启动心跳 writer**,每 5s 向 `harness:heartbeat:{run_id}` Redis key 写 TTL 60s 的当前时间戳;Backend HeartbeatMonitor 扫描超 30s 无更新 → 标记 crashed
- **v4:permission ask 通过 Redis BLPOP 阻塞等待用户回答**,超时(默认 300s)默认 deny(fail-safe)
- **v4:MAX_TURNS_PER_RUN 按 agent_type 分档**:chat=50 / explore=30 / build=100 / coordinator=200 / verifier=20 / plugin_builder=40
- turn_count 达到上限时强制退出,回调 run_error
- stop_reason 为 "end_turn" 时正常退出并回调 run_complete
- 模型返回错误时回调 run_error
- **v4:HTTP 关键事件回调均携带 `X-Callback-Secret` 头(CALLBACK_SECRET,独立于 JWT_SECRET / ENCRYPTION_KEY)**,Backend 强制校验

#### 设计决策(ADR)

- **ADR-020(Harness 单实例)**:Harness Runtime 只在子进程内实例化一次,Backend 进程不持有任何 Harness 对象。Backend 只是事件路由/持久化层。来源:Batch 2 §A3-1, Master M1。
- **ADR-021(工具并行 gather)**:同一轮内的多个 ToolUseBlock 若无声明依赖,使用 `asyncio.gather` 并发执行,结果按 block 顺序收集为单条 user message 的 tool_result 列表(canonical Anthropic 语义)。依赖检测目前保守实现为"全部并行",DOC-04 Coordinator 模式下可精细化。来源:PDF 补丁, Batch 2 §A3-1。
- **ADR-022(Redis 直通)**:text_delta 和 tool_use_delta 从子进程通过 `redis.publish("run:{run_id}:stream", event)` 直接发布,Backend SSE Manager 订阅 channel 立即 forward 给前端,不走 HTTP。每 token 不再穿越 Backend 路由层。关键事件(非高频)仍走 HTTP。来源:Master M2, Batch 1 §3.3 D3。
- **ADR-023(心跳机制)**:子进程启动时 `asyncio.create_task(heartbeat_writer())`,每 5s `SETEX harness:heartbeat:{run_id} 60 {now}`;Backend HeartbeatMonitor 每 10s `SCAN harness:heartbeat:*`,超 30s 无更新即标记 Run crashed 并 promote 队列。来源:Batch 2 §B-2, Batch 3 B3-2。
- **ADR-024(MAX_TURNS 按 agent_type 分档)**:不同 agent_type 的循环上限差异巨大,统一 50 的上限要么压死 Coordinator 要么放过 runaway。配置通过 DOC-02 v4 Task 2.4 的 agent_type 路由决定。来源:Batch 2 §A3-1, PDF 补丁。

#### v4 数据流(修订)

```
用户 Prompt
    ↓
QueryEngine.run()
    ↓
┌─────────── TAOR Loop ──────────────────────────────────┐
│ [pre_turn Middleware 4 钩点 #1]                          │
│                                                          │
│ 1. PromptAssembler.build(agent_type) → system_prompt    │
│ 2. ModelAdapter.stream(messages, system_prompt, tools,  │
│                        session_id=run_context.session_id)│
│ 3. 解析 StreamEvent:                                     │
│    ├─ text_delta → 累积文本,Redis PUBLISH 直通 → SSE     │
│    ├─ tool_use_start/delta → 收集工具调用,Redis 直通     │
│    └─ message_end → 获取 stop_reason + usage(cache tokens)│
│                                                          │
│ [message_complete HTTP 回调带重试,持久化 messages 表]    │
│                                                          │
│ 4. 如果 stop_reason == "tool_use":                       │
│    ├─ 对所有 ToolUseBlock:                               │
│    │   ├─ [Middleware pre_tool_use #2]                   │
│    │   ├─ [HookSystem PreToolUse] → HookDecision 合并    │
│    │   ├─ [PermissionEngine.check()]                     │
│    │   │   ├─ allow → 继续                                │
│    │   │   ├─ deny → 返回 tool_result(is_error=True)     │
│    │   │   └─ ask → PermissionAskProtocol.ask()          │
│    │   │        ├─ 发 permission_ask 回调(HTTP)          │
│    │   │        ├─ Redis BLPOP `perm_answer:{req_id}`    │
│    │   │        ├─ 超时 300s → fail-safe deny            │
│    │   │        └─ answer → allow / deny                 │
│    │   ├─ asyncio.gather 并行 ToolExecutionPipeline      │
│    │   ├─ [HookSystem PostToolUse]                       │
│    │   ├─ [Middleware post_tool_use #3]                  │
│    │   └─ ContextBudget.truncate_tool_result()           │
│    ├─ 追加单条 user message(role=user,content=tool_result*)│
│    ├─ 回调 Backend(tool_start / tool_end HTTP 带重试)    │
│    ├─ [CompactionPipeline.maybe_compact() 4 级渐进]      │
│    ├─ [Middleware post_turn #4]                          │
│    └─ turn_count++ → 继续循环                             │
│                                                          │
│ 5. 如果 stop_reason == "end_turn" 或 "max_tokens":       │
│    └─ 退出循环,回调 run_complete(HTTP 带重试)           │
│                                                          │
│ 6. 如果 turn_count >= MAX_TURNS[agent_type]:             │
│    └─ 强制退出,回调 run_error("max turns exceeded")      │
│                                                          │
└─────────────────────────────────────────────────────────┘
         ↑                                          │
    (并行)│                                          ↓
┌─────────────────────────┐              ┌─────────────────┐
│ heartbeat_writer task   │              │ BackendCallback │
│ 每 5s SETEX             │              │ (HTTP+Redis 双通道)│
│ harness:heartbeat:*     │              └─────────────────┘
└─────────────────────────┘
```

---

### Part B — Claude Code 执行 Prompt

> **v4 Observability 采集要求(本 Task 所有代码适用)**:
> - 所有 logger 用 `structlog.get_logger()`,事件名 `{domain}.{action}`(如 `harness.tool.invoked`, `harness.callback.failed`)
> - 业务关键路径(工具调用/回调/心跳/Compaction)必须有 Prometheus counter + histogram
> - 跨进程操作(subprocess 启动/模型请求/工具执行)必须有 OTel trace span
> - 详细规范见 DOC-12 Task 12.4/12.5/12.6

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的核心运行时——TAOR 主循环和工具执行 Pipeline。DOC-02 v4 的全部 Task 已完成(项目骨架、双协议 Driver、Provider 管理、Prompt 装配引擎)。本 Task 是 Prism 的心脏。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

1. DOC-02 全部 Task 完成
2. `executor/adapters/` 下 AnthropicDriver / OpenAIDriver 可用
3. `executor/engine/prompt_assembler.py` 和 `context_budget.py` 可用
4. `executor/adapters/provider_manager.py` 可用

## 要创建的文件

```
executor/
├── __main__.py                    # 更新：Agent 执行入口完整实现
├── engine/
│   └── query_engine.py            # TAOR 主循环
├── tools/
│   ├── base.py                    # Tool 抽象基类（声明式 Schema）
│   ├── pipeline.py                # ToolExecutionPipeline
│   ├── registry.py                # 工具注册表
│   └── builtin/
│       ├── __init__.py
│       └── echo.py                # 最小测试工具（echo 输入内容）
└── callbacks/
    └── backend_callback.py        # 回调 Backend 内部接口
```

## 实现规范

### 1. executor/tools/base.py — Tool 抽象基类

```python
"""
工具基类 — 声明式 Schema 定义

每个工具声明：
- name: 工具名称（全局唯一，格式 "{namespace}__{tool_name}" 或 "{tool_name}"）
- description: 给模型看的描述
- input_schema: JSON Schema（模型生成的参数必须符合此 Schema）
- execute(): 实际执行逻辑
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class ToolResult:
    """工具执行结果"""
    content: str          # 输出内容（纯文本或 JSON 字符串）
    is_error: bool = False

class BaseTool(ABC):
    """工具抽象基类"""
    
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @property
    @abstractmethod
    def description(self) -> str: ...
    
    @property
    @abstractmethod
    def input_schema(self) -> dict: ...
    
    @abstractmethod
    async def execute(self, tool_input: dict) -> ToolResult:
        """执行工具。子类实现具体逻辑。"""
        ...
    
    def to_definition(self) -> "ToolDefinition":
        """转为传给模型的 ToolDefinition"""
        from executor.adapters.base import ToolDefinition
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
        )
```

### 2. executor/tools/registry.py — 工具注册表

```python
"""
工具注册表

职责：
- 注册内置工具和 MCP 工具
- 按名称查找工具实例
- 返回所有工具的 ToolDefinition 列表（供 PromptAssembler 使用）
"""

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
    
    def register(self, tool: BaseTool) -> None:
        """注册工具。名称重复则覆盖（MCP 工具可覆盖内置同名工具）。"""
        self._tools[tool.name] = tool
    
    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)
    
    def list_definitions(self) -> list["ToolDefinition"]:
        """返回所有工具的 ToolDefinition，按名称排序（cache 友好）"""
        return sorted(
            [t.to_definition() for t in self._tools.values()],
            key=lambda d: d.name,
        )
```

### 3. executor/tools/pipeline.py — ToolExecutionPipeline

```python
"""
工具执行 Pipeline

完整链路（对标 CC 的 Tool.ts + runTools()）：
1. 从 ToolRegistry 查找工具
2. JSON Schema 校验 input
3. [预留] PreToolUse Hook 拦截点（Task 3.3 实现）
4. [预留] PermissionEngine 决策点（Task 3.3 实现）
5. 执行 tool.execute()
6. ContextBudgetManager.truncate_tool_result() 截断超长结果
7. [预留] PostToolUse Hook 拦截点（Task 3.3 实现）
8. 返回 ToolResultBlock

本 Task 先实现 1-2-5-6-8 的骨架链路，Hook 和 Permission 的集成点用
明确的注释标记（# HARNESS_INTEGRATION_POINT），Task 3.3 填充。
"""

import json
import jsonschema  # 需要加入 requirements.txt

class ToolExecutionPipeline:
    def __init__(
        self,
        registry: ToolRegistry,
        context_budget: ContextBudgetManager,
    ):
        self._registry = registry
        self._budget = context_budget
        # HARNESS_INTEGRATION_POINT: hook_system 和 permission_engine 在 Task 3.3 注入
        self._hook_system = None
        self._permission_engine = None
    
    async def execute(self, tool_name: str, tool_input: dict, tool_use_id: str) -> ToolResultBlock:
        """
        执行单个工具调用。
        返回 ToolResultBlock（直接追加到 messages）。
        """
        # 1. 查找工具
        tool = self._registry.get(tool_name)
        if tool is None:
            return ToolResultBlock(
                tool_use_id=tool_use_id,
                content=f"工具 '{tool_name}' 不存在",
                is_error=True,
            )
        
        # 2. Schema 校验
        try:
            jsonschema.validate(instance=tool_input, schema=tool.input_schema)
        except jsonschema.ValidationError as e:
            return ToolResultBlock(
                tool_use_id=tool_use_id,
                content=f"参数校验失败: {e.message}",
                is_error=True,
            )
        
        # 3. HARNESS_INTEGRATION_POINT: PreToolUse Hook
        # 4. HARNESS_INTEGRATION_POINT: PermissionEngine.check()
        
        # 5. 执行
        try:
            result = await tool.execute(tool_input)
        except Exception as e:
            return ToolResultBlock(
                tool_use_id=tool_use_id,
                content=f"工具执行异常: {str(e)}",
                is_error=True,
            )
        
        # 6. 截断超长结果
        truncated_content = self._budget.truncate_tool_result(result.content)
        
        # 7. HARNESS_INTEGRATION_POINT: PostToolUse Hook
        
        # 8. 返回
        return ToolResultBlock(
            tool_use_id=tool_use_id,
            content=truncated_content,
            is_error=result.is_error,
        )
```

### 4. executor/callbacks/backend_callback.py(v4:双通道方案 A)

```python
"""
Backend 回调客户端(v4 双通道)

方案 A:
- 高频事件(text_delta, tool_use_delta)→ Redis PUBLISH 直通,Backend SSE Manager
  订阅 channel 立即 forward 给前端。不走 HTTP,避免每 token 穿越 Backend 路由层。
- 关键事件(tool_start/tool_end/message_complete/run_complete/run_error/permission_ask/
  harness_event/coordinator_plan_update)→ HTTP POST 到 Backend 内部接口,带 3 次
  指数退避重试;全部重试失败后入 Redis dead letter queue `callback:dlq:{run_id}`。
- HTTP 请求携带 X-Callback-Secret 头(CALLBACK_SECRET,独立于 JWT_SECRET 和
  ENCRYPTION_KEY,启动时 main.py 校验三者不同)。

协议定义:DOC-01 v4 §9.1(回调协议)+ §9.2(Redis namespace 规范)
"""

import asyncio
import json
from datetime import datetime, timezone
import httpx
import redis.asyncio as redis_async
import structlog

logger = structlog.get_logger()

HTTP_MAX_RETRIES = 3
HTTP_TIMEOUT_SECONDS = 10.0
HTTP_BACKOFF_BASE = 0.5  # 0.5s, 1.0s, 2.0s

class BackendCallback:
    def __init__(
        self,
        callback_url: str,
        callback_secret: str,
        run_id: str,
        session_id: str,
        redis_url: str,
    ):
        self._url = callback_url
        self._secret = callback_secret
        self._run_id = run_id
        self._session_id = session_id
        self._client = httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS)
        self._redis = redis_async.from_url(redis_url, decode_responses=True)
        self._stream_channel = f"run:{run_id}:stream"

    # -------- 高频路径(Redis 直通)--------

    async def text_delta(self, text: str, message_id: str) -> None:
        """高频事件:走 Redis PUBLISH,Backend SSE 订阅立即 forward"""
        await self._redis.publish(self._stream_channel, json.dumps({
            "type": "text_delta",
            "run_id": self._run_id,
            "session_id": self._session_id,
            "message_id": message_id,
            "text": text,
            "ts": datetime.now(timezone.utc).isoformat(),
        }))

    async def tool_use_delta(self, tool_use_id: str, partial_json: str) -> None:
        """高频事件:工具入参 JSON 流式增量"""
        await self._redis.publish(self._stream_channel, json.dumps({
            "type": "tool_use_delta",
            "run_id": self._run_id,
            "session_id": self._session_id,
            "tool_use_id": tool_use_id,
            "partial_json": partial_json,
            "ts": datetime.now(timezone.utc).isoformat(),
        }))

    # -------- 关键事件(HTTP 带重试)--------

    async def _http_post_with_retry(self, event_type: str, data: dict) -> None:
        """POST 到 Backend,3 次指数退避;全失败入 DLQ"""
        payload = {
            "run_id": self._run_id,
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for attempt in range(HTTP_MAX_RETRIES):
            try:
                resp = await self._client.post(
                    self._url,
                    json=payload,
                    headers={"X-Callback-Secret": self._secret},
                )
                if resp.status_code < 500:
                    # 成功或客户端错误(不该重试)
                    if resp.status_code >= 400:
                        logger.warning("callback.client_error",
                                       event_type=event_type,
                                       status=resp.status_code,
                                       body=resp.text[:500])
                    return
                logger.warning("callback.server_error",
                               event_type=event_type,
                               status=resp.status_code,
                               attempt=attempt + 1)
            except Exception as e:
                logger.warning("callback.exception",
                               event_type=event_type,
                               error=str(e),
                               attempt=attempt + 1)
            await asyncio.sleep(HTTP_BACKOFF_BASE * (2 ** attempt))

        # 全部失败 → dead letter queue
        logger.error("callback.dlq",
                     event_type=event_type,
                     run_id=self._run_id)
        await self._redis.rpush(
            f"callback:dlq:{self._run_id}",
            json.dumps(payload),
        )

    async def message_complete(self, role: str, content: list, sequence_no_hint: int | None = None) -> None:
        await self._http_post_with_retry("message_complete", {
            "role": role,
            "content": content,
            "sequence_no_hint": sequence_no_hint,
        })

    async def tool_start(self, tool_use_id: str, tool_name: str, tool_input: dict) -> None:
        await self._http_post_with_retry("tool_start", {
            "tool_use_id": tool_use_id,
            "tool_name": tool_name,
            "input": tool_input,
        })

    async def tool_end(
        self,
        tool_use_id: str,
        output: str,
        is_error: bool,
        duration_ms: int,
    ) -> None:
        await self._http_post_with_retry("tool_end", {
            "tool_use_id": tool_use_id,
            "output": output[:500],  # 回调 preview,完整内容走 messages 表
            "is_error": is_error,
            "duration_ms": duration_ms,
        })

    async def harness_event(self, event_subtype: str, detail: dict) -> None:
        await self._http_post_with_retry("harness_event", {
            "type": event_subtype,
            "detail": detail,
        })

    async def permission_ask(
        self,
        request_id: str,
        tool_name: str,
        tool_input: dict,
        reason: str,
        timeout_at: str,
    ) -> None:
        await self._http_post_with_retry("permission_ask", {
            "request_id": request_id,
            "tool_name": tool_name,
            "tool_input": tool_input,
            "reason": reason,
            "timeout_at": timeout_at,
        })

    async def compaction_in_progress(self, tier: int, before_tokens: int, after_tokens: int) -> None:
        await self._http_post_with_retry("harness_event", {
            "type": "compaction",
            "detail": {
                "tier": tier,
                "before_tokens": before_tokens,
                "after_tokens": after_tokens,
            },
        })

    async def coordinator_plan_update(self, **kwargs) -> None:
        await self._http_post_with_retry("coordinator_plan_update", kwargs)

    async def run_complete(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_hit_tokens: int,
        cache_creation_tokens: int,
        turn_count: int,
    ) -> None:
        await self._http_post_with_retry("run_complete", {
            "run_id": self._run_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_hit_tokens": cache_hit_tokens,
            "cache_creation_tokens": cache_creation_tokens,
            "turn_count": turn_count,
        })

    async def run_error(self, error: str) -> None:
        await self._http_post_with_retry("run_error", {
            "run_id": self._run_id,
            "error": error,
        })

    async def close(self) -> None:
        await self._client.aclose()
        await self._redis.aclose()
```

### 5. executor/engine/query_engine.py — TAOR 主循环

```python
"""
TAOR 主循环 — Prism v2 的心脏

对标 CC 的 query.ts while(true) 循环。
Model-Driven：模型决定做什么，Runtime 只负责执行和治理。

生命周期：
1. 初始化（从 DB 读取配置，构建 PromptAssembler、ToolRegistry、Pipeline）
2. run()：进入 TAOR 循环
3. 每轮：Prompt 组装 → API 调用 → 解析响应 → 工具执行 → 回调 → Compaction 检查
4. 退出：end_turn / max_tokens / max_turns / 异常
"""

class QueryEngine:
    def __init__(
        self,
        adapter: ModelAdapter,
        assembler: PromptAssembler,
        pipeline: ToolExecutionPipeline,
        budget: ContextBudgetManager,
        callback: BackendCallback,
        max_turns: int,
        # HARNESS_INTEGRATION_POINT: middleware_pipeline 在 Task 3.2 注入
    ):
        self._adapter = adapter
        self._assembler = assembler
        self._pipeline = pipeline
        self._budget = budget
        self._callback = callback
        self._max_turns = max_turns
        self._messages: list[PrismMessage] = []
        self._turn_count = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
    
    async def run(self, user_prompt: str) -> None:
        """
        执行完整的 TAOR 循环。
        
        这是主入口，被 __main__.py 调用。
        """
        # 初始消息
        self._messages.append(PrismMessage(
            role="user",
            content=[TextBlock(text=user_prompt)],
        ))
        
        try:
            while True:
                # 检查 turn 上限
                if self._turn_count >= self._max_turns:
                    await self._callback.run_error(f"达到最大循环次数 ({self._max_turns})")
                    return
                
                # HARNESS_INTEGRATION_POINT: MiddlewarePipeline.pre_turn() 在 Task 3.2 注入
                
                # 构造 System Prompt
                system_prompt = self._assembler.build(language="zh-CN")
                
                # 调用模型
                stop_reason, tool_use_blocks = await self._process_turn(system_prompt)
                self._turn_count += 1
                
                # 判断是否继续
                if stop_reason == "end_turn" or stop_reason == "max_tokens":
                    break
                
                if stop_reason == "tool_use" and tool_use_blocks:
                    # 执行工具
                    await self._execute_tools(tool_use_blocks)
                    
                    # Compaction 检查
                    if self._budget.should_compress(self._messages, system_prompt):
                        self._messages = self._budget.compress_history(self._messages)
                        await self._callback.harness_event("compaction", {
                            "tier": 0,
                            "messages_after": len(self._messages),
                        })
                    
                    # HARNESS_INTEGRATION_POINT: MiddlewarePipeline.post_turn() 在 Task 3.2 注入
                    continue
                
                # 未知 stop_reason
                break
            
            # 正常完成
            await self._callback.run_complete(
                input_tokens=self._total_input_tokens,
                output_tokens=self._total_output_tokens,
                turn_count=self._turn_count,
            )
        except Exception as e:
            await self._callback.run_error(str(e))
            raise
    
    async def _process_turn(self, system_prompt: str) -> tuple[str, list[ToolUseBlock]]:
        """
        执行单轮模型调用，解析流式响应。
        返回 (stop_reason, tool_use_blocks)。
        """
        tool_definitions = self._pipeline._registry.list_definitions()
        
        accumulated_text = ""
        tool_use_blocks: list[ToolUseBlock] = []
        current_tool_id = ""
        current_tool_name = ""
        current_tool_input_json = ""
        stop_reason = ""
        
        # v4:stream() 接受 session_id 参数,Adapter 内部在 text_delta/tool_use_delta 时
        # 可选择把事件直接通过 Redis 直通发给前端(Anthropic Driver 已实现,见 DOC-02 v4 Task 2.2)
        # 若 Adapter 已做 Redis 直通,这里就不再 double-publish
        message_id = str(uuid7.create())
        async for event in self._adapter.stream(
            messages=self._messages,
            system_prompt=system_prompt,
            tools=tool_definitions if tool_definitions else None,
            session_id=self._run_context.session_id,
        ):
            if event.type == "text_delta":
                accumulated_text += event.text
                # v4:Adapter 未做直通时,在此直通(兜底);Adapter 已做则这里 no-op
                if not self._adapter.capabilities.redis_passthrough:
                    await self._callback.text_delta(event.text, message_id=message_id)

            elif event.type == "tool_use_start":
                current_tool_id = event.tool_use_id
                current_tool_name = event.tool_name
                current_tool_input_json = ""

            elif event.type == "tool_use_delta":
                current_tool_input_json += event.tool_input_delta
                if not self._adapter.capabilities.redis_passthrough:
                    await self._callback.tool_use_delta(
                        tool_use_id=current_tool_id,
                        partial_json=event.tool_input_delta,
                    )

            elif event.type == "tool_use_end":
                tool_use_blocks.append(ToolUseBlock(
                    id=current_tool_id,
                    name=current_tool_name,
                    input=event.tool_input_complete,
                ))

            elif event.type == "message_end":
                stop_reason = event.stop_reason
                self._total_input_tokens += event.input_tokens
                self._total_output_tokens += event.output_tokens
                # v4:cache tokens 三字段(见 DOC-02 v4 StreamEvent)
                self._total_cache_hit_tokens += getattr(event, "cache_hit_tokens", 0) or 0
                self._total_cache_creation_tokens += getattr(event, "cache_creation_tokens", 0) or 0

            elif event.type == "error":
                raise RuntimeError(f"模型返回错误: {event.error_message}")

        # 将 Assistant 消息追加到 messages
        content_blocks: list[ContentBlock] = []
        if accumulated_text:
            content_blocks.append(TextBlock(text=accumulated_text))
        content_blocks.extend(tool_use_blocks)

        if content_blocks:
            assistant_msg = PrismMessage(role="assistant", content=content_blocks)
            self._messages.append(assistant_msg)
            # v4:关键事件 HTTP 带重试上报 message 完整体(供 Backend 持久化 messages 表)
            await self._callback.message_complete(
                role="assistant",
                content=[_block_to_dict(b) for b in content_blocks],
            )

        return stop_reason, tool_use_blocks
    
    async def _execute_tools(self, tool_use_blocks: list[ToolUseBlock]) -> None:
        """
        执行工具调用列表(v4:asyncio.gather 并行)

        策略:
        1. 按依赖关系分组(无依赖可并行,有依赖顺序执行)
        2. 无依赖组 → asyncio.gather
        3. 有依赖组 → 顺序 for

        依赖检测:若 ToolUseBlock.input 中包含 `{{tool_result:X}}` 占位符,
        则依赖 id=X 的工具。Phase 1 保守实现:所有 tool 无依赖 → 全部并行。
        DOC-04 Coordinator 模式下可精细化依赖分析(ADR-021)。

        结果按 block 顺序收集到单条 user message 的 tool_result 列表
        (canonical Anthropic 语义,OpenAIDriver 在出站时展开为多条 role=tool)。
        """
        import asyncio
        tool_coros = [
            self._execute_single_tool(block)
            for block in tool_use_blocks
        ]
        results = await asyncio.gather(*tool_coros, return_exceptions=True)

        result_blocks: list[ToolResultBlock] = []
        for block, result in zip(tool_use_blocks, results):
            if isinstance(result, Exception):
                logger.exception("harness.tool.exception",
                                 tool_use_id=block.id,
                                 tool_name=block.name,
                                 error=str(result))
                result_blocks.append(ToolResultBlock(
                    tool_use_id=block.id,
                    content=f"工具异常: {str(result)}",
                    is_error=True,
                ))
            else:
                result_blocks.append(result)

        # canonical Anthropic:追加单条 user message,content 为 tool_result* 列表
        self._messages.append(PrismMessage(
            role="user",
            content=result_blocks,
        ))

    async def _execute_single_tool(self, block: ToolUseBlock) -> ToolResultBlock:
        """单工具执行,走完整 Pipeline(Hook → Permission → 执行 → 截断)"""
        import time
        await self._callback.tool_start(block.id, block.name, block.input)
        start = time.monotonic()

        prism_tool_invocations_total.labels(tool_name=block.name).inc()
        try:
            result = await self._pipeline.execute(
                tool_name=block.name,
                tool_input=block.input,
                tool_use_id=block.id,
                run_context=self._run_context,  # v4:传递 run_id/session_id/user_id
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            prism_tool_duration_seconds.labels(tool_name=block.name).observe(duration_ms / 1000.0)
            await self._callback.tool_end(
                tool_use_id=block.id,
                output=result.content,
                is_error=result.is_error,
                duration_ms=duration_ms,
            )
            return result
        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            prism_tool_errors_total.labels(tool_name=block.name, error_type=type(e).__name__).inc()
            await self._callback.tool_end(
                tool_use_id=block.id,
                output=str(e),
                is_error=True,
                duration_ms=duration_ms,
            )
            raise
```

### 6. executor/__main__.py — 完整入口(v4:加心跳 writer)

```python
"""
Prism v2 Agent 执行器入口(v4)

用法:python -m executor --run-id=019... --session-id=... --user-id=... \\
                         --callback-url=http://... --callback-secret=... \\
                         --redis-url=redis://... [--resume-from-step=N] [--otel-trace-id=...]

环境变量(由 Backend subprocess 启动时注入,见 DOC-01 v4 §9.1):
- ENCRYPTION_KEY:AES-256-GCM,用于 Provider API Key 解密
- PRISM_RUN_ID / PRISM_SESSION_ID / PRISM_USER_ID:上下文
- OTEL_TRACE_ID(可选):跨进程 trace 传播

生命周期:
1. 解析命令行参数
2. 从 DB 读取 Run 配置 + Provider(独立 DB session)
3. 初始化 Adapter + PromptAssembler + ToolRegistry + Pipeline + Budget
4. v4:启动 heartbeat writer task(asyncio.create_task,每 5s SETEX harness:heartbeat:*)
5. 初始化 Harness Runtime(Middleware + Hook + Permission + Guardrails,Task 3.2-3.4)
6. 初始化 QueryEngine(按 agent_type 选 MAX_TURNS)
7. 执行 QueryEngine.run()
8. 停止心跳,清理资源
"""

import argparse
import asyncio
import os
import signal
import time
import redis.asyncio as redis_async
import structlog

logger = structlog.get_logger()

HEARTBEAT_INTERVAL = int(os.environ.get("HEARTBEAT_INTERVAL_SECONDS", "5"))
HEARTBEAT_TTL = int(os.environ.get("HEARTBEAT_TTL_SECONDS", "60"))

MAX_TURNS_BY_AGENT_TYPE = {
    "chat": 50,
    "explore": 30,
    "build": 100,
    "coordinator": 200,
    "verifier": 20,
    "plugin_builder": 40,
}


async def heartbeat_writer(run_id: str, redis_url: str, stop_event: asyncio.Event) -> None:
    """
    v4 新增:心跳 writer task
    每 HEARTBEAT_INTERVAL 秒向 Redis 写 `harness:heartbeat:{run_id}` key,TTL=60s
    Backend HeartbeatMonitor 每 10s SCAN,超 30s 无更新 → 标记 Run crashed
    """
    r = redis_async.from_url(redis_url)
    try:
        while not stop_event.is_set():
            try:
                await r.setex(
                    f"harness:heartbeat:{run_id}",
                    HEARTBEAT_TTL,
                    str(int(time.time())),
                )
            except Exception as e:
                logger.warning("harness.heartbeat.write_failed", run_id=run_id, error=str(e))

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=HEARTBEAT_INTERVAL)
            except asyncio.TimeoutError:
                continue
    finally:
        try:
            await r.delete(f"harness:heartbeat:{run_id}")
        except Exception:
            pass
        await r.aclose()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--callback-url", required=True)
    parser.add_argument("--callback-secret", required=True)
    parser.add_argument("--redis-url", required=True)
    parser.add_argument("--resume-from-step", type=int, default=None,
                        help="Coordinator 恢复执行起点(DOC-07 v4 Task 7.4)")
    parser.add_argument("--otel-trace-id", default=None)
    args = parser.parse_args()

    # 1. 从 DB 读取 Run 配置(独立 session)
    # run = db.query(Run).filter_by(id=args.run_id).one()
    # provider = db.query(Provider).filter_by(id=run.provider_id).one()

    # 2. Adapter + 引擎组件
    # adapter = ProviderManager.get_adapter(provider)   # 内部用 ENCRYPTION_KEY 解密
    # budget = ContextBudgetManager(max_context_tokens=provider.max_context_tokens)
    # assembler = PromptAssembler(agent_type=run.agent_type, tools=registry.list_definitions())
    # registry = ToolRegistry(); register_builtin_tools(registry, mcp_servers=run.mcp_whitelist)
    # pipeline = ToolExecutionPipeline(registry, budget, hook_system, permission_engine)

    # 3. Callback
    callback = BackendCallback(
        callback_url=args.callback_url,
        callback_secret=args.callback_secret,
        run_id=args.run_id,
        session_id=args.session_id,
        redis_url=args.redis_url,
    )

    # 4. 心跳 writer
    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        heartbeat_writer(args.run_id, args.redis_url, stop_event)
    )

    # 5. Harness Runtime(Task 3.2-3.4)
    # middleware = MiddlewarePipeline([...])
    # hook_system = HookSystem.load_from_config(...)
    # permission_engine = PermissionEngine(redis_url=args.redis_url, callback=callback)
    # guardrails = GuardrailsEngine(platform_rules=platform_rules, agent_rules=agent_rules)

    # 6. QueryEngine
    # max_turns = MAX_TURNS_BY_AGENT_TYPE.get(run.agent_type, 50)
    # engine = QueryEngine(
    #     adapter=adapter, assembler=assembler, pipeline=pipeline, budget=budget,
    #     callback=callback, middleware=middleware, max_turns=max_turns,
    #     run_context=RunContext(run_id=args.run_id, session_id=args.session_id, user_id=args.user_id),
    # )

    # 7. SIGTERM 处理(graceful cancel)
    def _sigterm(*_):
        logger.info("harness.subprocess.sigterm_received", run_id=args.run_id)
        stop_event.set()
        asyncio.get_event_loop().create_task(engine.cancel(graceful=True))

    signal.signal(signal.SIGTERM, _sigterm)

    # 8. 执行
    try:
        if args.resume_from_step is not None:
            # Coordinator Recovery(DOC-04 v4 Task 4.3,DOC-07 v4 Task 7.4)
            await engine.resume(from_step=args.resume_from_step)
        else:
            await engine.run(run.prompt)
    finally:
        stop_event.set()
        await heartbeat_task
        await callback.close()


if __name__ == "__main__":
    asyncio.run(main())
```

注意:`__main__.py` 中的注释标注了完整链路,实际代码根据 Task 2.1-2.4 + 3.2-3.4 已实现的类填充。每一步都有对应模块,不需要新造依赖。心跳 writer 和 SIGTERM 处理是 v4 必须。

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/tools/base.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/tools/registry.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/tools/pipeline.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/callbacks/backend_callback.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/engine/query_engine.py

# 2. 导入检查
docker compose -f docker-compose.dev.yml exec backend python -c "
from executor.tools.base import BaseTool, ToolResult
from executor.tools.registry import ToolRegistry
from executor.tools.pipeline import ToolExecutionPipeline
from executor.engine.query_engine import QueryEngine
from executor.callbacks.backend_callback import BackendCallback
print('All core imports successful')
"

# 3. 工具注册 + Pipeline 单元测试
docker compose -f docker-compose.dev.yml exec backend python -c "
import asyncio
from executor.tools.base import BaseTool, ToolResult
from executor.tools.registry import ToolRegistry
from executor.tools.pipeline import ToolExecutionPipeline
from executor.engine.context_budget import ContextBudgetManager
from executor.adapters.base import ToolResultBlock

class EchoTool(BaseTool):
    @property
    def name(self): return 'echo'
    @property
    def description(self): return '回显输入内容'
    @property
    def input_schema(self): return {'type':'object','properties':{'message':{'type':'string'}},'required':['message']}
    async def execute(self, tool_input):
        return ToolResult(content=f'Echo: {tool_input[\"message\"]}')

registry = ToolRegistry()
registry.register(EchoTool())
assert registry.get('echo') is not None, 'Tool registration failed'
assert len(registry.list_definitions()) == 1, 'Tool listing failed'
print('Registry: PASS')

budget = ContextBudgetManager(tool_result_max_chars=50)
pipeline = ToolExecutionPipeline(registry, budget)

async def test():
    # 正常执行
    result = await pipeline.execute('echo', {'message': 'hello'}, 'test-001')
    assert result.content == 'Echo: hello', f'Unexpected: {result.content}'
    assert not result.is_error
    print('Pipeline normal: PASS')
    
    # 工具不存在
    result = await pipeline.execute('nonexistent', {}, 'test-002')
    assert result.is_error
    print('Pipeline not found: PASS')
    
    # Schema 校验失败
    result = await pipeline.execute('echo', {'wrong_field': 123}, 'test-003')
    assert result.is_error
    print('Pipeline schema validation: PASS')
    
    # 结果截断
    class LongTool(BaseTool):
        @property
        def name(self): return 'long'
        @property
        def description(self): return 'test'
        @property
        def input_schema(self): return {'type':'object'}
        async def execute(self, tool_input):
            return ToolResult(content='x' * 200)
    
    registry.register(LongTool())
    result = await pipeline.execute('long', {}, 'test-004')
    assert '截断' in result.content, 'Truncation failed'
    print('Pipeline truncation: PASS')

asyncio.run(test())
print('\nAll Task 3.1 checks passed!')
"

# 4. v4 工具并行时序断言
docker compose -f docker-compose.dev.yml exec backend python -c "
import asyncio, time
from executor.tools.base import BaseTool, ToolResult
from executor.tools.registry import ToolRegistry
from executor.tools.pipeline import ToolExecutionPipeline
from executor.engine.context_budget import ContextBudgetManager

class SlowTool(BaseTool):
    @property
    def name(self): return 'slow'
    @property
    def description(self): return 'sleeps'
    @property
    def input_schema(self): return {'type':'object','properties':{'ms':{'type':'integer'}},'required':['ms']}
    async def execute(self, tool_input):
        await asyncio.sleep(tool_input['ms']/1000)
        return ToolResult(content='ok')

reg = ToolRegistry(); reg.register(SlowTool())
# 模拟 3 个 5s 工具并行执行,总耗时应 < 7s(留 2s 余量)
async def _t():
    from executor.adapters.base import ToolUseBlock
    start = time.monotonic()
    blocks = [ToolUseBlock(id=f'tu_{i}', name='slow', input={'ms': 5000}) for i in range(3)]
    coros = [asyncio.create_task(_run_one(reg, b)) for b in blocks]
    await asyncio.gather(*coros)
    dur = time.monotonic() - start
    assert dur < 7.0, f'Tools did not run in parallel: {dur:.2f}s'
    print(f'Parallel tools: PASS (total {dur:.2f}s for 3×5s)')
async def _run_one(reg, b):
    t = reg.get(b.name)
    return await t.execute(b.input)
asyncio.run(_t())
"

# 5. v4 Redis 直通断言(需要 Redis 运行)
docker compose -f docker-compose.dev.yml exec backend python -c "
import asyncio, json
import redis.asyncio as redis_async

async def _t():
    r = redis_async.from_url('redis://redis:6379', decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe('run:test-run-id:stream')

    # 模拟 Callback 发 text_delta
    await r.publish('run:test-run-id:stream', json.dumps({'type':'text_delta','text':'hi'}))

    got = None
    async for msg in pubsub.listen():
        if msg.get('type') == 'message':
            got = json.loads(msg['data'])
            break
    assert got and got['type'] == 'text_delta'
    print('Redis passthrough: PASS')
    await pubsub.unsubscribe(); await pubsub.close(); await r.aclose()
asyncio.run(_t())
"

# 6. v4 心跳 Key 存在检查
docker compose -f docker-compose.dev.yml exec backend python -c "
import asyncio, redis.asyncio as redis_async
from executor.__main__ import heartbeat_writer
async def _t():
    stop = asyncio.Event()
    task = asyncio.create_task(heartbeat_writer('hb-test-run', 'redis://redis:6379', stop))
    await asyncio.sleep(6)
    r = redis_async.from_url('redis://redis:6379', decode_responses=True)
    val = await r.get('harness:heartbeat:hb-test-run')
    assert val is not None, 'Heartbeat not written'
    print(f'Heartbeat: PASS (last={val})')
    stop.set(); await task; await r.aclose()
asyncio.run(_t())
"

# 7. 集成测试(需要真实 API Key,手动执行)
# 用 EchoTool 注册到 QueryEngine,发送一条消息,验证完整循环,Redis PUBLISH 到位
```

## 完成后

1. 更新 PROGRESS.md:记录 Task 3.1 完成状态
2. 更新 DECISIONS.md:记录 **ADR-020(Harness 单实例)/ADR-021(工具并行 gather)/ADR-022(Redis 直通)/ADR-023(心跳)/ADR-024(MAX_TURNS 按 agent_type 分档)**
3. 在 requirements.txt 中加入 `jsonschema>=4.0.0`
4. 加载 Simplify skill 审查
5. 加载 PJR skill 验证
6. `git add -A && git commit -m "feat(v4): TAOR parallel tools + Redis passthrough + heartbeat + dual-channel callback"`
```

---

## Task 3.2: Middleware Pipeline(v4:升到 4 钩点)

### Part A — 设计与解释

#### 问题陈述

TAOR 主循环需要在每轮执行前后插入治理逻辑:上下文增强、循环检测、速率限制、输出校验、反馈采集、可观测性记录。这些逻辑如果直接写进 QueryEngine 会违反单一职责原则,也无法按需启停。

Middleware Pipeline 是 Harness Runtime 的编排骨架——可插拔中间件链,每个中间件单一职责,按顺序执行。对标 NxCode 描述的架构:`Request → ContextMiddleware → LoopDetectionMiddleware → ... → Response`。

**v4 修订**:仅 2 钩点(pre_turn/post_turn)无法在工具执行前后插入逻辑。例如循环检测最佳时机是 pre_tool_use(输入未执行前就可以 abort),敏感输出扫描最佳时机是 post_tool_use(结果已产出但尚未进入 context)。v4 升级为 **4 钩点**,对应 TAOR 循环的 4 个观察/干预时机。

#### CC 架构映射

CC 没有显式的 Middleware Pipeline,但它的 QueryEngine 内部按固定顺序执行了等效逻辑(prefetch memory → compaction → API call → tool dispatch → recovery)。Prism 将这些逻辑抽取为独立中间件,实现 P7 可撕裂架构——模型升级后,某些"补偿性"中间件可以直接关闭。

#### 设计决策(ADR)

- **ADR-025(Middleware 4 钩点)**:Middleware 从 2 钩点(pre_turn/post_turn)升级为 4 钩点(pre_turn/pre_tool_use/post_tool_use/post_turn)。对应 TAOR 循环的 4 个观察/干预时机:
  - `pre_turn`:本轮 API 调用之前(可改写 messages / 注入上下文)
  - `pre_tool_use`:工具执行之前(可改写 tool_input / 决定 permission,在 Hook 决策之前)
  - `post_tool_use`:工具执行之后(可改写 tool_result,在追加到 messages 之前)
  - `post_turn`:本轮结束之后(可触发 compaction / 检测 loop)

  来源:PDF 补丁, Batch 2 §A3-5。

#### 验收标准(v4 扩展)

- MiddlewarePipeline 按注册顺序执行中间件的 4 个钩点
- 每个中间件可以在任意钩点插入逻辑(默认 pass)
- 中间件可以中断循环(返回 abort 信号)——在 pre_turn 或 pre_tool_use 阶段设置 `ctx.abort=True`
- LoopDetectionMiddleware 检测到连续重复工具调用时在 `pre_tool_use` 触发告警(未执行就可以 abort)
- ObservabilityMiddleware 将每轮 turn 的关键指标写入 trace + OTel span(`turn.executed`)
- 集成到 QueryEngine 后不改变已有的 TAOR 行为(4 个钩点在无 Middleware 时均为 no-op)

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的 Middleware Pipeline——Harness Runtime 的编排骨架。Task 3.1 已完成 TAOR 主循环，其中标记了 `HARNESS_INTEGRATION_POINT`。本 Task 实现中间件机制并集成到 QueryEngine 中。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

Task 3.1 已完成，QueryEngine 可运行

## 要创建的文件

```
executor/harness/middleware/
├── base.py                    # Middleware 抽象基类
├── pipeline.py                # MiddlewarePipeline 编排器
├── loop_detection.py          # 循环检测中间件
└── observability.py           # 可观测性中间件
```

## 实现规范

### 1. executor/harness/middleware/base.py(v4:4 钩点)

```python
"""
Middleware 抽象基类(v4:4 钩点)

4 钩点对应 TAOR 循环的 4 个观察/干预时机:
- pre_turn:       本轮 API 调用之前(可改写 messages / 注入上下文)
- pre_tool_use:   工具执行之前(可改写 tool_input / 决定 permission)
- post_tool_use:  工具执行之后(可改写 tool_result)
- post_turn:      本轮结束之后(可触发 compaction / 检测 loop)

context 是一个 mutable 对象,中间件之间通过它传递状态。
"""

from abc import ABC
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MiddlewareContext:
    """Middleware 调用上下文(v4)"""
    run_id: str
    session_id: str
    user_id: str
    turn_count: int
    agent_type: str
    messages: list                          # 当前 messages
    system_prompt: str
    tool_use_block: Any = None              # pre_tool_use / post_tool_use 时有值
    tool_result_block: Any = None           # post_tool_use 时有值
    abort: bool = False
    abort_reason: str = ""
    custom_data: dict = field(default_factory=dict)   # middleware 之间传递数据


# 向后兼容别名(v4 之前代码可能引用 TurnContext)
TurnContext = MiddlewareContext


class Middleware(ABC):
    """所有 Middleware 继承此类,按需 override 钩点。无 override 的钩点为 no-op。"""

    name: str = "unnamed"

    async def pre_turn(self, ctx: MiddlewareContext) -> None:
        """本轮 API 调用之前。可修改 messages / 注入 context / 设置 ctx.abort"""
        pass

    async def pre_tool_use(self, ctx: MiddlewareContext) -> None:
        """工具执行之前。ctx.tool_use_block 为当前待执行的 ToolUseBlock。"""
        pass

    async def post_tool_use(self, ctx: MiddlewareContext) -> None:
        """工具执行之后。ctx.tool_result_block 为执行结果,可改写或观测。"""
        pass

    async def post_turn(self, ctx: MiddlewareContext) -> None:
        """本轮结束之后(含 compaction 检查)。可记录指标、触发告警等。"""
        pass
```

### 2. executor/harness/middleware/pipeline.py

```python
"""
MiddlewarePipeline — 按注册顺序执行中间件链

使用方式：
    pipeline = MiddlewarePipeline()
    pipeline.register(LoopDetectionMiddleware(window=5, redis=redis_client, run_id=run_id))
    pipeline.register(ObservabilityMiddleware(callback=callback))
    
    # 在 QueryEngine 的每轮循环中：
    ctx = TurnContext(turn_count=n, messages=messages, run_id=run_id)
    await pipeline.run_pre_turn(ctx)
    if ctx.abort:
        # 中断循环
    ... 正常执行 ...
    await pipeline.run_post_turn(ctx)
"""

class MiddlewarePipeline:
    """v4:编排 4 钩点"""

    def __init__(self):
        self._middlewares: list[Middleware] = []

    def register(self, mw: Middleware) -> None:
        self._middlewares.append(mw)

    async def run_pre_turn(self, ctx: MiddlewareContext) -> None:
        for mw in self._middlewares:
            await mw.pre_turn(ctx)
            if ctx.abort:
                return

    async def run_pre_tool_use(self, ctx: MiddlewareContext) -> None:
        """v4 新增:工具执行前。在 Hook 决策之前运行,可 abort 整个循环。"""
        for mw in self._middlewares:
            await mw.pre_tool_use(ctx)
            if ctx.abort:
                return

    async def run_post_tool_use(self, ctx: MiddlewareContext) -> None:
        """v4 新增:工具执行后。可改写 tool_result。全部执行,不短路。"""
        for mw in self._middlewares:
            await mw.post_tool_use(ctx)

    async def run_post_turn(self, ctx: MiddlewareContext) -> None:
        # post_turn 全部执行,不短路
        for mw in self._middlewares:
            await mw.post_turn(ctx)
```

### 2.1 QueryEngine `_execute_tools` 集成 4 钩点(v4)

```python
# QueryEngine._execute_single_tool 内部调度(Task 3.1 已骨架,本 Task 补 Middleware 钩点)
async def _execute_single_tool(self, block: ToolUseBlock) -> ToolResultBlock:
    ctx = MiddlewareContext(
        run_id=self._run_context.run_id,
        session_id=self._run_context.session_id,
        user_id=self._run_context.user_id,
        turn_count=self._turn_count,
        agent_type=self._run_context.agent_type,
        messages=self._messages,
        system_prompt=self._current_system_prompt,
        tool_use_block=block,
    )

    # pre_tool_use 钩点(v4 新增)
    await self._middleware.run_pre_tool_use(ctx)
    if ctx.abort:
        return ToolResultBlock(
            tool_use_id=block.id,
            content=f"Middleware aborted: {ctx.abort_reason}",
            is_error=True,
        )

    # Hook + Permission + 执行(沿用 Task 3.1 路径)
    result = await self._pipeline.execute(
        tool_name=block.name,
        tool_input=block.input,
        tool_use_id=block.id,
        run_context=self._run_context,
    )

    # post_tool_use 钩点(v4 新增:Middleware 可改写 result)
    ctx.tool_result_block = result
    await self._middleware.run_post_tool_use(ctx)
    return ctx.tool_result_block
```

### 3. executor/harness/middleware/loop_detection.py

```python
"""
循环检测中间件

检测 Agent 是否在重复调用同一工具+同一参数。
在 post_turn 阶段检查最近 N 轮的工具调用，如果发现
连续 N 次相同的 (tool_name, tool_input_hash)，触发告警。

状态通过 Redis 存储（key: harness:loop:{run_id}），支持跨 compaction 保持检测。
"""

class LoopDetectionMiddleware(Middleware):
    def __init__(self, window: int, redis_client, run_id: str, callback: BackendCallback):
        self._window = window
        self._redis = redis_client
        self._run_id = run_id
        self._callback = callback
    
    async def post_turn(self, ctx: TurnContext) -> None:
        """检查最近 messages 中的工具调用是否有循环模式"""
        # 从 ctx.messages 尾部提取最近的 tool_use blocks
        # hash(tool_name + json(tool_input)) 生成指纹
        # 写入 Redis list（harness:loop:{run_id}），保留最近 window 条
        # 如果 window 条指纹全部相同 → 循环检测命中
        # 命中后：ctx.abort = True，通过 callback 上报 harness_event("loop_detected")
        ...
```

### 4. executor/harness/middleware/observability.py

```python
"""
可观测性中间件

post_turn 阶段记录每轮的关键指标：
- turn_count
- 工具调用数
- token 消耗增量
- 耗时
通过 callback.harness_event 上报，Backend 写入 audit_logs。
"""

class ObservabilityMiddleware(Middleware):
    def __init__(self, callback: BackendCallback):
        self._callback = callback
        self._turn_start_time: float = 0
    
    async def pre_turn(self, ctx: TurnContext) -> None:
        import time
        self._turn_start_time = time.monotonic()
    
    async def post_turn(self, ctx: TurnContext) -> None:
        import time
        duration_ms = int((time.monotonic() - self._turn_start_time) * 1000)
        # 统计本轮工具调用数（从 ctx.metadata 或 messages 尾部提取）
        await self._callback.harness_event("turn_complete", {
            "turn": ctx.turn_count,
            "duration_ms": duration_ms,
            "tool_calls": ctx.metadata.get("tool_call_count", 0),
        })
```

### 5. 集成到 QueryEngine

修改 `executor/engine/query_engine.py`：
- `__init__` 新增参数 `middleware_pipeline: MiddlewarePipeline | None = None`
- `run()` 循环中，替换 `HARNESS_INTEGRATION_POINT` 注释为实际调用：
  - 循环开始：`ctx = TurnContext(...)` → `await self._middleware.run_pre_turn(ctx)` → 检查 `ctx.abort`
  - 循环结束：`ctx.metadata["tool_call_count"] = len(tool_use_blocks)` → `await self._middleware.run_post_turn(ctx)`

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/harness/middleware/base.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/harness/middleware/pipeline.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/harness/middleware/loop_detection.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/harness/middleware/observability.py

# 2. Pipeline 单元测试
docker compose -f docker-compose.dev.yml exec backend python -c "
import asyncio
from executor.harness.middleware.base import Middleware, TurnContext
from executor.harness.middleware.pipeline import MiddlewarePipeline

class CounterMW(Middleware):
    def __init__(self):
        self.pre_count = 0
        self.post_count = 0
    async def pre_turn(self, ctx):
        self.pre_count += 1
    async def post_turn(self, ctx):
        self.post_count += 1

class AbortMW(Middleware):
    async def pre_turn(self, ctx):
        ctx.abort = True
        ctx.abort_reason = 'test abort'

async def test():
    # 正常执行
    p = MiddlewarePipeline()
    c1, c2 = CounterMW(), CounterMW()
    p.register(c1)
    p.register(c2)
    ctx = TurnContext(turn_count=1, messages=[], run_id='test')
    await p.run_pre_turn(ctx)
    await p.run_post_turn(ctx)
    assert c1.pre_count == 1 and c2.pre_count == 1
    assert c1.post_count == 1 and c2.post_count == 1
    print('Normal pipeline: PASS')
    
    # 中断短路
    p2 = MiddlewarePipeline()
    abort = AbortMW()
    c3 = CounterMW()
    p2.register(abort)
    p2.register(c3)
    ctx2 = TurnContext(turn_count=1, messages=[], run_id='test')
    await p2.run_pre_turn(ctx2)
    assert ctx2.abort
    assert c3.pre_count == 0, 'Short circuit failed'
    print('Abort short circuit: PASS')

asyncio.run(test())
print('\nAll Task 3.2 checks passed!')
"
```

## 完成后

1. 更新 PROGRESS.md
2. 更新 DECISIONS.md：记录 ADR-007（可插拔 Middleware Pipeline — 治理逻辑与业务逻辑分离）
3. 加载 Simplify skill 审查
4. 加载 PJR skill 验证
5. `git add -A && git commit -m "feat: Harness Middleware Pipeline with loop detection and observability"`
```

---

## Task 3.3: Hook System 与 Permission Engine(v4:HookDecision 11 字段 + permission ask Redis BLPOP)

### Part A — 设计与解释

#### 问题陈述

CC 源码的 Hook System 是其 Harness 最强大的治理能力——在每个生命周期事件节点触发外部脚本/webhook/LLM 审查,可以拦截、改写、放行工具调用。Prism 需要实现等效的 Hook System(21 种事件 × 4 种 handler)和分层 Permission Engine(平台级 + 插件级)。

**v4 核心修订**:
1. HookDecision 扩到 **11 个字段**(对标 CC 的 `toolHooks.ts`),支持完整合并规则
2. Permission `ask` 从"fail-safe deny 占位"升级为**端到端反向通信协议**:Redis BLPOP 阻塞等待用户回答
3. Handler 类型从 2 种扩到 **4 种**:command / http / prompt(LLM 决策) / agent(子 Agent 决策)
4. 平台级护栏规则集补齐:破坏性操作 + 速率 + PII + 跨用户

#### CC 架构映射

| CC 机制 | Prism 对应 |
|---------|-----------|
| `src/services/tools/toolHooks.ts` 11 字段 | `executor/harness/hooks/decision.py` HookDecision 11 字段 |
| `.claude/settings.json` hooks 配置 | `.prism/hooks.json` |
| PreToolUse / PostToolUse / PermissionRequest 事件 | HookSystem 事件分发 |
| exit 0 + JSON / exit 2 协议 | HookHandler 决策协议 |
| 4 种 handler(command/http/prompt/agent) | HookHandlerExecutor 4 种实现 |
| 6 种权限模式 | PermissionEngine 分层模型 |
| `canUseTool` ask 弹窗 | PermissionAskProtocol(Redis BLPOP) |
| matcher regex | HookMatcher 正则匹配 |
| Dyad 的 GREEN/YELLOW/RED 分类 | PermissionEngine 风险路由 |

> **Phase 分期**:Phase 1 实现以下 8 个核心事件(覆盖完整的工具执行和会话生命周期):
> `PreToolUse`, `PostToolUse`, `SessionStart`, `SessionEnd`, `PreModelCall`, `PostModelCall`, `CompactionTrigger`, `ErrorOccurred`
>
> 其余事件(如 `ForkStart`, `ForkEnd`, `PlanStepStart` 等)在 Phase 1 中保留枚举定义和类型声明但不实现分发逻辑,Phase 2 按需开启。

#### 设计决策(ADR)

- **ADR-026(HookDecision 11 字段完整)**:对标 CC 的 `toolHooks.ts`,HookDecision 必须包含 11 个字段的完整语义,不能砍字段。字段清单:`permission_decision` / `updated_input` / `updated_mcp_tool_output` / `prevent_continuation` / `stop` / `stop_reason` / `additional_context` / `message` / `blocking_error` / `reason` / `handler_name`。来源:PDF 补丁 P4。

- **ADR-027(合并规则)**:多个 Hook 对同一事件返回 HookDecision 时,合并规则按**严格度降序**:
  1. `stop` 最高优先级(立即停止,不处理后续)
  2. `prevent_continuation` 次优
  3. `permission_decision`:`deny > ask > allow`
  4. `updated_input` / `updated_mcp_tool_output` 冲突时 abort(raise ValueError,**不猜**)
  5. `additional_context` / `message` 按顺序拼接
  6. `blocking_error` 任一触发即阻断

  来源:PDF 补丁 P4, Batch 2 §A3-6。

- **ADR-028(permission ask Redis BLPOP 协议)**:Permission Engine 做 `ask` 决策时,通过 `PermissionAskProtocol.ask()` 发起:
  1. 生成 `request_id = uuid7`,写入 Redis `perm_req:{request_id}` TTL=timeout
  2. 通过 BackendCallback 发 `permission_ask` 事件(HTTP 带重试)
  3. Backend 收到 → 通过 SSE `permission_ask` 事件推给前端 → 弹窗
  4. 子进程 `BLPOP perm_answer:{request_id}` 阻塞等待,超时(默认 300s)默认 `deny`(fail-safe)
  5. 用户点击 → Backend `POST /sessions/{id}/permission-answer` → Backend `RPUSH perm_answer:{request_id} "allow|deny"`
  6. 子进程 BLPOP 返回 → 继续执行

  来源:Batch 2 §A3-7, PDF 补丁。

#### Harness 交互:Permission ask 三方协议

```
子进程(Harness)                Backend                     前端
     │                             │                           │
     │ permission_ask 回调(HTTP)   │                           │
     ├────────────────────────────>│                           │
     │                             │ 写 permission_requests 表  │
     │                             │ SSE permission_ask        │
     │                             ├──────────────────────────>│
     │                             │                           │ 弹窗展示
     │ BLPOP perm_answer:{id}      │                           │
     │ (阻塞,timeout=300s)         │                           │ 用户点"允许"
     │                             │ POST /permission-answer   │
     │                             │<──────────────────────────┤
     │                             │ UPDATE permission_requests│
     │                             │ RPUSH perm_answer:{id}    │
     │ (BLPOP 解除阻塞)            │                           │
     │<────────────────────────────┤                           │
     │                             │                           │
     │ 继续执行工具(或 deny)       │                           │
```

#### 验收标准(v4 扩展)

- HookSystem 能在 PreToolUse / PostToolUse / SessionStart / SessionEnd 等事件触发注册的 handler
- command / http / prompt / agent **4 种** handler 均可运行
- HookDecision **11 字段完整定义**,合并规则按严格度降序执行
- `updated_input` 多 Hook 冲突时 raise ValueError(不猜)
- Permission Engine 对每个工具调用做 allow/deny/ask 决策
- **`ask` 决策走 PermissionAskProtocol.ask():Redis BLPOP 等待,超时 fail-safe deny**
- Guardrails 平台级规则(破坏性操作拦截 + 速率 + PII + 跨用户)正确触发
- Hook 可以改写工具输入(updated_input)
- Hook 可以阻断执行(permission_decision: deny)
- 集成到 ToolExecutionPipeline 的 HARNESS_INTEGRATION_POINT

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的 Hook System 和 Permission Engine——Harness Runtime 的治理核心。Task 3.1（TAOR 循环）和 Task 3.2（Middleware Pipeline）已完成。ToolExecutionPipeline 中标记了 `HARNESS_INTEGRATION_POINT`，本 Task 填充这些集成点。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

Task 3.1 和 3.2 已完成

## 要创建的文件

```
executor/harness/
├── hooks/
│   ├── events.py              # 事件类型定义
│   ├── decision.py            # v4 新文件:HookDecision 11 字段 + merge_decisions()
│   ├── system.py              # HookSystem(事件分发)
│   └── handlers.py            # v4:4 种 Handler(command/http/prompt/agent)
├── permissions/
│   ├── engine.py              # PermissionEngine(含 ask 方法)
│   └── ask_protocol.py        # v4 新文件:Redis BLPOP 反向通信协议
├── guardrails/
│   ├── engine.py              # GuardrailsEngine
│   ├── rules.py               # 规则基类
│   └── platform_rules.py      # 平台级内置规则(v4 补齐 4 类)
└── lifecycle.py               # 生命周期控制器(组装 Hook + Permission + Guardrails)
```

## 实现规范

### 1. executor/harness/hooks/events.py

```python
"""
Hook 事件类型定义 — 对标 CC 的 21 种生命周期事件

Phase 1 实现核心 8 种，其余在后续 DOC 中扩展。
"""

from dataclasses import dataclass, field
from typing import Literal

HookEventType = Literal[
    # Phase 1 核心事件
    "SessionStart",          # 会话开始
    "SessionEnd",            # 会话结束
    "PreToolUse",            # 工具调用前（可拦截/改写）
    "PostToolUse",           # 工具调用后（可检查输出）
    "PostToolUseFailure",    # 工具调用失败后
    "PermissionRequest",     # 权限请求（快速规则未匹配时的 LLM 兜底）
    "Compact",               # 上下文压缩时
    "Notification",          # 通知事件
]

@dataclass
class HookEvent:
    """Hook 事件"""
    event_type: HookEventType
    tool_name: str = ""          # PreToolUse/PostToolUse 时有值
    tool_input: dict = field(default_factory=dict)
    tool_output: str = ""        # PostToolUse 时有值
    is_error: bool = False       # PostToolUseFailure 时 True
    run_id: str = ""
    session_id: str = ""

@dataclass
class HookDecision:
    """Hook handler 返回的决策(v4:简化版,完整 11 字段定义在 decision.py)"""
    permission_decision: Literal["allow", "deny", "ask"] | None = None
    updated_input: dict | None = None     # 改写后的工具输入
    additional_context: str | None = None  # 追加到 Agent 上下文的信息
    prevent_continuation: bool = False     # 阻止 Agent 继续
    reason: str = ""
```

### 1.1 executor/harness/hooks/decision.py(v4 新文件:11 字段完整定义)

```python
"""
HookDecision — Hook 执行结果的完整决策对象
对标 CC 的 src/services/tools/toolHooks.ts(11 个字段)
"""

from dataclasses import dataclass
from typing import Literal

PermissionDecision = Literal["allow", "ask", "deny"]


@dataclass
class HookDecision:
    """11 字段完整定义(v4 ADR-026)"""
    # 核心决策
    permission_decision: PermissionDecision | None = None
    # 输入改写
    updated_input: dict | None = None
    # MCP 工具输出改写
    updated_mcp_tool_output: dict | None = None
    # 流程控制
    prevent_continuation: bool = False
    stop: bool = False
    stop_reason: str | None = None
    # 追加上下文给 Agent
    additional_context: str | None = None
    # 用户消息(显示在 UI)
    message: str | None = None
    # 阻断性错误
    blocking_error: str | None = None
    # 审计
    reason: str | None = None
    handler_name: str | None = None


def merge_decisions(decisions: list[HookDecision]) -> HookDecision:
    """
    合并多个 Hook 的决策(v4 ADR-027)。
    严格度排序(高 → 低):
      stop > prevent_continuation > permission_deny > permission_ask > permission_allow

    updated_input / updated_mcp_tool_output 冲突时 abort(不猜),raise ValueError
    """
    result = HookDecision()

    # stop 优先级最高
    for d in decisions:
        if d.stop:
            result.stop = True
            result.stop_reason = d.stop_reason
            result.handler_name = d.handler_name
            return result  # 立即返回,不处理后续

    # prevent_continuation 次优先级
    for d in decisions:
        if d.prevent_continuation:
            result.prevent_continuation = True
            result.reason = d.reason

    # permission 按严格度:deny > ask > allow
    permission_priority = {"deny": 3, "ask": 2, "allow": 1, None: 0}
    result.permission_decision = max(
        (d.permission_decision for d in decisions),
        key=lambda p: permission_priority[p],
        default=None,
    )

    # updated_input 冲突检测
    updated_inputs = [d.updated_input for d in decisions if d.updated_input is not None]
    if len(updated_inputs) > 1:
        raise ValueError(f"Multiple hooks want to modify input, refusing to guess: {updated_inputs}")
    if updated_inputs:
        result.updated_input = updated_inputs[0]

    # updated_mcp_tool_output 同理
    updated_outputs = [d.updated_mcp_tool_output for d in decisions if d.updated_mcp_tool_output is not None]
    if len(updated_outputs) > 1:
        raise ValueError(f"Multiple hooks want to modify MCP output: {updated_outputs}")
    if updated_outputs:
        result.updated_mcp_tool_output = updated_outputs[0]

    # additional_context 拼接
    contexts = [d.additional_context for d in decisions if d.additional_context]
    if contexts:
        result.additional_context = "\n\n".join(contexts)

    # blocking_error 任一触发即阻断
    errors = [d.blocking_error for d in decisions if d.blocking_error]
    if errors:
        result.blocking_error = "; ".join(errors)

    # message 拼接
    messages = [d.message for d in decisions if d.message]
    if messages:
        result.message = "\n".join(messages)

    return result
```

### 2. executor/harness/hooks/system.py

```python
"""
HookSystem — 事件分发器

对标 CC 的 Hook 执行流程：
1. 事件触发
2. 遍历注册的 handler（按优先级排序）
3. matcher 正则匹配（对 tool 事件匹配 tool_name）
4. 执行 handler
5. 合并决策

配置加载自 .prism/hooks.json（如存在），格式对标 CC 的 .claude/settings.json hooks 字段。
"""

class HookSystem:
    def __init__(self):
        self._handlers: dict[str, list[HookHandlerConfig]] = {}
    
    def register(self, event_type: str, config: "HookHandlerConfig") -> None:
        ...
    
    def load_from_config(self, config_path: str) -> None:
        """从 .prism/hooks.json 加载 Hook 配置"""
        ...
    
    async def fire(self, event: HookEvent) -> HookDecision:
        """
        触发事件，执行匹配的 handler，合并决策返回。
        
        决策合并规则：
        - 任何一个 handler 返回 deny → 最终 deny
        - 只要有 updated_input → 使用最后一个
        - additional_context 拼接
        """
        ...
```

### 3. executor/harness/hooks/handlers.py

```python
"""
Hook Handler 执行器

Phase 1 实现 2 种 handler：
- command: 执行 shell 命令，stdin 传入 JSON，stdout 读取 JSON 决策
- http: POST 到 webhook URL，body 为 JSON，response 为 JSON 决策

决策协议对标 CC：
- exit 0 + stdout JSON → 成功，解析 HookDecision
- exit 2 + stderr → 阻断，reason = stderr 内容
- 其他 exit code → 非阻断警告
"""

@dataclass
class HookHandlerConfig:
    type: Literal["command", "http", "prompt", "agent"]  # v4:扩到 4 种
    # command 类型
    command: str = ""
    # http 类型
    url: str = ""
    # prompt 类型(v4 新增):用 LLM 判断
    prompt_template: str = ""
    prompt_model: str = ""
    # agent 类型(v4 新增):fork 子 Agent 判断
    agent_type: str = ""
    # 共同
    matcher: str = ""             # 正则,匹配 tool_name(空字符串匹配所有)
    timeout_seconds: int = 10


class HookHandlerExecutor:
    """v4:4 种 handler 执行器"""

    def __init__(self, adapter=None, fork_manager=None):
        self._adapter = adapter           # prompt handler 用
        self._fork_manager = fork_manager  # agent handler 用

    async def execute(self, config: HookHandlerConfig, event: HookEvent) -> HookDecision:
        """执行单个 handler,返回决策"""
        if config.type == "command":
            return await self._execute_command(config, event)
        elif config.type == "http":
            return await self._execute_http(config, event)
        elif config.type == "prompt":
            return await self._execute_prompt(config, event)
        elif config.type == "agent":
            return await self._execute_agent(config, event)
        return HookDecision()

    async def _execute_command(self, config: HookHandlerConfig, event: HookEvent) -> HookDecision:
        """执行 shell 命令。stdin 传入事件 JSON,解析 stdout 为 HookDecision JSON。
        协议对标 CC:
        - exit 0 + stdout JSON → 成功,解析 HookDecision
        - exit 2 + stderr → 阻断,permission_decision=deny, reason=stderr
        - 其他 exit code → 非阻断警告(空 HookDecision)
        """
        import asyncio, json
        try:
            proc = await asyncio.create_subprocess_shell(
                config.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            event_json = json.dumps(event.__dict__, default=str).encode()
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=event_json),
                    timeout=config.timeout_seconds,
                )
            except asyncio.TimeoutError:
                proc.kill()
                return HookDecision(
                    blocking_error=f"hook command timeout after {config.timeout_seconds}s",
                    handler_name=config.command[:50],
                )

            if proc.returncode == 0 and stdout:
                try:
                    data = json.loads(stdout.decode())
                    data["handler_name"] = config.command[:50]
                    return HookDecision(**{k: v for k, v in data.items() if k in HookDecision.__dataclass_fields__})
                except json.JSONDecodeError:
                    return HookDecision(reason="hook stdout non-JSON, ignored", handler_name=config.command[:50])
            elif proc.returncode == 2:
                return HookDecision(
                    permission_decision="deny",
                    blocking_error=stderr.decode()[:500],
                    reason="hook exit 2",
                    handler_name=config.command[:50],
                )
            return HookDecision(reason=f"hook exit {proc.returncode}", handler_name=config.command[:50])
        except Exception as e:
            return HookDecision(reason=f"hook error: {e}", handler_name=config.command[:50])

    async def _execute_http(self, config: HookHandlerConfig, event: HookEvent) -> HookDecision:
        """POST 到 webhook URL。body 为事件 JSON,response 为 HookDecision JSON。"""
        import httpx, json
        try:
            async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
                resp = await client.post(config.url, json=event.__dict__)
                if resp.status_code == 200:
                    data = resp.json()
                    data["handler_name"] = config.url
                    return HookDecision(**{k: v for k, v in data.items() if k in HookDecision.__dataclass_fields__})
                return HookDecision(reason=f"hook http {resp.status_code}", handler_name=config.url)
        except Exception as e:
            return HookDecision(reason=f"hook http error: {e}", handler_name=config.url)

    async def _execute_prompt(self, config: HookHandlerConfig, event: HookEvent) -> HookDecision:
        """用 LLM 判断。prompt_template 中 {tool_name}/{tool_input} 等变量占位,
        期望 LLM 返回 JSON {permission_decision, reason}。"""
        if not self._adapter:
            return HookDecision(reason="prompt hook: no adapter injected", handler_name="prompt")
        prompt = config.prompt_template.format(
            tool_name=event.tool_name,
            tool_input=event.tool_input,
            tool_output=event.tool_output,
        )
        # 调用 adapter.complete,解析 JSON,返回 HookDecision
        # ...(省略细节,Phase 1 仅骨架)
        return HookDecision(handler_name="prompt")

    async def _execute_agent(self, config: HookHandlerConfig, event: HookEvent) -> HookDecision:
        """fork 子 Agent 判断(用于重度 policy 审查)。依赖 DOC-04 ForkManager。"""
        if not self._fork_manager:
            return HookDecision(reason="agent hook: no fork_manager injected", handler_name="agent")
        # briefing 注入事件,fork 子 Agent,等结果
        # ...(Phase 1 仅骨架)
        return HookDecision(handler_name="agent")
```

### 4. executor/harness/permissions/engine.py

```python
"""
Permission Engine — 分层权限模型

两层权限检查：
Layer 1 — 平台级护栏（全局，不可覆盖）:
  - 由 GuardrailsEngine 提供的规则
  - 破坏性操作（rm -rf, DROP TABLE 等）直接 deny
  - 敏感数据操作需要额外审查

Layer 2 — Hook 级权限（可配置）:
  - PreToolUse Hook 返回的 permission_decision
  - 支持 allow / deny / ask

快速检查优先（确定性规则 ms 级），Hook 审查兜底（可能秒级）。
"""

class PermissionEngine:
    """v4:加 ask() 方法,走 Redis BLPOP 协议"""

    def __init__(
        self,
        guardrails: "GuardrailsEngine",
        hook_system: HookSystem,
        ask_protocol: "PermissionAskProtocol",
    ):
        self._guardrails = guardrails
        self._hook_system = hook_system
        self._ask_protocol = ask_protocol

    async def check(
        self,
        tool_name: str,
        tool_input: dict,
        run_id: str,
    ) -> "PermissionResult":
        """
        对工具调用做权限决策(v4 支持 ask 反向通信)。

        返回 PermissionResult:
        - decision: "allow" | "deny"
        - reason: str
        - updated_input: dict | None(Hook 可能改写了输入)
        """
        # Layer 1: 平台级护栏(快速检查)
        guardrail_result = self._guardrails.check(tool_name, tool_input)
        if guardrail_result.decision == "deny":
            return guardrail_result

        # Layer 2: Hook 级权限
        event = HookEvent(
            event_type="PreToolUse",
            tool_name=tool_name,
            tool_input=tool_input,
            run_id=run_id,
        )
        hook_decision = await self._hook_system.fire(event)

        if hook_decision.permission_decision == "deny":
            return PermissionResult(
                decision="deny",
                reason=hook_decision.reason or "hook deny",
            )

        # v4 新增:ask 走反向通信
        if hook_decision.permission_decision == "ask":
            answer = await self._ask_protocol.ask(
                run_id=run_id,
                tool_name=tool_name,
                tool_input=tool_input,
                reason=hook_decision.reason or "需要用户确认",
            )
            prism_permission_ask_total.labels(decision=answer).inc()
            if answer == "deny":
                return PermissionResult(decision="deny", reason="user denied")

        return PermissionResult(
            decision="allow",
            updated_input=hook_decision.updated_input,
        )


@dataclass
class PermissionResult:
    decision: Literal["allow", "deny"]
    reason: str = ""
    updated_input: dict | None = None
```

### 4.1 executor/harness/permissions/ask_protocol.py(v4 新文件)

```python
"""
Permission Ask 反向通信协议(v4 新增, ADR-028)

子进程通过 Redis BLPOP 阻塞等待用户回答。
Backend 通过 SSE 把 permission_ask 事件推给前端。
用户点击后 Backend POST /sessions/{id}/permission-answer,RPUSH 到 Redis。
子进程 BLPOP 返回 → 继续执行。

超时(默认 300s)默认 deny(fail-safe)。
"""

import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, TYPE_CHECKING

import redis.asyncio as redis_async
import structlog

if TYPE_CHECKING:
    from executor.callbacks.backend_callback import BackendCallback

logger = structlog.get_logger()

PERMISSION_ASK_TIMEOUT_SECONDS = int(
    os.environ.get("PERMISSION_ASK_TIMEOUT_SECONDS", "300")
)


class PermissionAskProtocol:
    def __init__(self, redis_url: str, callback: "BackendCallback"):
        self._redis = redis_async.from_url(redis_url, decode_responses=True)
        self._callback = callback

    async def ask(
        self,
        run_id: str,
        tool_name: str,
        tool_input: dict,
        reason: str,
        timeout_seconds: int = PERMISSION_ASK_TIMEOUT_SECONDS,
    ) -> Literal["allow", "deny"]:
        """
        发起 permission ask 请求,阻塞等待用户回答。
        返回 'allow' 或 'deny'。超时默认 deny(fail-safe)。
        """
        request_id = str(uuid.uuid4())  # 若 Python 环境有 uuid7,改为 uuid7.create()
        answer_key = f"perm_answer:{request_id}"
        req_key = f"perm_req:{request_id}"
        timeout_at = datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds)

        # 记录请求到 Redis(供 Backend 查询/回查)
        await self._redis.setex(
            req_key,
            timeout_seconds,
            json.dumps({
                "run_id": run_id,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "reason": reason,
                "timeout_at": timeout_at.isoformat(),
            }),
        )

        # 通过 HTTP 回调推送 permission_ask 事件(Backend → SSE → 前端弹窗)
        await self._callback.permission_ask(
            request_id=request_id,
            tool_name=tool_name,
            tool_input=tool_input,
            reason=reason,
            timeout_at=timeout_at.isoformat(),
        )

        logger.info(
            "harness.permission_ask.pending",
            request_id=request_id,
            tool_name=tool_name,
            timeout_seconds=timeout_seconds,
        )

        # BLPOP 阻塞等待用户回答
        result = await self._redis.blpop(answer_key, timeout=timeout_seconds)

        if result is None:
            # 超时 → fail-safe deny
            logger.warning(
                "harness.permission_ask.timeout",
                request_id=request_id,
                tool_name=tool_name,
            )
            await self._callback.harness_event("permission_ask_timeout", {
                "request_id": request_id,
                "tool_name": tool_name,
            })
            return "deny"

        _, answer = result
        if answer not in ("allow", "deny"):
            logger.error(
                "harness.permission_ask.invalid_answer",
                request_id=request_id,
                answer=answer,
            )
            return "deny"

        logger.info(
            "harness.permission_ask.answered",
            request_id=request_id,
            tool_name=tool_name,
            decision=answer,
        )
        return answer

    async def close(self):
        await self._redis.aclose()
```

### 5. executor/harness/guardrails/engine.py + platform_rules.py

```python
# engine.py
"""
GuardrailsEngine — 声明式护栏规则引擎

平台级规则硬编码（不可被用户/插件覆盖）。
插件级规则随 Plugin 加载（DOC-05 实现）。
"""

class GuardrailsEngine:
    def __init__(self):
        self._rules: list[GuardrailRule] = []
        self._load_platform_rules()
    
    def _load_platform_rules(self) -> None:
        from executor.harness.guardrails.platform_rules import get_platform_rules
        self._rules.extend(get_platform_rules())
    
    def check(self, tool_name: str, tool_input: dict) -> PermissionResult:
        """对工具调用做确定性规则检查。O(rules) 复杂度，ms 级。"""
        for rule in self._rules:
            if rule.matches(tool_name, tool_input):
                return PermissionResult(decision="deny", reason=rule.reason)
        return PermissionResult(decision="allow")
```

```python
# platform_rules.py(v4 补齐 4 类规则)
"""
平台级内置护栏规则

这些规则全局生效,不可被插件或用户覆盖。
对标 DOC-00 v4 §7 四条铁律的 Harness 强制层。

v4 补齐 4 类规则:
1. 破坏性操作(rm / DROP / DELETE 全表 / FORMAT / mkfs)
2. 速率限制(单 run 同工具 >N 次/分钟)
3. PII 检测(api_key/secret/password/token 明文进入 tool_input)
4. 跨用户访问(tool_input 中用户 ID 与 run 的 user_id 不一致)
"""

import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

DANGEROUS_PATTERNS = [
    # Shell 破坏性命令
    r"rm\s+(-rf?|--recursive)",
    r"DROP\s+(TABLE|DATABASE)",
    r"DELETE\s+FROM\s+\w+\s*;?\s*$",  # 无 WHERE 的全表删除
    r"TRUNCATE\s+TABLE",
    r"FORMAT\s+",
    r"mkfs\.",
    r":\(\)\s*\{.*\};.*:\|:",          # fork bomb
    r">\s*/dev/sd[a-z]",                # 写 raw device
]

PII_PATTERNS = [
    r"(api[-_]?key|secret|password|token|bearer)\s*[:=]\s*[\"']?[\w\-\.]{16,}",
    r"\b[A-Z0-9]{20,}\b",                # AWS Key 形式
    r"sk-[A-Za-z0-9]{32,}",              # OpenAI Key 形式
    r"\bghp_[A-Za-z0-9]{20,}\b",         # GitHub PAT
]

# 速率限制:每个 (run_id, tool_name) 在 60s 内的调用次数不超过 limit
_rate_window: dict[tuple[str, str], deque] = defaultdict(deque)
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_PER_TOOL = {
    # 默认 30 次/分钟;特定工具有更低阈值
    "bash": 20,
    "Write": 50,
    "WebFetch": 10,
    "WebSearch": 10,
}
RATE_LIMIT_DEFAULT = 30


@dataclass
class GuardrailRule:
    id: str
    reason: str
    scope: str = "platform"
    tool_pattern: str = ".*"
    input_patterns: list = field(default_factory=list)
    # 钩子方式匹配(v4):自定义匹配函数,用于复杂规则
    custom_match: callable = None

    def matches(self, tool_name: str, tool_input: dict, run_context=None) -> bool:
        if not re.search(self.tool_pattern, tool_name):
            return False
        if self.custom_match:
            return self.custom_match(tool_name, tool_input, run_context)
        # 默认:对 tool_input 所有 string 值做 pattern 匹配
        flat = " ".join(str(v) for v in _flatten_values(tool_input))
        return any(re.search(p, flat, re.IGNORECASE) for p in self.input_patterns)


def _flatten_values(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _flatten_values(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _flatten_values(v)
    else:
        yield obj


def _rate_limit_check(tool_name: str, tool_input: dict, run_context) -> bool:
    """返回 True 表示触发限流(deny)"""
    if run_context is None:
        return False
    limit = RATE_LIMIT_PER_TOOL.get(tool_name, RATE_LIMIT_DEFAULT)
    key = (run_context.run_id, tool_name)
    now = time.monotonic()
    window = _rate_window[key]
    while window and now - window[0] > RATE_LIMIT_WINDOW_SECONDS:
        window.popleft()
    window.append(now)
    return len(window) > limit


def _cross_user_check(tool_name: str, tool_input: dict, run_context) -> bool:
    """若 tool_input 中出现其他用户的 ID,触发 deny"""
    if run_context is None:
        return False
    uid = getattr(run_context, "user_id", None)
    if not uid:
        return False
    # 保守:凡是 input 中出现 "user_id" 字段且不等于当前 run 的 user_id
    for key in ("user_id", "userId", "uid"):
        v = tool_input.get(key)
        if v and str(v) != str(uid):
            return True
    return False


def get_platform_rules() -> list[GuardrailRule]:
    rules = []

    # 1. 破坏性命令
    rules.append(GuardrailRule(
        id="GR-PLATFORM-001",
        tool_pattern=r"bash|Bash|shell|Shell",
        input_patterns=DANGEROUS_PATTERNS,
        reason="平台级护栏:检测到破坏性命令(rm/DROP/FORMAT/fork bomb 等)",
    ))

    # 2. PII 泄露(tool_input 中明文出现密钥)
    rules.append(GuardrailRule(
        id="GR-PLATFORM-002",
        tool_pattern=".*",
        input_patterns=PII_PATTERNS,
        reason="平台级护栏:tool_input 中检测到明文凭据/密钥",
    ))

    # 3. 速率限制
    rules.append(GuardrailRule(
        id="GR-PLATFORM-003",
        tool_pattern=".*",
        reason="平台级护栏:工具调用超过速率限制(60s 窗口)",
        custom_match=_rate_limit_check,
    ))

    # 4. 跨用户访问
    rules.append(GuardrailRule(
        id="GR-PLATFORM-004",
        tool_pattern=".*",
        reason="平台级护栏:检测到跨用户访问(tool_input 中 user_id 与 run 的 user_id 不符)",
        custom_match=_cross_user_check,
    ))

    return rules
```

### 6. 集成到 ToolExecutionPipeline

修改 `executor/tools/pipeline.py`：
- `__init__` 新增参数 `permission_engine: PermissionEngine | None = None`、`hook_system: HookSystem | None = None`
- `execute()` 方法中，替换 `HARNESS_INTEGRATION_POINT` 注释：
  - Step 3: `permission_result = await self._permission_engine.check(tool_name, tool_input, run_id)`
  - 如果 deny → 直接返回 ToolResultBlock(is_error=True, content=reason)
  - 如果 updated_input → 使用改写后的 input
  - Step 7: `await self._hook_system.fire(PostToolUse event)`

## 验证步骤

```bash
# 1. 编译检查（所有新文件）
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/harness/hooks/events.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/harness/hooks/system.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/harness/hooks/handlers.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/harness/permissions/engine.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/harness/guardrails/engine.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/harness/guardrails/platform_rules.py

# 2. 护栏规则测试
docker compose -f docker-compose.dev.yml exec backend python -c "
from executor.harness.guardrails.engine import GuardrailsEngine

engine = GuardrailsEngine()

# 危险命令应被拦截
result = engine.check('bash', {'command': 'rm -rf /'})
assert result.decision == 'deny', f'Expected deny, got {result.decision}'
print('Dangerous command blocked: PASS')

# 安全命令应放行
result = engine.check('bash', {'command': 'ls -la'})
assert result.decision == 'allow', f'Expected allow, got {result.decision}'
print('Safe command allowed: PASS')

# 非 bash 工具不受 bash 规则影响
result = engine.check('web_search', {'query': 'DROP TABLE users'})
assert result.decision == 'allow', 'Non-bash tool should not be blocked by bash rules'
print('Non-bash tool unaffected: PASS')

print('\\nAll Task 3.3 baseline checks passed!')
"

# 3. v4 HookDecision 合并规则测试
docker compose -f docker-compose.dev.yml exec backend python -c "
from executor.harness.hooks.decision import HookDecision, merge_decisions

# stop 最高优先级
r = merge_decisions([
    HookDecision(permission_decision='allow'),
    HookDecision(stop=True, stop_reason='admin abort'),
    HookDecision(permission_decision='deny'),  # 不应被看到
])
assert r.stop and r.stop_reason == 'admin abort'
print('Merge stop priority: PASS')

# deny > ask > allow
r = merge_decisions([
    HookDecision(permission_decision='allow'),
    HookDecision(permission_decision='ask'),
    HookDecision(permission_decision='deny'),
])
assert r.permission_decision == 'deny'
print('Merge permission severity: PASS')

# updated_input 冲突 → ValueError
try:
    merge_decisions([
        HookDecision(updated_input={'a': 1}),
        HookDecision(updated_input={'a': 2}),
    ])
    assert False, 'Expected ValueError'
except ValueError:
    print('Merge updated_input conflict: PASS')
"

# 4. v4 Permission ask 端到端测试(mock Redis BLPOP + 超时 + answer)
docker compose -f docker-compose.dev.yml exec backend python -c "
import asyncio
import redis.asyncio as redis_async
from executor.harness.permissions.ask_protocol import PermissionAskProtocol

class FakeCallback:
    async def permission_ask(self, **kwargs): pass
    async def harness_event(self, *a, **k): pass

async def _t():
    proto = PermissionAskProtocol('redis://redis:6379', FakeCallback())
    r = redis_async.from_url('redis://redis:6379', decode_responses=True)

    # 场景 1:用户在 2s 内回答 allow
    async def _answer():
        await asyncio.sleep(2)
        # 从 perm_req:* 找 request_id(测试简化:扫描最新)
        keys = await r.keys('perm_req:*')
        assert keys
        req_id = keys[0].split(':')[1]
        await r.rpush(f'perm_answer:{req_id}', 'allow')

    answer_task = asyncio.create_task(_answer())
    result = await proto.ask(run_id='r1', tool_name='Bash', tool_input={'cmd':'ls'}, reason='test', timeout_seconds=5)
    assert result == 'allow', f'Expected allow, got {result}'
    await answer_task
    print('Permission ask allow: PASS')

    # 场景 2:超时 → deny
    result = await proto.ask(run_id='r2', tool_name='Bash', tool_input={'cmd':'ls'}, reason='test', timeout_seconds=1)
    assert result == 'deny', f'Expected deny on timeout, got {result}'
    print('Permission ask timeout fail-safe: PASS')

    await proto.close(); await r.aclose()

asyncio.run(_t())
"
```

## 完成后

1. 更新 PROGRESS.md
2. 更新 DECISIONS.md:记录 **ADR-026(HookDecision 11 字段)/ADR-027(合并规则)/ADR-028(permission ask Redis BLPOP 协议)**
3. 加载 Simplify skill 审查
4. 加载 PJR skill 验证
5. `git add -A && git commit -m "feat(v4): HookDecision 11 fields + 4 handler types + permission ask Redis BLPOP protocol + platform guardrails 4 categories"`
```

---

## Task 3.4: Guardrails Engine 与 Feedback Loop(v4:结构化事件 + SessionEnd user_memory)

### Part A — 设计与解释

#### 问题陈述

Harness 的核心理念:**Agent 每次犯错,修复方式不是"换个 prompt 试试",而是"在 Harness 中新增一条永久性约束"。** Feedback Loop Engine 实现这个闭环——捕获失败事件,分析模式,生成新的护栏建议。

Phase 1 的 Feedback Loop 采用半自动模式(检测 + 告警 + 人工触发),不做全自动规则生成。

**v4 修订**:
1. Feedback 事件不再是自由格式 dict,必须结构化:`{event_type / severity / context / timestamp}`
2. Redis 缓存 feedback 事件时有明确 TTL(默认 7 天)
3. SessionEnd Hook 触发 **user_memory 提炼**:本 session 的要点由 LLM 凝练 → 通过 Backend 回调写入 `user_memories` 表(DOC-01 v4 新增 5 表之一)

#### CC 架构映射

CC 没有显式的 Feedback Loop,但 Anthropic 通过 Hooks 的 `PostToolUseFailure` 事件和 CLAUDE.md 的自我学习机制(auto-memory)实现了等效功能。Prism 将这个过程系统化。

CC 的 `SessionEnd` → `/memory` 命令结构化写入 `CLAUDE.md` 的模式,在 Prism 中对应 `SessionEnd Hook → user_memory 提炼 → user_memories 表`。

#### 设计决策(ADR)

- **ADR-029(feedback 事件结构化)**:所有 feedback_capture 事件必须是结构化 dataclass:
  - `event_type`:`tool_error` / `permission_deny` / `guardrail_hit` / `loop_detected` / `compaction_triggered`
  - `severity`:`info` / `warning` / `error` / `critical`
  - `context`:dict,含 run_id/session_id/tool_name/input_preview/reason
  - `timestamp`:ISO 8601

  来源:Batch 2 §A3-8。

- **ADR-030(SessionEnd user_memory 提炼)**:SessionEnd Hook 触发时,若 session.turns > 5:
  1. 收集本 session 所有 user/assistant 消息
  2. 用 LLM 生成 200 字以内的要点(决策 / 偏好 / 待办)
  3. 通过 BackendCallback.harness_event("user_memory_extracted", {content, source_session_id}) 上报
  4. Backend 写入 `user_memories` 表,后续 session 的 PromptAssembler 可读

  来源:Batch 2 §A3-9。

#### 验收标准(v4 扩展)

- FeedbackCaptureMiddleware 在 post_turn 阶段记录**结构化**失败事件(按 ADR-029 schema)
- Redis 缓存 feedback 事件 TTL 默认 7 天(`FEEDBACK_TTL_SECONDS=604800`)
- 失败事件通过 callback 上报 Backend,写入 audit_logs
- 提供查询接口:按 run_id / session_id / 时间范围查询失败模式
- **SessionEnd Hook 触发 user_memory 提炼**(当 turns > 5):LLM 生成 ≤200 字要点 → 通过 Backend 回调写入 user_memories 表
- Harness lifecycle controller 组装所有子系统(HookSystem + PermissionEngine + GuardrailsEngine + MiddlewarePipeline + AskProtocol)

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的 Feedback Loop 和 Harness 生命周期控制器。Task 3.1-3.3 已完成核心子系统。本 Task 实现失败捕获闭环，并通过 lifecycle.py 将所有 Harness 子系统组装为一个完整的 Runtime。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

Task 3.1-3.3 已完成

## 要创建的文件

```
executor/harness/
├── middleware/
│   └── feedback_capture.py    # 反馈采集中间件
└── lifecycle.py               # Harness 生命周期控制器
```

## 实现规范

### 1. executor/harness/middleware/feedback_capture.py

```python
"""
反馈采集中间件

在 post_turn 阶段检查本轮是否有：
- 工具执行失败（is_error = True）
- 护栏拦截（permission_decision = deny）
- 循环检测命中

将失败事件结构化记录，通过 callback 上报 Backend。
这些数据是 Entropy Detection（DOC-12）和手动 Feedback Loop 的基础。
"""

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Literal

FEEDBACK_TTL_SECONDS = int(os.environ.get("FEEDBACK_TTL_SECONDS", "604800"))  # 7 天


@dataclass
class FeedbackEvent:
    """v4 ADR-029:结构化 feedback 事件"""
    event_type: Literal[
        "tool_error", "permission_deny", "guardrail_hit",
        "loop_detected", "compaction_triggered",
    ]
    severity: Literal["info", "warning", "error", "critical"]
    context: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class FeedbackCaptureMiddleware(Middleware):
    name = "feedback_capture"

    def __init__(self, callback: BackendCallback, redis_client=None):
        self._callback = callback
        self._redis = redis_client
        self._failures_this_run: list[FeedbackEvent] = []

    async def post_turn(self, ctx) -> None:
        """扫描本轮结果,记录结构化失败事件"""
        events = self._extract_failures(ctx)
        for evt in events:
            self._failures_this_run.append(evt)
            await self._callback.harness_event("feedback_capture", asdict(evt))
            # Redis 缓存(TTL 7 天),供 Entropy Detector 扫描(DOC-12 Task 12.2)
            if self._redis:
                key = f"feedback:{ctx.run_id}:{evt.timestamp}"
                await self._redis.setex(key, FEEDBACK_TTL_SECONDS, json.dumps(asdict(evt)))
            prism_harness_feedback_total.labels(
                event_type=evt.event_type,
                severity=evt.severity,
            ).inc()

    def _extract_failures(self, ctx) -> list[FeedbackEvent]:
        """从 messages 尾部 + ctx.custom_data 提取失败事件"""
        events: list[FeedbackEvent] = []
        # 1. 最新 tool_result 是 is_error
        for msg in reversed(ctx.messages[-3:]):
            if getattr(msg, "role", None) == "user":
                for block in getattr(msg, "content", []):
                    if getattr(block, "is_error", False):
                        events.append(FeedbackEvent(
                            event_type="tool_error",
                            severity="error",
                            context={
                                "run_id": ctx.run_id,
                                "session_id": ctx.session_id,
                                "tool_use_id": getattr(block, "tool_use_id", None),
                                "preview": str(getattr(block, "content", ""))[:200],
                            },
                        ))
                break

        # 2. ctx.custom_data 中 Middleware 塞入的 guardrail/permission/loop 信号
        for sig in ctx.custom_data.get("feedback_signals", []):
            events.append(FeedbackEvent(**sig))

        return events

    def get_run_summary(self) -> dict:
        """返回本次 Run 的失败摘要,写入 runs.harness_summary"""
        by_type: dict[str, int] = {}
        for evt in self._failures_this_run:
            by_type[evt.event_type] = by_type.get(evt.event_type, 0) + 1
        return {
            "total_failures": len(self._failures_this_run),
            "failure_types": by_type,
        }
```

### 2. executor/harness/lifecycle.py

```python
"""
Harness 生命周期控制器

职责：一站式组装所有 Harness 子系统，返回给 __main__.py 使用。

初始化顺序：
1. GuardrailsEngine（平台级规则加载）
2. HookSystem（从配置文件加载 Hook）
3. PermissionEngine（组合 Guardrails + HookSystem）
4. MiddlewarePipeline（注册所有中间件）
5. 注入到 ToolExecutionPipeline 和 QueryEngine
"""

class HarnessRuntime:
    def __init__(
        self,
        run_id: str,
        session_id: str,
        user_id: str,
        callback: BackendCallback,
        redis_client,
        redis_url: str,
        adapter,
        settings,
    ):
        self.run_id = run_id
        self.session_id = session_id
        self.user_id = user_id
        self._callback = callback
        self._adapter = adapter

        self.guardrails = GuardrailsEngine()
        self.hook_system = HookSystem()
        self.ask_protocol = PermissionAskProtocol(redis_url=redis_url, callback=callback)  # v4
        self.permission_engine = PermissionEngine(
            guardrails=self.guardrails,
            hook_system=self.hook_system,
            ask_protocol=self.ask_protocol,       # v4 新增
        )

        self.feedback_mw = FeedbackCaptureMiddleware(callback, redis_client=redis_client)
        self.loop_mw = LoopDetectionMiddleware(
            window=settings.LOOP_DETECTION_WINDOW,
            redis_client=redis_client,
            run_id=run_id,
            callback=callback,
        )
        self.observability_mw = ObservabilityMiddleware(callback)

        self.middleware = MiddlewarePipeline()
        self.middleware.register(self.loop_mw)
        self.middleware.register(self.observability_mw)
        self.middleware.register(self.feedback_mw)

    def inject_into_pipeline(self, pipeline: ToolExecutionPipeline) -> None:
        """将 Harness 子系统注入到 ToolExecutionPipeline"""
        pipeline._permission_engine = self.permission_engine
        pipeline._hook_system = self.hook_system

    async def on_session_start(self) -> None:
        """触发 SessionStart Hook"""
        await self.hook_system.fire(HookEvent(
            event_type="SessionStart",
            run_id=self.run_id,
            session_id=self.session_id,
        ))

    async def on_session_end(self, messages: list, turn_count: int) -> None:
        """
        v4 ADR-030:SessionEnd Hook + user_memory 提炼
        """
        await self.hook_system.fire(HookEvent(
            event_type="SessionEnd",
            run_id=self.run_id,
            session_id=self.session_id,
        ))

        # turns > 5 才提炼(短会话无价值)
        if turn_count <= 5:
            return

        # LLM 凝练要点
        history_text = "\n\n".join(
            f"{m.role}: {_extract_text(m)}"
            for m in messages
            if m.role in ("user", "assistant")
        )[:12000]  # 保守裁剪,避免提炼 prompt 超长

        prompt = (
            "请从以下对话中凝练出对下次会话有价值的要点,以要点列表输出,"
            "≤200 字。重点抓:1) 用户明确偏好/禁令;2) 达成的关键决策;"
            "3) 未完成的事项。不要复述对话。\n\n" + history_text
        )

        try:
            resp = await self._adapter.complete(
                messages=[PrismMessage(role="user", content=[TextBlock(text=prompt)])],
                system_prompt="你是要点提炼工具。只输出要点列表,不说其他。",
                max_tokens=400,
            )
            content = resp.messages[0].content[0].text.strip()
            if content:
                await self._callback.harness_event("user_memory_extracted", {
                    "content": content,
                    "source_session_id": self.session_id,
                    "source_run_id": self.run_id,
                })
                prism_harness_memory_extracted_total.inc()
        except Exception as e:
            logger.warning("harness.memory.extract_failed", error=str(e))

    def get_run_harness_summary(self) -> dict:
        """返回完整的 Harness 运行摘要(写入 runs.harness_summary)"""
        return {
            **self.feedback_mw.get_run_summary(),
            "middleware_count": len(self.middleware._middlewares),
            "guardrail_rules_count": len(self.guardrails._rules),
        }


def _extract_text(msg) -> str:
    """从 PrismMessage content 提取首个 text 块"""
    for block in getattr(msg, "content", []):
        if hasattr(block, "text"):
            return block.text
    return ""
```

### 3. 更新 executor/__main__.py

替换 `HARNESS_INTEGRATION_POINT` 注释为实际代码：
```python
# 初始化 Harness Runtime
harness = HarnessRuntime(run_id=args.run_id, callback=callback, redis_client=redis, settings=settings)
harness.inject_into_pipeline(pipeline)
await harness.on_session_start()

# 初始化 QueryEngine（传入 middleware）
engine = QueryEngine(..., middleware_pipeline=harness.middleware)

# 执行
await engine.run(run.prompt)

# 收尾
await harness.on_session_end()
# 将 harness_summary 写回 runs 表
```

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/harness/middleware/feedback_capture.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/harness/lifecycle.py

# 2. HarnessRuntime 组装测试
docker compose -f docker-compose.dev.yml exec backend python -c "
from executor.harness.lifecycle import HarnessRuntime
from executor.callbacks.backend_callback import BackendCallback

# 用 mock callback 测试组装
class MockCallback:
    async def harness_event(self, *a, **kw): pass

class MockRedis: pass
class MockSettings:
    LOOP_DETECTION_WINDOW = 5

harness = HarnessRuntime('test-run', MockCallback(), MockRedis(), MockSettings())
assert harness.guardrails is not None
assert harness.hook_system is not None
assert harness.permission_engine is not None
assert len(harness.middleware._middlewares) == 3
print('HarnessRuntime assembly: PASS')

summary = harness.get_run_harness_summary()
assert 'total_failures' in summary
assert 'middleware_count' in summary
print('Harness summary: PASS')

print('\nAll Task 3.4 checks passed!')
"
```

## 完成后

1. 更新 PROGRESS.md
2. 更新 DECISIONS.md：记录 ADR-010（Feedback Loop 半自动模式——检测+告警+人工触发）
3. 加载 Simplify skill 审查
4. 加载 PJR skill 验证
5. `git add -A && git commit -m "feat: Feedback Loop + HarnessRuntime lifecycle controller"`
```

---

## Task 3.5: 4 级 Compaction Pipeline 与 6 层 Memory(v4:按回合组原子裁剪 + is_skill_context 优先保留)

### Part A — 设计与解释

#### 问题陈述

CC 源码揭示了最精妙的设计之一:4 级渐进式上下文压缩。不是简单地"满了就截断",而是按从低成本到高成本的顺序,逐级释放空间,每级牺牲不同类型的信息。Prism v2 的 `ContextBudgetManager`(Task 2.4)只实现了 Tier 0 基础能力,本 Task 补完 4 级 Compaction Pipeline。

同时实现 6 层 Memory 系统,确保 Agent 不从零开始——对标 CC 的 CLAUDE.md + auto-memory + session history。

**v4 核心修订(ADR-029 / ADR-030)**:
1. **所有裁剪必须以"回合组"为原子单元**——一个回合组是一次 assistant 响应(含 text + tool_use)及其对应的 tool_result(单条 user message,canonical Anthropic 语义)。按 index 裁剪会破坏 tool_use ↔ tool_result 配对导致 API 报 400。
2. **is_skill_context=True 的消息优先保留**——Skill 注入的上下文不参与压缩,只有在 Tier 4 兜底时才能被裁。
3. 阈值调整:Tier 1 的阈值从 80% 下调到 60%(CC 的实测阈值),Tier 2 从 85% 保持,Tier 3 在 SessionEnd 触发(而非阈值),Tier 4 仍为 API 报错 fallback。

#### CC 架构映射

```
Token 使用量 ──────────────────────────────────────▶
0%        80%         85%         90%        98%
│          │           │           │          │
│ Normal   │ Tier 1    │ Tier 2    │ Tier 3   │ BLOCK
│ operation│ micro-    │ auto-     │ session  │ (hard
│          │ compact   │ compact   │ memory   │ stop)
│          │ (clear    │ (full     │ compact  │
│          │ old tool  │ summary   │ (extract │
│          │ results)  │ of old    │ to       │
│          │           │ msgs)     │ memory)  │
```

CC 的 6 层 Memory：
1. `/etc/claude-code/CLAUDE.md`（全局）
2. `~/.claude/CLAUDE.md`（用户）
3. `./CLAUDE.md`（项目）
4. `./.claude/CLAUDE.md`（项目内部）
5. `./.claude/rules/*.md`（项目规则）
6. `./CLAUDE.local.md`（本地）

Prism 适配为：
1. Platform memory（系统内置行为规范——PromptAssembler 静态 section 承担）
2. User memory（用户级偏好——DB user 配置）
3. Session memory（会话级——Compaction Tier 3 提取的关键信息）
4. Auto memory（自动学习——PostToolUse 成功模式记录）
5. Skill memory（Skill 注入的上下文——按需加载）
6. Team memory（未来多用户协作——Phase 2）

> **Phase 分期**:Phase 1 先实现 2 层 Memory:
> 1. **Session Memory**(Layer 1,会话级上下文)— 必需,TAOR 循环的基础,存在 messages 表 + Redis 缓存
> 2. **User Memory**(Layer 2,用户级偏好/历史)— 跨会话延续性,存在 `user_memories` 表(DOC-01 v4 新增)
>
> 其余 4 层(Project Memory, Tool Memory, Agent Memory, Global Memory)在 Phase 1 中预留接口定义(`MemoryLayer` 抽象基类 + `MemoryManager.get_layer()` 方法签名),Phase 2 按需实现。

#### 设计决策(ADR)

- **ADR-029(Compaction 按回合组原子裁剪)**:裁剪的最小单元是"回合组"(turn group),由 ContextBudgetManager.identify_turn_groups() 识别。定义:相邻的 `assistant(text + tool_use*)` + `user(tool_result*)` 构成一个回合组。裁剪时整组保留或整组裁掉,绝不按 message index 裁。这是因为 Anthropic 要求 tool_use ↔ tool_result 必须配对出现,任何"半组"都会导致 400 Bad Request。来源:Batch 2 §A3-3, Master M4。

- **ADR-030(is_skill_context 优先保留)**:PrismMessage 的 `is_skill_context: bool` 字段(见 DOC-02 v4 Task 2.2)标记该消息来自 Skill 注入。Compaction Tier 1/2/3 均不能裁 is_skill_context=True 的消息,仅 Tier 4 紧急兜底时可裁。来源:Batch 2 §A3-3。

#### 验收标准(v4 扩展)

- 4 级 Compaction 按阈值自动触发
- **所有级别按回合组为原子单元裁剪,裁剪后 messages 仍能通过 Anthropic API 校验**(tool_use 必有对应 tool_result)
- Tier 1(micro-compact,≥60%)裁掉最老 1 个回合组,保留所有 is_skill_context
- Tier 2(auto-compact,≥85%)LLM 生成历史摘要替换最老 50% 回合组(token 消耗约 500 for 摘要)
- Tier 3(session memory)在 SessionEnd Hook 触发,提炼要点到 user_memories 表(见 Task 3.4 ADR-030)
- Tier 4(reactive)API 返回 context_too_long 错误时触发,强制裁到最近 3 个回合组 + 所有 skill_context
- Memory 系统在 Session 开始时加载 user_memories(如有),PromptAssembler 注入到 `<memory>` section

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的 4 级 Compaction Pipeline 和 Memory 系统。Task 2.4 的 ContextBudgetManager 提供了 Tier 0 基础能力（token 估算 + 工具截断）。本 Task 在其上扩展完整的 4 级渐进式压缩和 6 层 Memory 加载。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

Task 3.1-3.4 已完成，QueryEngine + HarnessRuntime 可运行

## 要创建的文件

```
executor/engine/
├── compaction.py              # 4 级 Compaction Pipeline
└── memory.py                  # 6 层 Memory 系统
```

## 实现规范

### 1. executor/engine/compaction.py

```python
"""
4 级渐进式 Compaction Pipeline

对标 CC 的 multi-tier compaction：
- Tier 1 (micro-compact, ~80% 阈值): 清除旧工具结果
  目标 tool 类型: FileRead, Bash, WebSearch, WebFetch, Grep
  只清除超过 N 轮前的结果，替换为 "[旧工具结果已清除]"
  信息损失最小，token 释放效率高

- Tier 2 (auto-compact, ~85% 阈值): 调用模型生成摘要
  将 Tier 1 后仍然过长的旧消息段调用模型生成摘要
  保留最近 M 条消息不动
  消耗约 1000-2000 token 用于摘要生成
  需要通过 ModelAdapter 调用模型（complete 模式，非 stream）

- Tier 3 (session memory compact, ~90% 阈值): 提取到持久化
  将历史中的关键决策/发现提取为结构化 memory
  写入 DB（session.config_snapshot 或专用字段）
  下次 Session 恢复时重新加载

- Tier 4 (reactive, ~98% 或 API 报错): 紧急截断
  当 API 返回 context_too_long 错误时触发
  激进截断：只保留 system_prompt + 最近 K 条消息
  最后手段，信息损失最大

每级有断路器防止无限重试。
"""

class CompactionPipeline:
    """v4:按回合组原子裁剪的 4 级 Compaction"""

    # v4 阈值配置(占 max_context_tokens 的百分比)
    TIER1_THRESHOLD = 0.60   # v4:60%(CC 实测阈值)
    TIER2_THRESHOLD = 0.85
    # Tier 3 不再按阈值触发,在 SessionEnd Hook 触发(Task 3.4 ADR-030)
    # Tier 4 在 API 报 context_too_long 错误时触发(由 Adapter 捕获后调用)

    def __init__(
        self,
        budget: ContextBudgetManager,
        adapter: ModelAdapter,   # Tier 2 需要调用模型
        callback: BackendCallback,
    ):
        self._budget = budget
        self._adapter = adapter
        self._callback = callback

    async def maybe_compact(
        self,
        messages: list[PrismMessage],
        system_prompt: str,
    ) -> list[PrismMessage]:
        """
        入口:根据阈值决定是否触发哪一级 Compaction。
        Tier 3 / Tier 4 不在此处触发:
          - Tier 3 由 SessionEnd Hook 触发(Task 3.4 HarnessRuntime.on_session_end)
          - Tier 4 由 Adapter 捕获 context_too_long 异常后调用 reactive_truncate()
        """
        current = self._budget.estimate_messages_tokens(messages, system_prompt)
        max_tokens = self._budget._max_context_tokens - self._budget._reserve_for_response
        usage_ratio = current / max_tokens if max_tokens > 0 else 0

        if usage_ratio >= self.TIER2_THRESHOLD:
            return await self._tier2_auto_compact(messages, system_prompt, current)
        elif usage_ratio >= self.TIER1_THRESHOLD:
            return self._tier1_micro_compact(messages, current)
        return messages

    # ---------------- Tier 1 ----------------

    def _tier1_micro_compact(
        self,
        messages: list[PrismMessage],
        before_tokens: int,
    ) -> list[PrismMessage]:
        """
        Tier 1:裁最老 1 个回合组。
        ADR-029:按回合组为原子单元(identify_turn_groups 识别)
        ADR-030:is_skill_context=True 的消息必须保留
        """
        groups = self._budget.identify_turn_groups(messages)
        if len(groups) <= 2:
            return messages

        # 保留第 2 组到最后 + 所有 is_skill_context
        to_keep = set()
        for start, end in groups[1:]:
            to_keep.update(range(start, end + 1))

        result = [
            msg for i, msg in enumerate(messages)
            if i in to_keep or getattr(msg, "is_skill_context", False)
        ]

        after_tokens = self._budget.estimate_messages_tokens(result, "")
        asyncio.create_task(self._callback.compaction_in_progress(
            tier=1,
            before_tokens=before_tokens,
            after_tokens=after_tokens,
        ))
        prism_compaction_total.labels(tier="1").inc()
        return result

    # ---------------- Tier 2 ----------------

    async def _tier2_auto_compact(
        self,
        messages: list[PrismMessage],
        system_prompt: str,
        before_tokens: int,
    ) -> list[PrismMessage]:
        """
        Tier 2:LLM 摘要替换最老的 50% 回合组。
        skill_context 消息一律保留(不参与摘要)。
        """
        groups = self._budget.identify_turn_groups(messages)
        if len(groups) <= 3:
            return messages

        split_point = len(groups) // 2
        old_groups = groups[:split_point]
        recent_groups = groups[split_point:]

        old_indices = set()
        for start, end in old_groups:
            old_indices.update(range(start, end + 1))
        old_messages = [
            msg for i, msg in enumerate(messages)
            if i in old_indices and not getattr(msg, "is_skill_context", False)
        ]

        summary_prompt = (
            "请将以下对话历史凝练为 200 字内的摘要,保留关键决策、"
            "工具调用结果、未完成事项:\n\n"
        )
        for msg in old_messages:
            summary_prompt += f"{msg.role}: {_extract_text(msg)}\n\n"

        summary_response = await self._adapter.complete(
            messages=[PrismMessage(role="user", content=[TextBlock(text=summary_prompt)])],
            system_prompt="你是对话历史压缩工具。只输出摘要,不说其他。",
            max_tokens=500,
        )
        summary_text = summary_response.messages[0].content[0].text

        # 构造新 messages:摘要消息 + 保留的回合组 + 所有 skill_context
        result: list[PrismMessage] = [
            PrismMessage(
                role="user",
                content=[TextBlock(text=f"[历史对话摘要]\n{summary_text}")],
            )
        ]

        recent_indices = set()
        for start, end in recent_groups:
            recent_indices.update(range(start, end + 1))

        for i, msg in enumerate(messages):
            if i in recent_indices:
                result.append(msg)
            elif getattr(msg, "is_skill_context", False):
                result.append(msg)

        after_tokens = self._budget.estimate_messages_tokens(result, system_prompt)
        await self._callback.compaction_in_progress(
            tier=2,
            before_tokens=before_tokens,
            after_tokens=after_tokens,
        )
        prism_compaction_total.labels(tier="2").inc()
        return result

    # ---------------- Tier 4(紧急兜底)----------------

    def reactive_truncate(
        self,
        messages: list[PrismMessage],
    ) -> list[PrismMessage]:
        """
        Tier 4:API 报 context_too_long 时紧急裁剪。
        强制裁到最近 3 个回合组 + 所有 skill_context。
        """
        groups = self._budget.identify_turn_groups(messages)
        keep_groups = groups[-3:] if len(groups) >= 3 else groups

        keep_indices = set()
        for start, end in keep_groups:
            keep_indices.update(range(start, end + 1))

        result = [
            msg for i, msg in enumerate(messages)
            if i in keep_indices or getattr(msg, "is_skill_context", False)
        ]
        # 开头插入告警 hint(not a skill_context,可参与后续裁剪)
        hint = PrismMessage(
            role="user",
            content=[TextBlock(text="[上下文已紧急压缩,部分历史信息丢失]")],
        )
        prism_compaction_total.labels(tier="4").inc()
        return [hint] + result
```

### 2. executor/engine/memory.py

```python
"""
6 层 Memory 系统

在 Session 开始时加载所有层级的 memory，
注入到 PromptAssembler 的动态 section 中。

层级（优先级从低到高）：
1. Platform — PromptAssembler 静态 section 已覆盖
2. User — 用户偏好（从 DB 加载）
3. Session — 会话级记忆（Tier 3 Compaction 产出）
4. Auto — 自动学习的成功模式（从历史 runs 提取）
5. Skill — Skill 注入（PluginHost 加载时提供）
6. Team — 多用户协作记忆（Phase 2，预留接口）
"""

from abc import ABC, abstractmethod


class MemoryLayer(ABC):
    """v4:6 层 Memory 抽象基类,Phase 1 只实现 Layer 1/2"""

    @abstractmethod
    async def load(self) -> str | None:
        ...


class SessionMemory(MemoryLayer):
    """Layer 1:会话级上下文。Phase 1 实现:从 messages 表读本 session 已压缩摘要。"""

    def __init__(self, session_id: str, db_session):
        self._session_id = session_id
        self._db = db_session

    async def load(self) -> str | None:
        # sessions 表 config_snapshot 或 messages 表最早的 `[历史对话摘要]` 消息
        row = self._db.execute(
            "SELECT config_snapshot FROM sessions WHERE id = :sid",
            {"sid": self._session_id},
        ).first()
        if row and row.config_snapshot:
            return row.config_snapshot.get("session_memory")
        return None


class UserMemory(MemoryLayer):
    """Layer 2:用户级偏好/历史。v4:查 user_memories 表(DOC-01 v4 新增)。"""

    def __init__(self, user_id: str, db_session):
        self._user_id = user_id
        self._db = db_session

    async def load(self) -> str | None:
        # v4:从 user_memories 表聚合最近 N 条
        rows = self._db.execute(
            """
            SELECT content FROM user_memories
            WHERE user_id = :uid
            ORDER BY created_at DESC
            LIMIT 10
            """,
            {"uid": self._user_id},
        ).fetchall()
        if not rows:
            return None
        return "\n\n---\n\n".join(r.content for r in rows)


class MemoryManager:
    """v4:Phase 1 加载 Layer 1 + Layer 2,其余 4 层返回空字符串"""

    def __init__(self, user_id: str, session_id: str, db_session):
        self._layers: dict[int, MemoryLayer] = {
            1: SessionMemory(session_id, db_session),
            2: UserMemory(user_id, db_session),
            # Layer 3/4/5/6 Phase 2
        }

    def get_layer(self, layer: int) -> MemoryLayer | None:
        """供 Phase 2 按需扩展使用"""
        return self._layers.get(layer)

    async def load(self) -> str:
        """
        加载所有已实现层级 memory,拼接为字符串。
        返回的字符串注入到 PromptAssembler.build(memory=...) 中。
        """
        parts: list[str] = []

        # Layer 2: User memory(优先,内容更稳定)
        user_mem = await self._layers[2].load()
        if user_mem:
            parts.append(f"## 用户长期偏好与历史要点\n{user_mem}")

        # Layer 1: Session memory
        session_mem = await self._layers[1].load()
        if session_mem:
            parts.append(f"## 本会话历史摘要\n{session_mem}")

        return "\n\n".join(parts) if parts else ""
```

### 3. 集成到 QueryEngine

修改 `executor/engine/query_engine.py`：
- `__init__` 新增参数 `compaction: CompactionPipeline`
- 替换原有的 `self._budget.should_compress` + `self._budget.compress_history` 调用为：
  ```python
  self._messages = await self._compaction.check_and_compact(self._messages, system_prompt)
  ```

修改 `executor/harness/lifecycle.py`：
- `HarnessRuntime.__init__` 中初始化 `CompactionPipeline` 和 `MemoryManager`
- 在 Session 开始时调用 `memory_manager.load()` 传给 PromptAssembler

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/engine/compaction.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/engine/memory.py

# 2. Compaction 单元测试
docker compose -f docker-compose.dev.yml exec backend python -c "
from executor.engine.compaction import CompactionPipeline
from executor.engine.context_budget import ContextBudgetManager
from executor.adapters.base import PrismMessage, TextBlock, ToolResultBlock

budget = ContextBudgetManager(max_context_tokens=1000, tool_result_max_chars=5000)

# 构造大量消息模拟上下文膨胀
messages = []
for i in range(50):
    messages.append(PrismMessage(role='user', content=[TextBlock(text=f'问题 {i}')]))
    messages.append(PrismMessage(role='assistant', content=[TextBlock(text='x' * 500)]))

# 验证 Tier 1 micro-compact
pipeline = CompactionPipeline(budget, adapter=None, callback=None)
compacted = pipeline._tier1_micro_compact(messages.copy())
# 应该比原始短（旧工具结果被清除）
print(f'Original messages: {len(messages)}, After Tier 1: {len(compacted)}')
print('Tier 1 micro-compact: PASS')

# 验证 Tier 4 reactive
emergency = pipeline._tier4_reactive(messages.copy())
assert len(emergency) <= 11, f'Tier 4 should keep <=11 messages, got {len(emergency)}'  # 1 system hint + 5 pairs
print('Tier 4 reactive: PASS')

print('\nAll Task 3.5 checks passed!')
"
```

## 完成后

1. 更新 PROGRESS.md
2. 更新 DECISIONS.md：记录 ADR-011（4 级渐进式 Compaction——每级牺牲不同类型信息换取空间）、ADR-012（6 层 Memory 系统——Agent 不从零开始）
3. 加载 Simplify skill 审查
4. 加载 PJR skill 验证
5. `git add -A && git commit -m "feat: 4-tier Compaction Pipeline + 6-layer Memory System"`
```

---

## Task 3.6: Harness 垂类配置(v4 简化:2 源 + 删除 PATCH 运行时 API)

### Part A — 设计与解释

#### 问题陈述

Prism v2 的 Harness Runtime(Task 3.1-3.5)目前采用"全部硬编码"方式——底层框架和垂类规则混在同一层,修改任何 Guardrail 规则或 Permission 策略都需要重启服务。

**v3.1 原设计(4 源 + 运行时 PATCH)的问题**:
1. DB 配置 + 文件配置 + 硬编码 + Plugin 注入 = 4 源,合并逻辑复杂,bug 多
2. PATCH /harness/config 运行时修改规则,会造成"正在执行的 Run 配置漂移"
3. toggle_middleware 运行时开关使 Middleware 生命周期不可预测
4. 跨进程同步 Redis pub/sub 机制脆弱(子进程可能已经读旧配置在 TAOR 循环中)

**v4 简化(ADR-031)**:
- 配置源从 4 源砍到 **2 源**:代码默认(`harness_defaults.py` 硬编码)+ `harness_config.yaml`(部署时配置)
- **删除** PATCH /harness/config 运行时 API(保留 GET readonly)
- **删除** toggle_middleware 运行时开关
- 配置变更 → 重启服务(或 reload 子进程启动参数)
- Plugin 级配置在 Plugin 加载时一次性 merge 进 effective config,Plugin 卸载时回退到 base config — 不在运行时动态注入

#### 设计原则(v4 简化)

| 层级 | 包含内容 | 更新方式 | 理由 |
|------|---------|---------|------|
| **代码默认(底层)** | TAOR 主循环框架、MiddlewarePipeline 分发机制、HookSystem 事件分发器、PermissionEngine 决策框架、CircuitBreaker 熔断框架、CompactionPipeline 四级策略框架 + 默认 Guardrail / Permission 常量 | 代码更新 + 重启 | 通用性强,改动易出问题,稳定性优先 |
| **harness_config.yaml(部署配置)** | Guardrail 自定义规则、Permission 策略、Middleware 启停与参数、Hook 注册表、Agent 行为约束 | 改文件 + 重启服务 | 部署期定版本,运行期稳定 |

#### 设计决策(ADR)

- **ADR-031(Harness 配置 2 源化 + 禁止运行时修改)**:
  - 配置源仅 2 个:代码默认 + harness_config.yaml
  - GET /harness/config:返回 effective config + source_trace(readonly)
  - **PATCH /harness/config 删除**
  - toggle_middleware 运行时开关删除
  - reload 改为通过"停止现有 subprocess → 等队列空 → 新 run 启动时加载新配置"的方式
  - Plugin 级配置在插件 install 时一次性写入 harness_config.yaml 的 plugins 段,卸载时移除该段 + 重启

  来源:Batch 2 §A3-10, Master M8。

#### HarnessConfigLoader(v4 简化版)

```python
"""
executor/harness/config_loader.py(v4 简化版)

配置加载器(非运行时管理器):
- 只在子进程启动时调用一次
- 无运行时 reload 逻辑
- 无 Redis pub/sub 同步
- 无 DB 读取

2 源合并策略:
  1. 代码默认(executor/harness/defaults.py 常量导入)
  2. harness_config.yaml(部署文件)

平台级规则(platform_rules.py)单独加载,不在此合并(它们独立于 Harness 配置,
属于"无论如何不可关闭的底线")。
"""

from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class HarnessEffectiveConfig:
    """合并后的最终有效配置(v4:简化字段)"""
    # Guardrail 规则(平台级由 platform_rules.py 独立提供,这里仅含 yaml 自定义)
    custom_guardrail_rules: list = field(default_factory=list)
    # Permission 策略:tool_name → "allow" | "deny" | "ask"
    permission_policies: dict = field(default_factory=dict)
    # Middleware 启停 + 参数:mw_name → {enabled, params}
    middleware_config: dict = field(default_factory=dict)
    # Hook 注册
    hook_registrations: list = field(default_factory=list)
    # Agent 行为约束:agent_type → [constraint_text]
    agent_constraints: dict = field(default_factory=dict)
    # v4 新增:每个字段的来源标注(debug 用)
    source_trace: dict = field(default_factory=dict)


class HarnessConfigLoader:
    """v4:启动时一次性加载,运行时不变"""

    def __init__(self, config_file_path: str | None):
        self._config_file_path = config_file_path

    def load(self) -> HarnessEffectiveConfig:
        """
        合并 2 源,返回 effective config。
        source_trace:每字段标注来源("default" | "yaml")
        """
        from executor.harness.defaults import (
            DEFAULT_PERMISSION_POLICIES,
            DEFAULT_MIDDLEWARE_CONFIG,
            DEFAULT_AGENT_CONSTRAINTS,
        )

        # 1. 先用代码默认填充
        cfg = HarnessEffectiveConfig(
            custom_guardrail_rules=[],
            permission_policies=dict(DEFAULT_PERMISSION_POLICIES),
            middleware_config=dict(DEFAULT_MIDDLEWARE_CONFIG),
            agent_constraints=dict(DEFAULT_AGENT_CONSTRAINTS),
        )
        for k in cfg.permission_policies:
            cfg.source_trace[f"permission_policies.{k}"] = "default"
        for k in cfg.middleware_config:
            cfg.source_trace[f"middleware_config.{k}"] = "default"
        for k in cfg.agent_constraints:
            cfg.source_trace[f"agent_constraints.{k}"] = "default"

        # 2. yaml 覆盖
        if self._config_file_path and Path(self._config_file_path).exists():
            with open(self._config_file_path) as f:
                data = yaml.safe_load(f) or {}

            for rule in data.get("guardrails", {}).get("custom_rules", []):
                cfg.custom_guardrail_rules.append(rule)
                cfg.source_trace[f"guardrail.{rule.get('id','?')}"] = "yaml"

            for tool, policy in data.get("permissions", {}).get("tool_overrides", {}).items():
                cfg.permission_policies[tool] = policy
                cfg.source_trace[f"permission_policies.{tool}"] = "yaml"

            for mw, params in data.get("middlewares", {}).items():
                cfg.middleware_config[mw] = params
                cfg.source_trace[f"middleware_config.{mw}"] = "yaml"

            for agent_type, constraints in data.get("agent_constraints", {}).items():
                cfg.agent_constraints[agent_type] = constraints
                cfg.source_trace[f"agent_constraints.{agent_type}"] = "yaml"

            for hook in data.get("hooks", {}).get("registrations", []):
                cfg.hook_registrations.append(hook)
                cfg.source_trace[f"hook.{hook.get('event','?')}"] = "yaml"

        return cfg
```

#### API 端点(v4 简化)

```
GET    /harness/config          — 返回当前 effective config + source_trace(readonly,admin only)
# PATCH /harness/config          — 【v4 删除】不再提供运行时修改
# POST  /harness/config/reload   — 【v4 删除】reload 通过重启服务实现
# POST  /harness/middleware/toggle — 【v4 删除】运行时开关禁用
```

#### 配置文件格式

```yaml
# .prism/harness_config.yaml
# Harness 垂类配置文件 — 运行时热更新

version: "1.0"

guardrails:
  custom_rules:
    - id: GR-CUSTOM-001
      trigger: pre_tool_use
      condition:
        tool_name: bash
        input_contains: ["rm -rf", "DROP TABLE", "DELETE FROM"]
      action: block
      message: "检测到破坏性操作，已拦截"

    - id: GR-CUSTOM-002
      trigger: post_tool_use
      condition:
        output_contains: ["投资建议", "建议买入", "建议卖出"]
      action: block
      message: "检测到投资建议内容，已拦截（铁律 1）"

middlewares:
  loop_detection:
    enabled: true
    params:
      window_size: 5
      max_identical: 3

  rate_limit:
    enabled: true
    params:
      max_tool_calls_per_minute: 30
      max_tokens_per_minute: 100000

  output_validation:
    enabled: true

  feedback_capture:
    enabled: true

  observability:
    enabled: true

permissions:
  default_mode: balanced   # strict / balanced / permissive
  tool_overrides:
    bash: ask_user
    file_write: ask_user
    file_delete: deny
    web_search: allow
    skill_install: ask_user

agent_constraints:
  research:
    - "你是只读探索者。绝对不能创建、修改、删除任何文件或数据。"
  planner:
    - "你是规划者。只输出 step-by-step 计划，不执行任何操作。"
  verifier:
    - "你是验证者。你的工作是尝试打破系统，发现问题。"
  plugin_builder:
    - "严禁一键生成。必须进入多轮需求收集流程。"
```

#### 与现有子系统的集成(v4 简化)

| 子系统 | v4 实现 |
|--------|--------|
| GuardrailsEngine | `platform_rules.py` 硬编码(不可覆盖)+ `HarnessConfigLoader.load().custom_guardrail_rules`(yaml 补充) |
| PermissionEngine | 启动时从 `HarnessConfigLoader.load().permission_policies` 读取 tool 粒度策略 |
| MiddlewarePipeline | 启动时从配置按 `middleware_config[mw_name].enabled` 过滤注册。**运行时无法增减** |
| HookSystem | 启动时从 `hook_registrations` 加载。运行时无 toggle |
| Agent 行为约束 | `prompt_sections.py` 硬编码 + `agent_constraints[agent_type]`(yaml 补充) |

#### 验收标准(v4)

- 启动时 `HarnessConfigLoader.load()` 合并代码默认 + yaml,`source_trace` 标注每字段来源
- `GET /harness/config` 返回 `{effective, source_trace}`,readonly
- **不存在** PATCH /harness/config 端点(尝试调用返回 405)
- **不存在** toggle_middleware API
- yaml 格式错误 → 子进程启动失败(快速失败,不吞错)
- 平台级规则(platform_rules.py 的 4 条)不受 yaml 影响,始终生效
- 配置变更需要重启服务(或让现有 Run 跑完后新 Run 用新配置)

---

### Part B — Claude Code 执行 Prompt

> **v4 Observability 采集要求(本 Task 所有代码适用)**:
> - 所有 logger 用 `structlog.get_logger()`,事件名 `harness.config.loaded` / `harness.config.load_failed`
> - Prometheus:`prism_harness_config_load_total.labels(source=...).inc()`
> - 详细规范见 DOC-12 v4 Task 12.4/12.5/12.6

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在实现 Harness 配置加载器(v4 简化版)。原 v3.1 设计是 4 源动态合并 + 运行时 PATCH,
v4 简化为 2 源(代码默认 + yaml),删除所有运行时修改 API。

## 前置条件

Task 3.1-3.5 已完成

## 要创建的文件

```
executor/harness/
├── defaults.py              # 代码默认常量(v4 新文件)
└── config_loader.py         # 2 源加载器(v4 新文件)

backend/app/api/v1/
└── harness.py               # GET /harness/config(readonly)
```

## 实现规范

### 1. executor/harness/defaults.py

```python
DEFAULT_PERMISSION_POLICIES = {
    "bash": "ask",
    "Bash": "ask",
    "Write": "allow",
    "Edit": "allow",
    "Read": "allow",
    "Grep": "allow",
    "WebFetch": "ask",
    "WebSearch": "allow",
    "skill_install": "ask",
}

DEFAULT_MIDDLEWARE_CONFIG = {
    "loop_detection": {"enabled": True, "params": {"window_size": 5, "max_identical": 3}},
    "rate_limit": {"enabled": True, "params": {"max_tool_calls_per_minute": 30}},
    "feedback_capture": {"enabled": True, "params": {}},
    "observability": {"enabled": True, "params": {}},
}

DEFAULT_AGENT_CONSTRAINTS = {
    "chat": [],
    "explore": ["你是只读探索者。绝对不能创建、修改、删除任何文件或数据。"],
    "planner": ["你是规划者。只输出 step-by-step 计划,不执行任何操作。"],
    "verifier": ["你是验证者。你的工作是尝试打破系统,发现问题。"],
    "plugin_builder": ["严禁一键生成。必须进入多轮需求收集流程。"],
    "coordinator": [],
}
```

### 2. executor/harness/config_loader.py

见 Part A 上方 `HarnessConfigLoader` 完整代码。

### 3. backend/app/api/v1/harness.py(readonly)

```python
from fastapi import APIRouter, Depends
from app.auth.deps import require_admin
from executor.harness.config_loader import HarnessConfigLoader

router = APIRouter(prefix="/harness", tags=["harness"])

@router.get("/config")
async def get_harness_config(admin=Depends(require_admin)):
    loader = HarnessConfigLoader(config_file_path="/app/config/harness_config.yaml")
    cfg = loader.load()
    return {
        "effective": {
            "custom_guardrail_rules": cfg.custom_guardrail_rules,
            "permission_policies": cfg.permission_policies,
            "middleware_config": cfg.middleware_config,
            "hook_registrations": cfg.hook_registrations,
            "agent_constraints": cfg.agent_constraints,
        },
        "source_trace": cfg.source_trace,
    }

# 注:PATCH/POST/DELETE 端点均 **不提供**(v4 ADR-031)
```

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/harness/defaults.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/harness/config_loader.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile backend/app/api/v1/harness.py

# 2. HarnessConfigLoader 单测
docker compose -f docker-compose.dev.yml exec backend python -c "
from executor.harness.config_loader import HarnessConfigLoader

loader = HarnessConfigLoader(config_file_path=None)  # 无 yaml 路径
cfg = loader.load()
assert 'bash' in cfg.permission_policies
assert cfg.source_trace['permission_policies.bash'] == 'default'
print('Default-only load: PASS')

# 写一个临时 yaml
import tempfile, textwrap
with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False) as f:
    f.write(textwrap.dedent('''
    permissions:
      tool_overrides:
        bash: allow
    middlewares:
      loop_detection:
        enabled: false
    '''))
    path = f.name

loader2 = HarnessConfigLoader(config_file_path=path)
cfg2 = loader2.load()
assert cfg2.permission_policies['bash'] == 'allow'
assert cfg2.source_trace['permission_policies.bash'] == 'yaml'
assert cfg2.middleware_config['loop_detection']['enabled'] is False
print('YAML override: PASS')
"

# 3. API readonly 断言
curl -s -X PATCH http://localhost:8000/api/v1/harness/config -H 'Authorization: Bearer $ADMIN_TOKEN' \
  | grep -q '405\\|Method Not Allowed' && echo 'PATCH rejected: PASS'
```

## 完成后

1. 更新 PROGRESS.md:Task 3.6 完成
2. 更新 DECISIONS.md:记录 **ADR-031(Harness 配置 2 源化 + 禁止运行时修改)**
3. `git add -A && git commit -m "feat(v4): harness config loader (2-source), remove runtime PATCH/toggle APIs"`
```

---

## 附录 A: v4 修订清单

本次修订共 35 处精确修补,对应 Batch 1-5 review + PDF 补丁 + Master + user preferences archive:

| # | 位置 | 修订内容 | 来源 |
|---|---|---|---|
| 1 | Header | 版本 3.1 → 4.0,日期 2026-04-18,前置依赖 v4,v4 摘要段 | 全局 |
| 2 | Task 3.1 Part A | 新增 ADR-020(Harness 单实例)/ADR-021(工具并行 gather)/ADR-022(Redis 直通)/ADR-023(心跳)/ADR-024(MAX_TURNS 按 agent_type 分档) | Batch 2 §A3-1, Master M1/M2/M3 |
| 3 | Task 3.1 Part A 数据流图 | 重写:加 4 钩点 / 工具并行 / Redis 直通 / permission ask BLPOP / 心跳启停 | 同 #2 |
| 4 | Task 3.1 Part A 验收标准 | 加工具并行 / Redis 直通 / HTTP 关键事件带重试 / 心跳 / permission ask / MAX_TURNS 分档 | 同 #2 |
| 5 | Task 3.1 backend_callback.py | **重写为方案 A 双通道**(Redis 直通 + HTTP 带 3 次重试 + dead letter queue) | Batch 1 §3.3 D3, Master M2 |
| 6 | Task 3.1 query_engine.py `_execute_tools` | 改为 `asyncio.gather` 并行 + `_execute_single_tool` 加 run_context 传递 | Batch 2 §A3-1, PDF 补丁 |
| 7 | Task 3.1 query_engine.py `_process_turn` | 加 tool_use_delta Redis 直通 / message_complete HTTP / stream 接受 session_id / cache tokens 三字段 | 同上 |
| 8 | Task 3.1 `__main__.py` | 重写:加心跳 writer task(asyncio.create_task)+ SIGTERM 处理 + MAX_TURNS_BY_AGENT_TYPE + resume-from-step | Batch 2 §B-2, Batch 3 B3-2 |
| 9 | Task 3.1 验证步骤 | 加工具并行时序断言 / Redis PUBLISH 断言 / 心跳 Key 存在检查 | 同上 |
| 10 | Task 3.2 Part A | Middleware 从 2 钩点升到 **4 钩点**(pre_turn / pre_tool_use / post_tool_use / post_turn),ADR-025 | Batch 2 §A3-5, PDF 补丁 |
| 11 | Task 3.2 middleware/base.py | Middleware 基类加 4 个钩点方法,MiddlewareContext 扩展字段 | 同上 |
| 12 | Task 3.2 middleware/pipeline.py | MiddlewarePipeline 调度 4 钩点的方法 | 同上 |
| 13 | Task 3.2 `_execute_tools` 集成 | 在工具执行前后加 pre_tool_use / post_tool_use 钩点调用(2.1 新增小节) | 同上 |
| 14 | Task 3.3 Part A | ADR-026(HookDecision 11 字段完整)/ADR-027(合并规则)/ADR-028(permission ask Redis BLPOP 协议)+ 三方协议图 | PDF 补丁 P4, Batch 2 §A3-6/§A3-7 |
| 15 | Task 3.3 文件树 | 加 decision.py / ask_protocol.py 新文件 | PDF 补丁 P4 |
| 16 | Task 3.3 hooks/decision.py(新文件) | `HookDecision` dataclass 完整 11 字段 + `merge_decisions()` 合并函数 | PDF 补丁 P4 |
| 17 | Task 3.3 hooks/handlers.py | Handler 扩到 **4 种**(command/http/prompt/agent),command 完整 subprocess 实现,http 完整 httpx 实现 | 同上 |
| 18 | Task 3.3 permissions/engine.py | 加 `ask()` 方法:走 PermissionAskProtocol.ask();ask 决策 allow/deny 返回 | Batch 2 §A3-7 |
| 19 | Task 3.3 permissions/ask_protocol.py(新文件) | Redis BLPOP 协议完整实现:request / 超时 fail-safe deny / answer 消费 | 同上 |
| 20 | Task 3.3 guardrails/platform_rules.py | 补完整平台级护栏规则集 4 类(破坏性 + PII + 速率 + 跨用户)+ GuardrailRule custom_match 钩子 | Batch 2 §A3-8 |
| 21 | Task 3.3 验证步骤 | 加 HookDecision 合并规则测试 / permission ask e2e 端到端测试(mock Redis BLPOP + 超时 + answer) | 同上 |
| 22 | Task 3.4 Part A | ADR-029(feedback 事件结构化)/ADR-030(SessionEnd user_memory 提炼) | Batch 2 §A3-8/§A3-9 |
| 23 | Task 3.4 feedback_capture.py | FeedbackEvent 结构化 dataclass + Redis TTL 7 天 + Prometheus counter | 同上 |
| 24 | Task 3.4 lifecycle.py | HarnessRuntime 构造函数加 session_id/user_id/adapter/redis_url;`on_session_end` 实现 user_memory LLM 提炼 + 通过 Backend 回调写 user_memories 表 | Batch 2 §A3-9 |
| 25 | Task 3.5 Part A | ADR-029(Compaction 按回合组原子裁剪)+ 4 级策略完整定义 + ADR-030(is_skill_context 优先保留)+ 阈值从 80% 调到 60% | Batch 2 §A3-3, Master M4 |
| 26 | Task 3.5 compaction.py | 4 级实现骨架重写:maybe_compact 入口 / Tier 1 micro-compact / Tier 2 auto-compact(LLM 摘要)/ reactive_truncate;每级以回合组为原子单元;is_skill_context 优先保留 | 同上 |
| 27 | Task 3.5 memory.py | MemoryLayer 抽象基类 + SessionMemory + UserMemory(Layer 1/2)+ get_layer() 接口(Layer 3-6 Phase 2)+ user_memories 表查询 | Batch 2 §A3-9 |
| 28 | Task 3.6 Part A | **简化**:配置源从 4 源砍到 2 源;**删除 PATCH /harness/config** 运行时 API;删 toggle_middleware;ADR-031 替代原 ADR-030 | Batch 2 §A3-10, Master M8 |
| 29 | Task 3.6 config_loader.py | HarnessConfigLoader(非运行时管理器)2 源合并 + source_trace 标注 | 同上 |
| 30 | Task 3.6 API 端点 | GET /harness/config(readonly)保留 / **PATCH/POST/toggle 均删除** | 同上 |
| 31 | 所有 Part B | 开头加 v4 Observability 采集要求说明 | 全局 §3.4 |
| 32 | 所有 ADR 编号 | 从 ADR-020 开始接续至 ADR-031 | 全局 §3.7 |
| 33 | 交叉引用 | DOC-01 v3 → v4,DOC-02 v3 → v4 | 全局 |
| 34 | 附录 A | 完整 35 行修订清单表 | SOP |
| 35 | 文末维护说明 | 更新日期 + 下一步 DOC-04 v4 | 全局 |

---

> **文档维护说明**:本文档的 6 个 Task 完成后,Prism v2 将拥有完整的 Harness Runtime(Layer 3)和 Agent Engine Core(Layer 4):TAOR 主循环(工具并行 + Redis 直通 + 心跳)+ ToolExecutionPipeline + Middleware Pipeline(**4 钩点**)+ Hook System(8 种事件 × 4 种 handler + **HookDecision 11 字段**)+ Permission Engine(分层权限模型 + **Redis BLPOP ask 协议**)+ Guardrails Engine(平台级护栏 4 类)+ Feedback Loop(结构化事件 + user_memory 提炼)+ **4 级 Compaction Pipeline(按回合组原子裁剪)** + 6 层 Memory 骨架 + BackendCallback(双通道方案 A)+ HarnessConfigLoader(2 源简化)。这是 DOC-04 v4(Agent Orchestration)和 DOC-05 v4(Plugin Ecosystem)的基础。
> **最后更新**: 2026-04-18 (v4 review 修订版) | **下一步**: DOC-04 v4 Agent Orchestration
