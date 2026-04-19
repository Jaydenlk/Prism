"""
executor/harness/middleware/plugin_builder_gate.py — PluginBuilderGate Middleware

v4 修订（ADR-042，原标 ADR-038）：
- 仅对 agent_type == "plugin_builder" 生效的阶段门控 Middleware
- 不再按"最小 5 轮"硬门控，改为"完整度打分 < 0.8 不允许进入设计展示"
- post_turn 主动打分（调 LLM 的 RequirementCompleteness.score）并写 custom_data
- 达阈值时自动抽取 YAML manifest 块 → callback.harness_event("plugin_manifest_ready")
- 通过 ctx.custom_data 追踪阶段状态：
    plugin_build_phase: 1~4（需求收集 / 设计展示 / 生成 / 验证）
    last_completeness_score: 最近一次打分的 overall
    design_confirmed: 用户是否确认了设计方案
    manifest_emitted: 本 run 是否已发 plugin_manifest_ready（单次触发）

GuardrailsEngine 规则（GR-PLUGIN-CREATE-001）在本模块底部定义，
与此 Middleware 配合构成"Harness 双保险"。

Observability（v4）：
- structlog 事件: plugin_builder.gate.phase_transition / manifest_ready_emitted
- OTel span: plugin_builder.phase.{1,2,3,4}（stub，DOC-12 Task 12.5 接入）

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

import re

import structlog

from executor.harness.middleware.base import Middleware, MiddlewareContext
from executor.harness.guardrails.rules import GuardrailRule

logger = structlog.get_logger()


# Scoring every turn costs an LLM call; only do it when user said something new
# since the last score. We detect "new user turn" by turn_count increment.
_YAML_FENCE_RE = re.compile(r"```(?:ya?ml)?\s*\n([\s\S]*?)\n```", re.MULTILINE)


def _extract_yaml_manifest(messages: list) -> str | None:
    """从最后一条 assistant 消息的 TextBlock 里抽取 yaml fenced block。"""
    for msg in reversed(messages):
        if getattr(msg, "role", None) != "assistant":
            continue
        for block in getattr(msg, "content", []):
            text = getattr(block, "text", None)
            if not text:
                continue
            match = _YAML_FENCE_RE.search(text)
            if match:
                return match.group(1).strip()
    return None


# ---------------------------------------------------------------------------
# PluginBuilderGate Middleware — 阶段门控 + 自动完整度打分 + manifest 事件
# ---------------------------------------------------------------------------

class PluginBuilderGate(Middleware):
    """v4：仅对 PluginBuilder Agent 生效的完整度打分门控 Middleware。

    pre_turn  → 检查当前阶段和打分，决定是否注入约束提示
    post_turn → 调 LLM 打 7 维度完整度分；达阈值时 emit plugin_manifest_ready
    """

    name = "plugin_builder_gate"

    def __init__(self, adapter=None, callback=None) -> None:
        """
        adapter: ModelAdapter 用于 RequirementCompleteness.score 的 LLM 调用
        callback: BackendCallback 用于 emit plugin_manifest_ready harness_event
        adapter/callback 都为 None 时降级为纯门控（不打分、不 emit）
        """
        self._adapter = adapter
        self._callback = callback

    async def pre_turn(self, ctx: MiddlewareContext) -> None:
        """阶段门控检查。只对 plugin_builder Agent 生效。"""
        if ctx.agent_type != "plugin_builder":
            return

        # 延迟 import 避免循环依赖（RequirementCompleteness 在 agents 包）
        from executor.agents.plugin_builder_scoring import RequirementCompleteness

        phase = ctx.custom_data.get("plugin_build_phase", 1)
        last_score = ctx.custom_data.get("last_completeness_score", 0.0)

        if phase == 1:
            if last_score < RequirementCompleteness.THRESHOLD:
                # 未达完整度阈值，继续收集
                ctx.custom_data["constraint_injection"] = (
                    f"你仍在需求收集阶段。当前完整度评分 {last_score:.2f} "
                    f"（阈值 {RequirementCompleteness.THRESHOLD}）。"
                    "请针对权重最高的缺失维度继续提问。"
                    "不要强行进入设计方案展示。"
                )
                logger.info(
                    "plugin_builder.gate.phase1_continue",
                    last_score=last_score,
                    threshold=RequirementCompleteness.THRESHOLD,
                )
            else:
                # 达阈值，允许进入阶段 2
                ctx.custom_data["plugin_build_phase"] = 2
                ctx.custom_data.pop("constraint_injection", None)
                logger.info(
                    "plugin_builder.gate.phase_transition",
                    from_phase=1,
                    to_phase=2,
                    score=last_score,
                )

        elif phase == 2:
            if not ctx.custom_data.get("design_confirmed"):
                ctx.custom_data["constraint_injection"] = (
                    "设计方案尚未获得用户确认。"
                    "请展示完整的设计方案并等待用户确认后再开始生成。"
                    "绝对不能在用户确认前开始写任何文件。"
                )
                logger.info("plugin_builder.gate.phase2_waiting_confirmation")
            else:
                # 用户已确认，进入阶段 3
                ctx.custom_data["plugin_build_phase"] = 3
                ctx.custom_data.pop("constraint_injection", None)
                logger.info(
                    "plugin_builder.gate.phase_transition",
                    from_phase=2,
                    to_phase=3,
                )

        elif phase == 3:
            # 生成阶段：无特殊门控，允许写文件
            pass

        elif phase == 4:
            # 验证阶段：无特殊门控
            pass

    async def post_turn(self, ctx: MiddlewareContext) -> None:
        """本轮 assistant 响应结束后：对 messages 打分；达阈值且含 YAML → emit 事件。"""
        if ctx.agent_type != "plugin_builder":
            return
        if self._adapter is None:
            return  # 降级：无 adapter 则不打分
        if ctx.custom_data.get("manifest_emitted"):
            return  # 一次 run 只 emit 一次

        # 延迟 import 避免循环依赖
        from executor.agents.plugin_builder_scoring import RequirementCompleteness

        try:
            scores = await RequirementCompleteness.score(ctx.messages, self._adapter)
        except Exception as e:
            logger.warning(
                "plugin_builder.gate.score_failed",
                error=str(e),
                turn=ctx.turn_count,
            )
            return

        overall = scores.get("overall", 0.0)
        ctx.custom_data["last_completeness_score"] = overall
        logger.info(
            "plugin_builder.gate.scored",
            overall=round(overall, 3),
            turn=ctx.turn_count,
        )

        if overall < RequirementCompleteness.THRESHOLD:
            return

        # 达阈值 → 抽 YAML manifest 块
        manifest_yaml = _extract_yaml_manifest(ctx.messages)
        if not manifest_yaml:
            logger.info(
                "plugin_builder.gate.threshold_reached_no_manifest",
                overall=round(overall, 3),
                note="score >= threshold but no yaml fence in latest assistant message",
            )
            return

        # Emit plugin_manifest_ready （前端 PluginsPage 监听此 harness_event subtype）
        if self._callback is not None:
            try:
                await self._callback.harness_event(
                    "plugin_manifest_ready",
                    {
                        "manifest_yaml": manifest_yaml,
                        "completeness": scores,
                    },
                )
                ctx.custom_data["manifest_emitted"] = True
                logger.info(
                    "plugin_builder.gate.manifest_ready_emitted",
                    overall=round(overall, 3),
                    yaml_length=len(manifest_yaml),
                )
            except Exception as e:
                logger.warning(
                    "plugin_builder.gate.emit_failed",
                    error=str(e),
                )

    async def pre_tool_use(self, ctx: MiddlewareContext) -> None:
        """工具使用前检查：阶段 1/2 时阻止写 plugin 相关文件。"""
        if ctx.agent_type != "plugin_builder":
            return

        phase = ctx.custom_data.get("plugin_build_phase", 1)
        if phase >= 3:
            return  # 阶段 3/4 允许写文件

        if ctx.tool_use_block is None:
            return

        tool_name = getattr(ctx.tool_use_block, "name", "")
        tool_input = getattr(ctx.tool_use_block, "input", {})

        if _is_plugin_file(tool_input) and phase < 3:
            ctx.abort = True
            ctx.abort_reason = (
                f"PluginBuilderGate: 阶段 {phase} 不允许操作插件文件。"
                "请先完成需求收集（完整度 ≥ 0.8）并获得用户设计确认后再生成文件。"
            )
            logger.warning(
                "plugin_builder.gate.blocked_file_write",
                tool_name=tool_name,
                phase=phase,
            )


# ---------------------------------------------------------------------------
# _is_plugin_file — 检测是否操作插件相关文件
# ---------------------------------------------------------------------------

def _is_plugin_file(tool_input: dict) -> bool:
    """检测 tool_input 中是否涉及插件相关文件路径。"""
    path = tool_input.get("path", "") or tool_input.get("command", "")
    if not isinstance(path, str):
        path = str(path)
    plugin_patterns = [
        "plugin.yaml",
        "plugin.json",
        "SKILL.md",
        ".skills/",
        ".prism/plugins/",
        "hooks/preToolUse",
        "hooks/postToolUse",
    ]
    return any(p in path for p in plugin_patterns)


# ---------------------------------------------------------------------------
# GR-PLUGIN-CREATE-001 — 可配置降级 Guardrail 规则（Harness 双保险第二层）
#
# v4：scope="tier" 支持降级（block / warn / off），不再是 platform_level 硬规。
# 原因：高级用户可能需要直接手写 plugin.yaml，硬阻止不合理。
#
# 配置示例（harness_config.yaml）：
#   guardrails:
#     overrides:
#       GR-PLUGIN-CREATE-001:
#         action: warn
#         message: "..."
# 未配置时默认 block。
# ---------------------------------------------------------------------------

GR_PLUGIN_CREATE_GUARD = GuardrailRule(
    id="GR-PLUGIN-CREATE-001",
    scope="tier",   # v4：可降级为 "warn" / 可关闭（区别于 "platform" 硬规）
    tool_pattern=r"Write|Edit|Bash",
    reason="插件文件的创建/修改应通过 PluginBuilder Agent 流程完成",
    custom_match=lambda tool_name, tool_input, run_context: (
        getattr(run_context, "agent_type", "") != "plugin_builder"
        and _is_plugin_file(tool_input if tool_input else {})
    ),
)
