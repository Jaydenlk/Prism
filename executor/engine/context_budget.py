"""
上下文预算管理（Tier 0 — 基础能力，v4 升级为精确估算 + 回合组原子裁剪）

职责:
1. **精确估算**当前 messages + system prompt 的 token 数（v4：依赖注入 TokenEstimator，不再粗估）
2. 判断是否需要触发压缩（信号源，供 Harness Compaction Pipeline 使用）
3. 工具结果超过阈值时截断并生成摘要
4. **回合组（turn group）原子裁剪骨架**（v4：绝不破坏 tool_use ↔ tool_result 配对）

CC 参考：CC 的 compact / transcript / function result clearing 机制

注意：4 级渐进式 Compaction Pipeline 的完整实现在 DOC-03 中。
本模块只负责 token 估算、工具结果截断、回合组边界识别，不负责 LLM 生成摘要。

ADR-015: TokenEstimator Protocol — 依赖注入精确 tokenizer
ADR-016: Compaction 按回合组（turn group）为原子单元裁剪，绝不破坏 tool_use↔tool_result 配对
ADR-017: is_skill_context=True 的消息在 compress_history 时优先保留

进程边界：本模块只 import executor.adapters.base，禁止 import backend.app.*
"""

from __future__ import annotations

from typing import Protocol

from executor.adapters.base import PrismMessage


# ============================================================
# TokenEstimator Protocol（v4 新增，依赖注入，ADR-015）
# ============================================================


class TokenEstimator(Protocol):
    """Token 估算策略接口（v4 新增，依赖注入）

    实现方由 Driver 层提供（AnthropicDriver / OpenAIDriver 各自实现精确 tokenizer）。
    ContextBudgetManager 通过此接口与具体 tokenizer 解耦。

    ADR-015：不接受字符计数粗估，必须使用精确 tokenizer（tiktoken 或 Anthropic SDK）。
    """

    def estimate(self, text: str) -> int:
        """精确估算单段文本的 token 数"""
        ...

    def estimate_messages(self, messages: list[PrismMessage], system_prompt: str) -> int:
        """精确估算完整请求（messages + system_prompt）的 token 数"""
        ...


# ============================================================
# ContextBudgetManager（Tier 0 基础能力）
# ============================================================


class ContextBudgetManager:
    """上下文预算管理器（Tier 0）

    Tier 0 职责（本模块实现）：
    - 精确 token 估算（依赖 TokenEstimator）
    - 工具结果截断（tool_result_max_chars）
    - 回合组边界识别（identify_turn_groups）
    - 基础历史裁剪骨架（compress_history，整组删除，不破坏配对）
    - 压缩触发信号（should_compress）

    Tier 1-3 完整 Compaction Pipeline 在 DOC-03 Task 3.5 实现。
    """

    def __init__(
        self,
        estimator: TokenEstimator,                   # v4：必传，由 Driver 提供精确 tokenizer
        max_context_tokens: int = 128000,            # 模型上下文窗口
        reserve_for_response: int = 4096,             # 预留给响应的 token
        tool_result_max_chars: int = 10000,           # 单个工具结果的最大字符数
        compact_trigger_ratio: float = 0.85,          # 达到上下文 85% 时触发 compact
    ):
        self._estimator = estimator
        self._max_context_tokens = max_context_tokens
        self._reserve_for_response = reserve_for_response
        self.tool_result_max_chars = tool_result_max_chars
        self._compact_trigger_ratio = compact_trigger_ratio

    def estimate_tokens(self, text: str) -> int:
        """精确估算文本的 token 数（v4：依赖 TokenEstimator）"""
        return self._estimator.estimate(text)

    def estimate_messages_tokens(
        self, messages: list[PrismMessage], system_prompt: str
    ) -> int:
        """估算完整请求的 token 数（v4：精确）"""
        return self._estimator.estimate_messages(messages, system_prompt)

    def should_compress(
        self, messages: list[PrismMessage], system_prompt: str
    ) -> bool:
        """是否需要压缩历史消息（信号源，供 Harness Compaction Pipeline 使用）

        触发条件：当前 token 数 >= (max - reserve) * compact_trigger_ratio
        默认为：已使用 85% 上下文窗口（扣除预留响应空间后）
        """
        current = self.estimate_messages_tokens(messages, system_prompt)
        threshold = int(
            (self._max_context_tokens - self._reserve_for_response)
            * self._compact_trigger_ratio
        )
        return current >= threshold

    def truncate_tool_result(self, result: str) -> str:
        """如果工具结果超过阈值，截断并追加提示。

        截断标记中文字 '截断' 必须存在（验证步骤断言）。
        """
        if len(result) <= self.tool_result_max_chars:
            return result
        truncated = result[: self.tool_result_max_chars]
        return truncated + "\n\n[结果已截断，完整内容已保存到工作目录]"

    # =========================================================
    # 回合组原子裁剪骨架（v4 新增，ADR-016）
    # =========================================================

    def identify_turn_groups(self, messages: list[PrismMessage]) -> list[tuple[int, int]]:
        """识别回合组边界（v4 新增，ADR-016）。

        回合组定义：
          起点：role=user 且 content 不含任何 tool_result block（是真实的用户 query）
          终点：下一个这样的 user message 之前（含中间的所有 assistant + tool_result user message）
          组内：assistant messages（可能多条，含 tool_use）+ user messages（全是 tool_result）

        返回每个回合组的 (start_idx, end_idx_inclusive) 列表。

        裁剪时必须整组删除或整组保留，绝不破坏 tool_use ↔ tool_result 配对。
        （违反此规则会导致 Anthropic API 报 400 错误：tool_result 没有对应的 tool_use）

        示例（Part B 验证步骤）：
          msgs[0] = user("问题 1")          ← 新 turn group 起点
          msgs[1] = assistant(tool_use A)
          msgs[2] = user(tool_result A)     ← tool_result，不是新起点
          msgs[3] = assistant("回答 1")
          msgs[4] = user("问题 2")          ← 新 turn group 起点
          msgs[5] = assistant("回答 2")
          → groups == [(0, 3), (4, 5)]
        """
        groups: list[tuple[int, int]] = []
        start: int | None = None
        for i, msg in enumerate(messages):
            is_user_query = (
                msg.role == "user"
                and not any(getattr(block, "type", None) == "tool_result" for block in msg.content)
            )
            if is_user_query:
                if start is not None:
                    groups.append((start, i - 1))
                start = i
        if start is not None:
            groups.append((start, len(messages) - 1))
        return groups

    def compress_history(self, messages: list[PrismMessage]) -> list[PrismMessage]:
        """基础历史裁剪（Tier 0）：

        1. 识别回合组边界（identify_turn_groups）
        2. 保留最近 3 个回合组不动
        3. 保留所有 is_skill_context=True 的消息（Skill Level 2 注入，ADR-017）
        4. 其他老回合组**整组删除**
           （DOC-03 Tier 2 auto-compact 会用 LLM 生成摘要替换，本 Tier 0 只做结构化裁剪）

        注意：
        - 这个方法不调用模型，只做结构化裁剪
        - 绝不单独删除一个 assistant message 或单独删除一个 tool_result
          （会破坏 tool_use ↔ tool_result 配对，导致 Anthropic API 400）
        - LLM 摘要生成在 DOC-03 Task 3.5 Compaction Pipeline

        ADR-017：is_skill_context=True 的消息跨越回合组边界保留。
        即使整个回合组被删除，组内含 is_skill_context=True 的消息也单独保留。
        """
        groups = self.identify_turn_groups(messages)
        if len(groups) <= 3:
            return messages  # 太少，不裁剪

        # 保留最近 3 组 + 所有 is_skill_context 消息
        recent_groups = groups[-3:]
        recent_indices: set[int] = set()
        for start, end in recent_groups:
            recent_indices.update(range(start, end + 1))

        result: list[PrismMessage] = []
        for i, msg in enumerate(messages):
            if i in recent_indices:
                result.append(msg)
            elif getattr(msg, "is_skill_context", False):
                # ADR-017：Skill Level 2 注入的消息优先保留，不论所在回合组是否被裁剪
                result.append(msg)
        return result
