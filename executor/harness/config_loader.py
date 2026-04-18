"""
executor/harness/config_loader.py — Harness 配置加载器(v4 简化版)

配置加载器(非运行时管理器):
- 只在子进程启动时调用一次
- 无运行时 reload 逻辑
- 无 Redis pub/sub 同步
- 无 DB 读取

2 源合并策略:
  1. 代码默认(executor/harness/defaults.py 常量导入)
  2. harness_config.yaml(部署文件)

平台级规则(platform_rules.py)单独加载,不在此合并(它们独立于 Harness 配置,
属于"无论如何不可关闭的底线")。

进程边界:本模块仅依赖 stdlib + pyyaml,禁止 import backend.app.*
"""

from __future__ import annotations

import structlog
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from executor.observability.metrics import EXECUTOR_REGISTRY
from prometheus_client import Counter

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Prometheus metric: config 加载来源统计
# ---------------------------------------------------------------------------
prism_harness_config_load_total = Counter(
    "prism_harness_config_load_total",
    "Total Harness config load attempts, labelled by source (yaml / default_only).",
    ["source"],
    registry=EXECUTOR_REGISTRY,
)


# ---------------------------------------------------------------------------
# HarnessEffectiveConfig — 合并后的最终有效配置(v4 简化字段)
# ---------------------------------------------------------------------------

@dataclass
class HarnessEffectiveConfig:
    """合并后的最终有效配置(v4:6 字段)"""

    # Guardrail 自定义规则(平台级由 platform_rules.py 独立提供,这里仅含 yaml 补充)
    custom_guardrail_rules: list = field(default_factory=list)

    # Permission 策略:tool_name → "allow" | "deny" | "ask"
    permission_policies: dict = field(default_factory=dict)

    # Middleware 启停 + 参数:mw_name → {enabled, params}
    middleware_config: dict = field(default_factory=dict)

    # Hook 注册列表
    hook_registrations: list = field(default_factory=list)

    # Agent 行为约束:agent_type → [constraint_text]
    agent_constraints: dict = field(default_factory=dict)

    # 每字段的来源标注(debug 用): key → "default" | "yaml"
    source_trace: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# HarnessConfigLoader — 启动时一次性加载,运行时不变
# ---------------------------------------------------------------------------

class HarnessConfigLoader:
    """v4:启动时一次性加载,运行时不变"""

    def __init__(self, config_file_path: str | None):
        self._config_file_path = config_file_path

    def load(self) -> HarnessEffectiveConfig:
        """
        合并 2 源,返回 effective config。
        source_trace 对每字段标注来源("default" | "yaml")。

        行为:
        - yaml 路径为 None 或文件不存在 → 返回代码默认(不 raise)
        - yaml 文件存在但解析失败 → raise RuntimeError(快速失败,不吞错)
        - yaml 字段中 "ask_user" 值归一化为 "ask"
        """
        from executor.harness.defaults import (
            DEFAULT_PERMISSION_POLICIES,
            DEFAULT_MIDDLEWARE_CONFIG,
            DEFAULT_AGENT_CONSTRAINTS,
        )

        # ------------------------------------------------------------------
        # 步骤 1: 用代码默认填充,打 source_trace="default"
        # ------------------------------------------------------------------
        cfg = HarnessEffectiveConfig(
            custom_guardrail_rules=[],
            permission_policies=dict(DEFAULT_PERMISSION_POLICIES),
            middleware_config={
                k: dict(v) for k, v in DEFAULT_MIDDLEWARE_CONFIG.items()
            },
            agent_constraints={
                k: list(v) for k, v in DEFAULT_AGENT_CONSTRAINTS.items()
            },
        )

        for k in cfg.permission_policies:
            cfg.source_trace[f"permission_policies.{k}"] = "default"
        for k in cfg.middleware_config:
            cfg.source_trace[f"middleware_config.{k}"] = "default"
        for k in cfg.agent_constraints:
            cfg.source_trace[f"agent_constraints.{k}"] = "default"

        # ------------------------------------------------------------------
        # 步骤 2: yaml 覆盖(仅当路径存在时)
        # ------------------------------------------------------------------
        yaml_path = self._config_file_path
        if yaml_path and Path(yaml_path).exists():
            try:
                with open(yaml_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            except yaml.YAMLError as exc:
                logger.error(
                    "harness.config.load_failed",
                    config_file_path=yaml_path,
                    error=str(exc),
                )
                raise RuntimeError(
                    f"harness_config.yaml 解析失败,快速失败(不吞错): {exc}"
                ) from exc
            except Exception as exc:
                logger.error(
                    "harness.config.load_failed",
                    config_file_path=yaml_path,
                    error=str(exc),
                )
                raise RuntimeError(
                    f"harness_config.yaml 读取失败: {exc}"
                ) from exc

            # 2a. guardrails.custom_rules
            for rule in data.get("guardrails", {}).get("custom_rules", []):
                cfg.custom_guardrail_rules.append(rule)
                cfg.source_trace[f"guardrail.{rule.get('id', '?')}"] = "yaml"

            # 2b. permissions.tool_overrides
            for tool, policy in (
                data.get("permissions", {}).get("tool_overrides", {}).items()
            ):
                # 归一化 ask_user → ask
                if isinstance(policy, str):
                    policy = policy.replace("ask_user", "ask")
                cfg.permission_policies[tool] = policy
                cfg.source_trace[f"permission_policies.{tool}"] = "yaml"

            # 2c. middlewares
            for mw, params in data.get("middlewares", {}).items():
                cfg.middleware_config[mw] = params
                cfg.source_trace[f"middleware_config.{mw}"] = "yaml"

            # 2d. agent_constraints
            for agent_type, constraints in data.get("agent_constraints", {}).items():
                cfg.agent_constraints[agent_type] = constraints
                cfg.source_trace[f"agent_constraints.{agent_type}"] = "yaml"

            # 2e. hooks.registrations
            for hook in data.get("hooks", {}).get("registrations", []):
                cfg.hook_registrations.append(hook)
                cfg.source_trace[f"hook.{hook.get('event', '?')}"] = "yaml"

            prism_harness_config_load_total.labels(source="yaml").inc()
            logger.info(
                "harness.config.loaded",
                source="yaml",
                config_file_path=yaml_path,
                permission_count=len(cfg.permission_policies),
                middleware_count=len(cfg.middleware_config),
            )

        else:
            # yaml 不存在或未提供 → default only
            prism_harness_config_load_total.labels(source="default_only").inc()
            logger.info(
                "harness.config.loaded",
                source="default_only",
                config_file_path=yaml_path,
                permission_count=len(cfg.permission_policies),
                middleware_count=len(cfg.middleware_config),
            )

        return cfg
