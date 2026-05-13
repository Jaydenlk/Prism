from __future__ import annotations

from executor_v2.skills.base import Skill

CHAT_SKILL = Skill(
    name="对话",
    description="日常对话、问答、闲聊",
    system_prompt_addition="自然对话，简洁回答。记住用户偏好。",
    verify=False,
)
