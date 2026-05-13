from __future__ import annotations

from executor_v2.skills.base import Skill

BRAINSTORM_SKILL = Skill(
    name="研讨",
    description="头脑风暴、讨论、分析问题",
    system_prompt_addition=(
        "研讨模式。不要顺从，要挑战用户假设。\n"
        "使用框架：MECE / SWOT / 5W1H / 正反辩论。\n"
        "每个观点给出支持论据和反驳。\n"
        "最终总结各方立场，不急于给结论。"
    ),
    verify=False,
)
