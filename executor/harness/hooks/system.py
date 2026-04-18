"""
HookSystem — 事件分发器

对标 CC 的 Hook 执行流程：
1. 事件触发
2. 遍历注册的 handler（按注册顺序）
3. matcher 正则匹配（对 tool 事件匹配 tool_name，空 matcher 匹配所有）
4. asyncio.gather 并行执行所有匹配 handler（ADR-021）
5. merge_decisions() 合并决策（ADR-027）

配置加载自 .prism/hooks.json（如存在），格式对标 CC 的 .claude/settings.json hooks 字段。
.prism/hooks.json 不存在时静默跳过（log info），不 raise。

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import TYPE_CHECKING

import structlog

from executor.harness.hooks.decision import HookDecision, merge_decisions
from executor.harness.hooks.events import HookEvent
from executor.harness.hooks.handlers import HookHandlerConfig, HookHandlerExecutor

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()


class HookSystem:
    """事件驱动 Hook 分发器"""

    def __init__(self, adapter=None, fork_manager=None):
        # event_type → list of HookHandlerConfig
        self._handlers: dict[str, list[HookHandlerConfig]] = {}
        self._executor = HookHandlerExecutor(
            adapter=adapter,
            fork_manager=fork_manager,
        )

    def register(self, event_type: str, config: HookHandlerConfig) -> None:
        """注册 handler 到指定事件类型"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(config)
        logger.info(
            "harness.hook.registered",
            event_type=event_type,
            handler_type=config.type,
            matcher=config.matcher or "(all)",
        )

    def load_from_config(self, config_path: str) -> None:
        """从 .prism/hooks.json 加载 Hook 配置。
        若文件不存在，log info 跳过，不 raise。
        格式示例：
        {
            "hooks": {
                "PreToolUse": [
                    {"type": "command", "command": "./scripts/check.sh", "matcher": "bash"},
                    {"type": "http", "url": "http://localhost:9000/check"}
                ],
                "PostToolUse": [...]
            }
        }
        """
        if not os.path.isfile(config_path):
            logger.info(
                "harness.hook.config_not_found",
                path=config_path,
                message="hooks config file not found, skipping",
            )
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning(
                "harness.hook.config_load_error",
                path=config_path,
                error=str(e),
            )
            return

        hooks_data = data.get("hooks", {})
        for event_type, handler_list in hooks_data.items():
            if not isinstance(handler_list, list):
                logger.warning(
                    "harness.hook.config_invalid_entry",
                    event_type=event_type,
                    detail="expected list",
                )
                continue
            for entry in handler_list:
                if not isinstance(entry, dict):
                    continue
                handler_type = entry.get("type", "command")
                try:
                    config = HookHandlerConfig(
                        type=handler_type,
                        command=entry.get("command", ""),
                        url=entry.get("url", ""),
                        prompt_template=entry.get("prompt_template", ""),
                        prompt_model=entry.get("prompt_model", ""),
                        agent_type=entry.get("agent_type", ""),
                        matcher=entry.get("matcher", ""),
                        timeout_seconds=int(entry.get("timeout_seconds", 10)),
                    )
                    self.register(event_type, config)
                except Exception as e:
                    logger.warning(
                        "harness.hook.config_entry_error",
                        event_type=event_type,
                        error=str(e),
                    )

        logger.info(
            "harness.hook.config_loaded",
            path=config_path,
            event_types=list(hooks_data.keys()),
        )

    async def fire(self, event: HookEvent) -> HookDecision:
        """
        触发事件，执行匹配的 handler，合并决策返回。

        matcher 正则匹配 tool_name：
        - 空 matcher "" → re.search("", tool_name) 恒 True → 匹配所有
        - 非空 → re.search(matcher, tool_name) 部分匹配

        并行执行（asyncio.gather + return_exceptions=True）：
        - 异常 handler 视为空 HookDecision 继续（ADR-021）

        合并规则：merge_decisions()（ADR-027）
        """
        handlers = self._handlers.get(event.event_type, [])
        if not handlers:
            return HookDecision()

        # 过滤匹配的 handler
        matched = []
        for config in handlers:
            matcher = config.matcher
            try:
                if re.search(matcher, event.tool_name) is not None:
                    matched.append(config)
            except re.error as e:
                logger.warning(
                    "harness.hook.matcher_invalid_regex",
                    matcher=matcher,
                    error=str(e),
                )

        if not matched:
            return HookDecision()

        # 并行执行（return_exceptions=True，异常不中断其余 handler）
        results = await asyncio.gather(
            *[self._executor.execute(config, event) for config in matched],
            return_exceptions=True,
        )

        decisions: list[HookDecision] = []
        for i, r in enumerate(results):
            if isinstance(r, BaseException):
                logger.error(
                    "harness.hook.handler_exception",
                    event_type=event.event_type,
                    handler_index=i,
                    error=str(r),
                )
                decisions.append(HookDecision())
            else:
                decisions.append(r)

        try:
            from executor.observability.metrics import prism_hook_fired_total
            for config in matched:
                prism_hook_fired_total.labels(
                    event_type=event.event_type,
                    handler_type=config.type,
                ).inc()
        except Exception:
            pass  # metrics 降级不影响主路径

        return merge_decisions(decisions)
