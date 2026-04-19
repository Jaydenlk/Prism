"""
Prism v2 — Plugin 管理 API（DOC-05 Task 5.7）

路由表（PRD DOC-05 v4 Task 5.7 Part A，DOC-01 v4 §6.x）:
  POST   /api/v1/plugins/load         从目录加载 Plugin（CC 或 Prism 格式，ADR-054）
  POST   /api/v1/plugins/export-cc    将 PluginConfig 导出为 CC 兼容格式（返回 ConversionReport）
  POST   /api/v1/plugins/validate     校验 plugin.yaml schema（ADR-055，缺字段 422）

ADR-054（PRD 原标 ADR-050-A 平移）:
    export_to_cc 返回 ConversionReport（含 cc_compat_zip / lost_fields / warnings /
    cc_plugin_json），而非直接写文件。

ADR-055（PRD 原标 ADR-050-B 平移）:
    plugin.yaml 用 Pydantic schema 严格校验；缺字段返回 HTTP 422 + 详细错误位置；
    未识别字段警告（不拒绝，便于 forward-compat）。

进程边界：
    Backend 不 import Harness 跑业务（CLAUDE.md 六原则第 6 条）。
    插件加载（CCPluginAdapter.load）只做格式检测 + 数据结构转换，不启动子进程。
    实际 MCP 子进程由 Executor 侧 PluginHost 负责（无边界违反）。
"""

from __future__ import annotations

import base64
import os
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_db
from app.models.user import User

logger = structlog.get_logger()
router = APIRouter(prefix="/plugins", tags=["plugins"])


# ---------------------------------------------------------------------------
# Request / Response schema（内联 Pydantic models）
# ---------------------------------------------------------------------------


class PluginLoadRequest(BaseModel):
    """POST /plugins/load 请求体。"""

    plugin_dir: str = Field(
        ...,
        description="插件目录的绝对路径（服务器侧路径）",
        min_length=1,
    )
    session_id: str = Field(default="", description="Session ID（可选，用于变量替换）")


class PluginLoadResponse(BaseModel):
    """POST /plugins/load 响应体。"""

    name: str
    version: str
    description: str
    format: str  # "prism" / "cc" / "skills_only"
    skills_dir: str
    mcp_count: int
    hook_events: list[str]


class ExportCCRequest(BaseModel):
    """POST /plugins/export-cc 请求体（传入 PluginConfig 的关键字段）。"""

    plugin_dir: str = Field(
        ...,
        description="插件目录的绝对路径（从此处加载 PluginConfig 后导出）",
        min_length=1,
    )


class ConversionReportResponse(BaseModel):
    """POST /plugins/export-cc 响应体（与 ConversionReport dataclass 对齐）。"""

    success: bool
    plugin_name: str
    lost_fields: list[str]
    warnings: list[str]
    cc_plugin_json: dict
    cc_compat_zip_b64: str = Field(
        description="CC 兼容格式 zip 的 base64 编码（调用方 decode 后落盘）"
    )


class ValidatePluginRequest(BaseModel):
    """POST /plugins/validate 请求体。"""

    plugin_dir: str = Field(
        ...,
        description="插件目录的绝对路径（校验 plugin.yaml）",
        min_length=1,
    )


class ValidatePluginResponse(BaseModel):
    """POST /plugins/validate 响应体。"""

    valid: bool
    name: str
    version: str
    format: str
    extra_fields: list[str] = Field(
        default_factory=list,
        description="未在 schema 定义的额外字段（forward-compat 告警）",
    )


# ---------------------------------------------------------------------------
# 路由实现
# ---------------------------------------------------------------------------


@router.post(
    "/load",
    response_model=PluginLoadResponse,
    summary="从目录加载 Plugin（自动检测 CC / Prism 格式）",
    description=(
        "检测 plugin_dir 中的插件格式（CC plugin.json / Prism plugin.yaml / "
        "skills_only），转换为 Prism PluginConfig 并返回摘要。\n\n"
        "若 plugin.yaml 缺必填字段，返回 HTTP 422（ADR-055）。\n"
        "若格式无法识别，返回 HTTP 400。\n\n"
        "注：Backend 不启动 MCP 子进程（进程边界约束）；"
        "实际加载由 Executor 侧 PluginHost 完成。"
    ),
)
async def load_plugin(
    body: PluginLoadRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> PluginLoadResponse:
    """检测格式并返回 PluginConfig 摘要（不启动 MCP 子进程）。"""
    from executor.plugins.cc_compat import (
        CCPluginAdapter,
        PluginFormatError,
        PluginSchemaError,
    )

    plugin_dir = body.plugin_dir

    if not os.path.isdir(plugin_dir):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"插件目录不存在或不是目录: {plugin_dir}",
        )

    adapter = CCPluginAdapter()
    fmt = adapter.detect_format(plugin_dir)

    try:
        config = adapter.load(plugin_dir)
    except PluginSchemaError as exc:
        # ADR-055: plugin.yaml 缺必填字段 → HTTP 422
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": str(exc),
                "errors": exc.errors,
            },
        ) from exc
    except PluginFormatError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    logger.info(
        "plugin.api.loaded",
        user_id=str(current_user.id),
        plugin=config.name,
        format=fmt,
    )

    return PluginLoadResponse(
        name=config.name,
        version=config.version,
        description=config.description,
        format=fmt,
        skills_dir=config.skills_dir,
        mcp_count=len(config.mcp_servers),
        hook_events=list(config.hooks_config.keys()),
    )


@router.post(
    "/export-cc",
    response_model=ConversionReportResponse,
    summary="将 Plugin 导出为 CC 兼容格式（返回 ConversionReport）",
    description=(
        "从 plugin_dir 加载 PluginConfig，然后导出为 CC 兼容 zip 格式。\n\n"
        "返回 ConversionReport（ADR-054）：\n"
        "  - cc_compat_zip_b64: CC 格式 zip 的 base64 编码\n"
        "  - lost_fields:       Prism 扩展字段清单（CC 不支持）\n"
        "  - warnings:          转换告警（MCP 名称冲突等）\n"
        "  - cc_plugin_json:    生成的 plugin.json 内容\n\n"
        "双向不对称：Prism→CC 可能不完整（lost_fields 非空时提示人工审查）。"
    ),
)
async def export_to_cc(
    body: ExportCCRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> ConversionReportResponse:
    """将 Plugin 导出为 CC 兼容格式，返回 ConversionReport（ADR-054）。"""
    from executor.plugins.cc_compat import (
        CCPluginAdapter,
        PluginFormatError,
        PluginSchemaError,
    )

    plugin_dir = body.plugin_dir

    if not os.path.isdir(plugin_dir):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"插件目录不存在或不是目录: {plugin_dir}",
        )

    adapter = CCPluginAdapter()

    try:
        config = adapter.load(plugin_dir)
    except PluginSchemaError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "errors": exc.errors},
        ) from exc
    except PluginFormatError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    report = adapter.export_to_cc(config)

    logger.info(
        "plugin.api.exported_cc",
        user_id=str(current_user.id),
        plugin=config.name,
        lost_fields=report.lost_fields,
        warnings=report.warnings,
        zip_size=len(report.cc_compat_zip),
    )

    return ConversionReportResponse(
        success=report.success,
        plugin_name=report.plugin_name,
        lost_fields=report.lost_fields,
        warnings=report.warnings,
        cc_plugin_json=report.cc_plugin_json,
        cc_compat_zip_b64=base64.b64encode(report.cc_compat_zip).decode("ascii"),
    )


@router.post(
    "/validate",
    response_model=ValidatePluginResponse,
    summary="校验 plugin.yaml schema（ADR-055）",
    description=(
        "校验 plugin_dir 中的 plugin.yaml 是否满足 Pydantic schema 约束。\n\n"
        "  - 缺必填字段（name）→ HTTP 422 + 详细错误位置（ADR-055）\n"
        "  - 格式无法识别 → HTTP 400\n"
        "  - 有未识别字段 → 200 OK，extra_fields 列出（forward-compat，不拒绝）\n"
    ),
)
async def validate_plugin(
    body: ValidatePluginRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> ValidatePluginResponse:
    """校验 plugin.yaml schema，返回 valid 状态 + 额外字段告警（ADR-055）。"""
    from executor.plugins.cc_compat import (
        CCPluginAdapter,
        PluginFormatError,
        PluginSchemaError,
        PluginYamlSchema,
    )

    plugin_dir = body.plugin_dir

    if not os.path.isdir(plugin_dir):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"插件目录不存在或不是目录: {plugin_dir}",
        )

    adapter = CCPluginAdapter()
    fmt = adapter.detect_format(plugin_dir)

    if fmt == "unknown":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"插件目录中未找到 plugin.yaml / plugin.json / skills/: {plugin_dir}",
        )

    if fmt != "prism":
        # CC 格式或 skills_only：直接加载即可（无 schema 校验）
        try:
            config = adapter.load(plugin_dir)
        except (PluginFormatError, PluginSchemaError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        return ValidatePluginResponse(
            valid=True,
            name=config.name,
            version=config.version,
            format=fmt,
            extra_fields=[],
        )

    # Prism 格式：执行 Pydantic 校验（ADR-055）
    yaml_path = os.path.join(plugin_dir, "plugin.yaml")
    try:
        raw = CCPluginAdapter._read_yaml(yaml_path)
        schema = CCPluginAdapter._validate_plugin_yaml(raw, yaml_path)
    except PluginSchemaError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "errors": exc.errors},
        ) from exc

    extra_fields = schema.extra_field_names() if hasattr(schema, "extra_field_names") else []

    if extra_fields:
        logger.warning(
            "plugin.api.validate.unknown_fields",
            user_id=str(current_user.id),
            plugin=schema.name,
            extra_fields=extra_fields,
        )

    return ValidatePluginResponse(
        valid=True,
        name=schema.name,
        version=getattr(schema, "version", "1.0.0"),
        format=fmt,
        extra_fields=extra_fields,
    )


# ---------------------------------------------------------------------------
# Plugin Library schemas (Task A-3)
# ---------------------------------------------------------------------------


class PluginSaveRequest(BaseModel):
    """POST /plugins/save 请求体 — 保存 Plugin manifest 到用户插件库。"""

    name: str = Field(..., min_length=1, description="插件名称（唯一标识）")
    version: str = Field(default="1.0.0", description="版本号")
    description: str = Field(default="", description="描述")
    manifest_yaml: str = Field(default="", description="Plugin manifest YAML 字符串")
    manifest_json: dict = Field(default_factory=dict, description="manifest 解析后的 JSON 对象")


class PluginLibraryResponse(BaseModel):
    """单条插件库条目响应。"""

    id: str
    user_id: str
    name: str
    version: str
    description: str
    manifest_yaml: str
    manifest_json: dict
    enabled: bool
    created_at: str
    updated_at: str


class PluginLibraryPatchRequest(BaseModel):
    """PATCH /plugins/library/{plugin_id} 请求体。"""

    enabled: bool = Field(description="true=启用, false=禁用")


# ---------------------------------------------------------------------------
# GET /plugins/library — 用户插件库列表
# ---------------------------------------------------------------------------


@router.get(
    "/library",
    response_model=list[PluginLibraryResponse],
    summary="获取用户插件库（当前用户拥有的插件）",
)
async def list_plugin_library(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[PluginLibraryResponse]:
    """列出当前用户插件库中的所有插件（按 created_at DESC 排序）。"""
    from app.models.plugin_library import PluginLibrary

    entries = (
        db.query(PluginLibrary)
        .filter_by(user_id=current_user.id)
        .order_by(PluginLibrary.created_at.desc())
        .all()
    )

    return [_plugin_library_to_response(e) for e in entries]


# ---------------------------------------------------------------------------
# POST /plugins/save — 保存 Plugin manifest 到用户插件库
# ---------------------------------------------------------------------------


@router.post(
    "/save",
    response_model=PluginLibraryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="保存 Plugin manifest 到用户插件库（UPSERT 语义）",
)
async def save_plugin(
    body: PluginSaveRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PluginLibraryResponse:
    """将 Plugin manifest 保存到用户插件库（同名则更新，否则新建）。"""
    import yaml as _yaml
    from datetime import datetime, timezone

    from app.models.plugin_library import PluginLibrary

    now = datetime.now(timezone.utc)

    # If manifest_json is empty ({}) but YAML is provided, parse YAML server-side
    # so the JSONB cache column stays consistent with manifest_yaml.
    manifest_json = body.manifest_json
    if not manifest_json and body.manifest_yaml.strip():
        try:
            parsed = _yaml.safe_load(body.manifest_yaml)
            if isinstance(parsed, dict):
                manifest_json = parsed
        except Exception:
            pass  # YAML parse error — keep {} rather than reject the save

    existing = (
        db.query(PluginLibrary)
        .filter_by(user_id=current_user.id, name=body.name)
        .first()
    )

    if existing is not None:
        existing.version = body.version
        existing.description = body.description
        existing.manifest_yaml = body.manifest_yaml
        existing.manifest_json = manifest_json
        existing.updated_at = now
        entry = existing
        logger.info(
            "plugin.library.updated",
            user_id=str(current_user.id),
            plugin=body.name,
        )
    else:
        entry = PluginLibrary(
            user_id=current_user.id,
            name=body.name,
            version=body.version,
            description=body.description,
            manifest_yaml=body.manifest_yaml,
            manifest_json=manifest_json,
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        db.add(entry)
        logger.info(
            "plugin.library.saved",
            user_id=str(current_user.id),
            plugin=body.name,
        )

    db.commit()
    db.refresh(entry)

    return _plugin_library_to_response(entry)


# ---------------------------------------------------------------------------
# PATCH /plugins/library/{plugin_id} — 启用/禁用插件
# ---------------------------------------------------------------------------


@router.patch(
    "/library/{plugin_id}",
    response_model=PluginLibraryResponse,
    summary="启用或禁用用户插件库中的插件",
)
async def patch_plugin_library(
    plugin_id: str,
    body: PluginLibraryPatchRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PluginLibraryResponse:
    """切换用户插件库中某插件的启用状态。"""
    from datetime import datetime, timezone

    from app.models.plugin_library import PluginLibrary

    entry = (
        db.query(PluginLibrary)
        .filter_by(id=plugin_id, user_id=current_user.id)
        .first()
    )

    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"插件 '{plugin_id}' 不存在或不属于当前用户。",
        )

    entry.enabled = body.enabled
    entry.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(entry)

    logger.info(
        "plugin.library.patched",
        user_id=str(current_user.id),
        plugin_id=plugin_id,
        enabled=body.enabled,
    )
    return _plugin_library_to_response(entry)


# ---------------------------------------------------------------------------
# DELETE /plugins/library/{plugin_id} — 从用户插件库删除
# ---------------------------------------------------------------------------


@router.delete(
    "/library/{plugin_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="从用户插件库删除插件",
)
async def delete_plugin_library(
    plugin_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """从用户插件库中删除指定插件。"""
    from app.models.plugin_library import PluginLibrary

    entry = (
        db.query(PluginLibrary)
        .filter_by(id=plugin_id, user_id=current_user.id)
        .first()
    )

    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"插件 '{plugin_id}' 不存在或不属于当前用户。",
        )

    db.delete(entry)
    db.commit()

    logger.info(
        "plugin.library.deleted",
        user_id=str(current_user.id),
        plugin_id=plugin_id,
    )


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _plugin_library_to_response(entry) -> PluginLibraryResponse:
    """将 PluginLibrary ORM 对象转为 PluginLibraryResponse。"""
    return PluginLibraryResponse(
        id=entry.id,
        user_id=entry.user_id,
        name=entry.name,
        version=entry.version,
        description=entry.description,
        manifest_yaml=entry.manifest_yaml,
        manifest_json=entry.manifest_json or {},
        enabled=entry.enabled,
        created_at=entry.created_at.isoformat() if entry.created_at else "",
        updated_at=entry.updated_at.isoformat() if entry.updated_at else "",
    )
