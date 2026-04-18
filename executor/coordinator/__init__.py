"""
executor/coordinator — Fork 管理器、Plan 结构、Coordinator 编排

导出:
- ForkBriefing: 结构化 Fork 任务入参(v4 ADR-039)
- ForkResult: 子 Agent 执行结果
- ForkManager: Fork 管理器（子 Agent 上下文隔离）
- ForkDepthExceeded: Fork 深度超限异常
- FORK_HARD_CONSTRAINTS: 3 条 prompt-level 硬约束常量（ADR-038）
- Plan / PlanStep: Coordinator 执行计划(v4 ADR-040)
- serialize_plan / deserialize_plan: Plan 持久化助手
- Coordinator: 多步骤任务编排器(v4 ADR-040 checkpoint)

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from executor.coordinator.coordinator import Coordinator
from executor.coordinator.fork_briefing import FORK_HARD_CONSTRAINTS, ForkBriefing
from executor.coordinator.fork_manager import ForkDepthExceeded, ForkManager
from executor.coordinator.fork_result import ForkResult
from executor.coordinator.plan import Plan, PlanStep, deserialize_plan, serialize_plan

__all__ = [
    "ForkBriefing",
    "ForkResult",
    "ForkManager",
    "ForkDepthExceeded",
    "FORK_HARD_CONSTRAINTS",
    "Plan",
    "PlanStep",
    "serialize_plan",
    "deserialize_plan",
    "Coordinator",
]
