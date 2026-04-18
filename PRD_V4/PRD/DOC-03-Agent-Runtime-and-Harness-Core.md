# Prism 棱镜 v2 — Agent Runtime & Harness Core (DOC-03)

> **文档编号**: DOC-03  
> **版本**: 3.1
> **日期**: 2026-04-02  
> **性质**: 实现文档 — Prism 最核心的两层：Harness Runtime（Layer 3）+ Agent Engine Core（Layer 4）  
> **前置依赖**: DOC-00 v3, DOC-01 v3, DOC-02 v3（Task 2.1-2.4 全部完成）  
> **Phase**: 1（Agent 核心）  
> **Task 数**: 6

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

#### 验收标准

- QueryEngine 能驱动完整的对话循环（纯文本 + 工具调用 + 多轮）
- 工具调用走 ToolExecutionPipeline（Schema 校验 → 执行 → 结果截断）
- 每轮通过回调接口向 Backend 上报事件（text_delta / tool_start / tool_end）
- turn_count 达到上限时强制退出
- stop_reason 为 "end_turn" 时正常退出并回调 run_complete
- 模型返回错误时回调 run_error

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的核心运行时——TAOR 主循环和工具执行 Pipeline。DOC-02 的全部 Task 已完成（项目骨架、双协议 Driver、Provider 管理、Prompt 装配引擎）。本 Task 是 Prism 的心脏。

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

### 4. executor/callbacks/backend_callback.py

```python
"""
Backend 回调客户端

CLI 子进程通过 HTTP POST 向 Backend 上报事件。
协议定义见 DOC-01 v3 §9.1。
"""

import httpx
from datetime import datetime, timezone

class BackendCallback:
    def __init__(self, callback_url: str, callback_secret: str, run_id: str):
        self._url = callback_url
        self._secret = callback_secret
        self._run_id = run_id
        self._client = httpx.AsyncClient(timeout=10.0)
    
    async def emit(self, event_type: str, data: dict) -> None:
        """发送回调事件。失败时只记日志，不中断 Agent 执行。"""
        payload = {
            "run_id": self._run_id,
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await self._client.post(
                self._url,
                json=payload,
                headers={"X-Callback-Secret": self._secret},
            )
        except Exception:
            pass  # 回调失败不应影响 Agent 执行
    
    async def text_delta(self, text: str) -> None:
        await self.emit("text_delta", {"text": text})
    
    async def tool_start(self, tool_use_id: str, tool_name: str, tool_input: dict) -> None:
        await self.emit("tool_start", {
            "tool_use_id": tool_use_id,
            "tool_name": tool_name,
            "input": tool_input,
        })
    
    async def tool_end(self, tool_use_id: str, output: str, is_error: bool, duration_ms: int) -> None:
        await self.emit("tool_end", {
            "tool_use_id": tool_use_id,
            "output": output[:500],  # 回调内容截断，完整内容在 messages 表
            "is_error": is_error,
            "duration_ms": duration_ms,
        })
    
    async def harness_event(self, event_subtype: str, detail: dict) -> None:
        await self.emit("harness_event", {"type": event_subtype, "detail": detail})
    
    async def run_complete(self, input_tokens: int, output_tokens: int, turn_count: int) -> None:
        await self.emit("run_complete", {
            "run_id": self._run_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "turn_count": turn_count,
        })
    
    async def run_error(self, error: str) -> None:
        await self.emit("run_error", {"run_id": self._run_id, "error": error})
    
    async def close(self) -> None:
        await self._client.aclose()
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
        
        async for event in self._adapter.stream(
            messages=self._messages,
            system_prompt=system_prompt,
            tools=tool_definitions if tool_definitions else None,
        ):
            if event.type == "text_delta":
                accumulated_text += event.text
                await self._callback.text_delta(event.text)
            
            elif event.type == "tool_use_start":
                current_tool_id = event.tool_use_id
                current_tool_name = event.tool_name
                current_tool_input_json = ""
            
            elif event.type == "tool_use_delta":
                current_tool_input_json += event.tool_input_delta
            
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
            
            elif event.type == "error":
                raise RuntimeError(f"模型返回错误: {event.error_message}")
        
        # 将 Assistant 消息追加到 messages
        content_blocks: list[ContentBlock] = []
        if accumulated_text:
            content_blocks.append(TextBlock(text=accumulated_text))
        content_blocks.extend(tool_use_blocks)
        
        if content_blocks:
            self._messages.append(PrismMessage(role="assistant", content=content_blocks))
        
        return stop_reason, tool_use_blocks
    
    async def _execute_tools(self, tool_use_blocks: list[ToolUseBlock]) -> None:
        """
        执行工具调用列表。
        每个工具串行执行（并行执行在 DOC-04 Coordinator 中实现）。
        """
        tool_results: list[ToolResultBlock] = []
        
        for block in tool_use_blocks:
            import time
            start = time.monotonic()
            
            await self._callback.tool_start(block.id, block.name, block.input)
            
            result = await self._pipeline.execute(
                tool_name=block.name,
                tool_input=block.input,
                tool_use_id=block.id,
            )
            
            duration_ms = int((time.monotonic() - start) * 1000)
            await self._callback.tool_end(block.id, result.content, result.is_error, duration_ms)
            
            tool_results.append(result)
        
        # 将工具结果追加到 messages
        self._messages.append(PrismMessage(
            role="tool_result",
            content=tool_results,
        ))
```

### 6. executor/__main__.py — 完整入口

```python
"""
Prism v2 Agent 执行器入口

用法：python -m prism.executor --run-id=019... --callback-url=http://... --callback-secret=...

生命周期：
1. 解析命令行参数
2. 从 DB 读取 Run 配置
3. 初始化 Provider → Adapter
4. 初始化 PromptAssembler + ToolRegistry + Pipeline + Budget
5. 初始化 QueryEngine
6. 执行 QueryEngine.run()
7. 退出

HARNESS_INTEGRATION_POINT: 
- Step 3.5 后初始化 Harness Runtime（MiddlewarePipeline + HookSystem + PermissionEngine + GuardrailsEngine）
- 这些在 Task 3.2-3.4 中实现
"""

import argparse
import asyncio
import sys

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--callback-url", required=True)
    parser.add_argument("--callback-secret", required=True)
    args = parser.parse_args()
    
    # 1. 从 DB 读取 Run 配置
    # 使用独立的 DB session（子进程自己的连接）
    # run = db.query(Run).filter(Run.id == args.run_id).one()
    # provider = db.query(Provider).filter(Provider.id == run.provider_id).one()
    
    # 2. 初始化 Adapter
    # adapter = ProviderManager 获取对应 Driver
    
    # 3. 初始化引擎组件
    # assembler = PromptAssembler(agent_type=..., tools=...)
    # budget = ContextBudgetManager(max_context_tokens=...)
    # registry = ToolRegistry() → 注册内置工具
    # pipeline = ToolExecutionPipeline(registry, budget)
    
    # 4. 初始化回调
    # callback = BackendCallback(args.callback_url, args.callback_secret, args.run_id)
    
    # 5. HARNESS_INTEGRATION_POINT: 初始化 Harness Runtime
    
    # 6. 初始化 QueryEngine
    # engine = QueryEngine(adapter, assembler, pipeline, budget, callback, max_turns=settings.MAX_TURNS_PER_RUN)
    
    # 7. 执行
    # await engine.run(run.prompt)
    
    # 8. 清理
    # await callback.close()

if __name__ == "__main__":
    asyncio.run(main())
```

注意：`__main__.py` 中的注释标注了完整链路，但实际代码需要你根据 Task 2.1-2.4 已经实现的类来填充。每一步都有对应的已实现模块，不需要新造任何依赖。

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

# 4. 集成测试（需要真实 API Key，手动执行）
# 用 EchoTool 注册到 QueryEngine，发送一条消息，验证完整循环
```

## 完成后

1. 更新 PROGRESS.md：记录 Task 3.1 完成状态
2. 更新 DECISIONS.md：记录 ADR-006（TAOR Model-Driven 循环 — 模型决策，Runtime 执行+治理）
3. 在 requirements.txt 中加入 `jsonschema>=4.0.0`
4. 加载 Simplify skill 审查
5. 加载 PJR skill 验证
6. `git add -A && git commit -m "feat: TAOR main loop + ToolExecutionPipeline + BackendCallback"`
```

---

## Task 3.2: Middleware Pipeline

### Part A — 设计与解释

#### 问题陈述

TAOR 主循环需要在每轮执行前后插入治理逻辑：上下文增强、循环检测、速率限制、输出校验、反馈采集、可观测性记录。这些逻辑如果直接写进 QueryEngine 会违反单一职责原则，也无法按需启停。

Middleware Pipeline 是 Harness Runtime 的编排骨架——可插拔中间件链，每个中间件单一职责，按顺序执行。对标 NxCode 描述的架构：`Request → ContextMiddleware → LoopDetectionMiddleware → ... → Response`。

#### CC 架构映射

CC 没有显式的 Middleware Pipeline，但它的 QueryEngine 内部按固定顺序执行了等效逻辑（prefetch memory → compaction → API call → tool dispatch → recovery）。Prism 将这些逻辑抽取为独立中间件，实现 P7 可撕裂架构——模型升级后，某些"补偿性"中间件可以直接关闭。

#### 验收标准

- MiddlewarePipeline 按注册顺序执行中间件
- 每个中间件可以在 pre_turn 和 post_turn 阶段插入逻辑
- 中间件可以中断循环（返回 abort 信号）
- LoopDetectionMiddleware 检测到连续重复工具调用时触发告警
- ObservabilityMiddleware 将每轮 turn 的关键指标写入 trace
- 集成到 QueryEngine 后不改变已有的 TAOR 行为

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

### 1. executor/harness/middleware/base.py

```python
"""
Middleware 抽象基类

每个中间件有两个钩子：
- pre_turn(context): TAOR 循环每轮开始前调用
- post_turn(context): TAOR 循环每轮结束后调用

context 是一个 mutable dict，中间件之间通过它传递状态。
"""

from abc import ABC

class TurnContext:
    """单轮上下文，中间件之间共享"""
    def __init__(self, turn_count: int, messages: list, run_id: str):
        self.turn_count = turn_count
        self.messages = messages
        self.run_id = run_id
        self.abort = False           # 任何中间件可置 True 中断循环
        self.abort_reason = ""
        self.metadata: dict = {}     # 中间件自由写入的元数据

class Middleware(ABC):
    """中间件抽象基类"""
    
    @property
    def name(self) -> str:
        return self.__class__.__name__
    
    async def pre_turn(self, ctx: TurnContext) -> None:
        """TAOR 每轮开始前。可修改 ctx 或设置 ctx.abort=True 中断。"""
        pass
    
    async def post_turn(self, ctx: TurnContext) -> None:
        """TAOR 每轮结束后。可记录指标、触发告警等。"""
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
    def __init__(self):
        self._middlewares: list[Middleware] = []
    
    def register(self, mw: Middleware) -> None:
        self._middlewares.append(mw)
    
    async def run_pre_turn(self, ctx: TurnContext) -> None:
        for mw in self._middlewares:
            await mw.pre_turn(ctx)
            if ctx.abort:
                return  # 短路：某个中间件要求中断
    
    async def run_post_turn(self, ctx: TurnContext) -> None:
        # post_turn 全部执行，不短路
        for mw in self._middlewares:
            await mw.post_turn(ctx)
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

## Task 3.3: Hook System 与 Permission Engine

### Part A — 设计与解释

#### 问题陈述

CC 源码的 Hook System 是其 Harness 最强大的治理能力——在每个生命周期事件节点触发外部脚本/webhook/LLM 审查，可以拦截、改写、放行工具调用。Prism 需要实现等效的 Hook System（21 种事件 × 4 种 handler）和分层 Permission Engine（平台级 + 插件级）。

#### CC 架构映射

| CC 机制 | Prism 对应 |
|---------|-----------|
| `.claude/settings.json` hooks 配置 | `.prism/hooks.json` |
| PreToolUse / PostToolUse / PermissionRequest 事件 | HookSystem 事件分发 |
| exit 0 + JSON / exit 2 协议 | HookHandler 决策协议 |
| 6 种权限模式 | PermissionEngine 分层模型 |
| matcher regex | HookMatcher 正则匹配 |
| Dyad 的 GREEN/YELLOW/RED 分类 | PermissionEngine 风险路由 |

> **Phase 分期**：Phase 1 实现以下 8 个核心事件（覆盖完整的工具执行和会话生命周期）：
> `PreToolUse`, `PostToolUse`, `SessionStart`, `SessionEnd`, `PreModelCall`, `PostModelCall`, `CompactionTrigger`, `ErrorOccurred`
>
> 其余事件（如 `ForkStart`, `ForkEnd`, `PlanStepStart` 等）在 Phase 1 中保留枚举定义和类型声明但不实现分发逻辑，Phase 2 按需开启。

#### 验收标准

- HookSystem 能在 PreToolUse / PostToolUse / SessionStart / SessionEnd 等事件触发注册的 handler
- command handler 执行 shell 命令，解析 stdout JSON
- Permission Engine 对每个工具调用做 allow/deny/ask 决策
- Guardrails 平台级规则（破坏性操作拦截）正确触发
- Hook 可以改写工具输入（updatedInput）
- Hook 可以阻断执行（permissionDecision: deny）
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
│   ├── system.py              # HookSystem（事件分发）
│   └── handlers.py            # Handler 执行器（command / http）
├── permissions/
│   └── engine.py              # PermissionEngine
├── guardrails/
│   ├── engine.py              # GuardrailsEngine
│   ├── rules.py               # 规则基类
│   └── platform_rules.py     # 平台级内置规则
└── lifecycle.py               # 生命周期控制器（组装 Hook + Permission + Guardrails）
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
    """Hook handler 返回的决策"""
    permission_decision: Literal["allow", "deny", "ask"] | None = None
    updated_input: dict | None = None     # 改写后的工具输入
    additional_context: str | None = None  # 追加到 Agent 上下文的信息
    prevent_continuation: bool = False     # 阻止 Agent 继续
    reason: str = ""
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
    type: Literal["command", "http"]
    command: str = ""             # command 类型
    url: str = ""                 # http 类型
    matcher: str = ""             # 正则，匹配 tool_name（空字符串匹配所有）
    timeout_seconds: int = 10

class HookHandlerExecutor:
    async def execute(self, config: HookHandlerConfig, event: HookEvent) -> HookDecision:
        """执行单个 handler，返回决策"""
        if config.type == "command":
            return await self._execute_command(config, event)
        elif config.type == "http":
            return await self._execute_http(config, event)
        return HookDecision()
    
    async def _execute_command(self, config: HookHandlerConfig, event: HookEvent) -> HookDecision:
        """执行 shell 命令。stdin 传入事件 JSON，解析 stdout。"""
        ...
    
    async def _execute_http(self, config: HookHandlerConfig, event: HookEvent) -> HookDecision:
        """POST 到 webhook URL。"""
        ...
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
    def __init__(self, guardrails: "GuardrailsEngine", hook_system: HookSystem):
        self._guardrails = guardrails
        self._hook_system = hook_system
    
    async def check(self, tool_name: str, tool_input: dict, run_id: str) -> "PermissionResult":
        """
        对工具调用做权限决策。
        
        返回 PermissionResult:
        - decision: "allow" | "deny"
        - reason: str
        - updated_input: dict | None（Hook 可能改写了输入）
        """
        # Layer 1: 平台级护栏（快速检查）
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
                reason=hook_decision.reason,
            )
        
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
# platform_rules.py
"""
平台级内置护栏规则

这些规则全局生效，不可被插件或用户覆盖。
对标 DOC-00 v3 §7 四条铁律的 Harness 强制层。
"""

DANGEROUS_PATTERNS = [
    # Shell 破坏性命令
    r"rm\s+(-rf?|--recursive)",
    r"DROP\s+(TABLE|DATABASE)",
    r"DELETE\s+FROM\s+\w+\s*;?\s*$",  # 无 WHERE 的全表删除
    r"FORMAT\s+",
    r"mkfs\.",
    # 敏感数据泄露
    r"(api_key|secret|password|token)\s*[:=]",
]

def get_platform_rules() -> list["GuardrailRule"]:
    rules = []
    # Bash 工具的危险命令检测
    rules.append(GuardrailRule(
        id="GR-PLATFORM-001",
        tool_pattern="bash|Bash|shell",
        input_patterns=DANGEROUS_PATTERNS,
        reason="平台级护栏：检测到破坏性命令",
        scope="platform",
    ))
    # 合规铁律相关规则可在此扩展
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

print('\nAll Task 3.3 checks passed!')
"
```

## 完成后

1. 更新 PROGRESS.md
2. 更新 DECISIONS.md：记录 ADR-008（分层权限模型——确定性规则优先 + Hook 兜底）、ADR-009（Hook 决策协议——exit code 语义对标 CC）
3. 加载 Simplify skill 审查
4. 加载 PJR skill 验证
5. `git add -A && git commit -m "feat: Hook System + Permission Engine + Guardrails Engine"`
```

---

## Task 3.4: Guardrails Engine 与 Feedback Loop

### Part A — 设计与解释

#### 问题陈述

Harness 的核心理念：**Agent 每次犯错，修复方式不是"换个 prompt 试试"，而是"在 Harness 中新增一条永久性约束"。** Feedback Loop Engine 实现这个闭环——捕获失败事件，分析模式，生成新的护栏建议。

Phase 1 的 Feedback Loop 采用半自动模式（检测 + 告警 + 人工触发），不做全自动规则生成。

#### CC 架构映射

CC 没有显式的 Feedback Loop，但 Anthropic 通过 Hooks 的 `PostToolUseFailure` 事件和 CLAUDE.md 的自我学习机制（auto-memory）实现了等效功能。Prism 将这个过程系统化。

#### 验收标准

- FeedbackCaptureMiddleware 在 post_turn 阶段记录失败事件（工具执行失败、护栏拦截）
- 失败事件通过 callback 上报 Backend，写入 audit_logs
- 提供查询接口：按 run_id / session_id / 时间范围查询失败模式
- Harness lifecycle controller 组装所有子系统（HookSystem + PermissionEngine + GuardrailsEngine + MiddlewarePipeline）

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

class FeedbackCaptureMiddleware(Middleware):
    def __init__(self, callback: BackendCallback):
        self._callback = callback
        self._failures_this_run: list[dict] = []
    
    async def post_turn(self, ctx: TurnContext) -> None:
        """扫描本轮结果，记录失败事件"""
        failures = self._extract_failures(ctx)
        if failures:
            self._failures_this_run.extend(failures)
            for f in failures:
                await self._callback.harness_event("feedback_capture", f)
    
    def _extract_failures(self, ctx: TurnContext) -> list[dict]:
        """从 messages 尾部提取失败事件"""
        # 检查最新的 tool_result 是否 is_error
        # 检查 ctx.metadata 中是否有 permission_deny 记录
        # 检查 ctx.abort 是否因 loop_detection 触发
        ...
    
    def get_run_summary(self) -> dict:
        """返回本次 Run 的失败摘要，写入 runs.harness_summary"""
        return {
            "total_failures": len(self._failures_this_run),
            "failure_types": ...,  # 按类型统计
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
    def __init__(self, run_id: str, callback: BackendCallback, redis_client, settings):
        self.guardrails = GuardrailsEngine()
        self.hook_system = HookSystem()
        self.permission_engine = PermissionEngine(self.guardrails, self.hook_system)
        
        self.feedback_mw = FeedbackCaptureMiddleware(callback)
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
        await self.hook_system.fire(HookEvent(event_type="SessionStart"))
    
    async def on_session_end(self) -> None:
        """触发 SessionEnd Hook"""
        await self.hook_system.fire(HookEvent(event_type="SessionEnd"))
    
    def get_run_harness_summary(self) -> dict:
        """返回完整的 Harness 运行摘要（写入 runs.harness_summary）"""
        return {
            **self.feedback_mw.get_run_summary(),
            "middleware_count": len(self.middleware._middlewares),
            "guardrail_rules_count": len(self.guardrails._rules),
        }
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

## Task 3.5: 4 级 Compaction Pipeline 与 6 层 Memory

### Part A — 设计与解释

#### 问题陈述

CC 源码揭示了最精妙的设计之一：4 级渐进式上下文压缩。不是简单地"满了就截断"，而是按从低成本到高成本的顺序，逐级释放空间，每级牺牲不同类型的信息。Prism v2 的 `ContextBudgetManager`（Task 2.4）只实现了 Tier 0 基础能力，本 Task 补完 4 级 Compaction Pipeline。

同时实现 6 层 Memory 系统，确保 Agent 不从零开始——对标 CC 的 CLAUDE.md + auto-memory + session history。

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

> **Phase 分期**：Phase 1 先实现 2 层 Memory：
> 1. **Session Memory**（会话级上下文）— 必需，TAOR 循环的基础
> 2. **User Memory**（用户级偏好/历史）— 跨会话延续性的基础
>
> 其余 4 层（Project Memory, Tool Memory, Agent Memory, Global Memory）在 Phase 1 中预留接口定义（`MemoryLayer` 抽象基类 + `MemoryManager.get_layer()` 方法签名），Phase 2 按需实现。

#### 验收标准

- 4 级 Compaction 按阈值自动触发
- Tier 1（micro-compact）清除旧工具结果，信息损失最小
- Tier 2（auto-compact）调用模型生成摘要（token 消耗约 1000-2000）
- Tier 3（session memory）提取关键决策到持久化存储
- Tier 4（reactive）API 返回 context_too_long 错误时的最后手段
- Memory 系统在 Session 开始时加载，CompactInstructions 在压缩时保留

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
    # 阈值配置（占 max_context_tokens 的百分比）
    TIER1_THRESHOLD = 0.80
    TIER2_THRESHOLD = 0.85
    TIER3_THRESHOLD = 0.90
    TIER4_THRESHOLD = 0.98
    
    def __init__(
        self,
        budget: ContextBudgetManager,
        adapter: ModelAdapter,   # Tier 2 需要调用模型
        callback: BackendCallback,
    ):
        self._budget = budget
        self._adapter = adapter
        self._callback = callback
    
    async def check_and_compact(
        self,
        messages: list[PrismMessage],
        system_prompt: str,
    ) -> list[PrismMessage]:
        """
        检查上下文使用率，按需执行分级压缩。
        返回压缩后的 messages。
        """
        usage_ratio = self._get_usage_ratio(messages, system_prompt)
        
        if usage_ratio < self.TIER1_THRESHOLD:
            return messages
        
        if usage_ratio < self.TIER2_THRESHOLD:
            messages = self._tier1_micro_compact(messages)
            await self._callback.harness_event("compaction", {"tier": 1})
            return messages
        
        if usage_ratio < self.TIER3_THRESHOLD:
            messages = self._tier1_micro_compact(messages)
            messages = await self._tier2_auto_compact(messages, system_prompt)
            await self._callback.harness_event("compaction", {"tier": 2})
            return messages
        
        if usage_ratio < self.TIER4_THRESHOLD:
            messages = self._tier1_micro_compact(messages)
            messages = await self._tier2_auto_compact(messages, system_prompt)
            await self._tier3_session_memory(messages)
            await self._callback.harness_event("compaction", {"tier": 3})
            return messages
        
        # Tier 4: 紧急截断
        messages = self._tier4_reactive(messages)
        await self._callback.harness_event("compaction", {"tier": 4})
        return messages
    
    def _get_usage_ratio(self, messages, system_prompt) -> float:
        tokens = self._budget.estimate_messages_tokens(messages, system_prompt)
        return tokens / self._budget.max_context_tokens
    
    def _tier1_micro_compact(self, messages: list[PrismMessage]) -> list[PrismMessage]:
        """
        清除旧工具结果。
        
        规则：
        - 保留最近 10 条消息不动
        - 更早的 tool_result 内容替换为 "[旧工具结果已清除]"
        - 不破坏 tool_use → tool_result 的配对关系
        """
        ...
    
    async def _tier2_auto_compact(self, messages: list[PrismMessage], system_prompt: str) -> list[PrismMessage]:
        """
        调用模型生成摘要。
        
        规则：
        - 保留最近 10 条消息不动
        - 将更早的消息打包发给模型，要求生成摘要
        - 用摘要替换原始消息
        - 摘要 prompt: "请将以下对话历史压缩为关键信息摘要，保留所有重要决策、数据和发现..."
        """
        ...
    
    async def _tier3_session_memory(self, messages: list[PrismMessage]) -> None:
        """
        提取关键信息到持久化存储。
        
        调用模型提取：
        - 用户的核心需求
        - 已做出的关键决策
        - 重要的发现/数据
        
        通过 callback 传回 Backend 持久化。
        """
        ...
    
    def _tier4_reactive(self, messages: list[PrismMessage]) -> list[PrismMessage]:
        """
        紧急截断：只保留最近 5 条消息。
        在消息开头插入 "[上下文已紧急压缩，部分历史信息丢失]"。
        """
        ...
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

class MemoryManager:
    def __init__(self, user_id: str, session_id: str, db_session):
        self._user_id = user_id
        self._session_id = session_id
        self._db = db_session
    
    def load(self) -> str:
        """
        加载所有层级 memory，拼接为字符串。
        
        返回的字符串注入到 PromptAssembler.build(memory=...) 中。
        """
        parts = []
        
        # Layer 2: User memory
        user_memory = self._load_user_memory()
        if user_memory:
            parts.append(f"## 用户偏好\n{user_memory}")
        
        # Layer 3: Session memory
        session_memory = self._load_session_memory()
        if session_memory:
            parts.append(f"## 会话记忆\n{session_memory}")
        
        # Layer 4: Auto memory（从最近 N 次成功 Run 提取模式）
        auto_memory = self._load_auto_memory()
        if auto_memory:
            parts.append(f"## 经验记忆\n{auto_memory}")
        
        # Layer 5: Skill memory（由外部注入，不在此处加载）
        # Layer 6: Team memory（Phase 2）
        
        return "\n\n".join(parts) if parts else ""
    
    def _load_user_memory(self) -> str | None:
        """从 users 表或 user_config 加载用户偏好"""
        ...
    
    def _load_session_memory(self) -> str | None:
        """从 sessions.config_snapshot 加载 Tier 3 Compaction 产出的记忆"""
        ...
    
    def _load_auto_memory(self) -> str | None:
        """从最近成功的 runs 提取经验模式"""
        ...
    
    def save_session_memory(self, memory: str) -> None:
        """Tier 3 Compaction 调用，将提取的记忆持久化"""
        ...
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

## Task 3.6: Harness 垂类配置动态更新

### Part A — 设计与解释

#### 问题陈述

Prism v2 的 Harness Runtime（Task 3.1-3.5）目前采用"全部硬编码"方式——底层框架和垂类规则混在同一层，修改任何 Guardrail 规则或 Permission 策略都需要重启服务。这在生产环境中代价高昂，且无法满足多垂类场景下的灵活配置需求。

需要实现分层配置管理：底层框架固化（代码级，重启更新），垂类规则热更新（配置级，运行时生效）。

#### 设计原则

| 层级 | 包含内容 | 更新方式 | 理由 |
|------|---------|---------|------|
| **底层（固化）** | TAOR 主循环框架、MiddlewarePipeline 分发机制、HookSystem 事件分发器、PermissionEngine 决策框架、CircuitBreaker 熔断框架、CompactionPipeline 四级策略框架 | 代码更新 + 重启 | 通用性强，改动易出问题，稳定性优先 |
| **垂类层（动态）** | Guardrail 规则集、Permission 策略集（允许/拒绝/询问规则）、Middleware 启停配置及参数调优、Hook 注册表（新增/移除 handler）、Agent 行为约束（各类型约束增减） | 配置更新，运行时热生效 | 垂类影响大，频繁迭代，需要灵活性 |

#### HarnessConfigManager

```python
"""
executor/harness/config_manager.py

Harness 垂类配置运行时管理器。

配置来源（优先级从低到高）：
1. platform_rules.py 硬编码（平台级底线，不可被覆盖）
2. harness_config.yaml 文件（部署时配置）
3. DB 存储的配置（Web UI / API 修改）
4. Plugin 注入的配置（插件加载时动态注入，随插件卸载移除）

热更新触发机制：
- 文件变更：watchdog 监听 harness_config.yaml，检测到变更自动 reload
- DB 变更：API 调用 PATCH /harness/config 后主动 reload
- Plugin 变更：PluginHost 加载/卸载时回调 reload
- 跨进程同步：通过 Redis pub/sub channel `harness:config_reload` 通知其他 CLI 子进程

变更不中断原则：
- reload 操作不中断正在执行的 Run
- 新配置在下一个 TAOR turn 开始时生效（turn 粒度的原子切换）
- 如果 reload 失败（配置格式错误），保持旧配置并写入 audit_logs 告警
"""

@dataclass
class HarnessEffectiveConfig:
    """合并后的最终有效配置"""
    guardrail_rules: list[GuardrailRule]
    permission_policies: dict[str, str]  # tool_name → "allow" | "deny" | "ask_user"
    middleware_config: dict[str, MiddlewareConfig]  # mw_name → {enabled, params}
    hook_registrations: list[HookRegistration]
    agent_constraints: dict[str, list[str]]  # agent_type → [constraint_text]
    source_trace: dict[str, str]  # 每条配置的来源标注（debug 用）


class HarnessConfigManager:
    def __init__(
        self,
        config_file_path: str,        # harness_config.yaml 路径
        db_session_factory,             # DB session 工厂（读取 DB 存储的配置）
        redis_client,                   # Redis（跨进程同步）
        platform_rules: list,           # 不可覆盖的平台级规则
    ):
        self._effective: HarnessEffectiveConfig | None = None
        ...

    def reload(self) -> HarnessEffectiveConfig:
        """
        重新计算有效配置。

        合并策略：
        1. 从 platform_rules.py 加载平台级规则（最低优先级但不可覆盖）
        2. 从 harness_config.yaml 加载文件配置
        3. 从 DB 加载用户/admin 修改的配置
        4. 从 PluginHost 收集所有已加载插件的 harness_overrides
        5. 合并：高优先级源覆盖低优先级源，但平台级规则不可被覆盖
        6. 每条配置标注来源（source_trace）
        """
        ...

    def reload_guardrails(self) -> None:
        """仅重新加载 Guardrail 规则集"""
        ...

    def reload_permissions(self) -> None:
        """仅重新加载权限策略"""
        ...

    def toggle_middleware(self, name: str, enabled: bool) -> None:
        """
        启用/禁用指定 Middleware（P7 可撕裂原则的运行时体现）。
        写入 DB + 通知 Redis → 所有进程生效。
        """
        ...

    def get_effective_config(self) -> HarnessEffectiveConfig:
        """获取当前有效配置（供 API 查询和调试）"""
        if self._effective is None:
            self._effective = self.reload()
        return self._effective

    def inject_plugin_config(self, plugin_name: str, overrides: dict) -> None:
        """插件加载时注入配置"""
        ...

    def remove_plugin_config(self, plugin_name: str) -> None:
        """插件卸载时移除配置"""
        ...
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

#### 与现有子系统的集成

| 子系统 | 当前实现 | 修改后 |
|--------|---------|--------|
| GuardrailsEngine | `platform_rules.py` 硬编码 + Plugin 注入 | 从 `HarnessConfigManager.get_effective_config().guardrail_rules` 读取。平台级规则仍硬编码且不可覆盖 |
| PermissionEngine | 静态配置 | 从配置读取 `default_mode` + `tool_overrides` |
| MiddlewarePipeline | 启动时固定注册 | 启动时从配置加载 MW 列表 + `toggle_middleware()` 运行时增减 |
| HookSystem | settings + Plugin frontmatter | 新增从 `harness_config.yaml` 读取的 Hook 注册 |
| Agent 行为约束 | `prompt_sections.py` 硬编码 | `session_guidance_section()` 合并硬编码约束 + 配置中的自定义约束 |

#### API 端点

```
GET    /harness/config          — 获取当前有效配置（含 source_trace）
PATCH  /harness/config          — 更新配置（admin only，写入 DB）
POST   /harness/config/reload   — 强制重载所有配置源（admin only）
```

#### 设计决策: ADR-030

**ADR-030: Harness 底层/垂类分层架构**

- **决策**：底层框架（TAOR 循环、Middleware 分发、HookSystem 分发器、PermissionEngine 框架）固化为代码，垂类规则（Guardrail 规则集、Permission 策略、Middleware 参数、Hook 注册表、Agent 约束）抽象为配置层，支持运行时热更新。
- **理由**：底层框架通用性强，改动风险高，稳定性优先；垂类规则垂类差异大，频繁迭代，灵活性优先。两者混在同层违反单一职责原则。
- **影响**：GuardrailsEngine、PermissionEngine、MiddlewarePipeline、HookSystem 均需改造为从 HarnessConfigManager 读取配置，而非硬编码。平台级铁律通过 `platform_rules.py` 硬编码保证，不可被任何配置源覆盖。

#### 验收标准

- `harness_config.yaml` 修改后，下一个 TAOR turn 自动使用新配置
- `PATCH /harness/config` 修改 Guardrail 规则后，新规则立即生效（下一个 Run）
- `toggle_middleware("loop_detection", false)` 后，循环检测不再执行
- 平台级规则（铁律相关的 Guardrail）不可被任何配置源覆盖
- 配置格式错误时不 crash，保持旧配置并写入 audit_logs
- 跨进程同步：修改配置后，所有正在运行的 CLI 子进程在下一个 turn 使用新配置

---

### Part B — Claude Code 执行 Prompt

待实施计划执行阶段补充。

---

## 完成后

1. 更新 PROGRESS.md：记录 Task 3.6 完成状态
2. 更新 DECISIONS.md：记录 ADR-030（Harness 底层/垂类分层架构——底层固化 + 垂类热更新）
3. 在 requirements.txt 中加入 `watchdog>=3.0.0`（文件变更监听）
4. 加载 Simplify skill 审查
5. 加载 PJR skill 验证
6. `git add -A && git commit -m "feat: HarnessConfigManager + runtime hot-reload for vertical config"`

---

> **文档维护说明**：本文档的 6 个 Task 完成后，Prism v2 将拥有完整的 Harness Runtime（Layer 3）和 Agent Engine Core（Layer 4）：TAOR 主循环 + ToolExecutionPipeline + Middleware Pipeline（可插拔中间件链）+ Hook System（8 种事件 × 2 种 handler）+ Permission Engine（分层权限模型）+ Guardrails Engine（平台级护栏）+ Feedback Loop（半自动闭环）+ 4 级 Compaction Pipeline + 6 层 Memory + BackendCallback + HarnessConfigManager（垂类配置热更新）。这是 DOC-04（Agent Orchestration）和 DOC-05（Plugin Ecosystem）的基础。
> **最后更新**: 2026-04-05 | **下一步**: DOC-04 Agent Orchestration
