"""
Prism v2 — 企业微信 (WeCom) IM 适配器 (DOC-08 Task 8.2)

接入方式：
  - 消息接收：Webhook 回调（POST /im/webhook/wecom）
  - 消息发送：企业微信应用消息 API（POST /cgi-bin/message/send）
  - Token 刷新：自动刷新 access_token（过期前 60 秒更新）

配置字段（im_channel_configs.config JSONB）：
  - corp_id:   企业 ID（CorpID）
  - agent_id:  应用 AgentID（整数，以字符串存储）
  - secret:    应用 Secret
  - token:     企业微信回调 Token（用于 msg_signature 校验）
  - encoding_aes_key: 消息加解密密钥（43 位 Base64，用于 XML 消息解密）

消息长度限制：2048 字符（超出截断并追加 "[消息已截断]"）

安全说明：
  企业微信 Webhook 有两层验证：
  1. URL 验证（GET 请求）：验证 msg_signature 后返回 echostr 明文
  2. 消息签名（POST 请求）：验证 msg_signature = SHA1(sort(token, timestamp, nonce, encrypt))

  消息解密：
  企业微信消息体为 AES-CBC-256 加密的 XML，使用 pycryptodome 解密。
  解密密钥 = Base64Decode(encoding_aes_key + "=")（补充 base64 padding）

API 文档参考：https://developer.work.weixin.qq.com/document
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import struct
import time
import xml.etree.ElementTree as ET
from typing import Any

import httpx
import structlog

from app.services.im_adapter import IMAdapter, IMIncomingMessage, IMOutgoingMessage

logger = structlog.get_logger(__name__)

# 企业微信消息长度限制
WECOM_MAX_LENGTH = 2048
_TRUNCATE_SUFFIX = "\n\n[消息已截断，完整结果请在 Prism Web 端查看]"

# 企业微信 API 基础 URL
WECOM_API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"


class WeComAdapter(IMAdapter):
    """
    企业微信 IM 适配器。

    实现 IMAdapter 接口，通过 Webhook 回调接收消息（需 msg_signature 验证），
    通过企业微信消息 API 发送应用消息。

    使用方式（由 IMGateway 管理）：
        adapter = WeComAdapter(config)
        gateway.register_adapter(adapter)
        # 企业微信消息通过 POST /im/webhook/wecom → handle_webhook() 路由进来
        # 企业微信 URL 验证通过 GET /im/webhook/wecom → verify_url() 路由
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """
        Args:
            config: im_channel_configs.config JSONB，包含 corp_id / agent_id /
                    secret / token / encoding_aes_key
        """
        super().__init__()
        self._config = config
        self._corp_id: str = config.get("corp_id", "")
        self._agent_id: str = str(config.get("agent_id", ""))
        self._secret: str = config.get("secret", "")
        self._token: str = config.get("token", "")
        self._encoding_aes_key: str = config.get("encoding_aes_key", "")

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
        return "wecom"

    def is_configured(self) -> bool:
        return bool(self._corp_id and self._token and self._encoding_aes_key)

    async def start(self) -> None:
        """
        启动企业微信适配器。

        Webhook 模式下 start() 只需预热 token 并标记已就绪。
        实际消息接收由 FastAPI Webhook 端点驱动（push 模式）。
        """
        if not self._corp_id or not self._secret:
            logger.warning(
                "wecom.adapter.start_skipped",
                reason="corp_id or secret not configured",
            )
            return

        self._running = True
        try:
            await self._ensure_token()
            logger.info("wecom.adapter.started", corp_id=self._corp_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("wecom.adapter.token_preheat_failed", error=str(exc))

    async def stop(self) -> None:
        """停止适配器（幂等）。"""
        self._running = False
        self._access_token = ""
        self._token_expires_at = 0.0
        logger.info("wecom.adapter.stopped")

    async def send(self, message: IMOutgoingMessage) -> bool:
        """
        通过企业微信应用消息 API 发送消息。

        POST https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token=...

        Args:
            message: 待发送消息（platform_chat_id 为企业微信 openid / userid）

        Returns:
            True — 发送成功；False — 发送失败（已 log error，不抛异常）

        发送策略：
          - platform_chat_id 以 "@" 开头，视为 userid（单人推送）
          - 其他情况视为 party_id（部门推送）或整体推送到 toall
        """
        text = message.text
        if len(text) > WECOM_MAX_LENGTH:
            text = text[: WECOM_MAX_LENGTH - len(_TRUNCATE_SUFFIX)] + _TRUNCATE_SUFFIX

        try:
            token = await self._ensure_token()
            url = f"{WECOM_API_BASE}/message/send"

            # 判断消息类型：touser（个人）或 toparty（部门）
            chat_id = message.platform_chat_id
            if chat_id.startswith("party:"):
                to_user = ""
                to_party = chat_id[len("party:"):]
            else:
                to_user = chat_id
                to_party = ""

            payload: dict[str, Any] = {
                "agentid": int(self._agent_id) if self._agent_id.isdigit() else self._agent_id,
                "msgtype": "text",
                "text": {"content": text},
            }
            if to_user:
                payload["touser"] = to_user
            if to_party:
                payload["toparty"] = to_party
            if not to_user and not to_party:
                payload["toall"] = 1

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url,
                    params={"access_token": token},
                    json=payload,
                )

            data = resp.json()
            if data.get("errcode") != 0:
                logger.error(
                    "wecom.send.api_error",
                    chat_id=chat_id,
                    errcode=data.get("errcode"),
                    errmsg=data.get("errmsg"),
                )
                return False

            logger.info(
                "wecom.send.success",
                chat_id=chat_id,
                text_len=len(text),
            )
            return True

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "wecom.send.exception",
                chat_id=message.platform_chat_id,
                error=str(exc),
            )
            return False

    # ------------------------------------------------------------------
    # Webhook handling (called by api/v1/im.py)
    # ------------------------------------------------------------------

    def verify_signature(
        self,
        msg_signature: str,
        timestamp: str,
        nonce: str,
        encrypt: str = "",
    ) -> bool:
        """
        验证企业微信消息签名。

        签名算法：
          sort([token, timestamp, nonce, encrypt]) → 拼接 → SHA1 → hexdigest
          结果必须等于 msg_signature。

        若 token 未配置，跳过校验（返回 True，仅适合内网部署）。

        参考：https://developer.work.weixin.qq.com/document/path/90968
        """
        if not self._token or not self._encoding_aes_key:
            return False

        parts = sorted([self._token, timestamp, nonce, encrypt])
        s = "".join(parts)
        expected = hashlib.sha1(s.encode("utf-8")).hexdigest()
        return expected == msg_signature

    def verify_url(
        self,
        msg_signature: str,
        timestamp: str,
        nonce: str,
        echostr: str,
    ) -> str:
        """
        企业微信 URL 验证（GET 请求）。

        流程：
          1. 验证 msg_signature = SHA1(sort(token, timestamp, nonce, echostr))
          2. 解密 echostr（AES-CBC-256）
          3. 返回解密后的明文（企业微信要求响应此值）

        若签名验证失败，返回空字符串。
        """
        if not self.verify_signature(msg_signature, timestamp, nonce, echostr):
            logger.warning("wecom.verify_url.signature_mismatch")
            return ""

        try:
            decrypted = self._decrypt_aes(echostr)
            # 解密结果结构：random(16) + msg_len(4) + msg + corp_id
            # 取出 msg 部分
            msg_len = struct.unpack(">I", decrypted[16:20])[0]
            msg = decrypted[20 : 20 + msg_len].decode("utf-8")
            return msg
        except Exception as exc:  # noqa: BLE001
            logger.error("wecom.verify_url.decrypt_failed", error=str(exc))
            return ""

    async def handle_webhook(
        self,
        body_bytes: bytes,
        msg_signature: str,
        timestamp: str,
        nonce: str,
    ) -> str:
        """
        处理企业微信 POST Webhook 事件。

        Args:
            body_bytes: 原始 POST body（XML 格式）
            msg_signature, timestamp, nonce: URL 查询参数（用于签名验证）

        Returns:
            "success" — 处理成功（企业微信要求的响应字符串）
        """
        body_str = body_bytes.decode("utf-8")

        # 解析外层 XML（加密消息）
        try:
            root = ET.fromstring(body_str)
        except ET.ParseError as exc:
            logger.error("wecom.webhook.xml_parse_failed", error=str(exc))
            return "success"

        encrypt_elem = root.find("Encrypt")
        if encrypt_elem is None or not encrypt_elem.text:
            logger.warning("wecom.webhook.no_encrypt_field")
            return "success"

        encrypted_msg = encrypt_elem.text.strip()

        # 验证签名
        if not self.verify_signature(msg_signature, timestamp, nonce, encrypted_msg):
            logger.warning(
                "wecom.webhook.signature_mismatch",
                timestamp=timestamp,
                nonce=nonce,
            )
            return "success"  # 仍返回 success 避免平台重试风暴

        # 解密消息
        try:
            decrypted = self._decrypt_aes(encrypted_msg)
            msg_len = struct.unpack(">I", decrypted[16:20])[0]
            msg_xml = decrypted[20 : 20 + msg_len].decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.error("wecom.webhook.decrypt_failed", error=str(exc))
            return "success"

        # 解析消息 XML
        try:
            msg_root = ET.fromstring(msg_xml)
        except ET.ParseError as exc:
            logger.error("wecom.webhook.msg_xml_parse_failed", error=str(exc))
            return "success"

        await self._process_message_xml(msg_root, msg_xml)
        return "success"

    async def _process_message_xml(
        self,
        root: ET.Element,
        raw_xml: str,
    ) -> None:
        """
        解析企业微信消息 XML，转换为 IMIncomingMessage 并回调 handler。

        企业微信消息字段：
          <MsgType>text</MsgType>
          <Content>消息内容</Content>
          <FromUserName>发送者 userid</FromUserName>
          <AgentID>应用 AgentID</AgentID>
          <MsgId>消息 ID（整数）</MsgId>
        """
        msg_type = _xml_text(root, "MsgType", "")
        if msg_type != "text":
            logger.debug("wecom.message.ignored_type", msg_type=msg_type)
            return

        from_user = _xml_text(root, "FromUserName", "")
        content = _xml_text(root, "Content", "").strip()
        msg_id = _xml_text(root, "MsgId", "")

        if not from_user or not content or not msg_id:
            logger.warning(
                "wecom.message.invalid",
                from_user=from_user,
                has_content=bool(content),
                msg_id=msg_id,
            )
            return

        incoming = IMIncomingMessage(
            channel=self.channel_name,
            platform_user_id=from_user,
            platform_chat_id=from_user,  # 企业微信单聊 chat_id = from_user
            text=content,
            msg_id=msg_id,
            raw={"xml": raw_xml},
        )

        if self._message_handler:
            try:
                await self._message_handler(incoming)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "wecom.message.handler_error",
                    msg_id=msg_id,
                    error=str(exc),
                )

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def _ensure_token(self) -> str:
        """
        获取（或刷新）企业微信 access_token。

        Token 在过期前 60 秒自动刷新。
        并发安全：使用 asyncio.Lock。

        参考：https://developer.work.weixin.qq.com/document/path/91039
        """
        async with self._token_lock:
            now = time.time()
            if self._access_token and now < self._token_expires_at - 60:
                return self._access_token

            url = f"{WECOM_API_BASE}/gettoken"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    url,
                    params={
                        "corpid": self._corp_id,
                        "corpsecret": self._secret,
                    },
                )
            data = resp.json()
            if data.get("errcode") != 0:
                raise RuntimeError(
                    f"WeCom token fetch failed: errcode={data.get('errcode')}, "
                    f"errmsg={data.get('errmsg')}"
                )

            self._access_token = data["access_token"]
            self._token_expires_at = now + int(data.get("expires_in", 7200))
            logger.info(
                "wecom.token.refreshed",
                expires_in=data.get("expires_in", 7200),
            )
            return self._access_token

    # ------------------------------------------------------------------
    # AES decryption (企业微信消息加解密)
    # ------------------------------------------------------------------

    def _decrypt_aes(self, encrypted_b64: str) -> bytes:
        """
        AES-CBC-256 解密企业微信加密消息。

        解密密钥 = Base64Decode(encoding_aes_key + "=")（补 padding）。
        IV = key[:16]（密钥前 16 字节）。

        依赖 pycryptodome（需在 requirements.txt 中声明）。

        参考：https://developer.work.weixin.qq.com/document/path/90968
        """
        try:
            from Crypto.Cipher import AES  # pycryptodome
        except ImportError as exc:
            raise RuntimeError(
                "pycryptodome is required for WeCom message decryption. "
                "Add 'pycryptodome>=3.20.0' to requirements.txt."
            ) from exc

        if not self._encoding_aes_key:
            raise ValueError("encoding_aes_key not configured")

        # 企业微信 AES key = Base64Decode(encoding_aes_key + "=")
        aes_key = base64.b64decode(self._encoding_aes_key + "=")
        # IV = key 前 16 字节
        iv = aes_key[:16]

        ciphertext = base64.b64decode(encrypted_b64)
        cipher = AES.new(aes_key, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(ciphertext)

        # 去除 PKCS7 padding
        pad_len = decrypted[-1]
        return decrypted[:-pad_len]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _xml_text(root: ET.Element, tag: str, default: str = "") -> str:
    """从 XML 元素中提取指定标签的文本内容（安全版本）。"""
    elem = root.find(tag)
    if elem is None or elem.text is None:
        return default
    return elem.text
