"""
Prism v2 — IM API 端点 (DOC-08 Task 8.1 / 8.2 / 8.3)

路由表：
  GET    /im/channels              — 已配置的 IM 渠道列表（admin only）
  PATCH  /im/channels/{channel}    — 更新渠道配置（admin only）

Webhook 端点（Task 8.2 实现，企微/飞书平台直接回调，public + 平台签名验证）：
  POST   /im/webhook/feishu        — 飞书事件回调（含 URL 验证 + 签名校验）
  GET    /im/webhook/wecom         — 企业微信 URL 验证（返回 echostr 解密值）
  POST   /im/webhook/wecom         — 企业微信事件回调（含签名验证 + XML 解密）

绑定端点（Task 8.3 IMBindingService 实现）：
  GET    /im/bindings              — 当前用户的 IM 绑定列表
  POST   /im/bindings/pair         — 生成配对码（6 位，5 分钟有效）
  DELETE /im/bindings/{binding_id} — 解除绑定（物理删除）

设计要点：
  - Webhook 端点 public（IM 平台直接调用），用平台签名替代 JWT
  - 渠道 config 管理需要 admin 权限（包含 app_secret 等密钥）
  - GET /im/channels 不返回 config JSONB 的 secret 字段（脱敏）
  - 适配器实例从 app.state.im_gateway 懒获取（由 lifespan 注入）
  - 绑定逻辑全部委托给 IMBindingService（Task 8.3 重构）
"""
from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_db, require_admin
from app.models.im import ImChannelConfig
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.im import (
    IMBindingResponse,
    IMChannelConfigResponse,
    IMChannelConfigUpdate,
    PairingCodeResponse,
    TestSendRequest,
)
from app.services.credential_cipher import encrypt_config_secrets
from app.services.im_adapter import IMCardAction, IMOutgoingCard
from app.services.im_binding_service import IMBindingService
from app.services.im_feishu import FeishuAdapter

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/im", tags=["im"])

# ---------------------------------------------------------------------------
# Channel config management (admin only)
# ---------------------------------------------------------------------------

#: 已知 IM 渠道枚举（DOC-IM2 ADR-088 扩展到 slack + discord）
_KNOWN_CHANNELS = ("feishu", "wecom", "slack", "discord", "telegram")


@router.get(
    "/channels",
    response_model=ApiResponse[list[IMChannelConfigResponse]],
    summary="列出所有 IM 渠道配置（admin only）",
)
def list_channels(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ApiResponse[list[IMChannelConfigResponse]]:
    """列出所有已知 IM 渠道配置(config 字段脱敏)。

    DB 已有行直接返回;_KNOWN_CHANNELS 中尚未写入 im_channel_configs 的渠道
    返回占位行(is_enabled=False, config={}),以便 Admin UI 始终展示完整列表。
    """
    rows = db.query(ImChannelConfig).order_by(ImChannelConfig.channel).all()
    by_channel = {row.channel: row for row in rows}

    result: list[IMChannelConfigResponse] = []
    for channel in _KNOWN_CHANNELS:
        row = by_channel.get(channel)
        if row is None:
            result.append(
                IMChannelConfigResponse(
                    id="",
                    channel=channel,
                    is_enabled=False,
                    config={},
                    created_at=None,
                    updated_at=None,
                )
            )
        else:
            result.append(
                IMChannelConfigResponse(
                    id=row.id,
                    channel=row.channel,
                    is_enabled=row.is_enabled,
                    config=_redact_secrets(row.config),
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
            )
    return ApiResponse(data=result)


@router.patch(
    "/channels/{channel}",
    response_model=ApiResponse[IMChannelConfigResponse],
    summary="更新渠道配置（admin only）",
)
def update_channel(
    channel: str,
    data: IMChannelConfigUpdate,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ApiResponse[IMChannelConfigResponse]:
    """
    更新 im_channel_configs 中指定渠道的 is_enabled / config。

    不存在则自动创建（upsert 语义）。
    config 字段为 JSONB，传入值与现有值合并（partial update）。

    ADR-088 Session 4b (I4):写入前对 key 包含 secret/token/key/password 的
    字符串 value 自动 Fernet 加密(前缀 ``fernet:``);GET 路径仍脱敏,
    Adapter 重启后从 DB 读时自动解密。
    """
    row = db.query(ImChannelConfig).filter(ImChannelConfig.channel == channel).first()

    if row is None:
        row = ImChannelConfig(
            channel=channel,
            is_enabled=False,
            config={},
        )
        db.add(row)

    if data.is_enabled is not None:
        row.is_enabled = data.is_enabled
    if data.config is not None:
        cipher = getattr(request.app.state, "credential_cipher", None)
        new_config = encrypt_config_secrets(data.config, cipher) if cipher else dict(data.config)
        merged = dict(row.config or {})
        merged.update(new_config)
        row.config = merged

    db.commit()
    db.refresh(row)

    logger.info(
        "im.channel.updated",
        channel=channel,
        is_enabled=row.is_enabled,
        admin_id=admin.id,
    )

    return ApiResponse(
        data=IMChannelConfigResponse(
            id=row.id,
            channel=row.channel,
            is_enabled=row.is_enabled,
            config=_redact_secrets(row.config),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
    )


@router.post(
    "/channels/{channel}/test-send",
    response_model=ApiResponse[dict],
    summary="向 IM 渠道发送一张测试卡片(admin only, ADR-088 Session 4b)",
)
async def test_send_channel(
    channel: str,
    body: TestSendRequest,
    request: Request,
    admin: User = Depends(require_admin),
) -> ApiResponse[dict]:
    """向指定 IM 渠道发送一张硬编码测试卡片,用于 Admin UI 配置验证。

    Response:
      - 200 + {sent:true,channel}   — adapter 已配置且 send_card 成功
      - 200 + {sent:false,channel}  — adapter 已配置但平台 API 返错误
      - 404                         — 渠道未注册
      - 503                         — 渠道未配置(需先 PATCH config + 重启 adapter)
      - 502                         — send_card 抛异常
    """
    gw = getattr(request.app.state, "im_gateway", None)
    adapter = gw.get_adapter(channel) if gw else None
    if adapter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"channel '{channel}' adapter not found",
        )
    if not adapter.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"channel '{channel}' not configured",
        )

    card = IMOutgoingCard(
        channel=channel,
        platform_chat_id=body.target_chat_id,
        title=body.title or "Prism 测试卡片",
        body_markdown=body.body or "这是一张由 Prism admin 发送的测试互动卡片。\n您可以点击下方按钮测试 action 回传。",
        actions=[IMCardAction(label="确认", action_id="test_confirm", style="primary")],
    )
    try:
        sent = await adapter.send_card(card)
    except NotImplementedError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"channel '{channel}' adapter does not support send_card",
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("im.test_send.exception", channel=channel, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"send failed: {exc}",
        )

    logger.info("im.test_send.result", channel=channel, sent=sent, admin_id=admin.id)
    return ApiResponse(data={"sent": bool(sent), "channel": channel})


# ---------------------------------------------------------------------------
# Webhook endpoints (public, platform signature verification)
# Task 8.2: FeishuAdapter + WeComAdapter real implementations.
# ---------------------------------------------------------------------------

@router.post(
    "/webhook/feishu",
    include_in_schema=False,  # public endpoint, excluded from OpenAPI auth docs
    summary="飞书事件回调（飞书平台直接调用）",
)
async def webhook_feishu(
    request: Request,
) -> dict[str, Any]:
    """
    飞书 Webhook / Event Callback 入口（Task 8.2 完整实现）。

    安全流程：
      1. 读取 body bytes（用于签名验证）
      2. 若 X-Lark-Signature 存在，验证签名（HMAC-SHA256）
      3. 若 encrypt 字段存在，解密消息（AES-CBC-256）
      4. URL 验证：响应 {"challenge": "..."}
      5. 真实事件：交由 FeishuAdapter.handle_webhook() 处理并路由到 IMGateway

    飞书 URL 验证流程：
      POST body 包含 {"challenge": "xxx", "type": "url_verification"}
      → 响应 {"challenge": "xxx"}
    """
    body_bytes = await request.body()

    # --- Parse body first (needed for URL verification fast path) ---
    try:
        import json as _json
        body: dict[str, Any] = _json.loads(body_bytes) if body_bytes else {}
    except Exception:
        body = {}

    # --- Fast path: URL verification challenge (Feishu initial setup) ---
    # Must be handled before 503/401 checks — Feishu sends this with no
    # signature and before any app_id is necessarily configured.
    if body.get("type") == "url_verification":
        challenge = body.get("challenge", "")
        logger.info("im.webhook.feishu.url_verification_fast_path")
        return {"challenge": challenge}

    # --- Check adapter is present and configured ---
    adapter: FeishuAdapter | None = _get_feishu_adapter(request)
    if adapter is None or not adapter.is_configured():
        logger.warning(
            "im.webhook.feishu.not_configured",
            has_adapter=adapter is not None,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Feishu bot not configured. Set FEISHU_APP_ID and FEISHU_APP_SECRET.",
        )

    # --- Signature verification (X-Lark-Signature present) ---
    signature = request.headers.get("X-Lark-Signature", "")
    timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
    nonce = request.headers.get("X-Lark-Request-Nonce", "")

    if signature:
        if not adapter.verify_signature(timestamp, nonce, body_bytes, signature):
            logger.warning(
                "im.webhook.feishu.signature_mismatch",
                timestamp=timestamp,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Feishu webhook signature.",
            )

    result = await adapter.handle_webhook(body)
    logger.info(
        "im.webhook.feishu.processed",
        event_type=body.get("header", {}).get("event_type", body.get("type", "unknown")),
    )
    return result


# ---------------------------------------------------------------------------
# Slack Events API webhook (DOC-IM2 I2, ADR-088)
# ---------------------------------------------------------------------------

@router.post(
    "/webhook/slack",
    include_in_schema=False,
    summary="Slack Events API 回调",
)
async def webhook_slack(request: Request) -> dict[str, Any]:
    """
    Slack Events API 入口。

    Flow(https://docs.slack.dev/apis/events-api/):
      1. 读取 body bytes(签名覆盖原始 body)
      2. Fast path:url_verification → {"challenge": "..."}
      3. 检查 adapter 已配置 + 签名通过(HMAC-SHA256 v0 + 5min 窗口)
      4. 委托给 SlackAdapter.parse_event → IMGateway._handle_message
      5. 3s ACK budget:立即返回 {"ok": True},重任务 defer 到后台(v1 简化:同步处理,未来接 TaskService)
    """
    body_bytes = await request.body()

    from app.services.im_slack import SlackAdapter
    gw = getattr(request.app.state, "im_gateway", None)
    adapter = gw.get_adapter("slack") if gw else None
    if not isinstance(adapter, SlackAdapter):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Slack adapter not initialized.",
        )

    # Fast path: URL verification (Slack initial config).
    challenge = SlackAdapter.build_url_verification_response(body_bytes)
    if challenge is not None:
        logger.info("im.webhook.slack.url_verification")
        return challenge

    if not adapter.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Slack bot not configured.",
        )

    if not adapter.verify_signature(dict(request.headers), body_bytes):
        logger.warning("im.webhook.slack.signature_mismatch")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Slack webhook signature.",
        )

    incoming = await adapter.parse_event(body_bytes)
    if incoming is not None:
        # Route via the gateway's message handler (set in register_adapter).
        if adapter._message_handler is not None:
            try:
                await adapter._message_handler(incoming)
            except Exception as exc:  # noqa: BLE001
                logger.error("im.webhook.slack.handler_error", error=str(exc))

    return {"ok": True}


# ---------------------------------------------------------------------------
# Discord HTTP Interactions webhook (DOC-IM2 I3, ADR-088)
# ---------------------------------------------------------------------------

@router.post(
    "/webhook/discord",
    include_in_schema=False,
    summary="Discord Interactions 回调",
)
async def webhook_discord(request: Request) -> dict[str, Any]:
    """Discord HTTP Interactions 入口。

    Discord 会主动 probe 坏签名,**必须** 在 signature 校验失败时返回 401
    (non-2xx)而非 200。PING(type=1)回 PONG(type=1)。
    """
    body_bytes = await request.body()

    from app.services.im_discord import DiscordAdapter
    gw = getattr(request.app.state, "im_gateway", None)
    adapter = gw.get_adapter("discord") if gw else None
    if not isinstance(adapter, DiscordAdapter):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Discord adapter not initialized.",
        )

    if not adapter.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Discord adapter not configured.",
        )

    # Signature check BEFORE parsing — Discord probes bad sigs.
    if not adapter.verify_signature(dict(request.headers), body_bytes):
        logger.warning("im.webhook.discord.signature_mismatch")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Discord webhook signature.",
        )

    import json as _json
    try:
        parsed = _json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
    except Exception:
        parsed = {}

    pong = DiscordAdapter.build_ping_response(parsed)
    if pong is not None:
        logger.info("im.webhook.discord.ping_pong")
        return pong

    incoming = await adapter.parse_event(body_bytes)
    if incoming is not None and adapter._message_handler is not None:
        try:
            await adapter._message_handler(incoming)
        except Exception as exc:  # noqa: BLE001
            logger.error("im.webhook.discord.handler_error", error=str(exc))

    # Defer/empty ACK for a handled interaction (type 5 = DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE)
    return {"type": 5}


@router.get(
    "/webhook/wecom",
    include_in_schema=False,
    summary="企业微信 URL 验证（GET 请求）",
)
async def webhook_wecom_verify(
    request: Request,
    msg_signature: str = Query(default=""),
    timestamp: str = Query(default=""),
    nonce: str = Query(default=""),
    echostr: str = Query(default=""),
) -> PlainTextResponse:
    """
    企业微信 URL 验证（GET 请求）。

    企业微信在配置回调 URL 时发送 GET 请求：
      ?msg_signature=xxx&timestamp=xxx&nonce=xxx&echostr=xxx
    → 验证 msg_signature → 解密 echostr → 响应解密后的明文

    若验证失败，返回空字符串（企业微信将提示 URL 不合法）。
    """
    adapter = _get_wecom_adapter(request)
    if adapter is None:
        logger.warning("im.webhook.wecom.adapter_not_found")
        return PlainTextResponse("")

    decrypted = adapter.verify_url(msg_signature, timestamp, nonce, echostr)
    if not decrypted:
        logger.warning(
            "im.webhook.wecom.url_verify_failed",
            timestamp=timestamp,
        )
        return PlainTextResponse("")

    logger.info("im.webhook.wecom.url_verified")
    return PlainTextResponse(decrypted)


@router.post(
    "/webhook/wecom",
    include_in_schema=False,
    summary="企业微信事件回调（企微平台直接调用）",
)
async def webhook_wecom(
    request: Request,
    msg_signature: str = Query(default=""),
    timestamp: str = Query(default=""),
    nonce: str = Query(default=""),
) -> PlainTextResponse:
    """
    企业微信 Webhook / Callback 入口（Task 8.2 完整实现）。

    安全流程：
      1. 读取 body bytes（XML 格式）
      2. 解析外层 XML，提取 <Encrypt> 字段
      3. 验证 msg_signature（SHA1 签名）
      4. 解密消息（AES-CBC-256）
      5. 解析内层 XML，提取消息内容，路由到 IMGateway

    企业微信要求响应 "success" 字符串。
    """
    body_bytes = await request.body()
    adapter = _get_wecom_adapter(request)

    if adapter is None:
        logger.warning("im.webhook.wecom.adapter_not_found")
        return PlainTextResponse("success")

    result = await adapter.handle_webhook(body_bytes, msg_signature, timestamp, nonce)
    logger.info("im.webhook.wecom.processed")
    return PlainTextResponse(result)


# ---------------------------------------------------------------------------
# Adapter helpers (懒获取适配器实例)
# ---------------------------------------------------------------------------

def _get_feishu_adapter(request: Request):
    """
    从 app.state.im_gateway 获取 FeishuAdapter 实例。

    若 IMGateway 未初始化或未注册 feishu 适配器，返回 None。
    """
    try:
        gateway = getattr(request.app.state, "im_gateway", None)
        if gateway is None:
            return None
        return gateway.get_adapter("feishu")
    except Exception:
        return None


def _get_wecom_adapter(request: Request):
    """
    从 app.state.im_gateway 获取 WeComAdapter 实例。

    若 IMGateway 未初始化或未注册 wecom 适配器，返回 None。
    """
    try:
        gateway = getattr(request.app.state, "im_gateway", None)
        if gateway is None:
            return None
        return gateway.get_adapter("wecom")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# User binding endpoints (authenticated)
# Task 8.3: Full implementation via IMBindingService.
# ---------------------------------------------------------------------------

@router.get(
    "/bindings",
    response_model=ApiResponse[list[IMBindingResponse]],
    summary="列出当前用户的 IM 绑定",
)
def list_bindings(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[list[IMBindingResponse]]:
    """列出当前用户所有 IM 绑定记录（含未完成绑定）。"""
    svc = IMBindingService(db)
    bindings = svc.list_bindings(user.id)
    return ApiResponse(
        data=[
            IMBindingResponse(
                id=b.id,
                user_id=b.user_id,
                channel=b.channel,
                platform_user_id=b.platform_user_id,
                platform_chat_id=b.platform_chat_id,
                display_name=b.display_name,
                paired_at=b.paired_at,
                created_at=b.created_at,
            )
            for b in bindings
        ]
    )


@router.post(
    "/bindings/pair",
    response_model=ApiResponse[PairingCodeResponse],
    summary="生成 IM 配对码（6 位，5 分钟有效）",
)
def generate_pairing_code(
    channel: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[PairingCodeResponse]:
    """
    生成配对码（Task 8.3 IMBindingService 实现）。

    流程：
      1. IMBindingService.generate_pairing_code() 处理碰撞重试（最多 3 次）
      2. 若已有未完成绑定记录 → 覆盖旧配对码并重置 created_at
      3. 返回配对码 + 过期时间
    """
    svc = IMBindingService(db)
    try:
        code = svc.generate_pairing_code(user_id=user.id, channel=channel)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    db.commit()

    return ApiResponse(
        data=PairingCodeResponse(
            pairing_code=code,
            channel=channel,
            expires_at=svc.expires_at(),
        )
    )


@router.delete(
    "/bindings/{binding_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="解除 IM 绑定（物理删除）",
)
def unbind(
    binding_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """解除绑定（物理删除）。只能删除属于当前用户的绑定。"""
    svc = IMBindingService(db)
    deleted = svc.unbind(user_id=user.id, binding_id=binding_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Binding {binding_id} not found.",
        )
    db.commit()


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

_SECRET_KEYWORDS = frozenset(
    {"secret", "token", "key", "password", "private", "webhook_secret"}
)


def _redact_secrets(config: dict) -> dict:
    """脱敏 config JSONB：将包含敏感关键词的字段值替换为 '***'。"""
    if not config:
        return {}
    return {
        k: ("***" if any(kw in k.lower() for kw in _SECRET_KEYWORDS) else v)
        for k, v in config.items()
    }
