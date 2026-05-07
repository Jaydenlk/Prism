"""
Prism v2 — Skills Market API（DOC-05 Task 5.6）

路由表（PRD DOC-05 v4 Task 5.6 Part A，DOC-01 v4 §6.12）:
  GET    /api/v1/skills/search?q=...&source=local|github  跨源搜索（ADR-052）
  GET    /api/v1/skills/installed                          已安装列表（from skill_installs 表）
  POST   /api/v1/skills/install                            安装（写 skill_installs 表，ADR-053）
  DELETE /api/v1/skills/{skill_name}                       卸载（更新 skill_installs.status，ADR-053）
  POST   /api/v1/skills/{skill_name}/update                更新
  GET    /api/v1/skills/{skill_name}                       Skill 详情

ADR-052 (PRD 原标 ADR-048 平移): Agent Tool 仅搜索权限，无 install/uninstall。
ADR-053 (PRD 原标 ADR-049 平移): Backend 写 skill_installs 表，Redis 缓存 key 格式
         skill_install:status:{user_id}:{skill_name} TTL 600s。

Prometheus metrics（Batch 5 §B5-I）:
  prism_skill_searches_total — 搜索次数计数
  prism_skill_installs_total — 安装次数计数（label: source）
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Annotated, Literal

import httpx

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_db
from app.models.user import User
from app.observability.metrics import REGISTRY
from app.schemas.common import ApiResponse
from app.services.marketplace_service import MarketplaceService
from app.services.skill_install_service import SkillInstallService

logger = structlog.get_logger()
router = APIRouter(prefix="/skills", tags=["skills"])


# ---------------------------------------------------------------------------
# Prometheus metrics（Batch 5 §B5-I）
# ---------------------------------------------------------------------------

try:
    from prometheus_client import Counter

    _SEARCHES_TOTAL = Counter(
        "prism_skill_searches_total",
        "Total Skill market search requests",
        ["source"],
        registry=REGISTRY,
    )
    _INSTALLS_TOTAL = Counter(
        "prism_skill_installs_total",
        "Total Skill install operations",
        ["source", "status"],
        registry=REGISTRY,
    )
except Exception:
    # 防止 Prometheus 重复注册（测试环境 / 重载）
    _SEARCHES_TOTAL = None
    _INSTALLS_TOTAL = None


def _inc_search(source: str) -> None:
    if _SEARCHES_TOTAL is not None:
        try:
            _SEARCHES_TOTAL.labels(source=source or "all").inc()
        except Exception:
            pass


def _inc_install(source: str, install_status: str) -> None:
    if _INSTALLS_TOTAL is not None:
        try:
            _INSTALLS_TOTAL.labels(source=source, status=install_status).inc()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Pydantic Schemas（内联，不创建独立 schemas/skill.py 以控制 Task 范围）
# ---------------------------------------------------------------------------


class SkillPackageResponse(BaseModel):
    """Skills 搜索结果单条（对应 executor.plugins.skills_registry.SkillPackage）"""

    name: str
    description: str
    version: str
    source: Literal["local", "github", "marketplace"]  # fix#3+ 加 marketplace
    source_url: str
    author: str | None = None
    tags: list[str] = Field(default_factory=list)
    installed: bool = False
    installed_version: str | None = None
    marketplace_id: str | None = None
    plugin_name: str | None = None
    homepage: str | None = None
    repository: str | None = None
    license: str | None = None
    readme_available: bool = False


class SkillInstallRequest(BaseModel):
    """安装 Skill 请求体（来自 CLI 或 UI）"""

    skill_name: str | None = Field(default=None, description="Skill 名称（如 'web-researcher'）；source='marketplace' 时可省略，将以 plugin_name 为准")
    source: Literal["local", "github", "marketplace"] = Field(description="来源")
    source_url: str | None = Field(default=None, description="源地址（本地路径 / GitHub URL / marketplace 时可省略）；local+content_base64 时可省略")
    version: str | None = Field(default=None, description="版本号（如 '1.0.0'）；local+content_base64 时可省略，默认 '1.0.0'")
    install_path: str | None = Field(default=None, description="本地安装路径；local+content_base64 时由服务端自动推导")
    has_hooks: bool = Field(default=False, description="是否含 hooks")
    has_mcp: bool = Field(default=False, description="是否含 MCP 配置")
    content_base64: str | None = Field(default=None, description="Skill SKILL.md 内容 base64（source='local' 或 'marketplace' 时直接上传内容）")
    marketplace_id: str | None = Field(default=None, description="当 source='marketplace' 时关联的 marketplace_registry.id（DOC-SK R1, ADR-086）")
    plugin_name: str | None = Field(default=None, description="当 source='marketplace' 时在 catalog 中查找的 plugin entry name（v1：plugin = 单 skill 包装）")


class SkillInstallResponse(BaseModel):
    """安装结果响应（对应 skill_installs 表条目）"""

    id: str
    user_id: str
    skill_name: str
    source: str
    source_url: str | None
    version: str
    installed_at: str  # ISO 8601
    updated_at: str    # ISO 8601
    metadata: dict     # has_hooks / has_mcp / status / install_path
    marketplace_id: str | None = None  # DOC-SK R1, ADR-086


class SkillUpdateRequest(BaseModel):
    """更新 Skill 请求体（当前版本只需 package_id + source）"""

    package_id: str = Field(description="Skill 包 ID（用于向 SkillsRegistry 发起更新）")
    source: Literal["local", "github"] = Field(description="来源")


# ---------------------------------------------------------------------------
# GET /skills/search — 跨源搜索（ADR-052）
# ---------------------------------------------------------------------------


@router.get(
    "/search",
    response_model=ApiResponse[list[SkillPackageResponse]],
    summary="搜索 Skills 市场（Local + GitHub 两源，ADR-052）",
)
async def search_skills(
    q: str = Query(default="", description="搜索关键词（空 = 全部）"),
    source: str | None = Query(
        default=None,
        description="限定源（local | github，默认全部）",
    ),
    limit: int = Query(default=20, ge=1, le=100, description="最大结果数（1-100）"),
    current_user: Annotated[User, Depends(get_current_user)] = None,
) -> ApiResponse[list[SkillPackageResponse]]:
    """跨源并行搜索 Skill 市场（ADR-052）。

    v4：仅搜索，无副作用。Agent 也使用 skills_search 工具调用此搜索逻辑。
    """
    _inc_search(source or "all")

    # 懒加载 SkillsRegistry（不依赖 DB，直接操作文件系统）
    registry = _get_registry()

    sources_filter = [source] if source else None

    try:
        packages = await registry.search(q, sources=sources_filter)
    except Exception as exc:
        logger.error(
            "skills_api.search_error",
            q=q,
            source=source,
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"搜索失败: {exc}",
        )

    truncated = packages[:limit]
    results = [
        SkillPackageResponse(
            name=p.name,
            description=p.description,
            version=p.version,
            source=p.source,
            source_url=p.source_url,
            author=p.author,
            tags=p.tags,
            installed=p.installed,
            installed_version=p.installed_version,
            marketplace_id=p.marketplace_id,
            plugin_name=p.plugin_name,
        )
        for p in truncated
    ]

    logger.info(
        "skills_api.search",
        q=q,
        source=source,
        found=len(packages),
        returned=len(results),
    )

    return ApiResponse(data=results)


# ---------------------------------------------------------------------------
# GET /skills/installed — 已安装列表
# ---------------------------------------------------------------------------


@router.get(
    "/installed",
    response_model=ApiResponse[list[SkillInstallResponse]],
    summary="获取已安装 Skills 列表（from skill_installs 表，ADR-053）",
)
async def list_installed_skills(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[list[SkillInstallResponse]]:
    """从 skill_installs 表查询当前用户的已安装 Skills（ADR-053）。"""
    svc = SkillInstallService(db=db)
    installs = svc.list_installed(user_id=current_user.id)

    results = [_skill_install_to_response(i) for i in installs]
    return ApiResponse(data=results)


# ---------------------------------------------------------------------------
# POST /skills/install — 安装（写 skill_installs 表，ADR-053）
# ---------------------------------------------------------------------------


class SkillPatchRequest(BaseModel):
    """PATCH /skills/{skill_name} 请求体：切换启用/禁用状态"""

    enabled: bool = Field(description="true=启用, false=禁用")


@router.post(
    "/install",
    response_model=ApiResponse[SkillInstallResponse],
    status_code=status.HTTP_201_CREATED,
    summary="安装 Skill（写 skill_installs 表，ADR-053）",
)
async def install_skill(
    request: SkillInstallRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[SkillInstallResponse]:
    """接收 CLI/UI install 请求，写入 skill_installs 表（ADR-053）。

    local + content_base64: 将 base64 内容写入 .prism/skills/@local/<name>/SKILL.md。
    github: source_url 和 version 必填。
    marketplace: marketplace_id + plugin_name 必填；v1 也接受 content_base64
      作为 catalog 下载的 SKILL.md（DOC-SK R1, ADR-086）。
    """
    # ── resolve effective skill_name for marketplace source ──
    effective_skill_name = request.skill_name or request.plugin_name
    if request.source == "marketplace":
        if not request.marketplace_id or not request.plugin_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="source='marketplace' 时 marketplace_id 和 plugin_name 为必填",
            )
        effective_skill_name = request.plugin_name
    if not effective_skill_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="skill_name (或 marketplace 下的 plugin_name) 为必填",
        )

    # ── 本地/marketplace content_base64 路径 ────────────────────────────────
    resolved_source_url = request.source_url
    resolved_version = request.version or "1.0.0"
    resolved_install_path = request.install_path
    resolved_marketplace_id: str | None = None

    if request.source in ("local", "marketplace") and request.content_base64:
        try:
            md_bytes = base64.b64decode(request.content_base64)
            md_text = md_bytes.decode("utf-8")
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"content_base64 解码失败: {exc}",
            )

        workspace = os.environ.get("PRISM_WORKSPACE", os.getcwd())
        ns = "@marketplace" if request.source == "marketplace" else "@local"
        skill_dir = os.path.join(workspace, ".prism", "skills", ns, effective_skill_name)
        os.makedirs(skill_dir, exist_ok=True)
        skill_md_path = os.path.join(skill_dir, "SKILL.md")
        with open(skill_md_path, "w", encoding="utf-8") as f:
            f.write(md_text)

        resolved_source_url = resolved_source_url or skill_md_path
        resolved_install_path = resolved_install_path or skill_dir

        if request.source == "marketplace":
            resolved_marketplace_id = request.marketplace_id

        logger.info(
            "skills_api.install.content_written",
            skill_name=effective_skill_name,
            path=skill_md_path,
            source=request.source,
            user_id=str(current_user.id),
        )

    elif request.source == "github" and not request.source_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source='github' 时 source_url 为必填",
        )
    elif request.source == "marketplace" and not request.content_base64:
        # marketplace_id + plugin_name path: delegate to MarketplaceService.install_plugin()
        # which runs the 5-source resolver, downloads, parses SKILL.md, and UPSERTs skill_installs.
        try:
            mp_svc = MarketplaceService(db=db)
            report = await mp_svc.install_plugin(
                marketplace_id=request.marketplace_id,
                plugin_name=request.plugin_name,
                user_id=str(current_user.id),
            )
        except HTTPException:
            _inc_install(request.source, "error")
            raise
        except Exception as exc:
            logger.error(
                "skills_api.install_error",
                skill_name=request.skill_name,
                source=request.source,
                error=str(exc),
            )
            _inc_install(request.source, "error")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"安装失败: {exc}",
            )

        _inc_install(request.source, "success")
        logger.info(
            "skills_api.install",
            user_id=current_user.id,
            skill_name=effective_skill_name,
            source=request.source,
            marketplace_id=request.marketplace_id,
            installed_skills=report.installed_skills,
        )

        # Return the first installed skill record; report all in metadata.
        first_skill_name = report.installed_skills[0] if report.installed_skills else effective_skill_name
        redis_client = _get_redis_client()
        svc = SkillInstallService(db=db, redis_client=redis_client)
        install_record = svc.get_install(user_id=current_user.id, skill_name=first_skill_name)
        if install_record is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"安装完成但记录未找到: {first_skill_name}",
            )
        return ApiResponse(data=_skill_install_to_response(install_record))

    try:
        # 懒加载 Redis（DOC-07 Task 7.1 之前占位）
        redis_client = _get_redis_client()
        svc = SkillInstallService(db=db, redis_client=redis_client)
        install_record = svc.install(
            user_id=current_user.id,
            skill_name=effective_skill_name,
            source=request.source,
            source_url=resolved_source_url,
            version=resolved_version,
            install_path=resolved_install_path or "",
            has_hooks=request.has_hooks,
            has_mcp=request.has_mcp,
            marketplace_id=resolved_marketplace_id,
        )
    except Exception as exc:
        logger.error(
            "skills_api.install_error",
            skill_name=request.skill_name,
            source=request.source,
            error=str(exc),
        )
        _inc_install(request.source, "error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"安装失败: {exc}",
        )

    _inc_install(request.source, "success")
    logger.info(
        "skills_api.install",
        user_id=current_user.id,
        skill_name=effective_skill_name,
        version=request.version,
        source=request.source,
        marketplace_id=resolved_marketplace_id,
    )

    return ApiResponse(data=_skill_install_to_response(install_record))


# ---------------------------------------------------------------------------
# DELETE /skills/{skill_name} — 卸载（更新 skill_installs.status，ADR-053）
# ---------------------------------------------------------------------------


@router.delete(
    "/{skill_name}",
    response_model=ApiResponse[dict],
    summary="卸载 Skill（更新 skill_installs 状态，ADR-053）",
)
async def uninstall_skill(
    skill_name: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[dict]:
    """将 skill_installs 表中对应记录的 status 更新为 'uninstalled'（ADR-053）。

    注：实际文件删除由 CLI（SkillsRegistry.uninstall()）完成。
    """
    redis_client = _get_redis_client()
    svc = SkillInstallService(db=db, redis_client=redis_client)
    found = svc.uninstall(user_id=current_user.id, skill_name=skill_name)

    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill '{skill_name}' 未安装或不属于当前用户。",
        )

    logger.info(
        "skills_api.uninstall",
        user_id=current_user.id,
        skill_name=skill_name,
    )
    return ApiResponse(data={"skill_name": skill_name, "status": "uninstalled"})


# ---------------------------------------------------------------------------
# PATCH /skills/{skill_name} — 启用 / 禁用（更新 metadata_.enabled）
# ---------------------------------------------------------------------------


@router.patch(
    "/{skill_name}",
    response_model=ApiResponse[dict],
    summary="启用或禁用 Skill（更新 metadata_.enabled 字段）",
)
async def patch_skill(
    skill_name: str,
    request: SkillPatchRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[dict]:
    """切换已安装 Skill 的启用状态，写入 metadata_.enabled（ADR-053）。"""
    from app.models.skill_install import SkillInstall
    from datetime import datetime, timezone

    existing = (
        db.query(SkillInstall)
        .filter_by(user_id=current_user.id, skill_name=skill_name)
        .first()
    )
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill '{skill_name}' 未安装或不属于当前用户。",
        )

    meta = dict(existing.metadata_ or {})
    meta["enabled"] = request.enabled
    existing.metadata_ = meta
    existing.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info(
        "skills_api.patch",
        user_id=str(current_user.id),
        skill_name=skill_name,
        enabled=request.enabled,
    )
    return ApiResponse(data={"skill_name": skill_name, "enabled": request.enabled})


# ---------------------------------------------------------------------------
# GET /skills/{skill_name}/content — 返回 SKILL.md 内容（供查看弹窗使用）
# ---------------------------------------------------------------------------


@router.get(
    "/{skill_name}/content",
    response_model=ApiResponse[dict],
    summary="获取已安装 Skill 的 SKILL.md 内容（供查看弹窗）",
)
async def get_skill_content(
    skill_name: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[dict]:
    """返回已安装 Skill 的 SKILL.md 文件内容，供前端查看弹窗显示。"""
    svc = SkillInstallService(db=db)
    install = svc.get_install(user_id=current_user.id, skill_name=skill_name)

    if install is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill '{skill_name}' 未安装或不属于当前用户。",
        )

    meta = install.metadata_ or {}
    install_path = meta.get("install_path") or ""
    skill_md_path = os.path.join(install_path, "SKILL.md") if install_path else ""

    content = ""
    if skill_md_path and os.path.isfile(skill_md_path):
        try:
            with open(skill_md_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as exc:
            logger.warning(
                "skills_api.content_read_error",
                skill_name=skill_name,
                path=skill_md_path,
                error=str(exc),
            )

    return ApiResponse(data={"skill_name": skill_name, "content": content})


# ---------------------------------------------------------------------------
# GET /skills/{skill_name}/readme — 安装前预览 README/SKILL.md 内容
# ---------------------------------------------------------------------------


@router.get(
    "/{skill_name}/readme",
    response_model=ApiResponse[dict],
    summary="预览 Skill 的 README/SKILL.md 内容（已安装读本地，否则从 GitHub 拉取）",
)
async def get_skill_readme(
    skill_name: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    source_url: str | None = Query(default=None, description="可选 GitHub URL；含 github.com 时从远程拉取"),
) -> ApiResponse[dict]:
    """返回 Skill 的 SKILL.md 内容，供安装前预览。

    优先级:
    a. 已安装 → 从 install_path/SKILL.md 读本地文件 (source=local)
    b. source_url 含 github.com → 从 raw.githubusercontent.com 拉取 (source=github)
    c. 都没有 → 404
    """
    svc = SkillInstallService(db=db)
    install = svc.get_install(user_id=current_user.id, skill_name=skill_name)

    # (a) 已安装 → 读本地 SKILL.md
    if install is not None:
        meta = install.metadata_ or {}
        install_path = meta.get("install_path") or ""
        skill_md_path = Path(install_path) / "SKILL.md" if install_path else None
        if skill_md_path and skill_md_path.is_file():
            content = skill_md_path.read_text(encoding="utf-8")
            return ApiResponse(data={"skill_name": skill_name, "content": content, "source": "local"})

    # (b) source_url 含 github.com → 拉取 raw
    effective_url = source_url or (install.source_url if install else None)
    if effective_url and "github.com" in effective_url:
        # 转换: github.com/owner/repo → raw.githubusercontent.com/owner/repo/main/SKILL.md
        raw_url = effective_url.replace("github.com", "raw.githubusercontent.com")
        if not raw_url.endswith("/SKILL.md"):
            raw_url = raw_url.rstrip("/") + "/main/SKILL.md"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(raw_url)
            if resp.status_code == 200:
                return ApiResponse(data={"skill_name": skill_name, "content": resp.text, "source": "github"})
            # 尝试 master 分支
            raw_master = raw_url.replace("/main/SKILL.md", "/master/SKILL.md")
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(raw_master)
            if resp.status_code == 200:
                return ApiResponse(data={"skill_name": skill_name, "content": resp.text, "source": "github"})
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"GitHub 请求失败: {exc}",
            )

    # (c) 已安装但本地无文件且无可用 GitHub URL → 返回空内容
    if install is not None:
        return ApiResponse(data={"skill_name": skill_name, "content": "", "source": "installed"})

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Skill '{skill_name}' 未安装且未提供有效的 source_url。",
    )


# ---------------------------------------------------------------------------
# POST /skills/{skill_name}/update — 更新
# ---------------------------------------------------------------------------


@router.post(
    "/{skill_name}/update",
    response_model=ApiResponse[SkillInstallResponse],
    summary="更新 Skill 到最新版本（ADR-053）",
)
async def update_skill(
    skill_name: str,
    request: SkillUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[SkillInstallResponse]:
    """更新 Skill（卸载旧版 + 安装新版）。

    本端点协调 SkillsRegistry.update() 文件操作 + DB 同步（ADR-053）。
    """
    registry = _get_registry()

    try:
        updated = await registry.update(skill_name)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error(
            "skills_api.update_error",
            skill_name=skill_name,
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新失败: {exc}",
        )

    # 同步 DB
    redis_client = _get_redis_client()
    svc = SkillInstallService(db=db, redis_client=redis_client)
    install_record = svc.install(
        user_id=current_user.id,
        skill_name=updated.name,
        source=updated.source,
        source_url=updated.source_url,
        version=updated.version,
        install_path=updated.install_path,
        has_hooks=updated.has_hooks,
        has_mcp=updated.has_mcp,
    )

    logger.info(
        "skills_api.update",
        user_id=current_user.id,
        skill_name=skill_name,
        new_version=updated.version,
    )
    return ApiResponse(data=_skill_install_to_response(install_record))


# ---------------------------------------------------------------------------
# GET /skills/{skill_name} — Skill 详情
# ---------------------------------------------------------------------------


@router.get(
    "/{skill_name}",
    response_model=ApiResponse[SkillInstallResponse | SkillPackageResponse],
    summary="获取 Skill 详情（已安装 → DB；未安装 → 搜索市场）",
)
async def get_skill_detail(
    skill_name: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[SkillInstallResponse | SkillPackageResponse]:
    """查询 Skill 详情：已安装则返回 DB 记录，否则搜索市场返回第一条匹配。"""
    svc = SkillInstallService(db=db)
    install = svc.get_install(user_id=current_user.id, skill_name=skill_name)

    if install is not None:
        return ApiResponse(data=_skill_install_to_response(install))

    # 未安装 → 搜索市场
    registry = _get_registry()
    packages = await registry.search(skill_name)
    match = next((p for p in packages if p.name == skill_name), None)

    if match is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill '{skill_name}' 未找到（已安装列表和 Skills 市场均无记录）。",
        )

    return ApiResponse(
        data=SkillPackageResponse(
            name=match.name,
            description=match.description,
            version=match.version,
            source=match.source,
            source_url=match.source_url,
            author=match.author,
            tags=match.tags,
            installed=False,
        )
    )


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _get_registry():
    """懒加载 SkillsRegistry(fix#3+: LocalSource + MarketplaceCatalogSource).

    与 Claude Code 官方 Discover pattern 对齐:用户先注册 marketplace,然后
    search 从已注册 catalogs 浏览。无 GITHUB_TOKEN 依赖。
    """
    from app.core.database import SessionLocal
    from executor.plugins.github_source import GitHubSource
    from executor.plugins.skills_registry import (
        LocalSource,
        MarketplaceCatalogSource,
        SkillsRegistry,
    )

    workspace = os.environ.get("PRISM_WORKSPACE", os.getcwd())
    install_dir = os.path.join(workspace, ".prism", "skills")
    return SkillsRegistry(
        sources=[
            LocalSource(workspace=workspace),
            MarketplaceCatalogSource(db_session_factory=SessionLocal),
            GitHubSource(),
        ],
        install_dir=install_dir,
    )


def _get_redis_client():
    """懒加载 Redis 客户端（DOC-07 Task 7.1 前返回 None）。"""
    try:
        import redis as redis_lib

        from app.core.config import settings

        return redis_lib.from_url(settings.REDIS_URL, decode_responses=False)
    except Exception:
        # Redis 未就绪时不阻断请求，只跳过缓存
        return None


def _skill_install_to_response(install) -> SkillInstallResponse:
    """将 SkillInstall ORM 对象转为 SkillInstallResponse。"""
    return SkillInstallResponse(
        id=install.id,
        user_id=install.user_id,
        skill_name=install.skill_name,
        source=install.source,
        source_url=install.source_url,
        version=install.version,
        installed_at=install.installed_at.isoformat() if install.installed_at else "",
        updated_at=install.updated_at.isoformat() if install.updated_at else "",
        metadata=install.metadata_ or {},
        marketplace_id=install.marketplace_id,
    )
