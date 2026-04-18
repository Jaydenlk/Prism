"""
HarnessLifecycle — 组装 Hook System + Permission Engine + Guardrails + Ask Protocol

提供给 __main__.py 一次性构造所有治理组件，简化启动逻辑。

参数：
- redis_url: str
- callback: BackendCallback
- hooks_config_path: str（默认 ".prism/hooks.json"）
- adapter: 可选，prompt handler 用
- fork_manager: 可选，agent handler 用

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from executor.harness.guardrails.engine import GuardrailsEngine
from executor.harness.hooks.system import HookSystem
from executor.harness.permissions.ask_protocol import PermissionAskProtocol
from executor.harness.permissions.engine import PermissionEngine

if TYPE_CHECKING:
    from executor.callbacks.backend_callback import BackendCallback

logger = structlog.get_logger()


class HarnessLifecycle:
    """组装治理核心组件的生命周期管理器"""

    def __init__(
        self,
        redis_url: str,
        callback: "BackendCallback",
        hooks_config_path: str = ".prism/hooks.json",
        adapter=None,
        fork_manager=None,
    ) -> None:
        self._redis_url = redis_url
        self._callback = callback
        self._hooks_config_path = hooks_config_path

        # 构造 GuardrailsEngine（自动加载 4 条平台规则）
        self._guardrails = GuardrailsEngine()

        # 构造 HookSystem（加载 .prism/hooks.json，不存在时静默跳过）
        self._hook_system = HookSystem(adapter=adapter, fork_manager=fork_manager)
        self._hook_system.load_from_config(hooks_config_path)

        # 构造 PermissionAskProtocol（Redis BLPOP 反向通信，ADR-028）
        self._ask_protocol = PermissionAskProtocol(
            redis_url=redis_url,
            callback=callback,
        )

        # 构造 PermissionEngine（两层：Guardrails + Hook）
        self._permission_engine = PermissionEngine(
            guardrails=self._guardrails,
            hook_system=self._hook_system,
            ask_protocol=self._ask_protocol,
        )

        logger.info(
            "harness.lifecycle.initialized",
            hooks_config=hooks_config_path,
        )

    def get_hook_system(self) -> HookSystem:
        """返回 HookSystem 实例"""
        return self._hook_system

    def get_permission_engine(self) -> PermissionEngine:
        """返回 PermissionEngine 实例"""
        return self._permission_engine

    def get_guardrails_engine(self) -> GuardrailsEngine:
        """返回 GuardrailsEngine 实例"""
        return self._guardrails

    async def close(self) -> None:
        """释放资源（Redis 连接等）"""
        await self._ask_protocol.close()
        logger.info("harness.lifecycle.closed")
