"""Skills 搜索评分引擎 — 拆词 + 模糊匹配 + 加权计分"""
from __future__ import annotations

from rapidfuzz import fuzz

WEIGHT_NAME = 5
WEIGHT_TAGS = 3
WEIGHT_DESC = 1
FUZZY_THRESHOLD = 60


def score_match(query: str, name: str, description: str, tags: list[str]) -> float:
    if not query or not query.strip():
        return 100.0

    tokens = query.lower().split()
    if not tokens:
        return 100.0

    name_lower = name.lower()
    desc_lower = description.lower()
    tags_lower = [t.lower() for t in tags]

    total = 0.0
    max_possible = len(tokens) * (WEIGHT_NAME + WEIGHT_TAGS + WEIGHT_DESC) * 100

    for token in tokens:
        name_score = fuzz.partial_ratio(token, name_lower)
        best_tag_score = max((fuzz.partial_ratio(token, t) for t in tags_lower), default=0)
        desc_score = fuzz.partial_ratio(token, desc_lower)

        if name_score >= FUZZY_THRESHOLD:
            total += name_score * WEIGHT_NAME
        if best_tag_score >= FUZZY_THRESHOLD:
            total += best_tag_score * WEIGHT_TAGS
        if desc_score >= FUZZY_THRESHOLD:
            total += desc_score * WEIGHT_DESC

    return round((total / max_possible) * 100, 1) if max_possible > 0 else 0.0
