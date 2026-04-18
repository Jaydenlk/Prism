"""
executor/agents/plugin_builder_scoring.py — PluginBuilder 需求完整度打分（v4 新文件）

ADR-042（原标 ADR-038）: PluginBuilder 需求完整度打分
- 7 维度加权打分（plugin_name / purpose / tools_or_skills / input_output /
  error_handling / permission_boundary / examples）
- overall ≥ 0.8（THRESHOLD）触发生成，不再按固定轮数
- 未达到时找权重最高的缺失维度问
- max_turns=40 作为兜底上限，非正常退出条件

Observability（v4 要求）：
- structlog 事件: agent.plugin_builder.completeness_scored（含 overall + by dimension）
- Prometheus: prism_plugin_builder_completeness_histogram（打分分布直方图）
- OTel span: plugin_builder.phase.{1,2,3,4}

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

import json
import structlog

from executor.adapters.base import PrismMessage, TextBlock

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Prometheus metric（降级安全：如 metrics 未初始化则跳过）
# ---------------------------------------------------------------------------
def _get_histogram():
    try:
        from prometheus_client import Histogram
        return Histogram(
            "prism_plugin_builder_completeness_histogram",
            "PluginBuilder 需求完整度打分分布",
            buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        )
    except Exception:
        return None


_completeness_histogram = None  # lazy init


def _record_completeness(overall: float) -> None:
    """安全记录打分到 Prometheus（降级不影响主路径）"""
    global _completeness_histogram
    try:
        if _completeness_histogram is None:
            _completeness_histogram = _get_histogram()
        if _completeness_histogram is not None:
            _completeness_histogram.observe(overall)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# RequirementCompleteness — 7 维度加权打分
# ---------------------------------------------------------------------------

class RequirementCompleteness:
    """插件需求完整度维度（加权，ADR-042）

    7 个维度权重之和为 1.0（100%）：
      plugin_name:        0.15  插件名（唯一标识）
      purpose:            0.20  目的/解决什么问题
      tools_or_skills:    0.25  提供哪些工具 / skill
      input_output:       0.15  输入输出样例
      error_handling:     0.10  错误处理策略
      permission_boundary:0.10  权限边界（哪些操作需要 ask）
      examples:           0.05  用例场景
    """

    CRITERIA: dict[str, float] = {
        "plugin_name": 0.15,               # 插件名（唯一标识）
        "purpose": 0.20,                   # 目的/解决什么问题
        "tools_or_skills": 0.25,           # 提供哪些工具 / skill
        "input_output": 0.15,              # 输入输出样例
        "error_handling": 0.10,            # 错误处理策略
        "permission_boundary": 0.10,       # 权限边界（哪些操作需要 ask）
        "examples": 0.05,                  # 用例场景
    }

    THRESHOLD: float = 0.8   # overall 达到此值触发生成

    @classmethod
    async def score(cls, conversation: list[PrismMessage], adapter) -> dict:
        """用 LLM 分析对话，对每个维度打 0 / 0.5 / 1 分。

        返回 {criterion: score, ..., "overall": weighted_sum}

        adapter 须实现 complete(messages, system_prompt, max_tokens) → PrismMessage-like
        """
        criteria_list = "\n".join(
            f"- {k}: 权重 {v * 100:.0f}%" for k, v in cls.CRITERIA.items()
        )
        conv_text = "\n\n".join(
            f"{m.role}: {m.content[0].text if m.content else ''}"
            for m in conversation
        )
        analysis_prompt = (
            "分析以下对话，判断用户是否已提供足够信息构建插件。\n"
            "对每个维度给分（0=缺失 / 0.5=部分 / 1=清晰）：\n"
            f"{criteria_list}\n\n"
            f"对话：\n{conv_text}\n\n"
            "只输出 JSON，格式：\n"
            '{"plugin_name": 1.0, "purpose": 1.0, "tools_or_skills": 0.5, '
            '"input_output": 0.0, "error_handling": 0.0, '
            '"permission_boundary": 0.0, "examples": 0.0}'
        )

        response = await adapter.complete(
            messages=[PrismMessage(role="user", content=[TextBlock(text=analysis_prompt)])],
            system_prompt="你是信息完整度评估工具，只输出 JSON",
            max_tokens=300,
        )

        raw_text = response.messages[0].content[0].text if response.messages else "{}"
        scores: dict = json.loads(raw_text)

        # 确保所有维度都有值（防御性补零）
        for k in cls.CRITERIA:
            if k not in scores:
                scores[k] = 0.0

        overall = sum(scores.get(k, 0.0) * v for k, v in cls.CRITERIA.items())
        scores["overall"] = overall

        # Observability
        logger.info(
            "agent.plugin_builder.completeness_scored",
            overall=round(overall, 4),
            **{k: scores.get(k, 0.0) for k in cls.CRITERIA},
        )
        _record_completeness(overall)

        return scores


# ---------------------------------------------------------------------------
# 维度→问题映射（找最缺维度后询问用户）
# ---------------------------------------------------------------------------

_DIMENSION_QUESTIONS: dict[str, str] = {
    "plugin_name": (
        "这个插件的名称是什么？请给出一个简短且唯一的标识名（如 finance-analyzer）。"
    ),
    "purpose": (
        "这个插件的核心目的是什么？它要解决哪个具体问题？目标用户是谁？"
    ),
    "tools_or_skills": (
        "这个插件需要提供哪些工具（Tools）或技能（Skills）？"
        "请列出每个工具/技能的名称和核心功能。"
    ),
    "input_output": (
        "这个插件的典型输入是什么？期望的输出格式和内容是什么？"
        "能给一个输入→输出的具体例子吗？"
    ),
    "error_handling": (
        "当外部服务不可用或用户输入不合法时，插件应该如何处理？"
        "需要重试、降级还是直接报错？"
    ),
    "permission_boundary": (
        "插件需要哪些权限？哪些操作需要先询问用户确认（ask 权限）？"
        "有没有不允许执行的操作？"
    ),
    "examples": (
        "能描述 2-3 个典型使用场景吗？"
        "用户会如何调用这个插件，期望得到什么结果？"
    ),
}


def get_missing_dimension_question(scores: dict) -> tuple[str, str]:
    """返回 (缺失最多的维度名, 对应问题文本)

    按 weighted_gap = (1 - score) * weight 排序，取最大值。
    """
    from executor.agents.plugin_builder_scoring import RequirementCompleteness as RC
    weighted_gap = {
        k: (1.0 - scores.get(k, 0.0)) * v
        for k, v in RC.CRITERIA.items()
    }
    missing_dim = max(weighted_gap, key=weighted_gap.get)
    question = _DIMENSION_QUESTIONS.get(missing_dim, f"请补充 {missing_dim} 相关信息。")
    return missing_dim, question


# ---------------------------------------------------------------------------
# PluginBuilderAgent — 完整度打分驱动的多轮对话 Agent（骨架）
# ---------------------------------------------------------------------------

class PluginBuilderAgent:
    """完整度打分驱动的 PluginBuilder 对话流程控制器。

    注意：这是高层业务骨架，实际 SSE 推送 / 用户回复等待依赖 DOC-07 Task 7.3
    的 callback 机制（目前为 stub）。此类与 Harness TAOR 循环解耦：
    PluginBuilderGate Middleware 是主路径门控，此类供独立单元测试验证打分逻辑。
    """

    MAX_TURNS: int = 40  # 兜底上限，非正常退出条件（ADR-042）

    def __init__(self, adapter) -> None:
        self._adapter = adapter
        self._turn_count: int = 0
        self._conversation: list[PrismMessage] = []

    async def run(self, user_request: str):
        """主循环：打分 → 继续问 / 进入阶段 2。

        循环：
          1. 用户说话
          2. 打分（RequirementCompleteness.score）
          3. 若 overall >= 0.8 → 进入阶段 2（设计展示）
          4. 若 < 0.8 → 问权重最高的缺失维度 + 回到 1
        """
        self._conversation = [
            PrismMessage(role="user", content=[TextBlock(text=user_request)])
        ]

        while self._turn_count < self.MAX_TURNS:
            scores = await RequirementCompleteness.score(self._conversation, self._adapter)

            if scores["overall"] >= RequirementCompleteness.THRESHOLD:
                # 进入设计方案展示阶段
                return await self._present_design(self._conversation)

            # 找加权缺失最多的维度
            weighted_gap = {
                k: (1.0 - scores.get(k, 0.0)) * v
                for k, v in RequirementCompleteness.CRITERIA.items()
            }
            missing_dim = max(weighted_gap, key=weighted_gap.get)
            question = _DIMENSION_QUESTIONS.get(
                missing_dim, f"请补充 {missing_dim} 相关信息。"
            )

            self._conversation.append(
                PrismMessage(role="assistant", content=[TextBlock(text=question)])
            )

            # 通过 SSE 推给用户，阻塞等待回答（DOC-07 Task 7.3 实现）
            user_reply = await self._wait_for_user_reply()
            self._conversation.append(
                PrismMessage(role="user", content=[TextBlock(text=user_reply)])
            )
            self._turn_count += 1

        # 达到 max_turns，强制进入设计方案展示并在 prompt 中说明
        return await self._present_design(self._conversation, forced=True)

    async def _present_design(
        self,
        conversation: list[PrismMessage],
        forced: bool = False,
    ) -> dict:
        """阶段 2：设计方案展示（stub，DOC-05 Task 5.3 + DOC-07 Task 7.3 补全）。

        返回设计摘要 dict，供上层展示给用户。
        """
        # TODO: 与 Harness SSE 集成（DOC-07 Task 7.3），目前返回 stub
        note = "（已达到 max_turns，基于现有信息展示设计）" if forced else ""
        return {
            "phase": 2,
            "forced": forced,
            "note": note,
            "turns_used": self._turn_count,
            "conversation_length": len(conversation),
            # 实际设计方案由 Harness TAOR 循环 + PromptAssembler 生成
        }

    async def _wait_for_user_reply(self) -> str:
        """等待用户通过 SSE 回复（stub，DOC-07 Task 7.3 实现 Redis BLPOP）。

        TODO: 接入 PermissionAskProtocol / callback 机制（DOC-07 Task 7.3）
        """
        # stub：在实际集成前抛出 NotImplementedError，避免无限 mock 循环
        raise NotImplementedError(
            "_wait_for_user_reply 需要 DOC-07 Task 7.3 的 callback/BLPOP 实现"
        )
