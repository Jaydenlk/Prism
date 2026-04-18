"""
TaskRouter — 任务路由

根据任务内容决定执行策略：
- "direct:{agent_type}" — 指定 Agent 直接执行
- "coordinator" — 走 Coordinator 模式

Phase 1 使用关键词匹配（确定性规则），不调用模型。
Phase 2 可升级为 LLM 分类（ADR-041，未实现）。

进程边界：本模块只在 executor 进程内使用，禁止 import backend.app.*
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class RouteDecision:
    mode: str        # "direct" | "coordinator"
    agent_type: str  # direct 模式时的 Agent 类型
    reason: str      # 路由决策理由（写入 audit_logs）


# ---------------------------------------------------------------------------
# 触发 Coordinator 的关键词模式（v4：中英文）
# ---------------------------------------------------------------------------
COORDINATOR_PATTERNS: list[str] = [
    r"分步",
    r"step by step",
    r"多个步骤",
    r"调研并",
    r"搜索并",
    r"先.*然后.*最后",
    r"制定计划并执行",
    r"全面分析",
    r"完整报告",
    # v4 英文
    r"(analyze|research|compare).{0,10}(and|then).{0,10}(implement|build|create)",
    r"(step by step|multi-step|complex).{0,10}(task|project|workflow)",
]

# ---------------------------------------------------------------------------
# 触发特定 Agent 的关键词（v4：6 种 agent_type）
# 优先级：列表中靠前的 agent_type 优先匹配
# ---------------------------------------------------------------------------
AGENT_TYPE_PATTERNS: dict[str, list[str]] = {
    "explore": [
        "帮我搜索",
        "帮我查",
        "查一下",
        "调研",
        "了解一下",
        "search for",
        "look up",
        "find out",
        "research",
    ],
    "planner": [
        "帮我规划",
        "制定计划",
        "怎么做",
        "步骤是什么",
        "plan",
        "planning",
        "how to",
        "outline",
    ],
    "verifier": [
        "帮我验证",
        "检查一下",
        "是否正确",
        "有没有问题",
        "verify",
        "check",
        "validate",
        "audit",
    ],
    # v4 新增：plugin_builder
    "plugin_builder": [
        "创建插件",
        "做个插件",
        "新建插件",
        "构建插件",
        "create plugin",
        "build plugin",
        "new plugin",
    ],
    # coordinator 不走关键词，走模式匹配（见 COORDINATOR_PATTERNS）
}

# ---------------------------------------------------------------------------
# 别名规范化表（来自 AgentPool Task 4.1 定义）
# chat → general / research → explore / build → general
# ---------------------------------------------------------------------------
AGENT_TYPE_ALIASES: dict[str, str] = {
    "chat": "general",
    "research": "explore",
    "build": "general",
}


class TaskRouter:
    """任务路由器（Phase 1：关键词匹配，确定性，ms 级）

    Phase 2：关键词未命中时 fallback 到 Haiku LLM 意图分类（ADR-041，未实现）。
    """

    def route(
        self,
        prompt: str,
        explicit_agent_type: str | None = None,
    ) -> RouteDecision:
        """根据任务内容和显式配置决定路由。

        优先级：
        1. 显式指定 agent_type → 直接使用（别名规范化后）
        2. 关键词匹配 Coordinator → Coordinator 模式
        3. 关键词匹配特定 Agent → 该 Agent 直接执行
        4. 默认 → General Agent 直接执行
        """
        # 1. 显式指定
        if explicit_agent_type:
            canonical = AGENT_TYPE_ALIASES.get(explicit_agent_type, explicit_agent_type)
            return RouteDecision(
                mode="direct",
                agent_type=canonical,
                reason=f"显式指定: {explicit_agent_type}",
            )

        prompt_lower = prompt.lower()

        # 2. Coordinator 模式匹配
        for pattern in COORDINATOR_PATTERNS:
            if re.search(pattern, prompt_lower):
                return RouteDecision(
                    mode="coordinator",
                    agent_type="general",
                    reason=f"关键词匹配 Coordinator: {pattern}",
                )

        # 3. 特定 Agent 关键词匹配
        for agent_type, patterns in AGENT_TYPE_PATTERNS.items():
            for pattern in patterns:
                if pattern in prompt_lower:
                    return RouteDecision(
                        mode="direct",
                        agent_type=agent_type,
                        reason=f"关键词匹配 {agent_type}: {pattern}",
                    )

        # 4. 默认：General Agent
        return RouteDecision(
            mode="direct",
            agent_type="general",
            reason="默认路由: general",
        )
