"""
Middleware 抽象基类(v4:4 钩点)

4 钩点对应 TAOR 循环的 4 个观察/干预时机:
- pre_turn:       本轮 API 调用之前(可改写 messages / 注入上下文)
- pre_tool_use:   工具执行之前(可改写 tool_input / 决定 permission)
- post_tool_use:  工具执行之后(可改写 tool_result)
- post_turn:      本轮结束之后(可触发 compaction / 检测 loop)

context 是一个 mutable 对象,中间件之间通过它传递状态。

ADR-025: Middleware 4 钩点 — 对应 TAOR 循环的 4 个观察/干预时机。
进程边界: 本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MiddlewareContext:
    """Middleware 调用上下文(v4)

    所有字段均提供默认值，兼容 Part B 验证脚本的简短构造:
        TurnContext(turn_count=1, messages=[], run_id='test')
    """

    run_id: str = ""
    session_id: str = ""
    user_id: str = ""
    turn_count: int = 0
    agent_type: str = "general"
    messages: list = field(default_factory=list)          # 当前 messages
    system_prompt: str = ""
    tool_use_block: Any = None                            # pre_tool_use / post_tool_use 时有值
    tool_result_block: Any = None                         # post_tool_use 时有值
    abort: bool = False
    abort_reason: str = ""
    custom_data: dict = field(default_factory=dict)       # middleware 之间传递数据


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
