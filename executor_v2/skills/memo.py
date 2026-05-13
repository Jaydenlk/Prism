from __future__ import annotations

from executor_v2.skills.base import Skill

MEMO_SKILL = Skill(
    name="备忘",
    description="记录、保存、管理备忘信息",
    system_prompt_addition=(
        "用户要求记录信息。确认已记录，简要复述内容。\n"
        "格式：标题 + 内容 + 标签。\n"
        "如果用户说'记一下'、'帮我记住'，提取关键信息存储。"
    ),
    verify=False,
)
