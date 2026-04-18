"""
HookDecision — Hook 执行结果的完整决策对象
对标 CC 的 src/services/tools/toolHooks.ts（11 个字段）

ADR-026: HookDecision 11 字段完整定义，不可砍字段。
ADR-027: merge_decisions() 合并规则按严格度降序执行。

进程边界：本模块只 import 标准库，禁止 import backend.app.*
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PermissionDecision = Literal["allow", "ask", "deny"]


@dataclass
class HookDecision:
    """11 字段完整定义（v4 ADR-026）"""
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
    # 用户消息（显示在 UI）
    message: str | None = None
    # 阻断性错误
    blocking_error: str | None = None
    # 审计
    reason: str | None = None
    handler_name: str | None = None


def merge_decisions(decisions: list[HookDecision]) -> HookDecision:
    """
    合并多个 Hook 的决策（v4 ADR-027）。
    严格度排序（高 → 低）：
      stop > prevent_continuation > permission_deny > permission_ask > permission_allow

    updated_input / updated_mcp_tool_output 冲突时 abort（不猜），raise ValueError
    additional_context 多个拼接 "\\n\\n"
    blocking_error 拼接 "; "
    message 拼接 "\\n"
    空 decisions list 返回空 HookDecision
    """
    if not decisions:
        return HookDecision()

    result = HookDecision()

    # stop 优先级最高 — 立即返回，不处理后续
    for d in decisions:
        if d.stop:
            result.stop = True
            result.stop_reason = d.stop_reason
            result.handler_name = d.handler_name
            return result

    # prevent_continuation 次优先级
    for d in decisions:
        if d.prevent_continuation:
            result.prevent_continuation = True
            if d.reason:
                result.reason = d.reason

    # permission 按严格度：deny > ask > allow
    permission_priority: dict[PermissionDecision | None, int] = {
        "deny": 3,
        "ask": 2,
        "allow": 1,
        None: 0,
    }
    result.permission_decision = max(
        (d.permission_decision for d in decisions),
        key=lambda p: permission_priority.get(p, 0),
        default=None,
    )

    # updated_input 冲突检测
    updated_inputs = [d.updated_input for d in decisions if d.updated_input is not None]
    if len(updated_inputs) > 1:
        raise ValueError(
            f"Multiple hooks want to modify input, refusing to guess: {updated_inputs}"
        )
    if updated_inputs:
        result.updated_input = updated_inputs[0]

    # updated_mcp_tool_output 同理
    updated_outputs = [
        d.updated_mcp_tool_output
        for d in decisions
        if d.updated_mcp_tool_output is not None
    ]
    if len(updated_outputs) > 1:
        raise ValueError(
            f"Multiple hooks want to modify MCP output: {updated_outputs}"
        )
    if updated_outputs:
        result.updated_mcp_tool_output = updated_outputs[0]

    # additional_context 拼接（"\n\n"）
    contexts = [d.additional_context for d in decisions if d.additional_context]
    if contexts:
        result.additional_context = "\n\n".join(contexts)

    # blocking_error 任一触发即阻断，多个拼接（"; "）
    errors = [d.blocking_error for d in decisions if d.blocking_error]
    if errors:
        result.blocking_error = "; ".join(errors)

    # message 拼接（"\n"）
    messages = [d.message for d in decisions if d.message]
    if messages:
        result.message = "\n".join(messages)

    return result
