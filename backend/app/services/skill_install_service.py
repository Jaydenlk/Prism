"""
SkillInstallService — Skill 安装/卸载 Backend 服务

DOC-05 Task 5.6: Skills CLI & Agent Tool（ADR-053）
ADR-053 (PRD 原标 ADR-049 平移): Backend 写 skill_installs 表（DOC-01 v4 §4.2）。
  - install: 调用 SkillsRegistry.install() + INSERT/UPSERT skill_installs
  - uninstall: 调用 SkillsRegistry.uninstall() + UPDATE skill_installs SET status='uninstalled'
  - Redis 缓存 key: skill_install:status:{user_id}:{skill_name} TTL 600s

来源: Batch 3 §A9-4; PRD DOC-05 v4 Task 5.6 Part A

Backend 侧可以 import executor.plugins.skills_registry（executor 侧不 import backend.app）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.orm import Session

logger = structlog.get_logger()

# Redis TTL for skill install status cache (ADR-053)
_SKILL_INSTALL_STATUS_TTL = 600  # 10 minutes


# ---------------------------------------------------------------------------
# SkillInstallService
# ---------------------------------------------------------------------------


class SkillInstallService:
    """Skill 安装/卸载服务（ADR-053）

    职责：
    1. 接收 install/uninstall 请求（来自 CLI POST 或 UI POST）
    2. 调用 SkillsRegistry 操作文件系统
    3. 写/更新 skill_installs 表（INSERT UPSERT on conflict）
    4. 刷新 Redis 缓存（skill_install:status:{user_id}:{skill_name}）
    5. 返回 SkillInstall ORM 对象

    进程边界：Backend 服务可 import executor.plugins.skills_registry。
    Executor 进程不 import backend.app（单向依赖）。
    """

    def __init__(
        self,
        db: Session,
        redis_client: Any | None = None,
    ) -> None:
        """
        Args:
            db: SQLAlchemy Session（同步）
            redis_client: redis.Redis 实例（可选，用于缓存 key 刷新）
        """
        self._db = db
        self._redis = redis_client

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def install(
        self,
        user_id: str,
        skill_name: str,
        source: str,
        source_url: str,
        version: str,
        install_path: str,
        has_hooks: bool,
        has_mcp: bool,
        marketplace_id: str | None = None,
    ) -> "SkillInstall":
        """写入或更新 skill_installs 表（ADR-053）。

        采用 UPSERT 语义（同 user_id + skill_name 冲突则更新）。

        Args:
            user_id: 操作用户 ID
            skill_name: Skill 名称（如 "web-researcher"）
            source: 来源（"local" | "github" | "marketplace"）
            source_url: 源地址（本地路径 / GitHub URL / marketplace.json URL）
            version: 版本号
            install_path: 本地安装路径（.prism/skills/@source/name/）
            has_hooks: 是否含 hooks
            has_mcp: 是否含 MCP 配置
            marketplace_id: 当 source='marketplace' 时关联的 marketplace_registry.id（DOC-SK R1, ADR-086）

        Returns:
            SkillInstall ORM 对象（已持久化）
        """
        from app.models.skill_install import SkillInstall

        now = datetime.now(timezone.utc)

        # UPSERT: 查找现有记录
        existing = (
            self._db.query(SkillInstall)
            .filter_by(user_id=user_id, skill_name=skill_name)
            .first()
        )

        metadata_payload = {
            "install_path": install_path,
            "has_hooks": has_hooks,
            "has_mcp": has_mcp,
            "status": "installed",
        }

        if existing is not None:
            # 更新现有记录
            existing.source = source
            existing.source_url = source_url
            existing.version = version
            existing.installed_at = now
            existing.updated_at = now
            existing.metadata_ = metadata_payload
            existing.marketplace_id = marketplace_id
            skill_install = existing
            logger.info(
                "skill_install_service.install.update",
                user_id=user_id,
                skill_name=skill_name,
                version=version,
                source=source,
            )
        else:
            # INSERT 新记录
            skill_install = SkillInstall(
                user_id=user_id,
                skill_name=skill_name,
                source=source,
                source_url=source_url,
                version=version,
                installed_at=now,
                updated_at=now,
                metadata_=metadata_payload,
                marketplace_id=marketplace_id,
            )
            self._db.add(skill_install)
            logger.info(
                "skill_install_service.install.insert",
                user_id=user_id,
                skill_name=skill_name,
                version=version,
                source=source,
            )

        self._db.commit()
        self._db.refresh(skill_install)

        # Redis 缓存刷新（ADR-053）
        self._set_status_cache(user_id, skill_name, "installed")

        return skill_install

    def uninstall(
        self,
        user_id: str,
        skill_name: str,
    ) -> bool:
        """将 skill_installs 表中的 status 更新为 'uninstalled'（ADR-053）。

        注：实际文件删除由 CLI/UI 调用 SkillsRegistry.uninstall() 完成。
            本方法只更新 DB 状态。

        Returns:
            True = 记录找到并更新；False = 记录不存在
        """
        from app.models.skill_install import SkillInstall

        existing = (
            self._db.query(SkillInstall)
            .filter_by(user_id=user_id, skill_name=skill_name)
            .first()
        )

        if existing is None:
            logger.warning(
                "skill_install_service.uninstall.not_found",
                user_id=user_id,
                skill_name=skill_name,
            )
            return False

        now = datetime.now(timezone.utc)
        existing.updated_at = now
        existing.metadata_ = {
            **existing.metadata_,
            "status": "uninstalled",
        }
        self._db.commit()

        # Redis 缓存刷新（ADR-053）
        self._set_status_cache(user_id, skill_name, "uninstalled")

        logger.info(
            "skill_install_service.uninstall",
            user_id=user_id,
            skill_name=skill_name,
        )
        return True

    def list_installed(self, user_id: str) -> list["SkillInstall"]:
        """列出用户所有已安装 Skill（status='installed'）。"""
        from app.models.skill_install import SkillInstall

        return (
            self._db.query(SkillInstall)
            .filter(
                SkillInstall.user_id == user_id,
                SkillInstall.metadata_["status"].astext == "installed",
            )
            .order_by(SkillInstall.installed_at.desc())
            .all()
        )

    def get_install(
        self, user_id: str, skill_name: str
    ) -> "SkillInstall | None":
        """查询单个 Skill 安装记录。先查 Redis 缓存 status，再查 DB。"""
        # 优先查 Redis 缓存
        cached_status = self._get_status_cache(user_id, skill_name)
        if cached_status == "not_installed":
            return None

        from app.models.skill_install import SkillInstall

        return (
            self._db.query(SkillInstall)
            .filter_by(user_id=user_id, skill_name=skill_name)
            .first()
        )

    # ------------------------------------------------------------------
    # Redis 缓存工具（ADR-053）
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_key(user_id: str, skill_name: str) -> str:
        """Redis key 格式: skill_install:status:{user_id}:{skill_name}（ADR-053）。"""
        return f"skill_install:status:{user_id}:{skill_name}"

    def _set_status_cache(
        self, user_id: str, skill_name: str, status: str
    ) -> None:
        """写入 Redis 缓存，TTL=600s（ADR-053）。"""
        if self._redis is None:
            return
        key = self._cache_key(user_id, skill_name)
        try:
            self._redis.set(key, status, ex=_SKILL_INSTALL_STATUS_TTL)
        except Exception as exc:
            logger.warning(
                "skill_install_service.redis_set_error",
                key=key,
                error=str(exc),
            )

    def _get_status_cache(self, user_id: str, skill_name: str) -> str | None:
        """读取 Redis 缓存，返回状态字符串或 None（cache miss）。"""
        if self._redis is None:
            return None
        key = self._cache_key(user_id, skill_name)
        try:
            value = self._redis.get(key)
            return value.decode() if isinstance(value, bytes) else value
        except Exception as exc:
            logger.warning(
                "skill_install_service.redis_get_error",
                key=key,
                error=str(exc),
            )
            return None
