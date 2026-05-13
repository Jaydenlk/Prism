from __future__ import annotations

from executor_v2.skills.base import Skill

ANALYSIS_SKILL = Skill(
    name="分析",
    description="数据分析、表格处理、趋势分析",
    system_prompt_addition=(
        "数据分析任务。\n"
        "1. 理解数据结构和分析目标\n"
        "2. 处理数据（清洗、计算、可视化描述）\n"
        "3. 用数据说话，给出洞察\n"
        "4. 提出可执行建议\n"
        "如有数字，标注来源。"
    ),
    verify=True,
)
