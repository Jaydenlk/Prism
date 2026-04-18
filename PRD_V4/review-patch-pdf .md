# PDF 对照补丁 — Batch 1 & 2 校准

> **触发**: 用户上传 Xiao Tan 的 CC 源码深度研究 PDF(26 页增强完整版)
> **目的**: 基于 PDF 新披露的 CC 细节,对 Batch 1 / Batch 2 做增量校准
> **形式**: 补丁,不是重写。只标"新增"、"校准"、"撤回"三类

---

## P1. 关于 Prompt Assembly 的细化

### Batch 1 §Q2 已提: tiktoken 精确化
### 新增: PDF §3.1 揭示 CC 的 Prompt Section 粒度

CC 的 `src/constants/prompts.ts` 包含 **10+ 个独立的 section getter 函数**,分别是:

**静态前缀**(适合缓存):
- `getSimpleIntroSection()` — 身份与基础定位(交互 agent、软件工程、Output Style 约束、CYBER_RISK_INSTRUCTION 注入、禁止猜 URL)
- `getSimpleSystemSection()` — runtime reality(所有非工具输出直接给用户、permission mode、拒绝后不能原样重试、<system-reminder> 标签、prompt injection 警惕、hooks 存在、上下文自动压缩)
- `getSimpleDoingTasksSection()` — 任务哲学(不要加没要求的功能、不过度抽象、不瞎重构、不乱加 comments/docstrings/type annotations、不做不必要 error handling、不做 future-proof 抽象、先读代码再改、不轻易创建新文件、不给时间估计、方法失败先诊断、注意安全漏洞、删除确认没用的东西、结果如实汇报)
- `getActionsSection()` — 风险动作规范(destructive / hard-to-reverse / 修改共享状态 / 对外可见动作 / 上传第三方;不要用 destructive actions 当捷径、陌生状态先调查、merge conflict/lock file 不粗暴删)
- `getUsingYourToolsSection()` — 工具使用规范(FileRead > cat;FileEdit > sed/awk;FileWrite > echo;Glob/Grep;Bash 只在真需要 shell 时;TodoWrite/TaskCreate;**无依赖的工具调用要并行**)
- `getSimpleToneAndStyleSection()` — 交互感受(不乱用 emoji、简洁、file_path:line_number、owner/repo#123、tool call 前不加冒号)
- `getOutputEfficiencySection()` — 输出效率(先说结论或行动、不要铺垫、该更新时更新但不废话、不过度解释、不塞无谓表格、短句直给)

**动态后缀**(按条件注入):
- `getSessionSpecificGuidanceSection()` — 运行时可变的局部指令(根据当前 tools 和 feature gates 拼出约束)
- `getMcpInstructionsSection()` — MCP Server 提供的 instructions
- `getMemorySection()` — memory 内容
- `getAntModelOverride()` — 模型特定覆盖
- `getEnvInfoSection()` — 环境信息
- `getLanguageSection()` — 语言偏好
- `getOutputStyleSection()` — 输出风格
- `getScratchpadSection()` — scratchpad 说明
- `getFunctionResultClearingSection()` — 函数结果清理提示
- `getSummarizeToolResultsSection()` — 工具结果摘要提示
- `getNumericLengthAnchorsSection()` — 数字长度锚点
- `getTokenBudgetSection()` — token 预算
- `getBriefSection()` — 简洁模式

### 校准动作

**Batch 1 §Q2 补充**: ContextBudgetManager 用 tiktoken 是对的,但同时要求 PromptAssembler 的 `prompt_sections.py` **完整对标 CC 的 10+ section 粒度**,不是当前 DOC-02 里的 7 + 4 section 简化版。

**改写阶段落地**: DOC-02 Task 2.4 的 `prompt_sections.py` 必须至少定义上面列出的所有 section 的 Prism 对应函数,每个函数独立可测。这是 CC 架构 fidelity 的底线。

---

## P2. 关于 Fork 机制的校准

### Batch 2 §A4-2 已提: fork cache 字节级一致只在同 agent_type 时成立,建议把 session_guidance 移到动态部分

### 新增: PDF §6.3/6.4 揭示 CC 的 fork path 更激进的设计

CC 的 fork path 不只是"共享 cache",而是**多层保护措施**确保 cache 命中:
- `useExactTools = true` — 工具集与父线程完全一致
- 继承父线程的 system prompt(不重新生成)
- `buildForkedMessages()` 构造 prompt messages(不是从空白开始)
- Prompt 里明确告诉模型: **"不要给 fork 单独设 model,否则 cache 命中会变差"**
- Prompt 里明确告诉模型: **"不要偷窥 fork 输出文件"** — 这是 prompt-level 的行为约束,不是代码级别的限制
- Prompt 里明确告诉模型: **"不要预言 fork 结果"** — 强制等待 fork 真正完成

### 校准动作

**Batch 2 §A4-2 补充**: 我之前建议的"把 session_guidance 移到动态部分"方向是对的,但还漏了两个细节:
1. **Fork 时必须保持父 Agent 的 model 设置**,不允许子 Agent 覆盖 model(这是 cache 命中要求)
2. **Fork 相关的 prompt-level 行为约束必须写进 Agent 的 prompt**: "不要偷窥 fork 的输出文件"、"不要预言 fork 结果"

**改写阶段落地**: DOC-04 Task 4.2 的 Part A 设计必须明文包含这两条 prompt-level 约束,Part B 的 Prompt 必须在 ForkManager 实现里体现(构造 fork prompt 时自动附加这些约束段)。

---

## P3. 关于 Verification Agent 的完整形态

### Batch 2 §A4-1 已提: 用 capability-based 白名单替代硬编码 allowed_tools 列表

### 新增: PDF §5.7 揭示 Verification Agent 的 "try to break it" 反制逻辑

这个 Agent 在 CC 里做得**极其刚硬**,不是"再跑一次测试"那么简单。PDF 原话:

> "verification avoidance: 只看代码、不跑检查、写 PASS 就走"
> "被前 80% 迷惑: UI 看起来还行、测试也过了,就忽略最后 20% 的问题"

Prompt 的反制:
- **必须跑 build**
- **必须跑 test suite**
- **必须跑 linter / type-check**
- **根据变更类型做专项验证**:
  - frontend → 跑浏览器自动化 / 页面子资源验证
  - backend → curl/fetch 实测响应
  - CLI → 看 stdout/stderr/exit code
  - migration → 测 up/down 和已有数据
  - refactor → 测 public API surface
- **必须做 adversarial probes** — 主动找边界 case、找漏洞
- **每个 check 必须带 command 和 output observed** — 不接受"我觉得应该没问题"
- **必须输出 VERDICT: PASS / FAIL / PARTIAL** — 强制三态结论格式

### 校准动作

**Batch 2 §C 针对 DOC-04 的补充**(Verification Agent 设计章节缺失):

DOC-04 Task 4.1 当前对 Verifier 的描述只有一句"对抗性验证者,目标是 try to break it"。这远远不够。**改写阶段必须扩展为完整的 VerificationAgent 定义**:

```python
VERIFICATION = AgentDefinition(
    name="verifier",
    display_name="验证者",
    system_prompt_override="""你是 Prism 的验证者 Agent。你的工作是 try to break it。

你要警惕两种失败模式:
1. verification avoidance — 只看代码、不跑检查、写 PASS 就走
2. 被前 80% 迷惑 — 实现看起来没问题、测试也过了,就忽略最后 20% 的边界问题

你必须:
- 跑 build / test suite / linter / type-check
- 根据变更类型做专项验证(frontend/backend/CLI/migration/refactor)
- 做 adversarial probes(主动找边界 case、找漏洞)
- 每个 check 必须带 command 和 output observed
- 最后必须输出 VERDICT: PASS / FAIL / PARTIAL

不要说"应该没问题",要说"我跑了 X 命令,看到 Y 输出,所以 Z 结论"。
""",
    allowed_capabilities={"readonly", "writable", "destructive", "network"},  # 验证需要所有能力
    behavior_constraints=[
        "你是对抗性验证者,不是友好验收者",
        "所有结论必须有 command + output 支撑",
        "最终必须输出 VERDICT: PASS | FAIL | PARTIAL",
    ],
    output_format="verdict_structured",
    max_turns=30,
)
```

---

## P4. 关于 Hook Decision 的完整接口

### Batch 2 §A3-6 已提: HookDecision 合并规则明文化

### 新增: PDF §8.3 揭示 HookDecision 的完整字段

PDF 原话(§8.3):

> "在 `runPreToolUseHooks()` 中,hook 可以产出:
> - 普通 message
> - hookPermissionResult
> - hookUpdatedInput
> - preventContinuation
> - stopReason
> - additionalContext
> - stop"

以及(§7.3):

> "Hook 结果不仅仅能记日志,还能:
> - 返回 message
> - blockingError
> - updatedInput
> - permissionBehavior
> - preventContinuation
> - stopReason
> - additionalContexts
> - updatedMCPToolOutput"

### 校准动作

**Batch 2 §A3-6 扩充**: 我之前给的 `HookDecision` dataclass 字段不全,要扩展:

```python
@dataclass
class HookDecision:
    """Hook handler 返回的决策(对标 CC 的 hook result 完整字段)"""
    # 权限决策
    permission_decision: Literal["allow", "deny", "ask"] | None = None
    
    # 输入改写(Pre 阶段)
    updated_input: dict | None = None
    
    # 输出改写(Post 阶段,专门针对 MCP tool)
    updated_mcp_tool_output: str | None = None
    
    # 流程控制
    prevent_continuation: bool = False   # 不 deny 也能阻止 Agent 继续
    stop: bool = False                   # 完全停止 Run(比 prevent_continuation 更强)
    stop_reason: str = ""                # stop 时的理由
    
    # 上下文注入
    additional_context: str = ""         # 追加到 Agent 上下文的信息
    
    # 展示给用户
    message: str = ""                    # 给用户看的 hook 反馈
    blocking_error: str = ""             # 阻断性错误信息
    
    # 元信息
    reason: str = ""                     # 决策理由(写 audit_logs)
    handler_name: str = ""               # 哪个 handler 产生的决策
```

Merge 规则也要相应扩展:
- `stop=True` 严格度最高,任一 handler 返回即生效
- `prevent_continuation=True` 次之
- `permission_decision` deny > ask > allow
- `updated_mcp_tool_output` 多个冲突时 abort(同 updated_input 规则)
- `additional_context` / `message` / `blocking_error` 按 handler 顺序拼接

---

## P5. 关于 MCP Instructions 注入机制

### Batch 1 没专门提,Batch 2 Task 5.2 也只提了注册时 cache 失效

### 新增: PDF §7.5 揭示 MCP 的双通道价值

PDF 原话:

> "MCP 能同时注入:
> 1. 新工具
> 2. 如何使用这些工具的说明"

关键: `getMcpInstructionsSection(mcpClients)` 会遍历所有已连接的 MCP Server,**把每个 Server 提供的 `instructions` 字段拼接到 system prompt 的动态 section**。这让模型不只看到"有什么工具",还看到"怎么用这些工具"。

### 校准动作

**改写阶段落地**: DOC-05 Task 5.2 的 PromptAssembler 集成必须显式包含:

```python
# executor/engine/prompt_sections.py

def mcp_instructions_section(mcp_servers: list[MCPServerInfo]) -> str:
    """
    MCP Server 提供的使用说明注入(对标 CC 的 getMcpInstructionsSection)
    
    每个 MCP Server 的 instructions 字段(如果提供)会被拼接到动态 section,
    让模型不只看到工具列表,还看到如何使用这些工具。
    """
    if not mcp_servers:
        return ""
    
    sections = []
    for server in mcp_servers:
        if server.instructions:
            sections.append(
                f"### {server.name}\n{server.instructions}"
            )
    
    if not sections:
        return ""
    
    return "## MCP 工具使用说明\n\n" + "\n\n".join(sections)
```

并且: `MCPServerInfo` 必须有 `instructions: str | None` 字段,从 MCP Server 的 stdio 协议响应中提取(MCP 协议里有 ServerCapabilities.instructions 概念)。

---

## P6. 关于"Skill 必须执行"的强制语义

### Batch 2 没提

### 新增: PDF §7.1 揭示 CC 的 SkillTool prompt 强制要求

PDF 原话:

> "task 匹配 skill 时必须调用 Skill tool"
> "不能只提 skill 不执行"
> "slash command 可以视为 skill 入口"
> "如果 skill 已经通过 tag 注入,则不要重复调用"

这是一条**behavioral contract**: 模型看到匹配的 Skill 时,必须通过 `Skill` 工具调用来"加载并执行"这个 Skill,不能只在回答里提一句"有个 Skill 可以做这件事"就跳过。

### 校准动作

**改写阶段落地**: DOC-05 Task 5.1 的 `skill_grammar_section()` 必须强化这段约束:

```python
def skill_grammar_section(available_skills: list[SkillInfo]) -> str:
    """Skill 使用规范(对标 CC 的 SkillTool prompt)"""
    if not available_skills:
        return ""
    
    return """## Skill 使用规则

你有以下 Skill 可用:

{skill_list}

**强制规则**:
1. 当任务匹配某个 Skill 的 description 或 triggers 时,你必须通过 `skill_invoke` 工具调用该 Skill,不能只在回答里提一下就跳过
2. Skill 内容已经通过 tag 注入到你的上下文中时(会有 `<skill_context name="X">` 标签),不要再调用 `skill_invoke`,直接使用注入的内容
3. 如果不确定是否应该调用某个 Skill,优先调用,不要"节省"—— Skill 调用很便宜
""".format(skill_list=_format_skill_list(available_skills))
```

---

## P7. 关于 Fork / Sub-agent Prompt 的 briefing 要求

### Batch 2 §A4-1 轻微提到

### 新增: PDF §5.3 揭示 "How to write the prompt" 的完整 briefing 协议

PDF 原话:

> "fresh agent 没有上下文,要像对新同事 briefing 一样写 prompt"
> "说明目标和原因"
> "说明你已经排除了什么"
> "提供足够背景,让它能做判断"
> "如果要短答,明确说"
> "不要把理解任务的工作外包给 agent"
> "不要写'基于你的发现再去修 bug'这种偷懒 prompt"
> "应该给到 file path、line、具体改动要求"

### 校准动作

**改写阶段落地**: DOC-04 Task 4.2 的 `ForkManager.fork()` 接口签名必须强制要求 briefing 结构化:

```python
@dataclass
class ForkBriefing:
    """Fork 子 Agent 的 briefing 结构(对标 CC 的 sub-agent prompt 协议)"""
    goal: str                      # 明确的目标
    why: str                       # 为什么做这个(背景和原因)
    excluded: list[str]            # 已经排除的方向(避免子 Agent 重复探索)
    background_context: str        # 必要的背景信息
    expected_output: str           # 期望的输出形态(短答/详细报告/结构化 JSON)
    file_references: list[tuple[str, int]] = field(default_factory=list)
    # ^ [(file_path, line_number), ...] 具体的代码位置引用

class ForkManager:
    async def fork(
        self,
        agent_type: str,
        briefing: ForkBriefing,     # 必须提供结构化 briefing,不允许传裸字符串
        parent_context,
        **kwargs,
    ) -> ForkResult:
        ...
```

主 Agent 看到的 `fork_agent` 工具 Schema 必须要求这些字段,这样系统级防止"懒 delegation"。

---

## P8. 关于 Background Agent 的异步语义

### Batch 1/2 都没提

### 新增: PDF §6.5 揭示 CC 的 Background Path 完整机制

PDF §6.5.1 原话:

> "background path 特点:
> - 注册 async agent task
> - 独立 abort controller
> - 可以在后台运行
> - 完成后通过 notification 回到主线程
> - 可选自动 summarization
> - 可查看 outputFile 但 prompt 里明确不鼓励偷看"

这是**另一个维度的子 Agent 模式**,和 Fork 的区别是:
- Fork = 同步,主 Agent 等子 Agent 完成
- Background = 异步,主 Agent 继续干别的,子 Agent 完成后发 notification

### 校准动作

**改写阶段落地**: DOC-04 当前完全没提 Background Agent。Task 4.5 的 PluginBuilder 是一个很合适的 Background Agent 场景(多轮对话耗时长),但应该**在 Task 4.3 Coordinator-Workers 之后增加一个新的子章节**讨论 Background Agent 模式(不一定是完整 Task,可以是 §4.6 设计章节,留 Phase 2 实现接口)。

数据模型层面: `runs` 表 + 新增 `run_mode` 字段:
```sql
run_mode VARCHAR(20) NOT NULL DEFAULT 'foreground'  -- 'foreground' | 'background' | 'fork'
parent_run_id UUID NULL  -- fork 和 background 都有 parent
```

这是为 Phase 2 扩展预留,不是 Phase 1 强制实现。

---

## P9. 关于 Runtime 变量替换

### Batch 2 §A5-3 提了命名空间,没提变量替换

### 新增: PDF §7.2 揭示 Plugin 的 runtime 变量系统

PDF 原话:

> "runtime 变量替换
> 例如支持:
> - ${CLAUDE_PLUGIN_ROOT}
> - ${CLAUDE_PLUGIN_DATA}
> - ${CLAUDE_SKILL_DIR}
> - ${CLAUDE_SESSION_ID}
> - ${user_config.X}"

Plugin 的 commands / SKILL.md / hooks 脚本里可以用这些变量,加载时替换成实际路径或值。这让 Plugin 具备**环境感知能力**,不必硬编码路径。

### 校准动作

**改写阶段落地**: DOC-05 Task 5.7 CC 兼容层必须支持变量替换。Prism 的对应命名:

```python
# executor/plugins/variable_resolver.py

class PluginVariableResolver:
    """
    Plugin 文件(plugin.yaml、SKILL.md、hook 脚本等)里的 runtime 变量替换
    对标 CC 的 ${CLAUDE_*} 变量系统
    """
    
    PRISM_VARS = {
        "${PRISM_PLUGIN_ROOT}",     # plugin 安装目录
        "${PRISM_PLUGIN_DATA}",     # plugin 专属数据目录(可读写)
        "${PRISM_SKILL_DIR}",       # 当前 skill 目录
        "${PRISM_SESSION_ID}",      # 当前 session ID
        "${PRISM_RUN_ID}",          # 当前 run ID
        "${PRISM_USER_ID}",         # 当前 user ID
    }
    
    CC_COMPAT_VARS = {
        "${CLAUDE_PLUGIN_ROOT}": "${PRISM_PLUGIN_ROOT}",
        "${CLAUDE_PLUGIN_DATA}": "${PRISM_PLUGIN_DATA}",
        "${CLAUDE_SKILL_DIR}": "${PRISM_SKILL_DIR}",
        "${CLAUDE_SESSION_ID}": "${PRISM_SESSION_ID}",
    }
    
    def resolve(self, text: str, context: dict) -> str:
        """替换文本中的变量为实际值"""
        # 先把 CC 兼容变量映射到 Prism 变量
        for cc_var, prism_var in self.CC_COMPAT_VARS.items():
            text = text.replace(cc_var, prism_var)
        # 再替换 Prism 变量
        for var in self.PRISM_VARS:
            value = self._get_value(var, context)
            text = text.replace(var, value)
        # user_config.X 的替换
        text = self._resolve_user_config(text, context)
        return text
```

---

## P10. 关于 agent-specific MCP servers

### Batch 2 没明确区分

### 新增: PDF §6.7 揭示 agent 可以有专属 MCP

PDF 原话:

> "initializeAgentMcpServers() 很有意思。
> 它支持 agentDefinition 自带 mcpServers,并且可以:
> - 从现有配置按名字引用服务器
> - 在 frontmatter 里内联定义 agent-specific MCP server
> - 连接 server
> - 拉取 tools
> - 把 agent-specific MCP tools 合并进当前 agent 的 tools
> - 在 agent 结束时做 cleanup"

关键点: Agent 不只消费全局 MCP,**它可以带自己的外接能力**。比如一个 financial-analyst Agent 可以自带 financial-data MCP server,这个 MCP 只在该 Agent 运行时启动,结束时清理,不污染全局 MCP 列表。

### 校准动作

**改写阶段落地**: DOC-04 Task 4.1 的 `AgentDefinition` 必须新增 `mcp_servers` 字段:

```python
@dataclass
class AgentMCPServer:
    """Agent 专属 MCP Server 定义"""
    name: str                      # MCP Server 名称(agent 内唯一)
    command: str                   # 启动命令
    args: list[str]
    env: dict[str, str] = field(default_factory=dict)
    source: Literal["reference", "inline"] = "reference"
    # reference: 从全局 mcp_servers 表按名字引用
    # inline: 在 agent 定义里内联(用于 plugin 自带的专属 MCP)

@dataclass
class AgentDefinition:
    name: str
    display_name: str
    system_prompt_override: str | None = None
    allowed_capabilities: set[str] = field(default_factory=set)
    denied_capabilities: set[str] = field(default_factory=set)
    behavior_constraints: list[str] = field(default_factory=list)
    
    # 新增
    mcp_servers: list[AgentMCPServer] = field(default_factory=list)
    # Agent 启动时单独 spawn 这些 MCP,Agent 结束时 cleanup
    
    skills: list[str] = field(default_factory=list)
    # Agent 启动时预加载这些 skill 到初始 messages(对标 CC 的 frontmatter skills)
    
    output_format: str = "conversational"
    max_turns: int = 30
```

`runAgent()`(对应 Prism 的子进程 `__main__.py`)需要实现 `initializeAgentMcpServers()` 的 Prism 对应逻辑。

---

## 总结 & 对 Batch 3-5 的影响

### Batch 1 v2 的调整:
- §Q2 扩展为"tiktoken 精确化 + Prompt Section 粒度对齐 CC 10+ getter" (P1)
- 新增 §Q6 MCP instructions 注入机制(P5)

### Batch 2 的调整:
- §A3-6 HookDecision 字段补全 (P4)
- §A4-1 Verifier Agent 完整形态 (P3)
- §A4-2 Fork 约束补充 model 不覆盖 + prompt-level 行为约束 (P2)
- §C4 Skill 必须执行的强制语义 (P6)
- §Part A 新增 ForkBriefing 结构化要求 (P7)
- §Part B 新增 Background Agent 模式讨论 (P8)
- §A5-3 命名空间 + 新增变量替换系统 (P9)
- §A4-1 AgentDefinition 扩展 agent-specific MCP + frontmatter skills (P10)

### Batch 3-5 需要带着这些新认识去审:
- **Batch 3**: DOC-07 的 run_mode 字段 + fork/background 的持久化语义
- **Batch 3**: DOC-09 的 MCP 表要支持 agent-scoped MCP(新字段 `scope: global | agent`)
- **Batch 4**: 前端要区分展示 foreground/background/fork 子 Agent 的不同 UI
- **Batch 5**: Obs 要追踪 CC 的完整生命周期事件(含 background completion notification)

---

> **状态**: 本补丁写入 `/home/claude/review-patch-pdf.md`,会落盘到 outputs。
> **下一步**: 直接进 Batch 3。

---

## 附: 11 个关键 CC 文件索引(PDF §10 提炼,改写时精准引用)

```
Prompt 装配:       src/constants/prompts.ts
Agent Tool 协议:   src/tools/AgentTool/prompt.ts
Skill Tool 协议:   src/tools/SkillTool/prompt.ts

Agent 调度:
  src/tools/AgentTool/AgentTool.tsx      — 调度总控
  src/tools/AgentTool/runAgent.ts        — 子 agent runtime constructor
  src/tools/AgentTool/resumeAgent.ts     — 恢复机制
  src/tools/AgentTool/forkSubagent.ts    — fork 专用路径
  src/tools/AgentTool/agentMemory.ts     — memory 管理
  src/tools/AgentTool/builtInAgents.ts   — 内建 agent 注册

内建 agents:
  src/tools/AgentTool/built-in/exploreAgent.ts
  src/tools/AgentTool/built-in/planAgent.ts
  src/tools/AgentTool/built-in/verificationAgent.ts
  src/tools/AgentTool/built-in/generalPurposeAgent.ts

Plugin/Hook/Tool:
  src/utils/plugins/loadPluginCommands.ts
  src/services/tools/toolHooks.ts
  src/services/tools/toolExecution.ts

MCP:
  src/services/mcp/types.ts
  src/services/mcp/normalization.ts
  src/entrypoints/mcp.ts
```

DOC-03/04/05 改写时,每个 Task 的"CC 架构映射"表格必须精确到这些文件名。
