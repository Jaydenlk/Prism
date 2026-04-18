"""
Prism v2 — Provider API 端点 (DOC-02 Task 2.3)

路由表 (DOC-01 v4 §6.6):
  GET    /api/v1/providers/presets         — 公开,无需认证
  GET    /api/v1/providers                 — 列出 scope='system' + 本人的 scope='user'
  POST   /api/v1/providers                 — 创建,config.capabilities 必填
  PUT    /api/v1/providers/{id}            — 更新,scope='user' 仅限 owner;scope='system' require_admin
  DELETE /api/v1/providers/{id}            — 删除,权限同上
  POST   /api/v1/providers/{id}/test       — 探测连通性 + detected_capabilities

ADR-010: scope 权限矩阵
ADR-011: config.capabilities 必填,缺失 422
ADR-012: api_key 响应中永远返回掩码版本
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_db, require_admin
from app.models.provider import Provider
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.provider import (
    CreateProviderRequest,
    ProviderPreset,
    ProviderResponse,
    TestProviderResponse,
    UpdateProviderRequest,
)
from app.services.provider_service import ProviderService

router = APIRouter(prefix="/providers", tags=["providers"])


# ---------------------------------------------------------------------------
# GET /providers/presets — 公开端点,无需认证
# ---------------------------------------------------------------------------

@router.get(
    "/presets",
    response_model=ApiResponse[list[ProviderPreset]],
    summary="获取内置 Provider 预设列表",
    description="返回所有内置 Provider 预设(厂商、模型、能力声明)。无需认证，可公开访问。",
)
async def list_presets() -> ApiResponse[list[ProviderPreset]]:
    """返回内置 Provider 预设列表 (ADR-011: 每个预设带 capabilities 声明)."""
    presets = ProviderService.get_presets()
    return ApiResponse(data=presets)


# ---------------------------------------------------------------------------
# GET /providers — 列出可见的 Provider
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=ApiResponse[list[ProviderResponse]],
    summary="列出可见的 Provider",
    description="返回 scope='system' 的全局预设 + 当前用户的 scope='user' Provider。需要认证。",
)
async def list_providers(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[ProviderResponse]]:
    """ADR-010: 列出 scope='system' OR (scope='user' AND user_id=current)."""
    providers = ProviderService.list_providers(db=db, user_id=current_user.id)
    return ApiResponse(data=providers)


# ---------------------------------------------------------------------------
# POST /providers — 创建 Provider
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=ApiResponse[ProviderResponse],
    status_code=status.HTTP_201_CREATED,
    summary="创建 Provider",
    description=(
        "创建用户私有 Provider (scope='user')。"
        "config.capabilities 为必填字段，缺失时返回 422。"
        "API Key 使用 AES-256-GCM 加密存储，响应中只返回掩码。"
    ),
)
async def create_provider(
    data: CreateProviderRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[ProviderResponse]:
    """ADR-011: config.capabilities 已在 Pydantic 层校验。ADR-012: API Key 加密。"""
    provider = ProviderService.create_provider(db=db, user_id=current_user.id, data=data)
    return ApiResponse(data=provider)


# ---------------------------------------------------------------------------
# PUT /providers/{id} — 更新 Provider
# ---------------------------------------------------------------------------

@router.put(
    "/{provider_id}",
    response_model=ApiResponse[ProviderResponse],
    summary="更新 Provider",
    description=(
        "更新 Provider 信息。"
        "scope='user' 只能由 owner 修改；scope='system' 需要 admin 权限。"
    ),
)
async def update_provider(
    provider_id: str,
    data: UpdateProviderRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[ProviderResponse]:
    """ADR-010: 权限矩阵 — user scope 需 owner,system scope 需 admin."""
    is_admin = (current_user.role == "admin")
    provider = ProviderService.update_provider(
        db=db,
        user_id=current_user.id,
        provider_id=provider_id,
        data=data,
        is_admin=is_admin,
    )
    return ApiResponse(data=provider)


# ---------------------------------------------------------------------------
# DELETE /providers/{id} — 删除 Provider
# ---------------------------------------------------------------------------

@router.delete(
    "/{provider_id}",
    response_model=ApiResponse[dict],
    summary="删除 Provider",
    description=(
        "删除 Provider。"
        "scope='user' 只能由 owner 删除；scope='system' 需要 admin 权限。"
    ),
)
async def delete_provider(
    provider_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    """ADR-010: 权限矩阵 — user scope 需 owner,system scope 需 admin."""
    is_admin = (current_user.role == "admin")
    ProviderService.delete_provider(
        db=db,
        user_id=current_user.id,
        provider_id=provider_id,
        is_admin=is_admin,
    )
    return ApiResponse(data={"deleted": provider_id})


# ---------------------------------------------------------------------------
# POST /providers/{id}/test — 连通性 + 能力探测
# ---------------------------------------------------------------------------

@router.post(
    "/{provider_id}/test",
    response_model=ApiResponse[TestProviderResponse],
    summary="探测 Provider 连通性与能力",
    description=(
        "向 Provider 发送最小测试请求，检测连通性和能力支持情况。"
        "返回 detected_capabilities 供用户确认是否与声明一致。"
        "需要认证；API Key 在 Backend 侧解密后用于探测，不会暴露给调用方。"
    ),
)
async def test_provider(
    provider_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[TestProviderResponse]:
    """ADR-011: 探测 capabilities。ADR-012: 解密在 Backend 侧，明文不出 Backend。"""
    result = await ProviderService.test_provider(
        db=db,
        user_id=current_user.id,
        provider_id=provider_id,
    )
    return ApiResponse(data=result)
