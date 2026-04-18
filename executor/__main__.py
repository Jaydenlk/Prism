"""
Prism v2 Agent 执行器入口（v4）

用法：python -m executor --run-id=019... --session-id=... --user-id=... \\
                         --callback-url=http://... --callback-secret=... \\
                         --redis-url=redis://... [--resume-from-step=N] [--otel-trace-id=...]

命令行参数（7 个）：
- --run-id:          Run UUID7（必须）
- --session-id:      Session UUID7（必须）
- --user-id:         User UUID7（必须）
- --callback-url:    Backend 内部回调地址（必须）
- --callback-secret: CALLBACK_SECRET，X-Callback-Secret 头（必须，独立于 JWT_SECRET/ENCRYPTION_KEY）
- --redis-url:       Redis 连接 URL（必须）
- --resume-from-step: Coordinator 恢复执行起点（可选，DOC-07 Task 7.4）
- --otel-trace-id:   跨进程 trace 传播（可选）

环境变量（由 Backend subprocess 启动时注入，见 DOC-01 v4 §9.1）：
- ENCRYPTION_KEY:      AES-256-GCM，用于 Provider API Key 解密
- PRISM_RUN_ID / PRISM_SESSION_ID / PRISM_USER_ID：上下文冗余（命令行优先）
- HEARTBEAT_INTERVAL_SECONDS：心跳间隔（默认 5）
- HEARTBEAT_TTL_SECONDS：心跳 Key TTL（默认 60）
- OTEL_TRACE_ID（可选）：跨进程 trace 传播

生命周期：
1. 解析命令行参数
2. FROM_DB: 从 DB 读取 Run 配置 + Provider（独立 DB session，DOC-07 Task 7.4）
3. 初始化 Adapter + PromptAssembler + ToolRegistry + Pipeline + Budget
4. v4：启动 heartbeat writer task（asyncio.create_task，每 5s SETEX harness:heartbeat:*）
5. 初始化 Harness Runtime（Middleware + Hook + Permission + Guardrails，Task 3.2-3.4）
6. 初始化 QueryEngine（按 agent_type 选 MAX_TURNS）
7. SIGTERM 处理（graceful cancel）
8. 执行 QueryEngine.run()
9. 停止心跳，清理资源

ADR-020：Harness 单实例，只在子进程内实例化，Backend 不持有任何 Harness 对象。
ADR-023：子进程启动时 asyncio.create_task(heartbeat_writer())，每 5s SETEX；
         Backend HeartbeatMonitor 每 10s SCAN，超 30s 无更新 → 标记 Run crashed。

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import time

import redis.asyncio as redis_async
import structlog

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# 心跳配置（ADR-023）
# ---------------------------------------------------------------------------
HEARTBEAT_INTERVAL = int(os.environ.get("HEARTBEAT_INTERVAL_SECONDS", "5"))
HEARTBEAT_TTL = int(os.environ.get("HEARTBEAT_TTL_SECONDS", "60"))

# ---------------------------------------------------------------------------
# MAX_TURNS 按 agent_type 分档（ADR-024）
# chat=50 / explore=30 / build=100 / coordinator=200 / verifier=20 / plugin_builder=40
# ---------------------------------------------------------------------------
MAX_TURNS_BY_AGENT_TYPE: dict[str, int] = {
    "chat": 50,
    "explore": 30,
    "build": 100,
    "coordinator": 200,
    "verifier": 20,
    "plugin_builder": 40,
}


async def heartbeat_writer(
    run_id: str, redis_url: str, stop_event: asyncio.Event
) -> None:
    """心跳 writer task（ADR-023）

    每 HEARTBEAT_INTERVAL 秒向 Redis 写 `harness:heartbeat:{run_id}` key，
    值为当前 Unix 时间戳（秒），TTL=HEARTBEAT_TTL（默认 60s）。

    Backend HeartbeatMonitor：
    - 每 10s SCAN harness:heartbeat:*
    - 超 30s 无更新 → 标记 Run crashed，promote 队列

    stop_event.set() 后：
    1. 退出 while 循环
    2. finally 块 DELETE key（优雅清理）
    3. aclose Redis 连接
    """
    r = redis_async.from_url(redis_url)
    try:
        while not stop_event.is_set():
            try:
                await r.setex(
                    f"harness:heartbeat:{run_id}",
                    HEARTBEAT_TTL,
                    str(int(time.time())),
                )
            except Exception as e:
                logger.warning(
                    "harness.heartbeat.write_failed", run_id=run_id, error=str(e)
                )

            # 等待 stop_event 或超时（HEARTBEAT_INTERVAL 秒后继续下一轮）
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=HEARTBEAT_INTERVAL)
            except asyncio.TimeoutError:
                continue  # 超时：正常，继续下一轮心跳
            # stop_event.set() 时 wait_for 返回（无 TimeoutError），退出循环
            break
    finally:
        # 优雅清理：删除心跳 key，释放连接
        try:
            await r.delete(f"harness:heartbeat:{run_id}")
        except Exception:
            pass
        await r.aclose()


async def main() -> None:
    """执行器主入口"""
    parser = argparse.ArgumentParser(
        description="Prism v2 Agent Executor — TAOR 主循环子进程"
    )
    parser.add_argument("--run-id", required=True, help="Run UUID7")
    parser.add_argument("--session-id", required=True, help="Session UUID7")
    parser.add_argument("--user-id", required=True, help="User UUID7")
    parser.add_argument("--callback-url", required=True, help="Backend 内部回调地址")
    parser.add_argument(
        "--callback-secret",
        required=True,
        help="CALLBACK_SECRET（独立于 JWT_SECRET/ENCRYPTION_KEY）",
    )
    parser.add_argument("--redis-url", required=True, help="Redis 连接 URL")
    parser.add_argument(
        "--resume-from-step",
        type=int,
        default=None,
        help="Coordinator 恢复执行起点（DOC-07 v4 Task 7.4）",
    )
    parser.add_argument(
        "--otel-trace-id", default=None, help="跨进程 OTel trace 传播（可选）"
    )
    args = parser.parse_args()

    # FROM_DB: 从 DB 读取 Run 配置（独立 session，DOC-07 Task 7.4 实现）
    # async with AsyncSessionFactory() as db:
    #     run = await db.get(Run, args.run_id)
    #     provider = await db.get(Provider, run.provider_id)

    # FROM_DB: Adapter 初始化（ProviderManager 用 ENCRYPTION_KEY 解密 API Key）
    # from executor.adapters.provider_manager import ProviderManager
    # adapter = ProviderManager.get_adapter(provider)

    # FROM_DB: 组件装配
    # from executor.engine.token_estimator_adapter import DriverTokenEstimator
    # from executor.engine.context_budget import ContextBudgetManager
    # from executor.engine.prompt_assembler import PromptAssembler
    # from executor.tools.registry import ToolRegistry
    # from executor.tools.builtin import register_builtin_tools
    # from executor.tools.pipeline import ToolExecutionPipeline
    # from executor.engine.query_engine import QueryEngine, RunContext
    #
    # estimator = DriverTokenEstimator(adapter)
    # budget = ContextBudgetManager(estimator=estimator, max_context_tokens=provider.max_context_tokens)
    # registry = ToolRegistry()
    # register_builtin_tools(registry)
    # assembler = PromptAssembler(agent_type=run.agent_type, tools=registry.list_definitions())
    # pipeline = ToolExecutionPipeline(registry, budget)

    # 1b. Structured logging (ADR-118, DOC-12 Task 12.6)
    # Must be initialised before any other logging so all log records are JSON.
    from executor.observability.logging import bind_run_context, init_logging as _init_logging

    _prism_env = os.environ.get("PRISM_ENV", "production")
    _dev_mode = _prism_env == "development"
    _log_level = "DEBUG" if _dev_mode else "INFO"
    _init_logging(level=_log_level, dev_mode=_dev_mode)

    # Bind run-level context so every subsequent log record carries these fields.
    bind_run_context(
        run_id=args.run_id,
        session_id=args.session_id,
        user_id=args.user_id,
        agent_type="general",  # updated after DB read / TaskRouter in full integration
        trace_id=args.otel_trace_id,
    )

    # 1c. OTel Tracing setup (ADR-117, DOC-12 Task 12.5)
    # init_tracing() returns a Context derived from the traceparent argv so all
    # spans in this process are children of the Backend "run" span.
    from executor.observability.tracing import SpanAttr, SpanName, init_tracing  # noqa: F401

    _otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    _parent_ctx = init_tracing(
        otlp_endpoint=_otel_endpoint or None,
        traceparent=args.otel_trace_id,
        prism_env=_prism_env,
    )
    logger.info(
        "harness.tracing.initialized",
        otlp_endpoint=_otel_endpoint or "stdout(dev)",
        has_parent_context=bool(args.otel_trace_id),
    )

    # 3. BackendCallback（双通道：Redis 高频直通 + HTTP 关键事件重试）
    from executor.callbacks.backend_callback import BackendCallback
    from executor.router import TaskRouter

    # 5. TaskRouter 路由决策（ADR-041 Phase 1 关键词匹配）
    # FROM_DB: prompt = run.prompt, explicit_agent_type = run.agent_type (if pre-set)
    # _router = TaskRouter()
    # _route = _router.route(run.prompt, explicit_agent_type=run.agent_type or None)
    # agent_type = _route.agent_type
    # use_coordinator = (_route.mode == "coordinator")

    callback = BackendCallback(
        callback_url=args.callback_url,
        callback_secret=args.callback_secret,
        run_id=args.run_id,
        session_id=args.session_id,
        redis_url=args.redis_url,
    )

    # 4. 心跳 writer（ADR-023）
    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        heartbeat_writer(args.run_id, args.redis_url, stop_event)
    )

    # 5. Harness Runtime（Task 3.2-3.4 实现）
    # HARNESS_INTEGRATION_POINT: MiddlewarePipeline 在 Task 3.2 注入
    # from executor.harness.middleware.pipeline import MiddlewarePipeline
    # from executor.harness.hooks.system import HookSystem
    # from executor.harness.permissions.engine import PermissionEngine
    # from executor.harness.guardrails.engine import GuardrailsEngine
    # middleware = MiddlewarePipeline([...])
    # hook_system = HookSystem.load_from_config(...)
    # permission_engine = PermissionEngine(redis_url=args.redis_url, callback=callback)

    # 6. QueryEngine（按 agent_type 选 MAX_TURNS，ADR-024）
    # FROM_DB: agent_type = run.agent_type
    # max_turns = MAX_TURNS_BY_AGENT_TYPE.get(agent_type, 50)
    # run_context = RunContext(run_id=args.run_id, session_id=args.session_id, user_id=args.user_id)
    # engine = QueryEngine(
    #     adapter=adapter,
    #     assembler=assembler,
    #     pipeline=pipeline,
    #     budget=budget,
    #     callback=callback,
    #     run_context=run_context,
    #     max_turns=max_turns,
    # )

    # 7. SIGTERM 处理（graceful cancel）
    # engine 暂为占位（DOC-07 Task 7.4 接入 DB 后实例化）
    # 此处定义 _sigterm 但 engine 引用在真正连接 DB 后才有效
    _engine_holder: list = []  # mutable container for closure

    def _sigterm(*_: object) -> None:
        logger.info("harness.subprocess.sigterm_received", run_id=args.run_id)
        stop_event.set()
        # graceful cancel：若 engine 已实例化则通知其取消
        if _engine_holder:
            loop = asyncio.get_event_loop()
            loop.create_task(_engine_holder[0].cancel(graceful=True))

    signal.signal(signal.SIGTERM, _sigterm)

    # 8. 执行 — root span wraps the entire run (ADR-117 span tree)
    from opentelemetry import trace as _otel_trace

    _tracer = _otel_trace.get_tracer("prism-executor")
    try:
        with _tracer.start_as_current_span(
            SpanName.RUN,
            context=_parent_ctx,
            attributes={
                SpanAttr.RUN_ID: args.run_id,
                SpanAttr.SESSION_ID: args.session_id,
                SpanAttr.USER_ID: args.user_id,
                # agent_type / route_mode populated from DB in full integration
            },
        ):
            # FROM_DB: 执行入口（DOC-07 Task 7.4 实现）
            # if args.resume_from_step is not None:
            #     # Coordinator Recovery（DOC-04 v4 Task 4.3，DOC-07 v4 Task 7.4）
            #     await engine.resume(from_step=args.resume_from_step)
            # else:
            #     await engine.run(run.prompt)
            logger.info(
                "harness.subprocess.started",
                run_id=args.run_id,
                session_id=args.session_id,
                otel_traceparent=args.otel_trace_id or "none",
                note="DB integration pending DOC-07 Task 7.4",
            )
    finally:
        stop_event.set()
        await heartbeat_task
        await callback.close()


if __name__ == "__main__":
    asyncio.run(main())
