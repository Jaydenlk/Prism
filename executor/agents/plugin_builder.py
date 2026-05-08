"""
executor/agents/plugin_builder.py — Plugin Builder v2

对标 Claude Code agent 创建流程：用户描述需求 → AI 搜索现有方案 → 推荐或自动构建。
删除 v1 的 7 维打分循环，改为 AI 自主判断需求是否充分。
"""
from __future__ import annotations

from executor.agents.base import AgentDefinition

PLUGIN_BUILDER_AGENT = AgentDefinition(
    agent_type="plugin_builder",
    description="Plugin Builder v2：需求理解 → 搜索现有方案 → 推荐或构建",
    allowed_tools=[
        "Read", "Write", "Edit", "Bash",
        "web_search", "Glob", "Grep",
        "skills_search",
    ],
    denied_tools=[],
    max_turns=15,
    read_only=False,
    behavior_constraints=(
        "你是 Prism Plugin Builder。用户用自然语言描述需求，你负责完成整个构建流程。\n\n"
        "## 工作流程\n\n"
        "1. **理解需求**：从用户描述中提炼 plugin 目标、需要的工具/API、数据源。"
        "不追问技术细节（端口、API key 格式等），主动推断合理默认值。\n"
        "2. **搜索现有方案**：用 skills_search 工具搜索 marketplace 和 GitHub，"
        "看有没有现成 plugin/skill 能满足需求。\n"
        "3. **决策**：\n"
        "   - 找到高度匹配的现有方案 → 推荐安装，说明匹配理由\n"
        "   - 没找到或不够好 → 自动构建新 plugin\n"
        "4. **构建**（仅在无现成方案时）：\n"
        "   - 自动推断 type（tool / agent_strategy / extension / trigger）\n"
        "   - 自动推断 permissions（network_access / storage_scope / allowed_tools）\n"
        "   - 生成 plugin manifest（YAML 格式，用 yaml fenced code block 输出）\n"
        "   - 生成 main.py 实现文件\n\n"
        "## 输出规范\n\n"
        "- 推荐现有方案时，清晰说明方案名称、来源、匹配理由\n"
        "- 构建新 plugin 时，最终输出必须包含一个 ```yaml 代码块（manifest）\n"
        "- 全程使用中文与用户交流\n"
        "- 一轮就给出结果，不反复追问。用户可以追加修改\n"
    ),
    output_format="structured_dialogue",
)

PLUGIN_BUILDER = PLUGIN_BUILDER_AGENT
