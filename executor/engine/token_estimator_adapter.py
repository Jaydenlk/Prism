"""
DriverTokenEstimator — ModelAdapter → TokenEstimator Protocol 适配器

将 ModelAdapter.count_tokens() 包装成 ContextBudgetManager 依赖的 TokenEstimator Protocol。

ADR-015：TokenEstimator 依赖注入，ContextBudgetManager 不直接持有 Driver 引用。

estimate(text):
    构造单条 user message，调用 adapter.count_tokens()。

estimate_messages(messages, system_prompt):
    直接调用 adapter.count_tokens(messages, system_prompt)。

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

from executor.adapters.base import ModelAdapter, PrismMessage, TextBlock


class DriverTokenEstimator:
    """将 ModelAdapter 包装为 TokenEstimator Protocol 实现。

    使用方式：
        adapter = AnthropicDriver(...)
        estimator = DriverTokenEstimator(adapter)
        budget = ContextBudgetManager(estimator=estimator)
    """

    def __init__(self, adapter: ModelAdapter) -> None:
        self._adapter = adapter

    def estimate(self, text: str) -> int:
        """精确估算单段文本的 token 数。

        构造单条 user PrismMessage，调用 adapter.count_tokens()。
        ADR-015：不接受字符计数粗估。
        """
        messages = [
            PrismMessage(
                role="user",
                content=[TextBlock(text=text)],
            )
        ]
        return self._adapter.count_tokens(messages, system_prompt="")

    def estimate_messages(
        self, messages: list[PrismMessage], system_prompt: str
    ) -> int:
        """精确估算完整请求（messages + system_prompt）的 token 数。

        直接调用 adapter.count_tokens()，复用 Driver 的精确 tokenizer。
        """
        return self._adapter.count_tokens(messages, system_prompt=system_prompt)
