"""
backend/app/api/v1/harness.py — Harness 管理端点

v4 设计(ADR-033 / ADR-112 / ADR-113):
- GET  /harness/config              — Harness 配置只读(admin only)
- GET  /harness/analytics           — Harness 数据聚合(当前用户或 admin 全局)
- POST /harness/entropy-check       — 手动触发 Entropy 检测(admin only)
- POST /harness/threshold-calibrate — 手动触发阈值校准(admin only)

PATCH / POST / DELETE /harness/config 均不注册 → FastAPI 默认返回 405。
config_file_path 从环境变量 HARNESS_CONFIG_PATH 读取。

进程边界：此文件允许 import executor.harness.config_loader（纯 yaml+stdlib），
但 config_loader 禁止反向 import backend.app.*。
"""

from __future__ import annotations

import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.models.user import User
from app.services.harness_analytics import HarnessAnalytics
from app.services.entropy_detector import EntropyDetector, ThresholdCalibrator

# 允许的单向 import: backend → executor.harness.config_loader (纯 yaml + stdlib)
from executor.harness.config_loader import HarnessConfigLoader

router = APIRouter(prefix="/harness", tags=["harness"])


@router.get("/config")
async def get_harness_config(
    _admin: Annotated[Any, Depends(require_admin)],
) -> dict:
    """
    返回当前 Harness effective config + source_trace(readonly)。

    - 需要 admin 身份(require_admin 依赖)
    - config_file_path 从环境变量 HARNESS_CONFIG_PATH 读取
    - 若 yaml 不存在,返回 default-only config
    - 不提供 PATCH/POST/DELETE(v4 ADR-033:禁止运行时修改)
    """
    config_file_path = os.environ.get(
        "HARNESS_CONFIG_PATH",
        "/app/config/harness_config.yaml",
    )
    loader = HarnessConfigLoader(config_file_path=config_file_path)
    cfg = loader.load()

    return {
        "effective": {
            "custom_guardrail_rules": cfg.custom_guardrail_rules,
            "permission_policies": cfg.permission_policies,
            "middleware_config": cfg.middleware_config,
            "hook_registrations": cfg.hook_registrations,
            "agent_constraints": cfg.agent_constraints,
        },
        "source_trace": cfg.source_trace,
    }

# 注:PATCH/POST/DELETE /harness/config 端点均不提供(ADR-033)
# 任何 PATCH/POST/DELETE /harness/config 请求将由 FastAPI 自动返回 405 Method Not Allowed


# ---------------------------------------------------------------------------
# ADR-112: Harness 数据聚合 + Entropy 检测端点
# ---------------------------------------------------------------------------


@router.get("/analytics")
def get_harness_analytics(
    days: int = Query(default=7, ge=1, le=90),
    offset_days: int = Query(default=0, ge=0, le=90),
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: Session = Depends(get_db),
) -> dict:
    """
    Harness 数据聚合（ADR-112）。

    - 普通用户：只聚合自己的 runs（user_id = current_user.id）
    - Admin：传 user_id=None 可聚合全局（或省略 user_id 同样按自身过滤）
    - 支持非重叠窗口查询（offset_days 参数，P0 修复）
    """
    # Admin 可通过 offset_days 滑窗对比；非 admin 按自身 user_id 过滤
    user_id = str(current_user.id) if current_user else None
    analytics = HarnessAnalytics(db)
    return analytics.aggregate(user_id=user_id, days=days, offset_days=offset_days)


@router.post("/entropy-check")
def run_entropy_check(
    _admin: Annotated[Any, Depends(require_admin)],
    db: Session = Depends(get_db),
) -> dict:
    """
    手动触发 Entropy 检测（Admin only，ADR-112）。

    - 使用非重叠窗口：current(days=7,offset=0) vs previous(days=7,offset=7)
    - 超过阈值的信号写入 audit_logs(action=harness.entropy_alert)
    - 返回告警列表（可能为空）
    """
    analytics = HarnessAnalytics(db)
    detector = EntropyDetector(db, analytics)
    alerts = detector.detect(user_id=None)
    return {"alerts": alerts, "alert_count": len(alerts)}


@router.post("/threshold-calibrate")
def run_threshold_calibrate(
    _admin: Annotated[Any, Depends(require_admin)],
    scan_days: int = Query(default=30, ge=7, le=90),
    db: Session = Depends(get_db),
) -> dict:
    """
    手动触发阈值校准（Admin only，ADR-113）。

    扫描最近 scan_days 天 harness_summary，
    对每个 Entropy 信号计算 p90，
    返回建议阈值（0.7*current + 0.3*p90）。

    仅返回建议值，不自动写入——Admin 审核后手动生效（P7 可撕裂原则）。
    """
    analytics = HarnessAnalytics(db)
    calibrator = ThresholdCalibrator(db, analytics, scan_days=scan_days)
    suggestions = calibrator.calibrate()
    return {"scan_days": scan_days, "suggestions": suggestions}
