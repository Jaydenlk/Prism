"""
Skill 数据类型定义

ADR-043 (PRD 原标 ADR-040 平移): Skill 三级加载规范
- Level 0 (注册): 启动时扫描 plugins/skills/**/SKILL.md，解析 frontmatter 入内存索引；不占 system prompt
- Level 1 (描述注入): Session 开始时把 name + description + triggers 拼接到 <available_skills> section 注入 system prompt
- Level 2 (完整加载): 匹配命中或 Agent 主动调用 load_skill(name) 时，把 SKILL.md 全文作为一条 user 消息插入 messages，
  该消息 is_skill_context=True (DOC-02 v4 新字段，Compaction 优先保留)

进程边界：本模块只 import 标准库，禁止 import backend.app.*
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SkillMetadata:
    """Skill 元数据（Level 0 注册信息）

    字段：
        name:        Skill 唯一名称（frontmatter 的 name 字段）
        description: Skill 功能描述（模型用此判断何时触发，Level 1 注入）
        triggers:    触发关键词列表（辅助触发判断，Level 1 也注入）
        hooks:       frontmatter 中的 hooks 定义（Level 2 加载时注册）
        path:        SKILL.md 文件路径
        agents:      frontmatter 的 agents 字段 — 仅对指定 agent_type 可见；
                     空列表表示全 agent 可见（ADR-044 / PRD 原标 ADR-041 agent 过滤）
    """

    name: str
    description: str
    triggers: list[str] = field(default_factory=list)
    hooks: dict = field(default_factory=dict)   # frontmatter 中的 hooks 定义
    path: str = ""                               # SKILL.md 文件路径
    agents: list[str] = field(default_factory=list)  # [] = 全 agent 可见


@dataclass
class SkillContent:
    """Skill 完整内容（Level 2 加载）

    字段：
        metadata:   Level 0 注册时的元数据
        full_text:  SKILL.md 的 body 内容（不含 frontmatter）
        is_loaded:  是否已完整加载到上下文
    """

    metadata: SkillMetadata
    full_text: str              # SKILL.md 的 body 内容（不含 frontmatter）
    is_loaded: bool = False     # 是否已完整加载到上下文
