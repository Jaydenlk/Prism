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
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.dependencies import get_current_user
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
