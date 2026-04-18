"""
TokenEstimator — 可替换 Token 计数策略 (ADR-110)

策略模式：ContextBudgetManager 依赖注入此接口，不直接使用字符计数。

ADR-110(精确 tokenizer 直接上)：
  - AnthropicTokenCounter  — 包装 ModelAdapter.count_tokens()，Claude 模型首选
  - TiktokenEstimator      — tiktoken cl100k_base，OpenAI/DeepSeek 等
  - CalibratingCharCountEstimator — 字符计数 + usage feedback 动态校准系数，fallback

通过 Provider capabilities 动态选择（DOC-02 v4 ADR-009）。

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from executor.adapters.base import ModelAdapter, PrismMessage

logger = logging.getLogger(__name__)


# ============================================================
# TokenEstimator ABC
# ============================================================


class TokenEstimator(ABC):
    """Token 估算策略抽象接口（ADR-110）

    实现方由 Driver 层或 fallback 策略提供。
    ContextBudgetManager 通过此接口与具体 tokenizer 解耦。
    """

    @abstractmethod
    def estimate(self, text: str) -> int:
        """估算单段文本的 token 数"""
        ...

    @abstractmethod
    def estimate_messages(self, messages: list[dict], system_prompt: str = "") -> int:
        """估算消息列表的 token 数（含 role/structure overhead）"""
        ...

    def observe_usage(self, estimated: int, actual: int) -> None:
        """观测实际 token 数，用于校准（可选 override）。

        AnthropicDriver stream 结束后调用 estimator.observe_usage(estimated, actual)
        以支持 CalibratingCharCountEstimator 动态校准。
        默认 no-op，子类按需覆盖。
        """


# ============================================================
# AnthropicTokenCounter  —  ADR-110 实现 1（Claude 首选，精确）
# ============================================================


class AnthropicTokenCounter(TokenEstimator):
    """包装 ModelAdapter.count_tokens() 的精确估算器。

    构造时持有 ModelAdapter（AnthropicDriver / OpenAIDriver），
    调用其 count_tokens() 实现精确计数。

    使用方式：
        adapter = AnthropicDriver(...)
        estimator = AnthropicTokenCounter(adapter)
        budget = ContextBudgetManager(estimator=estimator)

    进程边界：本模块只 import executor.adapters.base（Type hint 用 TYPE_CHECKING 避免循环）
    """

    def __init__(self, adapter: "ModelAdapter") -> None:
        self._adapter = adapter

    def estimate(self, text: str) -> int:
        """精确估算单段文本的 token 数。

        构造单条 user PrismMessage，调用 adapter.count_tokens()。
        ADR-110: 不接受字符计数粗估。
        """
        from executor.adapters.base import PrismMessage, TextBlock

        messages = [PrismMessage(role="user", content=[TextBlock(text=text)])]
        try:
            return self._adapter.count_tokens(messages, system_prompt="")
        except Exception:
            logger.warning(
                "AnthropicTokenCounter.estimate failed, falling back to char count",
                exc_info=True,
            )
            return _char_count_estimate(text)

    def estimate_messages(
        self, messages: list[dict], system_prompt: str = ""
    ) -> int:
        """精确估算完整请求（messages + system_prompt）的 token 数。

        将 dict messages 转换为 PrismMessage 列表后调用 adapter.count_tokens()。
        """
        from executor.adapters.base import PrismMessage, TextBlock

        prism_msgs = _dicts_to_prism_messages(messages)
        try:
            return self._adapter.count_tokens(prism_msgs, system_prompt=system_prompt)
        except Exception:
            logger.warning(
                "AnthropicTokenCounter.estimate_messages failed, falling back",
                exc_info=True,
            )
            return _char_count_messages(messages)


# ============================================================
# TiktokenEstimator  —  ADR-110 实现 2（OpenAI/DeepSeek/通用）
# ============================================================


class TiktokenEstimator(TokenEstimator):
    """基于 tiktoken 的精确计数器（ADR-110 实现 2）。

    使用 cl100k_base encoding（Claude / GPT-4 近似编码器）。
    误差范围 < 5%（不同模型 tokenizer 略有差异）。
    首次加载需下载编码器文件 (~1MB)，后续 LRU 缓存在进程内存。

    OpenAI / DeepSeek / 通用模型首选。
    """

    def __init__(self, encoding: str = "cl100k_base") -> None:
        try:
            import tiktoken

            self._enc = tiktoken.get_encoding(encoding)
        except ImportError:
            logger.error("tiktoken not installed; TiktokenEstimator unavailable")
            raise

    def estimate(self, text: str) -> int:
        return len(self._enc.encode(text))

    def estimate_messages(
        self, messages: list[dict], system_prompt: str = ""
    ) -> int:
        total = 0
        # per-message overhead (OpenAI tiktoken 约定: 4 tokens/message + 3 priming)
        if system_prompt:
            total += self.estimate(system_prompt) + 4
        for msg in messages:
            total += 4  # role + structure overhead
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.estimate(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        total += self.estimate(block.get("text", str(block)))
                    else:
                        total += self.estimate(str(block))
        total += 3  # reply priming
        return total


# ============================================================
# CalibratingCharCountEstimator  —  ADR-110 实现 3（fallback + 自校准）
# ============================================================

_DEFAULT_ASCII_RATIO = 4.0   # 4 ASCII chars ≈ 1 token
_DEFAULT_CJK_RATIO = 1.5     # 1.5 CJK chars ≈ 1 token
_CALIBRATION_ALPHA = 0.1     # EMA 平滑系数（低 α = 稳定，高 α = 敏感）
_MIN_SAMPLES_TO_CALIBRATE = 5  # 至少采样 N 次才开始更新系数


class CalibratingCharCountEstimator(TokenEstimator):
    """字符计数 + usage feedback 动态校准（ADR-110 实现 3，fallback）。

    observer 模式：每次 stream 结束后调用 observe_usage(estimated, actual)，
    用 actual/estimated 比值的 EMA 更新校准系数（_calibration_factor）。

    初始时 _calibration_factor = 1.0（无校准），
    随着真实 usage 反馈逐渐收敛到合适值。

    线程安全：_calibration_factor 更新使用 threading.Lock。
    """

    def __init__(self) -> None:
        self._ascii_ratio: float = _DEFAULT_ASCII_RATIO
        self._cjk_ratio: float = _DEFAULT_CJK_RATIO
        self._calibration_factor: float = 1.0
        self._sample_count: int = 0
        self._lock = threading.Lock()

    def estimate(self, text: str) -> int:
        """字符计数估算，乘以校准系数。"""
        raw = _char_count_estimate_detailed(text, self._ascii_ratio, self._cjk_ratio)
        return max(1, int(raw * self._calibration_factor))

    def estimate_messages(
        self, messages: list[dict], system_prompt: str = ""
    ) -> int:
        """估算消息列表 token 数（含 role/structure overhead）。"""
        total = 0
        if system_prompt:
            total += self.estimate(system_prompt) + 4
        for msg in messages:
            total += 4  # role + structure overhead
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.estimate(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        total += self.estimate(block.get("text", str(block)))
                    else:
                        total += self.estimate(str(block))
        return total

    def observe_usage(self, estimated: int, actual: int) -> None:
        """接收实际 usage 反馈，动态更新校准系数（EMA）。

        actual/estimated 比值：> 1 表示低估（下次放大），< 1 表示高估（下次缩小）。
        使用 EMA 平滑，避免单次异常数据导致剧烈抖动。

        ADR-110: CalibratingCharCountEstimator 根据 usage feedback 动态校准系数。
        """
        if estimated <= 0 or actual <= 0:
            return
        ratio = actual / estimated
        with self._lock:
            self._sample_count += 1
            if self._sample_count >= _MIN_SAMPLES_TO_CALIBRATE:
                # EMA: new = (1 - α) * old + α * ratio
                self._calibration_factor = (
                    (1.0 - _CALIBRATION_ALPHA) * self._calibration_factor
                    + _CALIBRATION_ALPHA * ratio
                )

    @property
    def calibration_factor(self) -> float:
        """当前校准系数（用于调试/监控）"""
        return self._calibration_factor

    @property
    def sample_count(self) -> int:
        """已采样次数"""
        return self._sample_count


# ============================================================
# 工厂函数 (ADR-110)
# ============================================================


def create_estimator(
    strategy: str = "charcount",
    adapter: "ModelAdapter | None" = None,
    tiktoken_encoding: str = "cl100k_base",
) -> TokenEstimator:
    """根据策略名称创建 TokenEstimator 实例。

    strategy 取值：
      "anthropic"  — AnthropicTokenCounter（需要传入 adapter）
      "tiktoken"   — TiktokenEstimator（tiktoken cl100k_base）
      "charcount"  — CalibratingCharCountEstimator（零依赖 fallback）

    根据 Provider capabilities 动态选择的逻辑（ADR-110）：
      - Claude 模型 → "anthropic"（adapter 必传）
      - OpenAI / DeepSeek → "tiktoken"
      - 其他 / 无依赖环境 → "charcount"
    """
    if strategy == "anthropic":
        if adapter is None:
            raise ValueError(
                "create_estimator(strategy='anthropic') requires adapter parameter"
            )
        return AnthropicTokenCounter(adapter)
    if strategy == "tiktoken":
        return TiktokenEstimator(tiktoken_encoding)
    # Default: calibrating char count (fallback)
    return CalibratingCharCountEstimator()


# ============================================================
# 内部辅助函数
# ============================================================


def _char_count_estimate(text: str) -> int:
    """基础字符计数估算（无校准系数）。"""
    return _char_count_estimate_detailed(text, _DEFAULT_ASCII_RATIO, _DEFAULT_CJK_RATIO)


def _char_count_estimate_detailed(
    text: str, ascii_ratio: float, cjk_ratio: float
) -> int:
    """按 ASCII / CJK 分区字符计数。"""
    cjk_count = sum(
        1
        for c in text
        if "\u4e00" <= c <= "\u9fff" or "\u3000" <= c <= "\u303f"
    )
    ascii_count = len(text) - cjk_count
    return max(1, int(ascii_count / ascii_ratio + cjk_count / cjk_ratio))


def _char_count_messages(messages: list[dict]) -> int:
    """用字符计数估算 dict message 列表的 token 数（fallback 辅助）。"""
    total = 0
    for msg in messages:
        total += 4
        content = msg.get("content", "")
        if isinstance(content, str):
            total += _char_count_estimate(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total += _char_count_estimate(block.get("text", str(block)))
                else:
                    total += _char_count_estimate(str(block))
    return total


def _dicts_to_prism_messages(messages: list[dict]) -> list["PrismMessage"]:
    """将 dict 格式 messages 转换为 PrismMessage 列表（用于 count_tokens 调用）。"""
    from executor.adapters.base import PrismMessage, TextBlock

    result: list[PrismMessage] = []
    for msg in messages:
        role = msg.get("role", "user")
        if role not in ("user", "assistant"):
            role = "user"
        content = msg.get("content", "")
        if isinstance(content, str):
            blocks = [TextBlock(text=content)]
        elif isinstance(content, list):
            blocks = [TextBlock(text=str(b)) for b in content]
        else:
            blocks = [TextBlock(text=str(content))]
        result.append(PrismMessage(role=role, content=blocks))  # type: ignore[arg-type]
    return result
