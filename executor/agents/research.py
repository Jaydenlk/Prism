"""
executor/agents/research.py — Research/Explore Agent（只读探索者）

对标 CC 的 Explore Agent：
- 被故意裁成 read-only specialist
- 只保留搜索、读取、分析类工具
- 绝对不能创建/修改/删除任何数据
- Harness 层通过 read_only=True 做硬性保障
- Bash 严格白名单：仅允许 9 条只读命令

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

from executor.agents.base import AgentDefinition

# v4: 只读工具白名单
READ_ONLY_TOOLS: list[str] = [
    "web_search",
    "file_read",
    "Read",
    "grep",
    "Grep",
    "glob",
    "Glob",
    "list_directory",
    "LS",
    "bash",
    "Bash",   # Bash 允许，但 input 走严格白名单（见 bash_whitelist）
]

# v4 ADR-030/034: Explore/Research 的 Bash 严格白名单（PDF 补丁 P3）
# 共 9 条只读命令，其他 Bash 命令均禁用
BASH_WHITELIST: list[str] = [
    "ls",
    "git status",
    "git log",
    "git diff",
    "find",
    "grep",
    "cat",
    "head",
    "tail",
]

RESEARCH_AGENT = AgentDefinition(
    agent_type="explore",   # v4: 规范化为 "explore"，研究场景复用
    description="研究/探索 Agent，只读模式，用于信息搜索和分析",
    allowed_tools=READ_ONLY_TOOLS,
    max_turns=30,           # 探索任务通常不需要太多轮
    read_only=True,
    bash_whitelist=BASH_WHITELIST,   # v4 新增
    behavior_constraints=(
        "你是只读探索者。\n"
        "绝对不能创建、修改、删除任何文件或数据。\n"
        "你的工作是搜索信息、阅读内容、分析数据，然后将发现总结返回。\n"
        "Bash 命令严格白名单：ls, git status, git log, git diff, find, grep, cat, head, tail。\n"
        "其他 Bash 命令一律禁用（平台级护栏会拦截）。\n"
        "如果任务需要写操作，明确告知用户你无法执行，建议切换到通用 Agent。"
    ),
)

# v4 向后兼容别名
EXPLORE_AGENT = RESEARCH_AGENT
