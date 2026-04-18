"""
executor.engine — Prompt 动态装配引擎（DOC-02 Task 2.4）

导出：
  PromptAssembler     — Prompt 动态装配引擎（21+ section）
  CACHE_BOUNDARY_MARKER — 静态/动态分界标记字面值
  MCPServerInfo       — MCP Server 信息（临时定义，DOC-05 Task 5.2 后替换）
  SkillInfo           — Skill 信息（临时定义，DOC-05 Task 5.1 后替换）
  ContextBudgetManager — 上下文预算管理器（Tier 0）
  TokenEstimator      — Token 估算 Protocol（依赖注入接口）

以及 21 个 section getter 函数（从 prompt_sections 直接 import 使用）。
"""

from executor.engine.context_budget import ContextBudgetManager, TokenEstimator
from executor.engine.prompt_assembler import (
    CACHE_BOUNDARY_MARKER,
    MCPServerInfo,
    PromptAssembler,
    SkillInfo,
)

__all__ = [
    "PromptAssembler",
    "CACHE_BOUNDARY_MARKER",
    "MCPServerInfo",
    "SkillInfo",
    "ContextBudgetManager",
    "TokenEstimator",
]
