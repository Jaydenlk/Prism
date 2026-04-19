"""
TAOR 主循环 — Prism v2 的心脏

对标 CC 的 query.ts while(true) 循环。
Model-Driven：模型决定做什么，Runtime 只负责执行和治理。

生命周期：
1. 初始化（RunContext 注入，构建 PromptAssembler、ToolRegistry、Pipeline）
2. run()：进入 TAOR 循环
3. 每轮：Prompt 组装 → API 调用 → 解析响应 → 工具执行 → 回调 → Compaction 检查
4. 退出：end_turn / max_tokens / max_turns / 异常

ADR-020：QueryEngine 只在 executor 子进程内实例化，Backend 不持有任何 Harness 对象。
ADR-021：同一轮内多个 ToolUseBlock 通过 asyncio.gather 并行执行。
ADR-022：text_delta/tool_use_delta 由 Driver 直通 Redis；QueryEngine 层不 double-publish。

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import structlog
import uuid_extensions as uuid7_ext
from structlog.contextvars import bind_contextvars

from executor.adapters.base import (
    ContentBlock,
    ModelAdapter,
    PrismMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from executor.callbacks.backend_callback import BackendCallback
from executor.engine.compaction import CompactionPipeline
from executor.engine.context_budget import ContextBudgetManager
from executor.engine.prompt_assembler import PromptAssembler
from executor.harness.middleware.base import MiddlewareContext
from executor.harness.middleware.pipeline import MiddlewarePipeline
from executor.tools.pipeline import ToolExecutionPipeline

logger = structlog.get_logger()

# Driver 类名白名单：这些 Driver 在 stream() 时已经自行做了 Redis 直通（ADR-022）。
# 通过类名判断，避免给 ProviderCapabilities 添加字段（Task 2.2 不改动）。
# 未来接入第三方 Adapter 时，若其未实现直通，需从此 frozenset 移除，
# QueryEngine 会在兜底路径中调用 callback.text_delta / callback.tool_use_delta。
_ADAPTERS_WITH_PASSTHROUGH: frozenset[str] = frozenset(
    ["AnthropicDriver", "OpenAIDriver"]
)


def _block_to_dict(block: ContentBlock) -> dict:
    """把 ContentBlock dataclass 实例序列化为 Backend 友好 dict。

    text      → {type, text}
    tool_use  → {type, id, name, input}
    tool_result → {type, tool_use_id, content, is_error}

    json.dumps 不能直接序列化 dataclass，此 helper 在 message_complete 回调前使用。
    """
    if isinstance(block, TextBlock):
        return {"type": "text", "text": block.text}
    elif isinstance(block, ToolUseBlock):
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": block.input,
        }
    elif isinstance(block, ToolResultBlock):
        return {
            "type": "tool_result",
            "tool_use_id": block.tool_use_id,
            "content": block.content,
            "is_error": block.is_error,
        }
    else:
        # 兜底：尝试 __dict__，不抛异常
        return getattr(block, "__dict__", {"type": "unknown"})


@dataclass
class RunContext:
    """执行上下文（跨组件传递，供 Hook / Permission / Metrics 使用）

    字段精确对应 Backend 子进程启动参数：
    - run_id:     UUID7，对应 runs 表主键
    - session_id: UUID7，对应 sessions 表主键
    - user_id:    UUID7，对应 users 表主键
    - agent_type: Agent 类型（默认 "general"），供 MiddlewareContext 使用（Task 3.2）
    """

    run_id: str
    session_id: str
    user_id: str
    agent_type: str = "general"


class QueryEngine:
    """TAOR 主循环引擎

    Model-Driven 自主循环：
    - Think（模型调用）→ Act（工具执行）→ Observe（结果收集）→ Respond（回调 Backend）
    - 所有智能在模型端，所有治理在 Harness 端
    """

    def __init__(
        self,
        adapter: ModelAdapter,
        assembler: PromptAssembler,
        pipeline: ToolExecutionPipeline,
        budget: ContextBudgetManager,
        callback: BackendCallback,
        run_context: RunContext,
        max_turns: int,
        middleware_pipeline: MiddlewarePipeline | None = None,  # Task 3.2: 可选中间件管道
        agent_type: str = "general",  # Task 3.2: 供 MiddlewareContext 使用
        compaction: CompactionPipeline | None = None,  # Task 3.5: 4 级 Compaction Pipeline
    ) -> None:
        self._adapter = adapter
        self._assembler = assembler
        self._pipeline = pipeline
        self._budget = budget
        self._callback = callback
        self._run_context = run_context
        self._max_turns = max_turns
        self._middleware = middleware_pipeline  # None 时所有钩点 no-op
        self._agent_type = agent_type
        self._compaction = compaction  # Task 3.5: None 时回退 Task 2.4 budget.compress_history 路径
        self._messages: list[PrismMessage] = []
        self._turn_count = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cache_hit_tokens = 0
        self._total_cache_creation_tokens = 0
        # 判断 Adapter 是否已做 Redis 直通（避免 double-publish）
        self._adapter_has_passthrough = (
            type(self._adapter).__name__ in _ADAPTERS_WITH_PASSTHROUGH
        )

    async def run(self, user_prompt: str) -> None:
        """执行完整的 TAOR 循环。这是主入口，被 __main__.py 调用。

        策略：
        1. 将用户 prompt 追加为第一条 user message
        2. 进入 while(True) 循环，每轮：
           a. 检查 turn 上限
           b. 构造 system prompt
           c. 调用 _process_turn()，获取 stop_reason + tool_use_blocks
           d. 若 stop_reason="tool_use"：执行工具 → Compaction 检查 → 继续
           e. 若 stop_reason="end_turn"/"max_tokens"：退出
        3. 正常退出：回调 run_complete
        4. 异常：回调 run_error 并重新 raise
        """
        # ADR-118: bind run-level context to structlog contextvars so all records
        # emitted during this run automatically carry run_id / session_id / user_id.
        bind_contextvars(
            run_id=self._run_context.run_id,
            session_id=self._run_context.session_id,
            user_id=self._run_context.user_id,
            agent_type=getattr(self._run_context, "agent_type", self._agent_type),
        )

        logger.info(
            "run.started",
            run_id=self._run_context.run_id,
            session_id=self._run_context.session_id,
            agent_type=getattr(self._run_context, "agent_type", self._agent_type),
            max_turns=self._max_turns,
            prompt_preview=user_prompt[:50],
        )

        # 初始消息
        self._messages.append(
            PrismMessage(
                role="user",
                content=[TextBlock(text=user_prompt)],
            )
        )

        try:
            while True:
                # 检查 turn 上限（ADR-024）
                if self._turn_count >= self._max_turns:
                    await self._callback.run_error(
                        f"达到最大循环次数 ({self._max_turns})"
                    )
                    return

                # Task 3.2: MiddlewarePipeline.pre_turn() 钩点
                _mw_ctx: MiddlewareContext | None = None
                if self._middleware is not None:
                    _mw_ctx = MiddlewareContext(
                        run_id=self._run_context.run_id,
                        session_id=self._run_context.session_id,
                        user_id=self._run_context.user_id,
                        turn_count=self._turn_count,
                        agent_type=getattr(self._run_context, "agent_type", self._agent_type),
                        messages=self._messages,
                        system_prompt="",  # system_prompt 在 build() 调用后才有，此处传空占位
                    )
                    await self._middleware.run_pre_turn(_mw_ctx)
                    if _mw_ctx.abort:
                        await self._callback.run_error(
                            f"pre_turn aborted: {_mw_ctx.abort_reason}"
                        )
                        return

                # 构造 System Prompt（PromptAssembler 按 agent_type 动态组装）
                system_prompt = self._assembler.build(language="zh-CN")

                # 调用模型（流式），返回 stop_reason + 本轮工具调用列表
                stop_reason, tool_use_blocks = await self._process_turn(system_prompt)
                self._turn_count += 1

                # 记录 TAOR 轮次指标
                try:
                    from executor.observability.metrics import prism_harness_turn_total

                    agent_type = getattr(self._assembler, "_agent_type", "unknown")
                    prism_harness_turn_total.labels(
                        agent_type=agent_type, stop_reason=stop_reason
                    ).inc()
                except Exception:
                    pass  # metrics 降级不影响主路径

                # ADR-025: MiddlewarePipeline.post_turn() fires at the END of EVERY
                # turn, regardless of stop_reason. Moving this before the break so
                # end_turn responses (pure text replies, no tool calls) still
                # trigger loop detection, observability, feedback, and plugin
                # builder scoring.
                if self._middleware is not None:
                    if _mw_ctx is None:
                        _mw_ctx = MiddlewareContext(
                            run_id=self._run_context.run_id,
                            session_id=self._run_context.session_id,
                            user_id=self._run_context.user_id,
                            turn_count=self._turn_count,
                            agent_type=getattr(self._run_context, "agent_type", self._agent_type),
                            messages=self._messages,
                            system_prompt="",
                        )
                    _mw_ctx.custom_data["tool_call_count"] = len(tool_use_blocks)
                    _mw_ctx.custom_data["stop_reason"] = stop_reason
                    await self._middleware.run_post_turn(_mw_ctx)

                # 判断是否继续
                if stop_reason in ("end_turn", "max_tokens"):
                    break

                if stop_reason == "tool_use" and tool_use_blocks:
                    # 执行工具（asyncio.gather 并行，ADR-021）
                    await self._execute_tools(tool_use_blocks)

                    # Compaction 检查（Task 3.5：若传入 CompactionPipeline 则走 Tier 1/2；
                    # 否则回退 Task 2.4 的 Tier 0 budget.compress_history 路径）
                    if self._compaction is not None:
                        # Task 3.5 路径：4 级 CompactionPipeline（ADR-031/032）
                        self._messages = await self._compaction.check_and_compact(
                            self._messages, system_prompt
                        )
                    else:
                        # Task 2.4 fallback 路径（Tier 0，保持向后兼容，不删除）
                        if self._budget.should_compress(self._messages, system_prompt):
                            before_count = len(self._messages)
                            self._messages = self._budget.compress_history(self._messages)
                            after_count = len(self._messages)
                            logger.info(
                                "harness.compaction.tier0",
                                run_id=self._run_context.run_id,
                                before=before_count,
                                after=after_count,
                            )
                            await self._callback.harness_event(
                                "compaction",
                                {
                                    "tier": 0,
                                    "messages_before": before_count,
                                    "messages_after": after_count,
                                },
                            )
                            try:
                                from executor.observability.metrics import (
                                    prism_harness_compaction_total,
                                )

                                prism_harness_compaction_total.labels(tier="0").inc()
                            except Exception:
                                pass

                    # post_turn already invoked above (before the branch); just continue
                    continue

                # 未知 stop_reason（例如模型返回空或自定义 stop）
                logger.warning(
                    "harness.taor.unknown_stop_reason",
                    stop_reason=stop_reason,
                    run_id=self._run_context.run_id,
                )
                break

            # 正常完成
            logger.info(
                "run.completed",
                run_id=self._run_context.run_id,
                turn_count=self._turn_count,
                input_tokens=self._total_input_tokens,
                output_tokens=self._total_output_tokens,
                cache_hit_tokens=self._total_cache_hit_tokens,
                cache_creation_tokens=self._total_cache_creation_tokens,
            )
            await self._callback.run_complete(
                input_tokens=self._total_input_tokens,
                output_tokens=self._total_output_tokens,
                cache_hit_tokens=self._total_cache_hit_tokens,
                cache_creation_tokens=self._total_cache_creation_tokens,
                turn_count=self._turn_count,
            )
        except Exception as e:
            logger.error(
                "run.failed",
                run_id=self._run_context.run_id,
                error=str(e),
                exc_info=True,
            )
            await self._callback.run_error(str(e))
            raise

    async def _process_turn(
        self, system_prompt: str
    ) -> tuple[str, list[ToolUseBlock]]:
        """执行单轮模型调用，解析流式响应。

        返回：(stop_reason, tool_use_blocks)

        流式 StreamEvent 解析：
        - text_delta → 累积文本；若 Adapter 无 Redis 直通则兜底调用 callback.text_delta
        - tool_use_start/delta/end → 收集工具调用参数
        - message_end → 获取 stop_reason + usage（含 cache tokens）
        - error → raise RuntimeError

        message_complete HTTP 回调带序列化 content（用于 Backend 持久化 messages 表）。
        """
        tool_definitions = self._pipeline._registry.list_definitions()

        accumulated_text = ""
        tool_use_blocks: list[ToolUseBlock] = []
        current_tool_id = ""
        current_tool_name = ""
        current_tool_input_json = ""
        stop_reason = ""

        # 为本轮消息生成 UUID7 message_id
        message_id = str(uuid7_ext.uuid7())

        async for event in self._adapter.stream(
            messages=self._messages,
            system_prompt=system_prompt,
            tools=tool_definitions if tool_definitions else None,
            session_id=self._run_context.session_id,
        ):
            if event.type == "text_delta":
                accumulated_text += event.text
                # ADR-022：Adapter 已做 Redis 直通则不 double-publish；
                # 否则由 QueryEngine 兜底（第三方 Adapter 场景）
                if not self._adapter_has_passthrough:
                    await self._callback.text_delta(event.text, message_id=message_id)

            elif event.type == "tool_use_start":
                current_tool_id = event.tool_use_id
                current_tool_name = event.tool_name
                current_tool_input_json = ""

            elif event.type == "tool_use_delta":
                current_tool_input_json += event.tool_input_delta
                if not self._adapter_has_passthrough:
                    await self._callback.tool_use_delta(
                        tool_use_id=current_tool_id,
                        partial_json=event.tool_input_delta,
                    )

            elif event.type == "tool_use_end":
                tool_use_blocks.append(
                    ToolUseBlock(
                        id=current_tool_id,
                        name=current_tool_name,
                        input=event.tool_input_complete,
                    )
                )
                # 重置当前工具状态
                current_tool_id = ""
                current_tool_name = ""
                current_tool_input_json = ""

            elif event.type == "message_end":
                stop_reason = event.stop_reason
                self._total_input_tokens += event.input_tokens
                self._total_output_tokens += event.output_tokens
                self._total_cache_hit_tokens += (
                    getattr(event, "cache_hit_tokens", 0) or 0
                )
                self._total_cache_creation_tokens += (
                    getattr(event, "cache_creation_tokens", 0) or 0
                )

            elif event.type == "error":
                raise RuntimeError(f"模型返回错误: {event.error_message}")

        # 将 Assistant 消息追加到 messages
        content_blocks: list[ContentBlock] = []
        if accumulated_text:
            content_blocks.append(TextBlock(text=accumulated_text))
        content_blocks.extend(tool_use_blocks)

        if content_blocks:
            assistant_msg = PrismMessage(role="assistant", content=content_blocks)
            self._messages.append(assistant_msg)
            # v4：关键事件 HTTP 带重试上报 message 完整体（供 Backend 持久化 messages 表）
            await self._callback.message_complete(
                role="assistant",
                content=[_block_to_dict(b) for b in content_blocks],
            )

        return stop_reason, tool_use_blocks

    async def _execute_tools(self, tool_use_blocks: list[ToolUseBlock]) -> None:
        """执行工具调用列表（ADR-021：asyncio.gather 并行）

        策略（Phase 1 保守实现）：
        - 所有 tool 无依赖声明 → 全部并行（asyncio.gather）
        - return_exceptions=True：单个工具异常不 crash 整个 run
        - 结果按 block 顺序收集为单条 user message 的 tool_result 列表
          （canonical Anthropic 语义，OpenAIDriver 在出站时展开为多条 role=tool）

        DOC-04 Coordinator 模式下可精细化依赖分析（{{tool_result:X}} 占位符检测）。
        """
        tool_coros = [self._execute_single_tool(block) for block in tool_use_blocks]
        results = await asyncio.gather(*tool_coros, return_exceptions=True)

        result_blocks: list[ToolResultBlock] = []
        for block, result in zip(tool_use_blocks, results):
            if isinstance(result, Exception):
                logger.error(
                    "tool.exception",
                    tool_use_id=block.id,
                    tool_name=block.name,
                    error=str(result),
                    exc_info=result,
                )
                result_blocks.append(
                    ToolResultBlock(
                        tool_use_id=block.id,
                        content=f"工具异常: {str(result)}",
                        is_error=True,
                    )
                )
            else:
                result_blocks.append(result)

        # canonical Anthropic：追加单条 user message，content 为 tool_result* 列表
        # OpenAIDriver 在 stream() 出站时自行展开为多条 role=tool（ADR-007）
        self._messages.append(
            PrismMessage(
                role="user",
                content=result_blocks,
            )
        )

    async def _execute_single_tool(self, block: ToolUseBlock) -> ToolResultBlock:
        """单工具执行，走完整 Pipeline（Schema校验 → 执行 → 截断）

        Task 3.2: 在 Pipeline 前后注入 pre_tool_use / post_tool_use 中间件钩点。
        Task 3.3 将在 Pipeline 内添加 Hook / Permission 集成点。
        run_context 已透传到 pipeline.execute()，Task 3.3 可直接使用。
        """
        # Task 3.2: pre_tool_use 钩点（在 tool_start 回调之前，允许 abort）
        if self._middleware is not None:
            tool_ctx = MiddlewareContext(
                run_id=self._run_context.run_id,
                session_id=self._run_context.session_id,
                user_id=self._run_context.user_id,
                turn_count=self._turn_count,
                agent_type=getattr(self._run_context, "agent_type", self._agent_type),
                messages=self._messages,
                system_prompt="",
                tool_use_block=block,
            )
            await self._middleware.run_pre_tool_use(tool_ctx)
            if tool_ctx.abort:
                return ToolResultBlock(
                    tool_use_id=block.id,
                    content=f"Middleware aborted: {tool_ctx.abort_reason}",
                    is_error=True,
                )
        else:
            tool_ctx = None

        await self._callback.tool_start(block.id, block.name, block.input)
        start = time.monotonic()

        # ADR-118: structured lifecycle log
        logger.info(
            "tool.invoked",
            tool_name=block.name,
            tool_use_id=block.id,
        )

        # Prometheus 计数
        try:
            from executor.observability.metrics import prism_tool_invocations_total

            prism_tool_invocations_total.labels(tool_name=block.name).inc()
        except Exception:
            pass

        try:
            result = await self._pipeline.execute(
                tool_name=block.name,
                tool_input=block.input,
                tool_use_id=block.id,
                run_context=self._run_context,  # v4：透传，Task 3.3 Hook/Permission 使用
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            try:
                from executor.observability.metrics import prism_tool_duration_seconds

                prism_tool_duration_seconds.labels(tool_name=block.name).observe(
                    duration_ms / 1000.0
                )
            except Exception:
                pass
            await self._callback.tool_end(
                tool_use_id=block.id,
                output=result.content,
                is_error=result.is_error,
                duration_ms=duration_ms,
            )

            # Task 3.2: post_tool_use 钩点（全部执行，不短路，可改写 result）
            if self._middleware is not None and tool_ctx is not None:
                tool_ctx.tool_result_block = result
                await self._middleware.run_post_tool_use(tool_ctx)
                return tool_ctx.tool_result_block

            return result
        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            # ADR-118: structured error log
            logger.error(
                "tool.exception",
                tool_name=block.name,
                tool_use_id=block.id,
                error=str(e),
                duration_ms=duration_ms,
                exc_info=True,
            )
            try:
                from executor.observability.metrics import prism_tool_errors_total

                prism_tool_errors_total.labels(
                    tool_name=block.name, error_type=type(e).__name__
                ).inc()
            except Exception:
                pass
            await self._callback.tool_end(
                tool_use_id=block.id,
                output=str(e),
                is_error=True,
                duration_ms=duration_ms,
            )
            raise
