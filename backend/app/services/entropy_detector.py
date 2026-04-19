"""
Entropy Detection — 熵漂移检测 (DOC-12 Task 12.2, ADR-112/ADR-113)

Phase 1: 半自动模式（检测 + 告警 + 人工触发清理）

8 个检测信号（ADR-112 v4 扩展，从 5 扩到 8）：
  1. 护栏触发率上升        guardrail_triggers / turn_count > 0.3
  2. 工具错误率上升        total_tool_errors / total_tool_calls > 0.2
  3. Compaction 频率上升   compaction_events / turn_count > 0.2
  4. 循环检测命中          loop_detections > 0
  5. 平均 turn_count 上升  近 7 天 vs 前 7 天增长 > 50%
  6. Provider 健康度下降   provider_failovers 日增速 > 30%（ADR-112 v4）
  7. Cache 命中率下降      cache_hit_ratio 周比下降 > 20pp（ADR-112 v4）
  8. permission_ask 超时率 permission_ask_timeout / permission_ask_total > 0.15（ADR-112 v4）

窗口约定（P0 修复）：
  current  = analytics.aggregate(days=7, offset_days=0)   # 最近 7 天
  previous = analytics.aggregate(days=7, offset_days=7)   # 7~14 天前
  两窗口不重叠，delta 计算有意义。

ThresholdCalibrator（ADR-113）：
  每周扫描 30 天 harness_summary，对每个信号计算 p90，
  平滑过渡 new = 0.7 * current + 0.3 * p90（避免阈值剧烈跳动）。
  输出建议阈值供 Admin 审核后生效。

阈值通过环境变量可配置（ENTROPY_THRESHOLD_*）。
写入 audit_logs(action: harness.entropy_alert)。
进程边界：本模块仅 import backend.app.*，不依赖 executor.*。
"""

from __future__ import annotations

import logging
import os
import statistics
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

    from sqlalchemy.orm import Session
    from app.services.harness_analytics import HarnessAnalytics

import structlog
logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# 默认阈值（阶段 1 硬阈值，环境变量可覆盖）
# ---------------------------------------------------------------------------

def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


_GUARDRAIL_RATE_THRESHOLD = _env_float("ENTROPY_THRESHOLD_GUARDRAIL_RATE", 0.3)
_TOOL_ERROR_RATE_THRESHOLD = _env_float("ENTROPY_THRESHOLD_TOOL_ERROR_RATE", 0.2)
_COMPACTION_RATE_THRESHOLD = _env_float("ENTROPY_THRESHOLD_COMPACTION_RATE", 0.2)
_TURN_COUNT_GROWTH_THRESHOLD = _env_float("ENTROPY_THRESHOLD_TURN_COUNT_GROWTH", 0.5)
_PROVIDER_FAILOVER_GROWTH_THRESHOLD = _env_float("ENTROPY_THRESHOLD_PROVIDER_FAILOVER_GROWTH", 0.3)
_CACHE_HIT_DROP_THRESHOLD = _env_float("ENTROPY_THRESHOLD_CACHE_HIT_DROP", 0.20)  # 20 pp
_PERM_ASK_TIMEOUT_THRESHOLD = _env_float("ENTROPY_THRESHOLD_PERM_ASK_TIMEOUT", 0.15)


class EntropyDetector:
    """
    Entropy 检测器 — 8 信号（ADR-112）。

    用法::

        from app.services.harness_analytics import HarnessAnalytics
        analytics = HarnessAnalytics(db)
        detector = EntropyDetector(db, analytics)
        alerts = detector.detect()

    告警写入 audit_logs(action=harness.entropy_alert)。
    返回告警列表（可能为空列表）。
    """

    # 实例级阈值（可在构造时覆盖，便于测试）
    GUARDRAIL_RATE_THRESHOLD: float = _GUARDRAIL_RATE_THRESHOLD
    TOOL_ERROR_RATE_THRESHOLD: float = _TOOL_ERROR_RATE_THRESHOLD
    COMPACTION_RATE_THRESHOLD: float = _COMPACTION_RATE_THRESHOLD
    TURN_COUNT_GROWTH_THRESHOLD: float = _TURN_COUNT_GROWTH_THRESHOLD
    PROVIDER_FAILOVER_GROWTH_THRESHOLD: float = _PROVIDER_FAILOVER_GROWTH_THRESHOLD
    CACHE_HIT_DROP_THRESHOLD: float = _CACHE_HIT_DROP_THRESHOLD
    PERM_ASK_TIMEOUT_THRESHOLD: float = _PERM_ASK_TIMEOUT_THRESHOLD

    def __init__(
        self,
        db: "Session",
        analytics: "HarnessAnalytics",
    ) -> None:
        self._db = db
        self._analytics = analytics

    # ------------------------------------------------------------------
    # 主检测方法
    # ------------------------------------------------------------------

    def detect(
        self,
        user_id: str | None = None,
        alert_dispatcher: "Any | None" = None,
    ) -> list[dict]:
        """
        执行 Entropy 检测（8 信号）。

        P0 窗口约定：
          current  = aggregate(days=7, offset_days=0)
          previous = aggregate(days=7, offset_days=7)

        Args:
            user_id:          关联用户 ID（可选）
            alert_dispatcher: AlertDispatcher 实例（可选）。
                              传入时对每个 critical/error 告警调用 dispatch()，
                              实现 IM 群 + Email 路由（ADR-120 PRD Part B §4）。

        Returns:
            告警列表，每项含 signal / current_value / threshold /
            severity / message。可能为空列表。

        副作用：每个告警写入 audit_logs（action=harness.entropy_alert）。
        """
        current = self._analytics.aggregate(
            user_id=user_id, days=7, offset_days=0
        )
        previous = self._analytics.aggregate(
            user_id=user_id, days=7, offset_days=7
        )

        alerts: list[dict] = []

        # ── Signal 1: 护栏触发率 ──────────────────────────────────────
        gr_rate = current["averages"]["guardrail_rate"]
        if gr_rate > self.GUARDRAIL_RATE_THRESHOLD:
            alerts.append(
                self._make_alert(
                    "guardrail_rate",
                    gr_rate,
                    self.GUARDRAIL_RATE_THRESHOLD,
                    f"护栏触发率 {gr_rate*100:.1f}% 超过阈值 {self.GUARDRAIL_RATE_THRESHOLD*100:.0f}%",
                )
            )

        # ── Signal 2: 工具错误率 ──────────────────────────────────────
        err_rate = current["averages"]["error_rate"]
        if err_rate > self.TOOL_ERROR_RATE_THRESHOLD:
            alerts.append(
                self._make_alert(
                    "tool_error_rate",
                    err_rate,
                    self.TOOL_ERROR_RATE_THRESHOLD,
                    f"工具错误率 {err_rate*100:.1f}% 超过阈值 {self.TOOL_ERROR_RATE_THRESHOLD*100:.0f}%",
                )
            )

        # ── Signal 3: Compaction 频率 ─────────────────────────────────
        comp_rate = current["averages"]["compaction_rate"]
        if comp_rate > self.COMPACTION_RATE_THRESHOLD:
            alerts.append(
                self._make_alert(
                    "compaction_rate",
                    comp_rate,
                    self.COMPACTION_RATE_THRESHOLD,
                    f"上下文压缩频率 {comp_rate*100:.1f}% 超过阈值 {self.COMPACTION_RATE_THRESHOLD*100:.0f}%",
                )
            )

        # ── Signal 4: 循环检测命中 ────────────────────────────────────
        loop_count = current["totals"]["loop_detections"]
        if loop_count > 0:
            alerts.append(
                self._make_alert(
                    "loop_detection",
                    float(loop_count),
                    0.0,
                    f"存在循环检测命中（{loop_count} 次）",
                )
            )

        # ── Signal 5: 平均 turn_count 上升 ───────────────────────────
        if previous["runs_analyzed"] > 0:
            curr_avg = current["averages"]["turns_per_run"]
            prev_avg = previous["averages"]["turns_per_run"]
            if prev_avg > 0:
                growth = (curr_avg - prev_avg) / prev_avg
                if growth > self.TURN_COUNT_GROWTH_THRESHOLD:
                    alerts.append(
                        self._make_alert(
                            "turn_count_growth",
                            growth,
                            self.TURN_COUNT_GROWTH_THRESHOLD,
                            (
                                f"平均循环次数增长 {growth*100:.0f}%"
                                f"（{prev_avg:.1f} → {curr_avg:.1f}）"
                            ),
                        )
                    )

        # ── Signal 6: Provider 健康度下降（ADR-112 v4）───────────────
        curr_failovers = current["totals"]["provider_failovers"]
        prev_failovers = previous["totals"]["provider_failovers"]
        if prev_failovers > 0:
            failover_growth = (curr_failovers - prev_failovers) / prev_failovers
            if failover_growth > self.PROVIDER_FAILOVER_GROWTH_THRESHOLD:
                alerts.append(
                    self._make_alert(
                        "provider_failover_growth",
                        failover_growth,
                        self.PROVIDER_FAILOVER_GROWTH_THRESHOLD,
                        (
                            f"Provider 故障转移增速 {failover_growth*100:.0f}%"
                            f"（{prev_failovers} → {curr_failovers}）"
                        ),
                    )
                )

        # ── Signal 7: Cache 命中率下降（ADR-112 v4）──────────────────
        curr_hit_ratio = current["cache_stats"]["hit_ratio"]
        prev_hit_ratio = previous["cache_stats"]["hit_ratio"]
        cache_drop = prev_hit_ratio - curr_hit_ratio  # 下降为正值
        if cache_drop > self.CACHE_HIT_DROP_THRESHOLD:
            alerts.append(
                self._make_alert(
                    "cache_hit_ratio_drop",
                    cache_drop,
                    self.CACHE_HIT_DROP_THRESHOLD,
                    (
                        f"Cache 命中率下降 {cache_drop*100:.1f} pp"
                        f"（{prev_hit_ratio*100:.1f}% → {curr_hit_ratio*100:.1f}%）"
                    ),
                )
            )

        # ── Signal 8: permission_ask 超时率（ADR-112 v4）─────────────
        perm_timeout_rate = current["averages"]["permission_ask_timeout_rate"]
        if perm_timeout_rate > self.PERM_ASK_TIMEOUT_THRESHOLD:
            alerts.append(
                self._make_alert(
                    "permission_ask_timeout_rate",
                    perm_timeout_rate,
                    self.PERM_ASK_TIMEOUT_THRESHOLD,
                    f"permission_ask 超时率 {perm_timeout_rate*100:.1f}% 超过阈值 {self.PERM_ASK_TIMEOUT_THRESHOLD*100:.0f}%",
                )
            )

        # ------------------------------------------------------------------
        # 写入 audit_logs
        # ------------------------------------------------------------------
        if alerts:
            from app.models.audit import AuditLog  # 延迟 import 避免循环
            from app.models.base import generate_uuid

            now = datetime.now(tz=timezone.utc)
            for alert in alerts:
                log = AuditLog(
                    id=generate_uuid(),
                    action="harness.entropy_alert",
                    resource_type="system",
                    resource_id=None,
                    details=alert,
                    created_at=now,
                )
                self._db.add(log)
            self._db.commit()
            logger.warning(
                "entropy_alerts_generated",
                alert_count=len(alerts),
                signals=[a["signal"] for a in alerts],
            )

        # ------------------------------------------------------------------
        # AlertDispatcher 路由（ADR-120 PRD Part B §4）
        # ------------------------------------------------------------------
        if alerts and alert_dispatcher is not None:
            import asyncio

            for alert in alerts:
                alert_severity = alert.get("severity", "warning")
                # Entropy 告警固定为 error 或 critical（PRD Part B §4）
                dispatch_severity = "critical" if alert_severity == "critical" else "error"
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # 在 async 上下文中创建 task（fire-and-forget，不阻塞检测流程）
                        asyncio.ensure_future(
                            alert_dispatcher.dispatch(
                                severity=dispatch_severity,
                                event_type="harness.entropy_alert",
                                detail=alert,
                                user_id=user_id,
                                resource_type="system",
                            )
                        )
                    else:
                        loop.run_until_complete(
                            alert_dispatcher.dispatch(
                                severity=dispatch_severity,
                                event_type="harness.entropy_alert",
                                detail=alert,
                                user_id=user_id,
                                resource_type="system",
                            )
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "entropy_detector.alert_dispatcher_failed",
                        signal=alert.get("signal"),
                        error=str(exc),
                    )

        return alerts

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def _make_alert(
        self,
        signal: str,
        value: float,
        threshold: float,
        message: str,
        severity: str = "warning",
    ) -> dict:
        return {
            "signal": signal,
            "current_value": round(value, 6),
            "threshold": threshold,
            "severity": severity,
            "message": message,
        }


# ---------------------------------------------------------------------------
# ThresholdCalibrator — ADR-113
# ---------------------------------------------------------------------------

class ThresholdCalibrator:
    """
    阈值自动校准器（ADR-113）。

    每周扫描 30 天 harness_summary，对每个信号计算 p90，
    平滑过渡 new_threshold = 0.7 * current_threshold + 0.3 * p90。

    输出建议阈值供 Admin 审核；审核通过后人工写入环境变量或配置文件。
    不自动写入——遵循 P7 可撕裂原则，避免自动修复 AI 行为引入新风险。

    用法::

        calibrator = ThresholdCalibrator(db, analytics)
        suggestions = calibrator.calibrate()
        # suggestions: {signal: {current, p90, suggested, delta}}
    """

    # EMA 权重：当前阈值 70%，p90 参考 30%
    EMA_CURRENT_WEIGHT: float = 0.7
    EMA_P90_WEIGHT: float = 0.3

    # 对应 EntropyDetector 的当前阈值（phase 1 硬阈值）
    CURRENT_THRESHOLDS: dict[str, float] = {
        "guardrail_rate": _GUARDRAIL_RATE_THRESHOLD,
        "tool_error_rate": _TOOL_ERROR_RATE_THRESHOLD,
        "compaction_rate": _COMPACTION_RATE_THRESHOLD,
        # loop_detection_count: threshold=0，p90 仅供参考，不调整
        "turns_per_run": 20.0,  # 绝对值阈值（turns/run），用于参考
        "permission_ask_timeout_rate": _PERM_ASK_TIMEOUT_THRESHOLD,
        "cache_hit_ratio": _CACHE_HIT_DROP_THRESHOLD,  # 下降 pp 阈值
    }

    def __init__(
        self,
        db: "Session",
        analytics: "HarnessAnalytics",
        scan_days: int = 30,
    ) -> None:
        self._db = db
        self._analytics = analytics
        self._scan_days = scan_days

    def calibrate(self) -> dict:
        """
        执行阈值校准，返回建议阈值字典。

        Returns::

            {
                "guardrail_rate": {
                    "current_threshold": 0.3,
                    "p90": 0.28,
                    "suggested": 0.294,   # 0.7*0.3 + 0.3*0.28
                    "delta": -0.006,
                    "sample_count": 142,
                },
                ...
            }
        """
        raw_signals = self._analytics.compute_signal_p90(days=self._scan_days)
        suggestions: dict = {}

        for signal_key, values in raw_signals.items():
            if not values:
                continue

            sorted_vals = sorted(values)
            p90_idx = max(0, int(len(sorted_vals) * 0.90) - 1)
            p90 = sorted_vals[p90_idx]

            current = self.CURRENT_THRESHOLDS.get(signal_key)
            if current is None:
                # 信号无已知阈值（如 loop_detection_count），仅报告 p90
                suggestions[signal_key] = {
                    "current_threshold": None,
                    "p90": round(p90, 6),
                    "suggested": None,
                    "delta": None,
                    "sample_count": len(values),
                }
                continue

            suggested = (
                self.EMA_CURRENT_WEIGHT * current
                + self.EMA_P90_WEIGHT * p90
            )
            suggestions[signal_key] = {
                "current_threshold": round(current, 6),
                "p90": round(p90, 6),
                "suggested": round(suggested, 6),
                "delta": round(suggested - current, 6),
                "sample_count": len(values),
            }

        logger.info(
            "threshold_calibration_complete",
            scan_days=self._scan_days,
            signals_calibrated=len(suggestions),
        )
        return suggestions
