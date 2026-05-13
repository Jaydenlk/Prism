from __future__ import annotations

from executor_v2.skills.base import Skill

REMINDER_SKILL = Skill(
    name="提醒",
    description="设置提醒、日程、定时通知",
    system_prompt_addition=(
        "用户设置提醒。提取：时间 + 事项 + 重复规则。\n"
        "确认提醒内容和时间。格式化输出。\n"
        "如果时间模糊（如'明天'），确认具体时间。"
    ),
    verify=False,
)
