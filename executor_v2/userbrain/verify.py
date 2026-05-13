from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class VerifyResult:
    confidence: Confidence
    completeness_score: float  # 0.0 - 1.0
    consistency_score: float   # 0.0 - 1.0
    uncertain_claims: list[str]
    notes: str


_SKIP_KEYWORDS = frozenset({"hi", "hello", "thanks", "谢谢", "好的", "ok", "bye"})

_VERIFY_KEYWORDS = frozenset({
    "调研", "研究", "分析", "报告", "查找", "搜索",
    "research", "analyze", "investigate", "report", "find",
    "compare", "对比", "评估", "evaluate",
})


def should_verify(prompt: str) -> bool:
    """判断是否需要验证。简单对话跳过，调研/分析类强制验证。"""
    prompt_lower = prompt.lower().strip()
    if len(prompt_lower) < 10:
        return False
    if any(kw in prompt_lower for kw in _SKIP_KEYWORDS):
        return False
    return any(kw in prompt_lower for kw in _VERIFY_KEYWORDS)


class VerifyAgent:
    def __init__(self) -> None:
        self._api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self._base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        self._model = os.environ.get("VERIFY_MODEL", "auto-v2")
        self._enabled = bool(self._api_key)

    async def verify(
        self,
        task: str,
        result: str,
        user_memories: list[dict] | None = None,
    ) -> VerifyResult:
        """运行验证管道"""
        if not self._enabled:
            return VerifyResult(
                confidence=Confidence.HIGH,
                completeness_score=1.0,
                consistency_score=1.0,
                uncertain_claims=[],
                notes="Verification skipped (no API key)",
            )

        completeness = await self._check_completeness(task, result)
        consistency = await self._check_consistency(result, user_memories or [])
        uncertain = await self._extract_uncertain_claims(result)

        confidence = self._compute_confidence(completeness, consistency, len(uncertain))

        return VerifyResult(
            confidence=confidence,
            completeness_score=completeness,
            consistency_score=consistency,
            uncertain_claims=uncertain,
            notes="",
        )

    async def _check_completeness(self, task: str, result: str) -> float:
        """评估结果是否完整回答了问题"""
        prompt = (
            f"Rate from 0 to 10 how completely this response answers the task.\n"
            f"Task: {task[:500]}\n"
            f"Response: {result[:1000]}\n"
            f"Reply with ONLY a number 0-10."
        )
        score_text = await self._llm_call(prompt)
        try:
            score = float(score_text.strip()) / 10.0
            return max(0.0, min(1.0, score))
        except (ValueError, TypeError):
            return 0.5

    async def _check_consistency(self, result: str, memories: list[dict]) -> float:
        """检查结果是否与已知事实矛盾"""
        if not memories:
            return 1.0

        memory_text = "\n".join(
            m.get("memory", m.get("text", "")) for m in memories[:10]
        )
        prompt = (
            f"Do any statements in the Response contradict the Known Facts?\n"
            f"Known Facts:\n{memory_text[:500]}\n\n"
            f"Response:\n{result[:1000]}\n\n"
            f"Reply with ONLY 'yes' or 'no'."
        )
        answer = await self._llm_call(prompt)
        return 0.3 if "yes" in answer.lower() else 1.0

    async def _extract_uncertain_claims(self, result: str) -> list[str]:
        """提取结果中不确定的事实性声明"""
        prompt = (
            f"List any factual claims in this text that might be wrong or unverifiable. "
            f"Return each claim on a new line. If all claims seem reliable, reply 'NONE'.\n\n"
            f"Text: {result[:1500]}"
        )
        answer = await self._llm_call(prompt)
        if "none" in answer.lower().strip():
            return []
        return [line.strip() for line in answer.strip().split("\n") if line.strip()][:5]

    def _compute_confidence(
        self, completeness: float, consistency: float, uncertain_count: int
    ) -> Confidence:
        base = (completeness * 0.4 + consistency * 0.4 + (1.0 if uncertain_count == 0 else 0.2) * 0.2)
        if base >= 0.8:
            return Confidence.HIGH
        if base >= 0.5:
            return Confidence.MEDIUM
        return Confidence.LOW

    async def _llm_call(self, prompt: str) -> str:
        try:
            from executor_v2.userbrain import normalize_openai_base_url
            url = f"{normalize_openai_base_url(self._base_url)}/chat/completions"

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    url,
                    headers={
                        "authorization": f"Bearer {self._api_key}",
                        "content-type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "max_tokens": 200,
                        "temperature": 0.1,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
                return ""
        except Exception as exc:
            logger.warning("verify.llm_call_failed", error=str(exc))
            return ""
