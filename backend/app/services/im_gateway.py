"""
Prism v2 — IM 网关（统一消息路由） (DOC-08 Task 8.1)

审计关注点：
  - IM 消息走与 Web 端完全相同的 TaskService.submit() 链路（无"IM 简化版"）
  - 所有消息在 route() 前经过 ADR-070 幂等检查（im_message_dedup 表）
  - Session 按 (user_id, im_channel, im_chat_id) 查找或创建，与 Web Session 独立

职责：
  1. 注册和管理所有 IM 适配器（FeishuAdapter / WeComAdapter / TelegramAdapter）
  2. 收到消息 → 幂等检查 → 查找绑定 → 查找/创建 Session → TaskService.submit()
  3. Run 完成 → 通过对应适配器回传结果（send_run_result）
  4. 结构化日志（structlog）+ Prometheus metrics
"""
from __future__ import annotations

import structlog
from sqlalchemy.orm import Session as DBSession

from app.core.config import Settings
from app.core.database import SessionLocal
from app.models.im import ImBinding, ImChannelConfig
from app.models.session import Session as SessionModel
from app.observability.metrics import (
    prism_im_messages_total,
    prism_im_webhook_duplicates_total,
)
from app.schemas.task import SubmitTaskRequest
from app.services.im_adapter import IMAdapter, IMIncomingMessage, IMOutgoingMessage
from app.services.im_dedup import IMDedupService
from app.services.task_service import TaskService

logger = structlog.get_logger(__name__)

# IM 平台消息长度限制（字符数）
_PLATFORM_MAX_LENGTH: dict[str, int] = {
    "feishu": 4000,
    "wecom": 2048,
    "telegram": 4096,
}
_DEFAULT_MAX_LENGTH = 2000


class IMGateway:
    """
    IM 网关：统一消息路由层。

    使用方式（lifespan）：
        gateway = IMGateway(settings)
        gateway.register_adapter(feishu_adapter)
        gateway.register_adapter(wecom_adapter)
        gateway.register_adapter(telegram_adapter)
        await gateway.start_all()
        ...
        await gateway.stop_all()
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._adapters: dict[str, IMAdapter] = {}

    # ------------------------------------------------------------------
    # Adapter registration
    # ------------------------------------------------------------------

    def register_adapter(self, adapter: IMAdapter) -> None:
        """
        注册 IM 适配器，并将 _handle_message 注入为消息处理回调。

        每个 channel_name 只能注册一个适配器；重复注册会覆盖旧实例。
        """
        adapter.set_message_handler(self._handle_message)
        self._adapters[adapter.channel_name] = adapter
        logger.info(
            "im.gateway.adapter_registered",
            channel=adapter.channel_name,
        )

    def get_adapter(self, channel: str) -> IMAdapter | None:
        """返回指定渠道的适配器（不存在则 None）。"""
        return self._adapters.get(channel)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start_all(self) -> None:
        """启动所有已注册的适配器（跳过 im_channel_configs.is_enabled=False 的渠道）。"""
        with SessionLocal() as db:
            enabled_channels = _get_enabled_channels(db)

        for channel, adapter in self._adapters.items():
            if channel not in enabled_channels:
                logger.info(
                    "im.gateway.adapter_skipped",
                    channel=channel,
                    reason="not_enabled_in_db",
                )
                continue
            try:
                await adapter.start()
                logger.info("im.gateway.adapter_started", channel=channel)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "im.gateway.adapter_start_failed",
                    channel=channel,
                    error=str(exc),
                )

    async def stop_all(self) -> None:
        """停止所有已注册的适配器。单个适配器停止失败不影响其他。"""
        for channel, adapter in self._adapters.items():
            try:
                await adapter.stop()
                logger.info("im.gateway.adapter_stopped", channel=channel)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "im.gateway.adapter_stop_failed",
                    channel=channel,
                    error=str(exc),
                )

    # ------------------------------------------------------------------
    # Core routing
    # ------------------------------------------------------------------

    async def _handle_message(self, msg: IMIncomingMessage) -> None:
        """
        统一消息处理入口（由适配器收到消息后回调）。

        流程：
          1. ADR-070 幂等检查（im_message_dedup 表）
          2. 配对码识别（6 位纯数字 → 触发绑定流程）
          3. 查找 im_bindings → 获取 user_id
          4. 查找/创建 Session (user_id, im_channel, im_chat_id)
          5. TaskService.submit()（与 Web 端完全相同的链路）
          6. 启动子进程（accepted_type=immediate）或发排队通知
        """
        log = logger.bind(channel=msg.channel, platform_user_id=msg.platform_user_id)

        with SessionLocal() as db:
            # ---- 1. ADR-070 Webhook 幂等 ----
            dedup = IMDedupService(db)
            if dedup.is_duplicate(msg.channel, msg.msg_id):
                prism_im_webhook_duplicates_total.labels(channel=msg.channel).inc()
                log.info("im.message.duplicate", msg_id=msg.msg_id)
                return

            prism_im_messages_total.labels(
                platform=msg.channel, status="received"
            ).inc()
            log.info(
                "im.message.received",
                msg_id=msg.msg_id,
                text_preview=msg.text[:50],
            )

            # ---- 2. 配对码识别（/pair <code> 或纯 6 位数字）----
            text = msg.text.strip()
            pairing_code: str | None = None
            if text.startswith("/pair "):
                candidate = text[6:].strip()
                if candidate.isdigit() and len(candidate) == 6:
                    pairing_code = candidate
            elif text.isdigit() and len(text) == 6:
                pairing_code = text

            if pairing_code is not None:
                await self._handle_pairing(db, msg, pairing_code)
                db.commit()
                return

            # ---- 3. 查找绑定 ----
            binding = (
                db.query(ImBinding)
                .filter(
                    ImBinding.channel == msg.channel,
                    ImBinding.platform_user_id == msg.platform_user_id,
                    ImBinding.platform_chat_id == msg.platform_chat_id,
                    ImBinding.paired_at.isnot(None),
                )
                .first()
            )

            if binding is None:
                # 未绑定 → 发绑定引导
                db.commit()
                await self._send_binding_guide(msg)
                prism_im_messages_total.labels(
                    platform=msg.channel, status="unbound"
                ).inc()
                return

            user_id = binding.user_id

            # ---- 4. 查找/创建 Session ----
            session = self._find_or_create_session(
                db, user_id, msg.channel, msg.platform_chat_id
            )

            # ---- 5. TaskService.submit()（完全相同链路）----
            result = TaskService(db, self._settings).submit(
                user_id,
                SubmitTaskRequest(
                    session_id=session.id,
                    prompt=msg.text,
                ),
            )

            # 回填 session_id 到 dedup 记录（增强可追溯性）
            dedup.update_session_id(msg.channel, msg.msg_id, session.id)

            db.commit()
            log.info(
                "im.message.routed",
                session_id=session.id,
                run_id=result.run_id,
                accepted_type=result.accepted_type,
            )

        # ---- 6. 事务提交后启动子进程 ----
        if result.accepted_type == "immediate" and result.run_id:
            self._start_run(result.run_id)
        elif result.accepted_type == "queued_query":
            adapter = self._adapters.get(msg.channel)
            if adapter:
                await adapter.send(
                    IMOutgoingMessage(
                        channel=msg.channel,
                        platform_chat_id=msg.platform_chat_id,
                        text=f"消息已收到，当前排队第 {result.queue_position} 位，请稍候。",
                    )
                )

        prism_im_messages_total.labels(
            platform=msg.channel, status="processed"
        ).inc()

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _find_or_create_session(
        self,
        db: DBSession,
        user_id: str,
        channel: str,
        chat_id: str,
    ) -> SessionModel:
        """
        按 (user_id, im_channel, im_chat_id) 查找 Session。
        不存在则创建。IM 会话的 Session 与 Web 会话独立。
        """
        session = (
            db.query(SessionModel)
            .filter(
                SessionModel.user_id == user_id,
                SessionModel.im_channel == channel,
                SessionModel.im_chat_id == chat_id,
            )
            .first()
        )

        if session is None:
            # Build a descriptive title with the IM channel prefix
            _channel_prefix = f"[{channel.capitalize()}]" if channel else "[IM]"
            session = SessionModel(
                user_id=user_id,
                title=_channel_prefix,
                status="idle",
                config_snapshot={},
                im_channel=channel,
                im_chat_id=chat_id,
            )
            db.add(session)
            db.flush()
            logger.info(
                "im.session.created",
                user_id=user_id,
                channel=channel,
                chat_id=chat_id,
                session_id=session.id,
            )

        return session

    # ------------------------------------------------------------------
    # Binding guide
    # ------------------------------------------------------------------

    async def _send_binding_guide(self, msg: IMIncomingMessage) -> None:
        """向未绑定用户发送绑定引导消息。"""
        adapter = self._adapters.get(msg.channel)
        if adapter:
            await adapter.send(
                IMOutgoingMessage(
                    channel=msg.channel,
                    platform_chat_id=msg.platform_chat_id,
                    text=(
                        "你好！请先在 Prism Web 端生成配对码，"
                        "然后发送 /pair <配对码> 完成绑定。\n"
                        "例：/pair 382947"
                    ),
                )
            )

    # ------------------------------------------------------------------
    # Pairing
    # ------------------------------------------------------------------

    async def _handle_pairing(
        self,
        db: DBSession,
        msg: IMIncomingMessage,
        pairing_code: str,
    ) -> None:
        """
        处理配对请求（Task 8.3：委托给 IMBindingService.pair()）。

        IMBindingService 负责：
          - 配对码有效性校验（未使用、未过期）
          - 三元组唯一约束冲突处理（ADR-071）
          - 填写 platform_user_id / platform_chat_id / paired_at / 清空 pairing_code
        """
        from app.services.im_binding_service import IMBindingService

        adapter = self._adapters.get(msg.channel)
        if not adapter:
            return

        svc = IMBindingService(db)
        success = svc.pair(
            channel=msg.channel,
            platform_user_id=msg.platform_user_id,
            platform_chat_id=msg.platform_chat_id,
            code=pairing_code,
        )

        if success:
            await adapter.send(
                IMOutgoingMessage(
                    channel=msg.channel,
                    platform_chat_id=msg.platform_chat_id,
                    text="绑定成功！现在可以直接发消息使用 Prism 了。",
                )
            )
        else:
            await adapter.send(
                IMOutgoingMessage(
                    channel=msg.channel,
                    platform_chat_id=msg.platform_chat_id,
                    text="配对码无效或已过期，请在 Web 端重新生成。",
                )
            )

    # ------------------------------------------------------------------
    # Run result delivery
    # ------------------------------------------------------------------

    async def send_run_result(
        self,
        session_id: str,
        text: str,
        run_status: str = "completed",
    ) -> None:
        """
        Run 完成后回传结果到 IM（由 CallbackService 在 run_complete 时调用）。

        流程：
          1. 查找 Session 的 im_channel + im_chat_id
          2. 格式化消息（截断至平台限制）
          3. 通过对应适配器发送
        """
        with SessionLocal() as db:
            session = db.get(SessionModel, session_id)
            if session is None or session.im_channel is None:
                return  # 非 IM 来源的 Session，忽略

            channel = session.im_channel
            chat_id = session.im_chat_id

        adapter = self._adapters.get(channel)
        if adapter is None:
            logger.warning(
                "im.send_run_result.no_adapter",
                channel=channel,
                session_id=session_id,
            )
            return

        # 格式化消息
        if run_status == "failed":
            content = f"[任务失败] {text}" if text else "[任务执行失败，请稍后重试]"
        else:
            content = text or "[任务已完成]"

        # 截断至平台限制
        max_len = _PLATFORM_MAX_LENGTH.get(channel, _DEFAULT_MAX_LENGTH)
        if len(content) > max_len:
            suffix = "\n\n[消息已截断，完整结果请在 Prism Web 端查看]"
            content = content[: max_len - len(suffix)] + suffix

        await adapter.send(
            IMOutgoingMessage(
                channel=channel,
                platform_chat_id=chat_id,
                text=content,
            )
        )
        logger.info(
            "im.run_result.sent",
            session_id=session_id,
            channel=channel,
            run_status=run_status,
            text_len=len(content),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _start_run(self, run_id: str) -> None:
        """
        从 app.state.process_manager 启动子进程。

        IMGateway 不持有 app 引用；使用懒导入获取全局 process_manager。
        若 ProcessManager 未初始化（测试环境），仅记录 warning。
        """
        try:
            from app.main import app

            pm = getattr(app.state, "process_manager", None)
            if pm is not None:
                pm.start_run(run_id)
            else:
                logger.warning(
                    "im.gateway.process_manager_unavailable",
                    run_id=run_id,
                )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "im.gateway.start_run_failed",
                run_id=run_id,
                error=str(exc),
            )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_enabled_channels(db: DBSession) -> set[str]:
    """返回 im_channel_configs 中 is_enabled=True 的渠道集合。"""
    rows = (
        db.query(ImChannelConfig.channel)
        .filter(ImChannelConfig.is_enabled.is_(True))
        .all()
    )
    return {row.channel for row in rows}
