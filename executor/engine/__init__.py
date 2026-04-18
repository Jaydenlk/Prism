"""
executor.engine — Prompt 动态装配引擎（DOC-02 Task 2.4）

导出：
  PromptAssembler     — Prompt 动态装配引擎（21+ section）
  CACHE_BOUNDARY_MARKER — 静态/动态分界标记字面值
  MCPServerInfo       — MCP Server 信息（临时定义，DOC-05 Task 5.2 后替换）
  SkillInfo           — Skill 信息（临时定义，DOC-05 Task 5.1 后替换）
  ContextBudgetManager — 上下文预算管理器（Tier 0）
  TokenEstimator      — Token 估算 Protocol（依赖注入接口，context_budget.py）

  DOC-12 Task 12.1 新增（ADR-110）：
  AnthropicTokenCounter     — 包装 ModelAdapter.count_tokens()，Claude 首选
  TiktokenEstimator         — tiktoken cl100k_base，OpenAI/DeepSeek
  CalibratingCharCountEstimator — 字符计数 + usage feedback 动态校准，fallback
  create_estimator          — 策略工厂函数

以及 21 个 section getter 函数（从 prompt_sections 直接 import 使用）。
"""

from executor.engine.context_budget import ContextBudgetManager, TokenEstimator
from executor.engine.prompt_assembler import (
    CACHE_BOUNDARY_MARKER,
    MCPServerInfo,
    PromptAssembler,
    SkillInfo,
)
from executor.engine.token_estimator import (
    AnthropicTokenCounter,
    CalibratingCharCountEstimator,
    TiktokenEstimator,
    create_estimator,
)

__all__ = [
    "PromptAssembler",
    "CACHE_BOUNDARY_MARKER",
    "MCPServerInfo",
    "SkillInfo",
    "ContextBudgetManager",
    "TokenEstimator",
    # ADR-110 — DOC-12 Task 12.1
    "AnthropicTokenCounter",
    "CalibratingCharCountEstimator",
    "TiktokenEstimator",
    "create_estimator",
]
