"""
Prism v2 Model Adapter Layer — 核心类型定义与抽象基类

所有模型交互都通过 PrismMessage 统一格式进行。
两个 Driver(Anthropic / OpenAI)各自负责 PrismMessage ↔ 厂商格式的双向转换。

v4:canonical 语义对齐 Anthropic。role 只有 2 种(user/assistant),
tool_result 作为 user message 的 content block。OpenAIDriver 负责展开为 role=tool。

ADR-007: PrismMessage 以 Anthropic 语义为 canonical。
ADR-008: Driver 接口强制接受 provider_capabilities 参数。
ADR-009: 精确 tokenizer 集成在 Driver 层。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Literal


# === PrismMessage 核心类型 ===


@dataclass
class TextBlock:
    """纯文本内容块"""

    type: Literal["text"] = "text"
    text: str = ""


@dataclass
class ToolUseBlock:
    """工具调用请求块(模型发出)"""

    type: Literal["tool_use"] = "tool_use"
    id: str = ""  # 工具调用 ID
    name: str = ""  # 工具名称
    input: dict = field(default_factory=dict)  # 工具输入参数


@dataclass
class ToolResultBlock:
    """工具执行结果块(作为 user message 的 content block,canonical Anthropic 语义)

    v4:tool_result 不是独立 role,而是 user message 的 content block。
    OpenAIDriver 在 send 时负责展开为多条 role=tool 消息。
    """

    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str = ""  # 对应 ToolUseBlock.id
    content: str = ""  # 输出内容
    is_error: bool = False


# Union type: 消息内容块(ADR-007: canonical Anthropic block-based)
ContentBlock = TextBlock | ToolUseBlock | ToolResultBlock


@dataclass
class PrismMessage:
    """Prism 统一消息格式(v4:role 简化为 2 种)

    ADR-007: role 只有 'user' / 'assistant' 两种。
    禁止构造 role='tool' 或 role='system' 的 PrismMessage。
    """

    role: Literal["user", "assistant"]
    content: list[ContentBlock] = field(default_factory=list)
    # v4 新增:Skill Level 2 注入标记(Compaction 优先保留)
    is_skill_context: bool = False
    skill_name: str | None = None  # is_skill_context=True 时记录 Skill 名称


@dataclass
class ProviderCapabilities:
    """Provider 能力声明(v4 新增,ADR-008: Driver 按此降级行为)"""

    prompt_cache: bool = False  # 支持 Anthropic Prompt Cache
    streaming_tools: bool = True  # 支持流式返回工具调用参数
    extended_thinking: bool = False  # 支持 thinking 过程可见
    vision: bool = False  # 支持图片输入


@dataclass
class ToolDefinition:
    """工具定义(传给模型的 Schema)"""

    name: str = ""
    description: str = ""
    input_schema: dict = field(default_factory=dict)  # JSON Schema


@dataclass
class StreamEvent:
    """流式事件(Driver 解析后输出)"""

    type: Literal[
        "text_delta",
        "tool_use_start",
        "tool_use_delta",
        "tool_use_end",
        "message_end",
        "error",
    ]
    # text_delta: text 字段有值
    text: str = ""
    # tool_use_*: tool_use 相关字段有值
    tool_use_id: str = ""
    tool_name: str = ""
    tool_input_delta: str = ""  # JSON 参数增量(需要调用方拼接)
    tool_input_complete: dict = field(
        default_factory=dict
    )  # tool_use_end 时完整参数
    # message_end: usage 信息
    input_tokens: int = 0
    output_tokens: int = 0
    # v4 新增:Cache 相关
    cache_hit_tokens: int = 0  # Prompt Cache 命中 token 数
    cache_miss_tokens: int = 0  # Cache miss token 数
    cache_creation_tokens: int = 0  # Cache 创建消耗 token 数
    # error
    error_message: str = ""
    stop_reason: str = ""  # "end_turn" | "tool_use" | "max_tokens"


@dataclass
class ModelResponse:
    """非流式完整响应"""

    messages: list[PrismMessage]
    stop_reason: str
    input_tokens: int
    output_tokens: int
    cache_hit_tokens: int = 0  # v4 新增
    cache_miss_tokens: int = 0
    cache_creation_tokens: int = 0


class ModelAdapter(ABC):
    """模型适配器抽象基类

    ADR-008: Driver 接口强制接受 provider_capabilities 参数。
    ADR-009: count_tokens() 使用精确 tokenizer,不接受粗略字符计数。
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        capabilities: ProviderCapabilities | None = None,  # v4 新增
        **kwargs: object,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.capabilities = (
            capabilities or ProviderCapabilities()
        )  # 默认全 false,保守降级
        self.extra_config = kwargs

    @abstractmethod
    async def stream(
        self,
        messages: list[PrismMessage],
        system_prompt: str,
        tools: list[ToolDefinition] | None = None,
        max_tokens: int = 4096,
        session_id: str | None = None,  # v4 新增:用于 Redis 直通 publish channel
    ) -> AsyncIterator[StreamEvent]:
        """
        流式调用模型,返回 StreamEvent 异步迭代器。

        v4:实现时必须同时 PUBLISH text_delta / tool_use_delta 事件到
        Redis channel `sse:{session_id}`(绕过 Backend HTTP 回调),
        以实现 DOC-01 §9.1 方案 A 的流式直通。

        ADR-022:陷阱 1 — 禁止每 token 一次 HTTP 回调,必须 Redis 直通 PUBLISH。
        session_id=None 时跳过 publish(单测场景)。
        """
        # 子类必须实现:使用 yield 语法使该方法成为 async generator
        # 此处 raise 使 ABC 正确识别为抽象方法
        raise NotImplementedError
        # 使 mypy/pyright 识别返回类型为 AsyncIterator[StreamEvent]
        yield StreamEvent(type="error")  # type: ignore[misc]

    @abstractmethod
    async def complete(
        self,
        messages: list[PrismMessage],
        system_prompt: str,
        tools: list[ToolDefinition] | None = None,
        max_tokens: int = 4096,
    ) -> ModelResponse:
        """非流式调用模型,返回完整响应"""
        ...

    @abstractmethod
    def count_tokens(
        self,
        messages: list[PrismMessage],
        system_prompt: str = "",
    ) -> int:
        """
        精确估算 token 数(v4 新增,ADR-009: 不接受粗略字符计数)。

        AnthropicDriver 使用 anthropic SDK 的 count_tokens() 方法或官方 API。
        OpenAIDriver 使用 tiktoken.encoding_for_model()。
        未知模型兜底 cl100k_base 编码(并 log WARNING)。
        """
        ...

    def _sort_tools(
        self, tools: list[ToolDefinition] | None
    ) -> list[ToolDefinition] | None:
        """工具按名称字母表排序(CC 模式:保证 Prompt Cache 前缀稳定)"""
        if not tools:
            return tools
        return sorted(tools, key=lambda t: t.name)
