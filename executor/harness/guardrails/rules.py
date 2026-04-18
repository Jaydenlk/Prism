"""
GuardrailRule — 护栏规则基类

进程边界：本模块只 import 标准库，禁止 import backend.app.*
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable


def _flatten_values(obj):
    """递归提取 dict/list 中所有叶子值"""
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _flatten_values(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _flatten_values(v)
    else:
        yield obj


@dataclass
class GuardrailRule:
    """护栏规则定义"""
    id: str
    reason: str
    scope: str = "platform"
    tool_pattern: str = ".*"
    input_patterns: list = field(default_factory=list)
    # 自定义匹配函数，用于复杂规则（如速率限制、跨用户检测）
    custom_match: Callable | None = None

    def matches(self, tool_name: str, tool_input: dict, run_context=None) -> bool:
        """
        检查规则是否匹配。
        1. tool_pattern 正则匹配 tool_name
        2. 若有 custom_match，调用自定义函数
        3. 否则对 tool_input 所有叶子值做 input_patterns 正则匹配
        """
        if not re.search(self.tool_pattern, tool_name):
            return False
        if self.custom_match:
            return self.custom_match(tool_name, tool_input, run_context)
        if not self.input_patterns:
            return False
        # 默认：对 tool_input 所有 string 值做 pattern 匹配
        flat = " ".join(str(v) for v in _flatten_values(tool_input))
        return any(re.search(p, flat, re.IGNORECASE) for p in self.input_patterns)
