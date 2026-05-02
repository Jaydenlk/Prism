"""
Prompt 动态装配引擎

核心设计（参考 CC 的 getSystemPrompt()）：
1. 静态 section 拼接后缓存（同一 Session 内字节级一致）
2. 动态 section 按条件注入
3. 支持 cache boundary 标记（供支持 Prompt Cache 的厂商使用）

使用方式：
    assembler = PromptAssembler(agent_type="general", tools=[...])
    system_prompt = assembler.build(
        mcp_servers=[...],
        memory=None,
        language="zh-CN"
    )

进程边界：本模块只 import executor.adapters.base 和 executor.engine.prompt_sections，
禁止 import backend.app.* 或 executor.adapters.anthropic_driver / openai_driver。

ADR-014: PromptSection 对齐 CC 10+ getter 粒度，不简化。
ADR-015: TokenEstimator 直接上精确 tokenizer，依赖注入，不接受粗估。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from executor.adapters.base import ToolDefinition
from executor.engine.prompt_sections import (
    agent_behavior_section,
    brief_section,
    compliance_section,
    env_info_section,
    function_result_clearing_section,
    identity_section,
    language_section,
    mcp_instructions_section,
    memory_section,
    output_efficiency_section,
    output_style_section,
    risk_actions_section,
    scratchpad_section,
    session_guidance_section,
    skill_grammar_section,
    summarize_tool_results_section,
    system_rules_section,
    task_philosophy_section,
    token_budget_section,
    tone_style_section,
    tool_grammar_section,
)

# cache boundary 标记字面值（DOC-02 Part B 要求精确匹配）
CACHE_BOUNDARY_MARKER = "\n--- DYNAMIC BOUNDARY ---\n"


# ---------------------------------------------------------------------------
# 轻量 dataclass（临时定义，DOC-05 实现后替换为正式导入）
# ---------------------------------------------------------------------------


@dataclass
class MCPServerInfo:
    """MCP Server 信息（临时定义，DOC-05 Task 5.2 会定义正式版本）

    字段:
        name: MCP Server 名称（唯一标识）
        instructions: Server 向模型提供的使用说明（可为空字符串）
    """

    name: str
    instructions: str = ""


@dataclass
class SkillInfo:
    """Skill 信息（临时定义，DOC-05 Task 5.1 会定义正式版本）

    字段:
        name: Skill 唯一名称
        description: Skill 功能描述（模型用此判断何时触发）
        triggers: 触发关键词列表（辅助触发判断）
    """

    name: str
    description: str = ""
    triggers: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# PromptAssembler 核心类
# ---------------------------------------------------------------------------


class PromptAssembler:
    """Prompt 动态装配引擎（v4，对齐 CC getSystemPrompt()）

    静态部分：
        identity / system_rules / task_philosophy / risk_actions /
        tool_grammar / tone_style / output_efficiency / compliance /
        agent_behavior — 共 9 个 section，会话内缓存，字节级一致

    动态部分：
        session_guidance / mcp_instructions / skill_grammar / memory /
        env_info / language / output_style / scratchpad /
        function_result_clearing / summarize_tool_results /
        token_budget / brief — 共 12 个 section，按条件注入

    工具列表变更时，通过 tools_hash 感知，自动失效缓存重建静态部分。
    """

    def __init__(
        self,
        agent_type: str,  # "general" | "research" | "planner" | "verifier" | "coordinator" | "plugin_builder"
        tools: list[ToolDefinition],
    ):
        self._agent_type = agent_type
        self._tools = tools
        self._static_cache: str | None = None
        self._tools_hash: str | None = None
        # v4 Task 4.2: Fork 子 assembler 动态尾部注入（ADR-034 硬约束）
        # 非 None/非空时，_build_dynamic 会在末尾拼接此文本
        self._extra_dynamic_tail: str | None = None

    def set_extra_dynamic_tail(self, content: str | None) -> None:
        """Append extra section to the end of dynamic prompt tail.

        Used by: executor bootstrap (skill grammar) + ForkManager (hard constraints).
        Replaces any prior tail; pass None or empty to clear.
        """
        self._extra_dynamic_tail = content if content else None

    def _compute_tools_hash(self) -> str:
        """根据工具名 + description 计算 hash，供 cache 失效判断。

        严格按 Part B 示例：f"{t.name}:{t.description}" 排序后 SHA256 前 16 hex。
        """
        tool_sig = "|".join(
            f"{t.name}:{t.description}"
            for t in sorted(self._tools, key=lambda t: t.name)
        )
        return hashlib.sha256(tool_sig.encode()).hexdigest()[:16]

    def _build_static(self) -> str:
        """构建静态部分（会被缓存，9 个 section，对齐 CC）

        顺序固定，与 cache_control 注入点对齐：
        Driver 侧在最后一条 system text block 注入 cache_control: ephemeral，
        意即整个静态 prefix 都在 cache boundary 上游。
        """
        sections = [
            identity_section(),
            system_rules_section(),
            task_philosophy_section(),
            risk_actions_section(),              # v4 新增
            tool_grammar_section(self._tools),
            tone_style_section(),                 # v4 新增
            output_efficiency_section(),
            compliance_section(),                 # Prism 独有：四铁律（DOC-00 v4 §7）
            agent_behavior_section(self._agent_type),  # v4 新增：按 agent_type 注入行为约束
        ]
        return "\n\n".join(s for s in sections if s)

    def _build_dynamic(
        self,
        mcp_servers: list[MCPServerInfo] | None = None,
        skills: list[SkillInfo] | None = None,
        memory: str | None = None,
        language: str = "zh-CN",
        output_style: str = "normal",
        remaining_tokens: int | None = None,
        brief_mode: bool = False,
    ) -> str:
        """构建动态部分（每次请求可能不同，按条件注入，12 个 section）"""
        feature_gates = {
            "ask_user_question": any(t.name == "ask_user_question" for t in self._tools),
            "fork_agent": any(t.name == "fork_agent" for t in self._tools),
        }
        sections = [
            session_guidance_section(self._agent_type, [t.name for t in self._tools], feature_gates),
        ]
        if mcp_servers:
            sections.append(mcp_instructions_section(mcp_servers))   # v4
        if skills:
            sections.append(skill_grammar_section(skills))            # v4 新增
        if memory:
            sections.append(memory_section(memory))
        sections.append(env_info_section())
        sections.append(language_section(language))
        if output_style != "normal":
            sections.append(output_style_section(output_style))
        sections.append(scratchpad_section())
        sections.append(function_result_clearing_section())
        sections.append(summarize_tool_results_section())
        if remaining_tokens is not None and remaining_tokens < 20000:
            sections.append(token_budget_section(remaining_tokens))
        if brief_mode:
            sections.append(brief_section())
        # v4 Task 4.2: Fork 硬约束注入（ADR-034），非空时追加到动态部分末尾
        if self._extra_dynamic_tail:
            sections.append(self._extra_dynamic_tail)
        return "\n\n".join(s for s in sections if s)

    def build(self, **dynamic_kwargs) -> str:
        """组装完整 System Prompt，支持 tools 变更时 cache 自动失效。

        返回：static_prefix + CACHE_BOUNDARY_MARKER + dynamic（若 dynamic 非空）
        或仅 static_prefix（若 dynamic 为空）。
        """
        current_hash = self._compute_tools_hash()
        if self._static_cache is None or self._tools_hash != current_hash:
            self._static_cache = self._build_static()
            self._tools_hash = current_hash

        dynamic = self._build_dynamic(**dynamic_kwargs)

        if dynamic:
            return self._static_cache + CACHE_BOUNDARY_MARKER + dynamic
        return self._static_cache

    def get_static_prefix(self) -> str:
        """返回纯静态部分（供 cache boundary 标注使用）。

        Driver 侧（AnthropicDriver）在此 prefix 末尾的 system text block
        注入 cache_control: ephemeral，实现 Prompt Cache。
        不含 CACHE_BOUNDARY_MARKER，纯静态串，字节级一致。
        """
        current_hash = self._compute_tools_hash()
        if self._static_cache is None or self._tools_hash != current_hash:
            self._static_cache = self._build_static()
            self._tools_hash = current_hash
        return self._static_cache

    def invalidate_static_cache(self) -> None:
        """使静态 cache 失效（Task 5.2 MCP 热加载，ADR-046）。

        调用时机：
        - MCP 工具注册/注销后（工具列表变了，tool_grammar_section 需要重建）
        - Skill 加载/卸载后（如果 Skill 影响了工具集）

        下次 build() 或 get_static_prefix() 时会重新构建静态 section。
        将 _static_cache 置 None，_tools_hash 置 None 使双重条件均失效。
        """
        self._static_cache = None
        self._tools_hash = None

    def update_tools(self, tools: list[ToolDefinition]) -> None:
        """更新工具列表并使静态 cache 失效（Task 5.2 MCP 热加载，ADR-046）。

        用于 MCP 热加载场景：
        1. MCP 工具注册到 ToolRegistry
        2. 调用 assembler.update_tools(registry.list_definitions())
        3. 静态 cache 自动失效（invalidate_static_cache() 内部调用）
        4. 下次 build() 使用新的工具列表，tool_grammar_section 包含 MCP 工具

        Args:
            tools: 新的工具定义列表（来自 ToolRegistry.list_definitions()）
        """
        self._tools = tools
        self.invalidate_static_cache()
