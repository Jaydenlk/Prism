"""
Prism v2 — IM API 端点 (DOC-08 Task 8.1 skeleton / Task 8.2 Webhook 实现)

路由表：
  GET    /im/channels              — 已配置的 IM 渠道列表（admin only）
  PATCH  /im/channels/{channel}    — 更新渠道配置（admin only）

Webhook 端点（Task 8.2 实现，企微/飞书平台直接回调，public + 平台签名验证）：
  POST   /im/webhook/feishu        — 飞书事件回调
  POST   /im/webhook/wecom         — 企业微信事件回调

设计要点：
  - Webhook 端点 public（IM 平台直接调用），用平台签名替代 JWT
  - 渠道 config 管理需要 admin 权限（包含 app_secret 等密钥）
  - GET /im/channels 不返回 config JSONB 的 secret 字段（脱敏）
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_db, require_admin
from app.models.im import ImBinding, ImChannelConfig
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.im import (
    IMBindingResponse,
    IMChannelConfigResponse,
    IMChannelConfigUpdate,
    PairingCodeResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/im", tags=["im"])

# ---------------------------------------------------------------------------
# Channel config management (admin only)
# ---------------------------------------------------------------------------

@router.get(
    "/channels",
    response_model=ApiResponse[list[IMChannelConfigResponse]],
    summary="列出所有 IM 渠道配置（admin only）",
)
def list_channels(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ApiResponse[list[IMChannelConfigResponse]]:
    """列出 im_channel_configs 中所有渠道配置（config 字段脱敏）。"""
    rows = db.query(ImChannelConfig).order_by(ImChannelConfig.channel).all()
    result = []
    for row in rows:
        # 脱敏：移除 secret / token / key 类字段
        safe_config = _redact_secrets(row.config)
        result.append(
            IMChannelConfigResponse(
                id=row.id,
                channel=row.channel,
                is_enabled=row.is_enabled,
                config=safe_config,
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
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ApiResponse[IMChannelConfigResponse]:
    """
    更新 im_channel_configs 中指定渠道的 is_enabled / config。

    不存在则自动创建（upsert 语义）。
    config 字段为 JSONB，传入值与现有值合并（partial update）。
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
        # Merge: 保留现有字段，覆盖传入字段
        merged = dict(row.config or {})
        merged.update(data.config)
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


# ---------------------------------------------------------------------------
# Webhook endpoints (public, platform signature verification)
# Task 8.2 will add FeishuAdapter / WeComAdapter routing logic here.
# Task 8.1 provides the skeleton with 200 OK stubs.
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
    飞书 Webhook / Event Callback 入口。

    Task 8.1 skeleton：立即返回 {"challenge": ...} 用于 URL 验证；
    真实事件处理由 Task 8.2 FeishuAdapter 实现并注入 IMGateway。

    飞书 URL 验证流程：
      POST body 包含 {"challenge": "xxx", "type": "url_verification"}
      → 响应 {"challenge": "xxx"}
    """
    body: dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        pass

    # URL verification challenge (飞书要求)
    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge", "")}

    # TODO-Task8.2: 验证 X-Lark-Signature，解析事件，调用 IMGateway._handle_message()
    logger.info(
        "im.webhook.feishu.received",
        event_type=body.get("header", {}).get("event_type", "unknown"),
    )
    return {"status": "ok"}


@router.post(
    "/webhook/wecom",
    include_in_schema=False,
    summary="企业微信事件回调（企微平台直接调用）",
)
async def webhook_wecom(
    request: Request,
) -> Any:
    """
    企业微信 Webhook / Callback 入口。

    Task 8.1 skeleton：返回 "success" 字符串（企微要求）。
    真实事件处理由 Task 8.2 WeComAdapter 实现并注入 IMGateway。

    企微 URL 验证流程（GET 请求）：
      msg_signature / timestamp / nonce / echostr → 返回 echostr 解密值
    """
    # TODO-Task8.2: 验证 msg_signature，解密消息，调用 IMGateway._handle_message()
    logger.info("im.webhook.wecom.received")
    return "success"


# ---------------------------------------------------------------------------
# User binding endpoints (authenticated)
# Full implementation in Task 8.3; stubs here for Task 8.1 completeness.
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
    bindings = (
        db.query(ImBinding)
        .filter(ImBinding.user_id == user.id)
        .order_by(ImBinding.created_at.desc())
        .all()
    )
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
    生成配对码（Task 8.3 IMBindingService 将提供完整实现）。

    Task 8.1 skeleton：直接在此路由中实现基础逻辑，供后续 Task 8.3 重构。

    流程：
      1. 若已有未完成绑定记录 → 覆盖旧配对码
      2. 创建/更新 im_bindings 记录（platform_user_id 暂为空字符串）
      3. 返回配对码 + 过期时间
    """
    import secrets
    from datetime import timedelta

    VALID_CHANNELS = {"feishu", "wecom", "telegram"}
    if channel not in VALID_CHANNELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid channel. Must be one of: {', '.join(VALID_CHANNELS)}",
        )

    # 生成 6 位数字配对码（碰撞重试最多 3 次）
    code: str = ""
    for _ in range(3):
        candidate = "".join(str(secrets.randbelow(10)) for _ in range(6))
        # 检查是否存在相同有效码
        conflict = (
            db.query(ImBinding)
            .filter(
                ImBinding.channel == channel,
                ImBinding.pairing_code == candidate,
                ImBinding.paired_at.is_(None),
            )
            .first()
        )
        if conflict is None:
            code = candidate
            break
    if not code:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate unique pairing code. Please retry.",
        )

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=5)

    # 查找当前用户在该渠道的未完成绑定记录
    existing = (
        db.query(ImBinding)
        .filter(
            ImBinding.user_id == user.id,
            ImBinding.channel == channel,
            ImBinding.paired_at.is_(None),
        )
        .first()
    )

    if existing:
        existing.pairing_code = code
        existing.created_at = now  # 重置过期时间
    else:
        binding = ImBinding(
            user_id=user.id,
            channel=channel,
            platform_user_id="",  # 由 IM 端配对时填入
            platform_chat_id="",  # 由 IM 端配对时填入
            pairing_code=code,
            created_at=now,
        )
        db.add(binding)

    db.commit()

    logger.info(
        "im.binding.pairing_code_generated",
        user_id=user.id,
        channel=channel,
    )

    return ApiResponse(
        data=PairingCodeResponse(
            pairing_code=code,
            channel=channel,
            expires_at=expires_at,
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
    binding = db.get(ImBinding, binding_id)
    if binding is None or binding.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Binding {binding_id} not found.",
        )
    db.delete(binding)
    db.commit()

    logger.info(
        "im.binding.unpaired",
        binding_id=binding_id,
        user_id=user.id,
        channel=binding.channel,
    )


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
