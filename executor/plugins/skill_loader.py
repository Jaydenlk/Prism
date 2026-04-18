"""
Skill 三级加载器

ADR-043 (PRD 原标 ADR-040 平移): Skill 三级加载规范

Level 0 — 注册（启动时）:
  扫描 plugins/skills/ 目录，解析每个 SKILL.md 的 YAML frontmatter，
  注册 SkillMetadata 到内存。

Level 1 — 描述注入（Session 开始时）:
  将所有 Skill 的 name + description 格式化为文本，
  注入到 PromptAssembler 的动态 section 中。
  模型看到描述后可以决定是否需要使用某个 Skill。
  若 agent_type 指定，则按 ADR-044 (PRD 原标 ADR-041) frontmatter.agents 字段过滤。

Level 2 — 完整加载（按需）:
  当模型请求使用某个 Skill，或用户消息匹配 trigger 关键词时，
  读取 SKILL.md 的完整 body 内容，注入到当前 turn 的上下文中。
  同时将 Skill frontmatter 中的 hooks 注册到 HookSystem（scoped）。
  Level 2 产生的 user message 标记 is_skill_context=True（ADR-045 / PRD 原标 ADR-042）。

Skill 内嵌 Hooks 的生命周期：
  - Skill 加载（Level 2）时注册到 HookSystem
  - Skill 卸载或 Session 结束时从 HookSystem 清除
  - 这些 hooks 只在 Skill 活跃期间触发
  - Phase 1 只支持 8 个核心事件（PreToolUse, PostToolUse, PostToolUseFailure,
    PermissionRequest, SessionStart, SessionEnd, Compact, Notification）
  - 其余事件的 hook 配置静默忽略（Phase 2 扩展时生效）

ADR-044 注意：Skill 匹配命中但模型未调用 load_skill(name) 时，
  触发 skill_mentioned_not_loaded 审计日志（structlog 事件）。

进程边界：本模块仅依赖 stdlib + pyyaml，禁止 import backend.app.*
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import structlog
import yaml

from executor.plugins.skill_types import SkillContent, SkillMetadata

if TYPE_CHECKING:
    from executor.harness.hooks.system import HookSystem
    from executor.harness.hooks.handlers import HookHandlerConfig

logger = structlog.get_logger()

# Phase 1 支持的 8 个核心事件（DOC-03 v4 Task 3.3 定义，其余 13 个 Phase 2 扩展）
_PHASE1_EVENTS = frozenset({
    "SessionStart",
    "SessionEnd",
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "PermissionRequest",
    "Compact",
    "Notification",
})


class SkillLoader:
    """Skill 三级加载器（ADR-043 Skill 三级加载规范）

    使用方式：
        loader = SkillLoader(skills_dir='plugins/skills/', hook_system=hook_system)
        loader.scan_and_register()                           # Level 0（进程启动时）

        desc = loader.get_descriptions_for_prompt()          # Level 1（Session 开始时）

        triggered = loader.try_trigger(user_message)         # 触发判断
        for name in triggered:
            content = loader.load_skill(name)                # Level 2（按需）

        loader.unload_skill(name)                            # 卸载
        loader.unload_all()                                  # Session 结束时清除所有
    """

    def __init__(self, skills_dir: str, hook_system: "HookSystem | None"):
        self._skills_dir = skills_dir
        self._hook_system = hook_system
        self._registry: dict[str, SkillMetadata] = {}
        self._loaded: dict[str, SkillContent] = {}
        # skill_name → list[hook_id string] — 已注册的 scoped hook 标识
        self._registered_hook_ids: dict[str, list[str]] = {}

    # ------------------------------------------------------------------
    # Level 0 — 注册
    # ------------------------------------------------------------------

    def scan_and_register(self) -> None:
        """Level 0: 扫描目录，注册所有 Skill 元数据。

        目录结构：
        plugins/skills/
        ├── financial-analysis/
        │   └── SKILL.md
        ├── code-review/
        │   └── SKILL.md
        └── ...

        目录不存在时静默返回（log info）。
        frontmatter 解析失败时跳过该 Skill（log warning）。
        """
        if not os.path.exists(self._skills_dir):
            logger.info(
                "skill.scan.dir_not_found",
                skills_dir=self._skills_dir,
            )
            return

        for entry in os.listdir(self._skills_dir):
            skill_dir = os.path.join(self._skills_dir, entry)
            skill_file = os.path.join(skill_dir, "SKILL.md")
            if os.path.isdir(skill_dir) and os.path.exists(skill_file):
                metadata = self._parse_frontmatter(skill_file)
                if metadata:
                    metadata.path = skill_file
                    self._registry[metadata.name] = metadata
                    logger.info(
                        "skill.registered",
                        name=metadata.name,
                        triggers=len(metadata.triggers),
                        hooks_events=list(metadata.hooks.keys()),
                        agents_filter=metadata.agents or "(all)",
                    )
                else:
                    logger.warning(
                        "skill.parse_failed",
                        skill_file=skill_file,
                    )

    # ------------------------------------------------------------------
    # Level 1 — 描述注入
    # ------------------------------------------------------------------

    def get_descriptions_for_prompt(self, agent_type: str | None = None) -> str:
        """Level 1: 返回所有 Skill 的描述文本，供 PromptAssembler 注入。

        若 agent_type 指定，按 ADR-044 frontmatter.agents 字段过滤：
            - Skill.agents 为空列表 → 全 agent 可见
            - Skill.agents 非空 → 仅当 agent_type in Skill.agents 时可见

        格式：
        ## 可用 Skills
        - **financial-analysis**: 金融数据分析和报告生成能力...
          触发词: 财报, financial, 股票分析

        如果需要使用某个 Skill，必须调用 load_skill(name)，不能只提及不调用。
        """
        visible = self._filter_by_agent(agent_type)
        if not visible:
            return ""

        lines = ["## 可用 Skills"]
        for name in sorted(visible.keys()):
            meta = visible[name]
            lines.append(f"- **{name}**: {meta.description}")
            if meta.triggers:
                lines.append(f"  触发词: {', '.join(meta.triggers)}")
        lines.append("")
        lines.append(
            "如果需要使用某个 Skill，必须调用 load_skill(name)，不能只提及不调用。"
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Trigger 匹配
    # ------------------------------------------------------------------

    def try_trigger(
        self, user_message: str, agent_type: str | None = None
    ) -> list[str]:
        """检查用户消息是否匹配任何 Skill 的 trigger 关键词。

        返回匹配到的 Skill 名称列表（已加载的 Skill 跳过，避免重复触发）。
        若 agent_type 指定，按 ADR-044 agents 字段过滤可见范围。
        """
        visible = self._filter_by_agent(agent_type)
        triggered: list[str] = []
        for name, meta in visible.items():
            if name in self._loaded:
                continue  # 已加载，不重复触发
            for trigger in meta.triggers:
                if trigger.lower() in user_message.lower():
                    triggered.append(name)
                    break
        return triggered

    # ------------------------------------------------------------------
    # Level 2 — 完整加载
    # ------------------------------------------------------------------

    def load_skill(self, name: str) -> SkillContent | None:
        """Level 2: 完整加载 Skill 内容。

        1. 读取 SKILL.md body（不含 frontmatter）
        2. 注册 Skill 内嵌的 hooks（Phase 1 事件，scoped 到 Skill 生命周期）
        3. 标记为已加载

        返回 SkillContent（is_loaded=True），
        Level 2 产生的 user message 应由调用方标记 is_skill_context=True（ADR-045）。
        若 name 未注册，返回 None 并 log warning。
        若已加载，直接返回缓存（幂等）。
        """
        if name in self._loaded:
            return self._loaded[name]

        meta = self._registry.get(name)
        if not meta:
            logger.warning("skill.load.not_found", name=name)
            return None

        # 读取完整内容
        full_text = self._read_body(meta.path)
        content = SkillContent(metadata=meta, full_text=full_text, is_loaded=True)
        self._loaded[name] = content

        # 注册 Skill 内嵌的 hooks（scoped to skill lifetime）
        if meta.hooks:
            self._register_skill_hooks(name, meta.hooks)

        logger.info(
            "skill.loaded",
            name=name,
            body_chars=len(full_text),
            is_skill_context=True,  # ADR-045: 标记日志
        )
        return content

    def unload_skill(self, name: str) -> None:
        """卸载 Skill：清除已加载内容，注销 scoped hooks。

        Session 结束或 Skill 被手动移除时调用。
        若 name 未加载，静默跳过。
        """
        self._loaded.pop(name, None)
        self._unregister_skill_hooks(name)
        logger.info("skill.unloaded", name=name)

    def unload_all(self) -> None:
        """卸载所有已加载 Skill（Session 结束时调用）。"""
        for name in list(self._loaded.keys()):
            self.unload_skill(name)

    def emit_mentioned_not_loaded(self, name: str, turn_index: int = 0) -> None:
        """ADR-044: 模型仅提及但未调用 load_skill(name) 时触发审计事件。

        调用方（QueryEngine / Middleware）在检测到模型输出包含 Skill 名称
        但未发出 load_skill 工具调用时，调用此方法触发审计日志。
        """
        logger.warning(
            "skill_mentioned_not_loaded",
            name=name,
            turn_index=turn_index,
            audit=True,
        )

    # ------------------------------------------------------------------
    # 上下文整合
    # ------------------------------------------------------------------

    def get_loaded_context(self) -> str:
        """返回所有已加载 Skill 的完整内容，供注入到当前 turn 上下文。

        格式：
        ## [Skill: financial-analysis]
        <SKILL.md body>

        ## [Skill: code-review]
        <SKILL.md body>
        """
        if not self._loaded:
            return ""

        parts = []
        for name, content in self._loaded.items():
            parts.append(f"## [Skill: {name}]\n{content.full_text}")
        return "\n\n".join(parts)

    @property
    def registry(self) -> dict[str, SkillMetadata]:
        """只读视图：已注册 Skill 元数据（Level 0 扫描结果）。"""
        return dict(self._registry)

    @property
    def loaded(self) -> dict[str, SkillContent]:
        """只读视图：已完整加载的 Skill（Level 2 结果）。"""
        return dict(self._loaded)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _filter_by_agent(self, agent_type: str | None) -> dict[str, SkillMetadata]:
        """ADR-044: 按 frontmatter.agents 过滤可见 Skill。

        - agent_type 为 None → 全部可见（不过滤）
        - Skill.agents 为空列表 → 全 agent 可见
        - Skill.agents 非空 → 仅当 agent_type in Skill.agents 时可见
        """
        if agent_type is None:
            return dict(self._registry)
        result: dict[str, SkillMetadata] = {}
        for name, meta in self._registry.items():
            if not meta.agents or agent_type in meta.agents:
                result[name] = meta
        return result

    def _parse_frontmatter(self, filepath: str) -> SkillMetadata | None:
        """解析 SKILL.md 的 YAML frontmatter。

        格式要求：
        - 文件以 '---\\n' 开头
        - frontmatter 以 '---' 结尾
        - 必须包含 name 字段

        解析失败返回 None（调用方 log warning）。
        """
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as exc:
            logger.warning("skill.parse.read_error", filepath=filepath, error=str(exc))
            return None

        if not text.startswith("---"):
            return None

        end = text.find("---", 3)
        if end == -1:
            return None

        try:
            frontmatter = yaml.safe_load(text[3:end])
        except yaml.YAMLError as exc:
            logger.warning("skill.parse.yaml_error", filepath=filepath, error=str(exc))
            return None

        if not frontmatter or "name" not in frontmatter:
            return None

        return SkillMetadata(
            name=frontmatter["name"],
            description=frontmatter.get("description", ""),
            triggers=frontmatter.get("triggers", []),
            hooks=frontmatter.get("hooks", {}),
            agents=frontmatter.get("agents", []),
        )

    def _read_body(self, filepath: str) -> str:
        """读取 SKILL.md 的 body（不含 frontmatter）。

        若文件无 frontmatter 分隔，则返回全文。
        """
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()

        if text.startswith("---"):
            end = text.find("---", 3)
            if end != -1:
                return text[end + 3:].strip()
        return text

    def _register_skill_hooks(self, skill_name: str, hooks_config: dict) -> None:
        """注册 Skill 内嵌的 hooks 到 HookSystem。

        只注册 Phase 1 支持的 8 个核心事件：
        SessionStart, SessionEnd, PreToolUse, PostToolUse, PostToolUseFailure,
        PermissionRequest, Compact, Notification

        其余事件的 hook 配置静默忽略（Phase 2 扩展时生效）。
        若 hook_system 为 None（单元测试场景），跳过注册。
        """
        from executor.harness.hooks.handlers import HookHandlerConfig  # 避免顶层循环 import

        registered_ids: list[str] = []

        for event_type, handler_list in hooks_config.items():
            if event_type not in _PHASE1_EVENTS:
                logger.debug(
                    "skill.hook.phase2_skipped",
                    skill=skill_name,
                    event_type=event_type,
                )
                continue

            # handler_list 可能是 list[dict] 或 list of objects
            for idx, raw_config in enumerate(handler_list):
                # raw_config 可以是：
                #   { "type": "command", "command": "...", "matcher": "..." }
                # 或包含嵌套 "hooks" 列表（CC 格式，本实现展平一级）
                if isinstance(raw_config, dict):
                    handler_type = raw_config.get("type", "command")
                    config = HookHandlerConfig(
                        type=handler_type,  # type: ignore[arg-type]
                        command=raw_config.get("command", ""),
                        url=raw_config.get("url", ""),
                        prompt_template=raw_config.get("prompt_template", ""),
                        prompt_model=raw_config.get("prompt_model", ""),
                        agent_type=raw_config.get("agent_type", ""),
                        matcher=raw_config.get("matcher", ""),
                    )
                    hook_id = f"skill:{skill_name}:{event_type}:{idx}"
                    if self._hook_system is not None:
                        self._hook_system.register(event_type, config)
                    registered_ids.append(hook_id)

        self._registered_hook_ids[skill_name] = registered_ids
        logger.info(
            "skill.hooks.registered",
            skill=skill_name,
            count=len(registered_ids),
        )

    def _unregister_skill_hooks(self, skill_name: str) -> None:
        """注销 Skill 的 scoped hooks。

        Phase 1 HookSystem 未实现按 id 注销（DOC-05 Task 5.3 会扩展），
        此处记录 hook_ids 日志，供后续 Task 接入。
        已注册 id 从 _registered_hook_ids 移除。
        """
        hook_ids = self._registered_hook_ids.pop(skill_name, [])
        if hook_ids:
            logger.info(
                "skill.hooks.unregistered",
                skill=skill_name,
                hook_ids=hook_ids,
                note="Phase 1: HookSystem 无按 id 注销接口，Task 5.3 扩展",
            )
