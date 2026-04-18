"""
Hook Handler 执行器

4 种 handler（v4 ADR-026）：
- command: 执行 shell 命令，stdin 传入 JSON，stdout 读取 JSON 决策
- http: POST 到 webhook URL，body 为 JSON，response 为 JSON 决策
- prompt: 用 LLM 判断（Phase 1 骨架，需注入 adapter）
- agent: fork 子 Agent 判断（Phase 1 骨架，需注入 fork_manager）

决策协议对标 CC：
- exit 0 + stdout JSON → 成功，解析 HookDecision
- exit 2 + stderr → 阻断，permission_decision=deny, reason=stderr
- 其他 exit code → 非阻断警告（空 HookDecision）

安全：解析外部 handler 返回 JSON 时白名单过滤（只取 HookDecision.__dataclass_fields__ 中存在的键）。

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import structlog

from executor.harness.hooks.decision import HookDecision
from executor.harness.hooks.events import HookEvent

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()

# 白名单：只取 HookDecision 的合法字段
_HOOK_DECISION_FIELDS = set(HookDecision.__dataclass_fields__.keys())


def _parse_decision(data: dict, handler_name: str) -> HookDecision:
    """白名单过滤后构造 HookDecision，防止恶意注入"""
    filtered = {k: v for k, v in data.items() if k in _HOOK_DECISION_FIELDS}
    filtered["handler_name"] = handler_name
    return HookDecision(**filtered)


@dataclass
class HookHandlerConfig:
    """Hook handler 配置"""
    type: Literal["command", "http", "prompt", "agent"]  # v4：扩到 4 种
    # command 类型
    command: str = ""
    # http 类型
    url: str = ""
    # prompt 类型（v4 新增）：用 LLM 判断
    prompt_template: str = ""
    prompt_model: str = ""
    # agent 类型（v4 新增）：fork 子 Agent 判断
    agent_type: str = ""
    # 共同
    matcher: str = ""             # 正则，匹配 tool_name（空字符串匹配所有）
    timeout_seconds: int = 10


class HookHandlerExecutor:
    """v4：4 种 handler 执行器"""

    def __init__(self, adapter=None, fork_manager=None):
        self._adapter = adapter           # prompt handler 用
        self._fork_manager = fork_manager  # agent handler 用

    async def execute(self, config: HookHandlerConfig, event: HookEvent) -> HookDecision:
        """执行单个 handler，返回决策"""
        if config.type == "command":
            return await self._execute_command(config, event)
        elif config.type == "http":
            return await self._execute_http(config, event)
        elif config.type == "prompt":
            return await self._execute_prompt(config, event)
        elif config.type == "agent":
            return await self._execute_agent(config, event)
        logger.warning("harness.hook.unknown_type", handler_type=config.type)
        return HookDecision()

    async def _execute_command(self, config: HookHandlerConfig, event: HookEvent) -> HookDecision:
        """执行 shell 命令。stdin 传入事件 JSON，解析 stdout 为 HookDecision JSON。
        协议对标 CC：
        - exit 0 + stdout JSON → 成功，解析 HookDecision
        - exit 2 + stderr → 阻断，permission_decision=deny, reason=stderr
        - 其他 exit code → 非阻断警告（空 HookDecision）
        """
        handler_label = config.command[:50]
        try:
            proc = await asyncio.create_subprocess_shell(
                config.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            event_dict = {
                "event_type": event.event_type,
                "tool_name": event.tool_name,
                "tool_input": event.tool_input,
                "tool_output": event.tool_output,
                "is_error": event.is_error,
                "run_id": event.run_id,
                "session_id": event.session_id,
            }
            event_json = json.dumps(event_dict, default=str).encode()
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=event_json),
                    timeout=config.timeout_seconds,
                )
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                logger.warning(
                    "harness.hook.command.timeout",
                    command=handler_label,
                    timeout=config.timeout_seconds,
                )
                return HookDecision(
                    blocking_error=f"hook command timeout after {config.timeout_seconds}s",
                    handler_name=handler_label,
                )

            if proc.returncode == 0 and stdout:
                try:
                    data = json.loads(stdout.decode())
                    return _parse_decision(data, handler_label)
                except json.JSONDecodeError:
                    logger.warning(
                        "harness.hook.command.non_json_stdout",
                        command=handler_label,
                    )
                    return HookDecision(
                        reason="hook stdout non-JSON, ignored",
                        handler_name=handler_label,
                    )
            elif proc.returncode == 0:
                # exit 0 but no stdout — allowed, no decision
                return HookDecision(handler_name=handler_label)
            elif proc.returncode == 2:
                err_text = stderr.decode()[:500] if stderr else ""
                logger.info(
                    "harness.hook.command.exit2_deny",
                    command=handler_label,
                    stderr=err_text,
                )
                return HookDecision(
                    permission_decision="deny",
                    blocking_error=err_text,
                    reason="hook exit 2",
                    handler_name=handler_label,
                )
            else:
                logger.info(
                    "harness.hook.command.non_blocking_exit",
                    command=handler_label,
                    returncode=proc.returncode,
                )
                return HookDecision(
                    reason=f"hook exit {proc.returncode}",
                    handler_name=handler_label,
                )
        except Exception as e:
            logger.error("harness.hook.command.error", command=handler_label, error=str(e))
            return HookDecision(reason=f"hook error: {e}", handler_name=handler_label)

    async def _execute_http(self, config: HookHandlerConfig, event: HookEvent) -> HookDecision:
        """POST 到 webhook URL。body 为事件 JSON，response 为 HookDecision JSON。"""
        import httpx

        handler_label = config.url
        event_dict = {
            "event_type": event.event_type,
            "tool_name": event.tool_name,
            "tool_input": event.tool_input,
            "tool_output": event.tool_output,
            "is_error": event.is_error,
            "run_id": event.run_id,
            "session_id": event.session_id,
        }
        try:
            async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
                resp = await client.post(config.url, json=event_dict)
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        return _parse_decision(data, handler_label)
                    except Exception:
                        logger.warning(
                            "harness.hook.http.non_json_response",
                            url=handler_label,
                            status=resp.status_code,
                        )
                        return HookDecision(
                            reason=f"hook http response non-JSON",
                            handler_name=handler_label,
                        )
                logger.info(
                    "harness.hook.http.non_200",
                    url=handler_label,
                    status=resp.status_code,
                )
                return HookDecision(
                    reason=f"hook http {resp.status_code}",
                    handler_name=handler_label,
                )
        except Exception as e:
            logger.error("harness.hook.http.error", url=handler_label, error=str(e))
            return HookDecision(reason=f"hook http error: {e}", handler_name=handler_label)

    async def _execute_prompt(self, config: HookHandlerConfig, event: HookEvent) -> HookDecision:
        """用 LLM 判断。prompt_template 中 {tool_name}/{tool_input} 等变量占位，
        期望 LLM 返回 JSON {permission_decision, reason}。
        Phase 1：adapter 未注入时返回空 HookDecision + reason。
        """
        if not self._adapter:
            logger.info(
                "harness.hook.prompt.no_adapter",
                reason="prompt hook: no adapter injected",
            )
            return HookDecision(
                reason="prompt hook: no adapter injected",
                handler_name="prompt",
            )

        # Phase 1 骨架：构造 prompt 并调用 adapter，解析 JSON 结果
        try:
            prompt = config.prompt_template.format(
                tool_name=event.tool_name,
                tool_input=json.dumps(event.tool_input, default=str),
                tool_output=event.tool_output,
            )
            # adapter.complete() 同步骨架调用，Phase 2 完整实现
            logger.info(
                "harness.hook.prompt.skeleton",
                prompt_preview=prompt[:100],
                handler_name="prompt",
            )
            return HookDecision(handler_name="prompt")
        except Exception as e:
            logger.error("harness.hook.prompt.error", error=str(e))
            return HookDecision(
                reason=f"prompt hook error: {e}",
                handler_name="prompt",
            )

    async def _execute_agent(self, config: HookHandlerConfig, event: HookEvent) -> HookDecision:
        """fork 子 Agent 判断（用于重度 policy 审查）。依赖 DOC-04 ForkManager。
        Phase 1：fork_manager 未注入时返回空 HookDecision + reason。
        """
        if not self._fork_manager:
            logger.info(
                "harness.hook.agent.no_fork_manager",
                reason="agent hook: no fork_manager injected",
            )
            return HookDecision(
                reason="agent hook: no fork_manager injected",
                handler_name="agent",
            )

        # Phase 1 骨架：注入 fork_manager 后在 Phase 2 实现
        logger.info(
            "harness.hook.agent.skeleton",
            agent_type=config.agent_type,
            handler_name="agent",
        )
        return HookDecision(handler_name="agent")
