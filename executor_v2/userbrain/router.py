from __future__ import annotations

import re
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)

INTENT_CATEGORIES = [
    "memo", "reminder", "research", "brainstorm",
    "writing", "analysis", "meeting", "chat",
]


@dataclass
class Intent:
    category: str
    confidence: float


_PATTERNS: dict[str, list[str]] = {
    "memo": ["记一下", "帮我记", "记住", "备忘", "note", "remember this", "save this", "记录"],
    "reminder": ["提醒", "闹钟", "日程", "remind", "alarm", "schedule", "点.*会", "deadline"],
    "research": ["调研", "研究", "搜索", "查找", "查一下", "了解", "research", "investigate", "find out", "look up", "search for", "what are", "compare"],
    "brainstorm": ["讨论", "研讨", "头脑风暴", "brainstorm", "discuss", "debate", "think about", "explore ideas", "分析.*方向", "产品方向"],
    "writing": ["写", "撰写", "起草", "邮件", "报告", "文案", "周报", "write", "draft", "email", "report", "compose"],
    "analysis": ["分析", "数据", "统计", "趋势", "excel", "csv", "analyze", "data", "chart", "graph", "计算"],
    "meeting": ["会议", "纪要", "会议记录", "行动项", "meeting", "minutes", "action items", "attendees"],
}

_COMPILED: dict[str, re.Pattern[str]] = {
    cat: re.compile("|".join(re.escape(p) if ".*" not in p else p for p in patterns), re.IGNORECASE)
    for cat, patterns in _PATTERNS.items()
}


class IntentRouter:
    def __init__(self) -> None:
        pass

    async def classify(self, message: str, user_memories: list[dict] | None = None) -> Intent:
        if len(message.strip()) < 3:
            return Intent(category="chat", confidence=1.0)

        scores: dict[str, int] = {}
        for cat, pattern in _COMPILED.items():
            matches = pattern.findall(message)
            if matches:
                scores[cat] = len(matches)

        if not scores:
            return Intent(category="chat", confidence=0.7)

        best = max(scores, key=scores.get)  # type: ignore[arg-type]
        logger.info("router.classified", category=best, scores=scores)
        return Intent(category=best, confidence=0.9)
