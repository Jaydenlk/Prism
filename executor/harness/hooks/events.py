"""
Hook 事件类型定义 — 对标 CC 的 21 种生命周期事件

Phase 1 实现核心 8 种，其余在后续 DOC 中扩展。

进程边界：本模块只 import 标准库，禁止 import backend.app.*
"""

from __future__ import annotations

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
    tool_name: str = ""           # PreToolUse/PostToolUse 时有值
    tool_input: dict = field(default_factory=dict)
    tool_output: str = ""         # PostToolUse 时有值
    is_error: bool = False        # PostToolUseFailure 时 True
    run_id: str = ""
    session_id: str = ""
