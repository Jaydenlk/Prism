"""
executor/harness/defaults.py — Harness 配置代码默认常量(v4)

这些常量是 HarnessConfigLoader 的第一源(代码默认)。
第二源为 harness_config.yaml(部署时覆盖)。

进程边界：本模块仅含 stdlib 数据,禁止 import backend.app.*
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 1. Permission 策略: tool_name → "allow" | "deny" | "ask"
#    共 9 项(ADR-033)
# ---------------------------------------------------------------------------
DEFAULT_PERMISSION_POLICIES: dict[str, str] = {
    "bash": "ask",
    "Bash": "ask",
    "Write": "allow",
    "Edit": "allow",
    "Read": "allow",
    "Grep": "allow",
    "WebFetch": "ask",
    "WebSearch": "allow",
    "skill_install": "ask",
}

# ---------------------------------------------------------------------------
# 2. Middleware 启停 + 参数: mw_name → {enabled, params}
#    共 4 项(ADR-033)
# ---------------------------------------------------------------------------
DEFAULT_MIDDLEWARE_CONFIG: dict[str, dict] = {
    "loop_detection": {
        "enabled": True,
        "params": {"window_size": 5, "max_identical": 3},
    },
    "rate_limit": {
        "enabled": True,
        "params": {"max_tool_calls_per_minute": 30},
    },
    "feedback_capture": {
        "enabled": True,
        "params": {},
    },
    "observability": {
        "enabled": True,
        "params": {},
    },
}

# ---------------------------------------------------------------------------
# 3. Agent 行为约束: agent_type → [constraint_text]
#    共 6 种 agent type(ADR-033)
# ---------------------------------------------------------------------------
DEFAULT_AGENT_CONSTRAINTS: dict[str, list[str]] = {
    "chat": [],
    "explore": ["你是只读探索者。绝对不能创建、修改、删除任何文件或数据。"],
    "planner": ["你是规划者。只输出 step-by-step 计划，不执行任何操作。"],
    "verifier": ["你是验证者。你的工作是尝试打破系统，发现问题。"],
    "plugin_builder": ["严禁一键生成。必须进入多轮需求收集流程。"],
    "coordinator": [],
}
