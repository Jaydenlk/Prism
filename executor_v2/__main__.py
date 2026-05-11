from __future__ import annotations

import asyncio
import os
import signal
import sys

import structlog

from executor_v2.callbacks import BackendCallback
from executor_v2.config import load_run_config, parse_args
from executor_v2.heartbeat import run_heartbeat
from executor_v2.hooks.prism_hook import PrismHooks
from executor_v2.runtime import PrismAgentRuntime

logger = structlog.get_logger()


async def main() -> None:
    args = parse_args()
    log = logger.bind(run_id=args.run_id)
    log.info("executor_v2.starting")

    config = load_run_config(args)

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

    hooks = PrismHooks(callback)
    runtime = PrismAgentRuntime(config, callback, hooks)

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
                pass
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
