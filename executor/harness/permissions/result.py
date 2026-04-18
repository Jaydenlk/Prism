"""
PermissionResult — 权限决策结果

单独放置以避免循环 import：
- guardrails/engine.py 需要 PermissionResult
- permissions/engine.py 也需要 PermissionResult
- 两侧都从本模块 import，避免循环依赖

进程边界：本模块只 import 标准库，禁止 import backend.app.*
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class PermissionResult:
    """权限检查结果"""
    decision: Literal["allow", "deny"]
    reason: str = ""
    updated_input: dict | None = None
