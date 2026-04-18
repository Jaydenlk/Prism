"""
Plugin 数据类型定义

DOC-05 Task 5.4: PluginHost 统一管理与垂类特调（ADR-050）

Plugin 是 Prism 的最大扩展单元，可同时包含 Skill + Hook + MCP 配置：
    plugins/
    └── financial/                  # 金融垂类 Plugin
        ├── plugin.yaml            # Plugin 元数据 + 依赖声明
        ├── skills/
        │   └── analysis/
        │       └── SKILL.md
        ├── hooks/
        │   └── compliance-check.sh
        └── mcp/
            └── market-data.json   # MCP Server 配置

加载顺序（ADR-050）：Platform → User → Session，冲突时高优先级覆盖 + 写 audit。

进程边界：本模块只 import 标准库，禁止 import backend.app.*
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PluginScope(str, Enum):
    """Plugin 加载级别（ADR-050 三级加载顺序）

    Platform < User < Session，冲突时高优先级覆盖低优先级。
    数字越大优先级越高（用于冲突检测排序）。
    """

    PLATFORM = "platform"   # 平台内置（最低优先级，适用所有用户）
    USER = "user"            # 用户安装（覆盖 Platform）
    SESSION = "session"      # 会话临时（最高优先级，仅本次会话有效）

    @property
    def priority(self) -> int:
        """数字越大，优先级越高。"""
        return {"platform": 0, "user": 1, "session": 2}[self.value]


@dataclass
class PluginConfig:
    """Plugin 配置（从 plugin.yaml 解析后的结构化表示）

    字段：
        name:            Plugin 唯一名称（全局唯一，用于命名空间前缀）
        description:     Plugin 功能描述
        version:         版本号（SemVer 字符串）
        skills_dir:      Plugin 内 skills/ 子目录路径（相对 plugin.yaml 所在目录）
        hooks_config:    Plugin 级别的 Hook 配置（event_type → handler_list）
        mcp_servers:     MCP Server 配置列表（每项为 {"name", "command", "args", "env"}）
        agent_overrides: 覆盖 Agent 行为约束（垂类特调，合并后传给 QueryEngine）
        scope:           Plugin 加载级别（Platform/User/Session，默认 User）
        plugin_root:     Plugin 根目录的绝对路径（变量替换时使用，可选）
        user_config:     用户安装时填写的自定义配置（供 ${user_config.X} 变量替换）
    """

    name: str
    description: str = ""
    version: str = "1.0.0"
    skills_dir: str = ""                          # Plugin 内的 skills/ 子目录路径
    hooks_config: dict = field(default_factory=dict)   # hooks 配置
    mcp_servers: list[dict] = field(default_factory=list)  # MCP Server 配置列表
    agent_overrides: dict = field(default_factory=dict)  # 覆盖 Agent 行为约束
    scope: PluginScope = PluginScope.USER          # Plugin 加载级别（默认 User）
    plugin_root: str = ""                          # Plugin 根目录绝对路径
    user_config: dict = field(default_factory=dict)  # 用户自定义配置
