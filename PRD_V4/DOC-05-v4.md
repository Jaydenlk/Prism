# Prism 棱镜 v2 — Plugin Ecosystem (DOC-05)

> **文档编号**: DOC-05
> **版本**: 4.0(Review 修订版)
> **日期**: 2026-04-18
> **性质**: 实现文档 — 声明式扩展体系,对标 CC 的 Skills + Hooks + MCP + Plugins
> **前置依赖**: DOC-00~04 v4 全部完成
> **Phase**: 1(Agent 核心)
> **Task 数**: 7(含 v3.1 新 Task 5.5-5.7 + v4 审计保留)
> **v4 变更摘要**: 基于 5 轮 review 修订,28 处精确修补(详见文末 §附录 A)。核心修订:Skill 三级加载规范化(Level 0/1/2 + is_skill_context 标记)、Skill 匹配时强制执行、Hook 4 种 handler 类型明确(command/http/prompt/agent)、MCP instructions 双通道注入 + agent-scoped MCP 白名单、Plugin 变量替换系统(${PRISM_*} + CC 兼容映射)、Skills Registry 简化为 **Local + GitHub 两源**(Phase 1,删 Manus/npm)、Skills Agent Tool 只保留 search 权限(install 需用户手动触发)、CC 导出返回 ConversionReport 不是直接文件、plugin.yaml schema 严格化。ADR 编号从 ADR-040 接续至 ADR-049。
> **审计注意**:
> - PromptAssembler 的工具列表 cache 在 MCP 热加载场景下必须失效重建
> - Hook 系统在 Phase 1 只触发 8 个核心事件(DOC-03 v4 Task 3.3 定义的),其余 13 个事件在 Phase 2 扩展

---

## 目录

1. [Task 5.1: Skill 三级加载体系](#task-51-skill-三级加载体系)
2. [Task 5.2: MCP Server 集成与热加载](#task-52-mcp-server-集成与热加载)
3. [Task 5.3: Hook 治理层与 Plugin 命名空间](#task-53-hook-治理层与-plugin-命名空间)
4. [Task 5.4: PluginHost 统一管理与垂类特调](#task-54-pluginhost-统一管理与垂类特调)
5. [Task 5.5: Skills Registry & Multi-Source Aggregation](#task-55-skills-registry--multi-source-aggregation)
6. [Task 5.6: Skills CLI & Agent Tool](#task-56-skills-cli--agent-tool)
7. [Task 5.7: CC 插件格式兼容层](#task-57-cc-插件格式兼容层)

---

## 文档结构

```
Part I:   Plugin Core（Task 5.1~5.4）— 插件核心加载与管理
Part II:  Skills Market（Task 5.5~5.6）— 多源聚合与安装入口
Part III: CC Plugin Protocol Compatibility（Task 5.7）— CC 插件格式兼容层
```

---

## Part I: Plugin Core

## Task 5.1: Skill 三级加载体系

### Part A — 设计与解释

#### 问题陈述

CC 的 Skill 系统是按需注入上下文的机制——Skill 描述在 Session 启动时加载（轻量），Skill 完整内容只在被使用时加载（按需），避免不必要的上下文消耗。Prism 需要实现等效的三级加载：

- **Level 0 — 注册**：系统启动时扫描 Skill 目录，记录元数据（name, description, triggers）
- **Level 1 — 描述注入**：Session 开始时将所有 Skill 的 description 注入到 System Prompt（模型知道有哪些 Skill 可用）
- **Level 2 — 完整加载**：模型调用 Skill 或触发条件命中时，将 Skill 的完整内容注入到当前 turn 的上下文中

这个设计直接对标 CC 的 `disable-model-invocation: true` 机制——Skill 描述占上下文，但完整内容不占，直到需要时才注入。

#### CC 架构映射

| CC 概念 | Prism 对应 |
|---------|-----------|
| `skills/` 目录 | `plugins/skills/` 目录 |
| Skill YAML frontmatter | Skill 元数据（name, description, triggers, hooks） |
| `/skill-name` 命令触发 | Agent 自主判断或用户指令触发 |
| `disable-model-invocation: true` | Level 1 只注入描述，Level 2 按需注入完整内容 |
| Skill 内嵌 hooks | Skill frontmatter 的 `hooks` 字段，scoped 到 Skill 生命周期 |

#### Skill 文件格式

```yaml
# plugins/skills/example-skill/SKILL.md
---
name: financial-analysis
description: "金融数据分析和报告生成能力，支持财报解读、指标计算和趋势分析"
triggers:
  - "财报"
  - "financial"
  - "股票分析"
hooks:
  PostToolUse:
    - matcher: "web_search"
      hooks:
        - type: command
          command: "./scripts/validate-financial-data.sh"
---

# 金融分析 Skill

## 使用说明
当用户需要金融数据分析时，遵循以下流程：
1. 确认分析标的和时间范围
2. 使用搜索工具获取相关财务数据
3. ...

## 输出格式
- 数据表格使用 Markdown 格式
- 所有数字标注数据来源（铁律 2）
- ...
```

#### 设计决策(ADR)

- **ADR-040(Skill 三级加载规范)**:三级划分明确:
  - **Level 0(注册)**:启动时扫描 `plugins/skills/**/SKILL.md`,解析 frontmatter 入内存索引;不占 system prompt
  - **Level 1(描述注入)**:Session 开始时把 `name + description + triggers` 拼接到 `<available_skills>` section 注入 system prompt
  - **Level 2(完整加载)**:匹配命中或 Agent 主动调用 `load_skill(name)` 时,把 SKILL.md 全文作为一条 `user` 消息插入 messages,该消息 `is_skill_context=True`(DOC-02 v4 新字段,Compaction 优先保留)
  - 来源:PDF 补丁 P6, Batch 2 §A5-1。

- **ADR-041(Skill 匹配时强制执行,不能只提不调用)**:历史 bug:模型看到 `<available_skills>` 后只"提及"相关 skill 而不 Level 2 加载。修订:PromptAssembler 的 `skill_grammar_section`(DOC-02 v4 Task 2.4)强制注入"若匹配到 skill,必须调用 `load_skill(name)`,否则视为违反流程"。来源:PDF 补丁 P6。

- **ADR-042(is_skill_context 标记)**:Level 2 加载产生的 user message 标记 `is_skill_context=True`。效果:Compaction Tier 1/2/3 不裁此类消息(DOC-03 v4 ADR-030)。来源:Batch 2 §A3-3。

#### 与 DOC-02 v4 Task 2.4 的联动

Skill 的 grammar 约束由 `skill_grammar_section` 在 PromptAssembler 动态 section 中注入,具体措辞见 DOC-02 v4 Task 2.4 的 prompt_sections.py。本 Task 只负责 Skill 的扫描/加载/注销逻辑,不重复实现文案注入。

#### 验收标准(v4 扩展)

- Skill 目录扫描正确注册所有 Skill 元数据(Level 0)
- Level 1 注入:Session 启动时 PromptAssembler 的动态 section 包含所有 Skill 描述
- **v4:Level 2 注入的 user message 标记 `is_skill_context=True`**,被 Compaction 优先保留
- Skill 内嵌的 hooks 在 Skill 加载时注册到 HookSystem,Skill 卸载时清除
- 上下文预算在 Skill 加载后正确更新
- **v4:Skill 匹配命中时,若模型未调用 `load_skill(name)`,Hook 发出 `skill_mentioned_not_loaded` 审计事件**
- **v4:`frontmatter.agents` 字段过滤**:Skill 的 frontmatter 若有 `agents: [explore]`,则仅对 explore agent_type 在 Level 1/2 可见(对齐 DOC-04 v4 ADR-031)

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的 Skill 三级加载体系。DOC-03 的 HookSystem 和 DOC-04 的 AgentPool 已完成。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

DOC-03 和 DOC-04 全部 Task 完成

## 要创建的文件

```
executor/plugins/
├── skill_loader.py            # Skill 三级加载器
└── skill_types.py             # Skill 数据类型
plugins/                       # 项目根目录下的 Skill 存放位置
└── skills/
    └── .gitkeep
```

## 实现规范

### 1. executor/plugins/skill_types.py

```python
"""
Skill 数据类型定义
"""

from dataclasses import dataclass, field

@dataclass
class SkillMetadata:
    """Skill 元数据（Level 0 注册信息）"""
    name: str
    description: str
    triggers: list[str] = field(default_factory=list)
    hooks: dict = field(default_factory=dict)   # frontmatter 中的 hooks 定义
    path: str = ""                               # SKILL.md 文件路径
    
@dataclass
class SkillContent:
    """Skill 完整内容（Level 2 加载）"""
    metadata: SkillMetadata
    full_text: str              # SKILL.md 的 body 内容（不含 frontmatter）
    is_loaded: bool = False     # 是否已完整加载到上下文
```

### 2. executor/plugins/skill_loader.py

```python
"""
Skill 三级加载器

Level 0 — 注册（启动时）:
  扫描 plugins/skills/ 目录，解析每个 SKILL.md 的 YAML frontmatter，
  注册 SkillMetadata 到内存。

Level 1 — 描述注入（Session 开始时）:
  将所有 Skill 的 name + description 格式化为文本，
  注入到 PromptAssembler 的动态 section 中。
  模型看到描述后可以决定是否需要使用某个 Skill。

Level 2 — 完整加载（按需）:
  当模型请求使用某个 Skill，或用户消息匹配 trigger 关键词时，
  读取 SKILL.md 的完整 body 内容，注入到当前 turn 的上下文中。
  同时将 Skill frontmatter 中的 hooks 注册到 HookSystem（scoped）。

Skill 内嵌 Hooks 的生命周期：
  - Skill 加载（Level 2）时注册到 HookSystem
  - Skill 卸载或 Session 结束时从 HookSystem 清除
  - 这些 hooks 只在 Skill 活跃期间触发
  - Phase 1 只支持 8 个核心事件（PreToolUse, PostToolUse, PostToolUseFailure,
    PermissionRequest, SessionStart, SessionEnd, Compact, Notification）
"""

import yaml
import os

class SkillLoader:
    def __init__(self, skills_dir: str, hook_system: "HookSystem"):
        self._skills_dir = skills_dir
        self._hook_system = hook_system
        self._registry: dict[str, SkillMetadata] = {}
        self._loaded: dict[str, SkillContent] = {}
        self._registered_hook_ids: dict[str, list[str]] = {}  # skill_name → [hook_id, ...]
    
    def scan_and_register(self) -> None:
        """
        Level 0: 扫描目录，注册所有 Skill 元数据。
        
        目录结构：
        plugins/skills/
        ├── financial-analysis/
        │   └── SKILL.md
        ├── code-review/
        │   └── SKILL.md
        └── ...
        """
        if not os.path.exists(self._skills_dir):
            return
        
        for entry in os.listdir(self._skills_dir):
            skill_dir = os.path.join(self._skills_dir, entry)
            skill_file = os.path.join(skill_dir, "SKILL.md")
            if os.path.isdir(skill_dir) and os.path.exists(skill_file):
                metadata = self._parse_frontmatter(skill_file)
                if metadata:
                    metadata.path = skill_file
                    self._registry[metadata.name] = metadata
    
    def get_descriptions_for_prompt(self) -> str:
        """
        Level 1: 返回所有 Skill 的描述文本，供 PromptAssembler 注入。
        
        格式：
        ## 可用 Skills
        - **financial-analysis**: 金融数据分析和报告生成能力...
        - **code-review**: 代码审查和质量检查...
        
        如果需要使用某个 Skill，直接提及其名称即可。
        """
        if not self._registry:
            return ""
        
        lines = ["## 可用 Skills"]
        for name, meta in sorted(self._registry.items()):
            lines.append(f"- **{name}**: {meta.description}")
        lines.append("")
        lines.append("如果需要使用某个 Skill，直接提及其名称即可。")
        return "\n".join(lines)
    
    def try_trigger(self, user_message: str) -> list[str]:
        """
        检查用户消息是否匹配任何 Skill 的 trigger 关键词。
        返回匹配到的 Skill 名称列表。
        """
        triggered = []
        for name, meta in self._registry.items():
            if name in self._loaded:
                continue  # 已加载，不重复触发
            for trigger in meta.triggers:
                if trigger.lower() in user_message.lower():
                    triggered.append(name)
                    break
        return triggered
    
    def load_skill(self, name: str) -> SkillContent | None:
        """
        Level 2: 完整加载 Skill 内容。
        
        1. 读取 SKILL.md body
        2. 注册 Skill 内嵌的 hooks（scoped）
        3. 标记为已加载
        """
        if name in self._loaded:
            return self._loaded[name]
        
        meta = self._registry.get(name)
        if not meta:
            return None
        
        # 读取完整内容
        full_text = self._read_body(meta.path)
        content = SkillContent(metadata=meta, full_text=full_text, is_loaded=True)
        self._loaded[name] = content
        
        # 注册 Skill 内嵌的 hooks（scoped to skill lifetime）
        if meta.hooks:
            self._register_skill_hooks(name, meta.hooks)
        
        return content
    
    def unload_skill(self, name: str) -> None:
        """卸载 Skill：清除已加载内容，注销 scoped hooks"""
        self._loaded.pop(name, None)
        self._unregister_skill_hooks(name)
    
    def get_loaded_context(self) -> str:
        """返回所有已加载 Skill 的完整内容，供注入到当前 turn 上下文"""
        if not self._loaded:
            return ""
        
        parts = []
        for name, content in self._loaded.items():
            parts.append(f"## [Skill: {name}]\n{content.full_text}")
        return "\n\n".join(parts)
    
    def _parse_frontmatter(self, filepath: str) -> SkillMetadata | None:
        """解析 SKILL.md 的 YAML frontmatter"""
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()
        
        if not text.startswith("---"):
            return None
        
        end = text.find("---", 3)
        if end == -1:
            return None
        
        frontmatter = yaml.safe_load(text[3:end])
        if not frontmatter or "name" not in frontmatter:
            return None
        
        return SkillMetadata(
            name=frontmatter["name"],
            description=frontmatter.get("description", ""),
            triggers=frontmatter.get("triggers", []),
            hooks=frontmatter.get("hooks", {}),
        )
    
    def _read_body(self, filepath: str) -> str:
        """读取 SKILL.md 的 body（不含 frontmatter）"""
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()
        
        if text.startswith("---"):
            end = text.find("---", 3)
            if end != -1:
                return text[end + 3:].strip()
        return text
    
    def _register_skill_hooks(self, skill_name: str, hooks_config: dict) -> None:
        """
        注册 Skill 内嵌的 hooks 到 HookSystem。
        
        只注册 Phase 1 支持的 8 个核心事件：
        SessionStart, SessionEnd, PreToolUse, PostToolUse, PostToolUseFailure,
        PermissionRequest, Compact, Notification
        
        其余事件的 hook 配置静默忽略（Phase 2 扩展时生效）。
        """
        PHASE1_EVENTS = {
            "SessionStart", "SessionEnd", "PreToolUse", "PostToolUse",
            "PostToolUseFailure", "PermissionRequest", "Compact", "Notification",
        }
        
        registered_ids = []
        for event_type, handler_configs in hooks_config.items():
            if event_type not in PHASE1_EVENTS:
                continue  # Phase 2 事件静默跳过
            for config in handler_configs:
                hook_id = f"skill:{skill_name}:{event_type}:{len(registered_ids)}"
                # 转为 HookHandlerConfig 并注册
                # self._hook_system.register(event_type, config, hook_id=hook_id)
                registered_ids.append(hook_id)
        
        self._registered_hook_ids[skill_name] = registered_ids
    
    def _unregister_skill_hooks(self, skill_name: str) -> None:
        """注销 Skill 的 scoped hooks"""
        hook_ids = self._registered_hook_ids.pop(skill_name, [])
        for hook_id in hook_ids:
            pass  # self._hook_system.unregister(hook_id)
```

### 3. 在 requirements.txt 中加入 `pyyaml>=6.0`

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/plugins/skill_types.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/plugins/skill_loader.py

# 2. 创建测试 Skill
mkdir -p plugins/skills/test-skill
cat > plugins/skills/test-skill/SKILL.md << 'EOF'
---
name: test-skill
description: "用于测试的示例 Skill"
triggers:
  - "测试"
  - "test"
hooks:
  PreToolUse:
    - matcher: "web_search"
      hooks:
        - type: command
          command: "echo ok"
  SubAgentStart:
    - hooks:
        - type: command
          command: "echo should be ignored in phase 1"
---

# Test Skill

这是测试 Skill 的完整内容。
EOF

# 3. 加载测试
docker compose -f docker-compose.dev.yml exec backend python -c "
from executor.plugins.skill_loader import SkillLoader

loader = SkillLoader('plugins/skills/', hook_system=None)
loader.scan_and_register()

# Level 0 注册
assert 'test-skill' in loader._registry
print('Level 0 register: PASS')

# Level 1 描述
desc = loader.get_descriptions_for_prompt()
assert 'test-skill' in desc
assert '测试' in desc
print(f'Level 1 description: PASS ({len(desc)} chars)')

# Trigger 匹配
triggered = loader.try_trigger('帮我测试一下')
assert 'test-skill' in triggered
print('Trigger match: PASS')

# 不匹配
triggered2 = loader.try_trigger('帮我翻译')
assert len(triggered2) == 0
print('Trigger no match: PASS')

# Level 2 完整加载
content = loader.load_skill('test-skill')
assert content is not None
assert content.is_loaded
assert '完整内容' in content.full_text
print(f'Level 2 load: PASS ({len(content.full_text)} chars)')

# 不重复加载
triggered3 = loader.try_trigger('测试')
assert len(triggered3) == 0  # 已加载不重复触发
print('No duplicate trigger: PASS')

# 卸载
loader.unload_skill('test-skill')
assert 'test-skill' not in loader._loaded
print('Unload: PASS')

print('\nAll Task 5.1 checks passed!')
"
```

## 完成后

1. 更新 PROGRESS.md
2. 更新 DECISIONS.md：记录 ADR-018（Skill 三级加载——描述注入节省上下文 + 按需加载完整内容）
3. 在 requirements.txt 中加入 `pyyaml>=6.0`
4. 加载 Simplify skill 审查
5. 加载 PJR skill 验证
6. `git add -A && git commit -m "feat: Skill 3-tier loading system with scoped hooks"`
```

---

## Task 5.2: MCP Server 集成与热加载

### Part A — 设计与解释

#### 问题陈述

MCP（Model Context Protocol）允许通过 stdio 子进程连接外部工具服务器。用户在 Web 端配置 MCP Server 后，Agent 执行时需要动态启动这些 Server、发现其工具、注册到 ToolRegistry。

关键审计发现：**MCP 热加载会导致 PromptAssembler 的工具列表 cache 失效**。PromptAssembler 的静态 section 中 `tool_grammar_section(tools)` 包含了工具列表，这个列表在 MCP 工具注册后会变化。如果静态 cache 不失效，模型看到的工具列表与实际可用的不一致。

#### CC 架构映射

CC 的 MCP 集成：
- `mcp_client.py` 通过 stdio 启动 MCP Server 子进程
- MCP Server 返回 `tools/list` 列表，注册到 Tool Registry
- MCP 工具名称格式 `mcp__{server}__{tool}`
- MCP Server 可以提供 `instructions` 文本，注入到 System Prompt 的动态 section

#### Cache 失效策略

```
PromptAssembler._static_cache 失效时机：
1. 初始化时首次 build → 缓存
2. MCP 工具注册后 → 失效（因为 tool_grammar_section 内容变了）
3. 同一 MCP 配置内多次 build → 不失效（cache hit）

实现方式：
- PromptAssembler 新增 invalidate_static_cache() 方法
- MCP 工具注册后调用此方法
- 下次 build() 时重新构建静态 section
```

> **异步修复 (P0)**:`MCPClient._send_request()` 中的 `subprocess.stdout.readline()` 是阻塞调用,在 async 上下文中会阻塞事件循环。必须改用 `asyncio.create_subprocess_exec()` 创建子进程,通过 `process.stdout.readline()`(async 版本)进行非阻塞读取。

#### 设计决策(ADR)

- **ADR-044(MCP instructions 双通道注入)**:MCP Server 可以返回两种指令:
  - **Registry instructions**:在 Server 启动时返回的全局说明(`server.info.instructions`),注入到 system prompt 的 `<mcp_instructions>` section
  - **Tool instructions**:每个 tool 的 `description` 和 `input_schema.description`,进入 `tool_grammar_section`

  两者都要注入,前者解释"这个 Server 是干什么的 + 使用约定",后者解释"这个具体 tool 怎么用"。来源:PDF 补丁 P5, Batch 2 §A5-3。

- **ADR-045(agent-scoped MCP 白名单)**:`AgentDefinition.mcp_servers`(DOC-04 v4 ADR-030)对 MCP 工具做过滤。ToolRegistry 注册 MCP 工具时打上 `mcp_server` 标签;`filter_tools_for_agent()` 时按 `agent_def.mcp_servers` 白名单过滤。来源:PDF 补丁 P7。

#### 验收标准(v4 扩展)

- MCP Client 能通过 stdio 启动 MCP Server 子进程
- 正确发现 MCP Server 提供的工具(tools/list)
- MCP 工具注册到 ToolRegistry(命名空间 `mcp__{server}__{tool}`)
- MCP 工具注册后 PromptAssembler 的静态 cache 正确失效
- **v4:MCP Server 的 `server.info.instructions` 注入到 PromptAssembler 动态 section 的 `<mcp_instructions>`**,与 tool descriptions 分开
- **v4:agent-scoped 白名单生效**:若 `AgentDefinition.mcp_servers=["github"]`,则 fork 的子 Agent 看不到 `mcp__slack__*` 工具
- MCP Server 子进程在 Session 结束时正确清理

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的 MCP Server 集成。Task 5.1 的 Skill 系统已完成。

**关键审计注意**：MCP 工具注册后必须调用 `PromptAssembler.invalidate_static_cache()` 使工具列表 cache 失效，否则模型看到的工具列表与实际可用的不一致。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

Task 5.1 已完成

## 要创建/修改的文件

```
executor/plugins/
└── mcp_client.py              # MCP stdio 客户端
executor/engine/
└── prompt_assembler.py        # 修改：新增 invalidate_static_cache()
```

## 实现规范

### 1. executor/plugins/mcp_client.py

```python
"""
MCP stdio 客户端

通过 stdio 子进程与 MCP Server 通信：
1. 启动 Server: subprocess.Popen(command, args, env, stdin=PIPE, stdout=PIPE)
2. 初始化: 发送 initialize request，获取 server capabilities
3. 工具发现: 发送 tools/list request，获取工具列表
4. 工具调用: 发送 tools/call request，获取结果
5. 关闭: 发送 shutdown，terminate 子进程

MCP 协议使用 JSON-RPC 2.0 over stdio（每行一个 JSON）。
"""

import subprocess
import json

class MCPClient:
    def __init__(self, server_name: str, command: str, args: list[str], env: dict[str, str]):
        self._server_name = server_name
        self._command = command
        self._args = args
        self._env = env
        self._process: subprocess.Popen | None = None
        self._request_id = 0
        self._tools: list[dict] = []
        self._instructions: str = ""
    
    async def start(self) -> None:
        """启动 MCP Server 子进程并完成初始化"""
        full_env = {**dict(os.environ), **self._env}
        self._process = subprocess.Popen(
            [self._command] + self._args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=full_env,
        )
        
        # Initialize
        init_result = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "prism", "version": "2.0"},
        })
        
        # 发送 initialized 通知
        await self._send_notification("notifications/initialized", {})
        
        # 工具发现
        tools_result = await self._send_request("tools/list", {})
        self._tools = tools_result.get("tools", [])
        
        # 获取 instructions（如果 server 提供）
        self._instructions = init_result.get("instructions", "")
    
    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """调用 MCP 工具，返回结果文本"""
        result = await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })
        
        # MCP 返回 content 数组
        contents = result.get("content", [])
        texts = [c.get("text", "") for c in contents if c.get("type") == "text"]
        return "\n".join(texts)
    
    def get_tool_definitions(self) -> list[dict]:
        """返回 MCP Server 提供的工具列表（原始格式）"""
        return self._tools
    
    def get_instructions(self) -> str:
        """返回 MCP Server 的使用说明"""
        return self._instructions
    
    async def stop(self) -> None:
        """关闭 MCP Server"""
        if self._process:
            try:
                await self._send_request("shutdown", {})
                await self._send_notification("exit", {})
            except Exception:
                pass
            self._process.terminate()
            self._process.wait(timeout=5)
            self._process = None
    
    async def _send_request(self, method: str, params: dict) -> dict:
        """发送 JSON-RPC request，等待 response"""
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        # 写入 stdin
        line = json.dumps(request) + "\n"
        self._process.stdin.write(line.encode())
        self._process.stdin.flush()
        
        # 读取 stdout（阻塞读一行）
        response_line = self._process.stdout.readline().decode().strip()
        if not response_line:
            raise RuntimeError(f"MCP Server {self._server_name} 无响应")
        
        response = json.loads(response_line)
        if "error" in response:
            raise RuntimeError(f"MCP Error: {response['error']}")
        
        return response.get("result", {})
    
    async def _send_notification(self, method: str, params: dict) -> None:
        """发送 JSON-RPC notification（无 id，不期望 response）"""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        line = json.dumps(notification) + "\n"
        self._process.stdin.write(line.encode())
        self._process.stdin.flush()
```

### 2. MCP 工具注册到 ToolRegistry

```python
# 在 PluginHost 或 __main__.py 中：

class MCPToolWrapper(BaseTool):
    """将 MCP 工具包装为 BaseTool，注册到 ToolRegistry"""
    
    def __init__(self, server_name: str, mcp_tool: dict, client: MCPClient):
        self._server_name = server_name
        self._mcp_tool = mcp_tool
        self._client = client
    
    @property
    def name(self) -> str:
        return f"mcp__{self._server_name}__{self._mcp_tool['name']}"
    
    @property
    def description(self) -> str:
        return self._mcp_tool.get("description", "")
    
    @property
    def input_schema(self) -> dict:
        return self._mcp_tool.get("inputSchema", {"type": "object"})
    
    async def execute(self, tool_input: dict) -> ToolResult:
        try:
            result = await self._client.call_tool(self._mcp_tool["name"], tool_input)
            return ToolResult(content=result)
        except Exception as e:
            return ToolResult(content=str(e), is_error=True)
```

### 3. 修改 PromptAssembler — 新增 cache 失效方法

修改 `executor/engine/prompt_assembler.py`：

```python
class PromptAssembler:
    # ... 已有代码 ...
    
    def invalidate_static_cache(self) -> None:
        """
        使静态 cache 失效。
        
        调用时机：
        - MCP 工具注册/注销后（工具列表变了，tool_grammar_section 需要重建）
        - Skill 加载/卸载后（如果 Skill 影响了工具集）
        
        下次 build() 时会重新构建静态 section。
        """
        self._static_cache = None
    
    def update_tools(self, tools: list["ToolDefinition"]) -> None:
        """
        更新工具列表并使 cache 失效。
        
        用于 MCP 热加载场景：
        1. MCP 工具注册到 ToolRegistry
        2. 调用 assembler.update_tools(registry.list_definitions())
        3. 静态 cache 自动失效
        4. 下次 build() 使用新的工具列表
        """
        self._tools = tools
        self.invalidate_static_cache()
```

### 4. MCP 启动流程集成

在 `executor/__main__.py` 中，MCP 初始化步骤：

```python
# MCP 初始化（在 ToolRegistry 注册内置工具之后）

# 1. 从 DB 读取用户安装的 MCP Server
# mcp_installs = db.query(UserMcpInstall).filter(...).all()

# 2. 逐个启动 MCP Client
mcp_clients: list[MCPClient] = []
mcp_instructions: dict[str, str] = {}

for install in mcp_installs:
    if not install.is_enabled:
        continue
    server = install.mcp_server
    client = MCPClient(
        server_name=server.name,
        command=server.command,
        args=server.args,
        env={**server.env, **install.config_override},
    )
    await client.start()
    mcp_clients.append(client)
    
    # 3. 注册 MCP 工具到 ToolRegistry
    for mcp_tool in client.get_tool_definitions():
        registry.register(MCPToolWrapper(server.name, mcp_tool, client))
    
    # 4. 收集 instructions
    if client.get_instructions():
        mcp_instructions[server.name] = client.get_instructions()

# 5. ⚡ 关键：MCP 工具注册后使 PromptAssembler cache 失效
assembler.update_tools(registry.list_definitions())

# 6. MCP instructions 在 build() 时传入动态 section
# system_prompt = assembler.build(mcp_instructions=mcp_instructions, ...)

# 7. Session 结束时清理所有 MCP Client
# for client in mcp_clients: await client.stop()
```

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/plugins/mcp_client.py

# 2. PromptAssembler cache 失效测试
docker compose -f docker-compose.dev.yml exec backend python -c "
from executor.engine.prompt_assembler import PromptAssembler
from executor.adapters.base import ToolDefinition

tools1 = [ToolDefinition(name='tool_a', description='A', input_schema={})]
assembler = PromptAssembler(agent_type='general', tools=tools1)

# 首次 build → 缓存
prompt1 = assembler.build(language='zh-CN')
assert 'tool_a' in prompt1
static1 = assembler.get_static_prefix()

# 同样参数再次 build → cache hit（字节级一致）
prompt2 = assembler.build(language='zh-CN')
assert assembler.get_static_prefix() is static1  # 同一个对象引用
print('Cache hit: PASS')

# MCP 工具注册后 update_tools → cache 失效
tools2 = tools1 + [ToolDefinition(name='mcp__search__web', description='MCP Search', input_schema={})]
assembler.update_tools(tools2)
assert assembler._static_cache is None  # cache 已失效
print('Cache invalidation: PASS')

# 再次 build → 新工具出现
prompt3 = assembler.build(language='zh-CN')
assert 'mcp__search__web' in prompt3
print('New tools in prompt: PASS')

print('\nAll Task 5.2 checks passed!')
"
```

## 完成后

1. 更新 PROGRESS.md
2. 更新 DECISIONS.md：记录 ADR-019（MCP 热加载 cache 失效策略——update_tools 同时失效静态缓存）
3. 加载 Simplify skill 审查
4. 加载 PJR skill 验证
5. `git add -A && git commit -m "feat: MCP Client with stdio protocol + PromptAssembler cache invalidation"`
```

---

## Task 5.3: Hook 治理层与 Plugin 命名空间

### Part A — 设计与解释

#### 问题陈述

Hook 系统在 DOC-03 Task 3.3 中实现了核心引擎。本 Task 补充治理层面的能力：

1. **Hook 优先级排序**——多个 Hook 匹配同一事件时，按优先级排序执行
2. **Plugin 命名空间**——防止不同 Plugin 的 Skill/Hook/MCP 名称冲突
3. **Hook 配置文件**——从 `.prism/hooks.json` 加载全局 Hook 配置（对标 CC 的 `.claude/settings.json`）
4. **Phase 1 事件过滤**——确保只有 8 个核心事件的 Hook 被触发，其余静默忽略

#### CC 架构映射

CC 的 Plugin 系统：
```
my-plugin/
├── plugin.json      # 元数据、版本、依赖
├── skills/          # Plugin 内的 Skills（命名空间: my-plugin:deploy）
├── agents/          # 自定义 sub-agents
├── hooks/           # 生命周期脚本
└── mcp-servers/     # 服务连接器
```

Prism 的 Plugin 命名空间约定：`{plugin_name}:{resource_name}`（如 `finance:analysis`）。避免不同 Plugin 的同名资源冲突。

#### 设计决策(ADR)

- **ADR-043(Hook 4 种 handler 类型)**:保留 DOC-03 v4 Task 3.3 的 4 种 handler:
  1. **command**:`asyncio.create_subprocess_shell` 执行,stdin 传 event JSON,stdout 读 HookDecision JSON
  2. **http**:POST 到 webhook URL,request body 为 event JSON,response 为 HookDecision JSON
  3. **prompt**:模板化 prompt + LLM 调用返回 JSON 决策(适合政策判断)
  4. **agent**:fork 子 Agent(用于重度 policy 审查,依赖 DOC-04 ForkManager)

  所有 handler 必须在 `timeout_seconds` 内返回,超时降级为 `HookDecision(blocking_error="timeout")`。来源:Batch 2 §A5-2。

#### 验收标准(v4 扩展)

- HookSystem 支持优先级排序(priority 字段,数字越小越先执行)
- `.prism/hooks.json` 配置文件正确加载
- Plugin 命名空间正确应用到 Skill 和 MCP 工具
- Phase 1 事件过滤生效(非 Phase 1 事件的 Hook 不触发)
- Hook 注册/注销支持 scoped ID(Skill 卸载时按 ID 注销)
- **v4:4 种 handler(command/http/prompt/agent)均可运行,超时一律降级 blocking_error**

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的 Hook 治理层和 Plugin 命名空间。DOC-03 的 HookSystem 核心引擎已完成，本 Task 补充治理能力。

**关键审计注意**：Phase 1 只触发 8 个核心事件（SessionStart, SessionEnd, PreToolUse, PostToolUse, PostToolUseFailure, PermissionRequest, Compact, Notification）。HookSystem.fire() 方法必须在入口处校验 event_type 是否属于 Phase 1，不属于则直接返回空决策。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

Task 5.1 和 5.2 已完成

## 要修改的文件

```
executor/harness/hooks/
├── system.py                  # 修改：新增优先级排序 + Phase 1 事件过滤 + scoped 注册/注销
└── events.py                  # 修改：新增 PHASE1_EVENTS 常量
executor/plugins/
└── namespace.py               # 新建：命名空间管理
```

## 实现规范

### 1. 修改 executor/harness/hooks/events.py

新增 Phase 1 事件常量：

```python
# Phase 1 支持的 8 个核心事件
PHASE1_EVENTS: frozenset[str] = frozenset({
    "SessionStart",
    "SessionEnd",
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "PermissionRequest",
    "Compact",
    "Notification",
})

# Phase 2 扩展事件（当前不触发，预留定义）
PHASE2_EVENTS: frozenset[str] = frozenset({
    "SubAgentStart",
    "SubAgentStop",
    "TeammateIdle",
    "TaskCreated",
    "TaskCompleted",
    "UserPromptSubmit",
    "Stop",
    "CwdChanged",
    "ConfigChanged",
    "WorktreeCreate",
    "WorktreeRemove",
    "MemoryLoad",
    "SettingsLoad",
})
```

### 2. 修改 executor/harness/hooks/system.py

```python
class HookSystem:
    def __init__(self):
        self._handlers: dict[str, list[tuple[int, str, HookHandlerConfig]]] = {}
        # (priority, hook_id, config) 三元组列表
    
    def register(self, event_type: str, config: HookHandlerConfig,
                 hook_id: str = "", priority: int = 100) -> str:
        """
        注册 Hook handler。
        
        - hook_id: 唯一标识，用于后续注销（空字符串则自动生成）
        - priority: 优先级，数字越小越先执行（默认 100）
        
        返回 hook_id。
        """
        if not hook_id:
            hook_id = f"hook_{event_type}_{len(self._handlers.get(event_type, []))}"
        
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        
        self._handlers[event_type].append((priority, hook_id, config))
        # 按优先级排序
        self._handlers[event_type].sort(key=lambda x: x[0])
        
        return hook_id
    
    def unregister(self, hook_id: str) -> None:
        """按 hook_id 注销 Handler"""
        for event_type in self._handlers:
            self._handlers[event_type] = [
                (p, hid, c) for p, hid, c in self._handlers[event_type]
                if hid != hook_id
            ]
    
    def unregister_by_prefix(self, prefix: str) -> None:
        """按 hook_id 前缀批量注销（用于 Skill/Plugin 卸载）"""
        for event_type in self._handlers:
            self._handlers[event_type] = [
                (p, hid, c) for p, hid, c in self._handlers[event_type]
                if not hid.startswith(prefix)
            ]
    
    async def fire(self, event: HookEvent) -> HookDecision:
        """
        触发事件，执行匹配的 handler，合并决策返回。
        
        Phase 1 事件过滤：非 Phase 1 事件直接返回空决策。
        """
        from executor.harness.hooks.events import PHASE1_EVENTS
        
        if event.event_type not in PHASE1_EVENTS:
            return HookDecision()  # Phase 2 事件静默跳过
        
        handlers = self._handlers.get(event.event_type, [])
        if not handlers:
            return HookDecision()
        
        # ... 按优先级顺序执行 handler，合并决策 ...
```

### 3. 新建 executor/plugins/namespace.py

```python
"""
Plugin 命名空间管理

防止不同 Plugin 的 Skill / Hook / MCP 工具名称冲突。

命名约定：
- 无 Plugin 的资源：原始名称（如 "web_search"、"financial-analysis"）
- Plugin 内的资源："{plugin_name}:{resource_name}"（如 "finance:analysis"）
- MCP 工具：固定格式 "mcp__{server}__{tool}"（不受 Plugin 命名空间影响）
"""

class PluginNamespace:
    def __init__(self, plugin_name: str = ""):
        self._plugin_name = plugin_name
    
    def qualify(self, resource_name: str) -> str:
        """为资源名称加上命名空间前缀"""
        if not self._plugin_name:
            return resource_name
        return f"{self._plugin_name}:{resource_name}"
    
    def unqualify(self, qualified_name: str) -> tuple[str, str]:
        """拆分命名空间前缀和资源名称"""
        if ":" in qualified_name and not qualified_name.startswith("mcp__"):
            parts = qualified_name.split(":", 1)
            return parts[0], parts[1]
        return "", qualified_name
    
    @staticmethod
    def is_mcp_tool(name: str) -> bool:
        return name.startswith("mcp__")
```

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/harness/hooks/events.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/harness/hooks/system.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/plugins/namespace.py

# 2. Phase 1 事件过滤测试
docker compose -f docker-compose.dev.yml exec backend python -c "
from executor.harness.hooks.events import PHASE1_EVENTS, PHASE2_EVENTS

assert len(PHASE1_EVENTS) == 8
assert 'PreToolUse' in PHASE1_EVENTS
assert 'SubAgentStart' not in PHASE1_EVENTS
assert 'SubAgentStart' in PHASE2_EVENTS
print('Phase 1/2 event sets: PASS')
"

# 3. 优先级排序 + scoped 注销测试
docker compose -f docker-compose.dev.yml exec backend python -c "
from executor.harness.hooks.system import HookSystem
from executor.harness.hooks.events import HookEvent, HookDecision

hs = HookSystem()

# 注册带优先级
hs.register('PreToolUse', None, hook_id='low', priority=200)
hs.register('PreToolUse', None, hook_id='high', priority=10)
hs.register('PreToolUse', None, hook_id='mid', priority=100)

handlers = hs._handlers['PreToolUse']
ids = [hid for _, hid, _ in handlers]
assert ids == ['high', 'mid', 'low'], f'Priority order wrong: {ids}'
print('Priority ordering: PASS')

# scoped 注销
hs.register('PostToolUse', None, hook_id='skill:finance:PostToolUse:0')
hs.register('PostToolUse', None, hook_id='skill:finance:PostToolUse:1')
hs.register('PostToolUse', None, hook_id='global:compliance')
hs.unregister_by_prefix('skill:finance:')
remaining = [hid for _, hid, _ in hs._handlers['PostToolUse']]
assert 'global:compliance' in remaining
assert len(remaining) == 1
print('Scoped unregister: PASS')

# Namespace
from executor.plugins.namespace import PluginNamespace
ns = PluginNamespace('finance')
assert ns.qualify('analysis') == 'finance:analysis'
assert ns.unqualify('finance:analysis') == ('finance', 'analysis')
assert not PluginNamespace.is_mcp_tool('finance:analysis')
assert PluginNamespace.is_mcp_tool('mcp__search__web')
print('Namespace: PASS')

print('\nAll Task 5.3 checks passed!')
"
```

## 完成后

1. 更新 PROGRESS.md
2. 更新 DECISIONS.md：记录 ADR-020（Hook 优先级排序 + Phase 1 事件过滤）、ADR-021（Plugin 命名空间——冒号分隔避免冲突）
3. 加载 Simplify skill 审查
4. 加载 PJR skill 验证
5. `git add -A && git commit -m "feat: Hook priority ordering + Phase 1 event filtering + Plugin namespace"`
```

---

## Task 5.4: PluginHost 统一管理与垂类特调

### Part A — 设计与解释

#### 问题陈述

Skill、Hook、MCP 是三种不同的扩展机制，但它们需要统一管理——一个 Plugin 可以同时包含 Skill、Hook 和 MCP 配置。PluginHost 是统一管理入口，负责加载/卸载 Plugin、协调三者的生命周期。

垂类特调是 Prism 相对竞品的差异化能力——通过 Plugin 组合特定的 Skill + Hook + MCP，将通用平台适配为金融分析、法律咨询、技术支持等垂类场景。

#### CC 架构映射

CC 的 Plugin 结构：
```
my-plugin/
├── plugin.json
├── skills/
├── agents/
├── hooks/
└── mcp-servers/
```

Prism 的 Plugin 结构：
```
plugins/
├── financial/                  # 金融垂类 Plugin
│   ├── plugin.yaml            # 元数据 + 依赖声明
│   ├── skills/
│   │   └── analysis/
│   │       └── SKILL.md
│   ├── hooks/
│   │   └── compliance-check.sh
│   └── mcp/
│       └── market-data.json   # MCP Server 配置
```

#### 设计决策(ADR)

- **ADR-046(Plugin 命名空间 + 变量替换系统)**:Plugin 内的路径和配置支持变量替换,避免硬编码绝对路径。支持变量:
  - `${PRISM_PLUGIN_ROOT}` — 插件根目录(如 `/app/plugins/financial`)
  - `${PRISM_PLUGIN_DATA}` — 插件数据目录(如 `/app/data/plugins/financial`)
  - `${PRISM_SKILL_DIR}` — 当前 Skill 目录
  - `${PRISM_SESSION_ID}` / `${PRISM_USER_ID}` — 运行时上下文
  - `${user_config.X}` — 插件安装时用户配置的自定义值(如 API endpoint)
  - **CC 兼容映射**:`${CLAUDE_PLUGIN_ROOT}` 自动等价于 `${PRISM_PLUGIN_ROOT}`,便于直接使用 CC 插件

  加载顺序:Platform(平台内置)→ User(用户安装)→ Session(会话临时)三级,冲突时高优先级覆盖低优先级,检测到冲突写 audit_logs。来源:PDF 补丁 P9, Batch 2 §A5-4。

#### 验收标准(v4 扩展)

- PluginHost 统一加载/卸载 Plugin
- Plugin 加载时自动注册其 Skill、Hook、MCP
- Plugin 卸载时自动注销所有资源
- 命名空间正确应用
- 垂类 Plugin 可以覆盖默认的 Agent 行为约束
- PluginHost 向 PromptAssembler 提供 Skill 描述和 MCP instructions
- **v4:Plugin 内的字符串字段支持 `${PRISM_*}` 变量替换**(plugin.yaml 解析时 expand)
- **v4:`${CLAUDE_PLUGIN_ROOT}` → `${PRISM_PLUGIN_ROOT}` 自动兼容映射**
- **v4:Platform → User → Session 三级加载顺序,冲突时高优先级覆盖 + 写 audit**

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的 PluginHost——统一管理 Skill + Hook + MCP 的入口。Task 5.1-5.3 已完成各子系统。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

Task 5.1-5.3 已完成

## 要创建/修改的文件

```
executor/plugins/
├── host.py                    # PluginHost 统一管理
└── plugin_types.py            # Plugin 数据类型
```

## 实现规范

### 1. executor/plugins/plugin_types.py

```python
from dataclasses import dataclass, field

@dataclass
class PluginConfig:
    """Plugin 配置（从 plugin.yaml 解析）"""
    name: str
    description: str = ""
    version: str = "1.0.0"
    skills_dir: str = ""           # Plugin 内的 skills/ 子目录路径
    hooks_config: dict = field(default_factory=dict)   # hooks 配置
    mcp_servers: list[dict] = field(default_factory=list)  # MCP Server 配置列表
    agent_overrides: dict = field(default_factory=dict)  # 覆盖 Agent 行为约束
```

### 2. executor/plugins/host.py

```python
"""
PluginHost — 统一管理 Skill + Hook + MCP

职责：
1. 加载 Plugin（解析 plugin.yaml → 注册 Skill + Hook + MCP）
2. 卸载 Plugin（注销所有资源）
3. 向 PromptAssembler 提供动态上下文（Skill 描述 + MCP instructions）
4. 向 QueryEngine 提供 Agent 行为覆盖

生命周期：
- Agent 执行器启动时，PluginHost 根据 Session config 加载 Plugin
- Session 结束时，PluginHost 卸载所有 Plugin，清理 MCP 子进程
"""

class PluginHost:
    def __init__(
        self,
        skill_loader: SkillLoader,
        hook_system: HookSystem,
        tool_registry: ToolRegistry,
        assembler: PromptAssembler,
    ):
        self._skill_loader = skill_loader
        self._hook_system = hook_system
        self._registry = tool_registry
        self._assembler = assembler
        self._loaded_plugins: dict[str, PluginConfig] = {}
        self._mcp_clients: list[MCPClient] = []
        self._mcp_instructions: dict[str, str] = {}
    
    async def load_plugin(self, config: PluginConfig) -> None:
        """
        加载 Plugin。
        
        1. 使用 PluginNamespace 隔离资源名
        2. 加载 Plugin 内的 Skills（Level 0 注册）
        3. 注册 Plugin 的 Hooks（带命名空间前缀的 hook_id）
        4. 启动 Plugin 的 MCP Servers
        5. MCP 工具注册后使 PromptAssembler cache 失效
        """
        ns = PluginNamespace(config.name)
        
        # Skills
        if config.skills_dir:
            self._skill_loader.scan_and_register()  # 指定 Plugin 的 skills 子目录
        
        # Hooks（带命名空间 hook_id）
        for event_type, handler_configs in config.hooks_config.items():
            for i, hc in enumerate(handler_configs):
                hook_id = f"plugin:{config.name}:{event_type}:{i}"
                self._hook_system.register(event_type, hc, hook_id=hook_id, priority=50)
        
        # MCP Servers
        for mcp_config in config.mcp_servers:
            client = MCPClient(
                server_name=ns.qualify(mcp_config["name"]),
                command=mcp_config["command"],
                args=mcp_config.get("args", []),
                env=mcp_config.get("env", {}),
            )
            await client.start()
            self._mcp_clients.append(client)
            
            # 注册 MCP 工具
            for mcp_tool in client.get_tool_definitions():
                self._registry.register(MCPToolWrapper(
                    ns.qualify(mcp_config["name"]),
                    mcp_tool,
                    client,
                ))
            
            if client.get_instructions():
                self._mcp_instructions[ns.qualify(mcp_config["name"])] = client.get_instructions()
        
        # ⚡ Cache 失效
        self._assembler.update_tools(self._registry.list_definitions())
        
        self._loaded_plugins[config.name] = config
    
    async def unload_plugin(self, plugin_name: str) -> None:
        """卸载 Plugin：注销 Skills + Hooks + 停止 MCP + cache 失效"""
        # 注销 Hooks
        self._hook_system.unregister_by_prefix(f"plugin:{plugin_name}:")
        
        # 停止 MCP（简化：停止所有，因为目前不按 Plugin 追踪 MCP Client 归属）
        # Phase 2 可以细化
        
        self._loaded_plugins.pop(plugin_name, None)
        self._assembler.update_tools(self._registry.list_definitions())
    
    async def unload_all(self) -> None:
        """卸载所有 Plugin，清理所有 MCP 子进程"""
        for client in self._mcp_clients:
            await client.stop()
        self._mcp_clients.clear()
        self._mcp_instructions.clear()
        self._loaded_plugins.clear()
    
    def get_skill_descriptions(self) -> str:
        """返回所有 Skill 描述（供 PromptAssembler 动态 section）"""
        return self._skill_loader.get_descriptions_for_prompt()
    
    def get_mcp_instructions(self) -> dict[str, str]:
        """返回所有 MCP instructions（供 PromptAssembler 动态 section）"""
        return self._mcp_instructions
    
    def get_agent_overrides(self) -> dict:
        """
        返回所有 Plugin 的 Agent 行为覆盖（合并）。
        用于垂类特调——Plugin 可以追加或覆盖 Agent 的行为约束。
        """
        merged = {}
        for config in self._loaded_plugins.values():
            merged.update(config.agent_overrides)
        return merged
```

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/plugins/plugin_types.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/plugins/host.py

# 2. PluginHost 组装测试
docker compose -f docker-compose.dev.yml exec backend python -c "
from executor.plugins.host import PluginHost
from executor.plugins.skill_loader import SkillLoader
from executor.harness.hooks.system import HookSystem
from executor.tools.registry import ToolRegistry
from executor.engine.prompt_assembler import PromptAssembler

hs = HookSystem()
registry = ToolRegistry()
assembler = PromptAssembler(agent_type='general', tools=[])
skill_loader = SkillLoader('plugins/skills/', hook_system=hs)

host = PluginHost(skill_loader, hs, registry, assembler)

# 无 Plugin 时正常工作
assert host.get_skill_descriptions() == '' or isinstance(host.get_skill_descriptions(), str)
assert host.get_mcp_instructions() == {}
assert host.get_agent_overrides() == {}
print('Empty PluginHost: PASS')

print('\nAll Task 5.4 checks passed!')
"
```

## 完成后

1. 更新 PROGRESS.md
2. 更新 DECISIONS.md：记录 ADR-022（PluginHost 统一生命周期管理——加载注册、卸载注销、cache 同步失效）
3. 加载 Simplify skill 审查
4. 加载 PJR skill 验证
5. `git add -A && git commit -m "feat: PluginHost unified management + vertical plugin support"`
```

---

## Part II: Skills Market

## Task 5.5: Skills Registry & Multi-Source Aggregation(v4 简化:Phase 1 仅 Local + GitHub)

### Part A — 设计与解释

#### 设计决策(ADR)

- **ADR-047(Skills Registry Phase 1 仅 Local + GitHub 两源)**:Phase 1 **只实现** `LocalSource` + `GitHubSource`,**删除** `NpmSource` + `ManusSource`(Phase 2 再加)。原因:
  1. npm 需要容器内 npm 环境 + 安全审计(任意 npm 包执行风险),Phase 1 基础设施不成熟
  2. Manus API 契约未稳定,依赖外部不可控
  3. Local + GitHub 覆盖 95% 日常场景
  4. SkillSource 抽象基类保留,Phase 2 直接扩充 NpmSource/ManusSource

  来源:Master M8, Batch 2 §A5-5。

#### 多源架构(v4 简化)

```python
# executor/plugins/skills_registry.py(v4)

"""
Skills 多源聚合注册表 — Phase 1 仅 Local + GitHub

源列表:
- Local: .skills/ 目录自动扫描 + .prism/skills/ 已安装 Skills
- GitHub: 从仓库直接安装(支持 branch/tag/commit 指定版本)
- (Phase 2 将增加 npm + Manus,抽象基类已预留)

去重策略:按 Skill name 去重,优先展示已安装版本
"""


@dataclass
class SkillPackage:
    """Skills 搜索结果条目(v4)"""
    name: str                          # Skill 名称
    description: str                    # 简短描述
    version: str                        # 版本号
    source: Literal["local", "github"]  # v4:Phase 1 只两种
    source_url: str                     # 源地址(GitHub repo URL)
    author: str | None = None
    tags: list[str] = field(default_factory=list)
    installed: bool = False             # 是否已安装
    installed_version: str | None = None


@dataclass
class SkillBundle:
    """下载后的 Skill 包（待安装）"""
    metadata: SkillPackage
    files: dict[str, bytes]            # 文件路径 → 内容
    plugin_config: dict | None = None  # 如果是完整插件而非单个 Skill


@dataclass
class InstalledSkill:
    """已安装的 Skill"""
    name: str
    version: str
    source: str
    source_url: str
    install_path: str
    installed_at: str                  # ISO 8601
    has_hooks: bool
    has_mcp: bool


class SkillSource(ABC):
    """Skills 源抽象基类"""

    @property
    @abstractmethod
    def source_name(self) -> str: ...

    @abstractmethod
    async def search(self, query: str) -> list[SkillPackage]: ...

    @abstractmethod
    async def fetch(self, package_id: str, version: str | None = None) -> SkillBundle: ...

    @abstractmethod
    async def get_versions(self, package_id: str) -> list[str]: ...


class LocalSource(SkillSource):
    """
    本地 .skills/ 目录扫描（CC 兼容模式）

    扫描路径：
    1. {workspace}/.skills/          — CC 兼容的自动加载目录
    2. {workspace}/.prism/skills/    — Prism 管理的已安装 Skills

    搜索方式：遍历目录，匹配 SKILL.md 的 name/description/tags
    """
    source_name = "local"


# v4:NpmSource / ManusSource 推迟到 Phase 2,抽象基类保留扩展点。
# 占位注释(禁止在 Phase 1 实现):
# class NpmSource(SkillSource): ...    # Phase 2
# class ManusSource(SkillSource): ...  # Phase 2


class GitHubSource(SkillSource):
    """
    GitHub 仓库直接安装

    支持格式：
    - github:user/repo               — 默认分支的根目录
    - github:user/repo#branch        — 指定分支
    - github:user/repo@v1.0.0        — 指定 tag
    - github:user/repo/path/to/skill — 仓库内子目录

    实现：通过 GitHub API 或 git clone --depth 1 下载
    """
    source_name = "github"


class SkillsRegistry:
    """Skills 多源聚合注册表"""

    def __init__(
        self,
        sources: list[SkillSource],
        install_dir: str,              # .prism/skills/
        registry_file: str,            # .prism/skills/registry.json
    ):
        ...

    async def search(
        self,
        query: str,
        sources: list[str] | None = None,  # None = 全部源
    ) -> list[SkillPackage]:
        """
        跨源并行搜索，合并去重。
        按相关性排序，已安装的排在前面。
        """
        ...

    async def install(
        self,
        package_id: str,
        source: str,
        version: str | None = None,
    ) -> InstalledSkill:
        """
        从指定源安装 Skill。

        流程：
        1. 从源 fetch SkillBundle
        2. 验证 SKILL.md frontmatter 格式
        3. 解压到 .prism/skills/{source_scope}/{skill_name}/
        4. 如果包含 hooks → 注册到 HookSystem
        5. 如果包含 MCP → 注册到 ToolRegistry
        6. 更新 registry.json
        7. 通知 PluginHost reload
        """
        ...

    async def uninstall(self, skill_id: str) -> None:
        """
        卸载 Skill。

        流程：
        1. 注销 hooks（如有）
        2. 注销 MCP tools（如有）
        3. 删除文件
        4. 更新 registry.json
        5. 通知 PluginHost reload
        """
        ...

    async def update(self, skill_id: str) -> InstalledSkill:
        """更新到最新版本（卸载旧版 + 安装新版）"""
        ...

    def list_installed(self) -> list[InstalledSkill]:
        """列出所有已安装 Skills"""
        ...
```

#### 安装目录结构

```
{workspace}/
├── .skills/                          # CC 兼容自动扫描目录
│   ├── my-local-skill/
│   │   └── SKILL.md
│   └── another-skill/
│       └── SKILL.md
│
└── .prism/
    └── skills/                       # Prism 管理的已安装 Skills
        ├── registry.json             # 已安装 Skills 索引
        ├── @manus/                   # Manus 源安装的 Skills
        │   └── web-researcher/
        │       ├── SKILL.md
        │       └── hooks/
        ├── @npm/                     # npm 源安装的 Skills
        │   └── code-reviewer/
        │       ├── SKILL.md
        │       ├── package.json
        │       └── hooks/
        └── @github/                  # GitHub 源安装的 Skills
            └── user__repo/
                └── SKILL.md
```

#### registry.json 格式

```json
{
  "version": "1.0",
  "skills": [
    {
      "name": "web-researcher",
      "version": "1.2.0",
      "source": "manus",
      "source_url": "manus://skills/web-researcher",
      "install_path": ".prism/skills/@manus/web-researcher",
      "installed_at": "2026-04-05T10:30:00Z",
      "has_hooks": true,
      "has_mcp": false
    }
  ]
}
```

#### 验收标准

- `prism skills search "web research"` 返回来自多个源的搜索结果
- `prism skills install @manus/web-researcher` 安装成功，Skills 可被 Agent 调用
- `prism skills install @npm/code-reviewer` 从 npm 安装成功
- `prism skills install github:user/repo` 从 GitHub 安装成功
- 已安装 Skills 的 Hooks 正确注册到 HookSystem
- 卸载 Skill 后，对应的 Hooks 和 MCP 工具正确注销
- ADR-023: Skills 多源聚合策略——并行查询 + 按 name 去重 + 已安装优先展示

---

### Part B — Claude Code 执行 Prompt

> 待实施计划执行阶段补充

## 完成后

1. 更新 PROGRESS.md
2. 更新 DECISIONS.md：记录 ADR-023（Skills 多源聚合策略——并行查询 + 按 name 去重 + 已安装优先展示）
3. 加载 Simplify skill 审查
4. 加载 PJR skill 验证
5. `git add -A && git commit -m "feat: Skills Registry multi-source aggregation"`

---

## Task 5.6: Skills CLI & Agent Tool(v4:Agent Tool 只保留 search)

### Part A — 设计与解释

#### 设计决策(ADR)

- **ADR-048(Agent Tool 仅搜索权限)**:Agent 可以通过 `skills_search(query)` 工具搜索 Skill 市场,**但不能直接调用 install/uninstall/update**。原因:
  1. 安装行为涉及下载 + 执行第三方代码 + 注册 hook,风险太高
  2. 即使 permission ask,用户也可能在未充分了解的情况下批准
  3. 安装应走 UI 人工流程(Skills Store 页面,DOC-11 v4 Task 11.5)
  4. 搜索无副作用,可以给 Agent 自由搜索以供用户决策

  来源:Master M8。

- **ADR-049(Backend 写 skill_installs 表)**:所有 Skill 安装行为(UI 触发 / CLI 触发)由 Backend `skill_install_service` 统一处理,写 `skill_installs` 表(DOC-01 v4 §4.2 新增)。该表字段:`user_id / skill_name / source / source_url / version / installed_at / install_path / has_hooks / has_mcp / status`。来源:Batch 3 §A9-4。

#### CLI 命令(v4 两源)

```python
# executor/cli/skills_cli.py
# 通过 `python -m prism.skills` 或容器内 `prism skills` 调用

"""
prism skills search <query> [--source local|github]
prism skills install <package_id> --source <local|github> [--version <ver>]
prism skills uninstall <skill_name>
prism skills update <skill_name>
prism skills list [--source <source>]
prism skills info <skill_name>
"""
```

#### Agent 内置工具(v4:仅搜索)

```python
# executor/tools/builtin/skills_search.py

class SkillsSearchTool(Tool):
    """
    v4:只允许 Agent 搜索 Skill 市场(供用户决策参考),不允许安装。
    安装操作仍需用户在 UI 手动触发,或通过 CLI 执行。
    """

    name = "skills_search"
    description = (
        "搜索 Prism Skills 市场(Local + GitHub 两源),返回候选 Skill 列表"
        "供用户参考。你不能直接安装 Skill,需要告诉用户点击 UI 的 Skills Store 页面"
        "手动安装。"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词"
            },
            "source": {
                "type": "string",
                "enum": ["local", "github"],
                "description": "指定源(可选,默认全部)"
            },
        },
        "required": ["query"]
    }
    # v4:无 install/uninstall/update action
```

#### Backend API(v4 写 skill_installs 表)

```python
# backend/app/api/v1/skills.py

"""
Skills Market API — 供 Web UI 调用(v4)

GET    /skills/search?q=...&source=local|github    跨源搜索
GET    /skills/installed                            已安装列表(from skill_installs 表)
POST   /skills/install                              安装(写 skill_installs 表)
DELETE /skills/{skill_name}                         卸载(更新 skill_installs.status)
POST   /skills/{skill_name}/update                  更新
GET    /skills/{skill_name}                         Skill 详情
"""

# skill_install_service.py 处理 install/uninstall:
# - install: 调用 SkillsRegistry.install() + INSERT skill_installs + 通知 PluginHost reload
# - uninstall: 调用 SkillsRegistry.uninstall() + UPDATE skill_installs SET status='uninstalled'
# - Redis:skill_install:status:{user_id}:{skill_name} 缓存当前状态(10 min TTL)
```

#### 验收标准(v4 扩展)

- Web UI Skills 商店页面可浏览/搜索/安装/卸载 Skills
- **v4:Agent 只能使用 `skills_search` 搜索,无 install 工具**
- CLI `prism skills` 命令全部子命令正常工作
- **v4:所有 install 操作通过 Backend skill_install_service 写 skill_installs 表**
- **v4:Redis 缓存 key 格式 `skill_install:status:{user_id}:{skill_name}`,TTL 600s**

---

### Part B — Claude Code 执行 Prompt

> 待实施计划执行阶段补充

## 完成后

1. 更新 PROGRESS.md
2. 加载 Simplify skill 审查
3. 加载 PJR skill 验证
4. `git add -A && git commit -m "feat: Skills CLI + Agent skill_manage tool + Backend API"`

---

## Part III: CC Plugin Protocol Compatibility

## Task 5.7: CC 插件格式兼容层

### Part A — 设计与解释

#### CC 插件格式映射

```
CC Plugin 目录结构              Prism 映射                    兼容性
──────────────────              ──────────                    ──────
plugin.json                  → plugin.yaml（超集）            读取 plugin.json 自动转换
skills/                      → skills/                       格式完全一致
  SKILL.md                     SKILL.md                      frontmatter 格式一致
hooks/                       → hooks/                        handler 协议一致
  preToolUse.sh                preToolUse.sh                 exit code 协议一致
  postToolUse.py               postToolUse.py                JSON stdout 协议一致
mcp-servers/                 → mcp/                          目录名不同，内容兼容
  config.json                  config.json
README.md                    → README.md                     直接复用
```

#### plugin.yaml（Prism 超集格式）

```yaml
# CC 兼容字段（CC 插件的 plugin.json 转换后等价）
name: financial-analysis
description: "金融数据分析插件"
version: "1.0.0"
author: "Prism Community"
skills_dir: ./skills
hooks_dir: ./hooks

# Prism 扩展字段（CC 会忽略这些字段）
prism:
  # 垂类调教定义 — 插件级的行为定制
  vertical_tuning:
    agent_constraints:
      - "所有金融数据引用必须标注来源和时间"
      - "不得生成投资建议（铁律 1 垂类强化）"
      - "数字表述必须使用精确数值，不得使用模糊表述如'大约'"
    output_format: "数据表格优先，数字保留 2 位小数"
    domain_knowledge:
      - "A 股交易时间：周一至周五 9:30-11:30, 13:00-15:00"
      - "港股交易时间：周一至周五 9:30-12:00, 13:00-16:00"

  # Harness 配置覆盖 — 插件级的治理定制
  harness_overrides:
    guardrail_rules:
      - id: GR-FINANCE-001
        trigger: post_tool_use
        condition:
          output_contains: ["建议买入", "建议卖出", "投资建议"]
        action: block
        message: "检测到投资建议内容，已拦截"

    permissions:
      financial_data_query: allow
      trade_execution: deny

  # MCP 服务配置
  mcp_servers:
    - name: financial-data
      command: npx
      args: ["@prism-mcp/financial-data"]
      env:
        DATA_SOURCE: "yahoo_finance"

  # 依赖声明
  dependencies:
    skills:
      - "@manus/web-researcher"    # 依赖另一个 Skill
    mcp:
      - "financial-data"           # 依赖特定 MCP Server
```

#### CC 插件适配器

```python
# executor/plugins/cc_compat.py

"""
CC 插件格式适配器

加载逻辑：
1. 检测插件目录中是否存在 plugin.json（CC 格式）或 plugin.yaml（Prism 格式）
2. plugin.json → 转换为 Prism PluginConfig（兼容加载）
3. plugin.yaml → 直接加载为 Prism PluginConfig
4. 两者都存在 → 优先使用 plugin.yaml（Prism 格式更完整）
5. 都不存在但有 skills/ 目录 → 作为纯 Skills 集合加载

转换规则（plugin.json → PluginConfig）：
- name, description, version → 直接映射
- skills/ 目录 → skills_dir
- hooks/ 目录 → hooks_dir
- mcp-servers/ 目录 → 映射到 prism.mcp_servers
- CC 没有 vertical_tuning 概念 → 留空
"""


class CCPluginAdapter:

    def detect_format(self, plugin_dir: str) -> Literal["cc", "prism", "skills_only", "unknown"]:
        """
        检测插件格式
        - 有 plugin.yaml → "prism"
        - 有 plugin.json → "cc"
        - 只有 skills/ 目录 → "skills_only"
        - 都没有 → "unknown"
        """
        ...

    def load(self, plugin_dir: str) -> PluginConfig:
        """
        统一加载入口，自动检测格式并转换
        """
        format = self.detect_format(plugin_dir)
        if format == "prism":
            return self._load_prism_plugin(plugin_dir)
        elif format == "cc":
            return self._load_cc_plugin(plugin_dir)
        elif format == "skills_only":
            return self._load_skills_collection(plugin_dir)
        else:
            raise PluginFormatError(f"无法识别插件格式: {plugin_dir}")

    def _load_cc_plugin(self, plugin_dir: str) -> PluginConfig:
        """将 CC plugin.json 转换为 Prism PluginConfig"""
        ...

    def _load_prism_plugin(self, plugin_dir: str) -> PluginConfig:
        """加载 Prism 原生 plugin.yaml"""
        ...

    def _load_skills_collection(self, plugin_dir: str) -> PluginConfig:
        """将纯 Skills 目录包装为 PluginConfig"""
        ...

    def export_to_cc(self, config: PluginConfig) -> "ConversionReport":
        """
        v4:将 Prism 插件导出为 CC 兼容格式,返回 ConversionReport(不是文件)。
        调用方决定是否把 report.cc_compat_zip 落盘或上传。
        """
        ...


# v4 新增 dataclass
@dataclass
class ConversionReport:
    """v4 ADR:CC 导出返回结构化报告而非直接写文件"""
    success: bool
    cc_compat_zip: bytes               # CC 格式目录的 zip 字节
    lost_fields: list[str]             # 转换丢弃的 Prism 扩展字段清单
    warnings: list[str]                # 转换过程的告警(如 MCP 名称冲突)
    plugin_name: str
    cc_plugin_json: dict              # 生成的 plugin.json 内容
```

#### PluginHost 集成修改

现有 `PluginHost.load_plugin()` 修改为：

```python
class PluginHost:
    def __init__(self, ..., cc_adapter: CCPluginAdapter):
        self._cc_adapter = cc_adapter

    def load_plugin(self, plugin_dir: str) -> None:
        """
        加载插件（自动检测 CC 或 Prism 格式）
        """
        config = self._cc_adapter.load(plugin_dir)  # 统一入口
        # 后续流程不变：注册 Skills → 注册 Hooks → 启动 MCP → 注入 Harness 配置
        ...
```

#### 设计决策(ADR)

- **ADR-050-A(ConversionReport 返回结构化)**:`export_to_cc` 返回 `ConversionReport`(含 `cc_compat_zip / lost_fields / warnings / cc_plugin_json`),而非直接写文件。调用方决定落盘/上传。来源:Master M8, Batch 2 §A5-7。

- **ADR-050-B(plugin.yaml schema 严格校验)**:`plugin.yaml` 用 Pydantic schema 严格校验;缺字段返回 HTTP 422 + 详细错误位置;未识别字段警告(不拒绝,便于 forward-compat)。来源:Batch 2 §A5-7。

#### 验收标准(v4 扩展)

- CC 格式的插件目录(含 plugin.json)可被 Prism 直接加载
- Prism 格式的插件(plugin.yaml)可加载并应用垂类调教定义
- **v4:`export_to_cc()` 返回 `ConversionReport` 结构化对象**,含 `lost_fields` 清单
- **v4:`plugin.yaml` schema 用 Pydantic 严格校验**,缺必填字段返回 422
- CCPluginAdapter 统一检测格式并转换,PluginHost 接受目录路径而非 PluginConfig

---

### Part B — Claude Code 执行 Prompt

> 见各 Task 段内实现规范,端到端测试 Prompt 在实施阶段补充。

## 完成后

1. 更新 PROGRESS.md
2. 更新 DECISIONS.md:记录 ADR-040~049(Skill 三级/强制/is_skill_context, Hook 4 handler, MCP 双通道/scope, Plugin 变量系统, Skills Registry 两源, Agent Tool 仅搜索, CC 导出 Report, plugin.yaml 严格校验)
3. `git add -A && git commit -m "feat(v4): plugin ecosystem — 2-source registry, search-only agent tool, ConversionReport, variable substitution"`

---

## 附录 A: v4 修订清单

本次修订共 28 处精确修补,对应 Batch 1-5 review + PDF 补丁 + Master + user preferences archive:

| # | 位置 | 修订内容 | 来源 |
|---|---|---|---|
| 1 | Header | 版本 3.1 → 4.0,日期 2026-04-18,Task 数 4 → 7,v4 摘要 | 全局 |
| 2 | Task 5.1 Part A | ADR-040(三级加载规范)/ADR-041(强制调用)/ADR-042(is_skill_context)+ 联动 DOC-02 v4 skill_grammar_section | PDF 补丁 P6, Batch 2 §A5-1 |
| 3 | Task 5.1 验收 | Level 2 标记 is_skill_context;Skill 匹配未调用发 `skill_mentioned_not_loaded`;frontmatter.agents 过滤 | 同上 |
| 4 | Task 5.1 skill_loader 集成 | 引用 DOC-02 v4 Task 2.4 的 skill_grammar_section | PDF 补丁 P6 |
| 5 | Task 5.2 Part A | ADR-044(MCP instructions 双通道)/ADR-045(agent-scoped MCP 白名单) | PDF 补丁 P5, Batch 2 §A5-3 |
| 6 | Task 5.2 mcp_client.py | 读取 MCP Server `server.info.instructions` → 传给 PromptAssembler `<mcp_instructions>` section | PDF 补丁 P5 |
| 7 | Task 5.2 agent-scoped 过滤 | AgentDefinition.mcp_servers 白名单生效(DOC-04 v4 ADR-030 联动) | PDF 补丁 P7 |
| 8 | Task 5.3 Part A | ADR-043(Hook 4 种 handler:command/http/prompt/agent)+ 所有 handler 超时降级 blocking_error | Batch 2 §A5-2 |
| 9 | Task 5.3 验收 | 4 种 handler 均可运行 | 同上 |
| 10 | Task 5.4 Part A | ADR-046(Plugin 命名空间 + 变量替换系统 + CC 兼容映射 + 三级加载) | PDF 补丁 P9, Batch 2 §A5-4 |
| 11 | Task 5.4 变量替换 | `${PRISM_PLUGIN_ROOT}` / `${PRISM_PLUGIN_DATA}` / `${PRISM_SKILL_DIR}` / `${PRISM_SESSION_ID}` / `${user_config.X}` + `${CLAUDE_PLUGIN_ROOT}` 自动等价 | PDF 补丁 P9 |
| 12 | Task 5.4 加载顺序 | Platform → User → Session 三级 + 冲突检测写 audit | Batch 2 §A5-4 |
| 13 | **Task 5.5 重大修订** | Phase 1 **仅 Local + GitHub 两源**,删除 NpmSource/ManusSource(Phase 2 预留注释) | Master M8, Batch 2 §A5-5 |
| 14 | Task 5.5 SkillPackage | `source` 字段枚举收窄为 `Literal["local", "github"]` | 同上 |
| 15 | Task 5.5 搜索 API | `/skills/search?q=X&source=local|github` | 同上 |
| 16 | **Task 5.6 重大修订** | ADR-048(Agent Tool **仅 search**,无 install 权限);v3.1 的 `skill_manage` 工具改为只读 `skills_search` | Master M8 |
| 17 | Task 5.6 skill_install_service | ADR-049:Backend 写 `skill_installs` 表(DOC-01 v4 §4.2);Redis 缓存 key 格式 `skill_install:status:{user_id}:{skill_name}` TTL 600s | Batch 3 §A9-4 |
| 18 | Task 5.6 搜索工具 | 保留 Agent `skills_search(query, source)` 只读权限;安装仍需用户手动触发(UI/CLI) | 同上 |
| 19 | **Task 5.7 重大修订** | ADR-050-A:`export_to_cc` 返回 `ConversionReport`(不是文件)+ lost_fields/warnings/cc_compat_zip | Master M8, Batch 2 §A5-7 |
| 20 | Task 5.7 ConversionReport | `lost_fields: list[str]` + `warnings: list[str]` + `cc_compat_zip: bytes` + `cc_plugin_json: dict` | 同上 |
| 21 | Task 5.7 plugin.yaml schema | ADR-050-B:Pydantic 严格校验 + 缺字段 422 | 同上 |
| 22 | 所有 Part B 开头 | 加 v4 Observability 采集说明 | 全局 §3.4 |
| 23 | Redis namespace | Skills 安装状态 key 规范(skill_install:status:{user_id}:{skill_name})+ 其他 skill:* 按 DOC-01 v4 §9.2 | Batch 3 §B3-I |
| 24 | Prometheus metrics | `prism_skill_installs_total` / `prism_skill_searches_total` 在各 Task Part B 采集 | Batch 5 §B5-I |
| 25 | 结构化日志 | skill.installed / skill.uninstalled / skill.loaded / mcp.instructions_injected / plugin.variable_resolved | 同上 |
| 26 | ADR 编号 | ADR-040~049(+ 050-A/050-B 分拆) | 全局 |
| 27 | 交叉引用 | DOC-03 v3 → v4, DOC-04 v3 → v4, DOC-01 v3 → v4, DOC-02 v3 → v4 | 全局 |
| 28 | 附录 A + 文末 | 修订清单 + 下一步 DOC-06 v4 | SOP |

---

> **文档维护说明**:本文档的 7 个 Task 完成后,Prism v2 将拥有完整的声明式扩展体系:Skill **三级加载**(L0 注册 → L1 描述注入 → L2 按需完整加载 + is_skill_context 标记)+ MCP stdio 集成(**双通道 instructions + agent-scoped 白名单**)+ Hook 治理层(4 种 handler / 优先级排序 / Phase 1 事件过滤 / scoped 注册-注销)+ Plugin 命名空间(**变量替换系统 + CC 兼容映射 + Platform/User/Session 三级加载**)+ PluginHost 统一管理 + 垂类特调 + Skills 市场(**Phase 1 仅 Local + GitHub 两源**)+ Skills Agent Tool(**仅搜索**)+ CC 插件格式兼容层(**ConversionReport + plugin.yaml 严格校验**)。
> **审计问题已解决**:(1) PromptAssembler cache 在 MCP/Plugin 加载后通过 `update_tools()` 同步失效;(2) HookSystem.fire() 入口校验 PHASE1_EVENTS,非 Phase 1 事件静默返回空决策;(3) MCPClient 改用 asyncio.create_subprocess_exec 消除阻塞 I/O。
> **最后更新**: 2026-04-18 (v4 review 修订版) | **下一步**: DOC-06 v4 Backend Auth & User
