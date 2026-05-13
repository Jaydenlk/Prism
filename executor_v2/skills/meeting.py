from __future__ import annotations

from executor_v2.skills.base import Skill

MEETING_SKILL = Skill(
    name="会议",
    description="会议纪要、摘要、行动项提取",
    system_prompt_addition=(
        "会议纪要任务。输出格式：\n"
        "## 会议纪要\n"
        "- 日期：\n"
        "- 参会人：\n"
        "- 主题：\n\n"
        "### 讨论要点\n"
        "1. ...\n\n"
        "### 决议事项\n"
        "1. ...\n\n"
        "### 行动项\n"
        "| 负责人 | 事项 | 截止日期 |\n"
    ),
    verify=False,
)
