"""
executor/harness/middleware/plugin_builder_gate.py — PluginBuilderGate Middleware

v2：检测 manifest YAML 输出 → emit plugin_manifest_ready 事件。
删除 v1 的 7 维打分阶段门控，AI 自主判断需求充分性。

GuardrailsEngine 规则（GR-PLUGIN-CREATE-001）在本模块底部定义。

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

import re

import yaml
import structlog

from executor.harness.middleware.base import Middleware, MiddlewareContext
from executor.harness.guardrails.rules import GuardrailRule

logger = structlog.get_logger()


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


class PluginBuilderGate(Middleware):
    """v2：检测 manifest YAML 输出 → emit plugin_manifest_ready 事件。"""

    name = "plugin_builder_gate"

    def __init__(self, adapter=None, callback=None) -> None:
        self._callback = callback

    async def pre_turn(self, ctx: MiddlewareContext) -> None:
        if ctx.agent_type != "plugin_builder":
            return

    async def post_turn(self, ctx: MiddlewareContext) -> None:
        if ctx.agent_type != "plugin_builder":
            return
        if self._callback is None:
            return
        if ctx.custom_data.get("manifest_emitted"):
            return

        manifest_yaml = _extract_yaml_manifest(ctx.messages)
        if not manifest_yaml:
            return

        try:
            parsed = yaml.safe_load(manifest_yaml)
            if not isinstance(parsed, dict) or "name" not in parsed:
                return
        except Exception:
            return

        try:
            await self._callback.harness_event(
                "plugin_manifest_ready",
                {"manifest_yaml": manifest_yaml},
            )
            ctx.custom_data["manifest_emitted"] = True
            logger.info(
                "plugin_builder.gate.manifest_ready_emitted",
                yaml_length=len(manifest_yaml),
            )
        except Exception as e:
            logger.warning("plugin_builder.gate.emit_failed", error=str(e))

    async def pre_tool_use(self, ctx: MiddlewareContext) -> None:
        if ctx.agent_type != "plugin_builder":
            return
        if ctx.tool_use_block is None:
            return
        tool_input = getattr(ctx.tool_use_block, "input", {})
        if _is_plugin_file(tool_input):
            pass  # v2: allow plugin_builder to write files freely


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
