"""
路由决策准确率分析 (DOC-12 Task 12.1)

追踪指标：用户手动覆盖 agent_type 的比例。

如果用户频繁手动指定 agent_type（而非让 TaskRouter 自动选择），
说明自动路由不够准确。

数据来源：
  runs.harness_summary JSONB 中的 route_mode / route_agent_type / route_reason。
  - route_reason 包含 "显式指定" → 用户覆盖
  - route_reason 包含 "关键词匹配" 或 "默认路由" → 自动路由

ADR-110/111 范围：路由分析为 TokenEstimator/ResourceMonitor 的辅助统计，
便于 Task 12.2 Harness 聚合分析消费。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.run import Run

import structlog
logger = structlog.get_logger()

# route_reason 关键词 — 判断是否用户显式覆盖
_OVERRIDE_KEYWORDS = ("显式指定", "explicit", "user_override", "manual")
_AUTO_KEYWORDS = ("关键词匹配", "默认路由", "keyword", "default")


class RouteAnalytics:
    """路由决策准确率分析。

    分析 runs 表中 harness_summary JSONB 的路由信息，
    统计自动路由 vs 用户手动覆盖的比例。
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_accuracy_stats(self, days: int = 30) -> dict:
        """统计最近 N 天的路由准确率。

        Returns::

            {
                "total_runs": 100,
                "auto_routed": 85,        # 自动路由次数
                "user_overridden": 15,    # 用户手动覆盖次数
                "unknown": 0,             # route_reason 未记录次数
                "auto_route_rate": 0.85,  # 自动路由率（越高越好）
                "override_rate": 0.15,    # 手动覆盖率（越低越好）
                "override_breakdown": {   # 按 agent_type 的覆盖分布
                    "research": 8,
                    "verifier": 5,
                    "planner": 2,
                },
                "period_days": 30,
                "since": "2026-03-20T00:00:00+00:00",
            }
        """
        since = datetime.now(tz=timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        # Compute start boundary
        from datetime import timedelta

        since = since - timedelta(days=days)

        stmt = (
            select(Run.agent_type, Run.harness_summary)
            .where(Run.created_at >= since)
            .where(Run.harness_summary.isnot(None))
        )
        rows = self._db.execute(stmt).fetchall()

        total = 0
        auto_count = 0
        override_count = 0
        unknown_count = 0
        override_breakdown: dict[str, int] = defaultdict(int)

        for agent_type, harness_summary in rows:
            total += 1
            route_reason: str = ""
            if isinstance(harness_summary, dict):
                route_reason = harness_summary.get("route_reason", "") or ""

            if any(kw in route_reason for kw in _OVERRIDE_KEYWORDS):
                override_count += 1
                if agent_type:
                    override_breakdown[agent_type] += 1
            elif any(kw in route_reason for kw in _AUTO_KEYWORDS):
                auto_count += 1
            else:
                # route_reason 未记录或格式未知
                unknown_count += 1
                auto_count += 1  # 默认计为自动路由（保守估计）

        auto_rate = (auto_count / total) if total > 0 else 0.0
        override_rate = (override_count / total) if total > 0 else 0.0

        return {
            "total_runs": total,
            "auto_routed": auto_count,
            "user_overridden": override_count,
            "unknown": unknown_count,
            "auto_route_rate": round(auto_rate, 4),
            "override_rate": round(override_rate, 4),
            "override_breakdown": dict(override_breakdown),
            "period_days": days,
            "since": since.isoformat(),
        }

    def get_agent_type_distribution(self, days: int = 7) -> dict:
        """统计最近 N 天各 agent_type 的使用分布。

        Returns::

            {
                "general": 60,
                "research": 20,
                "planner": 10,
                ...
            }
        """
        from datetime import timedelta

        since = datetime.now(tz=timezone.utc) - timedelta(days=days)

        stmt = (
            select(Run.agent_type, func.count(Run.id).label("cnt"))
            .where(Run.created_at >= since)
            .where(Run.agent_type.isnot(None))
            .group_by(Run.agent_type)
            .order_by(text("cnt DESC"))
        )
        rows = self._db.execute(stmt).fetchall()
        return {row.agent_type: row.cnt for row in rows}
