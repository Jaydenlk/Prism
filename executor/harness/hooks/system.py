"""
HookSystem — 事件分发器（Task 5.3 治理层升级）

对标 CC 的 Hook 执行流程：
1. 事件触发
2. Phase 1 过滤：非 Phase 1 事件直接返回空决策（ADR-048）
3. 遍历注册的 handler（按优先级排序，priority 数字越小越先）
4. matcher 正则匹配（对 tool 事件匹配 tool_name，空 matcher 匹配所有）
5. asyncio.gather 并行执行所有匹配 handler（ADR-021）
6. merge_decisions() 合并决策（ADR-027）

注册/注销：
- register() 支持 hook_id（唯一标识）和 priority（优先级）
- unregister(hook_id) 按 ID 精确注销
- unregister_by_prefix(prefix) 按前缀批量注销（Skill/Plugin 卸载用）

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
from executor.harness.hooks.events import PHASE1_EVENTS, HookEvent
from executor.harness.hooks.handlers import HookHandlerConfig, HookHandlerExecutor

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()


class HookSystem:
    """事件驱动 Hook 分发器（优先级 + scoped 注销）"""

    def __init__(self, adapter=None, fork_manager=None):
        # event_type → list of (priority, hook_id, HookHandlerConfig)
        self._handlers: dict[str, list[tuple[int, str, HookHandlerConfig]]] = {}
        self._executor = HookHandlerExecutor(
            adapter=adapter,
            fork_manager=fork_manager,
        )

    def register(
        self,
        event_type: str,
        config: HookHandlerConfig,
        hook_id: str = "",
        priority: int = 100,
    ) -> str:
        """注册 Hook handler 到指定事件类型。

        - hook_id: 唯一标识，用于后续注销（空字符串则自动生成）
        - priority: 优先级，数字越小越先执行（默认 100）

        返回 hook_id。
        """
        if not hook_id:
            # 自动生成：保证在同一 event_type 内唯一
            hook_id = f"hook_{event_type}_{len(self._handlers.get(event_type, []))}"

        if event_type not in self._handlers:
            self._handlers[event_type] = []

        self._handlers[event_type].append((priority, hook_id, config))
        # 按优先级升序（小数字优先）
        self._handlers[event_type].sort(key=lambda x: x[0])

        logger.info(
            "harness.hook.registered",
            event_type=event_type,
            hook_id=hook_id,
            priority=priority,
            handler_type=config.type if config is not None else "none",
            matcher=(config.matcher or "(all)") if config is not None else "(all)",
        )
        return hook_id

    def unregister(self, hook_id: str) -> None:
        """按 hook_id 精确注销 handler。"""
        for event_type in self._handlers:
            self._handlers[event_type] = [
                (p, hid, c) for p, hid, c in self._handlers[event_type]
                if hid != hook_id
            ]
        logger.info("harness.hook.unregistered", hook_id=hook_id)

    def unregister_by_prefix(self, prefix: str) -> None:
        """按 hook_id 前缀批量注销（用于 Skill/Plugin 卸载）。"""
        removed = 0
        for event_type in self._handlers:
            before = len(self._handlers[event_type])
            self._handlers[event_type] = [
                (p, hid, c) for p, hid, c in self._handlers[event_type]
                if not hid.startswith(prefix)
            ]
            removed += before - len(self._handlers[event_type])
        logger.info(
            "harness.hook.unregistered_by_prefix",
            prefix=prefix,
            removed=removed,
        )

    # ------------------------------------------------------------------
    # 配置加载
    # ------------------------------------------------------------------

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
                    priority = int(entry.get("priority", 100))
                    hook_id = entry.get("hook_id", "")
                    self.register(event_type, config, hook_id=hook_id, priority=priority)
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

    # ------------------------------------------------------------------
    # 事件触发
    # ------------------------------------------------------------------

    async def fire(self, event: HookEvent) -> HookDecision:
        """触发事件，执行匹配的 handler，合并决策返回。

        Phase 1 事件过滤（ADR-048）：非 Phase 1 事件直接返回空决策。

        matcher 正则匹配 tool_name：
        - 空 matcher "" → re.search("", tool_name) 恒 True → 匹配所有
        - 非空 → re.search(matcher, tool_name) 部分匹配

        并行执行（asyncio.gather + return_exceptions=True）：
        - 异常 handler 视为空 HookDecision 继续（ADR-021）

        合并规则：merge_decisions()（ADR-027）
        """
        if event.event_type not in PHASE1_EVENTS:
            # Phase 2 事件静默跳过
            logger.debug(
                "harness.hook.phase2_event_skipped",
                event_type=event.event_type,
            )
            return HookDecision()

        triples = self._handlers.get(event.event_type, [])
        if not triples:
            return HookDecision()

        # 过滤匹配的 handler（按已排序优先级顺序）
        matched: list[HookHandlerConfig] = []
        for _priority, _hook_id, config in triples:
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
