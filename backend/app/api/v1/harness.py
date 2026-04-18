"""
backend/app/api/v1/harness.py — GET /harness/config (readonly)

v4 设计(ADR-033):
- 仅提供 GET /config(readonly,admin only)
- PATCH / POST / DELETE 均不注册 → FastAPI 默认返回 405 Method Not Allowed
- config_file_path 从环境变量读取:HARNESS_CONFIG_PATH
- Backend 侧 import executor.harness.config_loader 是被允许的:
  config_loader 本身是纯 yaml + stdlib,不依赖 backend.app(单向依赖)

进程边界注意:此文件允许 import executor.harness.config_loader,
但 config_loader 本身禁止反向 import backend.app.*。
"""

from __future__ import annotations

import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.core.dependencies import require_admin

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

# 注:PATCH/POST/DELETE 端点均不提供(v4 ADR-033:禁止运行时修改)
# 任何 PATCH/POST/DELETE /harness/config 请求将由 FastAPI 自动返回 405 Method Not Allowed
