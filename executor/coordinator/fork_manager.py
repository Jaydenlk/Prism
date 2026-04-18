"""
Fork 管理器 — 子 Agent 上下文隔离

核心原则：
1. 子 Agent 拥有独立的 messages[]（初始只含 fork task）
2. 子 Agent 共享父 Agent 的 PromptAssembler 静态前缀（cache 共享）
3. 子 Agent 拥有独立的 Harness Runtime（继承父级护栏规则）
4. 子 Agent 的工具集按 capability 白名单过滤（ADR-033）
5. 完成后只返回 ForkResult.synthesis，不传回完整 messages

使用方式（在 QueryEngine 或 Coordinator 中调用）：
    fork_manager = ForkManager(parent_assembler, pool, adapter, budget_factory,
                               callback, harness_factory, settings, root_registry)
    result = await fork_manager.fork(
        agent_type="research",
        briefing=ForkBriefing(goal="调研竞品 X 的定价策略", why="需要做对标分析"),
    )
    # result.synthesis 注入主 Agent 的 messages

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from executor.coordinator.fork_briefing import FORK_HARD_CONSTRAINTS, ForkBriefing
from executor.coordinator.fork_result import ForkResult
from executor.engine.prompt_assembler import PromptAssembler
from executor.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from executor.adapters.base import ModelAdapter, PrismMessage
    from executor.agents.base import AgentDefinition
    from executor.agents.pool import AgentPool
    from executor.callbacks.backend_callback import BackendCallback
    from executor.tools.base import BaseTool

logger = structlog.get_logger()


class ForkDepthExceeded(Exception):
    """子 Agent 嵌套深度超出限制（ADR 安全约束）"""


class ForkManager:
    """Fork 管理器：创建子 Agent 并在隔离上下文中执行（v4）"""

    def __init__(
        self,
        parent_assembler: PromptAssembler,    # 共享静态前缀
        agent_pool: "AgentPool",
        adapter: "ModelAdapter",              # 共享 Provider
        budget_factory,                        # 工厂函数: () -> ContextBudgetManager
        callback: "BackendCallback",
        harness_factory,                       # 工厂函数: (agent_def) -> HarnessRuntime
        settings,
        root_registry: ToolRegistry,           # 父 Agent 的完整工具注册表（capability 过滤源）
    ):
        self._parent_assembler = parent_assembler
        self._pool = agent_pool
        self._adapter = adapter
        self._budget_factory = budget_factory
        self._callback = callback
        self._harness_factory = harness_factory
        self._settings = settings
        self._root_registry = root_registry

    async def fork(
        self,
        agent_type: str,
        briefing: ForkBriefing,                           # v4:结构化入参
        required_capabilities: list[str] | None = None,  # v4:capability-based 白名单
        depth: int = 0,
        fork_timeout: int = 300,
        max_fork_depth: int = 2,
    ) -> ForkResult:
        """
        创建子 Agent 并在隔离上下文中执行(v4 修订)。

        步骤:
        1. 深度检查(ADR 安全性):depth >= max_fork_depth → ForkDepthExceeded
        2. 从 AgentPool 获取 Agent 定义
        3. v4:按 capability 白名单过滤工具(而非工具名列表)
        4. 创建子 PromptAssembler(复用父级静态前缀,system prompt 拼接 FORK_HARD_CONSTRAINTS)
        5. 创建独立 Budget / Pipeline / Harness / QueryEngine
        6. 执行 TAOR 循环(timeout 包裹)
        7. 提取 synthesis
        8. 返回 ForkResult
        """
        if depth >= max_fork_depth:
            raise ForkDepthExceeded(f"最大 Fork 深度为 {max_fork_depth}")

        agent_def = self._pool.get(agent_type)

        # v4:capability 过滤：优先 required_capabilities，其次 agent_def.allowed_capabilities
        allowed_caps: list[str] = (
            required_capabilities
            if required_capabilities is not None
            else (getattr(agent_def, "allowed_capabilities", None) or [])
        )

        # 通知前端 fork 开始
        await self._callback.harness_event("fork_start", {
            "agent_type": agent_type,
            "goal": briefing.goal[:200],
            "capabilities": allowed_caps,
            "depth": depth,
        })

        result: ForkResult
        try:
            # 构建子 Agent 的组件(全部独立实例)
            child_assembler = self._create_child_assembler(agent_def, inject_constraints=True)
            child_budget = self._budget_factory()
            child_registry = self._create_filtered_registry(agent_def, allowed_caps)

            # 延迟导入避免循环依赖
            from executor.tools.pipeline import ToolExecutionPipeline
            from executor.engine.query_engine import QueryEngine

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

            # v4:timeout 包裹
            await asyncio.wait_for(
                child_engine.run(briefing.to_prompt()),
                timeout=fork_timeout,
            )

            # 提取 synthesis(最后一条 assistant 消息的文本内容)
            synthesis = self._extract_synthesis(child_engine._messages)

            result = ForkResult(
                agent_type=agent_type,
                briefing=briefing,
                synthesis=synthesis,
                success=True,
                turn_count=child_engine._turn_count,
                input_tokens=child_engine._total_input_tokens,
                output_tokens=child_engine._total_output_tokens,
                allowed_capabilities=allowed_caps,
            )
        except asyncio.TimeoutError:
            result = ForkResult(
                agent_type=agent_type,
                briefing=briefing,
                synthesis="",
                success=False,
                turn_count=0,
                input_tokens=0,
                output_tokens=0,
                error=f"fork timeout after {fork_timeout}s",
                allowed_capabilities=allowed_caps,
            )
        except ForkDepthExceeded:
            raise
        except Exception as e:
            result = ForkResult(
                agent_type=agent_type,
                briefing=briefing,
                synthesis="",
                success=False,
                turn_count=0,
                input_tokens=0,
                output_tokens=0,
                error=str(e),
                allowed_capabilities=allowed_caps,
            )

        await self._callback.harness_event("fork_end", {
            "agent_type": agent_type,
            "success": result.success,
            "turn_count": result.turn_count,
        })

        return result

    def _create_child_assembler(
        self,
        agent_def: "AgentDefinition",
        inject_constraints: bool = True,
    ) -> PromptAssembler:
        """
        创建子 PromptAssembler(v4)。
        关键:复用父级的静态前缀(字节级一致,cache 命中)。
        只有动态部分(agent_type → session_guidance + FORK_HARD_CONSTRAINTS)不同。

        先调 get_static_prefix() 触发父级 cache 计算，然后直接赋值给子实例，
        避免子 fork 在首次 build 前 static_cache 为 None 的边界问题。
        """
        child = PromptAssembler(
            agent_type=agent_def.agent_type,
            tools=[],  # 先设空，后续 build 时会传入
        )
        # 强制复用父级的静态缓存（触发父级 cache 计算，字节级一致）
        parent_static = self._parent_assembler.get_static_prefix()
        child._static_cache = parent_static
        # 继承父级的 tools_hash，避免 cache 边界计算不一致
        child._tools_hash = self._parent_assembler._tools_hash
        if inject_constraints:
            # v4 ADR-034:把 3 条硬约束拼到动态 session_guidance 末尾
            child._extra_dynamic_tail = FORK_HARD_CONSTRAINTS
        return child

    def _create_filtered_registry(
        self,
        agent_def: "AgentDefinition",
        allowed_caps: list[str],
    ) -> ToolRegistry:
        """
        v4 ADR-033:按 capability 白名单过滤工具。
        Tool 实例声明自己的 capabilities，此方法只保留 capabilities ⊆ allowed_caps 的工具。

        allowed_caps 为空列表时：不过滤，返回所有工具（fork 不显式限定能力时等同父 Agent）。
        """
        child = ToolRegistry()
        for tool in self._root_registry.list_all():
            tool_caps = set(getattr(tool, "capabilities", []))
            if not allowed_caps or tool_caps.issubset(set(allowed_caps)):
                child.register(tool)
        return child

    def _extract_synthesis(self, messages: list) -> str:
        """从 messages 尾部提取最后一条 assistant 文本作为 synthesis"""
        for msg in reversed(messages):
            if msg.role == "assistant":
                texts = [
                    b.text
                    for b in msg.content
                    if hasattr(b, "text") and b.text
                ]
                if texts:
                    return "\n".join(texts)
        return "[子 Agent 未返回有效结论]"
