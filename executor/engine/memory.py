"""
6 层 Memory 系统（v4 Task 3.5，Phase 1 实现 Layer 1 + Layer 2）

层级（优先级从低到高）：
1. Platform memory — PromptAssembler 静态 section 已覆盖（本模块不实现）
2. User memory     — 用户级偏好/历史，从 user_memories 表聚合最近 10 条（Layer 2）
3. Session memory  — 会话级，从 sessions.config_snapshot.session_memory 读取（Layer 1）
4. Auto memory     — 自动学习（Phase 2 预留接口）
5. Skill memory    — Skill 注入（Phase 2 预留接口）
6. Team memory     — 多用户协作（Phase 2 预留接口）

进程边界注意：
- 本模块在 executor 下，直接接受已构造的 db_session（SQLAlchemy Session 协议）
- 禁止 import backend.app.*（进程边界规则）
- 使用 raw SQL（SQLAlchemy text() 字符串），不依赖 ORM model class
- db_session=None 时全部层级返回 None/空（单测场景）

ADR-031：Compaction 按回合组原子裁剪（见 compaction.py）
ADR-032：is_skill_context 优先保留（见 compaction.py）
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import structlog

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# MemoryLayer 抽象基类
# ---------------------------------------------------------------------------


class MemoryLayer(ABC):
    """v4：6 层 Memory 抽象基类，Phase 1 只实现 Layer 1/2。

    load() 返回该层级的 memory 文本（str），没有内容时返回 None。
    """

    @abstractmethod
    async def load(self) -> str | None:
        """加载该层级 memory，返回 str 或 None（无内容时）。"""
        ...


# ---------------------------------------------------------------------------
# Layer 1 — SessionMemory（会话级摘要）
# ---------------------------------------------------------------------------


class SessionMemory(MemoryLayer):
    """Layer 1：会话级上下文。

    从 sessions.config_snapshot JSONB 字段读取 session_memory key。
    Compaction Tier 2/3 产出的摘要写入此字段（DOC-07 Task 7.4 注入）。
    db_session=None 时直接返回 None（单测场景）。
    """

    def __init__(self, session_id: str, db_session) -> None:
        self._session_id = session_id
        self._db = db_session

    async def load(self) -> str | None:
        if self._db is None:
            return None
        try:
            from sqlalchemy import text

            row = self._db.execute(
                text("SELECT config_snapshot FROM sessions WHERE id = :sid"),
                {"sid": self._session_id},
            ).first()
            if row is None:
                return None
            config_snapshot = row[0]  # config_snapshot is JSONB → dict after driver decode
            if isinstance(config_snapshot, dict):
                return config_snapshot.get("session_memory") or None
            return None
        except Exception as exc:
            logger.warning(
                "memory.session.load_failed",
                session_id=self._session_id,
                error=str(exc),
            )
            return None


# ---------------------------------------------------------------------------
# Layer 2 — UserMemory（用户级偏好/历史）
# ---------------------------------------------------------------------------


class UserMemory(MemoryLayer):
    """Layer 2：用户级偏好与历史要点。

    从 user_memories 表聚合最近 10 条 memory_text，按 created_at DESC 排序，
    用 '\\n\\n---\\n\\n' 连接后返回。
    db_session=None 时直接返回 None（单测场景）。

    注意：user_memories 表的文本列名为 memory_text（ORM model 字段）。
    """

    def __init__(self, user_id: str, db_session) -> None:
        self._user_id = user_id
        self._db = db_session

    async def load(self) -> str | None:
        if self._db is None:
            return None
        try:
            from sqlalchemy import text

            rows = self._db.execute(
                text(
                    """
                    SELECT memory_text FROM user_memories
                    WHERE user_id = :uid
                    ORDER BY created_at DESC
                    LIMIT 10
                    """
                ),
                {"uid": self._user_id},
            ).fetchall()
            if not rows:
                return None
            texts = [r[0] for r in rows if r[0]]
            if not texts:
                return None
            return "\n\n---\n\n".join(texts)
        except Exception as exc:
            logger.warning(
                "memory.user.load_failed",
                user_id=self._user_id,
                error=str(exc),
            )
            return None


# ---------------------------------------------------------------------------
# MemoryManager（Phase 1：Layer 1 + Layer 2）
# ---------------------------------------------------------------------------


class MemoryManager:
    """v4：Phase 1 加载 Layer 1（SessionMemory）+ Layer 2（UserMemory）。

    其余 4 层（Layer 3/4/5/6）在 Phase 2 按需实现，get_layer() 预留接口。

    load() 拼接顺序：User（Layer 2，优先，内容更稳定）+ Session（Layer 1）。
    返回空字符串时表示没有任何 memory 需要注入。

    db_session=None（单测场景）时 load() 返回 ""。
    """

    def __init__(self, user_id: str, session_id: str, db_session) -> None:
        self._user_id = user_id
        self._session_id = session_id
        self._db = db_session
        # Phase 1 实现 Layer 1 + Layer 2
        self._layers: dict[int, MemoryLayer] = {
            1: SessionMemory(session_id, db_session),
            2: UserMemory(user_id, db_session),
            # Layer 3/4/5/6 Phase 2 预留
        }

    def get_layer(self, layer: int) -> MemoryLayer | None:
        """按层级编号获取 MemoryLayer 实例，供 Phase 2 按需扩展使用。"""
        return self._layers.get(layer)

    async def load(self) -> str:
        """加载所有已实现层级 memory，拼接为字符串。

        顺序：User（Layer 2）优先 → Session（Layer 1）。
        无内容时返回 ""（QueryEngine / PromptAssembler 可直接判断 if memory_str 注入）。
        """
        if self._db is None:
            return ""

        parts: list[str] = []

        # Layer 2：User memory（优先，跨 session 内容更稳定）
        user_mem = await self._layers[2].load()
        if user_mem:
            parts.append(f"## 用户长期偏好与历史要点\n{user_mem}")

        # Layer 1：Session memory
        session_mem = await self._layers[1].load()
        if session_mem:
            parts.append(f"## 本会话历史摘要\n{session_mem}")

        return "\n\n".join(parts) if parts else ""
