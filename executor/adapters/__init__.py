"""
Prism v2 Model Adapter Layer

导出核心符号,供 executor 其他模块导入。

核心类型(来自 base.py):
- PrismMessage: 统一消息格式(canonical Anthropic 语义,role ∈ {user, assistant})
- TextBlock / ToolUseBlock / ToolResultBlock: 内容块类型
- ContentBlock: 联合类型别名
- ProviderCapabilities: Provider 能力声明
- ToolDefinition: 工具定义
- StreamEvent: 流式事件
- ModelResponse: 非流式完整响应
- ModelAdapter: 抽象基类

Driver(具体实现):
- AnthropicDriver: Anthropic Messages API Driver
- OpenAIDriver: OpenAI Chat Completions API Driver

解析器:
- parse_sse_lines: 公共 SSE 行解析器
"""

from executor.adapters.anthropic_driver import AnthropicDriver
from executor.adapters.base import (
    ContentBlock,
    ModelAdapter,
    ModelResponse,
    PrismMessage,
    ProviderCapabilities,
    StreamEvent,
    TextBlock,
    ToolDefinition,
    ToolResultBlock,
    ToolUseBlock,
)
from executor.adapters.openai_driver import OpenAIDriver
from executor.adapters.stream_parser import parse_sse_lines

__all__ = [
    # 核心类型
    "PrismMessage",
    "TextBlock",
    "ToolUseBlock",
    "ToolResultBlock",
    "ContentBlock",
    "ProviderCapabilities",
    "ToolDefinition",
    "StreamEvent",
    "ModelResponse",
    "ModelAdapter",
    # Drivers
    "AnthropicDriver",
    "OpenAIDriver",
    # 解析器
    "parse_sse_lines",
]
