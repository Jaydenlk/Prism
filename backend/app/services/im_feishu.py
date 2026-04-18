"""
Prism v2 — 飞书 (Lark) IM 适配器 (DOC-08 Task 8.2)

接入方式：
  - 消息接收：飞书事件订阅 Webhook（POST /im/webhook/feishu）
    飞书支持 WebSocket 长连接（官方 SDK lark-oapi），但为简化部署，
    此实现使用 Webhook 回调模式（也是生产中最常见的方案）。
  - 消息发送：飞书消息 API（POST /open-apis/im/v1/messages）
  - Token 刷新：自动刷新 tenant_access_token（过期前 60 秒更新）

配置字段（im_channel_configs.config JSONB）：
  - app_id:     飞书应用 ID
  - app_secret: 飞书应用密钥
  - verify_token: 事件订阅验证 token（用于 X-Lark-Signature 校验）
  - encrypt_key: 消息加密密钥（可选，启用时消息体为加密 JSON）

消息长度限制：4000 字符（超出截断并追加 "[消息已截断]"）

签名校验：
  飞书 Webhook 使用 HMAC-SHA256 签名，header X-Lark-Signature。
  签名计算：HMAC-SHA256(timestamp + verify_token + body, verify_token)。
  若 verify_token 未配置，跳过校验（仅适合内网部署）。

加密消息（encrypt_key 配置时）：
  飞书事件通过 AES-CBC 加密传输，使用 pycryptodome 解密。
  参考：https://open.feishu.cn/document/server-docs/event-subscription-guide/event-subscription-configure-/encrypt-key-encryption-configuration-case

API 文档参考：https://open.feishu.cn/document
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
from typing import Any

import httpx
import structlog

from app.services.im_adapter import IMAdapter, IMIncomingMessage, IMOutgoingMessage

logger = structlog.get_logger(__name__)

# 飞书消息长度限制
FEISHU_MAX_LENGTH = 4000
_TRUNCATE_SUFFIX = "\n\n[消息已截断，完整结果请在 Prism Web 端查看]"

# 飞书 API 基础 URL
FEISHU_API_BASE = "https://open.feishu.cn"


class FeishuAdapter(IMAdapter):
    """
    飞书 IM 适配器。

    实现 IMAdapter 接口，通过 Webhook 回调接收消息，
    通过飞书消息 API 发送消息。

    使用方式（由 IMGateway 管理）：
        adapter = FeishuAdapter(config)
        gateway.register_adapter(adapter)
        # 飞书消息通过 POST /im/webhook/feishu → handle_webhook() 路由进来
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """
        Args:
            config: im_channel_configs.config JSONB，包含 app_id / app_secret /
                    verify_token / encrypt_key（可选）
        """
        super().__init__()
        self._config = config
        self._app_id: str = config.get("app_id", "")
        self._app_secret: str = config.get("app_secret", "")
        self._verify_token: str = config.get("verify_token", "")
        self._encrypt_key: str = config.get("encrypt_key", "")

        # token 缓存（access_token, 过期时间戳）
        self._access_token: str = ""
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

        self._running: bool = False

    # ------------------------------------------------------------------
    # IMAdapter interface
    # ------------------------------------------------------------------

    @property
    def channel_name(self) -> str:
        return "feishu"

    async def start(self) -> None:
        """
        启动飞书适配器。

        Webhook 模式下 start() 只需标记适配器已就绪并预热 token。
        实际消息接收由 FastAPI Webhook 端点驱动（push 模式）。
        """
        if not self._app_id or not self._app_secret:
            logger.warning(
                "feishu.adapter.start_skipped",
                reason="app_id or app_secret not configured",
            )
            return

        self._running = True
        # 预热 access_token（避免首条消息时等待获取）
        try:
            await self._ensure_token()
            logger.info("feishu.adapter.started", app_id=self._app_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("feishu.adapter.token_preheat_failed", error=str(exc))

    async def stop(self) -> None:
        """停止适配器（清理标志位，幂等）。"""
        self._running = False
        self._access_token = ""
        self._token_expires_at = 0.0
        logger.info("feishu.adapter.stopped")

    async def send(self, message: IMOutgoingMessage) -> bool:
        """
        通过飞书消息 API 发送消息。

        POST https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id

        Args:
            message: 待发送消息（platform_chat_id 为飞书 chat_id 或 open_id）

        Returns:
            True — 发送成功；False — 发送失败（已 log error，不抛异常）
        """
        text = message.text
        # 截断至平台限制
        if len(text) > FEISHU_MAX_LENGTH:
            text = text[: FEISHU_MAX_LENGTH - len(_TRUNCATE_SUFFIX)] + _TRUNCATE_SUFFIX

        try:
            token = await self._ensure_token()
            payload = {
                "receive_id": message.platform_chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}),
            }
            if message.reply_to_message_id:
                # 飞书回复消息需要使用 reply 接口
                url = f"{FEISHU_API_BASE}/open-apis/im/v1/messages/{message.reply_to_message_id}/reply"
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        url,
                        headers={"Authorization": f"Bearer {token}"},
                        json={"msg_type": "text", "content": json.dumps({"text": text})},
                    )
            else:
                url = f"{FEISHU_API_BASE}/open-apis/im/v1/messages"
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        url,
                        params={"receive_id_type": "chat_id"},
                        headers={"Authorization": f"Bearer {token}"},
                        json=payload,
                    )

            data = resp.json()
            if data.get("code") != 0:
                logger.error(
                    "feishu.send.api_error",
                    chat_id=message.platform_chat_id,
                    code=data.get("code"),
                    msg=data.get("msg"),
                )
                return False

            logger.info(
                "feishu.send.success",
                chat_id=message.platform_chat_id,
                text_len=len(text),
            )
            return True

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "feishu.send.exception",
                chat_id=message.platform_chat_id,
                error=str(exc),
            )
            return False

    # ------------------------------------------------------------------
    # Webhook handling (called by api/v1/im.py)
    # ------------------------------------------------------------------

    def verify_signature(
        self,
        timestamp: str,
        nonce: str,
        body_bytes: bytes,
        signature: str,
    ) -> bool:
        """
        验证飞书 Webhook 签名（X-Lark-Signature）。

        签名算法：
          concat = timestamp + nonce + verify_token + body_str
          expected = SHA256(concat).hexdigest()

        若 verify_token 未配置，跳过校验（返回 True）。

        参考：https://open.feishu.cn/document/server-docs/event-subscription-guide/
               event-subscription-configure-/request-url-configuration-case
        """
        if not self._verify_token:
            return True  # 未配置 verify_token，跳过校验

        body_str = body_bytes.decode("utf-8")
        content = timestamp + nonce + self._verify_token + body_str
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return hmac.compare_digest(expected, signature)

    def decrypt_message(self, encrypted: str) -> dict[str, Any]:
        """
        解密飞书加密消息（当 encrypt_key 已配置时使用）。

        飞书使用 AES-CBC-256 加密，key 为 encrypt_key 的 SHA256 摘要。
        依赖 pycryptodome（已在 requirements.txt 中追加）。

        参考：https://open.feishu.cn/document/server-docs/event-subscription-guide/
               event-subscription-configure-/encrypt-key-encryption-configuration-case
        """
        try:
            from Crypto.Cipher import AES  # pycryptodome
        except ImportError as exc:
            raise RuntimeError(
                "pycryptodome is required for Feishu message decryption. "
                "Please add pycryptodome to requirements.txt."
            ) from exc

        # AES key = SHA256(encrypt_key)
        key = hashlib.sha256(self._encrypt_key.encode("utf-8")).digest()
        # encrypted = base64(IV + ciphertext)
        raw = base64.b64decode(encrypted)
        iv = raw[:AES.block_size]
        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(raw[AES.block_size :])
        # 去除 PKCS7 padding
        pad_len = decrypted[-1]
        decrypted = decrypted[:-pad_len]
        return json.loads(decrypted.decode("utf-8"))

    async def handle_webhook(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        处理飞书 Webhook 事件（由 POST /im/webhook/feishu 端点调用）。

        返回值直接作为 HTTP 响应（飞书要求某些情况下响应特定字段）。

        飞书事件类型：
          - url_verification：URL 验证，响应 {"challenge": "..."}
          - im.message.receive_v1：收到消息事件
          - 其他事件类型：忽略，响应 {"status": "ok"}
        """
        # 处理加密消息（encrypt 字段存在时）
        if "encrypt" in body and self._encrypt_key:
            try:
                body = self.decrypt_message(body["encrypt"])
            except Exception as exc:  # noqa: BLE001
                logger.error("feishu.webhook.decrypt_failed", error=str(exc))
                return {"status": "error", "msg": "decrypt failed"}

        # URL 验证
        if body.get("type") == "url_verification":
            challenge = body.get("challenge", "")
            logger.info("feishu.webhook.url_verification")
            return {"challenge": challenge}

        # 事件处理
        header = body.get("header", {})
        event_type = header.get("event_type", body.get("event", {}).get("type", ""))

        if event_type == "im.message.receive_v1":
            await self._handle_message_event(body)
        else:
            logger.debug(
                "feishu.webhook.event_ignored",
                event_type=event_type,
            )

        return {"status": "ok"}

    async def _handle_message_event(self, body: dict[str, Any]) -> None:
        """
        解析飞书 im.message.receive_v1 事件，转换为 IMIncomingMessage 并回调 handler。

        事件结构（飞书 v2 event）：
          body.event.message.message_id  — 消息 ID（用于幂等）
          body.event.sender.sender_id.open_id — 发送者 open_id
          body.event.message.chat_id      — 群聊 ID 或单聊虚拟 ID
          body.event.message.content      — JSON 字符串，{"text": "..."}
        """
        event = body.get("event", {})
        message = event.get("message", {})
        sender = event.get("sender", {})

        msg_id: str = message.get("message_id", "")
        platform_user_id: str = sender.get("sender_id", {}).get("open_id", "")
        platform_chat_id: str = message.get("chat_id", platform_user_id)
        msg_type: str = message.get("message_type", "text")

        # 只处理文本消息
        if msg_type != "text":
            logger.debug(
                "feishu.message.ignored_type",
                msg_type=msg_type,
                msg_id=msg_id,
            )
            return

        # 解析消息内容
        try:
            content_str = message.get("content", "{}")
            content = json.loads(content_str)
            text = content.get("text", "").strip()
        except (json.JSONDecodeError, AttributeError):
            text = ""

        if not text or not platform_user_id or not msg_id:
            logger.warning(
                "feishu.message.invalid",
                msg_id=msg_id,
                has_text=bool(text),
                has_user=bool(platform_user_id),
            )
            return

        incoming = IMIncomingMessage(
            channel=self.channel_name,
            platform_user_id=platform_user_id,
            platform_chat_id=platform_chat_id,
            text=text,
            msg_id=msg_id,
            raw=body,
        )

        if self._message_handler:
            try:
                await self._message_handler(incoming)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "feishu.message.handler_error",
                    msg_id=msg_id,
                    error=str(exc),
                )

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def _ensure_token(self) -> str:
        """
        获取（或刷新）tenant_access_token。

        Token 在过期前 60 秒自动刷新（避免临界失效）。
        并发安全：使用 asyncio.Lock 防止并发重复刷新。
        """
        async with self._token_lock:
            now = time.time()
            # 剩余有效期 > 60 秒时直接返回缓存
            if self._access_token and now < self._token_expires_at - 60:
                return self._access_token

            # 请求新 token
            url = f"{FEISHU_API_BASE}/open-apis/auth/v3/tenant_access_token/internal"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url,
                    json={
                        "app_id": self._app_id,
                        "app_secret": self._app_secret,
                    },
                )
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(
                    f"Feishu token fetch failed: code={data.get('code')}, "
                    f"msg={data.get('msg')}"
                )

            self._access_token = data["tenant_access_token"]
            # expire 为秒数（通常 7200），存绝对时间戳
            self._token_expires_at = now + int(data.get("expire", 7200))
            logger.info(
                "feishu.token.refreshed",
                expires_in=data.get("expire", 7200),
            )
            return self._access_token
