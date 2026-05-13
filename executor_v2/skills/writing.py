from __future__ import annotations

from executor_v2.skills.base import Skill

WRITING_SKILL = Skill(
    name="写作",
    description="邮件、报告、文案、周报",
    system_prompt_addition=(
        "写作任务。流程：\n"
        "1. 确认写作类型和受众\n"
        "2. 生成初稿\n"
        "3. 自审查（语法、逻辑、语气）\n"
        "4. 输出定稿\n"
        "保持专业、简洁、有条理。"
    ),
    verify=True,
)
