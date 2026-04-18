"""
executor/coordinator — Fork 管理器与子 Agent 编排

导出:
- ForkBriefing: 结构化 Fork 任务入参(v4 ADR-035)
- ForkResult: 子 Agent 执行结果
- ForkManager: Fork 管理器（子 Agent 上下文隔离）
- ForkDepthExceeded: Fork 深度超限异常
- FORK_HARD_CONSTRAINTS: 3 条 prompt-level 硬约束常量（ADR-034）

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from executor.coordinator.fork_briefing import FORK_HARD_CONSTRAINTS, ForkBriefing
from executor.coordinator.fork_manager import ForkDepthExceeded, ForkManager
from executor.coordinator.fork_result import ForkResult

__all__ = [
    "ForkBriefing",
    "ForkResult",
    "ForkManager",
    "ForkDepthExceeded",
    "FORK_HARD_CONSTRAINTS",
]
