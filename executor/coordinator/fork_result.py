"""
ForkResult — 子 Agent 执行结果(v4 ADR-035)

包含子 Agent 的执行结论、token 消耗、状态等信息。
ForkManager.fork() 返回此结构，注入主 Agent 的 messages。

进程边界：本模块只 import 标准库，禁止 import backend.app.*
"""

from __future__ import annotations

from dataclasses import dataclass, field

from executor.coordinator.fork_briefing import ForkBriefing


@dataclass
class ForkResult:
    """子 Agent 执行结果"""

    agent_type: str                                          # 子 Agent 类型
    briefing: ForkBriefing                                   # v4:结构化入参
    synthesis: str                                           # 结论摘要(注入主 Agent 的 messages)
    success: bool                                            # 是否成功完成
    turn_count: int                                          # 子 Agent 的循环次数
    input_tokens: int                                        # 子 Agent 的输入 token 消耗
    output_tokens: int                                       # 子 Agent 的输出 token 消耗
    error: str | None = None                                 # 失败时的错误信息
    # v4:pre-fork 已验证的 capability 列表(可回溯)
    allowed_capabilities: list[str] = field(default_factory=list)
