"""
executor/harness/middleware/plugin_builder_gate.py — PluginBuilderGate Middleware

v4 修订（ADR-042，原标 ADR-038）：
- 仅对 agent_type == "plugin_builder" 生效的阶段门控 Middleware
- 不再按"最小 5 轮"硬门控，改为"完整度打分 < 0.8 不允许进入设计展示"
- 通过 ctx.custom_data 追踪阶段状态：
    plugin_build_phase: 1~4（需求收集 / 设计展示 / 生成 / 验证）
    last_completeness_score: 最近一次打分的 overall
    design_confirmed: 用户是否确认了设计方案

GuardrailsEngine 规则（GR-PLUGIN-CREATE-001）在本模块底部定义，
与此 Middleware 配合构成"Harness 双保险"。

Observability（v4）：
- structlog 事件: plugin_builder.gate.phase_transition
- OTel span: plugin_builder.phase.{1,2,3,4}（stub，DOC-12 Task 12.5 接入）

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

import structlog

from executor.harness.middleware.base import Middleware, MiddlewareContext
from executor.harness.guardrails.rules import GuardrailRule

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# PluginBuilderGate Middleware — 阶段门控
# ---------------------------------------------------------------------------

class PluginBuilderGate(Middleware):
    """v4：仅对 PluginBuilder Agent 生效的完整度打分门控 Middleware。

    pre_turn 时检查当前阶段和打分，决定是否注入约束提示。
    """

    name = "plugin_builder_gate"

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
