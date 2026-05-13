from __future__ import annotations

from executor_v2.skills.base import Skill

RESEARCH_SKILL = Skill(
    name="调研",
    description="搜索、调查、信息收集、竞品分析",
    system_prompt_addition=(
        "调研任务。要求：\n"
        "1. 多源搜索，交叉验证\n"
        "2. 结构化输出（表格对比）\n"
        "3. 标注来源和置信度\n"
        "4. 区分事实和观点\n"
        "输出格式：概述 → 关键发现(表格) → 分析 → 建议"
    ),
    verify=True,
)
