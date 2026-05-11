# Prism 架构重构 Master Spec

> **Date**: 2026-05-11
> **Status**: Approved
> **决策者**: 用户（产品创始人）
> **执行约束**: 参考 Claude Code 源码 + Claude Agent SDK 可直接用；Poco 只借鉴不抄

---

## 1. 现状诊断

### 1.1 Executor 实际状况（审计结论）
- **100% 自研**，未使用 Claude Agent SDK
- 仅用 `anthropic>=0.40.0` 官方包的 `count_tokens()` 方法
- TAOR 循环、工具系统、Compaction、Harness 全部从零写
- ~15K LOC，35 个 Task 拼接而成，胶水严重
- 致命 Bug：AnthropicDriver 丢弃 thinking blocks → 多轮工具调用全崩

### 1.2 产品定位
- **是**：个人助手 agent system（日常记录、备忘、会议、brainstorming、轻度生产力）
- **不是**：开发者工具（区别于 Poco）
- **目标**：弱模型（DeepSeek/Qwen）达到 Claude 80-90% 效果
- **部署**：自托管 + 云端订阅
- **核心体验**：预判、懂你、顺手、放心

### 1.3 重构决策
用户选择：**用 Claude Agent SDK 重写 executor**，保留有价值的自研部分。

---

## 2. 目标架构

```
用户（Web / IM）
    │
前端（React 18 + TypeScript + Vite）← 本 session 已完成
    │
后端（FastAPI）← 保留，清理 API 契约
    │
UserBrain（新增）
├── IntentRouter ─── 意图识别 → skill 匹配
├── MemoryManager ── mem0 持久记忆 + 用户画像
├── VerifyAgent ──── 结果自验证 + 置信度
└── Context7Client ─ 实时文档增强
    │
Executor（重写）
├── claude-agent-sdk ── Agent 循环核心（替代自研 TAOR）
├── ModelRouter ─────── 多模型适配（Anthropic/OpenAI/国产）
├── HarnessHooks ────── 治理层（从自研 Harness 精简移植）
│   ├── PermissionHook ─ 权限控制
│   ├── GuardrailHook ── 安全护栏
│   └── ObservabilityHook ─ 指标/日志/追踪
├── ToolRegistry ────── MCP + builtin + skill_invoke
└── CompactionManager ─ 上下文压缩（SDK 内建 or 精简自研）
    │
模型（Claude / DeepSeek / Qwen / GLM / Gemini）
```

---

## 3. 重构原则

1. **SDK 优先** — SDK 能做的不自研。Agent 循环、tool calling、streaming 交给 SDK
2. **只保留有价值的自研** — Harness 治理（权限/护栏/审计）、多模型适配、MCP 集成
3. **删比写重要** — 15K LOC 自研 executor 预计删 80%，保留 20% 精华
4. **效果驱动** — 每个阶段结束必须跑通真实任务验证效果
5. **不打补丁** — 不在旧 executor 上修修补补，直接新建 `executor_v2/`

---

## 4. 分阶段计划

### Phase A：SDK 接入 + 最小可用（预计 2-3 session）

**目标**：用 Claude Agent SDK 跑通一个多轮工具调用任务

**做什么**：
1. 安装 `claude-agent-sdk`，读源码理解 Agent/Tool/Hook 接口
2. 新建 `executor_v2/` 目录，不动旧代码
3. 实现最小 executor：SDK Agent + 基础工具（Bash/Read/Write）+ Anthropic Provider
4. 接入 backend 的 callback/SSE 协议
5. ProcessManager 启动新 executor_v2 替代旧 executor
6. **验证**：提交任务"帮我搜索今天上海天气"→ agent 调用工具 → 返回结果 → 前端显示

**不做**：多模型、Harness 治理、Compaction、Memory — 先让引擎转起来

**交付物**：
- `executor_v2/__main__.py` — 新入口
- `executor_v2/agent.py` — SDK Agent 包装
- `executor_v2/tools/` — 基础工具集
- `executor_v2/callbacks.py` — 对接 backend

### Phase B：多模型适配 + Harness 移植（预计 2-3 session）

**目标**：支持 DeepSeek/Qwen 等国产模型 + 基本治理

**做什么**：
1. SDK 的模型切换机制研究（是否支持 OpenAI 兼容端点）
2. 如果 SDK 不支持 → 在 SDK 外层包 ModelRouter，按 Provider 配置选模型
3. 从旧 Harness 移植精简版：
   - PermissionHook（权限询问，Redis BLPOP）
   - GuardrailHook（四铁律 + 平台规则）
   - ObservabilityHook（structlog + Prometheus）
4. ThinkingBlock 确认 SDK 原生支持（不需要自己处理）
5. **验证**：用 DeepSeek 跑"帮我做一个竞品调研"→ 多轮搜索 → 结构化报告

**交付物**：
- `executor_v2/model_router.py` — 多模型路由
- `executor_v2/hooks/` — 治理 hooks
- 旧 `executor/` 标记废弃

### Phase C：UserBrain 记忆层（预计 2 session）

**目标**：agent 记住用户，跨 session 持久

**做什么**：
1. 集成 mem0（pip install mem0ai）
2. 实现 MemoryManager：
   - 对话结束自动提取记忆（用小模型）
   - 对话开始自动召回相关记忆注入 prompt
   - 记忆类型：事实/偏好/习惯
3. 后端 API：记忆 CRUD
4. 前端：Settings → 记忆管理页
5. **验证**：第一次对话说"我住在上海"→ 关闭 → 第二次对话说"帮我查高铁"→ agent 自动查上海出发

**交付物**：
- `executor_v2/userbrain/memory.py`
- `backend/app/services/memory_service.py`
- `frontend-react/src/pages/Settings/MemoryTab.tsx`

### Phase D：UserBrain 验证层（预计 2 session）

**目标**：agent 输出经过验证，弱模型不瞎编

**做什么**：
1. 实现 VerifyAgent：
   - agent 输出后，第二个 agent（或同模型换 prompt）审查结果
   - 事实性声明用 Context7 + 搜索交叉验证
   - 置信度评分（高/中/低）
   - 低置信度 → 不返回结果，问用户确认
2. 弱模型补偿策略：
   - 大任务拆小步（每步可验证）
   - 多源交叉（同一事实 2+ 来源确认）
   - 结构化输出模板（约束模型输出格式）
3. 前端：置信度指示器（绿/黄/红）
4. **验证**：用 DeepSeek 做调研 → VerifyAgent 标注不确定点 → 用户确认后修正

**交付物**：
- `executor_v2/userbrain/verify.py`
- `executor_v2/userbrain/context7.py`
- 前端置信度 UI

### Phase E：UserBrain 意图路由 + 内置 Skill（预计 2-3 session）

**目标**：用户说人话，系统自动匹配工作流

**做什么**：
1. 实现 IntentRouter：
   - 用小模型做意图分类（7 类）
   - 意图 → skill 映射
   - 用户记忆影响路由权重
2. 实现 8 个内置 skill：
   - ChatSkill（日常对话 + 记忆注入）
   - MemoSkill（备忘录 — 存储/标签/检索）
   - ReminderSkill（提醒 — 定时触发）
   - ResearchSkill（调研 — 多源搜索 + 交叉验证 + 报告）
   - BrainstormSkill（研讨 — MECE/SWOT 框架引导）
   - WritingSkill（写作 — 模板 + 审查）
   - AnalysisSkill（数据分析 — Excel/CSV）
   - MeetingSkill（会议 — 摘要 + 行动项）
3. 前端：skill 匹配 badge + 手动切换
4. **验证**：输入"帮我记一下明天下午3点开会"→ 自动识别为 ReminderSkill → 存储 + 设置提醒

**交付物**：
- `executor_v2/userbrain/router.py`
- `executor_v2/skills/` — 8 个内置 skill
- 前端 skill UI

### Phase F：集成打磨 + E2E（预计 1-2 session）

**目标**：全链路跑通，产品可用

**做什么**：
1. 旧 `executor/` 完全移除
2. Docker Compose 更新（executor_v2）
3. nginx 配置更新（前端 dist 路径）
4. IM Gateway 对接新 executor
5. 全链路 E2E Playwright 测试
6. Simplify + PJR + 合并
7. **验证**：用户完整使用 5 个场景（备忘/调研/brainstorming/写作/对话），桌面 + 移动端

---

## 5. 技术参考

### Claude Agent SDK（重点研究）
- Agent 类：循环控制、tool calling、streaming
- Hook 接口：setup/response/teardown/error
- Tool 接口：定义、注册、执行
- 多模型：是否原生支持 OpenAI 兼容端点

### Claude Code 源码（可直接用）
- Compaction 策略
- Prompt engineering 模式
- Tool 实现（Bash/Read/Write/Glob/Grep）
- Permission 交互模式

### Poco（只借鉴）
- executor_manager 调度架构
- Hook 设计模式（WorkspaceHook/TodoHook/CallbackHook）
- Delta API 增量更新策略

### mem0（直接集成）
- 向量存储 + 知识图谱
- 自动记忆提取
- 相关性召回

### Context7（直接集成）
- /v2/libs/search — 库搜索
- /v2/context — 文档查询
- 事实验证增强

---

## 6. 验收标准

### 最终产品验收
- [ ] 用 DeepSeek 跑"帮我调研一下最近的 AI Agent 产品竞品"→ 输出结构化报告 → 关键事实经过验证
- [ ] 第一次对话说个人信息 → 第二次对话 agent 记住了
- [ ] 输入"帮我记一下"→ 自动走 MemoSkill → 存储成功
- [ ] 输入"跟我讨论一下产品方向"→ 自动走 BrainstormSkill → 框架引导
- [ ] 不确定的结果 agent 主动说"我不太确定"
- [ ] 桌面端 + 移动端全流程通
- [ ] 弱模型（DeepSeek）效果 ≥ Claude 80%

### 每阶段必须验证
- Phase A：多轮工具调用跑通
- Phase B：国产模型跑通 + 权限拦截
- Phase C：跨 session 记忆生效
- Phase D：验证层标注不确定点
- Phase E：意图自动路由正确
- Phase F：5 场景全通
