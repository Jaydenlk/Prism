"""
4 级渐进式 Compaction Pipeline（v4 Task 3.5）

对标 CC 的 multi-tier compaction，按回合组（turn group）原子裁剪：
- Tier 1 (micro-compact, ≥60% 阈值): 裁最老 1 个回合组，保留 is_skill_context
- Tier 2 (auto-compact, ≥85% 阈值): LLM 摘要替换最老 50% 回合组，skill_context 全保留
- Tier 3: 在 SessionEnd Hook 触发（Task 3.4 HarnessRuntime.on_session_end，本模块不实现）
- Tier 4 (reactive): API 报 context_too_long 时紧急裁到最近 3 组 + skill_context

核心 ADR：
- ADR-031（Compaction 按回合组原子裁剪）：绝不按 index 单独裁，整组保留或整组删除
- ADR-032（is_skill_context 优先保留）：Tier 1/2/4 均保留 is_skill_context=True 消息

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import structlog

from executor.adapters.base import PrismMessage, TextBlock
from executor.engine.context_budget import ContextBudgetManager

if TYPE_CHECKING:
    from executor.callbacks.backend_callback import BackendCallback
    from executor.adapters.base import ModelAdapter

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Prometheus metric（从 metrics.py 导入，降级安全）
# ---------------------------------------------------------------------------

def _inc_compaction_metric(tier: str) -> None:
    """安全地递增 prism_compaction_total{tier} Counter，失败时 log 降级不崩溃。"""
    try:
        from executor.observability.metrics import prism_harness_compaction_total
        prism_harness_compaction_total.labels(tier=tier).inc()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# helper：提取消息首个文本块
# ---------------------------------------------------------------------------

def _extract_text(msg: PrismMessage) -> str:
    """从 PrismMessage content 提取首个 .text 字段的文本，找不到返回空串。"""
    for block in getattr(msg, "content", []):
        if hasattr(block, "text"):
            return block.text
    return ""


# ---------------------------------------------------------------------------
# CompactionPipeline
# ---------------------------------------------------------------------------


class CompactionPipeline:
    """v4：按回合组原子裁剪的 4 级 Compaction Pipeline（ADR-031 / ADR-032）

    阈值配置（占 available context 的百分比）：
      TIER1_THRESHOLD = 0.60  （CC 实测阈值）
      TIER2_THRESHOLD = 0.85

    Tier 3 在 SessionEnd Hook 触发（Task 3.4 HarnessRuntime.on_session_end，不在此处）。
    Tier 4 由 Adapter 捕获 context_too_long 后调用 reactive_truncate()。
    """

    TIER1_THRESHOLD: float = 0.60
    TIER2_THRESHOLD: float = 0.85

    def __init__(
        self,
        budget: ContextBudgetManager,
        adapter: "ModelAdapter | None" = None,
        callback: "BackendCallback | None" = None,
    ) -> None:
        """
        adapter：Tier 2 LLM 摘要需要。adapter=None 时 Tier 2 降级为 Tier 1 行为。
        callback：compaction_in_progress 上报。callback=None 时跳过回调。
        """
        self._budget = budget
        self._adapter = adapter
        self._callback = callback

    # ------------------------------------------------------------------ #
    # 公共入口                                                              #
    # ------------------------------------------------------------------ #

    async def maybe_compact(
        self,
        messages: list[PrismMessage],
        system_prompt: str,
    ) -> list[PrismMessage]:
        """根据当前 token 占用比决定触发哪一级 Compaction。

        路由规则：
          usage_ratio >= TIER2_THRESHOLD → Tier 2 (auto-compact, LLM 摘要)
          usage_ratio >= TIER1_THRESHOLD → Tier 1 (micro-compact, 裁最老 1 组)
          否则 → 原样返回
        """
        available = self._budget._max_context_tokens - self._budget._reserve_for_response
        if available <= 0:
            return messages

        current = self._budget.estimate_messages_tokens(messages, system_prompt)
        usage_ratio = current / available

        if usage_ratio >= self.TIER2_THRESHOLD:
            return await self._tier2_auto_compact(messages, system_prompt, before_tokens=current)
        elif usage_ratio >= self.TIER1_THRESHOLD:
            return self._tier1_micro_compact(messages, before_tokens=current)
        return messages

    async def check_and_compact(
        self,
        messages: list[PrismMessage],
        system_prompt: str,
    ) -> list[PrismMessage]:
        """与 maybe_compact 同义，作为 QueryEngine 集成点的别名（PRD §3 建议命名）。"""
        return await self.maybe_compact(messages, system_prompt)

    # ------------------------------------------------------------------ #
    # Tier 1 — micro-compact（裁最老 1 个回合组）                           #
    # ------------------------------------------------------------------ #

    def _tier1_micro_compact(
        self,
        messages: list[PrismMessage],
        before_tokens: int | None = None,
    ) -> list[PrismMessage]:
        """Tier 1：原子裁掉最老 1 个回合组（ADR-031），保留 is_skill_context（ADR-032）。

        - groups <= 2 时直接返回原样（裁不了）
        - 保留第 2 组到最后所有组的全部消息
        - 保留所有 is_skill_context=True 消息（即使它们在被裁的第 1 组里）
        - fire-and-forget callback.compaction_in_progress(tier=1)
        """
        groups = self._budget.identify_turn_groups(messages)
        if len(groups) <= 2:
            return messages

        # 保留 groups[1:] 对应的 index 集合
        to_keep: set[int] = set()
        for start, end in groups[1:]:
            to_keep.update(range(start, end + 1))

        result = [
            msg
            for i, msg in enumerate(messages)
            if i in to_keep or getattr(msg, "is_skill_context", False)
        ]

        # 计算 after_tokens（如未传 before_tokens 则内部计算）
        if before_tokens is None:
            before_tokens = self._budget.estimate_messages_tokens(messages, "")
        after_tokens = self._budget.estimate_messages_tokens(result, "")

        # fire-and-forget callback（不 await，避免阻塞）
        if self._callback is not None:
            try:
                asyncio.create_task(
                    self._callback.compaction_in_progress(
                        tier=1,
                        before_tokens=before_tokens,
                        after_tokens=after_tokens,
                    )
                )
            except RuntimeError:
                # 无事件循环时（单测场景）静默跳过
                pass

        _inc_compaction_metric("1")
        logger.info(
            "harness.compaction.tier1",
            before_tokens=before_tokens,
            after_tokens=after_tokens,
            groups_before=len(groups),
            msgs_before=len(messages),
            msgs_after=len(result),
        )
        return result

    # ------------------------------------------------------------------ #
    # Tier 2 — auto-compact（LLM 摘要替换最老 50% 回合组）                  #
    # ------------------------------------------------------------------ #

    async def _tier2_auto_compact(
        self,
        messages: list[PrismMessage],
        system_prompt: str,
        before_tokens: int | None = None,
    ) -> list[PrismMessage]:
        """Tier 2：LLM 摘要替换最老 50% 回合组（ADR-031 / ADR-032）。

        - groups <= 3 时原样返回（没有足够旧组可摘要）
        - is_skill_context 消息不参与摘要，但全部保留在 result 里
        - adapter=None 时降级为 Tier 1 行为，并 log warning
        - 摘要 max_tokens=500，prompt 与 PRD Part B 一致
        """
        groups = self._budget.identify_turn_groups(messages)
        if len(groups) <= 3:
            return messages

        # adapter=None 降级为 Tier 1
        if self._adapter is None:
            logger.warning(
                "harness.compaction.tier2_no_adapter",
                msg="tier2 requires adapter, falling back to tier1",
            )
            if before_tokens is None:
                before_tokens = self._budget.estimate_messages_tokens(messages, system_prompt)
            return self._tier1_micro_compact(messages, before_tokens=before_tokens)

        if before_tokens is None:
            before_tokens = self._budget.estimate_messages_tokens(messages, system_prompt)

        # 分割：最老 50% 组 vs 最近 50% 组
        split_point = len(groups) // 2
        old_groups = groups[:split_point]
        recent_groups = groups[split_point:]

        old_indices: set[int] = set()
        for start, end in old_groups:
            old_indices.update(range(start, end + 1))

        # 只把非 skill_context 的老消息送给 LLM 做摘要
        old_messages = [
            msg
            for i, msg in enumerate(messages)
            if i in old_indices and not getattr(msg, "is_skill_context", False)
        ]

        # 构造摘要 prompt（与 PRD Part B 原文一致）
        summary_prompt = (
            "请将以下对话历史凝练为 200 字内的摘要，保留关键决策、"
            "工具调用结果、未完成事项：\n\n"
        )
        for msg in old_messages:
            summary_prompt += f"{msg.role}: {_extract_text(msg)}\n\n"

        summary_response = await self._adapter.complete(
            messages=[PrismMessage(role="user", content=[TextBlock(text=summary_prompt)])],
            system_prompt="你是对话历史压缩工具。只输出摘要，不说其他。",
            max_tokens=500,
        )
        summary_text = summary_response.messages[0].content[0].text

        # 构造 result：摘要消息 + 最近回合组 + 所有 skill_context
        summary_msg = PrismMessage(
            role="user",
            content=[TextBlock(text=f"[历史对话摘要]\n{summary_text}")],
            is_skill_context=False,
        )

        recent_indices: set[int] = set()
        for start, end in recent_groups:
            recent_indices.update(range(start, end + 1))

        result: list[PrismMessage] = [summary_msg]
        for i, msg in enumerate(messages):
            if i in recent_indices:
                result.append(msg)
            elif getattr(msg, "is_skill_context", False):
                result.append(msg)

        after_tokens = self._budget.estimate_messages_tokens(result, system_prompt)

        if self._callback is not None:
            await self._callback.compaction_in_progress(
                tier=2,
                before_tokens=before_tokens,
                after_tokens=after_tokens,
            )

        _inc_compaction_metric("2")
        logger.info(
            "harness.compaction.tier2",
            before_tokens=before_tokens,
            after_tokens=after_tokens,
            groups_before=len(groups),
            split_point=split_point,
            msgs_after=len(result),
        )
        return result

    # ------------------------------------------------------------------ #
    # Tier 4 — reactive_truncate（紧急截断）                                #
    # ------------------------------------------------------------------ #

    def reactive_truncate(
        self,
        messages: list[PrismMessage],
    ) -> list[PrismMessage]:
        """Tier 4：紧急截断，保留最近 3 个回合组 + 所有 is_skill_context 消息。

        开头插入 hint message（role=user, is_skill_context=False）告知历史已压缩。
        ADR-032：is_skill_context=True 消息全部保留（即使 groups < 3 也保留）。
        """
        groups = self._budget.identify_turn_groups(messages)
        # 保留最近 3 组（groups < 3 时保留全部）
        keep_groups = groups[-3:] if len(groups) >= 3 else groups

        keep_indices: set[int] = set()
        for start, end in keep_groups:
            keep_indices.update(range(start, end + 1))

        retained = [
            msg
            for i, msg in enumerate(messages)
            if i in keep_indices or getattr(msg, "is_skill_context", False)
        ]

        # 开头插入告警 hint（不是 skill_context，可参与后续裁剪）
        hint = PrismMessage(
            role="user",
            content=[TextBlock(text="[上下文已紧急压缩，部分历史信息丢失]")],
            is_skill_context=False,
        )

        _inc_compaction_metric("4")
        logger.warning(
            "harness.compaction.tier4_reactive",
            groups_before=len(groups),
            msgs_before=len(messages),
            msgs_after=len(retained) + 1,
        )
        return [hint] + retained

    # 别名：PRD 验证脚本使用 _tier4_reactive 名字
    _tier4_reactive = reactive_truncate
