"""
Prism v2 — IM 适配器抽象接口 (DOC-08 Task 8.1)

每个 IM 平台实现此接口。
IMGateway 通过此接口与具体平台解耦。

平台标识字符串：
  "feishu"   — 飞书 / Lark
  "wecom"    — 企业微信
  "telegram" — Telegram Bot
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Awaitable, Callable


# ---------------------------------------------------------------------------
# Message dataclasses
# ---------------------------------------------------------------------------

@dataclass
class IMIncomingMessage:
    """标准化的收到消息。

    所有 IM 平台的消息经适配器解析后转换为此格式，
    统一交由 IMGateway._handle_message() 处理。
    """

    channel: str
    """IM 平台标识：'feishu' | 'wecom' | 'telegram'"""

    platform_user_id: str
    """IM 平台的用户标识（平台内唯一）"""

    platform_chat_id: str
    """IM 平台的会话/群聊标识。单聊时等于 platform_user_id 或平台特定值；
    群聊时为群聊 ID。与 platform_user_id 一起构成绑定三元组的第三个字段。"""

    text: str
    """消息文本内容（已去除平台特定格式标记）"""

    msg_id: str
    """平台原生消息 ID（用于幂等去重，ADR-070）。
    若平台不提供消息 ID，适配器应生成可重现的代理 ID（如 hash 摘要）。"""

    raw: dict = field(default_factory=dict)
    """原始消息体（调试用，不参与业务逻辑）"""


@dataclass
class IMOutgoingMessage:
    """标准化的发送消息。

    IMGateway 或适配器通过 IMAdapter.send() 发出此消息。
    """

    channel: str
    """目标 IM 平台标识"""

    platform_chat_id: str
    """目标会话/群聊 ID"""

    text: str
    """消息文本"""

    reply_to_message_id: str | None = None
    """回复特定消息（可选，平台支持时生效）"""


# ---------------------------------------------------------------------------
# IMAdapter abstract base class
# ---------------------------------------------------------------------------

#: 消息处理回调类型：IMGateway 注入给适配器的 handler
MessageHandler = Callable[[IMIncomingMessage], Awaitable[None]]


class IMAdapter(ABC):
    """
    IM 平台适配器抽象基类。

    子类实现：
      - FeishuAdapter   (DOC-08 Task 8.2)
      - WeComAdapter    (DOC-08 Task 8.2)
      - TelegramAdapter (DOC-08 Task 8.2)

    生命周期：
      IMGateway.register_adapter(adapter) → set_message_handler(handler)
      lifespan → await start_all()
      [收到消息] → _message_handler(IMIncomingMessage)
      lifespan shutdown → await stop_all()
    """

    def __init__(self) -> None:
        self._message_handler: MessageHandler | None = None

    # ------------------------------------------------------------------
    # Abstract interface — must be implemented by every platform adapter
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """平台标识字符串：'feishu' | 'wecom' | 'telegram'"""
        ...

    @abstractmethod
    async def start(self) -> None:
        """
        启动适配器。

        实现：
          - 飞书：建立 WebSocket 长连接，开始监听消息事件
          - 企微：注册 Webhook 回调路由（路由端点在 im.py，start() 可仅记录日志）
          - Telegram：启动 Long Polling 后台任务
          - 若平台在 im_channel_configs 中 is_enabled=False，graceful 跳过
        """
        ...

    @abstractmethod
    async def stop(self) -> None:
        """
        停止适配器。

        实现应幂等（多次调用不抛异常），并清理后台任务/连接。
        """
        ...

    @abstractmethod
    async def send(self, message: IMOutgoingMessage) -> bool:
        """
        发送消息到 IM 平台。

        Returns:
            True  — 发送成功
            False — 发送失败（实现应 log error 但不抛异常，避免影响其他平台）

        消息长度超过平台限制时，实现应自动截断并追加 "[消息已截断]"。
        各平台限制：飞书 4000 字 / 企微 2048 字 / Telegram 4096 字。
        """
        ...

    # ------------------------------------------------------------------
    # Concrete helper
    # ------------------------------------------------------------------

    def set_message_handler(self, handler: MessageHandler) -> None:
        """
        注入消息处理回调（由 IMGateway 在 register_adapter() 时调用）。

        适配器收到消息后应调用：
            if self._message_handler:
                await self._message_handler(incoming_msg)
        """
        self._message_handler = handler
