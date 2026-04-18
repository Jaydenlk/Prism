# Prism 棱镜 v2 — Agent Orchestration (DOC-04)

> **文档编号**: DOC-04  
> **版本**: 3.1
> **日期**: 2026-04-02  
> **性质**: 实现文档 — 多 Agent 编排层，将单 Agent 的 TAOR 循环扩展为专业化分工、上下文隔离和协调模式  
> **前置依赖**: DOC-00 v3, DOC-01 v3, DOC-02 v3, DOC-03 v3（Task 3.1-3.5 全部完成）  
> **Phase**: 1（Agent 核心）  
> **Task 数**: 5

---

## 目录

1. [Task 4.1: Agent 专业化定义与 AgentPool](#task-41-agent-专业化定义与-agentpool)
2. [Task 4.2: Fork & Context Isolation](#task-42-fork--context-isolation)
3. [Task 4.3: Coordinator-Workers 编排](#task-43-coordinator-workers-编排)
4. [Task 4.4: Agent 类型自动选择与任务路由](#task-44-agent-类型自动选择与任务路由)
5. [Task 4.5: PluginBuilder Agent 与多轮对话流程](#task-45-pluginbuilder-agent-与多轮对话流程)

---

## Task 4.1: Agent 专业化定义与 AgentPool

### Part A — 设计与解释

#### 问题陈述

Prism v1 只有一个通用 Agent 处理所有任务——探索、规划、执行、验证全部混在一起，行为发散不可控。CC 源码揭示了专业化分工的设计：每种 Agent 被故意裁剪能力范围，注入不同的行为约束和工具集，确保行为可预测。

Prism v2 的 PromptAssembler 已经在 Task 2.4 中实现了 `session_guidance_section(agent_type)` 的差异化注入。本 Task 将 Agent 定义从"只是一个 prompt 参数"提升为完整的声明式对象——每种 Agent 有自己的工具白名单、行为约束、maxTurns 限制和输出格式要求。

#### CC 架构映射

| CC Agent | Prism Agent | 工具集 | 核心约束 |
|----------|-------------|--------|---------|
| General Purpose | **General** | 全部工具 | 无特殊限制 |
| Explore（只读） | **Research** | 只读工具（web_search, file_read, grep） | 绝对不能创建/修改/删除 |
| Plan | **Planner** | 只读工具 | 只输出 step-by-step plan，不执行 |
| Verification | **Verifier** | 全部工具（含破坏性测试） | 对抗性思维，尝试打破系统 |

CC 的 Sub-Agent 有三种内建类型（Explore/Plan/General-purpose），分别使用不同的模型（Explore 用 Haiku 快速模型）和工具集。Prism 不做模型级别的区分（统一使用用户配置的 Provider），但在工具集和行为约束上做等效裁剪。

#### 验收标准

- 4 种 Agent 定义完整实现，每种有独立的工具白名单和行为约束
- AgentPool 可以按类型创建 Agent 实例
- Research Agent 的工具集不包含任何写操作工具
- Planner Agent 的输出被约束为结构化计划格式
- Verifier Agent 的 prompt 注入对抗性思维
- Agent 定义是声明式的（.yaml 或 dataclass），不硬编码在业务逻辑中

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的 Agent 专业化系统。DOC-03 的 QueryEngine + Harness Runtime 已完成。本 Task 将 Agent 从"单一通用"升级为"专业化分工"。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

DOC-03 全部 Task 完成，QueryEngine + HarnessRuntime + ToolExecutionPipeline 可运行

## 要创建的文件

```
executor/agents/
├── base.py                    # AgentDefinition 基类
├── general.py                 # 通用 Agent
├── research.py                # 研究/探索 Agent（只读）
├── planner.py                 # 规划 Agent
├── verifier.py                # 验证 Agent
└── pool.py                    # AgentPool（工厂 + 注册表）
```

## 实现规范

### 1. executor/agents/base.py

```python
"""
Agent 定义基类 — 声明式 Agent 规格

每种 Agent 声明：
- agent_type: 类型标识
- description: 用途说明
- allowed_tools: 工具白名单（None = 全部允许）
- denied_tools: 工具黑名单（优先于白名单）
- max_turns: 该类型 Agent 的循环上限（覆盖全局默认值）
- behavior_constraints: 注入到 Prompt 的行为约束文本
- output_format: 期望的输出格式说明（如 Planner 要求结构化 JSON）
"""

from dataclasses import dataclass, field

@dataclass
class AgentDefinition:
    """Agent 声明式定义"""
    agent_type: str
    description: str
    allowed_tools: list[str] | None = None     # None = 全部允许
    denied_tools: list[str] = field(default_factory=list)
    max_turns: int = 50                         # 可被全局配置覆盖
    behavior_constraints: str = ""              # 注入到 session_guidance_section
    output_format: str | None = None            # 期望输出格式
    read_only: bool = False                     # True 时 Harness 强制拦截所有写操作
    
    def filter_tools(self, all_tools: list[str]) -> list[str]:
        """
        根据白名单/黑名单过滤可用工具。
        
        逻辑：
        1. 如果 allowed_tools 不为 None，只保留白名单中的
        2. 从结果中移除 denied_tools
        """
        if self.allowed_tools is not None:
            tools = [t for t in all_tools if t in self.allowed_tools]
        else:
            tools = list(all_tools)
        return [t for t in tools if t not in self.denied_tools]
```

### 2. executor/agents/general.py

```python
"""通用 Agent — 全能力，无特殊限制"""

GENERAL_AGENT = AgentDefinition(
    agent_type="general",
    description="通用 Agent，拥有全部工具和能力，适用于大多数任务",
    allowed_tools=None,          # 全部允许
    max_turns=50,
    behavior_constraints="",     # 无额外约束，依赖 PromptAssembler 的通用行为规范
)
```

### 3. executor/agents/research.py

```python
"""
Research Agent — 只读探索者

对标 CC 的 Explore Agent：
- 被故意裁成 read-only specialist
- 只保留搜索、读取、分析类工具
- 绝对不能创建/修改/删除任何数据
- Harness 层通过 read_only=True 做硬性保障
"""

# 只读工具白名单（具体名称根据实际注册的内置工具调整）
READ_ONLY_TOOLS = [
    "web_search",
    "file_read",
    "grep",
    "glob",
    "list_directory",
]

RESEARCH_AGENT = AgentDefinition(
    agent_type="research",
    description="研究/探索 Agent，只读模式，用于信息搜索和分析",
    allowed_tools=READ_ONLY_TOOLS,
    max_turns=30,                # 探索任务通常不需要太多轮
    read_only=True,
    behavior_constraints=(
        "你是只读探索者。\n"
        "绝对不能创建、修改、删除任何文件或数据。\n"
        "你的工作是搜索信息、阅读内容、分析数据，然后将发现总结返回。\n"
        "如果任务需要写操作，明确告知用户你无法执行，建议切换到通用 Agent。"
    ),
)
```

### 4. executor/agents/planner.py

```python
"""
Planner Agent — 纯规划不执行

对标 CC 的 Plan Agent：
- 只输出 step-by-step plan，不执行任何操作
- 只保留只读工具（用于理解当前状态）
- 输出格式为结构化计划
"""

PLANNER_AGENT = AgentDefinition(
    agent_type="planner",
    description="规划 Agent，分析任务并输出执行计划，不直接执行操作",
    allowed_tools=READ_ONLY_TOOLS,  # 复用 Research 的只读工具集
    max_turns=10,                    # 规划不需要太多轮
    read_only=True,
    behavior_constraints=(
        "你是规划者。\n"
        "你的工作是分析任务，理解当前状态，然后输出一个清晰的执行计划。\n"
        "绝对不要执行任何操作。只规划，不执行。\n"
        "你的输出必须是结构化的 step-by-step 计划。"
    ),
    output_format=(
        "输出格式要求：\n"
        "1. 任务理解（一句话总结用户想要什么）\n"
        "2. 当前状态分析（基于你读取到的信息）\n"
        "3. 执行步骤（编号列表，每步包含：操作描述、需要的工具、预期结果、风险点）\n"
        "4. 关键文件/资源清单"
    ),
)
```

### 5. executor/agents/verifier.py

```python
"""
Verifier Agent — 对抗性验证者

对标 CC 的 Verification Agent：
- 目标是"try to break it"
- 拥有全部工具（含破坏性测试需要的工具）
- 强制跑 build/test/lint/adversarial probes
- 不假设一切正常
"""

VERIFIER_AGENT = AgentDefinition(
    agent_type="verifier",
    description="验证 Agent，以对抗性思维检验结果的正确性和健壮性",
    allowed_tools=None,          # 全部允许（需要能跑测试、执行命令）
    max_turns=20,
    behavior_constraints=(
        "你是验证者。你的工作是尝试打破系统，发现问题。\n"
        "不要假设一切正常。对每个声明持怀疑态度。\n"
        "验证策略：\n"
        "- 检查边界条件和异常输入\n"
        "- 验证声明的结果是否真实（重新运行、交叉检查）\n"
        "- 寻找遗漏的场景\n"
        "- 如果有测试，运行测试\n"
        "- 如果有构建命令，执行构建\n"
        "- 汇报发现的所有问题，不要隐瞒"
    ),
)
```

### 6. executor/agents/pool.py

```python
"""
AgentPool — Agent 工厂 + 注册表

职责：
- 注册所有 Agent 定义
- 按类型创建 Agent 实例（返回配置好的 AgentDefinition）
- 根据 AgentDefinition 过滤 ToolRegistry 中的工具
"""

from executor.agents.general import GENERAL_AGENT
from executor.agents.research import RESEARCH_AGENT
from executor.agents.planner import PLANNER_AGENT
from executor.agents.verifier import VERIFIER_AGENT

class AgentPool:
    def __init__(self):
        self._definitions: dict[str, AgentDefinition] = {}
        # 注册内置 Agent
        for agent_def in [GENERAL_AGENT, RESEARCH_AGENT, PLANNER_AGENT, VERIFIER_AGENT]:
            self._definitions[agent_def.agent_type] = agent_def
    
    def get(self, agent_type: str) -> AgentDefinition:
        """获取 Agent 定义。不存在则回退到 general。"""
        return self._definitions.get(agent_type, GENERAL_AGENT)
    
    def list_types(self) -> list[str]:
        return list(self._definitions.keys())
    
    def filter_tools_for_agent(
        self,
        agent_type: str,
        registry: "ToolRegistry",
    ) -> list["ToolDefinition"]:
        """
        根据 Agent 类型过滤可用工具，返回排序后的 ToolDefinition 列表。
        """
        agent_def = self.get(agent_type)
        all_tool_names = [t.name for t in registry.list_definitions()]
        allowed_names = agent_def.filter_tools(all_tool_names)
        return sorted(
            [d for d in registry.list_definitions() if d.name in allowed_names],
            key=lambda d: d.name,
        )
```

### 7. 集成到 QueryEngine 和 HarnessRuntime

修改 `executor/engine/query_engine.py`：
- `__init__` 新增参数 `agent_def: AgentDefinition`
- 如果 `agent_def.read_only is True`，在 Harness 的 GuardrailsEngine 中动态注册一条只读规则，拦截所有写操作工具

修改 `executor/harness/lifecycle.py`：
- `HarnessRuntime.__init__` 接收 `agent_def` 参数
- 如果 `agent_def.read_only`，向 GuardrailsEngine 追加只读护栏规则

修改 `executor/__main__.py`：
- 根据 Run 配置（或默认 general）选择 Agent 类型
- `AgentPool().get(agent_type)` 获取定义
- 使用 `AgentPool().filter_tools_for_agent()` 过滤工具集
- 传入 QueryEngine 和 HarnessRuntime

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/agents/base.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/agents/general.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/agents/research.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/agents/planner.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/agents/verifier.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/agents/pool.py

# 2. Agent 定义测试
docker compose -f docker-compose.dev.yml exec backend python -c "
from executor.agents.pool import AgentPool
from executor.agents.base import AgentDefinition

pool = AgentPool()

# 4 种类型已注册
assert len(pool.list_types()) == 4
print('Agent types registered: PASS')

# General 允许全部工具
g = pool.get('general')
assert g.allowed_tools is None
assert not g.read_only
print('General agent: PASS')

# Research 只读 + 工具白名单
r = pool.get('research')
assert r.read_only
assert r.allowed_tools is not None
assert 'web_search' in r.allowed_tools
filtered = r.filter_tools(['web_search', 'file_read', 'file_write', 'bash'])
assert 'file_write' not in filtered
assert 'bash' not in filtered
assert 'web_search' in filtered
print('Research agent tool filtering: PASS')

# Planner 只读 + 低 max_turns
p = pool.get('planner')
assert p.read_only
assert p.max_turns <= 10
assert p.output_format is not None
print('Planner agent: PASS')

# Verifier 全工具 + 对抗性约束
v = pool.get('verifier')
assert not v.read_only
assert v.allowed_tools is None
assert '打破' in v.behavior_constraints or '验证' in v.behavior_constraints
print('Verifier agent: PASS')

# 未知类型回退到 general
fallback = pool.get('nonexistent')
assert fallback.agent_type == 'general'
print('Fallback to general: PASS')

print('\nAll Task 4.1 checks passed!')
"
```

## 完成后

1. 更新 PROGRESS.md
2. 更新 DECISIONS.md：记录 ADR-013（Agent 专业化声明式定义——工具白名单 + 行为约束 + read_only 硬保障）
3. 加载 Simplify skill 审查
4. 加载 PJR skill 验证
5. `git add -A && git commit -m "feat: 4 specialized Agent definitions + AgentPool factory"`
```

---

## Task 4.2: Fork & Context Isolation

### Part A — 设计与解释

#### 问题陈述

当主 Agent 需要探索一个不确定的方向（搜索信息、验证假设）时，直接在主上下文中执行会带来两个问题：(1) 探索过程产生的大量垃圾上下文（搜索结果、试错输出）污染主对话；(2) 如果探索方向错误，这些内容无法撤销，白白消耗了宝贵的上下文窗口。

CC 的 Fork 机制解决了这个问题——子 Agent 在隔离的上下文中运行，共享父对话的 Prompt Cache（不额外烧 token），完成后只传回结论（synthesis），不污染主上下文。

#### CC 架构映射

| CC 概念 | Prism 对应 |
|---------|-----------|
| Sub-agent fork | `ForkManager.fork()` |
| 独立 TAOR loop | Fork 出的 `QueryEngine` 实例 |
| `model: 'inherit'` 共享 cache | Fork 复用父 Agent 的 `PromptAssembler.get_static_prefix()` |
| 返回 synthesis | `ForkResult.synthesis` |
| Explore/Plan/General 三种内建 sub-agent | 复用 AgentPool 的 4 种定义 |

#### 数据流

```
主 Agent (QueryEngine)
    │
    │ 模型返回 "我需要先调研一下 X"
    │
    ├─ ForkManager.fork(agent_type="research", task="调研 X")
    │       │
    │       ▼
    │   子 Agent (独立 QueryEngine)
    │   ├─ 独立 messages[]（初始只含 fork task）
    │   ├─ 共享 PromptAssembler 的静态前缀（cache 命中）
    │   ├─ 独立 Harness Runtime（继承父级的护栏规则）
    │   ├─ 独立 ToolExecutionPipeline（工具集按 Agent 类型过滤）
    │   ├─ 执行 TAOR 循环
    │   └─ 完成 → 返回 ForkResult
    │       │
    │       ▼
    ├─ ForkResult.synthesis 注入主 Agent 的 messages[]
    │   （只有结论，不含探索过程的垃圾上下文）
    │
    └─ 主 Agent 继续基于 synthesis 执行
```


> **Fork 深度限制 (P0)**：`ForkManager` 增加 `max_fork_depth: int = 2` 参数。Fork 内再 Fork 时深度递增，达到 `max_fork_depth` 时返回错误 `ForkDepthExceeded("最大 Fork 深度为 {max_fork_depth}")` 而非继续嵌套。防止无限递归 Fork 消耗资源。

> **Fork 超时**：`ForkManager.fork()` 增加 `fork_timeout: int = 300`（秒）参数。子 Agent 执行超过此时间强制终止并返回超时错误。

#### 验收标准

- ForkManager 能创建子 Agent 并在隔离上下文中执行
- 子 Agent 的 messages 不污染父 Agent
- 子 Agent 的 PromptAssembler 静态前缀与父 Agent 字节级一致（cache 共享）
- 子 Agent 完成后返回 synthesis 文本
- 子 Agent 的 Harness 护栏规则继承父级
- 子 Agent 的工具集按 Agent 类型过滤
- 子 Agent 的回调事件带有 fork 标识（前端可区分显示）

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的 Fork 机制——子 Agent 上下文隔离。Task 4.1 的 AgentPool 已完成。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

Task 4.1 已完成

## 要创建的文件

```
executor/coordinator/
├── fork_manager.py            # Fork 管理器
└── fork_result.py             # Fork 结果结构
```

## 实现规范

### 1. executor/coordinator/fork_result.py

```python
@dataclass
class ForkResult:
    """子 Agent 执行结果"""
    agent_type: str              # 子 Agent 类型
    task: str                    # 原始任务描述
    synthesis: str               # 结论摘要（注入主 Agent 的 messages）
    success: bool                # 是否成功完成
    turn_count: int              # 子 Agent 的循环次数
    input_tokens: int            # 子 Agent 的 token 消耗
    output_tokens: int
    error: str | None = None     # 失败时的错误信息
```

### 2. executor/coordinator/fork_manager.py

```python
"""
Fork 管理器 — 子 Agent 上下文隔离

核心原则：
1. 子 Agent 拥有独立的 messages[]（初始只含 fork task）
2. 子 Agent 共享父 Agent 的 PromptAssembler 静态前缀（cache 共享）
3. 子 Agent 拥有独立的 Harness Runtime（继承父级护栏规则）
4. 子 Agent 的工具集按 Agent 类型过滤
5. 完成后只返回 ForkResult.synthesis，不传回完整 messages

使用方式（在 QueryEngine 或 Coordinator 中调用）：
    fork_manager = ForkManager(parent_assembler, pool, pipeline_factory, callback)
    result = await fork_manager.fork(
        agent_type="research",
        task="调研竞品 X 的定价策略",
    )
    # result.synthesis 注入主 Agent 的 messages
"""

class ForkManager:
    def __init__(
        self,
        parent_assembler: PromptAssembler,  # 共享静态前缀
        agent_pool: AgentPool,
        adapter: ModelAdapter,              # 共享 Provider
        budget_factory,                     # 创建独立的 ContextBudgetManager
        callback: BackendCallback,
        harness_factory,                    # 创建独立的 HarnessRuntime
        settings,
    ):
        self._parent_assembler = parent_assembler
        self._pool = agent_pool
        self._adapter = adapter
        self._budget_factory = budget_factory
        self._callback = callback
        self._harness_factory = harness_factory
        self._settings = settings
    
    async def fork(self, agent_type: str, task: str) -> ForkResult:
        """
        创建子 Agent 并在隔离上下文中执行。
        
        步骤：
        1. 从 AgentPool 获取 Agent 定义
        2. 创建子 PromptAssembler（复用父级静态前缀，独立动态部分）
        3. 过滤工具集
        4. 创建独立的 ContextBudgetManager
        5. 创建独立的 ToolExecutionPipeline + Harness
        6. 创建独立的 QueryEngine
        7. 执行 TAOR 循环
        8. 从最后的 assistant 消息中提取 synthesis
        9. 返回 ForkResult
        """
        agent_def = self._pool.get(agent_type)
        
        # 通知前端 fork 开始
        await self._callback.harness_event("fork_start", {
            "agent_type": agent_type,
            "task": task[:200],
        })
        
        try:
            # 构建子 Agent 的组件（全部独立实例）
            child_assembler = self._create_child_assembler(agent_def)
            child_budget = self._budget_factory()
            child_registry = self._create_filtered_registry(agent_def)
            child_pipeline = ToolExecutionPipeline(child_registry, child_budget)
            child_harness = self._harness_factory(agent_def)
            child_harness.inject_into_pipeline(child_pipeline)
            
            child_engine = QueryEngine(
                adapter=self._adapter,
                assembler=child_assembler,
                pipeline=child_pipeline,
                budget=child_budget,
                callback=self._callback,
                max_turns=agent_def.max_turns,
                middleware_pipeline=child_harness.middleware,
            )
            
            # 执行
            await child_engine.run(task)
            
            # 提取 synthesis（最后一条 assistant 消息的文本内容）
            synthesis = self._extract_synthesis(child_engine._messages)
            
            result = ForkResult(
                agent_type=agent_type,
                task=task,
                synthesis=synthesis,
                success=True,
                turn_count=child_engine._turn_count,
                input_tokens=child_engine._total_input_tokens,
                output_tokens=child_engine._total_output_tokens,
            )
        except Exception as e:
            result = ForkResult(
                agent_type=agent_type,
                task=task,
                synthesis="",
                success=False,
                turn_count=0,
                input_tokens=0,
                output_tokens=0,
                error=str(e),
            )
        
        await self._callback.harness_event("fork_end", {
            "agent_type": agent_type,
            "success": result.success,
            "turn_count": result.turn_count,
        })
        
        return result
    
    def _create_child_assembler(self, agent_def: AgentDefinition) -> PromptAssembler:
        """
        创建子 PromptAssembler。
        关键：复用父级的静态前缀（字节级一致，cache 命中）。
        只有动态部分（agent_type → session_guidance）不同。
        """
        child = PromptAssembler(
            agent_type=agent_def.agent_type,
            tools=[],  # 先设空，后续 build 时会传入
        )
        # 强制复用父级的静态缓存
        child._static_cache = self._parent_assembler.get_static_prefix()
        return child
    
    def _create_filtered_registry(self, agent_def: AgentDefinition) -> ToolRegistry:
        """根据 Agent 定义过滤工具，返回新的 ToolRegistry"""
        ...
    
    def _extract_synthesis(self, messages: list[PrismMessage]) -> str:
        """从 messages 尾部提取最后一条 assistant 文本作为 synthesis"""
        for msg in reversed(messages):
            if msg.role == "assistant":
                texts = [b.text for b in msg.content if hasattr(b, 'text') and b.text]
                if texts:
                    return "\n".join(texts)
        return "[子 Agent 未返回有效结论]"
```

### 3. 注册 Fork 工具到 ToolRegistry

创建 `executor/tools/builtin/fork.py`：

```python
"""
Fork 工具 — 允许 Agent 主动发起子 Agent

模型可以通过调用此工具来 fork 一个专业化子 Agent。
这是 Agent 自主编排的关键——模型决定何时需要 fork，Runtime 执行。
"""

class ForkTool(BaseTool):
    def __init__(self, fork_manager: ForkManager):
        self._fork_manager = fork_manager
    
    @property
    def name(self): return "fork_agent"
    
    @property
    def description(self):
        return (
            "派生一个专业化子 Agent 来执行特定子任务。"
            "子 Agent 在隔离的上下文中运行，完成后将结论返回给你。"
            "可用的 Agent 类型: research（只读调研）, planner（制定计划）, verifier（验证结果）。"
        )
    
    @property
    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "agent_type": {
                    "type": "string",
                    "enum": ["research", "planner", "verifier"],
                    "description": "子 Agent 类型",
                },
                "task": {
                    "type": "string",
                    "description": "交给子 Agent 的任务描述",
                },
            },
            "required": ["agent_type", "task"],
        }
    
    async def execute(self, tool_input: dict) -> ToolResult:
        result = await self._fork_manager.fork(
            agent_type=tool_input["agent_type"],
            task=tool_input["task"],
        )
        if result.success:
            return ToolResult(
                content=f"[{result.agent_type} Agent 完成，{result.turn_count} 轮，"
                        f"{result.input_tokens + result.output_tokens} tokens]\n\n"
                        f"{result.synthesis}",
            )
        else:
            return ToolResult(
                content=f"子 Agent 执行失败: {result.error}",
                is_error=True,
            )
```

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/coordinator/fork_result.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/coordinator/fork_manager.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/tools/builtin/fork.py

# 2. ForkResult 结构测试
docker compose -f docker-compose.dev.yml exec backend python -c "
from executor.coordinator.fork_result import ForkResult

r = ForkResult(
    agent_type='research',
    task='test',
    synthesis='结论内容',
    success=True,
    turn_count=5,
    input_tokens=1000,
    output_tokens=500,
)
assert r.success
assert r.synthesis == '结论内容'
print('ForkResult: PASS')
"

# 3. 集成测试需要真实 API Key，手动执行
```

## 完成后

1. 更新 PROGRESS.md
2. 更新 DECISIONS.md：记录 ADR-014（Fork 上下文隔离——共享静态缓存 + 独立 messages + synthesis 回传）
3. 加载 Simplify skill 审查
4. 加载 PJR skill 验证
5. `git add -A && git commit -m "feat: Fork & Context Isolation with cache-sharing sub-agents"`
```

---

## Task 4.3: Coordinator-Workers 编排

### Part A — 设计与解释

#### 问题陈述

对于复杂任务（需要多步骤、多角色协作），单 Agent 或单次 Fork 不够——需要一个 Coordinator 来拆解任务、分配给 Worker Agents、收集结果、合成最终输出。

CC 的 Coordinator Mode：Coordinator 被剥夺直接操作能力，只保留 Agent（派生子代理）、SendMessage、TaskStop 三个"元工具"。工作流固定为 Research → Synthesis → Implementation → Verification。

Prism 的 Coordinator 模式：简单任务走单 Agent 直接执行；当 Planner Agent 判定任务需要多步骤时，系统自动切换到 Coordinator 模式。

#### CC 架构映射

| CC 概念 | Prism 对应 |
|---------|-----------|
| Coordinator 剥夺操作能力 | Coordinator 只持有 fork_agent + synthesize 工具 |
| Workers 携带具体工具 | Fork 的子 Agent 按类型持有不同工具集 |
| Research → Synthesis → Implementation → Verification | Planner 输出的 step 列表按顺序执行 |


> **解析可靠性**：`Plan.parse_from_text()` 采用两级策略：
> 1. 优先使用 structured output（要求模型返回 JSON 格式的计划）
> 2. 如果模型不支持 structured output，回退到正则解析 + 一次 retry（将解析失败的结果连同原始文本重新发送给模型要求修正格式）

#### 验收标准

- Coordinator 能解析 Planner 输出的结构化计划
- 按计划顺序 fork 子 Agent 执行每个 step
- 每个 step 的结果累积，供后续 step 参考
- 最终输出合成所有 step 的结果
- step 失败时 Coordinator 可以决定跳过/重试/终止
- 通过 SSE 向前端推送 plan_step / step_start / step_end 事件

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的 Coordinator-Workers 编排模式。Task 4.1（Agent 专业化）和 4.2（Fork）已完成。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

Task 4.1 和 4.2 已完成

## 要创建/修改的文件

```
executor/coordinator/
├── coordinator.py             # Coordinator 编排器
└── plan.py                    # Plan 数据结构
executor/engine/
└── synthesizer.py             # 多步骤结果合成
```

## 实现规范

### 1. executor/coordinator/plan.py

```python
"""
Plan 数据结构 — Planner Agent 的输出格式

Coordinator 解析 Planner 的结构化输出为 Plan 对象，然后按步骤执行。
"""

from dataclasses import dataclass, field

@dataclass
class PlanStep:
    """单个执行步骤"""
    step_id: int
    description: str
    agent_type: str              # "research" | "general" | "verifier"
    task_prompt: str             # 交给子 Agent 的具体指令
    depends_on: list[int] = field(default_factory=list)  # 依赖的 step_id 列表
    status: str = "pending"      # "pending" | "running" | "completed" | "failed" | "skipped"
    result: str = ""             # 执行结果

@dataclass
class Plan:
    """执行计划"""
    task_summary: str            # 任务理解
    steps: list[PlanStep]
    
    @classmethod
    def parse_from_text(cls, planner_output: str) -> "Plan":
        """
        从 Planner Agent 的文本输出解析为 Plan 对象。
        
        支持两种格式：
        1. 结构化 JSON（Planner 遵循 output_format 时）
        2. Markdown 列表（回退解析）
        
        解析失败时返回单步 Plan（整个任务作为一个 general step）。
        """
        ...
```

### 2. executor/coordinator/coordinator.py

```python
"""
Coordinator — 多步骤任务编排器

工作流：
1. 接收用户任务
2. Fork Planner Agent 生成执行计划
3. 解析计划为 Plan 对象
4. 按步骤顺序 Fork Worker Agents 执行
5. 每个 step 完成后，将结果累积到上下文
6. 可选：Fork Verifier Agent 验证最终结果
7. 调用 Synthesizer 合成最终输出

简单任务判定：如果 Planner 返回的计划只有 1 个步骤，
跳过 Coordinator 模式，直接由 General Agent 执行。
"""

class Coordinator:
    def __init__(
        self,
        fork_manager: ForkManager,
        callback: BackendCallback,
        synthesizer: "Synthesizer",
    ):
        self._fork = fork_manager
        self._callback = callback
        self._synthesizer = synthesizer
    
    async def execute(self, user_prompt: str) -> str:
        """
        执行完整的 Coordinator 工作流。
        返回最终合成结果文本。
        """
        # Step 1: 规划
        plan = await self._plan(user_prompt)
        
        # 简单任务判定
        if len(plan.steps) <= 1:
            # 直接由 general agent 执行，不走 Coordinator
            result = await self._fork.fork(agent_type="general", task=user_prompt)
            return result.synthesis
        
        # Step 2: 按顺序执行
        step_results: list[str] = []
        for step in plan.steps:
            await self._callback.emit("step_start", {"step_id": step.step_id})
            
            # 将已完成步骤的结果注入到当前步骤的上下文中
            context_prefix = self._build_step_context(plan, step_results, step)
            full_task = f"{context_prefix}\n\n当前任务：{step.task_prompt}"
            
            result = await self._fork.fork(
                agent_type=step.agent_type,
                task=full_task,
            )
            
            step.status = "completed" if result.success else "failed"
            step.result = result.synthesis
            step_results.append(result.synthesis)
            
            await self._callback.emit("step_end", {
                "step_id": step.step_id,
                "status": step.status,
            })
            
            # 失败处理：记录但继续（不中断整个流程）
            if not result.success:
                step.result = f"[步骤失败: {result.error}]"
        
        # Step 3: 合成
        final = self._synthesizer.synthesize(
            task_summary=plan.task_summary,
            step_results=[(s.description, s.result) for s in plan.steps],
        )
        
        return final
    
    async def _plan(self, user_prompt: str) -> Plan:
        """Fork Planner Agent 生成计划"""
        result = await self._fork.fork(
            agent_type="planner",
            task=user_prompt,
        )
        
        if not result.success:
            # 规划失败，回退到单步 general
            return Plan(
                task_summary=user_prompt,
                steps=[PlanStep(step_id=1, description=user_prompt, agent_type="general", task_prompt=user_prompt)],
            )
        
        plan = Plan.parse_from_text(result.synthesis)
        
        # 通知前端计划
        for step in plan.steps:
            await self._callback.emit("plan_step", {
                "step_id": step.step_id,
                "type": step.agent_type,
                "description": step.description,
            })
        
        return plan
    
    def _build_step_context(self, plan: Plan, results_so_far: list[str], current_step: PlanStep) -> str:
        """为当前步骤构建上下文前缀，包含已完成步骤的结果"""
        if not results_so_far:
            return f"总体任务：{plan.task_summary}"
        
        parts = [f"总体任务：{plan.task_summary}", "", "已完成的步骤："]
        for i, (step, result) in enumerate(zip(plan.steps[:len(results_so_far)], results_so_far)):
            parts.append(f"步骤 {step.step_id} ({step.description}): {result[:500]}")
        
        return "\n".join(parts)
```

### 3. executor/engine/synthesizer.py

```python
"""
Synthesizer — 多步骤结果合成

将 Coordinator 执行的多个步骤的结果合成为一个连贯的最终输出。
Phase 1 使用模板化合成（不调用模型），Phase 2 可升级为 LLM 合成。
"""

class Synthesizer:
    def synthesize(self, task_summary: str, step_results: list[tuple[str, str]]) -> str:
        """
        合成最终输出。
        
        step_results: [(description, result), ...]
        """
        parts = [f"## 任务完成\n\n**目标**：{task_summary}\n"]
        
        for desc, result in step_results:
            parts.append(f"### {desc}\n{result}\n")
        
        return "\n".join(parts)
```

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/coordinator/plan.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/coordinator/coordinator.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/engine/synthesizer.py

# 2. Plan 解析测试
docker compose -f docker-compose.dev.yml exec backend python -c "
from executor.coordinator.plan import Plan, PlanStep

# 手动构造 Plan
plan = Plan(
    task_summary='调研竞品定价',
    steps=[
        PlanStep(step_id=1, description='搜索竞品列表', agent_type='research', task_prompt='搜索市面上的竞品'),
        PlanStep(step_id=2, description='整理定价表格', agent_type='general', task_prompt='将搜索结果整理为表格'),
    ],
)
assert len(plan.steps) == 2
assert plan.steps[0].agent_type == 'research'
print('Plan construction: PASS')

# Synthesizer 测试
from executor.engine.synthesizer import Synthesizer
s = Synthesizer()
result = s.synthesize('调研竞品定价', [('搜索', '找到 5 个竞品'), ('整理', '表格已生成')])
assert '调研竞品定价' in result
assert '搜索' in result
print('Synthesizer: PASS')

print('\nAll Task 4.3 checks passed!')
"
```

## 完成后

1. 更新 PROGRESS.md
2. 更新 DECISIONS.md：记录 ADR-015（Coordinator-Workers——Planner 规划 + Fork 执行 + Synthesizer 合成）
3. 加载 Simplify skill 审查
4. 加载 PJR skill 验证
5. `git add -A && git commit -m "feat: Coordinator-Workers orchestration with Plan parsing and Synthesizer"`
```

---

## Task 4.4: Agent 类型自动选择与任务路由

### Part A — 设计与解释

#### 问题陈述

用户提交任务时不应该需要手动选择 Agent 类型。系统需要根据任务内容自动判断：简单任务交给 General Agent 直接执行，复杂任务走 Coordinator 模式。这个判断逻辑集成到 `executor/__main__.py` 的入口处。

#### 路由策略

```
用户任务
    │
    ▼
TaskRouter.route()
    ├─ 任务明确简单（"帮我搜索 X"、"翻译这段话"）
    │   → General Agent 直接执行
    │
    ├─ 任务明确要求某种 Agent（"帮我验证"、"帮我做个计划"）
    │   → 对应 Agent 直接执行
    │
    └─ 任务模糊或复杂（"帮我调研竞品并写报告"）
        → Coordinator 模式（Planner 拆解 → Workers 执行 → Synthesizer 合成）
```

Phase 1 路由策略使用关键词匹配（确定性规则，ms 级），不调用模型。Phase 2 可升级为 LLM 分类。


> **国际化补充 (P1)**：所有路由模式补充英文关键词。示例：
> - COORDINATOR_PATTERNS 新增: `r"(analyze|research|compare).{0,10}(and|then).{0,10}(implement|build|create)"`, `r"(step by step|multi-step|complex).{0,10}(task|project|workflow)"`
> - AGENT_TYPE_PATTERNS 中 research/planner/verifier 各补充对应英文模式
> - PLUGIN_BUILDER_PATTERNS（新增，见 Task 4.5）同时包含中英文

#### 验收标准

- TaskRouter 能根据任务内容选择路由策略
- 简单任务直接走 General Agent
- 包含"计划"/"调研并"/"分步"等关键词的复杂任务走 Coordinator
- 显式指定 Agent 类型时直接使用（如会话配置中指定了 agent_type）
- 路由决策记录到 audit_logs
- 完整的 `__main__.py` 入口将 DOC-02 到 DOC-04 的所有组件串联

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的任务路由和完整入口。DOC-02 到 DOC-04 的所有组件已实现。本 Task 将它们串联为一个可运行的 Agent 执行器。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

DOC-02 全部 Task + DOC-03 全部 Task + Task 4.1-4.3 已完成

## 要创建/修改的文件

```
executor/
├── router.py                  # TaskRouter 任务路由
└── __main__.py                # 完整入口（串联所有组件）
```

## 实现规范

### 1. executor/router.py

```python
"""
TaskRouter — 任务路由

根据任务内容决定执行策略：
- "direct:{agent_type}" — 指定 Agent 直接执行
- "coordinator" — 走 Coordinator 模式

Phase 1 使用关键词匹配（确定性规则），不调用模型。
"""

from dataclasses import dataclass

@dataclass
class RouteDecision:
    mode: str               # "direct" | "coordinator"
    agent_type: str         # direct 模式时的 Agent 类型
    reason: str             # 路由决策理由（写入 audit_logs）

# 触发 Coordinator 的关键词模式
COORDINATOR_PATTERNS = [
    "分步", "step by step", "多个步骤",
    "调研并", "搜索并",
    "先.*然后.*最后",
    "制定计划并执行",
    "全面分析",
    "完整报告",
]

# 触发特定 Agent 的关键词
AGENT_TYPE_PATTERNS = {
    "research": ["帮我搜索", "帮我查", "查一下", "调研", "了解一下"],
    "planner": ["帮我规划", "制定计划", "怎么做", "步骤是什么"],
    "verifier": ["帮我验证", "检查一下", "是否正确", "有没有问题"],
}

class TaskRouter:
    def route(self, prompt: str, explicit_agent_type: str | None = None) -> RouteDecision:
        """
        根据任务内容和显式配置决定路由。
        
        优先级：
        1. 显式指定 agent_type → 直接使用
        2. 关键词匹配 Coordinator → Coordinator 模式
        3. 关键词匹配特定 Agent → 该 Agent 直接执行
        4. 默认 → General Agent 直接执行
        """
        # 1. 显式指定
        if explicit_agent_type:
            return RouteDecision(
                mode="direct",
                agent_type=explicit_agent_type,
                reason=f"显式指定: {explicit_agent_type}",
            )
        
        prompt_lower = prompt.lower()
        
        # 2. Coordinator 模式
        import re
        for pattern in COORDINATOR_PATTERNS:
            if re.search(pattern, prompt_lower):
                return RouteDecision(
                    mode="coordinator",
                    agent_type="general",
                    reason=f"关键词匹配 Coordinator: {pattern}",
                )
        
        # 3. 特定 Agent
        for agent_type, patterns in AGENT_TYPE_PATTERNS.items():
            for pattern in patterns:
                if pattern in prompt_lower:
                    return RouteDecision(
                        mode="direct",
                        agent_type=agent_type,
                        reason=f"关键词匹配 {agent_type}: {pattern}",
                    )
        
        # 4. 默认
        return RouteDecision(
            mode="direct",
            agent_type="general",
            reason="默认路由: general",
        )
```

### 2. executor/__main__.py — 完整入口

完整实现入口，串联所有组件。关键流程：

```python
"""
Prism v2 Agent 执行器入口

用法：python -m prism.executor --run-id=019... --callback-url=http://... --callback-secret=...

完整生命周期：
1. 解析命令行参数
2. 从 DB 读取 Run 配置
3. 初始化 Provider → Adapter
4. 初始化 ToolRegistry（注册内置工具）
5. TaskRouter 路由决策
6. AgentPool 获取 Agent 定义
7. 初始化 PromptAssembler（传入 Agent 类型和过滤后的工具集）
8. 初始化 ContextBudgetManager
9. 初始化 Harness Runtime
10. 初始化 ToolExecutionPipeline（注入 Harness）
11. 初始化 ForkManager + Coordinator（如需要）
12. 初始化 CompactionPipeline + MemoryManager
13. 根据路由决策执行（direct → QueryEngine / coordinator → Coordinator）
14. 将 harness_summary 写回 runs 表
15. 清理退出
"""
```

具体实现代码由 Claude Code 根据上述流程和已有组件填充。每一步都有对应的已实现模块，不需要新造依赖。所有组件的初始化参数和调用方式在各自的 Task 文档中已定义。

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/router.py

# 2. 路由测试
docker compose -f docker-compose.dev.yml exec backend python -c "
from executor.router import TaskRouter, RouteDecision

router = TaskRouter()

# 简单任务 → General
r = router.route('帮我翻译这段话')
assert r.mode == 'direct' and r.agent_type == 'general'
print(f'Simple task: {r.mode}/{r.agent_type} — {r.reason}')

# 搜索任务 → Research
r = router.route('帮我搜索一下 GitHub 上的 prism 项目')
assert r.mode == 'direct' and r.agent_type == 'research'
print(f'Search task: {r.mode}/{r.agent_type} — {r.reason}')

# 验证任务 → Verifier
r = router.route('帮我验证一下这个 API 是否正确')
assert r.mode == 'direct' and r.agent_type == 'verifier'
print(f'Verify task: {r.mode}/{r.agent_type} — {r.reason}')

# 复杂任务 → Coordinator
r = router.route('帮我调研并整理竞品的定价策略，写一份完整报告')
assert r.mode == 'coordinator'
print(f'Complex task: {r.mode}/{r.agent_type} — {r.reason}')

# 显式指定 → 直接使用
r = router.route('任意内容', explicit_agent_type='planner')
assert r.mode == 'direct' and r.agent_type == 'planner'
print(f'Explicit: {r.mode}/{r.agent_type} — {r.reason}')

print('\nAll Task 4.4 checks passed!')
"

# 3. 完整入口编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/__main__.py

# 4. 端到端测试（需要真实 API Key + DB，手动执行）
# 在 DB 中创建一个 Run 记录
# 执行：python -m prism.executor --run-id=... --callback-url=... --callback-secret=...
# 观察 Backend 收到的回调事件和 SSE 推送
```

## 完成后

1. 更新 PROGRESS.md
2. 更新 DECISIONS.md：记录 ADR-016（Phase 1 关键词路由——确定性规则优先，Phase 2 升级 LLM 分类）
3. 加载 Simplify skill 审查
4. 加载 PJR skill 验证
5. `git add -A && git commit -m "feat: TaskRouter + complete executor entry point wiring all components"`
```

---

> **文档维护说明**：本文档的 5 个 Task 完成后，Prism v2 将拥有完整的 Agent 编排能力：4 种专业化 Agent 定义 + AgentPool 工厂 + Fork 上下文隔离（cache 共享 + synthesis 回传）+ Coordinator-Workers 模式（Planner 规划 → Fork 执行 → Synthesizer 合成）+ TaskRouter 自动路由 + PluginBuilder Agent（多轮对话 + Harness 双保险）+ 完整的 executor 入口（串联 DOC-02 至 DOC-04 的全部组件）。这是 DOC-05（Plugin Ecosystem）的基础。
> **最后更新**: 2026-04-05 | **下一步**: DOC-05 Plugin Ecosystem

---

## Task 4.5: PluginBuilder Agent 与多轮对话流程

### Part A — 设计与解释

#### 问题陈述

用户提出"帮我创建一个插件"时，通用 Agent 会直接开始写文件——跳过需求澄清、没有设计确认、没有边界讨论，生成的插件往往偏离真实需求且质量不稳定。

PluginBuilder Agent 是一个专用的插件创建 Agent，通过 **Harness 双保险机制**强制执行多轮对话流程：先充分收集需求（5-8 轮），再展示设计方案（用户确认），然后执行生成，最后运行加载验证。任何阶段跳跃都会被 Harness 拦截。

#### Agent 定义

```python
# executor/agents/plugin_builder.py

PLUGIN_BUILDER = AgentDefinition(
    name="plugin_builder",
    display_name="插件构建器",
    system_prompt_override=(
        "你是 Prism 插件构建专家。你的工作是通过多轮对话充分理解用户的插件需求，"
        "然后设计并生成符合 Prism 插件规范（CC 兼容格式）的完整插件。\n\n"
        "你绝对不能一键生成插件。你必须按照以下流程工作：\n"
        "1. 需求收集阶段（5-8 轮对话，每轮最多 5 个问题）\n"
        "2. 设计方案展示阶段（展示完整设计，等待用户确认）\n"
        "3. 生成执行阶段（按确认的设计逐个生成文件）\n"
        "4. 验证阶段（加载测试 + 结果汇报）\n\n"
        "每个阶段必须获得用户明确确认才能推进。"
    ),
    allowed_tools=[
        "file_read", "file_write", "bash",
        "web_search", "skill_install",
    ],
    denied_tools=[],
    read_only=False,
    behavior_constraints=[
        "严禁一键生成。检测到插件创建意图后，必须进入多轮需求收集流程。",
        "需求收集阶段：最少 5 轮、最多 8 轮对话，每轮最多问 5 个问题。",
        "目标：最大化清晰所有模糊内容和可能的边界情况。",
        "每个阶段必须获得用户明确的确认才能推进到下一阶段。",
        "生成的插件必须符合 Prism 插件规范（CC 兼容格式）。",
        "生成完成后必须自动运行加载测试验证插件可用性。",
    ],
    output_format="structured_dialogue",
    max_turns=50,
)
```

#### 多轮对话流程

```
阶段 1: 需求收集（5-8 轮，每轮 ≤5 问题）
│
├── 第 1 轮：插件目标和核心使用场景
│   ├── 这个插件要解决什么问题？
│   ├── 目标用户是谁？
│   ├── 核心使用场景有哪些？
│   └── 有没有参考的产品或工具？
│
├── 第 2 轮：能力需求
│   ├── 需要哪些 Skills？（信息搜索、数据分析、内容生成等）
│   ├── 需要接入哪些外部服务/MCP？
│   ├── 需要哪些 Hook 控制？（前置检查、后置验证等）
│   └── 有没有需要累积的领域知识？
│
├── 第 3 轮：行为约束与安全
│   ├── Agent 在什么情况下应该被阻止？
│   ├── 输出格式有什么要求？
│   ├── 有没有合规性要求？（数据溯源、隐私保护等）
│   └── 权限边界在哪里？
│
├── 第 4 轮：边界场景与异常处理
│   ├── 用户输入模糊时如何处理？
│   ├── 外部服务不可用时的降级策略？
│   ├── 输出不符合预期时的重试策略？
│   └── 与其他插件的兼容性考虑？
│
├── 第 5 轮：细节确认与补充
│   ├── 回顾前几轮的理解是否正确
│   ├── 有没有遗漏的需求？
│   └── 优先级排序（核心 vs. 锦上添花）
│
├── [可选] 第 6-8 轮：深度探讨
│   └── 针对前几轮暴露的复杂点进一步细化
│
└── Harness 门控：轮数 < 5 时阻止进入阶段 2

阶段 2: 设计方案展示
│
├── 输出插件结构概览（目录树）
├── 各组件设计摘要
│   ├── Skills 列表 + 每个 Skill 的功能描述
│   ├── Hook 配置 + 触发时机说明
│   ├── MCP 接入点（如有）
│   └── 垂类调教定义（行为约束 + 输出格式 + 领域知识）
├── plugin.yaml 预览
├── Harness 配置覆盖预览
│
└── 等待用户明确"确认设计"→ Harness 门控检查

阶段 3: 生成执行
│
├── 创建插件目录结构
├── 逐个生成文件
│   ├── plugin.yaml（Prism 超集格式）
│   ├── skills/（每个 Skill 的 SKILL.md）
│   ├── hooks/（Hook handler 脚本）
│   ├── mcp/（MCP 配置，如需要）
│   └── README.md
├── 注册到 PluginHost
│
└── 进入阶段 4

阶段 4: 验证
│
├── 插件加载测试（PluginHost.load_plugin()）
├── Skills 加载测试（SkillLoader.scan_and_register()）
├── Hook 触发测试（模拟事件触发 Hook handler）
├── 汇报结果给用户
│
└── 完成
```

#### Harness 双保险: PluginBuilderGate Middleware

```python
# executor/harness/middleware/plugin_builder_gate.py

class PluginBuilderGate(Middleware):
    """
    仅对 PluginBuilder Agent 生效的阶段门控 Middleware。

    通过 context.metadata 追踪当前阶段和轮数：
    - plugin_build_phase: 1~4
    - phase_turn_count: 当前阶段已完成的对话轮数
    - design_confirmed: 用户是否确认了设计方案
    """

    MIN_COLLECTION_ROUNDS = 5
    MAX_COLLECTION_ROUNDS = 8
    MAX_QUESTIONS_PER_ROUND = 5

    def pre_turn(self, context: MiddlewareContext) -> MiddlewareContext:
        if context.agent_type != "plugin_builder":
            return context

        phase = context.metadata.get("plugin_build_phase", 1)
        turn_count = context.metadata.get("phase_turn_count", 0)

        if phase == 1:
            remaining = self.MIN_COLLECTION_ROUNDS - turn_count
            if remaining > 0:
                context.inject_constraint(
                    f"你仍在需求收集阶段。请继续提问以充分了解用户需求。"
                    f"还需要至少 {remaining} 轮对话。"
                    f"每轮最多问 {self.MAX_QUESTIONS_PER_ROUND} 个问题。"
                    f"目标：最大化清晰所有模糊内容和可能的边界情况。"
                )
            if turn_count >= self.MAX_COLLECTION_ROUNDS:
                context.inject_constraint(
                    "需求收集已达到上限轮数。请总结收集到的需求并进入设计方案展示。"
                )
                context.metadata["plugin_build_phase"] = 2
                context.metadata["phase_turn_count"] = 0

        elif phase == 2:
            if not context.metadata.get("design_confirmed"):
                context.inject_constraint(
                    "设计方案尚未获得用户确认。"
                    "请展示完整的设计方案并等待用户说'确认'后再开始生成。"
                    "绝对不能在用户确认前开始写任何文件。"
                )

        return context
```

#### Harness 双保险: GuardrailsEngine 规则

```python
# 新增 Guardrail 规则（hardcoded in platform_rules.py，不可覆盖）
GR_PLUGIN_CREATE_GUARD = GuardrailRule(
    id="GR-PLUGIN-CREATE-001",
    trigger="pre_tool_use",
    condition=lambda ctx: (
        ctx.tool_name in ["file_write", "bash"] and
        ctx.agent_type != "plugin_builder" and
        _is_plugin_file(ctx.tool_input)
    ),
    action="block",
    message="插件文件的创建/修改必须通过 PluginBuilder Agent 流程完成",
    platform_level=True,  # 不可被配置覆盖
)

def _is_plugin_file(tool_input: dict) -> bool:
    """检测是否在操作插件相关文件"""
    path = tool_input.get("path", "") or tool_input.get("command", "")
    plugin_patterns = [
        "plugin.yaml", "plugin.json", "SKILL.md",
        ".skills/", ".prism/plugins/", "hooks/preToolUse",
        "hooks/postToolUse",
    ]
    return any(p in path for p in plugin_patterns)
```

#### TaskRouter 扩展 (PLUGIN_BUILDER_PATTERNS)

```python
# executor/router.py — 在 Task 4.4 的 TaskRouter 基础上新增
PLUGIN_BUILDER_PATTERNS = [
    # 中文
    r"(创建|制作|开发|构建|搭建|生成|做).{0,10}(插件|plugin)",
    r"(帮我|请).{0,10}(做|弄|写|建).{0,10}(插件|plugin|skill)",
    # 英文
    r"(create|build|make|develop|generate).{0,10}(plugin|skill)",
    r"(help me|please).{0,10}(build|create|make).{0,10}(plugin|skill)",
]
# 匹配到时 → 路由到 plugin_builder Agent
```

#### 设计决策: ADR-017

**ADR-017: PluginBuilder Agent — 强制多轮对话 + Harness 双保险**

- **问题**: 用户提出"帮我创建插件"时，通用 Agent 缺乏结构化需求收集流程，导致生成的插件偏离需求且质量不稳定。
- **决策**: 专用 PluginBuilder Agent + Harness 双保险（Middleware 门控 + Guardrail 拦截），强制执行 4 阶段流程，不可绕过。
- **理由**: 插件创建是高复杂度、高定制化任务，需求不清晰的代价远高于多轮对话的摩擦成本。Harness 双保险确保即使 Agent 试图跳过阶段也会被系统拦截。
- **替代方案**: 单轮需求收集（rejected：太浅，边界情况无法覆盖）；纯 prompt 约束（rejected：不够可靠，模型可能绕过）。

#### 验收标准

1. 用户说"帮我创建一个金融分析插件" → 自动路由到 PluginBuilder Agent
2. Agent 在需求收集阶段提问 5-8 轮，每轮 ≤5 个问题
3. 需求收集不足 5 轮时，Agent 被 Harness 阻止进入设计阶段
4. 设计方案展示后，必须等待用户确认才进入生成阶段
5. 非 PluginBuilder Agent 尝试写 plugin.yaml 或 SKILL.md 时被 Guardrail 拦截
6. 生成完成后自动运行加载测试
7. 整个流程的每个阶段转换都有 audit_logs 记录

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt（待补充）

## 上下文

你正在构建 Prism v2 的 PluginBuilder Agent——专用插件创建 Agent + Harness 双保险。
Task 4.1-4.4 全部已完成。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

[完整 Claude Code 执行 Prompt 待 Task 5 完成后补充]
```

---

## 完成后

1. 更新 PROGRESS.md
2. 更新 DECISIONS.md：记录 ADR-017（PluginBuilder Agent——强制多轮对话 + Harness 双保险）
3. 加载 Simplify skill 审查
4. 加载 PJR skill 验证
5. `git add -A && git commit -m "feat: PluginBuilder Agent with multi-turn dialogue + Harness dual-guard"`
