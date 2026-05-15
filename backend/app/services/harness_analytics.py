"""
Harness Summary 数据聚合 — DOC-12 Task 12.2 (ADR-112)

消费 runs.harness_summary JSONB，提供多维度统计。
schema 定义见 DOC-07 前置定义。
对缺失字段用默认值兜底（get + default），不假设所有字段存在。

窗口修复 (P0 ADR-112)：aggregate() 增加 offset_days: int = 0 参数，
确保 EntropyDetector 可使用非重叠窗口对比：
  current  = aggregate(days=7, offset_days=0)   # 最近 7 天
  previous = aggregate(days=7, offset_days=7)   # 7~14 天前

v4 扩展：聚合结果含 cache_stats（hit_tokens / miss_tokens / creation_tokens /
         hit_ratio / creation_cost_ratio / by_provider）。
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

import structlog
logger = structlog.get_logger()


class HarnessAnalytics:
    """
    HarnessAnalytics — 聚合 runs.harness_summary JSONB。

    用法::

        analytics = HarnessAnalytics(db)
        result = analytics.aggregate(days=7, offset_days=0)
    """

    def __init__(self, db: "Session") -> None:
        self._db = db

    # ------------------------------------------------------------------
    # 主聚合方法
    # ------------------------------------------------------------------

    def aggregate(
        self,
        user_id: str | None = None,
        days: int = 7,
        offset_days: int = 0,
    ) -> dict:
        """
        聚合最近 N 天的 Harness 数据。

        Args:
            user_id:     None 时聚合全局（Admin 用）；指定时按用户过滤。
            days:        聚合窗口天数（默认 7）。
            offset_days: 窗口偏移天数（P0 非重叠窗口修复）。
                         offset_days=0 → 最近 days 天；
                         offset_days=7 → 7~14 天前的 days 天。

        Returns::

            {
                "period": {
                    "start": "2026-04-12T00:00:00+00:00",
                    "end":   "2026-04-19T00:00:00+00:00",
                    "days": 7,
                    "offset_days": 0,
                },
                "runs_analyzed": 42,
                "totals": {
                    "turns": 500,
                    "tool_calls": 300,
                    "tool_errors": 15,
                    "guardrail_triggers": 8,
                    "permission_denials": 3,
                    "permission_ask_total": 10,
                    "permission_ask_timeout": 1,
                    "compaction_events": 12,
                    "loop_detections": 1,
                    "forks": 5,
                    "provider_failovers": 2,
                },
                "averages": {
                    "turns_per_run": 11.9,
                    "tool_calls_per_run": 7.1,
                    "error_rate": 0.05,
                    "guardrail_rate": 0.016,
                    "compaction_rate": 0.024,
                    "permission_ask_timeout_rate": 0.1,
                },
                "cache_stats": {
                    "hit_tokens": 120000,
                    "miss_tokens": 80000,
                    "creation_tokens": 20000,
                    "hit_ratio": 0.545,
                    "creation_cost_ratio": 0.091,
                    "by_provider": {},
                },
                "route_distribution": {
                    "direct": 35,
                    "coordinator": 7,
                    "agent_types": {"general": 30, "research": 8, "verifier": 4},
                },
                "peak_context_usage": {
                    "max": 0.92,
                    "avg": 0.65,
                    "p95": 0.85,
                },
            }
        """
        now = datetime.now(tz=timezone.utc)
        end_dt = now - timedelta(days=offset_days)
        start_dt = end_dt - timedelta(days=days)

        # ----------------------------------------------------------
        # 查询 runs 表（completed + failed，排除 pending/running）
        # ----------------------------------------------------------
        base_sql = """
            SELECT
                id,
                agent_type,
                turn_count,
                cache_hit_tokens,
                cache_miss_tokens,
                cache_creation_tokens,
                harness_summary
            FROM runs
            WHERE
                status IN ('completed', 'failed')
                AND created_at >= :start_dt
                AND created_at < :end_dt
        """
        params: dict = {"start_dt": start_dt, "end_dt": end_dt}

        if user_id is not None:
            base_sql += " AND user_id = :user_id"
            params["user_id"] = user_id

        rows = self._db.execute(text(base_sql), params).fetchall()

        return self._build_result(rows, start_dt, end_dt, days, offset_days)

    # ------------------------------------------------------------------
    # 内部计算
    # ------------------------------------------------------------------

    def _build_result(
        self,
        rows: list,
        start_dt: datetime,
        end_dt: datetime,
        days: int,
        offset_days: int,
    ) -> dict:
        runs_analyzed = len(rows)

        # Accumulate totals
        total_turns = 0
        total_tool_calls = 0
        total_tool_errors = 0
        total_guardrail_triggers = 0
        total_permission_denials = 0
        total_permission_ask = 0
        total_permission_ask_timeout = 0
        total_compaction_events = 0
        total_loop_detections = 0
        total_forks = 0
        total_provider_failovers = 0

        # cache token sums (from Run columns first, harness_summary as supplement)
        total_cache_hit = 0
        total_cache_miss = 0
        total_cache_creation = 0
        cache_by_provider: dict[str, dict] = {}

        # route distribution
        direct_count = 0
        coordinator_count = 0
        agent_type_dist: dict[str, int] = {}

        # context usage samples (for peak_context_usage)
        context_usages: list[float] = []

        for row in rows:
            # row columns: id, agent_type, turn_count, cache_hit_tokens,
            #              cache_miss_tokens, cache_creation_tokens, harness_summary
            agent_type = row[1] or "general"
            turn_count_val = row[2] or 0
            row_cache_hit = row[3] or 0
            row_cache_miss = row[4] or 0
            row_cache_creation = row[5] or 0
            summary: dict = row[6] or {}

            total_turns += turn_count_val or summary.get("turn_count", 0)
            total_tool_calls += summary.get("total_tool_calls", 0)
            total_tool_errors += summary.get("total_tool_errors", 0)
            total_guardrail_triggers += summary.get("guardrail_triggers", 0)
            total_permission_denials += summary.get("permission_denials", 0)
            total_permission_ask += summary.get("permission_ask_total", 0)
            total_permission_ask_timeout += summary.get("permission_ask_timeout", 0)
            total_compaction_events += summary.get("compaction_events", 0)
            total_loop_detections += summary.get("loop_detections", 0)
            total_forks += summary.get("forks", 0)
            total_provider_failovers += summary.get("provider_failovers", 0)

            # cache tokens — prefer Run-level columns, fall back to harness_summary
            hit = row_cache_hit or summary.get("cache_hit_tokens", 0)
            miss = row_cache_miss or summary.get("cache_miss_tokens", 0)
            creation = row_cache_creation or summary.get("cache_creation_tokens", 0)
            total_cache_hit += hit
            total_cache_miss += miss
            total_cache_creation += creation

            # cache by_provider (from harness_summary.cache_by_provider)
            for prov, pdata in summary.get("cache_by_provider", {}).items():
                if prov not in cache_by_provider:
                    cache_by_provider[prov] = {
                        "hit_tokens": 0,
                        "miss_tokens": 0,
                        "creation_tokens": 0,
                    }
                cache_by_provider[prov]["hit_tokens"] += pdata.get("hit_tokens", 0)
                cache_by_provider[prov]["miss_tokens"] += pdata.get("miss_tokens", 0)
                cache_by_provider[prov]["creation_tokens"] += pdata.get("creation_tokens", 0)

            # route distribution
            route_mode = summary.get("route_mode", "direct")
            if route_mode == "coordinator":
                coordinator_count += 1
            else:
                direct_count += 1
            agent_type_dist[agent_type] = agent_type_dist.get(agent_type, 0) + 1

            # context usage (0-1 float)
            ctx_pct = summary.get("peak_context_usage")
            if ctx_pct is not None:
                try:
                    context_usages.append(float(ctx_pct))
                except (TypeError, ValueError):
                    pass

        # ----------------------------------------------------------
        # Averages
        # ----------------------------------------------------------
        turns_per_run = (total_turns / runs_analyzed) if runs_analyzed else 0.0
        tool_calls_per_run = (total_tool_calls / runs_analyzed) if runs_analyzed else 0.0
        error_rate = (
            total_tool_errors / total_tool_calls if total_tool_calls else 0.0
        )
        guardrail_rate = (
            total_guardrail_triggers / total_turns if total_turns else 0.0
        )
        compaction_rate = (
            total_compaction_events / total_turns if total_turns else 0.0
        )
        perm_ask_timeout_rate = (
            total_permission_ask_timeout / total_permission_ask
            if total_permission_ask
            else 0.0
        )

        # ----------------------------------------------------------
        # Cache stats (ADR-112 v4 addition)
        # ----------------------------------------------------------
        total_input = total_cache_hit + total_cache_miss
        hit_ratio = total_cache_hit / total_input if total_input else 0.0
        # creation_cost_ratio: creation tokens / total_input (creation charged at 1.25x)
        creation_cost_ratio = (
            total_cache_creation / total_input if total_input else 0.0
        )

        cache_stats = {
            "hit_tokens": total_cache_hit,
            "miss_tokens": total_cache_miss,
            "creation_tokens": total_cache_creation,
            "hit_ratio": round(hit_ratio, 4),
            "creation_cost_ratio": round(creation_cost_ratio, 4),
            "by_provider": cache_by_provider,
        }

        # ----------------------------------------------------------
        # Peak context usage
        # ----------------------------------------------------------
        if context_usages:
            sorted_cu = sorted(context_usages)
            p95_idx = max(0, int(len(sorted_cu) * 0.95) - 1)
            peak_ctx = {
                "max": round(max(sorted_cu), 4),
                "avg": round(statistics.mean(sorted_cu), 4),
                "p95": round(sorted_cu[p95_idx], 4),
            }
        else:
            peak_ctx = {"max": 0.0, "avg": 0.0, "p95": 0.0}

        return {
            "period": {
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
                "days": days,
                "offset_days": offset_days,
            },
            "runs_analyzed": runs_analyzed,
            "totals": {
                "turns": total_turns,
                "tool_calls": total_tool_calls,
                "tool_errors": total_tool_errors,
                "guardrail_triggers": total_guardrail_triggers,
                "permission_denials": total_permission_denials,
                "permission_ask_total": total_permission_ask,
                "permission_ask_timeout": total_permission_ask_timeout,
                "compaction_events": total_compaction_events,
                "loop_detections": total_loop_detections,
                "forks": total_forks,
                "provider_failovers": total_provider_failovers,
            },
            "averages": {
                "turns_per_run": round(turns_per_run, 2),
                "tool_calls_per_run": round(tool_calls_per_run, 2),
                "error_rate": round(error_rate, 4),
                "guardrail_rate": round(guardrail_rate, 4),
                "compaction_rate": round(compaction_rate, 4),
                "permission_ask_timeout_rate": round(perm_ask_timeout_rate, 4),
            },
            "cache_stats": cache_stats,
            "route_distribution": {
                "direct": direct_count,
                "coordinator": coordinator_count,
                "agent_types": agent_type_dist,
            },
            "peak_context_usage": peak_ctx,
        }

    # ------------------------------------------------------------------
    # p90 scan for ThresholdCalibrator
    # ------------------------------------------------------------------

    def compute_signal_p90(self, days: int = 30) -> dict:
        """
        扫描最近 N 天所有 runs，对每个 Entropy 信号计算 p90。
        用于 ThresholdCalibrator.calibrate() 的输入数据。

        Returns::

            {
                "guardrail_rate":             [0.0, 0.01, ..., 0.35],  # per-run values
                "tool_error_rate":            [...],
                "compaction_rate":            [...],
                "loop_detection_count":       [...],
                "turns_per_run":              [...],
                "permission_ask_timeout_rate":[...],
                "cache_hit_ratio":            [...],
            }
        """
        now = datetime.now(tz=timezone.utc)
        start_dt = now - timedelta(days=days)

        sql = """
            SELECT
                turn_count,
                cache_hit_tokens,
                cache_miss_tokens,
                harness_summary
            FROM runs
            WHERE
                status IN ('completed', 'failed')
                AND created_at >= :start_dt
        """
        rows = self._db.execute(text(sql), {"start_dt": start_dt}).fetchall()

        signals: dict[str, list[float]] = {
            "guardrail_rate": [],
            "tool_error_rate": [],
            "compaction_rate": [],
            "loop_detection_count": [],
            "turns_per_run": [],
            "permission_ask_timeout_rate": [],
            "cache_hit_ratio": [],
        }

        for row in rows:
            turn_count_val = row[0] or 0
            row_cache_hit = row[1] or 0
            row_cache_miss = row[2] or 0
            summary: dict = row[3] or {}

            turns = turn_count_val or summary.get("turn_count", 0)
            tool_calls = summary.get("total_tool_calls", 0)
            tool_errors = summary.get("total_tool_errors", 0)
            guardrail_triggers = summary.get("guardrail_triggers", 0)
            compaction_events = summary.get("compaction_events", 0)
            loop_det = summary.get("loop_detections", 0)
            perm_ask = summary.get("permission_ask_total", 0)
            perm_timeout = summary.get("permission_ask_timeout", 0)
            hit = row_cache_hit or summary.get("cache_hit_tokens", 0)
            miss = row_cache_miss or summary.get("cache_miss_tokens", 0)

            signals["guardrail_rate"].append(
                guardrail_triggers / turns if turns else 0.0
            )
            signals["tool_error_rate"].append(
                tool_errors / tool_calls if tool_calls else 0.0
            )
            signals["compaction_rate"].append(
                compaction_events / turns if turns else 0.0
            )
            signals["loop_detection_count"].append(float(loop_det))
            signals["turns_per_run"].append(float(turns))
            signals["permission_ask_timeout_rate"].append(
                perm_timeout / perm_ask if perm_ask else 0.0
            )
            total_input = hit + miss
            signals["cache_hit_ratio"].append(
                hit / total_input if total_input else 0.0
            )

        return signals
