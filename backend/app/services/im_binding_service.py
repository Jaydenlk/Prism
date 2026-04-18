"""
Prism v2 — IM 用户绑定服务 (DOC-08 Task 8.3, ADR-071)

职责：
  - 生成配对码（6 位数字，5 分钟有效期，碰撞重试最多 3 次）
  - 完成配对（channel + pairing_code → 填写 platform_user_id/chat_id/paired_at）
  - 列出绑定、解除绑定（物理删除）

ADR-071 约束：
  im_bindings 唯一约束为三元组 (channel, platform_user_id, platform_chat_id)，
  允许同一 IM 用户在同一平台的不同群聊分别绑定。
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.im import ImBinding

logger = structlog.get_logger(__name__)

VALID_CHANNELS: frozenset[str] = frozenset({"feishu", "wecom", "telegram"})
PAIRING_CODE_LENGTH: int = 6
PAIRING_CODE_TTL_MINUTES: int = 5
MAX_PAIRING_RETRIES: int = 3


class IMBindingService:
    """
    IM 用户绑定服务。

    所有方法在传入的 `db` Session 上操作；调用方负责 commit/rollback。
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # 生成配对码
    # ------------------------------------------------------------------

    def generate_pairing_code(self, user_id: str, channel: str) -> str:
        """
        为指定用户+平台生成 6 位数字配对码。

        策略：
          - 若该用户在该平台已有未完成的配对记录（paired_at is None），
            覆盖旧配对码并重置 created_at（延长有效期）。
          - 否则创建新 im_bindings 记录（platform_user_id/platform_chat_id 暂为空）。
          - 碰撞重试最多 3 次（同平台已存在相同有效码则重新生成）。

        Returns:
            6 位数字字符串配对码

        Raises:
            ValueError: channel 不合法
            RuntimeError: 3 次重试后仍碰撞（极低概率）
        """
        if channel not in VALID_CHANNELS:
            raise ValueError(
                f"Invalid channel '{channel}'. Must be one of: {', '.join(sorted(VALID_CHANNELS))}"
            )

        code = self._generate_unique_code(channel)
        now = datetime.now(timezone.utc)

        # 查找该用户在该渠道的未完成绑定记录
        existing = (
            self._db.query(ImBinding)
            .filter(
                ImBinding.user_id == user_id,
                ImBinding.channel == channel,
                ImBinding.paired_at.is_(None),
            )
            .first()
        )

        if existing is not None:
            # 覆盖旧配对码，重置 created_at（延长有效期）
            existing.pairing_code = code
            existing.created_at = now
            self._db.flush()
            logger.info(
                "im.binding.pairing_code_refreshed",
                user_id=user_id,
                channel=channel,
            )
        else:
            new_binding = ImBinding(
                user_id=user_id,
                channel=channel,
                platform_user_id="",  # IM 端配对时填入
                platform_chat_id="",   # IM 端配对时填入
                pairing_code=code,
                created_at=now,
            )
            self._db.add(new_binding)
            self._db.flush()
            logger.info(
                "im.binding.pairing_code_generated",
                user_id=user_id,
                channel=channel,
            )

        return code

    def expires_at(self) -> datetime:
        """返回配对码从现在起的过期时间（辅助工具方法，供路由层使用）。"""
        return datetime.now(timezone.utc) + timedelta(minutes=PAIRING_CODE_TTL_MINUTES)

    # ------------------------------------------------------------------
    # 完成配对（IM 端调用）
    # ------------------------------------------------------------------

    def pair(
        self,
        channel: str,
        platform_user_id: str,
        platform_chat_id: str,
        code: str,
        display_name: str | None = None,
    ) -> bool:
        """
        完成配对（由 IMGateway._handle_pairing 调用）。

        流程：
          1. 查找 im_bindings 中 channel + pairing_code 匹配的记录
          2. 校验未过期（created_at + TTL > now）
          3. 校验 paired_at is None（未使用）
          4. 填入 platform_user_id + platform_chat_id + display_name + paired_at
          5. 清除 pairing_code（一次性使用）
          6. 处理三元组唯一冲突（同 platform_user_id+chat_id 已存在绑定则拒绝）

        Returns:
            True  — 绑定成功
            False — 配对码无效、已过期或三元组冲突

        副作用：
            成功时执行 db.flush()，调用方需 commit()。
            失败时不修改 DB 状态。
        """
        binding = (
            self._db.query(ImBinding)
            .filter(
                ImBinding.channel == channel,
                ImBinding.pairing_code == code,
                ImBinding.paired_at.is_(None),
            )
            .first()
        )

        if binding is None:
            logger.info(
                "im.binding.pair_failed",
                reason="code_not_found_or_used",
                channel=channel,
                code=code,
            )
            return False

        # 校验是否过期
        now = datetime.now(timezone.utc)
        created = binding.created_at
        if created is not None:
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if now > created + timedelta(minutes=PAIRING_CODE_TTL_MINUTES):
                logger.info(
                    "im.binding.pair_failed",
                    reason="code_expired",
                    channel=channel,
                    code=code,
                )
                return False

        # 填入 IM 端信息（ADR-071 三元组唯一约束在 flush 时触发）
        binding.platform_user_id = platform_user_id
        binding.platform_chat_id = platform_chat_id
        binding.display_name = display_name
        binding.paired_at = now
        binding.pairing_code = None  # 清除配对码（一次性使用）

        try:
            self._db.flush()
        except IntegrityError:
            # 三元组 (channel, platform_user_id, platform_chat_id) 已存在
            self._db.rollback()
            logger.warning(
                "im.binding.pair_failed",
                reason="triple_conflict",
                channel=channel,
                platform_user_id=platform_user_id,
                platform_chat_id=platform_chat_id,
            )
            return False

        logger.info(
            "im.binding.paired",
            channel=channel,
            user_id=binding.user_id,
            platform_user_id=platform_user_id,
            platform_chat_id=platform_chat_id,
        )
        return True

    # ------------------------------------------------------------------
    # 列出绑定
    # ------------------------------------------------------------------

    def list_bindings(self, user_id: str) -> list[ImBinding]:
        """
        列出指定用户的所有 IM 绑定记录（含未完成绑定）。

        Returns:
            ImBinding 列表，按 created_at 降序。
        """
        return (
            self._db.query(ImBinding)
            .filter(ImBinding.user_id == user_id)
            .order_by(ImBinding.created_at.desc())
            .all()
        )

    # ------------------------------------------------------------------
    # 解除绑定
    # ------------------------------------------------------------------

    def unbind(self, user_id: str, binding_id: str) -> bool:
        """
        解除绑定（物理删除）。

        只能删除属于指定用户的绑定（所有权校验在此做，路由层不重复校验）。

        Returns:
            True  — 删除成功
            False — 记录不存在或不属于该用户
        """
        binding = self._db.get(ImBinding, binding_id)
        if binding is None or binding.user_id != user_id:
            return False

        channel = binding.channel
        self._db.delete(binding)
        self._db.flush()

        logger.info(
            "im.binding.unpaired",
            binding_id=binding_id,
            user_id=user_id,
            channel=channel,
        )
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_unique_code(self, channel: str) -> str:
        """
        生成在当前有效配对码中唯一的 6 位数字码。

        最多重试 MAX_PAIRING_RETRIES 次；超出则抛出 RuntimeError。
        碰撞的定义：同渠道已有 paired_at is None 且 pairing_code 相同的记录。
        """
        for attempt in range(MAX_PAIRING_RETRIES):
            candidate = "".join(
                str(secrets.randbelow(10)) for _ in range(PAIRING_CODE_LENGTH)
            )
            conflict = (
                self._db.query(ImBinding)
                .filter(
                    ImBinding.channel == channel,
                    ImBinding.pairing_code == candidate,
                    ImBinding.paired_at.is_(None),
                )
                .first()
            )
            if conflict is None:
                return candidate
            logger.debug(
                "im.binding.pairing_code_collision",
                channel=channel,
                attempt=attempt + 1,
            )

        raise RuntimeError(
            f"Failed to generate unique pairing code after {MAX_PAIRING_RETRIES} attempts."
        )
