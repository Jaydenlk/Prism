"""
Prism v2 — Telegram Bot IM 适配器 (DOC-08 Task 8.2)

接入方式：
  - 消息接收：Long Polling（getUpdates，在 asyncio 后台 Task 中循环）
  - 消息发送：sendMessage API
  - 认证：只需 bot_token，无需服务器端证书

配置字段（im_channel_configs.config JSONB）：
  - bot_token:      Telegram Bot Token（格式：123456789:ABCdef...）
  - poll_timeout:   Long Polling timeout（秒，默认 30）
  - poll_interval:  出错后重试间隔（秒，默认 2）

消息长度限制：4096 字符（超出截断并追加 "[消息已截断]"）

Long Polling 说明：
  start() 启动一个 asyncio.Task 在后台循环调用 getUpdates。
  stop() 取消该 Task，幂等。
  update_id 用于 getUpdates 的 offset 参数（避免重复接收）。

错误处理：
  - 网络错误：记录 warning，等待 poll_interval 后重试
  - API 错误（非 200）：记录 error，等待 poll_interval 后重试
  - 发送失败：记录 error 但不抛异常，不影响其他平台

API 文档参考：https://core.telegram.org/bots/api
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from app.services.im_adapter import IMAdapter, IMIncomingMessage, IMOutgoingMessage

logger = structlog.get_logger(__name__)

# Telegram 消息长度限制
TELEGRAM_MAX_LENGTH = 4096
_TRUNCATE_SUFFIX = "\n\n[消息已截断，完整结果请在 Prism Web 端查看]"

# Telegram Bot API 基础 URL
TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramAdapter(IMAdapter):
    """
    Telegram Bot IM 适配器。

    实现 IMAdapter 接口，通过 Long Polling 接收消息，
    通过 sendMessage API 发送消息。

    使用方式（由 IMGateway 管理）：
        adapter = TelegramAdapter(config)
        gateway.register_adapter(adapter)
        await gateway.start_all()  # 启动 Long Polling 后台 Task
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """
        Args:
            config: im_channel_configs.config JSONB，包含 bot_token /
                    poll_timeout / poll_interval
        """
        super().__init__()
        self._config = config
        self._bot_token: str = config.get("bot_token", "")
        self._poll_timeout: int = int(config.get("poll_timeout", 30))
        self._poll_interval: float = float(config.get("poll_interval", 2.0))

        # Long Polling 状态
        self._offset: int = 0
        self._polling_task: asyncio.Task[None] | None = None
        self._running: bool = False

    # ------------------------------------------------------------------
    # IMAdapter interface
    # ------------------------------------------------------------------

    @property
    def channel_name(self) -> str:
        return "telegram"

    def is_configured(self) -> bool:
        return bool(self._bot_token)

    async def start(self) -> None:
        """
        启动 Telegram Long Polling 后台任务。

        若 bot_token 未配置，graceful 跳过。
        若已在运行，幂等（不重复启动）。
        """
        if not self._bot_token:
            logger.warning(
                "telegram.adapter.start_skipped",
                reason="bot_token not configured",
            )
            return

        if self._running and self._polling_task and not self._polling_task.done():
            logger.debug("telegram.adapter.already_running")
            return

        self._running = True
        self._polling_task = asyncio.create_task(
            self._polling_loop(),
            name="telegram_polling",
        )
        logger.info("telegram.adapter.started")

    async def stop(self) -> None:
        """
        停止 Long Polling 任务（幂等）。

        等待任务完成（最多 5 秒）。
        """
        self._running = False
        if self._polling_task and not self._polling_task.done():
            self._polling_task.cancel()
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._polling_task),
                    timeout=5.0,
                )
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        self._polling_task = None
        logger.info("telegram.adapter.stopped")

    async def send(self, message: IMOutgoingMessage) -> bool:
        """
        通过 Telegram sendMessage API 发送消息。

        POST https://api.telegram.org/bot{token}/sendMessage

        Args:
            message: 待发送消息（platform_chat_id 为 Telegram chat_id，整数字符串）

        Returns:
            True — 发送成功；False — 发送失败（已 log error，不抛异常）
        """
        text = message.text
        if len(text) > TELEGRAM_MAX_LENGTH:
            text = text[: TELEGRAM_MAX_LENGTH - len(_TRUNCATE_SUFFIX)] + _TRUNCATE_SUFFIX

        try:
            url = self._api_url("sendMessage")
            payload: dict[str, Any] = {
                "chat_id": message.platform_chat_id,
                "text": text,
            }
            if message.reply_to_message_id:
                try:
                    payload["reply_to_message_id"] = int(message.reply_to_message_id)
                except ValueError:
                    pass  # 无效消息 ID，跳过回复参数

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)

            data = resp.json()
            if not data.get("ok"):
                logger.error(
                    "telegram.send.api_error",
                    chat_id=message.platform_chat_id,
                    description=data.get("description"),
                    error_code=data.get("error_code"),
                )
                return False

            logger.info(
                "telegram.send.success",
                chat_id=message.platform_chat_id,
                text_len=len(text),
            )
            return True

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "telegram.send.exception",
                chat_id=message.platform_chat_id,
                error=str(exc),
            )
            return False

    # ------------------------------------------------------------------
    # Long Polling loop
    # ------------------------------------------------------------------

    async def _polling_loop(self) -> None:
        """
        Long Polling 主循环（在 asyncio.Task 中运行）。

        循环逻辑：
          1. 调用 getUpdates(offset=self._offset, timeout=poll_timeout)
          2. 处理返回的 updates
          3. 更新 offset = max(update_id) + 1（确认 updates 已收到）
          4. 出错时等待 poll_interval 后重试
        """
        logger.info("telegram.polling.started", offset=self._offset)
        while self._running:
            try:
                updates = await self._get_updates()
                for update in updates:
                    await self._process_update(update)
                    # 更新 offset：已处理的最大 update_id + 1
                    self._offset = max(self._offset, update.get("update_id", 0) + 1)
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "telegram.polling.error",
                    error=str(exc),
                    retry_in=self._poll_interval,
                )
                try:
                    await asyncio.sleep(self._poll_interval)
                except asyncio.CancelledError:
                    break

        logger.info("telegram.polling.stopped")

    async def _get_updates(self) -> list[dict[str, Any]]:
        """
        调用 Telegram getUpdates API（Long Polling）。

        Returns:
            updates 列表（可能为空）

        Raises:
            httpx.HTTPError / RuntimeError — 供 _polling_loop 捕获并重试
        """
        url = self._api_url("getUpdates")
        params: dict[str, Any] = {
            "timeout": self._poll_timeout,
            "allowed_updates": ["message"],
        }
        if self._offset:
            params["offset"] = self._offset

        # httpx timeout 需比 poll_timeout 稍大
        async with httpx.AsyncClient(timeout=self._poll_timeout + 10.0) as client:
            resp = await client.get(url, params=params)

        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(
                f"getUpdates failed: {data.get('description')} "
                f"(error_code={data.get('error_code')})"
            )
        return data.get("result", [])

    async def _process_update(self, update: dict[str, Any]) -> None:
        """
        处理单条 Telegram Update。

        只处理 message 类型（含文本消息）。
        其他类型（callback_query / channel_post 等）忽略。
        """
        message = update.get("message")
        if not message:
            return  # 非文本消息类型（如 callback_query），忽略

        text: str = message.get("text", "").strip()
        if not text:
            return  # 非文本消息（图片/音频等），忽略

        from_user = message.get("from", {})
        chat = message.get("chat", {})
        update_id: int = update.get("update_id", 0)
        message_id: int = message.get("message_id", 0)

        # platform_user_id：Telegram 用户数字 ID（转字符串）
        user_id_int: int = from_user.get("id", 0)
        platform_user_id = str(user_id_int)

        # platform_chat_id：对话的 chat.id（群聊时与 user.id 不同）
        chat_id_int: int = chat.get("id", user_id_int)
        platform_chat_id = str(chat_id_int)

        # msg_id：以 update_id 为主（全局唯一），追加 message_id 确保唯一性
        msg_id = f"tg:{update_id}:{message_id}"

        if not platform_user_id or not msg_id:
            logger.warning(
                "telegram.message.invalid",
                update_id=update_id,
                has_user=bool(platform_user_id),
            )
            return

        incoming = IMIncomingMessage(
            channel=self.channel_name,
            platform_user_id=platform_user_id,
            platform_chat_id=platform_chat_id,
            text=text,
            msg_id=msg_id,
            raw=update,
        )

        if self._message_handler:
            try:
                await self._message_handler(incoming)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "telegram.message.handler_error",
                    update_id=update_id,
                    error=str(exc),
                )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _api_url(self, method: str) -> str:
        """构造 Telegram Bot API URL。"""
        return f"{TELEGRAM_API_BASE}/bot{self._bot_token}/{method}"
