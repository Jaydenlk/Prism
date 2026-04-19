"""
Prism v2 — 飞书 (Lark) IM 适配器 (DOC-08 Task 8.2 / Task B-1)

接入方式：
  - 消息接收：飞书事件订阅 Webhook（POST /im/webhook/feishu）
    Webhook 回调模式（push），无需 WebSocket 长连接。
  - 消息发送：飞书消息 API（POST /open-apis/im/v1/messages）
  - Token 刷新：tenant_access_token 缓存于 Redis（key=feishu:tenant_token），
    TTL = min(feishu_expire - 60, 7000)，比飞书 2h 过期提前刷新。

配置来源（Task B-1 起）：
  优先从 Settings（环境变量）读取 FEISHU_* 字段。
  若 Settings 未配置（全空），回退到 im_channel_configs.config JSONB（DB 端配置）。

签名校验（X-Lark-Signature）：
  飞书 Webhook 签名算法：
    timestamp + nonce + body_str → SHA256（注意：不混入任何密钥，只是内容 hash）
  或使用 encrypt_key 时的签名算法：
    SHA256(timestamp + encrypt_key + body_str).hexdigest()
  本实现采用飞书官方文档 "验证请求签名" 方案：
    HMAC-SHA256 的 key = encrypt_key，message = timestamp + nonce + body_bytes
  若 FEISHU_ENCRYPT_KEY 未配置，跳过签名校验（verify_signature 返回 False）。

加密消息（FEISHU_ENCRYPT_KEY 配置时）：
  飞书事件通过 AES-CBC-256 加密，key = SHA256(encrypt_key)，
  格式：base64(IV[16字节] + ciphertext)，PKCS7 padding。
  依赖 pycryptodome（requirements.txt）。

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

# Redis cache key for tenant_access_token
_REDIS_TOKEN_KEY = "feishu:tenant_token"
# Cache TTL: 7000s (slightly less than Feishu's 2h = 7200s)
_TOKEN_CACHE_MAX_TTL = 7000


class FeishuAdapter(IMAdapter):
    """
    飞书 IM 适配器。

    实现 IMAdapter 接口，通过 Webhook 回调接收消息，
    通过飞书消息 API 发送消息。

    配置读取顺序（Task B-1）：
      1. Settings 环境变量（FEISHU_APP_ID / FEISHU_APP_SECRET / ...）
      2. 回退到传入的 config dict（im_channel_configs.config JSONB）

    使用方式（由 IMGateway 管理）：
        adapter = FeishuAdapter(config, settings=settings, redis_client=redis)
        gateway.register_adapter(adapter)
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        settings: Any = None,
        redis_client: Any = None,
    ) -> None:
        """
        Args:
            config:       im_channel_configs.config JSONB（DB 端配置，可为 None）
            settings:     app.core.config.Settings 实例（优先级高于 config）
            redis_client: redis.asyncio.Redis 实例（用于 tenant_access_token 缓存）
        """
        super().__init__()
        cfg = config or {}

        # --- Config resolution: Settings > DB config dict ---
        if settings is not None and settings.FEISHU_APP_ID:
            self._app_id: str = settings.FEISHU_APP_ID
            self._app_secret: str = settings.FEISHU_APP_SECRET
            self._encrypt_key: str = settings.FEISHU_ENCRYPT_KEY
            self._verify_token: str = settings.FEISHU_VERIFICATION_TOKEN
        else:
            self._app_id = cfg.get("app_id", "")
            self._app_secret = cfg.get("app_secret", "")
            self._encrypt_key = cfg.get("encrypt_key", "")
            self._verify_token = cfg.get("verify_token", "")

        # Redis client for tenant_access_token cache (optional)
        self._redis = redis_client

        # In-memory token fallback (when Redis unavailable)
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

    def is_configured(self) -> bool:
        """Return True if app_id and app_secret are both non-empty."""
        return bool(self._app_id and self._app_secret)

    async def start(self) -> None:
        """
        启动飞书适配器。

        Webhook 模式下 start() 只需标记适配器已就绪并预热 token。
        若 app_id / app_secret 未配置，静默跳过（不抛异常，不阻止启动）。
        """
        if not self.is_configured():
            logger.warning(
                "feishu.adapter.start_skipped",
                reason="app_id or app_secret not configured",
            )
            return

        self._running = True
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
        if not self.is_configured():
            logger.warning(
                "feishu.send.not_configured",
                chat_id=message.platform_chat_id,
            )
            return False

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
                url = (
                    f"{FEISHU_API_BASE}/open-apis/im/v1/messages"
                    f"/{message.reply_to_message_id}/reply"
                )
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
    # Convenience method: send text directly by chat_id
    # ------------------------------------------------------------------

    async def send_message(self, chat_id: str, text: str) -> bool:
        """
        Convenience wrapper: send text message to a chat_id.

        Used by callback_service when delivering run_complete results.
        """
        return await self.send(
            IMOutgoingMessage(
                channel=self.channel_name,
                platform_chat_id=chat_id,
                text=text,
            )
        )

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

        飞书官方签名算法（encrypt_key 模式）：
          content = timestamp + encrypt_key + body_str
          expected = SHA256(content.encode()).hexdigest()

        若 encrypt_key 未配置，无法校验 → 返回 False（调用方应拒绝请求）。

        参考：https://open.feishu.cn/document/server-docs/event-subscription-guide/
               event-subscription-configure-/request-url-configuration-case
        """
        if not self._encrypt_key:
            # 未配置 encrypt_key，无法验签 → 拒绝（安全优先）
            return False

        body_str = body_bytes.decode("utf-8")
        content = timestamp + self._encrypt_key + body_str
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return hmac.compare_digest(expected, signature)

    def decrypt_message(self, encrypted: str) -> dict[str, Any]:
        """
        解密飞书加密消息（当 FEISHU_ENCRYPT_KEY 已配置时使用）。

        飞书使用 AES-CBC-256 加密，key 为 encrypt_key 的 SHA256 摘要。
        依赖 pycryptodome（requirements.txt）。

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

        # URL 验证（必须在 is_configured 检查之前，Feishu 初次配置时 token 可能未填）
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
    # Token management (Redis-backed with in-memory fallback)
    # ------------------------------------------------------------------

    async def _ensure_token(self) -> str:
        """
        获取（或刷新）tenant_access_token。

        Token 优先从 Redis 读取（key=feishu:tenant_token）；
        Redis 不可用或缓存不存在时回退到内存缓存。
        过期前 60 秒自动刷新。并发安全：asyncio.Lock。
        """
        async with self._token_lock:
            now = time.time()

            # --- 1. Try Redis cache ---
            if self._redis is not None:
                try:
                    cached = await self._redis.get(_REDIS_TOKEN_KEY)
                    if cached:
                        token_str = (
                            cached.decode("utf-8")
                            if isinstance(cached, bytes)
                            else cached
                        )
                        ttl = await self._redis.ttl(_REDIS_TOKEN_KEY)
                        if ttl > 60:
                            return token_str
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "feishu.token.redis_read_failed",
                        error=str(exc),
                    )

            # --- 2. Try in-memory cache ---
            if self._access_token and now < self._token_expires_at - 60:
                return self._access_token

            # --- 3. Fetch from Feishu API ---
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

            token = data["tenant_access_token"]
            feishu_expire: int = int(data.get("expire", 7200))
            # Cache TTL: slightly shorter than Feishu's expiry (min with max cap)
            cache_ttl = min(feishu_expire - 60, _TOKEN_CACHE_MAX_TTL)

            # Update in-memory cache
            self._access_token = token
            self._token_expires_at = now + cache_ttl

            # Update Redis cache
            if self._redis is not None:
                try:
                    await self._redis.setex(_REDIS_TOKEN_KEY, cache_ttl, token)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "feishu.token.redis_write_failed",
                        error=str(exc),
                    )

            logger.info(
                "feishu.token.refreshed",
                expires_in=feishu_expire,
                cache_ttl=cache_ttl,
            )
            return token
