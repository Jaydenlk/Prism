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
    source: Literal["local", "github", "marketplace", "context7"]
    source_url: str
    author: str | None = None
    tags: list[str] = Field(default_factory=list)
    stars: int = 0
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


class DirectInstallRequest(BaseModel):
    """直接通过 GitHub URL 或 owner/repo 安装 Skill 请求体"""

    url: str = Field(description="GitHub URL (https://github.com/owner/repo) 或 owner/repo 简写")
    name: str | None = Field(default=None, description="覆盖 marketplace 名称（省略时自动从 owner/repo 推导）")


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
    limit: int = Query(default=10, ge=1, le=100, description="最大结果数（1-100）"),
    db: Annotated[Session, Depends(get_db)] = None,
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

    # FIX 3: empty results + non-empty query → trigger marketplace re-sync and retry
    if not packages and q and db is not None and current_user is not None:
        try:
            mp_svc = MarketplaceService(db=db)
            mp_svc.sync_all(user_id=str(current_user.id))
            packages = await registry.search(q, sources=sources_filter)
            logger.info("skills_api.search.resync_triggered", q=q, found=len(packages))
        except Exception as exc:
            logger.warning("skills_api.search.resync_failed", q=q, error=str(exc))

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
            stars=p.stars,
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

        workspace = os.environ.get("PRISM_WORKSPACE", "/app/data")
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

    elif request.source == "github":
        # source_url already validated non-None above for non-content_base64 path
        if not request.source_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="source='github' 时 source_url 为必填",
            )
        workspace = os.environ.get("PRISM_WORKSPACE", "/app/data")
        try:
            resolved_install_path = await _download_github_skill(
                source_url=request.source_url,
                skill_name=effective_skill_name,
                workspace=workspace,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            )
        except Exception as exc:
            logger.error(
                "skills_api.install.github_download_error",
                skill_name=effective_skill_name,
                source_url=request.source_url,
                error=str(exc),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"GitHub 内容下载失败: {exc}",
            )
        resolved_source_url = request.source_url

        # Register sub-skills from skills/<name>/SKILL.md (multi-skill plugins like superpowers).
        # When _download_github_skill fetched marketplace.json, it created these sub-dirs.
        sub_skills_dir = os.path.join(resolved_install_path, "skills")
        if os.path.isdir(sub_skills_dir):
            import glob as _glob
            redis_client = _get_redis_client()
            svc = SkillInstallService(db=db, redis_client=redis_client)
            for sf in sorted(_glob.glob(os.path.join(sub_skills_dir, "*", "SKILL.md"))):
                sub_dir = os.path.dirname(sf)
                sub_name = os.path.basename(sub_dir)
                qualified_name = f"{effective_skill_name}:{sub_name}"
                try:
                    svc.install(
                        user_id=current_user.id,
                        skill_name=qualified_name,
                        source="github",
                        source_url=request.source_url,
                        version=resolved_version,
                        install_path=sub_dir,
                        has_hooks=request.has_hooks,
                        has_mcp=request.has_mcp,
                    )
                    logger.info(
                        "skills_api.install.sub_skill_registered",
                        skill_name=qualified_name,
                        install_path=sub_dir,
                        user_id=str(current_user.id),
                    )
                except Exception as exc:
                    logger.warning(
                        "skills_api.install.sub_skill_register_failed",
                        skill_name=qualified_name,
                        error=str(exc),
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
# POST /skills/install-url — 直接通过 GitHub URL 安装（注册为 marketplace）
# ---------------------------------------------------------------------------


@router.post(
    "/install-url",
    response_model=ApiResponse[dict],
    status_code=status.HTTP_201_CREATED,
    summary="直接通过 GitHub URL 或 owner/repo 安装 Skill（注册为 marketplace 并同步）",
)
async def install_skill_by_url(
    request: DirectInstallRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[dict]:
    """将 GitHub 仓库注册为 marketplace 并触发 catalog 同步。

    接受格式:
    - "owner/repo"（简写，如 "obra/superpowers"）
    - "https://github.com/owner/repo"（完整 URL）

    Flow:
    1. 规范化 URL → owner/repo 或 https://github.com/owner/repo
    2. 调用 MarketplaceService.create() — git clone + 读取 .claude-plugin/marketplace.json
    3. 返回注册结果（marketplace_id + catalog 摘要）
    """
    raw = request.url.strip().rstrip("/")

    # 规范化：提取 owner/repo 短名
    if raw.startswith("https://github.com/"):
        shorthand = raw[len("https://github.com/"):]
    elif raw.startswith("http://github.com/"):
        shorthand = raw[len("http://github.com/"):]
    else:
        shorthand = raw  # 已是 owner/repo 或其他 HTTPS URL

    # 去掉尾部 .git
    if shorthand.endswith(".git"):
        shorthand = shorthand[:-4]

    # 验证 owner/repo 格式（若不含 / 或含多余路径则拒绝）
    parts = shorthand.split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的 GitHub 仓库格式: '{request.url}'。期望 'owner/repo' 或 'https://github.com/owner/repo'",
        )

    # 使用 owner/repo 简写作为 MarketplaceService URL（_fetch_git 会自动补全为 HTTPS）
    normalized_url = f"{parts[0]}/{parts[1]}"
    mp_name = request.name or normalized_url

    # 验证 GitHub 仓库是否存在（公开 API，无需 token）
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            gh_resp = await client.get(
                f"https://api.github.com/repos/{normalized_url}",
                headers={"Accept": "application/vnd.github.v3+json"},
            )
        if gh_resp.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"GitHub 仓库不存在: '{normalized_url}'",
            )
        if gh_resp.status_code not in (200, 301, 302):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无法验证 GitHub 仓库 '{normalized_url}': HTTP {gh_resp.status_code}",
            )
    except HTTPException:
        raise
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub 连接失败: {exc}",
        )

    try:
        mp_svc = MarketplaceService(db=db)
        mp = mp_svc.create(
            user_id=str(current_user.id),
            url=normalized_url,
            name=mp_name,
        )
    except Exception as exc:
        logger.error(
            "skills_api.install_url_error",
            url=request.url,
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"注册 marketplace 失败: {exc}",
        )

    catalog = mp.catalog_json or {}
    plugin_count = len(catalog.get("plugins", []))
    plugin_names = [p.get("name") for p in catalog.get("plugins", []) if isinstance(p, dict) and p.get("name")]

    logger.info(
        "skills_api.install_url",
        user_id=str(current_user.id),
        url=request.url,
        marketplace_id=mp.id,
        plugin_count=plugin_count,
    )

    return ApiResponse(data={
        "marketplace_id": mp.id,
        "name": mp.name,
        "url": mp.url,
        "plugin_count": plugin_count,
        "plugins": plugin_names,
        "catalog_fetched": mp.catalog_json is not None,
    })


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

    # (b) source_url → 拉取 raw（支持 github.com URL 和 marketplace:// 内部 scheme）
    effective_url = source_url or (install.source_url if install else None)
    raw_candidates: list[str] = []

    if effective_url and effective_url.startswith("marketplace://"):
        # marketplace://{mp_name}/{plugin_name} → 通过 catalog_json 查找 GitHub 原始 URL
        mp_path = effective_url[len("marketplace://"):]
        mp_parts = mp_path.split("/", 1)
        if len(mp_parts) == 2:
            mp_name_part, plugin_name_part = mp_parts
            from app.models.marketplace import MarketplaceRegistry as _MPReg
            mp_row = db.query(_MPReg).filter_by(name=mp_name_part).first()
            if mp_row and mp_row.url:
                catalog = mp_row.catalog_json or {}
                plugins_list = catalog.get("plugins") or []
                source_path = plugin_name_part  # fallback: plugin name as path
                for entry in plugins_list:
                    if isinstance(entry, dict) and entry.get("name") == plugin_name_part:
                        entry_src = entry.get("source")
                        if isinstance(entry_src, dict):
                            source_path = entry_src.get("path", plugin_name_part)
                        elif isinstance(entry_src, str):
                            source_path = entry_src
                        break
                base_raw = f"https://raw.githubusercontent.com/{mp_row.url}/HEAD"
                raw_candidates = [f"{base_raw}/{source_path.rstrip('/')}/SKILL.md"]

    elif effective_url and "github.com" in effective_url:
        raw_base = effective_url.replace("github.com", "raw.githubusercontent.com").rstrip("/")
        raw_candidates = [
            f"{raw_base}/main/SKILL.md",
            f"{raw_base}/master/SKILL.md",
            f"{raw_base}/main/README.md",
            f"{raw_base}/master/README.md",
        ]

    if raw_candidates:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                for url in raw_candidates:
                    resp = await client.get(url)
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


import re as _re


async def _download_github_skill(source_url: str, skill_name: str, workspace: str) -> str:
    """Download skill files from a GitHub repo via git clone --depth 1.

    Returns the install_path directory. Clones the full repo structure so nested
    skill directories (e.g. skills/brainstorming/) are preserved.

    Raises ValueError for bad URLs or when no skill files are found.
    """
    import asyncio as _asyncio
    import shutil as _shutil

    match = _re.match(r"https?://github\.com/([^/]+/[^/?#]+)", source_url)
    if not match:
        raise ValueError(f"无效的 GitHub URL: {source_url}")

    owner_repo = match.group(1).rstrip("/")
    if owner_repo.endswith(".git"):
        owner_repo = owner_repo[:-4]

    install_dir = os.path.join(workspace, ".prism", "skills", "@github", skill_name)

    if os.path.isdir(install_dir):
        _shutil.rmtree(install_dir)

    clone_url = f"https://github.com/{owner_repo}.git"
    proc = await _asyncio.create_subprocess_exec(
        "git", "clone", "--depth", "1", clone_url, install_dir,
        stdout=_asyncio.subprocess.PIPE,
        stderr=_asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise ValueError(
            f"git clone 失败 ({owner_repo}): {stderr.decode(errors='replace').strip()}"
        )

    git_dir = os.path.join(install_dir, ".git")
    if os.path.isdir(git_dir):
        _shutil.rmtree(git_dir)

    has_skill = (
        os.path.isfile(os.path.join(install_dir, "SKILL.md"))
        or os.path.isfile(os.path.join(install_dir, "plugin.json"))
        or os.path.isfile(os.path.join(install_dir, ".claude-plugin", "marketplace.json"))
    )
    if not has_skill:
        skill_md_count = sum(
            1 for root, _, files in os.walk(install_dir) if "SKILL.md" in files
        )
        if skill_md_count == 0:
            _shutil.rmtree(install_dir, ignore_errors=True)
            raise ValueError(
                f"{owner_repo} 不是有效的 Skill 仓库（未找到 SKILL.md 或 plugin.json）"
            )

    file_count = sum(1 for _, _, files in os.walk(install_dir) for _ in files)
    logger.info(
        "skills_api.install.github_cloned",
        owner_repo=owner_repo,
        skill_name=skill_name,
        file_count=file_count,
        install_dir=install_dir,
    )
    return install_dir


def _get_registry():
    """懒加载 SkillsRegistry(fix#3+: LocalSource + MarketplaceCatalogSource).

    与 Claude Code 官方 Discover pattern 对齐:用户先注册 marketplace,然后
    search 从已注册 catalogs 浏览。无 GITHUB_TOKEN 依赖。
    """
    from app.core.database import SessionLocal
    from executor.plugins.context7_source import Context7Source
    from executor.plugins.github_source import GitHubSource
    from executor.plugins.skills_registry import (
        LocalSource,
        MarketplaceCatalogSource,
        SkillsRegistry,
    )

    workspace = os.environ.get("PRISM_WORKSPACE", "/app/data")
    install_dir = os.path.join(workspace, ".prism", "skills")
    return SkillsRegistry(
        sources=[
            LocalSource(workspace=workspace),
            MarketplaceCatalogSource(db_session_factory=SessionLocal),
            GitHubSource(),
            Context7Source(),
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


# ---------------------------------------------------------------------------
# GET /skills/personas/available — 可用 persona 列表（Think Tank 模式）
# ---------------------------------------------------------------------------


class PersonaInfo(BaseModel):
    """单个 persona 信息"""
    name: str
    slug: str
    description: str


_persona_router = APIRouter(prefix="/personas", tags=["personas"])


def _parse_persona_skill_md(path: str) -> PersonaInfo | None:
    """解析 SKILL.md 文件的 YAML front matter，提取 name + description。"""
    import re as _re_local

    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return None

    # YAML front matter: --- ... ---
    match = _re_local.match(r"^---\s*\n(.*?)\n---", text, _re_local.DOTALL)
    if not match:
        return None

    fm = match.group(1)

    def _extract(key: str) -> str:
        km = _re_local.search(rf"^{key}:\s*(.+?)$", fm, _re_local.MULTILINE)
        if km:
            return km.group(1).strip().strip('"\'')
        # multi-line description (starts with |)
        block_m = _re_local.search(rf"^{key}:\s*\|\s*\n((?:  .+\n?)*)", fm, _re_local.MULTILINE)
        if block_m:
            lines = [l.strip() for l in block_m.group(1).splitlines() if l.strip()]
            return " ".join(lines)
        return ""

    name = _extract("name")
    description = _extract("description")
    if not name:
        return None

    slug = os.path.basename(os.path.dirname(path))
    # Trim description to 200 chars
    if len(description) > 200:
        description = description[:197] + "..."

    return PersonaInfo(name=name, slug=slug, description=description)


def _find_persona_skills_dir() -> str | None:
    """查找 tempp/persona-skills 目录（支持 worktree + 主仓库两种布局）。"""
    cwd = os.getcwd()
    workspace = os.environ.get("PRISM_WORKSPACE", cwd)
    candidates = [
        os.path.join(workspace, "tempp", "persona-skills"),
        os.path.join(cwd, "tempp", "persona-skills"),
        os.path.join(cwd, "..", "tempp", "persona-skills"),
        os.path.join(cwd, "..", "..", "tempp", "persona-skills"),
    ]
    for c in candidates:
        resolved = os.path.normpath(c)
        if os.path.isdir(resolved):
            return resolved
    return None


@_persona_router.get(
    "/available",
    response_model=ApiResponse[list[PersonaInfo]],
    summary="获取可用 Persona 列表（Think Tank 模式）",
)
async def list_available_personas(
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[list[PersonaInfo]]:
    """读取 tempp/persona-skills/*/SKILL.md，返回所有可用 persona。"""
    import glob as _glob

    personas_dir = _find_persona_skills_dir()
    if not personas_dir:
        return ApiResponse(data=[])

    skill_files = sorted(_glob.glob(os.path.join(personas_dir, "*", "SKILL.md")))
    results: list[PersonaInfo] = []
    for sf in skill_files:
        info = _parse_persona_skill_md(sf)
        if info:
            results.append(info)

    results.sort(key=lambda p: p.name.lower())
    return ApiResponse(data=results)
