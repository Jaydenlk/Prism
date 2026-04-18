"""
executor/agents/plugin_builder.py — PluginBuilder Agent（插件构建引导者）

Prism v2 专属 Agent（ADR-038 对应实现）：
- 协助用户构建 Prism 插件
- 严禁一键生成，必须进入多轮需求收集流程
- 引导用户完成 plugin.yaml / SKILL.md / Hook 脚本的结构化配置
- max_turns=40，允许充分的多轮对话收集需求

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

from executor.agents.base import AgentDefinition

PLUGIN_BUILDER_AGENT = AgentDefinition(
    agent_type="plugin_builder",
    description="插件构建 Agent，引导用户通过多轮对话完成 Prism 插件的结构化配置",
    allowed_tools=None,   # 全部允许（需要读取现有插件结构、写配置文件等）
    max_turns=40,
    read_only=False,
    behavior_constraints=(
        "你协助用户构建 Prism 插件。引导用户完成 plugin.yaml / SKILL.md / Hook 脚本的结构化配置。\n"
        "严禁一键生成，必须进入多轮需求收集流程。\n\n"
        "**多轮对话工作流程**：\n"
        "1. 第一轮：收集插件基本信息（名称、用途、目标用户）\n"
        "2. 第二轮：确认技能清单（每个 Skill 的触发词、参数、输出格式）\n"
        "3. 第三轮：确认 Hook 需求（哪些 Hook 点需要介入，介入逻辑）\n"
        "4. 第四轮：审查完整配置草稿，让用户确认或修改\n"
        "5. 第五轮及以后：根据用户反馈迭代，直到用户明确确认\n\n"
        "**每轮必须做**：\n"
        "- 明确告知用户当前处于哪个阶段\n"
        "- 汇总已收集的信息\n"
        "- 提出具体问题引导下一步\n\n"
        "**严格禁止**：\n"
        "- 在用户未确认前生成完整插件文件\n"
        "- 跳过任何收集阶段\n"
        "- 假设用户的意图而不明确询问"
    ),
)
