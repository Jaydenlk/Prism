"""
Prism v2 — Usage Statistics Service (DOC-09 Task 9.2)

ADR-082: GET /providers/usage 返回 cache tokens 三字段 + cache_hit_ratio +
         estimated_cache_savings_usd + total_cost_usd + by_provider + by_model

数据来源: runs 表 input_tokens / output_tokens / cache_hit_tokens /
          cache_miss_tokens / cache_creation_tokens / cost_usd 字段

聚合维度: Provider / 模型 / 日 / 周 / 月
铁律4: get_user_usage() 严格按 user_id 过滤; get_global_usage() 仅 Admin 调用
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.provider import Provider
from app.models.run import Run

import structlog
logger = structlog.get_logger()

# Anthropic prompt cache pricing constants (approximate)
# cache_hit_tokens 节省 = 原 input price × 90%(缓存命中只收 10% 费用)
# 用 $0.30/1M tokens 作为 input baseline(Claude 3 Sonnet 近似)
_INPUT_PRICE_PER_TOKEN = 3.0e-6   # $3.00 / 1M input tokens (conservative)
_CACHE_HIT_SAVINGS_RATIO = 0.90   # 命中缓存节省 90%


def _compute_cache_savings(cache_hit_tokens: int) -> float:
    """估算 cache_hit 节省金额(USD).

    理论: 命中缓存时只收 10% 的 input 价格,节省 90%。
    用 Claude 3 Sonnet input 价格 $3.00/1M tokens 作基准。
    """
    return round(cache_hit_tokens * _INPUT_PRICE_PER_TOKEN * _CACHE_HIT_SAVINGS_RATIO, 6)


class UsageService:
    """用量统计服务.

    get_user_usage()  — 铁律4: 严格 user_id 过滤,供用户端使用
    get_global_usage() — 无 user_id 过滤,仅 Admin 调用
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def get_user_usage(
        self,
        user_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        group_by: str = "day",
    ) -> dict:
        """用户维度的用量统计.

        铁律4: WHERE user_id = :user_id 强制过滤,不可省略。

        Args:
            user_id:    当前登录用户 ID(强制隔离)
            start_date: 查询起始日期(含),默认最近 30 天
            end_date:   查询截止日期(含),默认今天
            group_by:   时间分组粒度 "day" | "week" | "month"

        Returns:
            {summary, by_provider, by_model, timeline}
        """
        start_dt, end_dt = self._resolve_date_range(start_date, end_date)

        base_q = (
            self._db.query(Run)
            .filter(
                Run.user_id == user_id,           # 铁律4: 数据隔离
                Run.status.in_(["completed", "failed"]),
                Run.created_at >= start_dt,
                Run.created_at <= end_dt,
            )
        )
        return self._build_usage_response(base_q, group_by)

    def get_global_usage(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        group_by: str = "day",
    ) -> dict:
        """全局用量统计(Admin 用).

        不做 user_id 过滤,聚合所有用户数据。
        """
        start_dt, end_dt = self._resolve_date_range(start_date, end_date)

        base_q = (
            self._db.query(Run)
            .filter(
                Run.status.in_(["completed", "failed"]),
                Run.created_at >= start_dt,
                Run.created_at <= end_dt,
            )
        )
        return self._build_usage_response(base_q, group_by)

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _resolve_date_range(
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> tuple[datetime, datetime]:
        """将 date 参数转换为 datetime(含时区)区间.

        默认: 最近 30 天(含今天)。
        """
        now = datetime.now(timezone.utc)
        if end_date is None:
            end_dt = now
        else:
            # end_date 当天末尾 23:59:59
            end_dt = datetime(
                end_date.year, end_date.month, end_date.day, 23, 59, 59,
                tzinfo=timezone.utc,
            )

        if start_date is None:
            start_dt = now - timedelta(days=30)
        else:
            start_dt = datetime(
                start_date.year, start_date.month, start_date.day, 0, 0, 0,
                tzinfo=timezone.utc,
            )

        return start_dt, end_dt

    def _build_usage_response(self, base_q, group_by: str) -> dict:
        """从 base_q 中聚合生成 ADR-082 规定的完整响应结构."""

        # --- 1. Summary totals -------------------------------------------
        totals = base_q.with_entities(
            func.count(Run.id).label("total_runs"),
            func.coalesce(func.sum(Run.input_tokens), 0).label("total_input_tokens"),
            func.coalesce(func.sum(Run.output_tokens), 0).label("total_output_tokens"),
            func.coalesce(func.sum(Run.cache_hit_tokens), 0).label("cache_hit_tokens"),
            func.coalesce(func.sum(Run.cache_miss_tokens), 0).label("cache_miss_tokens"),
            func.coalesce(func.sum(Run.cache_creation_tokens), 0).label("cache_creation_tokens"),
            func.coalesce(func.sum(Run.cost_usd), 0).label("total_cost_usd"),
        ).one()

        total_input = int(totals.total_input_tokens)
        cache_hit = int(totals.cache_hit_tokens)
        cache_miss = int(totals.cache_miss_tokens)
        cache_creation = int(totals.cache_creation_tokens)

        # cache_hit_ratio = cache_hit / (cache_hit + cache_miss)
        denominator = cache_hit + cache_miss
        cache_hit_ratio = round(cache_hit / denominator, 4) if denominator > 0 else 0.0

        estimated_savings = _compute_cache_savings(cache_hit)

        summary = {
            "total_runs": totals.total_runs,
            "total_input_tokens": total_input,
            "total_output_tokens": int(totals.total_output_tokens),
            "cache_hit_tokens": cache_hit,
            "cache_miss_tokens": cache_miss,
            "cache_creation_tokens": cache_creation,
            "cache_hit_ratio": cache_hit_ratio,
            "estimated_cache_savings_usd": estimated_savings,
            "total_cost_usd": round(float(totals.total_cost_usd), 6),
        }

        # --- 2. By provider ----------------------------------------------
        provider_rows = (
            base_q.with_entities(
                Run.provider_id,
                func.count(Run.id).label("runs"),
                func.coalesce(func.sum(Run.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(Run.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(Run.cache_hit_tokens), 0).label("cache_hit_tokens"),
                func.coalesce(func.sum(Run.cache_creation_tokens), 0).label("cache_creation_tokens"),
                func.coalesce(func.sum(Run.cost_usd), 0).label("cost_usd"),
            )
            .group_by(Run.provider_id)
            .all()
        )

        # Resolve provider names via JOIN-less lookup to avoid N+1
        provider_ids = [r.provider_id for r in provider_rows if r.provider_id]
        provider_name_map: dict[str, str] = {}
        if provider_ids:
            name_rows = (
                self._db.query(Provider.id, Provider.name)
                .filter(Provider.id.in_(provider_ids))
                .all()
            )
            provider_name_map = {r.id: r.name for r in name_rows}

        by_provider = [
            {
                "provider_id": row.provider_id,
                "provider_name": provider_name_map.get(row.provider_id, "unknown"),
                "runs": row.runs,
                "input_tokens": int(row.input_tokens),
                "output_tokens": int(row.output_tokens),
                "cache_hit_tokens": int(row.cache_hit_tokens),
                "cache_creation_tokens": int(row.cache_creation_tokens),
                "cost_usd": round(float(row.cost_usd), 6),
            }
            for row in provider_rows
        ]

        # --- 3. By model -------------------------------------------------
        model_rows = (
            base_q.with_entities(
                Run.model,
                func.count(Run.id).label("runs"),
                func.coalesce(func.sum(Run.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(Run.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(Run.cache_hit_tokens), 0).label("cache_hit_tokens"),
                func.coalesce(func.sum(Run.cost_usd), 0).label("cost_usd"),
            )
            .group_by(Run.model)
            .all()
        )

        by_model = [
            {
                "model": row.model,
                "runs": row.runs,
                "input_tokens": int(row.input_tokens),
                "output_tokens": int(row.output_tokens),
                "cache_hit_tokens": int(row.cache_hit_tokens),
                "cost_usd": round(float(row.cost_usd), 6),
            }
            for row in model_rows
        ]

        # --- 4. Timeline -------------------------------------------------
        timeline = self._build_timeline(base_q, group_by)

        return {
            "summary": summary,
            "by_provider": by_provider,
            "by_model": by_model,
            "timeline": timeline,
            "period": {
                "group_by": group_by,
            },
        }

    def _build_timeline(self, base_q, group_by: str) -> list[dict]:
        """按 group_by 粒度生成时间序列数据."""
        # 使用 PostgreSQL func.date_trunc 做时间分组
        # group_by 取值: "day" | "week" | "month"
        if group_by not in ("day", "week", "month"):
            group_by = "day"  # 防御性默认

        trunc_expr = func.date_trunc(group_by, Run.created_at).label("period")

        timeline_rows = (
            base_q.with_entities(
                trunc_expr,
                func.count(Run.id).label("runs"),
                func.coalesce(func.sum(Run.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(Run.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(Run.cache_hit_tokens), 0).label("cache_hit_tokens"),
                func.coalesce(func.sum(Run.cost_usd), 0).label("cost_usd"),
            )
            .group_by(trunc_expr)
            .order_by(trunc_expr)
            .all()
        )

        return [
            {
                "period": row.period.date().isoformat() if row.period else None,
                "runs": row.runs,
                "input_tokens": int(row.input_tokens),
                "output_tokens": int(row.output_tokens),
                "cache_hit_tokens": int(row.cache_hit_tokens),
                "cost_usd": round(float(row.cost_usd), 6),
            }
            for row in timeline_rows
        ]
