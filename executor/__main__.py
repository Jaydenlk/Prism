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
2. 从 DB 读取 Run 配置 + Provider（独立 DB session，裸 SQL，DOC-07 Task 7.4）
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
import sys
import time
from dataclasses import dataclass, field

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

# ---------------------------------------------------------------------------
# 纯 executor 侧 dataclass（不 import backend ORM，裸 SQL 填充）
# ---------------------------------------------------------------------------

@dataclass
class RunRow:
    """从 runs 表裸 SQL SELECT 填充的极简 dataclass"""
    id: str
    prompt: str
    model: str
    provider_id: str | None
    agent_type: str | None
    status: str


@dataclass
class ProviderRow:
    """从 providers 表裸 SQL SELECT 填充的极简 dataclass"""
    id: str
    name: str
    protocol: str
    base_url: str
    api_key_encrypted: str
    model_id: str
    is_default: bool
    priority: int
    is_healthy: bool
    config: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# AES-256-GCM 解密（与 backend/app/core/security.py decrypt_value 等价实现）
# 独立副本，避免 import backend.app —— 进程边界（ADR-020）
# ---------------------------------------------------------------------------

def _decrypt_api_key(envelope: str, key_hex: str) -> str:
    """解密 AES-256-GCM 信封格式 '<nonce_hex>:<ciphertext_hex>'"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    parts = envelope.split(":", 1)
    if len(parts) != 2:
        raise ValueError(
            f"Invalid encryption envelope format (expected '<nonce_hex>:<ciphertext_hex>'): {envelope[:20]!r}"
        )
    nonce_hex, ciphertext_hex = parts
    key_bytes = bytes.fromhex(key_hex)
    if len(key_bytes) != 32:
        raise ValueError(
            f"ENCRYPTION_KEY must decode to exactly 32 bytes; got {len(key_bytes)}."
        )
    aesgcm = AESGCM(key_bytes)
    plaintext_bytes = aesgcm.decrypt(
        bytes.fromhex(nonce_hex),
        bytes.fromhex(ciphertext_hex),
        None,
    )
    return plaintext_bytes.decode("utf-8")


# ---------------------------------------------------------------------------
# DB 读取函数（裸 SQL，同步，sqlalchemy.create_engine）
# ---------------------------------------------------------------------------

def _fetch_run_and_provider(run_id: str) -> tuple[RunRow, ProviderRow]:
    """从 DB 读取 Run 行 + Provider 行.

    1. 按 run_id 查 runs 表
    2. 按 run.provider_id 查 providers 表；若 NULL 取最高 priority 的 scope=system provider
    返回 (RunRow, ProviderRow)，失败时抛 RuntimeError。
    """
    from sqlalchemy import create_engine, text as sa_text

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is not set")

    engine = create_engine(database_url, pool_pre_ping=True)

    try:
        with engine.connect() as conn:
            # 1. 读取 Run
            run_result = conn.execute(
                sa_text(
                    "SELECT id, prompt, model, provider_id, agent_type, status "
                    "FROM runs WHERE id = :run_id"
                ),
                {"run_id": run_id},
            ).fetchone()

            if run_result is None:
                raise RuntimeError(f"Run not found: {run_id}")

            run = RunRow(
                id=run_result[0],
                prompt=run_result[1],
                model=run_result[2],
                provider_id=run_result[3],
                agent_type=run_result[4],
                status=run_result[5],
            )

            # 2. 读取 Provider
            if run.provider_id:
                prov_result = conn.execute(
                    sa_text(
                        "SELECT id, name, protocol, base_url, api_key_encrypted, "
                        "model_id, is_default, priority, is_healthy, config "
                        "FROM providers WHERE id = :provider_id"
                    ),
                    {"provider_id": run.provider_id},
                ).fetchone()
                if prov_result is None:
                    raise RuntimeError(f"Provider not found: {run.provider_id}")
            else:
                # NULL provider_id: 取最高 priority 的 scope=system provider
                prov_result = conn.execute(
                    sa_text(
                        "SELECT id, name, protocol, base_url, api_key_encrypted, "
                        "model_id, is_default, priority, is_healthy, config "
                        "FROM providers WHERE scope = 'system' "
                        "ORDER BY priority DESC, is_default DESC "
                        "LIMIT 1"
                    )
                ).fetchone()
                if prov_result is None:
                    raise RuntimeError(
                        "No system provider available (run.provider_id is NULL and no scope=system provider found)"
                    )

            provider = ProviderRow(
                id=prov_result[0],
                name=prov_result[1],
                protocol=prov_result[2],
                base_url=prov_result[3],
                api_key_encrypted=prov_result[4],
                model_id=prov_result[5],
                is_default=bool(prov_result[6]),
                priority=int(prov_result[7]),
                is_healthy=bool(prov_result[8]),
                config=prov_result[9] if prov_result[9] else {},
            )

    finally:
        engine.dispose()

    return run, provider


# ---------------------------------------------------------------------------
# 心跳 writer（ADR-023）
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Plugin bootstrap helper（DEC-004: L2 根因修复）
# ---------------------------------------------------------------------------

async def bootstrap_plugins(
    backend_url: str,
    user_id: str,
    callback_secret: str,
) -> tuple[list[dict], list[dict]]:
    """Fetch user-installed skills + accessible MCP servers from backend internal API.

    Two endpoints are independent and fetched concurrently. Each is evaluated
    independently — partial fault (e.g. skills succeed, servers fail) preserves
    the successful side rather than dropping both, so logs remain diagnostic.
    """
    import httpx
    headers = {"X-Callback-Secret": callback_secret}

    async def _fetch(path: str) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as http:
            resp = await http.get(f"{backend_url}{path}", headers=headers)
            resp.raise_for_status()
            return resp.json()

    skills_res, servers_res = await asyncio.gather(
        _fetch(f"/api/v1/internal/users/{user_id}/installed-skills"),
        _fetch(f"/api/v1/internal/users/{user_id}/mcp-servers"),
        return_exceptions=True,
    )

    if isinstance(skills_res, Exception):
        logger.warning("executor.plugin_bootstrap_skills_failed", error=str(skills_res), user_id=user_id)
        skills: list[dict] = []
    else:
        skills = skills_res.get("skills", [])

    if isinstance(servers_res, Exception):
        logger.warning("executor.plugin_bootstrap_servers_failed", error=str(servers_res), user_id=user_id)
        servers: list[dict] = []
    else:
        servers = servers_res.get("servers", [])

    return skills, servers


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

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
        agent_type="general",  # updated after DB read / TaskRouter
        trace_id=args.otel_trace_id,
    )

    # 1c. OTel Tracing setup (ADR-117, DOC-12 Task 12.5)
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
    # NOTE: 在 DB 读取之前初始化，确保任何错误都能通过 callback 报告
    from executor.callbacks.backend_callback import BackendCallback
    from executor.router import TaskRouter

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

    # 全局 try/except：所有异常走 callback.run_error()，正常 sys.exit(0)
    try:
        # ----------------------------------------------------------------
        # Step 2: 从 DB 读取 Run 配置 + Provider（裸 SQL，同步）
        # ----------------------------------------------------------------
        logger.info(
            "harness.subprocess.db_fetch.start",
            run_id=args.run_id,
        )

        try:
            run, provider = await asyncio.to_thread(
                _fetch_run_and_provider, args.run_id
            )
        except Exception as db_exc:
            logger.error(
                "harness.subprocess.db_fetch.failed",
                run_id=args.run_id,
                error=str(db_exc),
                exc_info=True,
            )
            await callback.run_error(f"DB fetch failed: {db_exc}")
            return

        logger.info(
            "harness.subprocess.db_fetch.done",
            run_id=args.run_id,
            provider_id=provider.id,
            provider_name=provider.name,
            protocol=provider.protocol,
        )

        # ----------------------------------------------------------------
        # Step 3a: 解密 API Key（SYSTEM_PRESET_NO_KEY 优雅处理）
        # ----------------------------------------------------------------
        PRESET_SENTINEL = "SYSTEM_PRESET_NO_KEY"

        # 检查未加密的 sentinel（admin 还没填 key 的情况）
        if provider.api_key_encrypted == PRESET_SENTINEL:
            error_msg = f"Provider {provider.name!r} has no API key configured (SYSTEM_PRESET_NO_KEY)"
            logger.warning(
                "harness.subprocess.provider.no_key",
                provider_id=provider.id,
                provider_name=provider.name,
            )
            await callback.run_error(error_msg)
            return

        encryption_key = os.environ.get("ENCRYPTION_KEY", "")
        if not encryption_key:
            await callback.run_error("ENCRYPTION_KEY environment variable is not set")
            return

        try:
            decrypted_api_key = _decrypt_api_key(provider.api_key_encrypted, encryption_key)
        except Exception as dec_exc:
            logger.error(
                "harness.subprocess.decrypt.failed",
                provider_id=provider.id,
                error=str(dec_exc),
                exc_info=True,
            )
            await callback.run_error(f"Failed to decrypt API key for provider {provider.name!r}: {dec_exc}")
            return

        # 解密后再次检查 sentinel（encrypted sentinel 场景）
        if decrypted_api_key == PRESET_SENTINEL:
            error_msg = f"Provider {provider.name!r} has no API key configured (SYSTEM_PRESET_NO_KEY)"
            logger.warning(
                "harness.subprocess.provider.no_key",
                provider_id=provider.id,
                provider_name=provider.name,
            )
            await callback.run_error(error_msg)
            return

        # ----------------------------------------------------------------
        # Step 3b: TaskRouter 路由决策
        # ----------------------------------------------------------------
        _router = TaskRouter()
        _route = _router.route(run.prompt, explicit_agent_type=run.agent_type or None)
        agent_type = _route.agent_type

        logger.info(
            "harness.subprocess.route",
            run_id=args.run_id,
            agent_type=agent_type,
            route_mode=_route.mode,
            route_reason=_route.reason,
        )

        # ----------------------------------------------------------------
        # Step 3c: 初始化 Adapter
        # ----------------------------------------------------------------
        from executor.adapters.base import ProviderCapabilities
        from executor.adapters.anthropic_driver import AnthropicDriver
        from executor.adapters.openai_driver import OpenAIDriver

        caps_dict = provider.config.get("capabilities", {})
        capabilities = ProviderCapabilities(
            prompt_cache=caps_dict.get("prompt_cache", False),
            streaming_tools=caps_dict.get("streaming_tools", True),
            extended_thinking=caps_dict.get("extended_thinking", False),
            vision=caps_dict.get("vision", False),
        )

        if provider.protocol == "anthropic":
            adapter = AnthropicDriver(
                base_url=provider.base_url,
                api_key=decrypted_api_key,
                model=provider.model_id,
                capabilities=capabilities,
            )
        elif provider.protocol == "openai":
            adapter = OpenAIDriver(
                base_url=provider.base_url,
                api_key=decrypted_api_key,
                model=provider.model_id,
                capabilities=capabilities,
            )
        else:
            await callback.run_error(
                f"Unknown provider protocol {provider.protocol!r} for provider {provider.name!r}"
            )
            return

        logger.info(
            "harness.subprocess.adapter.initialized",
            run_id=args.run_id,
            protocol=provider.protocol,
            model=provider.model_id,
        )

        # ----------------------------------------------------------------
        # Step 3d: 组件装配
        # ----------------------------------------------------------------
        from executor.engine.token_estimator_adapter import DriverTokenEstimator
        from executor.engine.context_budget import ContextBudgetManager
        from executor.engine.prompt_assembler import PromptAssembler
        from executor.tools.registry import ToolRegistry
        from executor.tools.pipeline import ToolExecutionPipeline
        from executor.engine.query_engine import QueryEngine, RunContext

        estimator = DriverTokenEstimator(adapter)
        max_context_tokens = provider.config.get("max_context_tokens", 200_000)
        budget = ContextBudgetManager(estimator=estimator, max_context_tokens=max_context_tokens)

        registry = ToolRegistry()
        from executor.tools.builtin import register_builtin_tools
        # Built-in action tools: Read/Write/Edit/Bash/Glob/Grep/WebFetch + Echo + SkillsSearch.
        # Registered before MCP tools so MCP can override on name collision (ADR-046).
        register_builtin_tools(registry)

        assembler = PromptAssembler(agent_type=agent_type, tools=registry.list_definitions())
        pipeline = ToolExecutionPipeline(registry, context_budget=budget)

        # ----------------------------------------------------------------
        # Step 3d-bis: Plugin Bootstrap (skills + MCP servers) — DEC-004
        # ----------------------------------------------------------------
        from executor.plugins.host import PluginHost
        from executor.plugins.skill_loader import SkillLoader
        from executor.harness.hooks.system import HookSystem

        skills_data, servers_data = await bootstrap_plugins(
            backend_url=os.environ.get("BACKEND_URL", "http://backend:8000"),
            user_id=args.user_id,
            callback_secret=args.callback_secret,
        )

        hook_system = HookSystem()
        skill_loader = SkillLoader(
            skills_dir=os.environ.get("PRISM_PLUGIN_DIR", "plugins/skills"),
            hook_system=hook_system,
        )
        plugin_host = PluginHost(
            skill_loader=skill_loader,
            hook_system=hook_system,
            tool_registry=registry,
            assembler=assembler,
        )

        # MCP servers — start concurrently (each is independent IO; stdio handshake
        # or HTTP initialize round-trip can be slow, parallel keeps startup tight)
        async def _safe_start(srv: dict) -> None:
            try:
                await plugin_host.start_server(srv)
            except Exception as exc:
                logger.warning(
                    "executor.mcp_load_failed",
                    server=srv.get("name"),
                    transport=srv.get("transport", "stdio"),
                    error=str(exc),
                )
        if servers_data:
            await asyncio.gather(*[_safe_start(srv) for srv in servers_data])

        # Skills — register each user-installed skill from its install_path
        for skill_data in skills_data:
            install_path = skill_data.get("install_path")
            if not install_path:
                continue
            try:
                skill_loader.register_from_path(install_path)
            except Exception as exc:
                logger.warning(
                    "executor.skill_register_failed",
                    skill=skill_data.get("skill_name"),
                    install_path=install_path,
                    error=str(exc),
                )

        # Refresh prompt with newly registered MCP tools + skill descriptions
        assembler.update_tools(registry.list_definitions())
        assembler.set_extra_dynamic_tail(
            skill_loader.get_descriptions_for_prompt(agent_type)
        )

        # ----------------------------------------------------------------
        # Step 5: Harness Runtime — wires middleware pipeline + permission
        # engine + guardrails. ADR-025 requires middleware to run for every
        # agent (loop detection, observability, feedback, plugin_builder gate).
        # ----------------------------------------------------------------
        from executor.harness.lifecycle import HarnessRuntime
        from executor.agents.pool import AgentPool
        import redis.asyncio as aioredis

        _redis_client = aioredis.from_url(args.redis_url, decode_responses=False)

        class _Settings:
            LOOP_DETECTION_WINDOW = int(os.environ.get("LOOP_DETECTION_WINDOW", "5"))

        _agent_def = AgentPool().get(agent_type)
        harness = HarnessRuntime(
            run_id=args.run_id,
            session_id=args.session_id,
            user_id=args.user_id,
            callback=callback,
            redis_client=_redis_client,
            redis_url=args.redis_url,
            adapter=adapter,
            settings=_Settings(),
            budget=budget,
            agent_def=_agent_def,
        )

        # ----------------------------------------------------------------
        # Step 6: QueryEngine（按 agent_type 选 MAX_TURNS，ADR-024）
        # ----------------------------------------------------------------
        max_turns = MAX_TURNS_BY_AGENT_TYPE.get(agent_type, 50)
        run_context = RunContext(
            run_id=args.run_id,
            session_id=args.session_id,
            user_id=args.user_id,
            agent_type=agent_type,
        )
        engine = QueryEngine(
            adapter=adapter,
            assembler=assembler,
            pipeline=pipeline,
            budget=budget,
            callback=callback,
            run_context=run_context,
            max_turns=max_turns,
            middleware_pipeline=harness.middleware,
            agent_type=agent_type,
        )

        # ----------------------------------------------------------------
        # Step 7: SIGTERM 处理（graceful cancel）
        # ----------------------------------------------------------------
        _engine_holder: list = [engine]  # mutable container for closure

        def _sigterm(*_: object) -> None:
            logger.info("harness.subprocess.sigterm_received", run_id=args.run_id)
            stop_event.set()
            if _engine_holder:
                loop = asyncio.get_event_loop()
                loop.create_task(_engine_holder[0].cancel(graceful=True))

        signal.signal(signal.SIGTERM, _sigterm)

        # ----------------------------------------------------------------
        # Step 8: 执行 — root span wraps the entire run (ADR-117 span tree)
        # ----------------------------------------------------------------
        from opentelemetry import trace as _otel_trace

        _tracer = _otel_trace.get_tracer("prism-executor")

        with _tracer.start_as_current_span(
            SpanName.RUN,
            context=_parent_ctx,
            attributes={
                SpanAttr.RUN_ID: args.run_id,
                SpanAttr.SESSION_ID: args.session_id,
                SpanAttr.USER_ID: args.user_id,
                SpanAttr.AGENT_TYPE: agent_type,
            },
        ):
            logger.info(
                "harness.subprocess.engine.run.start",
                run_id=args.run_id,
                session_id=args.session_id,
                agent_type=agent_type,
                max_turns=max_turns,
                prompt_preview=run.prompt[:80],
            )

            if args.resume_from_step is not None:
                # Coordinator Recovery（DOC-04 v4 Task 4.3，DOC-07 v4 Task 7.4）
                # resume() not yet implemented; fall back to engine.run()
                logger.warning(
                    "harness.subprocess.resume.fallback",
                    run_id=args.run_id,
                    resume_from_step=args.resume_from_step,
                    note="engine.resume() not implemented; falling back to engine.run()",
                )
                await engine.run(run.prompt)
            else:
                await engine.run(run.prompt)

    except Exception as top_exc:
        # 全局兜底：所有未被内层 except 捕获的异常
        logger.error(
            "harness.subprocess.fatal",
            run_id=args.run_id,
            error=str(top_exc),
            exc_info=True,
        )
        try:
            await callback.run_error(f"Executor fatal error: {top_exc}")
        except Exception:
            pass  # callback 本身失败时也不 crash

    finally:
        stop_event.set()
        await heartbeat_task
        await callback.close()


if __name__ == "__main__":
    asyncio.run(main())
