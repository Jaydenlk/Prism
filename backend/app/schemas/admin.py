"""
Prism v2 — Admin System Stats Schemas (DOC-09 Task 9.3)

ADR-085: admin_stats_service returns SystemStatsResponse.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SystemStatsResponse(BaseModel):
    """Response for GET /admin/stats/dashboard.

    Fields:
      - runs_24h          : total runs created in the last 24 h
      - runs_7d           : total runs created in the last 7 d
      - cost_usd_7d       : total cost_usd summed over last 7 d
      - cache_savings_usd_7d : estimated cache savings over 7 d
      - harness_events_24h : {action: count} for harness.* events in 24 h
      - active_sessions   : sessions with status = 'running'
      - active_users_24h  : users with last_login_at >= 24 h ago
      - component_health  : {redis: "healthy"|"unhealthy", postgres: "healthy", ...}
      - timestamp         : when this response was generated
    """

    runs_24h: int
    runs_7d: int
    cost_usd_7d: float
    cache_savings_usd_7d: float
    harness_events_24h: dict[str, int]
    active_sessions: int
    active_users_24h: int
    component_health: dict[str, str]
    timestamp: datetime
