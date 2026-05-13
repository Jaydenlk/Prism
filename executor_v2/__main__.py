from __future__ import annotations

import asyncio
import os
import signal
import sys

import structlog

from executor_v2.callbacks import BackendCallback
from executor_v2.config import RunConfig, load_run_config, parse_args
from executor_v2.heartbeat import run_heartbeat
from executor_v2.hooks.builtin.guardrail import post_guardrail, pre_guardrail
from executor_v2.hooks.builtin.observability import observability_handler
from executor_v2.hooks.builtin.permission import permission_handler
from executor_v2.hooks.builtin.safety import safety_handler
from executor_v2.hooks.memory_hook import MemoryHook
from executor_v2.hooks.router_hook import RouterHook
from executor_v2.hooks.verify_hook import VerifyHook
from executor_v2.hooks.prism_hook import PrismHooks
from executor_v2.hooks.registry import (
    POST_TOOL_USE,
    POST_TOOL_USE_FAILURE,
    PRE_TOOL_USE,
    HookHandler,
    HookRegistry,
)
from executor_v2.runtime import PrismAgentRuntime
from executor_v2.userbrain.memory import MemoryManager

logger = structlog.get_logger()


def build_registry(callback: BackendCallback, user_id: str, prompt: str) -> HookRegistry:
    registry = HookRegistry()
    prism = PrismHooks(callback)

    registry.register(PRE_TOOL_USE, HookHandler(callback=permission_handler, priority=10, category="permission"))
    registry.register(PRE_TOOL_USE, HookHandler(callback=pre_guardrail, priority=20, category="guardrail"))
    registry.register(PRE_TOOL_USE, HookHandler(callback=prism.on_pre_tool_use, priority=50, category="observability"))

    registry.register(POST_TOOL_USE, HookHandler(callback=post_guardrail, priority=20, category="guardrail"))
    registry.register(POST_TOOL_USE, HookHandler(callback=safety_handler, priority=30, category="safety"))
    registry.register(POST_TOOL_USE, HookHandler(callback=prism.on_post_tool_use, priority=50, category="observability"))

    registry.register(POST_TOOL_USE_FAILURE, HookHandler(callback=safety_handler, priority=30, category="safety"))
    registry.register(POST_TOOL_USE_FAILURE, HookHandler(callback=prism.on_post_tool_use_failure, priority=50, category="observability"))

    for event in [PRE_TOOL_USE, POST_TOOL_USE, POST_TOOL_USE_FAILURE]:
        registry.register(event, HookHandler(callback=observability_handler, priority=999, category="observability"))

    memory_hook = MemoryHook(MemoryManager(), user_id)
    memory_hook.register(registry)

    router_hook = RouterHook(prompt=prompt, user_id=user_id)
    router_hook.register(registry)

    verify_hook = VerifyHook(prompt=prompt, user_id=user_id)
    verify_hook.register(registry)

    return registry, router_hook


async def main() -> None:
    args = parse_args()
    log = logger.bind(run_id=args.run_id)
    log.info("executor_v2.starting")

    config = load_run_config(args)
    log = log.bind(user_id=config.user_id, session_id=config.session_id)

    callback = BackendCallback(
        callback_url=config.callback_url,
        callback_secret=config.callback_secret,
        run_id=config.run_id,
        session_id=config.session_id,
        redis_url=config.redis_url,
    )

    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        run_heartbeat(
            redis_url=config.redis_url,
            run_id=config.run_id,
            stop_event=stop_event,
            interval=int(os.environ.get("HEARTBEAT_INTERVAL_SECONDS", "5")),
            ttl=int(os.environ.get("HEARTBEAT_TTL_SECONDS", "60")),
        )
    )

    memory_prompt = ""
    memories: list[dict] = []
    try:
        mem = await asyncio.wait_for(
            asyncio.to_thread(MemoryManager, api_key=config.api_key, base_url=config.base_url, model=config.model),
            timeout=20,
        )
        memories = await asyncio.wait_for(mem.recall(config.user_id, config.prompt), timeout=15)
        memory_prompt = mem.build_prompt_section(memories)
    except Exception as exc:
        log.warning("memory_init_skipped", error=str(exc))

    # Classify intent BEFORE runtime (same pattern as memory recall)
    from executor_v2.userbrain.router import IntentRouter
    intent = await IntentRouter().classify(config.prompt, memories)
    from executor_v2.hooks.router_hook import _load_skills
    skills = _load_skills()
    matched_skill = skills.get(intent.category, skills["chat"])
    skill_prompt = getattr(matched_skill, "system_prompt_addition", "")
    log.info("intent.classified", category=intent.category, skill=getattr(matched_skill, "name", ""))

    combined_prompt = "\n\n".join(p for p in [memory_prompt, skill_prompt] if p)

    registry, _ = build_registry(callback, config.user_id, config.prompt)
    runtime = PrismAgentRuntime(config, callback, registry, memory_prompt=combined_prompt)

    shutdown_task: asyncio.Task[None] | None = None

    def handle_signal() -> None:
        nonlocal shutdown_task
        if shutdown_task is None or shutdown_task.done():
            shutdown_task = asyncio.create_task(_shutdown(runtime, stop_event))

    if sys.platform != "win32":
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, handle_signal)

    terminal_sent = False
    try:
        await runtime.run()
        terminal_sent = True
    except Exception as exc:
        log.error("executor_v2.failed", error=str(exc))
        if not terminal_sent:
            try:
                await callback.run_error(str(exc))
            except Exception:
                log.warning("executor_v2.error_callback_failed", exc_info=True)
    finally:
        stop_event.set()
        try:
            await heartbeat_task
        except Exception:
            log.warning("heartbeat_task_error", exc_info=True)
        await callback.close()
        log.info("executor_v2.stopped")


async def _shutdown(runtime: PrismAgentRuntime, stop_event: asyncio.Event) -> None:
    logger.info("executor_v2.shutdown_signal")
    await runtime.interrupt()
    stop_event.set()


if __name__ == "__main__":
    asyncio.run(main())
