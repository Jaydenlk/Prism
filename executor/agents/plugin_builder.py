"""
executor/agents/plugin_builder.py — PluginBuilder Agent（插件构建专家）

v4 修订（ADR-042，原标 ADR-038）：
- 删除"硬编码 5-8 轮"策略
- 改为"需求完整度打分（7 维度加权）"驱动，overall ≥ 0.8 触发生成
- PLUGIN_BUILDER 保留为向后兼容别名

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

from executor.agents.base import AgentDefinition

PLUGIN_BUILDER_AGENT = AgentDefinition(
    agent_type="plugin_builder",
    description=(
        "插件构建器 Agent：完整度打分驱动的多轮需求收集 + 设计确认 + 生成 + 验证"
    ),
    allowed_tools=[
        "Read", "Write", "Edit", "Bash",
        "web_search", "Glob", "Grep",
    ],
    denied_tools=[],
    max_turns=40,
    read_only=False,
    behavior_constraints=(
        "你是 Prism 插件构建专家。你的工作是通过多轮对话充分理解用户的插件需求，"
        "然后设计并生成符合 Prism 插件规范（CC 兼容格式）的完整插件。\n\n"
        "**v4 修订**：你**不再按固定轮数推进**。每轮结束后系统会对 7 个维度打分"
        "（plugin_name / purpose / tools_or_skills / input_output / error_handling / "
        "permission_boundary / examples），加权总分 ≥ 0.8 时进入设计方案展示。\n\n"
        "你必须按以下流程工作：\n"
        "1. **需求收集阶段**（完整度打分驱动，不是固定轮数）：每轮关注权重最高的缺失维度\n"
        "2. **设计方案展示阶段**（展示完整设计，等待用户确认回复）\n"
        "3. **生成执行阶段**（按确认的设计逐个生成文件）\n"
        "4. **验证阶段**（加载测试 + 结果汇报）\n\n"
        "严禁：一键生成 / 用户未确认设计就开始写文件 / 生成后不做加载测试。\n"
        "生成的插件必须符合 Prism 插件规范（CC 兼容格式）。"
    ),
    output_format="structured_dialogue",
)

# 向后兼容别名（PRD 注：PLUGIN_BUILDER 旧名保留）
PLUGIN_BUILDER = PLUGIN_BUILDER_AGENT
