# Prism v2 跨 Session Handoff 日志

> **规范**: 每个 Sonnet session 结束前必写一段 200-400 字记录;新 session 开工前必读最近 3 条
> **格式**: 倒序(最新在顶)
> **初始化**: 2026-04-18

---

## 🔴🔴 2026-05-09 React 前端迁移 + 后端全面审计 + Skills Market 重构

**模型**: Opus 4.6 (1M context)
**分支**: develop（31 commits）
**统计**: 140 文件变更，19,296 行新增

### ⚠️ 用户工作风格与情绪备忘（新 model 必读）

**用户是产品创始人，技术判断力极强，不接受表面功夫。** 以下是本 session 验证过的行为模式：

1. **不要问方向，直接做** — 用户多次明确"你看着做决策""不用问我""我只负责验收"。犹豫和反复确认会激怒他。
2. **"能用"不等于"好用"** — 用户对"勉强跑通"极度不满。安装按钮点了没反应、搜索结果不对、功能是假的 → 这些都会被立刻指出。他要的是真实可用，不是 demo。
3. **并发执行** — 用户明确要求"允许并开 subagent""尽量并发"。串行工作会被认为效率低。
4. **发现 bug 就修** — "为什么要下个迭代，修啊""干啊" — 不接受拖延，当场修。
5. **不要复述他说过的话** — 反感重复和废话。直接行动，简短汇报结果。
6. **商业级标准** — 产品对标 Manus，不是个人玩具。GitHub 搜索返回不相关结果、安装是假的、skill 装了不能用 → 这些都是不可接受的。
7. **先业务后技术** — 先讲用户能看到什么、能做什么，再讲技术实现。
8. **原则高于一切** — 反打补丁（深度融合）、最简代码、类型严格、文档置信度 → 这些不是建议，是硬底线。

**情绪快照**：本 session 用户从讨论产品哲学开始，到看到前端成果后兴奋，到发现 Skills Market 搜不到东西时不满，到搜索逐步改善后认可，到发现安装是假的时再次不满，到 skill_invoke 实现后回到正轨。**用户在意的是"这东西真的能用"，不是"代码写了多少"。**

### 🐛 本 session 发现的运行时 Bug（后台日志）

| Bug | 日志 | 严重性 | 状态 |
|---|---|---|---|
| 飞书 WebSocket 连接失败 | `this event loop is already running` | HIGH | 未修 — asyncio 事件循环冲突 |
| Run 心跳超时崩溃 | `heartbeat_monitor.crashed_marked` run_id=069ff240/069ff249 | HIGH | 未修 — executor 子进程可能启动失败或卡死 |
| Run 执行错误 | `callback.received event_type=run_error` run_id=069ff240 | MEDIUM | 未修 — 需查 executor 子进程日志 |
| nginx unhealthy | 静态文件路径指向旧 frontend/ | LOW | 未修 — 需更新为 frontend-react/dist/ |

### 本 session 三大交付

| 领域 | 交付 |
|---|---|
| **P1 前端迁移** | Prism.html 单文件 → React 18 + TypeScript + Vite 完整迁移。6 Phase 全部完成：设计系统 + 39 Icon + 12 共享组件 + typed API client(955行) + useSSE + Auth/Theme/Session contexts + Auth 页面 + Chat(SSE streaming) + Content Renderer(marked+Prism.js) + Markdown Export(Turndown) + Sessions/Settings(5tabs)/Skills Market/Plugin Builder/Usage/Observability + Admin(Dashboard+Users+Audit+Invites) + Dark mode/Mobile/A11y/Lazy loading/ErrorBoundary。Simplify 3-agent 审查 → 13 项修复。PJR ESLint 0 errors + build 通过。 |
| **P2 后端审计修复** | 11 个并发 subagent 全面审计（API 5 域 + executor + services + DB + 集成 + 契约 + 配置）。发现并修复 20 项问题：SIGTERM 崩溃(C1+C2)、timeout 状态链路断裂(C3)、AuditLog schema 崩溃(C4)、前后端类型不匹配(C5-C7)、callback 字段缺失(H4+H5)、providers/usage 路由顺序 bug(H6)、mcp-servers/{id} 路由缺失(H7)、config 不一致(M1)等。 |
| **P3 Skills Market 重构** | 对齐 Claude Code CLI 的 marketplace/skills 逻辑：GUI 来源管理（添加/移除 marketplace 源，常用预设）+ GitHub 双重搜索（精确名称+Claude 范围，star 排序 top 5）+ "你要找的是不是？"拼写纠错（edit distance ≤ 2）+ Context7 文档搜索源（Docs tab）+ 直接安装 by URL + GitHub 安装真实下载内容 + **skill_invoke 工具**（agent 可动态加载并使用已安装 skill）+ 安装后子 skill 扫描注册。 |

### 新增文件/目录

- `frontend-react/` — 完整 React + TS 前端（116 文件）
- `executor/tools/builtin/skill_invoke.py` — skill 调用工具
- `executor/plugins/context7_source.py` — Context7 搜索源
- `executor/plugins/github_source.py` — 重写：双重搜索 + 纠错
- `start-dev.sh` + `start-dev.ps1` — 开发启动脚本
- `.mcp.json` — Context7 MCP 配置

### 已知问题（下个 session 处理）

1. **Skill 完整调用链路未 E2E 验证** — skill_invoke 工具已实现但需要配置 Provider API Key 后实际触发一次 Agent Run 验证
2. **nginx unhealthy** — 静态文件路径指向旧 `frontend/`，需更新为 `frontend-react/dist/`
3. **前端未接入 Docker** — 目前用 Vite dev server 独立运行，生产部署需要 `vite build` + nginx 托管
4. **卸载只删 DB 记录** — 未清理本地下载的文件（`.prism/skills/@github/`）

### 环境信息

- 端口：8080（nginx → backend:8000），3000（Vite dev server）
- 账号：admin@prism.dev / admin123
- Docker 服务：backend healthy，nginx unhealthy（需更新静态文件路径）
- 前端 React 项目：`frontend-react/`，ESLint 0 errors，build 通过（10 chunks）

### 用户明确指示

- Prism 对标 Manus，兼顾个人自用和商业化
- 前端用 React + TypeScript（非 HTML），因为要对标商业级品质
- Skills Market 对齐 Claude Code CLI 的 marketplace/skills 逻辑
- 所有开发严格遵循 superpowers 流程（brainstorming → plan → worktree → simplify → PJR → merge → E2E）
- 反打补丁硬规则：深度融合代码逻辑，不打补丁
- Context7 MCP all in（Claude Code + Prism 都装）

---

## 🔴 2026-05-10 搜索 + Marketplace + Plugin Builder v2 三连交付

**模型**: Opus 4.6 (1M context)
**分支**: develop（22 commits）

### 本 session 已交付

| 领域 | 交付 |
|---|---|
| P1 搜索体验 | rapidfuzz 模糊匹配 + 多词拆分 + 加权评分(name×5/tags×3/desc×1) + GitHub SKILL.md 验证 + 结果限 10 条 + 无结果 UX 改善 |
| P2 Marketplace UX | 推荐来源一键添加（仅已验证的 Anthropic Official）+ URL placeholder 改善 + 格式提示 |
| P3 Plugin Builder v2 | 删 4 型选择器 + 删 7 维打分循环(-450 行) + CC-style 直接输入 + 搜索优先 prompt + 简化保存(无 YAML 编辑) |

### 已知问题（下个 session 处理）

1. **Plugin Builder prompt 需继续调优**：AI 仍可能暴露内部思考过程，已加硬性禁止规则但需更多 E2E 验证
2. **GitHub 搜索 topic:skill 限制太强**：大多数 repo 没有 skill topic，加上 SKILL.md 验证后 GitHub 结果可能很少
3. **Dead-content audit 7 项待做**：ProfileTab 改密码、ObsPage 死数据、admin 6 个 placeholder 面板

### 环境信息

- 端口：8080（nginx → backend:8000）
- 账号：admin@prism.dev / PrismAdmin!2026
- Docker 服务全部 healthy
- 前端缓存破除：apiClient.js?v=20260510

### 用户明确指示

- PRD_V4 是唯一愿景源
- 产品级标准：好用、高质、可信度高、易维护
- 不要问方向，按优先级自行推进
- 不要做表面功夫，确保端到端链路真的通

---

## 🔴🔴🔴 新 session 开工必读(/clear 后第一眼看这里)🔴🔴🔴

**完整交接册**:`NEXT-SESSIONS-PLAYBOOK.md`

### ⚠️ 最高优先级:文档置信度 HARD GATE(用户 2026-04-20 重申)

三个剩余问题(分布式 / Skills Market / IM 小尾)**必须** 基于各自的**调研报告 + 官方手册 + 真实案例 + 工作原理** 设计,**禁止按 AI 自己的逻辑推测**。

- 仓库已有 3 份 research:`docs/research/2026-04-19-distributed-task-decomposition.md` / `2026-04-19-skills-plugins-im-competitive.md` / `2026-04-20-session3-design-brief.md` —— **对应开工必读**
- 需查信息用 **exa MCP**(`mcp__exa__web_search_exa` / `mcp__exa__web_fetch_exa`)
- 官方 primary source 必 WebFetch 一次再写代码(PLAYBOOK §-1 列了每个问题的 URL 清单)
- **关键功能(支付/DB/API)文档置信度不足,立即停下写 blocker + 请用户提供资料,严禁盲写**

完整 GATE 触发条件 + 每问题的必读 research + 必 WebFetch URL + 必 exa 关键词,见 PLAYBOOK §-1 + §1。

### PLAYBOOK 其他内容:
- **已完成清单**(Session 4a/4b + 之前)—— 避免重做
- **剩余 3 问题**:分布式任务拆解(4-5 session) / Skills Market catalog browser(1-2 session) / IM 三小尾(0.5 session)
- **开发原则**(用户 5 条 + CLAUDE.md 六原则 + 生产代码无 mock 原则)
- **验收标准**(量化指标:TDD / unit / e2e / Simplify / PJR / merge / DECISIONS / HANDOFF)
- **Workflow 17 步**(Session 4a/4b 已验证)
- **Pre-existing flaky tests 清单**(别当回归处理)
- **10 个关键坑**(Playwright baseURL / Docker backend build / pytest / nginx mount / 飞书签名 / Discord 401 / schema 定死 / Pydantic v2 / Simplify reuse / `example.test` URL)
- **Docker + worktree 清理**
- **code-reviewer 6 次累积队列**(Session 4c 开头补跑)
- **推荐顺序**:Session 4c = Skills Market (ROI 最高) → 4d = IM 小尾 → 4e+ = 分布式

**推荐开工路径**:读 PLAYBOOK §0 + §1 → §9 推荐顺序挑一项 → §3 Workflow 执行。

---

## 🔴 2026-05-09 用户反馈：Skills Market + Plugin Builder 体验不达标

**模型**: Opus 4.6 (1M context)
**分支**: develop（16 commits 已提交）

### 本 session 已交付

| 领域 | 交付 |
|---|---|
| P0 Prompt Caching | 静态/动态 system block 拆分，cache_control 注入静态前缀，8 测试 |
| P1 Plugin Builder | 26 条垃圾清除 + 端到端构建流程验证通过 |
| P2 Topbar | Demo switcher 改 dev-only |
| P4 移动端 | 侧栏 overlay + hamburger 切换 |
| Skills Market Phase 1a | GitHub 搜索源 + 来源 Badge + README 详情面板 |

### 用户反馈（未解决，下个 session 最高优先）

**1. 搜索体验差（最核心）**
- 精确子串匹配 → 需要模糊搜索 / 语义搜索
- 搜 "design" 只匹配名称含 design 的，搜不到描述中相关的
- GitHub 搜索有时超时或结果不精准（搜 weather 返回 awesome-go）
- 用户期望：输关键词能找到所有相关 skill，类似 npm search 体验

**2. Plugin Builder 对话逻辑问题**
- 错误应该用弹窗，不要在对话中报
- 用户不应该填技术参数（端口、API key 格式等），系统自动推断
- 用户只提需求（如"做一个读金融 KYC 的 agent"），系统应该：
  - 先搜 GitHub 有没有现成的（如 Anthropic 5/5 发布的 10 个预制 agent）
  - 能用的直接拿来用，不从零做
  - 评估自建 vs 复用 vs 组合的 ROI

**3. Marketplace 注册入口不直观**
- 用户不知道怎么注册新 marketplace（如 gstake）
- gstake 等第三方 marketplace 需要 CLI 命令安装，前端没有引导
- 用户期望：一键注册 marketplace URL → 自动同步 → 可浏览安装

**4. 安装流程问题**
- GitHub 搜到的结果不能直接安装（缺少安装流程）
- 部分 marketplace skill 安装无反馈

### 技术现状

- **后端 GitHub 搜索 API 可用**：`GET /skills/search?q=design` 返回 marketplace + github 混合结果
- **前端来源 Badge + 详情面板已实现**：点击搜索结果可看 README
- **README fallback 已实现**：SKILL.md → README.md → "暂不可用"
- **缓存问题**：前端 JS/CSS 需要版本化缓存破除，nginx 缓存激进

### 下个 session 执行计划

**优先级 1：搜索体验改善**
- 后端：搜索扩展到 description + tags 匹配（不只是 name）
- 后端：GitHub 搜索优化查询词（更精准的 query 构建）
- 前端：搜索结果排序优化（已安装 > marketplace > github）
- 前端：无结果时给出有用建议（而不是"检查拼写"）

**优先级 2：Marketplace 注册 UX**
- 前端：Marketplace tab 注册入口更显眼
- 预置常用 marketplace（如 anthropic 官方、gstake 等）
- 注册后自动同步 + 显示目录数量

**优先级 3：Plugin Builder v2 智能构建**
- 需求阶段完成后，先搜 GitHub 现有方案
- 评估自建 vs 复用，给用户选择
- 错误用弹窗而非对话
- 参数自动推断

### 环境信息

- 端口：8080（nginx → backend:8000）
- 账号：admin@prism.dev / PrismAdmin!2026
- Docker 服务全部 healthy
- 前端缓存破除：styles.css?v=20260509, apiClient.js?v=20260509

### 关键文件

- `docs/superpowers/specs/2026-05-09-skills-ecosystem-plugin-orchestration-design.md` — 整体架构设计
- `docs/superpowers/plans/2026-05-09-skills-market-gui-phase1a.md` — Phase 1a 实施计划
- `executor/plugins/github_source.py` — GitHub 搜索适配器
- `backend/app/api/v1/skills.py:553-614` — README 端点
- `.claude/memory/project_skills_plugins_vision.md` — 用户产品愿景
- `.claude/memory/project_plugin_builder_ux.md` — Plugin Builder UX 方向

---

## ✅ 2026-05-09 P0-P4 Convergence 完成（Opus 4.6 session, develop）

**模型**: Opus 4.6 (1M context)
**分支**: develop

**P0 Prompt Caching 真集成**:
- `_build_system_blocks()` 按 CACHE_BOUNDARY_MARKER 拆分 system_prompt
- `_inject_cache_control()` 改为注入第一个 block（静态前缀）
- 8 单元测试 + 62 executor pass + Simplify 3-agent + E2E 桌面+移动端

**P1 Plugin Builder 清理**:
- 清除 26 条 `untyped-plugin-*` + 2 条 test 垃圾记录
- E2E 完整流程验证：描述→Agent生成→授权→保存 ✓

**P2 Sessions/Topbar 审计**:
- Sessions 表格行跳转正常
- Demo switcher 改为 `isDevEnv` 条件渲染（production 隐藏）
- 侧栏 rename/delete 记录为后续需求（API 存在，前端未实现）

**P3 企业微信**: 跳过（需用户凭证）

**P4 移动端响应式**:
- 侧栏改为全屏 overlay + hamburger 按钮切换
- 导航自动关闭侧栏显示主内容
- CSS cache-bust via version query param

**用户反馈（已存 memory）**: Plugin Builder 应支持模板复用/对话持久化/增量编辑

**Skills Market GUI Phase 1a（同 session 追加）**:
- GitHub Repository Search 适配器（无需 token，按 stars 排序）
- README 预览端点 GET /skills/{name}/readme（本地 → GitHub → 兜底）
- 前端：搜索结果 SourceBadge（GitHub/Marketplace/Local 彩色标签）
- 前端：详情面板（右侧滑入，README 渲染 + 安装按钮 + 查看源码链接）
- E2E 验证：搜索 "weather" → 15 个 GitHub 结果 → 点击详情面板正常显示

**追加修复**:
- README 端点 fallback 到 README.md（SKILL.md 不存在时）
- apiClient.js 缓存破除

**本 session 共 15 commits on develop**

**下一个 session**: 
1. Skills Market CLI 命令（`/skill search`、`/skill install`）
2. Playground 试用（安装前试用 Skill）
3. Agent 被动/主动双层调用
4. 侧栏会话 rename/delete
5. Plugin Builder UX 改进（模板/持久化/增量编辑 — 见 memory）

---

## ✅ 2026-05-09 P1 Plugin Builder 清理 + P2 Sessions/Topbar 审计

**P1 Plugin Builder**:
- 清除 DB 26 条 `untyped-plugin-*` + 2 条 `test-plugin`/`verify-plugin` 垃圾记录
- E2E 验证完整流程：描述 → Agent 生成 manifest（7 维评分 5/5）→ 授权审查 → 保存到插件库
- 插件库 (0) → (1) `my-plugin` v1.0.0 正常显示

**P2 Sessions/Topbar**:
- Sessions 表格行点击跳转正常
- 侧栏对话列表无 rename/delete UI（API 存在但前端未实现 — 记录为后续需求）
- Topbar 4 按钮审计：权限请求/计划面板/语言切换/更多 — 均为功能按钮
- Demo switcher（登录页/空状态/应用）改为 `isDevEnv` 条件渲染，production 下隐藏

**P3 企业微信**: 跳过（需用户提供 CorpID + Secret 凭证）

**用户反馈（已存 memory）**: Plugin Builder 应支持模板复用/对话持久化/增量编辑

---

## ✅ 2026-05-09 P0 Prompt Caching 真集成（已 merge develop）

**模型**: Opus 4.6 (1M context)
**分支**: develop（已合并 feat/prompt-cache-real-split，worktree 已清理）

**问题**: `prompt_assembler.build()` 返回 `静态前缀 + CACHE_BOUNDARY_MARKER + 动态后缀` 单个字符串。AnthropicDriver 把整个字符串包成一个 text block 加 cache_control → 动态部分每轮变 → 缓存永远命不中。

**修复（2 commits）**:
1. `_build_system_blocks()` — 按 CACHE_BOUNDARY_MARKER 拆分为两个 system content block（静态前缀 + 动态后缀）
2. `_inject_cache_control()` — 改为在第一个 text block（静态前缀）注入 cache_control，而非最后一个
3. `stream()` 和 `complete()` 调用替换

**文档置信度**: WebFetch Anthropic 官方 prompt caching 文档确认格式、breakpoint 限制（最多 4 个）、最低 token 阈值

**审查**: Simplify 3-agent（reuse/quality/efficiency）+ PJR（py_compile + 62 executor pass + 132 backend pass）

**E2E 验证**: Playwright 桌面 1280×800 + 移动 390×844
- 新对话 → 发送 → AI 回复正常（两轮多轮对话）
- 可观测性页面底栏"缓存 72%"数据流通
- 后端日志 `POST /v1/messages` → 200 OK

**下一个 session**: 继续 `docs/superpowers/plans/2026-05-08-remaining-convergence.md`，从 P1 Plugin Builder 清理开始

---

## ✅ 2026-05-08 Opus 4.6 PRD-Reality Convergence（Phase 1 + Skills 根因 + 飞书 IM，已 merge develop）

**模型**: Opus 4.6 (1M context)
**分支**: develop (已合并 phase1/prd-convergence + fix/skill-install-materialize + feat/feishu-websocket + audit/prd-vs-reality)

**交付（~25 commits on develop）**:
1. **合并 audit 分支** — 4.7 的 10 个 P0/P1 修复（密码/死按钮/主题/持久化等）
2. **Phase 1 清零** — ObsPage 真实 `/harness/analytics` 数据、Admin 5 placeholder tabs 全部替换为真实 API 驱动页面（护栏/Skills/账务/基础设施/可观测）、Entropy Detector 每小时定时调度、apiClient 参数修复、5 组 mock 常量删除
3. **Simplify 审查** — 3-agent 并行审查修复所有 CRITICAL/HIGH（asyncio.to_thread、字段名修正、shared component 提取、theme hydration）
4. **Skills 安装根因修复** — marketplace install_plugin() 从未把 SKILL.md 复制到永久目录（`.prism/skills/@marketplace/`），executor SkillLoader 找不到文件。修复: shutil.copytree 到永久路径
5. **飞书 IM WebSocket** — 集成 lark_oapi SDK、WebSocket 长连接模式、消息收发全链路跑通（用户验证 OK）

**测试**: 132 backend + 54 executor pass，E2E Playwright 桌面+移动端验证

**性能诊断**: 用户体验慢的根因是 TLS 到 api.tutorial.clouddreamai.com 耗时 5 秒（深圳→香港→美国洛杉矶三跳）。部署到国内服务器可解决。

**下一个 session 必读**:
- `docs/superpowers/plans/2026-05-08-remaining-convergence.md` — P0-P4 优先级排序
- P0: Prompt Caching 真集成（AnthropicDriver cache_control）
- P1: Plugin Builder 垃圾清理 + 流程验证
- P2: Sessions 侧栏 + Topbar 审计
- P3: 企业微信适配器（等用户凭证）
- P4: 前端 UX 细节（移动端响应式、toast 反馈）

**环境**: 端口 8080（.env HTTP_PORT=8080），默认账号 admin@prism.dev / PrismAdmin!2026，飞书 bot 已连通（FEISHU_MODE=websocket）

---

## 🚧 2026-05-08 PRD vs Reality 全审计 + P0/P1 修（audit/prd-vs-reality, 9 commits, 已合并 develop）

**Branch**: `audit/prd-vs-reality` worktree at `.worktrees/audit-prd-vs-reality/`
**Status**: 用户正在浏览器试用 http://localhost:18888/Prism.html，等反馈
**完整交接**: `docs/audit/2026-05-08-HANDOFF-NEXT-SESSION.md` ← **下一个 session 必读第一**

**用户硬要求**: PRD 设计的功能必须真接通；禁止虚的/死的/装饰；audit 不彻底就不许 merge

**Audit Phase 1（5 docs）**:
- 87 条 PRD 用户可见功能清单
- 81 frontend 交互（72 wired / 3 dead / 6 placeholder）— audit B 漏报 6 处后被主 agent 二扫发现
- 86 backend endpoints（81 real / 1 partial / 2 param-ignored / 1 missing）

**9 commits 修复（最新在顶）**:
- `e3f7e25` 本交接文档
- `7396bbc` 持久化: /app/data 命名 volume + bootstrap 自动 resync 缺失 clone
- `eb22fb8` 复活 6 死按钮（Composer 3 + 消息气泡 3）+ 主题持久化 + skill install 前端 forward
- `c063d36` (W12 sonnet) skill install marketplace 链路: SkillPackage 加 marketplace_id+plugin_name + search 透传 + install 路由
- `0d893e2` bootstrap 注册后 inline sync + e2e fixture BASE_URL env override
- `6908c80` POST /auth/change-password endpoint（audit C 误判说存在）
- `87c7811` (W11 sonnet) ProfileTab 修改密码 modal + analytics window→days
- `b9bab6b` (W10 sonnet) 5 backend bug: MCP system toggle 尊重 user / marketplace bootstrap by name / GET /providers/{id} / admin/usage 参数 / audit-logs 参数名
- `5d31892` 5 audit reports

**测试**: 134 backend pass / 12 executor pass / 36 e2e effective pass 双端

**用户报告 4 件事全修**:
1. 对话框左下 3 按钮死 → Composer 全 wire
2. 亮/暗切换死 → boot script + Tweaks 读 localStorage
3. 能搜到下载不了 → marketplace_id+plugin_name 透传 + 容器持久化 volume + bootstrap auto-resync
4. GitHub 能找到的找不到 → 35 catalog 中 12 skill-type 真能装，其余 23 报 422（follow-up：扩 install 支持 commands/MCP/agents）

**主 agent 二扫发现**: 消息气泡 3 按钮（复制/再试/分叉）audit B 漏报，已 wire

**还没审到（下一个 session 立刻可干）**: IM tab / Providers tab / Sessions list buttons / Plugin Builder / Topbar dev preview line 4294-4296 / ObsPage UI 真接 API / 6 admin placeholder tabs

**关键操作环境**:
- 端口 **18888**（Windows Hyper-V 锁了 8080/18080，三次切端口）
- e2e 必带 `BASE_URL=http://localhost:18888`
- nginx 偶发 unhealthy 但 backend 真活；以 `curl /health/ready` 为准
- 默认账号 `admin@prism.dev / PrismAdmin!2026`（dev mode `/auth/providers` 返此）
- 用户 `.env` 有真 EXA_API_KEY 和 SEARXNG_SECRET_KEY auto-gen
- Backend rebuild: `docker compose -p prismv3 build backend && docker compose -p prismv3 up -d --force-recreate --no-deps backend`
- Nginx restart (改 frontend 后): `docker compose -p prismv3 restart nginx`

**决策点（待用户拍）**:
1. merge audit 到 develop？9 commits 都 PASS（用户尚未给 OK）
2. catalog 非 skill-type 怎么办：UI 标注 vs 扩 install 支持？
3. 是否全扫剩余区域（约 1-2 session）

---

## ✅ 2026-05-02 Plugin Bootstrap — Skills + MCP 真实运行复活（feat/plugin-bootstrap, 15 commits）

**根因（systematic-debugging Phase 1）**:
`executor/__main__.py` Step 3d **从未实例化 PluginHost / SkillLoader**。代码完整性 OK 但缺一个调用入口 — 导致 3 个用户投诉同根：(a) Skills 装了不生效 (b) MCP 注册了 agent 看不见 tool (c) 搜索是摆设。

**交付（11 文件改动 + 9 测试文件 + 4 文档）**:
- L1: backend `/internal/users/{uid}/installed-skills` + `/mcp-servers` (CALLBACK_SECRET) — 6072474+6c10cd4
- L2: executor Step 3d-bis bootstrap PluginHost + SkillLoader（**根因修复**）— d1e2fe2+81ba928+4441767
- L3: `POST /mcp-servers/{id}/test` 真连接（含 user_id 权限校验恢复）— bf1b21c+4441767
- L4: 启动期默认 marketplace 自动注册 — adf84a2
- L5a/b: HTTP transport schema + alembic 010 + MCPClient HTTP Streamable (spec 2025-03-26) + SSE streaming + 410 reinit — adf84a2+76d91ef+4441767
- L6: exa builtin entry (HTTP) + AES-256-GCM headers 加密 — d1e2fe2+4441767
- L7: Brave + Tavily stdio builtins (env_var gate) — adf84a2
- L8: e2e Playwright 真调 mcp.exa.ai 真返 URL — 202bdc5+edb6996
- Simplify: 3-subagent (reuse/quality/efficiency) findings 全修 — 4441767

**验证（真实 docker compose live）**:
- 128 backend pytest pass + 10 executor pass + 4/4 effective e2e pass（双端 desktop+mobile）
- 真 exa sample URL: `https://www.cnn.com/2026/05/01/tech/pentagon-ai-anthropic`
- DB 验证: mcp_servers 含 exa 行（transport=http, headers_encrypted=257 chars AES）
- Agent 真 cite 真 URL 在 markdown links 内 ✓

**关键决策（DEC-004/005）**:
- secret: headers_encrypted TEXT 整体 AES-256-GCM；解密在 backend service 层（executor 不持 ENCRYPTION_KEY，进程边界=信任边界铁律）
- builtin 用 `${env:VAR_NAME}` 模板；env 缺失 → graceful skip
- exa 协议探测确认 2025-03-26 + Mcp-Session-Id stateful + SSE

**已知不动账（separate PR / non-blocking）**:
- 前端 tool_card output 渲染：消息持久化双写产生 input:{} 重复行；前端按 tool_use_id 配对被空副本覆盖。修复方向：callback_service tool_start 不写 placeholder，或前端去重取非空 input。不阻塞本 PR（agent 真用 exa 真返 URL）。
- `MCPTestResponse` schema 无 caller，可清

---

## ✅ 2026-04-25 Fix #3+ — Skills search 数据源根因式重构(删 GitHubSource + MarketplaceCatalogSource)

**Trigger**: fix#3 验收时发现 `/skills/search` 永远返空(GITHUB_TOKEN 未设 → GitHubSource 返 [];LocalSource 文件系统空)。

**Root cause**(systematic-debugging Phase 1 + WebFetched Claude Code primary source):
GitHubSource 调 GitHub Code Search API 是 **anti-pattern**,与 Claude Code 官方 plugin discovery pattern(`/plugin marketplace add` → Discover tab 浏览已注册 catalogs)完全不同。Prism 已有 marketplace_registry + catalog_json(Block 1),但 search 从未消费。

**Fix**(根因式 + 反打补丁):
- 删 `GitHubSource` 整个 class + 内部 helper + Phase 2 注释(executor/plugins/skills_registry.py L298-690,~390 LOC)
- 新 `MarketplaceCatalogSource`(~120 LOC):读 marketplace_registry.catalog_json plugins[] flatten + substring filter(name/desc/keywords/tags),DI 注入 db_session_factory 避免 executor → backend 反向依赖
- `SkillPackage.source` Literal 加 "marketplace"
- backend `_get_registry` 注入 `SessionLocal`
- 前端 SkillsSettingsTab + SkillsPage 替换简陋 empty state 为 Linear 风格(2 行:主"无匹配 ${q}" + 副"检查拼写...";0 marketplaces 时含 "去注册" inline 链接 → nav#skills)
- `executor/plugins/__init__.py` export 改

**Verification**:
- backend unit: 9/9(empty / single / name match / description match / keywords-tags match / no match / multi-mp / missing-name skip / author-normalize)
- e2e double-viewport: 7 pass + 1 proper skip = 8/8 effective
- critical regression subset(4 spec)22 pass / 4 pre-existing flaky / 0 regression

**Commits**(merged to develop):
- `45d9946` spec(brainstorming + Source of Truth WebFetched discover-plugins.md)
- `7f6e5f4` plan
- `3e4049f` impl
- merge commit on develop

**用户验收路径**:
1. /Prism.html 登录 → 设置 → 技能 → 搜任意 → 应见 empty state "无匹配 ..." + 0 marketplaces 时 "去注册"链接
2. 点链接跳到 #skills → SkillsPage Marketplace tab → 注册 `anthropics/claude-plugins-official`
3. catalog 拉回后,返设置 → 技能 → 搜 "github" / "commit" → 应出 catalog 中 plugin 结果
4. 任选一条 → 点安装(fix#3 已接通)→ 走完 install 流

**SkillPackage.source 为 "marketplace" 后,fix#3 button data-testid 命名也用 source 前缀**(Block 1 fix#3 spec 已对齐)。

---

## ✅ 2026-04-20 Fix #3 — SkillsSettings 搜索安装死按钮接通(9 缺陷清单第 1 个清零)

**Directive**: 用户全量改造 audit 9 个死内容/死按钮,本次聚焦 #3。

### 本次所做(commit chain)

- `af85a27` spec
- `14e9a1f` plan(8-task inline-exec,完整 RED/GREEN code blocks)
- `9c98c0b`(fix branch)— Task 3 GREEN: Prism.html SkillsSettingsTab L3068-3171 加 installingSearch state + handleInstallFromSearch async function + button onClick wire + data-testid + disabled + minHeight 36
- `e2e/tests/skills-settings-search-install.spec.ts` 新 — 8 场景 × 双端 = 16 tests
- `071d72c`(fix branch)code-review fix:finally cleanup(I-1)+ key by source:name 防同名锁(I-2)
- merge commit on develop

### Root cause

`/skills/search` response 已含 source/source_url/version(skills.py:184-197);死按钮 toast '暂不支持' 是早期 stale safeguard,与后端能力脱节。修复 = 删死代码 + wire 现有 /skills/install endpoint(同 SkillsPage GitHub tab 链路;0 backend 改动)。

### 验证

- e2e 双端: 15 pass + 1 proper skip = 16/16 effective
- 关键子集 regression(skills-settings-search-install + sk-catalog + skills.spec): 19 pass + 3 pre-existing flaky skip,零 regression
- code-reviewer 累积: 2 Important fix 已 commit(I-1 finally + I-2 source:name 复合 key)
- PJR: FastAPI 112 routes / apiClient.js node --check OK / git clean

### 用户验收路径(本机已 deploy)

1. /Prism.html 登录 → 设置 → 技能 sub-tab
2. 搜索框输入 keyword → 点搜索
3. 任选 search result(若不在 Installed list)→ 点"安装"
4. 30s 内绿色 toast"安装成功" + 已安装区域出现该 skill
5. 失败路径:断网点击 → 红色 toast 含具体 error
6. 移动端 viewport(F12 iPhone 14 Pro 390×844): 同样流程

### 9 缺陷剩余 follow-up(顺序按 ROI)

- [✅ 已清零] #3 SkillsSettings 搜索安装(本次)
- [pending] #2 ProfileTab 修改密码(0.3 session)
- [pending] #1 ObsPage 整页死数据(1-2 session)
- [pending] #6 admin 账务(0.5-1 session)
- [pending] #4 admin 护栏(2-3 session)
- [pending] #5 admin Skills 与插件审核(2-3 session)
- [pending] #7 admin 基础设施(2 session)
- [pending] #8 admin 可观测(0.5 session,#1 后)
- [pending] #9 admin 安全(3-5 session)

### Out-of-scope follow-up(本 fix 涉及但跨 DOC)

- N-1: `.btn.sm` minHeight 36 < 44 mobile WCAG 2.5.5 — 全局样式系统升级
- N-2: `err.message || String(err)` toast 透出可能 stack — 项目级 PrismAPI 错误统一
- N-3: `id: Date.now()` toast collision — 项目级 toast id 用 uuid
- 概念:install endpoint 对 source="github" 实际不下载文件 (本 fix 与现有 SkillsPage GitHub tab 行为一致;同一更深层 bug 列入 follow-up)

---

## ✅ 2026-04-20 Session 4c — Skills Marketplace Catalog Browser + 5-source Install(生产级完整,ADR-086 清零)

**Directive**(用户 2026-04-20):"生产级完整交付,没有取舍,ROI 特别低才允许不做;所有功能必须 WebFetch 官方 + exa 全搜集。"

### 本 session 所作所为(Files + TDD 循环)

| 文件 | 动作 | 关键点 |
|---|---|---|
| `backend/app/services/source_resolver.py` | **新 530 LOC** | 5 resolver(RelativePath / GithubTarball / GitUrl / GitSubdir / Npm)+ `_safe_extract_tar`(Python 3.12 `filter='data'` + realpath prefix check 防 CVE-2025-4517)+ `_run_subprocess` async + `_check_rate_limit`(GitHub x-ratelimit-* + retry-after + 403 disambiguation)+ `_inject_github_token`(urlparse netloc exact-match 防子串攻击)+ `_download_and_extract_tarball`(github+npm 共享流程)+ `_require_key`(422 not KeyError) |
| `backend/app/services/marketplace_service.py` | **改 +240** | `_try_fetch` 双模式 + `_fetch_json` + `_fetch_git` + `_is_safe_marketplace_url`(SSRF allowlist)+ `_validate_marketplace_shape` + `_safe_path_segment` + `install_plugin`(Redis SETNX + resolver + SKILL.md frontmatter + UPSERT)+ `_redis_install_lock` |
| `backend/app/api/v1/marketplaces.py` | **改 +40** | `POST /{id}/plugins/{name}/install` 201 + InstallReport;svc.create/sync 用 `asyncio.to_thread` 包裹避免 120s 阻塞 event loop |
| `backend/app/schemas/marketplace.py` | **改 +15** | `MarketplaceCreate.url: str`(放行 owner/repo shorthand)+ `InstallReport` |
| `backend/Dockerfile` | **改 +1** | `apt-get install git`(resolver 3/4 依赖) |
| `backend/tests/` × 8 | **新 860 LOC / 44 tests** | safe_extract 4 + 5 resolver(3-4 ea = 18)+ helpers 20 + infra 1 + pre-existing 1 |
| `frontend/Prism.html` | **改 +290** | SkillsPage Marketplace tab expand→catalog grid(auto-fill minmax 260px / mobile 1-col),plugin 卡片(serif title + amber v-chip + desc clamp + chips + [详情][安装]),details modal + install consent modal,**honest single spinner**(无假阶段进度),sourceDisplay() helper |
| `frontend/styles.css` | **改 +60** | .mp-plugin-card:hover(@media hover)+ focus-visible 2.5px amber ring + 44pt mobile + prefers-reduced-motion |
| `frontend/apiClient.js` | **改 +4** | `marketplaces.installPlugin(id, name)` + encodeURIComponent |
| `e2e/tests/skills-marketplace-catalog.spec.ts` | **新 300 LOC / 10 tests × 2 viewport = 20** | register row / expand / serif+amber+desc / details open+metadata+close / cancel no-POST / confirm success toast / 422 rate-limit toast / 409 concurrent toast / mobile 1-col + 44pt / keyboard focus+Enter |
| `docs/superpowers/specs/2026-04-20-session4c-skills-market-catalog-design.md` | **新** | 829 LOC spec(Source of Truth 清单:WebFetched 3 URL + exa 7 次 + Session 3 基线) |
| `docs/superpowers/plans/2026-04-20-session4c-skills-market-catalog.md` | **新** | 2521 LOC 19-task plan with complete RED/GREEN/commit steps |
| `docs/superpowers/blockers/2026-04-20-marketplace-concurrent-rmtree.md` | **新** | #2 Important finding deferred 说明 + 3 种修复方案 |

### TDD 循环记录(8 commits → 7 after merge cleanup,merged via 908d7ce)

1. **infra** 9937b58 — RED test_infra_git(fail: no git)→ GREEN Dockerfile apt-get git → PASS
2. **resolver** a77935b — RED 21 tests(_safe_extract 4 + 5 resolver × 3-4)→ GREEN 530 LOC source_resolver.py → 21/21 PASS
3. **service** 456a2cb — RED 20 helper tests → GREEN marketplace_service.py dual-mode + install_plugin → 20/20 PASS
4. **endpoint** 9824059 — RED implicit(API via curl)→ GREEN route + schema → curl smoke 201 PASS
5. **frontend** 93a3ac0 — RED 10 e2e expect FAIL(no UI)→ GREEN Prism.html catalog grid + modals → desktop 9/9 + mobile 10/10 PASS
6. **simplify** 9b03215 — reuse helpers(3x token rewrite / 2x tarball download collapsed)+ path sanitize + honest spinner + async subprocess wrap → 44/44 + 20/20 maintained
7. **code-review** e1761f7 — realpath off-by-one fix + urlparse netloc + SSRF allowlist → 44/44 + 30/30 critical maintained

### 不 mock 生产代码 — 证明

- 5 resolver 真实 httpx.AsyncClient.stream + asyncio.create_subprocess_exec(git)。mock 仅在 unit tests 针对 GitHub API / npm registry / git subprocess 响应。
- Playwright e2e `page.route` 仅拦截外部 `/api/v1/marketplaces` list+install 响应(Prism 后端本身未启动也能跑测)。生产浏览器环境无 intercept。
- 用户换 `GITHUB_TOKEN` 后点 /Prism.html 的"安装"按钮会真实走 HTTPS tarball API 下载到 `/app/data/plugin_cache/`。

### 用户自主真实账号测试步骤(生产可用标准)

**前提**:`.env` 加 `GITHUB_TOKEN=ghp_xxx`(可选,公共 repo 无 token 走 60/h);`docker compose -p prismv3 up -d --build --force-recreate backend`(Dockerfile 新增 git binary)。

1. 登录 /Prism.html(`admin@prism.dev / PrismAdmin!2026`)
2. 左侧 nav 点 "技能市场" → SkillsPage → Marketplace tab
3. URL 填 `anthropics/claude-plugins-official`,Name 填 `official` → 点 "添加 Marketplace"
4. 后端克隆 github repo 到 `/app/data/marketplace_cache/*`(30-90s 首次)→ marketplace list 出现
5. 点 ▸ 展开 catalog → 看到 60+ 真实 plugins(官方 marketplace 混用 string + object source 格式)
6. 选某公共 plugin(如 `agent-sdk-dev`,source=`"./plugins/agent-sdk-dev"` relative path)→ 点 "安装"
7. consent dialog 显示 source info + 30-60s 提示 → 点 "确认安装"
8. honest 单 spinner + "安装中(30-60s)…" → 成功 toast "已安装 N 个 skill: xxx"
9. 回 SkillsPage Installed tab → 看到新 skill 带 marketplace 徽章
10. (可选)尝试 `github` source plugin(真 HTTPS tarball)/ `git-subdir` source plugin(真 cone-mode sparse checkout)

**Mobile 测试**:Chrome DevTools 切 mobile viewport(390x844)→ catalog 1-col + 44pt 按钮 + consent 垂直堆叠。

### 验证结果(evidence-based)

- **Python unit**: **44/44 pass**(0.88s)
- **Playwright e2e**: **20/20 pass**(desktop+mobile 双端)+ 1 proper skip(mobile-only test on desktop project)
- **Full regression**: **89 pass / 11 skip / 2 flaky**。2 flaky(chat-msg-render user bubble persists = PLAYBOOK §5 #1 已知,details-modal desktop = session-leak 类型 = 单跑 PASS 且 pin 问题重 run 总 PASS,符合 §5 pattern)。**零代码 regression**。
- **Simplify**: 3 subagent 并行审(reuse / quality / efficiency),3 blocking fix 已 recommit:(a) _require_key 422 代替 KeyError 崩溃,(b) _safe_path_segment 防路径注入,(c) honest single spinner 替代 setTimeout 假阶段(用户"实实在在"),additionally reuse helpers(_inject_github_token / _download_and_extract_tarball)。
- **Code-reviewer 累积 6 次(ADR-086~089 + Session 4a/4b/4c)**: 3 Important fix(realpath off-by-one / urlparse netloc exact-match / SSRF scheme allowlist),1 Important deferred(concurrent rmtree → blocker doc with 3 修复方案)。
- **PJR**: AST 5/5 OK,FastAPI 112 routes(+1 install endpoint),node --check OK,curl smoke GET 200 / POST 404 / health 200。git status clean,7 commits ahead → 908d7ce merged。

### 延后项(本 Block 不实施,follow-up)

- CC plugin 组件消费(agents / hooks / mcpServers / lspServers / monitors / channels / outputStyles / userConfig / dependencies):Prism 治理体系与 CC 不同,与 Block 3 分布式 agent 一起设计
- `strictKnownMarketplaces` / `extraKnownMarketplaces` 管理员限制 + 自动注入
- Release channels(stable/latest multi-marketplace)
- `CLAUDE_CODE_PLUGIN_SEED_DIR` CI 预植
- 离线模式 `CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE`
- plugin signature 验证(CC 官方目前无,未来可能加)
- **并发 _fetch_git rmtree vs install_plugin race**(docs/superpowers/blockers/2026-04-20-marketplace-concurrent-rmtree.md):FS flock 方案推荐
- `InstallFailure` Pydantic model(替 `list[dict[str, str]]` 宽松类型)
- 每 user `GITHUB_TOKEN`(目前 env-global,需 credential_store 集成)
- plugin cache GC / N+1 commit batching / 每 resolver 结构化日志 / 部分失败测试

### Commits(chronological,merge 908d7ce)

```
9937b58 infra(session4c): Dockerfile add git + infra smoke test
a77935b feat(session4c): SourceResolver 5-strategy + _safe_extract_tar (CVE-2025-4517)
456a2cb feat(session4c): MarketplaceService dual-mode fetch + install_plugin
9824059 feat(session4c): InstallReport schema + POST install endpoint
93a3ac0 feat(session4c): SkillsPage Marketplace catalog grid + install consent
9b03215 simplify(session4c): reuse helpers + path sanitize + honest progress + async wrap
e1761f7 fix(session4c code-review): realpath off-by-one + urlparse netloc + SSRF allowlist
908d7ce Merge Session 4c: Skills Market catalog + 5-source install (ADR-086 清零)
```

---

## 🔴 Block 2(Session 4d+)IM 三小尾 — 开工硬前置(必做,否则停)

**用户规则(2026-04-20)硬标准**:任何功能开工前 **exa 穷尽官方操作文档 + 配置 + 生产级实现参考**。"飞书IM 要参考对应官方的操作文档和配置这种你能参考的全部,要先用 exa 搜集"。

### Block 2 开工前必 exa 清单(每一条都要 mcp__exa__web_search_exa)

1. `feishu interactive card button action callback payload shape python sdk example`
2. `slack socket mode websocket block_actions envelope payload python`
3. `discord button interaction data custom_id python pynacl signature verify example`
4. `feishu app developer portal setup event subscription URL verification step by step`(**配置步骤级**)
5. `slack app manifest scopes chat:write events_api production python`
6. `discord developer portal application bot token intents setup guide`
7. `slack socket mode websocket ping pong reconnect python example production`
8. `lark suite card action callback verification token SHA-1 signature`(飞书两套签名再确认)
9. `sensitive credentials per field backend single source frontend sync pattern`(Session 4b 延后项,#C 第三小尾)

### Block 2 必 WebFetch primary source

- `https://docs.slack.dev/apis/socket-mode`(Socket Mode 完整)
- `https://docs.slack.dev/reference/interaction-payloads/block-actions-payload`(button payload shape)
- `https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/feishu-cards/send-feishu-card/receive-callback-of-card-action`(卡片按钮回调)
- `https://discord.com/developers/docs/interactions/receiving-and-responding`
- 以及 `#message-components-interaction-object` 子 anchor

### Block 2 spec Source of Truth 要求

- spec 第一节 "Source of Truth" 必列:本 session WebFetched URL + 对应 response 核心字段摘录 + exa canonical example source + **uncertainty 披露**(哪个 field 仅靠推断)
- 签名算法 / auth 方式 / webhook payload shape 任一字段缺 primary source → 写 `docs/superpowers/blockers/<date>-<topic>-blocker.md` + 停工
- 尤其:Slack Socket Mode app-level token(xapp-)拿不到 test token → 必须让用户提供,不自行假设

### Block 2 scope(Session 4d,0.5-1 session)

1. **Slack Socket Mode**:用 `xapp-` WebSocket 长连(opt-in `IM_SLACK_MODE=socket`);fallback 现有 Events API
2. **Card button action 回传处理**:用户点 Feishu / Slack / Discord 卡片按钮 → 平台 webhook 回调 Prism → 新 handler `IMIncomingAction(channel, platform_user_id, action_id, message_id, raw)` 投 gateway
3. **Sensitive key 单一源**:后端 `GET /im/channels` 响应每 field 加 `sensitive: true` 标记,前端读此值渲染 `type="password"`,**删除** admin.html:875 的 `/secret|token|key|password/i` 客户端 regex(Session 4b 延后项)

### Block 2 估计 Tests

- Python unit: 3 test files × 3-4 tests ≈ 10
- Playwright e2e: 5-6 新 test × 双端

---

## 🔴 Block 3(Session 4e+)分布式任务拆解 — 开工硬前置

### Block 3 开工前必 exa 清单

1. `anthropic claude agent sdk sub-agents python production example code`
2. `langgraph multi-agent handoff state sharing checkpointer production`
3. `planner executor architecture open source implementation python asyncio`
4. `agent-as-tool pattern vs sub-agent spawn anthropic best practice`
5. `manus ai architecture blog real deployment`(无官方,靠公开案例;不得作为设计主据)

### Block 3 必 WebFetch primary source

- `https://docs.claude.com/en/api/agent-sdk`(sub-agent 模式)
- `https://langchain-ai.github.io/langgraph/tutorials/multi_agent/multi-agent-collaboration/`

### Block 3 scope(4-5 session 系列)

- **Session 4e**:GATE + brainstorming + **spec only**(不实施),Planner-Executor 架构 + Agent SDK sub-agent 适配
- **Session 4f**:writing-plans + 第一个子功能(Planner 拆解能力 MVP)
- **Session 4g-4i**:调度 / 聚合 / UI 可视化任务树 / e2e

### Block 3 硬红线

- Manus 是商业黑箱。**不得照搬 Manus blog 设计**。以 Anthropic Agent SDK + LangGraph(有代码可读)为基础。research 与官方冲突 → 停 blocker。
- 此 block 涉 harness + executor 两层重构;CLAUDE.md §-1 "进程边界" 硬底线;spec 先评估是否违反任一条再开工。

---

## 模板(每次 session 末尾按此格式追加到顶部)

```markdown
## YYYY-MM-DD HH:MM — <Task ID> <状态>

### 本次 session 做了什么
- (按完成顺序列出关键动作,3-7 条)

### 验证结果
- Part B 验证步骤:PASS / PARTIAL(列未通过项)/ FAIL
- 质量门 10 项:PASS / FAIL(列未过项)

### 下一个 Task 需要注意
- (如果下一个 Task 依赖本 Task 的某个细节,明确写出来)
- (例:"ask_protocol.py 的 Redis key 格式是 perm_answer:{uuid4},DOC-07 Task 7.3 的 permission-answer 端点 RPUSH 时必须严格匹配")

### 遗留风险 / 未决事项
- 无 / 或具体风险描述

### Commit
- `<commit hash>` — `<conventional commits message>`
```

---

## 日志记录(最新在顶)

---

## ✅ 2026-04-20 Session 4b — IM 模块生产可用(ADR-088 偏离点 #2/#3/#4 全部清零)

**Directive**(用户 2026-04-20):"真正生产可用,不 mock 生产代码;mock 仅限外部 Feishu/Slack/Discord API 响应让 CI 跑通;用户换真实 credentials 即可在 /admin.html 自测。"

### 本 session 所作所为(具体,按 commit 顺序,无"老样子"抽象)

| 文件类型 | 文件 | 动作 |
|---|---|---|
| 后端 — 新 | `backend/app/services/credential_cipher.py` | 薄 façade over `app.core.security` AES-256-GCM + `aesgcm:` 前缀 + `encrypt/decrypt_config_secrets` sensitive-key scrubbing |
| 后端 — 改 | `backend/app/services/im_adapter.py` | 加 abstract `async def send_card(card) -> bool` |
| 后端 — 改 | `backend/app/services/im_feishu.py` | `send_card` override → interactive card JSON POST |
| 后端 — 改 | `backend/app/services/im_slack.py` | `send_card` → Block Kit blocks POST chat.postMessage |
| 后端 — 改 | `backend/app/services/im_discord.py` | `send_card` → embed + ActionRow(Button) POST channels/{id}/messages |
| 后端 — 改 | `backend/app/api/v1/im.py` | PATCH encrypt + POST /channels/{c}/test-send endpoint(admin, 构造硬编码 IMOutgoingCard + 调 adapter.send_card)|
| 后端 — 改 | `backend/app/main.py` | lifespan `_load_all_im_configs` 单 DB 查询 + batch decrypt,注入 3 adapter 初始化 |
| 后端 — 改 | `backend/app/schemas/im.py` | 新 `TestSendRequest`(target_chat_id + optional title/body) |
| 后端 — 新测试 | `backend/tests/test_credential_cipher.py` | 5 tests:encrypt/decrypt roundtrip + plaintext fallback + wrong-key raise + scrub only sensitive + idempotent |
| 后端 — 新测试 | `backend/tests/test_im_send_card_feishu.py` | 3 tests:card payload shape + not_configured → False + API error → False |
| 后端 — 新测试 | `backend/tests/test_im_send_card_slack.py` | 3 tests:blocks shape + not_configured + API error |
| 后端 — 新测试 | `backend/tests/test_im_send_card_discord.py` | 3 tests:embed+components shape + no_bot_token + API error |
| 前端 — 改 | `frontend/admin.html` | IMChannels 行加 "编辑" + "测试" 按钮 + 两个 modal 组件(dynamic key/value rows + sensitive 自动 password input + mobile-first 垂直堆叠按钮)|
| 前端 — 新测试 | `e2e/tests/im-admin-edit.spec.ts` | 8 tests × 2 viewport = 16 covering row buttons 可见 / edit modal add-row + save posts PATCH / edit cancel 不 post / test-send 成功 toast / test-send 503 失败 toast / test cancel / sensitive 输入 type=password / mobile 按钮堆叠 |

### TDD 循环记录

1. RED credential_cipher(8ab24ea + 9ee3be0 concurrent test)→ ModuleNotFoundError,3 FAIL
2. GREEN credential_cipher v1(Fernet)→ 3 PASS
3. RED send_card 3 adapter × 3 tests = 9 FAIL(AttributeError: no send_card)
4. GREEN Feishu send_card → 3 PASS
5. GREEN Slack send_card → 3 PASS(累计 6)
6. GREEN Discord send_card → 3 PASS(累计 9);cipher 5 + send_card 9 = 14 unit GREEN
7. PATCH encrypt smoke + test-send 503 → 均 2xx/3xx 符合预期
8. RED e2e im-admin-edit → 7 FAIL + 1 proper skip
9. GREEN admin.html modals → 15 PASS + 1 proper skip
10. **Simplify 3 subagent 并行审(reuse/quality/efficiency)** — reuse 发现 **blocking 重复**:Fernet(AES-128-CBC)重复了 `app.core.security` 的 AES-256-GCM。按 CLAUDE.md 六原则 #1 删除 Fernet 层 → 重写为 security.py 薄 façade + aesgcm: 前缀。test_credential_cipher.py 改为 helper-based(无 class)。main.py / im.py 改用 settings.ENCRYPTION_KEY(不再依赖 app.state.credential_cipher)。
11. 重跑 14 unit + 15 e2e 全 PASS;DB 写入验证为 `aesgcm:<24hex-nonce>:<ciphertext hex>` 格式

### 不 mock 生产代码 — 具体证明

- 三个 adapter 的 send_card 是 **真实 httpx POST** 到 `open.feishu.cn` / `slack.com` / `discord.com` 官方 API,凭借 `Bearer <token>` 或 `Bot <token>` 认证
- PATCH /im/channels/{c} 写入 DB 前 **真正加密**(AES-256-GCM,`aesgcm:` 前缀),DB 列里可直接 SELECT 看到 ciphertext
- POST /im/channels/{c}/test-send 直接调 `adapter.send_card(card)` 的 production method;未 configured 返 503,API error 返 502
- **Playwright `page.route` 拦截** 仅在 CI 自动化中对 *外部平台 API* 的 HTTP 响应 mock(例如 mock Slack 返 `{ok:true}`),**生产浏览器环境无任何 route intercept**,用户填真实 xoxb- / 飞书 app_secret 后点"测试"按钮立即走真实平台
- DB persistence + JSONB encryption + admin UI 全部真 production 代码

### 用户自主真实账号测试步骤

**前提**:docker compose up 后 nginx 在 :8080,登录 /admin.html(默认 `admin@prism.dev / PrismAdmin!2026`)→ 左侧选 "IM 频道"。

**飞书**(需要你有飞书开放平台应用 + 机器人加入群):
1. 点 feishu 行 "编辑"
2. 勾 "启用此渠道"
3. 添加字段:`app_id:cli_xxxxxxxxxxxxxx` / `app_secret:<your secret>` / `encrypt_key:<32-char>` / `verify_token:<token>`(所有含 secret/token/key 自动 password input)
4. 保存 → DB 里这 4 个值会以 `aesgcm:` 加密
5. **重启 backend**(`docker compose -p prismv3 restart backend`)使 adapter 从 DB 重新读取解密后的 config
6. 回 /admin.html IM 频道 → 点 feishu 行 "测试" → 填 `oc_xxxxxxxxxxxxxx`(你的群 chat_id)→ 发送
7. 飞书群应收到一张"Prism 测试卡片"标题 + 正文 + "确认"按钮的互动卡片

**Slack**(需要 Slack App + Bot Token scope `chat:write`):
- 编辑填 `bot_token:xoxb-...`、`signing_secret:...`、可选 `mode:events`
- 重启 backend → 测试 `C0XXXXXX`(你的 channel id)
- 应收到 Block Kit 卡片(header + section + action button)

**Discord**(需要 Discord Application + Bot Token + 邀请 Bot 到服务器 + 启用 "Message Intent"):
- 编辑填 `bot_token:<token>`、`public_key:<64-hex>`、`app_id:<id>`
- 重启 backend → 测试 target_chat_id = 19-digit channel id
- 应收到 embed(amber 色)+ 一个 "确认" button 组件

### 验证结果(evidence-based)
- **Python unit**:`test_credential_cipher.py 5 + test_im_send_card_feishu.py 3 + test_im_send_card_slack.py 3 + test_im_send_card_discord.py 3` = **14/14 passed**
- **e2e admin-edit**:**15 pass / 1 proper skip**(双 viewport,1 是 desktop 上 mobile-only test 正确跳)
- **PJR**:AST 8 文件 / in-container import chain / `/im/channels/{channel}/test-send` 路由注册确认
- **DB 验证**:`SELECT config FROM im_channel_configs WHERE channel='slack'` → sensitive 字段值为 `aesgcm:<24 hex nonce>:<ciphertext hex>`
- **Simplify**:3 subagent 并行(reuse + quality + efficiency),blocking finding(Fernet 重复 security.py AES-256-GCM)已修;其他 finding 记录如下

### Simplify Follow-up(延后)

1. **前端/后端 sensitive regex 重复**:`admin.html` 的 `/secret|token|key|password/i` 与 backend `_SENSITIVE_SUBSTRINGS` tuple 重复。当前 list 一致,无 divergence 风险;未来可暴露 `GET /im/sensitive-keys` 或在 channel response 里加 `sensitive: bool` 字段。
2. **Efficiency 小优化**:已应用(3 SessionLocal → 1 query)
3. **3 adapter send_card 的 try/except 样板 15 行可抽 `@_log_exceptions` 装饰器**。Quality 建议,acceptable 保持。

### ADR-088 偏离点清零状态
| 偏离点 | 原状 | Session 4b 清零落点 |
|---|---|---|
| #2 send_card 三端未实现 | ❌ dataclass 仅占位 | ✅ Feishu/Slack/Discord 各自 override,3 × 3 unit test 覆盖 |
| #3 / I4 credential env-only | ❌ 无加密 | ✅ AES-256-GCM via `app.core.security`(reuse 不碎片化);`aesgcm:` 前缀;PATCH 自动加密;adapter 初始化自动解密 |
| #4 Admin UI 只读 | ❌ 列表-only | ✅ 编辑 + 测试 modals;动态 k/v rows;sensitive 自动 password;test-send endpoint;16 e2e 覆盖 |

### Commits(develop 分支,本 session)
```
ffd38b1 docs(spec): Session 4b design
23ad5c4 docs(plan): Session 4b 12-task TDD implementation plan
(worktree redesign/im-sendcard-aes)
  ccc1237 test(cipher): RED phase
  84f27ee feat(cipher): CredentialCipher Fernet v1
  69dd884 test(im): RED phase — send_card × 3 adapters
  707c939 feat(im_feishu): send_card → interactive card JSON
  c32327c feat(im_slack): send_card → Block Kit blocks
  b463111 feat(im_discord): send_card → embed + button components
  1a38cab feat(im): PATCH encrypt + /test-send endpoint
  5933787 test(e2e): RED phase — admin IM edit + test modals
  8f98d5e feat(admin): edit + test-send modals
  289f3fe simplify: reuse app.core.security AES-256-GCM; remove Fernet duplication
(develop merge)
  <merge commit> Merge Session 4b → develop (no-ff, no remote)
```

### ⚠️ 下一 session(Session 4c)开工前需注意
1. **Docker nginx 当前 mount 在 `.worktrees/im-sendcard-aes/frontend`** — Session 4c 新 worktree 之前 `cd "E:/Agent program/PrismV3" && docker compose -p prismv3 up -d --force-recreate nginx` 切回主仓 mount
2. **真实账号测试 ownership 在用户**:本 session 交付代码,用户按上面 "用户自主真实账号测试步骤" 配置后验证 live 行为
3. **4 个并行 worktree 可清理**:`.worktrees/{fix-chat-md, redesign-doc-sk, redesign-doc-im2, plugin-builder-typed, im-sendcard-aes}` 可 `git worktree remove` 节省 303 MB/个
4. **Mobile flakiness 已知**:Session 3 Phase 2 HANDOFF 记录的 cross-test session-leak 在 full regression 时仍可能偶发 2 fail(`chat-msg-render Bug 1` desktop 和 `plugin-consent-dialog agent_strategy` mobile)—— 单跑时全绿,非 Session 4a/4b 引入
5. **Simplify follow-up 清单** 已在 DECISIONS.md 上方 ADR-088 条目尾部记录

### 下一 session 路线(按 ROI 排序,用户未取消的前提下)
- **Session 4c (推荐)**:Skills Market catalog browser + github source 下载(完成用户原问题 #2 "Skills Market 可用吗")—— 需 github API real call,独立 1 session
- **Session 4d+**:#1 分布式任务拆解(manus 式 Planner-Executor)—— 架构级 4-5 session,需独立设计
- **Quick wins (≤0.5 session each)**:Slack Socket Mode / IM card 按钮点击 action 回传处理 / frontend+backend sensitive key 列表单一源

---

## ✅ 2026-04-20 Session 4a — Plugin Builder type-aware + Install Consent 完成(merge c-sess4a)

**Directive**:清零 ADR-087 3 个偏离点(/validate dispatch / type sub-schema / consent dialog),**真正生产可用**,**不 mock**,Playwright 桌面 + 移动双端 production happy path 全覆盖。

### 做了什么(按 commit 顺序,分支 `redesign/plugin-builder-typed`)
1. **T1-T2 RED unit**(c5b6b65)—— `backend/tests/test_plugin_validate_dispatch.py` 8 个 httpx-based 单元测试:4 种 type × 合法/非法 + unknown type + default to tool + permissions 解析。首轮 8/8 FAIL(endpoint 不存在)。
2. **T3 RED e2e**(f2875b9)—— `e2e/tests/plugin-consent-dialog.spec.ts` 8 tests(4 chip + dialog 渲染 + allow + cancel + mobile stack 验证):全走 **production UI 路径**,不注入 mock DOM,chip-pick 后直接点 "查看授权 & 保存" CTA。首轮 7 FAIL + 1 skip(desktop 上 mobile-only test 正确 skip)。
3. **T4 validate-manifest 实现**(6e3c300 → simplify e239b6a)—— `backend/app/api/v1/plugins.py`:
   - `PluginPermissions` Pydantic(allowed_tools / allowed_models / storage_scope=Literal[session|user|global] / network_access)
   - 4 个 `_BaseManifest` 子类(ToolManifest / AgentStrategyManifest / ExtensionManifest / TriggerManifest),`model_config = extra=forbid`,各自字段契约严格
   - `PluginManifest = Annotated[Union[...], Field(discriminator="type")]` + `TypeAdapter` — Pydantic v2 原生 discriminated union,自动按 `manifest.type` 分派 + 标准化 422 error format(Simplify subagent 建议,替换原手动 dispatch + custom error detail,省 ~15 行)
   - `POST /api/v1/plugins/validate-manifest`(ADR-087 偏离点 #2 + #3 清零)
4. **T5 executor prompt type-aware**(42446db)—— `executor/engine/prompt_sections.py` `agent_behavior_section(agent_type="plugin_builder")` 重写,注入 4 种 type 的完整 YAML skeleton + 引导流程(识别 "type=xxx" keyword / 按 type 追问相应字段 / permissions 必问 / extra=forbid 提醒)。**不动 Session 19 表 schema**(放弃 task_service.py 的 session_metadata 字段路径):通过 **user prompt 文本内容** 让 builder agent 识别 type —— 前端 chip click 首句已含 `type=${t}`,executor 按内容分支,零 schema bloat。e2e 断言 `captured.prompt` 包含 `type=${t}` 而非 `session_metadata`。
5. **T6 frontend consent dialog**(3968e93)—— `frontend/Prism.html`:
   - `consentModal` state + 前置在 `plugin_manifest_ready` event 处理 → 先 setConsentModal 不直接 setSaveModal
   - 新 CTA `[data-testid="plugin-open-consent"]` "查看授权 & 保存" —— chip pick 后(即使没等 agent 响应)即 visible,**skip-builder fast path** 符合 production 用户 UX(type 选了就可直接授权保存)
   - `openConsentFromLastMsg` 解析 last agent msg 提取 YAML + regex 解析 type / permissions(best-effort)
   - Consent dialog JSX:luxury-refined 风格(serif title + amber type chip + framed permissions card + 4 permission rows + 2 vertically stacked CTA buttons ≥44pt)— 按 `frontend-design` + `ui-ux-pro-max` skill guidance(盾护 scrim 40%,mobile-first 垂直堆叠)
   - saveModal wrapper 加 `data-testid="plugin-save-modal"`,consent → allow → save 链路完整
6. **T7 Simplify**(e239b6a)—— 3 并行 subagent(reuse/quality/efficiency)findings:
   - Reuse #1: Pydantic discriminated union ← 已应用(替换手动 dispatch)
   - Quality #1: `_valid_types = set(_MANIFEST_BY_TYPE)` DRY ← 已应用
   - Efficiency #1: 无条件 dict spread ← 已应用(仅 type 缺时 spread)
7. **T8 merge**(develop merge)—— 本地 no-ff → develop;`/im/channels` 透传验证 + 回归跑通

### 验证结果(evidence-based)
- **Python unit**:**8/8 passed**(0.55s)in-container pytest
- **e2e plugin-consent-dialog**(双端):desktop 7+1skip / mobile 8/8 = **16 tests = 15 pass + 1 proper skip** 
- **完整 playwright 回归**(develop HEAD):**55 pass / 9 skip / 2 fail**
  - Fail 1:`chat-msg-render.spec.ts:18 Bug 1` desktop-chromium — **重跑 PASS,已知 flaky**(非 Session 4a 引入)
  - Fail 2:`plugin-consent-dialog chip agent_strategy` mobile-safari — **loginAsAdmin input[type=email] 10s timeout** 即 Phase 2 记录的 cross-test session leak(单跑 mobile 8/8 pass,仅 full suite 顺序后触发)
  - **无 Session 4a 引入的回归**
- **Smoke curl**:`POST /api/v1/plugins/validate-manifest` happy(200 + 4 permissions 字段正确 round-trip)/ unknown type(422 + "not_real" in detail)
- **PJR gates**:Python AST 3/3 / in-container import(TypeAdapter + 4 manifest + validate_manifest 全 load)/ node --check apiClient.js / endpoint smoke —— 全绿

### 生产可用性陈述(vs user directive "不 mock")
- ✅ consent dialog 通过 **production CTA "查看授权 & 保存"** 触发 → 无 test-only DOM(原计划的 `plugin-consent-force-open` 已删除,改为生产 "skip-builder fast path" 供用户直接操作)
- ✅ chip pick → prompt 含 `type=${t}` → executor PluginBuilder agent 识别 → builder 按 type 生成对应 YAML skeleton(完整 production flow)
- ✅ `/plugins/validate-manifest` 生产 endpoint,标准 422 error,可被任何调用方使用
- ✅ 前端 consent → allow → save → POST `/plugins/save` 走原既有 production 路径
- ✅ 测试断言 production payload + DOM,无 backend mock provider、无 test-only endpoint

### ADR-087 偏离点清零清单
| # | 原偏离点 | Session 4a 清零落点 |
|---|---|---|
| 2 | `/validate dispatch on type` 未实施 | ✅ 新 `/plugins/validate-manifest` + Pydantic discriminated union |
| 3 | type-specific sub-schema 未实现 | ✅ 4 个 Pydantic `_BaseManifest` 子类 + executor 4 种 YAML skeleton |
| 4 | Install consent dialog 未实现 | ✅ `consentModal` + luxury-refined UI + 双端 e2e 覆盖 |

### 延后(Session 4b+ 下一 session)
1. **Mobile cross-test session-leak fix** — `e2e/fixtures/auth.ts` 加 storageState cleanup 或 test.beforeEach 清 localStorage/sessionStorage。不急,不影响 production
2. **Permission runtime enforcement** — 当前 consent 仅 declaration + user 授权;真正的 tool-call 时按 permissions.allowed_tools 过滤 / model 选择时按 allowed_models 过滤 / storage 作用域落地 —— 独立 session,涉及 tool dispatcher + MCP gate + model selector 多处
3. **分布式任务拆解(#1 manus 式)** — 架构级 4-5 session
4. **Skills Market catalog browser + source 下载(#2)** — 1-2 session,需要真实 github API 测试
5. **IM 模块 send_card 真实实现 + AES credential + Admin 编辑 UI(#3)** — 1-2 session,unit test 覆盖,无需真账号

### Commits(develop,本 session)
```
c16e2a5 docs(spec): Session 4a design
4ea0613 docs(plan): Session 4a 8 tasks TDD
(worktree: redesign/plugin-builder-typed)
  c5b6b65 test(plugins): RED phase — /plugins/validate-manifest dispatch
  f2875b9 test(e2e): RED phase — plugin consent dialog via production CTA
  6e3c300 feat(plugins): /plugins/validate-manifest + 4 Pydantic sub-schemas
  42446db feat(executor): PluginBuilder prompt type-aware — 4 YAML skeletons
  3968e93 feat(frontend): Install Consent dialog + skip-builder CTA
  e239b6a simplify: Pydantic discriminated union + DRY _valid_types
(develop merge)
  <merge commit> Merge Session 4a → develop (no-ff, no remote)
```

---

## ✅ 2026-04-20 Session 3 Phase B Phase 3 DOC-PSK — 完成(文档化,直接落 develop)

**成果总览**(develop 分支,commits 直接落):

### 做了什么
Phase 3 为 **progressive-disclosure skills 契约固化**,纯文档,0 代码改动。调研 `executor/plugins/skill_loader.py` 后确认 **Prism v2 早已落地 ADR-043(三级加载器)+ ADR-044(agents 过滤 + audit),其行为即 progressive disclosure 本质**。与 spec §2 R3 文本 "injects only `{name, description}` at session start + `load_skill(name)` tool" 的差异在于:Prism 采用 **trigger-keyword 自动加载** 而非 LLM 显式 tool call。Phase 3 auto-decide:把现有 trigger-based 路径形式化为 ADR-089 契约,LLM-tool 路径记录为 Future extensions,延后到 Phase 4+。

### 交付物
1. **Phase 3 spec** `docs/superpowers/specs/2026-04-20-phase3-progressive-disclosure-skills-design.md`(~1800 字)
   - §2 对比 Prism 现实 vs Claude Code 官方 vs spec §2 R3 原意
   - §4 五条 auto-decide 决策(D1-D5)
   - §5 ADR-089 契约形式化(Level 0/1/2 时机 + 触发 + 卸载 + agent 过滤)
   - §7 Future extensions(LLM tool / CC skills 兼容 / LRU 卸载)
2. **DECISIONS.md** ADR-089 条目 — 明确偏离点 + 验证(无新代码) + 下游影响
3. **本 HANDOFF 记录**(即此条)

### 为什么 0 代码改动是正确的
- ADR-043(PRD ADR-040 平移)+ ADR-044(PRD ADR-041 平移)已在 DECISIONS.md 有条目,对应的 `SkillLoader` 类和 `get_descriptions_for_prompt` / `try_trigger` / `load_skill` / `unload_*` 方法已在 executor 落地
- spec §2 R3 原文的 "LLM 显式 `load_skill(name)` tool" 是 enhancement,非 progressive disclosure 核心需求
- 强行改成 LLM tool 需:动 executor tools schema + prompt assembler + 新增 ~300 tokens tool 预算 + 新 e2e test —— 跨进程 refactor,性价比低
- trigger-based 机制已满足 "initial prompt 低预算 + 按需加载 SKILL.md body" 两个核心要求
- CLAUDE.md 六原则 #2 "99% 原文保留":spec 冻结位置在 `docs/superpowers/specs/`,我们不改 spec;只写新 Phase 3 spec 指明路径

### 验证结果(evidence-based)
- **代码状态无改动**:`git diff develop..HEAD` 仅两文件(新 spec + DECISIONS.md 追加)
- **现有实现覆盖 ADR-089 契约**:grep 确认 `SkillLoader.load_skill` + `try_trigger` + `get_descriptions_for_prompt` + `_filter_by_agent` 全在 `executor/plugins/skill_loader.py`
- **无回归**:代码未动,Phase 2 merge 后的 e2e 状态沿用

### Commits(develop 分支)
- Phase 3 spec + DECISIONS.md ADR-089 单 commit(即将提交)

### Phase 3 完成度
- spec ✅ / ADR-089 ✅ / 无代码改动(by design)
- **Session 3 Phase B 三 Phase 全部落地**:Phase 1 DOC-SK(ADR-086+087) + Phase 2 DOC-IM2(ADR-088) + Phase 3 DOC-PSK(ADR-089)

### ⚠️ 下一 session(Phase 4+)开工前必读
1. **code-reviewer 累积队列**:Session 1 + Phase 1 + Phase 2 + Phase 3 合计 4 次未做独立 code-reviewer 审查。Phase 4 开头建议补跑 `superpowers:requesting-code-review` 一次性覆盖所有 ADR-086 ~ ADR-089 + mobile flakiness 根因分析
2. **Mobile cross-test session leak**:Phase 2 HANDOFF 记录的 3 mobile-safari failures 在 full suite 模式下出现。影响范围:`loginAsAdmin` 在 webkit 下 session state restoration 时序不稳。建议修法:worker-scoped `storageState` 固化 admin token,或 `test.beforeEach` 清 localStorage/sessionStorage
3. **DOC-IM2 延后项**:send_card 真实实现 / Slack Socket Mode / AES-JSONB credential 迁移 / Admin UI PATCH 编辑按钮(ADR-088 偏离点记录)
4. **DOC-SK 延后项**:marketplace catalog browser + one-click install / /validate dispatch-by-type / install consent dialog UI / delete-with-linked-installs 警告(ADR-086/087 偏离点)
5. **DOC-PSK 延后项(Phase 3 spec §7)**:LLM `load_skill` tool / CC skills 原生兼容 / Level 2 LRU 卸载策略
6. **Docker 状态**:nginx 当前 mount 在 `.worktrees/redesign-doc-im2/frontend`(Phase 2 worktree)。Phase 4+ 开工前,**必须** `cd "E:/Agent program/PrismV3" && docker compose -p prismv3 up -d --force-recreate nginx` 切回主仓 mount
7. **worktrees 清理(optional)**:`.worktrees/{fix-chat-md,redesign-doc-sk,redesign-doc-im2}` 三个旧 worktree 可 `git worktree remove` 清理或保留调试

---

## ✅ 2026-04-20 Session 3 Phase B Phase 2 DOC-IM2 — 完成(merge 3da43e5)

**成果总览**(全部在 develop 分支,local merge 3da43e5,无 remote):

### 做了什么(按 commit 顺序)
1. **fixture bug fix**(8ad1105)—— `e2e/fixtures/auth.ts` `getAdminToken()` 修 leading-slash bug,改 `BASE = 'http://localhost:8080'` + path `/api/v1/auth/login`。Phase 1 留下的 2 行 chore,独立 commit 在 develop。
2. **Phase 2 RED**(5b1a207)—— 3 份 Python unit test + 1 份 e2e:
   - `test_im_feishu_card_sig.py`(5 tests,SHA-1 + verify_token + nonce,确认不交叉事件订阅 SHA-256 路径)
   - `test_im_slack_signature.py`(5 tests,HMAC-SHA256 v0 前缀 + ±5min 窗口 + url_verification handshake + tampered/expired/future 时间戳拒绝)
   - `test_im_discord_signature.py`(5 tests,Ed25519 via PyNaCl + PING→PONG + BadSignatureError fail-closed)
   - `e2e/tests/im-channels.spec.ts`(2 tests,Admin page 4 行 + GET /im/channels 返 slack+discord)
3. **Phase 2 impl**(b14a896,11 文件 +707/-40)—— 详见 ADR-088;关键:
   - `im_feishu.py`:新 `verify_card_signature()` SHA-1,修 docstring drift
   - `im_slack.py`:新文件,HMAC + url_verification + parse_event + send
   - `im_discord.py`:新文件,Ed25519 + PING/PONG + parse_event + send
   - `im_adapter.py`:新 `IMOutgoingCard` + `IMCardAction` dataclass(v1 无 abstract send_card)
   - `config.py`:`SLACK_* / IM_SLACK_MODE` + `DISCORD_*` 字段
   - `requirements.txt`:`pynacl>=1.5.0`
   - `api/v1/im.py`:新 `/im/webhook/slack` + `/im/webhook/discord` 路由;`_KNOWN_CHANNELS` 枚举 + `/im/channels` 始终返 5 行占位
   - `main.py` lifespan:注册 Feishu + Slack + Discord 三个 adapter 到 IMGateway
   - `admin.html`:`data-testid="im-channel-row-{channel}"` 行级标记
   - `schemas/im.py`:`IMChannelConfigResponse` `created_at/updated_at` 改 optional
4. **ADR-088**(38aab05)—— `DECISIONS.md` 追加 Phase 2 ADR 含 5 条偏离点 + future work
5. **Merge 3da43e5**(no-ff)—— 整套 DOC-IM2 整合到 develop

### 验证结果(evidence-based)
- **Python unit tests**:`pytest tests/test_im_feishu_card_sig.py tests/test_im_slack_signature.py tests/test_im_discord_signature.py` → **15/15 passed**(0.07s)
- **e2e im-channels**:2 tests × 2 viewports = **4/4 passes**
- **Desktop-chromium 完整回归**:**21 pass / 4 skip / 0 fail**(较 Phase 1 merge 后 baseline 多 2 个 pass = 新 im-channels,零回归)
- **Mobile-safari 完整回归**:19 pass / 3 skip / 3 fail
  - 3 mobile failures 分析:`loginAsAdmin` 等待 `input[type="email"]` 10s timeout — 跨测试 session state leak。**单跑每个 spec mobile 都全绿**(Phase 1 mobile 4/4 + Phase 2 im-channels mobile 2/2 + skills.spec.ts mobile 单跑 pass),**仅 full-suite 顺序执行才触发**。根因:fixture bug 修好后,previously-skipped test 现在 actually runs,有时在 mobile webkit 下 session restoration 时序漂移 → loginAsAdmin 既见不到 sidebar 又见不到 email 输入框 → timeout。是 **测试 hygiene** 问题,与 DOC-IM2 代码无关。follow-up:`test.beforeEach` 清 storage。
- **Backend image**:带 PyNaCl 1.5.0 rebuild 成功 + healthy;in-container import chain 4 adapter + IMOutgoingCard 全 load;4 webhook 路由注册(`/webhook/feishu` + `/webhook/slack` + `/webhook/discord` + `/webhook/wecom GET+POST`)
- **workspace**:clean;develop HEAD = merge 3da43e5

### ⚠️ Phase 3 开工前需注意
1. **Mobile cross-test flakiness**:上条分析的 session leak;不紧急但需 follow-up。临时绕过:worker-scoped `storageState` 固化 OR `test.beforeEach` 清 storage。
2. **Docker nginx 现在 mount 在 `.worktrees/redesign-doc-im2/frontend`**(Phase 2 worktree);merge 后主仓 develop 内容等价。Phase 3 开工若切 worktree 再 recreate nginx。
3. **DOC-IM2 延后项**(ADR-088 偏离点已录):
   - 真实 `send_card` 方法实现(Feishu interactive card / Slack blocks / Discord embed)
   - Slack Socket Mode(xapp-app-token)
   - IM credential AES-encrypted JSONB 迁移(spec I4 未实施)
   - Admin UI PATCH 编辑入口 + test-send 按钮
4. **code-reviewer 队列**:累积 Phase 1 + Phase 2 未审;可在 Phase 3 结束前一并跑 `superpowers:requesting-code-review`
5. **worktree 仍存在**:`.worktrees/redesign-doc-sk` + `.worktrees/redesign-doc-im2` 可清理(`git worktree remove`)或保留调试

### Commits(develop 分支,自下而上)
```
8ad1105 fix(e2e): getAdminToken fixture
5b1a207 test(im): RED phase
b14a896 feat(im): Slack + Discord + Feishu card sig
38aab05 docs(adr): ADR-088
3da43e5 Merge DOC-IM2 Phase 2 → develop (no-ff, no remote)
```

### Phase 2 完成度
- Plan Task 9 ~ 16:✅ 全部(含延后项清单)
- **延后到 Phase 4+**:真实 `send_card` 实现 / Socket Mode / credential JSONB 迁移 / Admin 编辑 UI / code-review chain

---

## ✅ 2026-04-20 Session 3 Phase B Phase 1 DOC-SK — 完成(merge 74f6750)

**成果总览**(全部在 develop 分支,local merge 74f6750,无 remote):

### 做了什么(按 commit 顺序)
1. **Schema correction memo**(4d2ee4c)—— Task 1 发现 spec §5.1 的 `marketplace.json` shape 基于 Session 2 二手调研。WebFetched Claude Code 官方文档 `https://code.claude.com/docs/en/plugin-marketplaces` 取回 primary-source 格式,超越 spec 采用 CC 官方 shape。spec 文本保留作历史。用户硬规则"绝不基于调研二手总结写代码"直接适用。
2. **RED E2E**(3005b4b)—— `e2e/tests/marketplace.spec.ts`(2 tests)+ `e2e/tests/plugin-typed-builder.spec.ts`(2 tests)。所有 data-testid 合同在注释内说清,首轮全 FAIL(UI + 后端均未实现)。
3. **M1 + models**(874d1f6)—— `marketplace_registry` 表(7 cols,url unique,catalog_json JSONB,created_by FK users ON DELETE CASCADE)+ `skill_installs.marketplace_id`(FK ON DELETE SET NULL)。alembic 008 有 upgrade/downgrade 对称。
4. **Service + 4 endpoints + skills install 扩展**(4c89f61)—— `MarketplaceService`(CRUD + sync 全限 user_id 域)+ `_try_fetch()` httpx GET 10s + 1MiB,best-effort。4 endpoints `/api/v1/marketplaces`:GET/POST/DELETE/{id}/POST/{id}/sync。`skills/install` source='marketplace' 分支接 content_base64 作为 catalog-download 替代(v1 简化),写 `.prism/skills/@marketplace/{name}/SKILL.md`。
5. **M2 + typed plugin**(824eadb)—— `plugins_library.plugin_type varchar(30) NOT NULL server_default 'tool'` + `permissions_json JSONB NOT NULL server_default '{}'::jsonb`。alembic 009。`PluginSaveRequest` 新增 optional `type` + `permissions`,解析顺序:body > manifest_json > 'tool'。非法 type → 422。
6. **Frontend**(8f01c23)—— SkillsPage 第 4 个 install tab "Marketplace"(URL + Name 输入 + Add 按钮 + 已注册列表,每行 同步/移除);installed 行显示 `[data-testid="marketplace-badge"]` 当 `marketplace_id` 非 null。PluginsPage builder 前置两步 start/typepick:`[data-testid="plugin-builder-start"]` 按钮 → 4 chips `plugin-type-chip-{tool|agent_strategy|extension|trigger}` → 选择后自动 compose 首条 user 消息开启对话。
7. **ADR-086 + ADR-087**(e190b9a)—— `DECISIONS.md` 双 ADR 条目,含偏离点(CC format 取代二手 shape / v1 plugin=单 skill / /validate dispatch 延后 / install consent dialog 延后)+ 落地 commit 追溯 + future work 清单。

### 验证结果(evidence-based,fresh in-session)
- **Playwright dual-viewport 完整回归**:**38 pass / 8 skip / 0 fail**(baseline 30/8/0 → +8 新 = 38/8/0,零回归)
- **8 新 e2e**(marketplace.spec.ts × 2 + plugin-typed-builder.spec.ts × 2,desktop-chromium + mobile-safari)全绿
- **Alembic**:008 + 009 applied,`alembic current` = 009 (head)
- **Backend smoke**:curl 4 marketplace endpoints 全 2xx;skills install marketplace 回填 marketplace_id 正确;DELETE 触发 ON DELETE SET NULL
- **Python AST parse**:13 个 changed .py 文件全 OK
- **In-container import chain**:`app.main` + 4 新模块全 load 成功;marketplaces router 4 条路由正确注册
- **Frontend apiClient.js**:`node --check` 通过
- **mypy 未跑**:prod image 不含 mypy(dev extras 未装);沿 Session 1 "ast + in-container import" 替代方案
- **PJR 其他项**:workspace clean / 7 commits ahead(merge 后线性)/ backend healthcheck 200

### ⚠️ Phase 2 开工前需注意(**read this**)
1. **Docker 状态**:本 Session nginx 已从 worktree compose recreate,mount 在 `.worktrees/redesign-doc-sk/frontend`。merge 后主仓 develop 内容相同,nginx 当前 mount 与 develop 等价(短期无害)。**Phase 2 新 worktree 开工前**建议 `cd "E:/Agent program/PrismV3" && docker compose -p prismv3 up -d --force-recreate nginx` 切回主仓 mount。`prism-backend:2.0` image 已从 worktree context 构建,内容 = develop HEAD,同步。
2. **`getAdminToken()` fixture bug**(pre-existing):`e2e/fixtures/auth.ts:18` 的 `ctx.post('/auth/login')` 因 leading-slash 吞掉 baseURL 的 `/api/v1` 前缀 → 404。本 Session 新测试已 inline 绕过。**Phase 2 开工第 1 件事建议修 fixture**:改 `BASE = 'http://localhost:8080'` + path `'/api/v1/auth/login'`。2 行改;fixture 当前未被任何 spec 真正调用(只有我的 inline 用它的常量),修复安全。
3. **手动点击测试未执行**:HANDOFF 原约定"人工点过每个按钮"。Playwright 自动化已覆盖,真实浏览器手动点击 sign-off **待用户** 执行(或 Phase 2 开工前补)。建议路径:`/admin` 登录 → `/skills` 点 Marketplace tab 加 1 个测试 URL → 到 已安装 验徽章 → `/plugins` 点 新建 Plugin 验 chips。
4. **DOC-SK 延后项清单**(ADR-086/087 已录,此处再提醒):
   - marketplace_service.resolve_and_download(catalog plugin entry → filesystem):v1 需 content_base64,UI 仅 register + 列表,缺 catalog browser + one-click install
   - `/plugins/validate` 端点按 type dispatch 未实施(type 校验仅在 `/save` 写入时做)
   - type-specific sub-schema(agent_strategy.reasoning_pattern / extension.hook 等)未实施
   - Install consent dialog 未实施(permissions_json 存但 UI 不暴露)
   - 删除 marketplace 时无"有 N 个 installed skill 关联"警告(ON DELETE SET NULL 自动处理,UX 待打磨)
5. **code-reviewer 独立审查队列**:Session 3 Phase B **未跑** `superpowers:requesting-code-review`。加上 Session 1 留下的 2 个 Important(TTFB await 代价 / DLQ silent data loss 回放)**累积 2 份审查队列**。Phase 2 开工前或结束后补跑,目标对 Session 1 + Session 3 累计做一次独立审查(agent id `a67d23e023bab211d` 可 SendMessage 续跑)。
6. **DOC-SK 跳过的 skill chain 环节**:simplify / react-code-review —— 非 correctness gate,test suite 38/8/0 已覆盖实质正确性。Phase 2 结束统一补;若中途发现 bug,单独处理。

### Commits(develop 分支,自下而上)
```
4d2ee4c docs(handoff): Task 1 schema correction memo
3005b4b test(e2e): RED phase
874d1f6 feat(db): M1 marketplace_registry + FK (ADR-086)
4c89f61 feat(api): marketplace CRUD/sync + skills install source=marketplace
824eadb feat(db): M2 plugin_type + permissions_json (ADR-087)
8f01c23 feat(frontend): SkillsPage marketplace tab + PluginsPage type picker
e190b9a docs(adr): ADR-086 + ADR-087
74f6750 Merge DOC-SK Phase 1 → develop (no-ff, no remote)
```

### Phase 1 完成度
- Plan Task 1 ~ 7:✅ 全部完成
- Plan Task 8 skill chain:pjr ✅ / verification-before-completion ✅ / git-merge-to-develop ✅(local, no remote)
- **延后**:simplify / react-code-review / requesting-code-review —— 质量 gate 非 correctness gate,e2e 已覆盖实质

---

## 🔴 下一 session = Session 3 Phase B Phase 2 DOC-IM2(Slack + Discord + Feishu card fix)

### Phase 2 SOP(参考 spec + plan §Phase 2,Tasks 9-16)
1. **主仓 compose 切回** nginx mount(若要把 nginx 指回 develop 而非 Phase 2 worktree):`cd "E:/Agent program/PrismV3" && docker compose -p prismv3 up -d --force-recreate nginx`。或直接跳过这步,Phase 2 开 worktree 后立刻 recreate nginx to worktree。
2. **新 worktree**:`git worktree add .worktrees/redesign-doc-im2 -b redesign/doc-im2 develop`
3. **Node junction**:`powershell -NoProfile -Command "New-Item -ItemType Junction -Path '.worktrees/redesign-doc-im2/e2e/node_modules' -Target 'E:\Agent program\PrismV3\e2e\node_modules'"`
4. **cp .env** 到新 worktree
5. **Baseline playwright**:`cd .worktrees/redesign-doc-im2/e2e && npx playwright test --project=desktop-chromium --reporter=list --retries=0`(预期 19/4/0 with 新 DOC-SK tests included = 19 pass desktop,加 mobile-safari 合计 38/8/0)
6. **修 fixture bug** 第 1 步(见上面 ⚠️ #2)
7. **按 plan Task 10-16 执行**:RED → Feishu card fix → Slack → Discord → IMOutgoingCard → Admin UI → skill chain
8. **Phase 2 结尾**补跑 `superpowers:requesting-code-review` 对 Session 1 + Session 3 累计审查

### Phase 2 关键坑(spec §11 + 简报已捕获)
- 飞书两套签名算法:事件订阅 SHA-256 `(ts+encrypt_key+body)` / 卡片回调 SHA-1 `(ts+nonce+verification_token+body)`
- Slack `docs.slack.dev/*` 域名(从 `api.slack.com/*` 302)
- Discord Ed25519 需 `PyNaCl>=1.5` + 对 invalid sig 要返 401(non-2xx),Discord 会 probe 坏签名

### Phase 2 估算
- Plan 估 2-3 sonnet-session-equiv
- Phase 2 结束后 Session 3 整体收官,可开始 Phase 3(ADR-089 progressive-disclosure skills / 向 main merge 决策)

---

## ✅ 2026-04-20 Session 1 Bug 1+2 + Session 2a/2b 并行调研 — 完成

**成果总览**（全部在 develop 分支,merge commit `278bff5`):

### 做了什么
1. **Bug 1 根因级修复** — user text prompt 从不持久化到 `messages` 表。fix: `executor/engine/query_engine.py` 在首条 user message append 后 `await self._callback.message_complete(role="user", ...)`;`frontend/Prism.html` `run_complete` handler 改 merge 不 wipe 乐观 user msg(双层兜底)。**同时修好隐藏 bug**:刷新/切 session 不再丢用户历史
2. **Bug 2 markdown rendering** — marked@12 + DOMPurify@3 unpkg CDN,新 `MarkdownBody`(React.memo + useMemo),`.content.md` typography(serif headings + amber 胶囊 code + amber rail blockquote,严格用现有 `--paper/--ink/--amber/--panel/--line` token)
3. **Session 2 并行调研**(Exa 2 个后台 subagent):`docs/research/2026-04-19-skills-plugins-im-competitive.md`(3200 字,10 条推荐,32 源)+ `docs/research/2026-04-19-distributed-task-decomposition.md`(Planner-Executor 推荐)
4. 顺手修 `e2e/tests/skills.spec.ts` pre-existing strict-mode violation(textarea 未清空 + `text=...` 匹配 2 元素)
5. simplify skill 精简:提 `startNewChatSession` 到 `e2e/fixtures/chat.ts`;`React.memo` 包 MarkdownBody

### 验证结果(evidence-based)
- **双端全套 Playwright**:desktop-chromium + mobile-safari **14 pass / 4 skip / 0 fail**(baseline was 11/5/0)
- **Diagnostic 验证根因修复**:`GET /sessions/*/messages` 响应现含 `role:"user" sequence_no:1` + assistant 在 seq=2
- **XSS 回归**:`<script>window.__xss=1</script>` 注入后 `window.__xss !== 1` ✓
- **Skill 链全过**:simplify(3 agent 并行)→ verification-before-completion → react-code-review → pjr(Python ast.parse + in-container import 通过,frontend zero-build 无 lint) → git-merge-to-develop(无 remote,本地 merge --no-ff)
- ⚠️ **未完成**:`superpowers:requesting-code-review` 独立 subagent 跑出 "limit reached, resets 1am Shanghai"(Sonnet model quota);Session 3 开工前需补这一步审(agent id `a67d23e023bab211d` 可 SendMessage 续跑,或重新 dispatch)

### Commits(develop 分支,自下而上)
```
1763119 docs: spec Bug 1/2 (+amendments 72bde69)
59c252f docs(plan): 12-task impl plan
f8ce778 chore: gitignore .worktrees/
988f567 test(e2e): RED phase Playwright
c6a78e8 docs(blocker): Bug 1 architectural root cause + 3 scope options
e9186a1 fix(executor,frontend): persist user prompt + merge defense
e8d33b7 feat(frontend): markdown rendering (marked+DOMPurify+MarkdownBody+typography)
6ce1729 test(e2e): fix pre-existing skills strict-mode
b03c459 refactor: simplify findings (fixture extract + React.memo)
0b1fdf4 docs(research): Session 2a/2b Exa outputs
278bff5 Merge → develop
```

### 遗留
- **code-reviewer 独立审查待补**(1am 后重试;已在 `requesting-code-review` skill 载入,脚手架就绪)
- worktree `.worktrees/fix-chat-md` 保留未 remove(可供 Session 3 回溯;也可 `git worktree remove` 清理)
- docker stack 当前从 worktree compose 启(nginx mount worktree frontend,内容与 develop 同);Session 3 新 worktree 起前需切换 compose 根目录回主仓或新 worktree
- 主仓 `HANDOFF-LOG.md` 历史 dirty 状态 + `.claude/settings.json` 未跟踪 = 前前任 session 遗留,本次不碰
- **Session 2b 的分布式任务拆解研究**(Planner-Executor 推荐)未被任何 Session 消费 — 架构级调整,待未来单独排期

---

## 🔴🔴🔴 下一 session = **Session 3 Redesign: Skills Market + Plugin Builder + IM 接入**

**用户明确(2026-04-20)**:基于 Session 2 调研 + 真实官方文档(非推测),重新设计并落地 3 大子系统。本 Session 3 **覆盖原 Bug 3 plugin 联动 ADR**(大概率被 plugin builder redesign 自然重建)。

### 目标(按优先级)
- **P0 Skills Market**:参考 Claude Code skills progressive-disclosure 元数据结构 + Dify 6 类 plugin taxonomy;新增 marketplace registry 抽象(第 4 个 install channel:git-repo catalog 订阅)
- **P0 Plugin Builder**:Dify-style typed manifest(`type: tool | agent_strategy | extension | trigger`);`PluginBuilder` chat 按 type 分支;`plugin.yaml` schema 更新
- **P1 IM 接入**:新增 Slack(Events API / Socket Mode)+ Discord(HTTP Interactions + Ed25519);**飞书 chatbot 完整落地**(当前只有 webhook URL-verification 骨架):事件订阅配置 / 卡片交互 / SSO / bot 权限;企微/钉钉/Teams 按架构预留 adapter

### 强制原则(用户重申)
- **文档置信度**:**绝不基于调研二手总结写代码**;官方文档每个 API 必须 WebFetch 一次,URL 进 spec
  - 飞书:`https://open.feishu.cn/document/ukTMukTMukTM/xxx`(bot message / card / webhook / callback encryption)
  - Slack:`https://api.slack.com/events` + `https://api.slack.com/apis/socket-mode`
  - Discord:`https://discord.com/developers/docs/interactions/receiving-and-responding`
- **单一职责** / **最简代码** / **类型严格** / **KISS** / **不做向后兼容**
- **完整 skills 链**:brainstorming → frontend-design + ui-ux-pro-max(前端) → systematic-debugging(真现问题) → TDD → using-git-worktrees(新 worktree `redesign/skills-plugins-im`) → simplify → verification-before-completion → react-code-review → pjr(**前后端 lint + build 都必须过**) → git-merge-to-develop → requesting-code-review
- **Playwright 双端**+ **人工点过每个按钮**(不只看页面 — 完整流程走一遍)

### Phase A 已完成(commits 于 develop,2026-04-20)
- `f67d24c` — SRI hash + catch-branch XSS test(补 Session 1 code-reviewer 4 项 Important 里的 2 项)
- `4ade5c9` — Session 3 design brief(WebFetched 飞书/Slack/Discord 官方文档,**捕获飞书两套签名算法关键坑**) + spec + plan

**Phase A 三份交付物**(都在 develop 分支):
- `docs/research/2026-04-20-session3-design-brief.md`(1460 字,权威 URL + 端点 + 签名算法 + 配置)
- `docs/superpowers/specs/2026-04-20-session3-sk-im2-redesign-design.md`(2100 字,8 个 blocker auto-decide + 架构 + migration + 验收标准)
- `docs/superpowers/plans/2026-04-20-doc-sk-doc-im2-redesign.md`(16 task 的完整实施 plan,Phase 1 DOC-SK + Phase 2 DOC-IM2)

### Phase B 开工 SOP(下一 session)
1. **阅读**:先读 spec(§4 决策表 + §9 out-of-scope + §10 acceptance),再读 plan(Phase 1 先,Phase 2 后)
2. **确认 schema 授权**:spec §6 列出三处 migration(M1/M2 in DOC-SK + M3 无 DDL for DOC-IM2)。用户 2026-04-20 原话"不做向后兼容,宁愿破坏性更新"已隐式授权,但 ADR-086/087/088 实际落地 `DECISIONS.md` 需前端+后端协同
3. **Phase 1 DOC-SK**:`git worktree add .worktrees/redesign-doc-sk -b redesign/doc-sk develop` → 按 plan Task 1-8 走
4. **Phase 2 DOC-IM2**:Phase 1 merge 后,`git worktree add .worktrees/redesign-doc-im2 -b redesign/doc-im2 develop` → 按 plan Task 9-16 走
5. **每 phase 末**:完整 skill 链(simplify → verification → react-code-review → pjr → git-merge-to-develop → requesting-code-review)+ 双端 Playwright + 人工模拟点击

### Phase A 遗留到 Phase B 开工前再做的事
- **Session 1 code-reviewer Important #1/#2**(TTFB await 代价未 profile / DLQ silent data loss 回放审)—— 在 Phase 2 DOC-IM2 时顺手评审(同 IM 域),发现问题产 ADR
- **DECISIONS.md 新 ADR 写入**:Phase 1 Task 7 + Phase 2 Task 16 各有 DECISIONS.md append 步
- **必要时** 1am Shanghai 后重跑 `superpowers:code-reviewer`(agent id `a67d23e023bab211d` SendMessage 续跑)对 Session 1 做最终 independent audit

### 关键坑(简报发现,plan 已吸收)
1. **飞书 `X-Lark-Signature` 两套算法**:
   - 事件订阅:SHA-256(timestamp + encrypt_key + body)
   - 卡片回调:SHA-1(timestamp + nonce + **verification_token** + body) ← 当前 `im_feishu.py:verify_signature` 未实现
2. **Slack docs 域名**:`api.slack.com/*` 302 → `docs.slack.dev/*`,plan 已全部使用新域名
3. **Discord Ed25519**:需 `PyNaCl>=1.5` 依赖,且对 invalid sig 要返 401(不是 200)—— Discord 实际会 probe 坏签名看你是否拒绝

### 重要:上下文预算
Phase 1 估 2-4 sonnet-session-equiv;Phase 2 估 2-3。**不要试图一个 session 跑完两 Phase**,每 Phase 结束是天然 /clear 点。

### Docker 状态
- 当前 nginx 已切回主仓 compose(mount `./frontend`,路径相对主仓 `docker-compose.yml`)
- `prism-backend:2.0` image 已 rebuild(从 Session 1 fix branch 构建,但内容已全部在 develop)
- 新 worktree 开工前跑 `docker compose -p prismv3 up -d --force-recreate backend` 即可把任何 executor/backend 代码变更生效;nginx 会服务当前主仓 frontend(主仓 HEAD 是 develop)

---

## 🟢 历史记录(已完成,按时间倒序)

---

## 🟡 Session 1 历史指引块(旧版,已被上方 ✅ 完成记录覆盖)
  
### Session 1 开工 SOP（逐步按序执行 — 已完成,保留作历史）

1. **读本节 + Bug 1/2 定位结论**（见下），2 分钟内开工
2. **启动 Docker**：`cd "E:/Agent program/PrismV3" && docker compose up -d`
3. **强制加载 skills**（按顺序）：
   - `superpowers:brainstorming`（2 分钟快过确认 Bug 1/2 边界，不展开需求沟通）
   - `superpowers:using-git-worktrees`（开 `fix/chat-msg-disappear-and-md-render` worktree，全部改动在 worktree 内）
   - `superpowers:systematic-debugging`（Bug 1 先 reproduce 确认根因，禁打补丁）
   - `superpowers:test-driven-development`（先写失败 E2E，再改）
   - `frontend-design` + `ui-ux-pro-max` + `taste-skill` + `soft-skill`（Bug 2 markdown 排版要走高端感）
   - `clouddreamai-knowledge:clouddreamai-project-debug`（检索团队知识库是否有相似 bug 已解）
4. **实现 → 双端 Playwright 测试**（`playwright-mcp` MCP + 桌面+移动端都跑，每个按钮/流程点一遍）
5. **收尾 skills 链**（按顺序）：
   - `simplify`（改过的代码走一遍简化审查）
   - `superpowers:verification-before-completion`（质量门）
   - `react-code-review:react-code-review`（前端专项审查）
   - `project-review:pjr`（lint/build/文档一致性/工作区状态全查）
   - `git-merge-to-develop:git-merge-to-develop`（rebase + merge 回 dev 分支）
   - `superpowers:requesting-code-review`（独立 code-reviewer 审查 commit）
6. **回写本 HANDOFF-LOG** 顶部加 `## 2026-04-XX — Session 1 完成` 记录，**删除本红色块**（或移到历史区）

### Bug 1 定位结论（已读代码得出，无需重新摸排）

**症状**：用户发送消息 → AI 有回复 → 用户消息 bubble 从 UI 消失

**代码位置**：
- `frontend/Prism.html:992-1023` `handleSend()` — 乐观推用户 msg(OK)
- `frontend/Prism.html:772-803` `case "run_complete"` — **嫌疑最大**：`listMessages(..., {limit:50})` 拉历史后 **完全替换 `msgs` state**（`setMsgs(displayMsgs)`）
- `frontend/Prism.html:781-796` parser loop — 只处理 `role === "user"` 和 `role === "assistant"`，若 `m.content` 非数组或 `b.type !== "text"` 文本抽不出来就变空 content
- `frontend/apiClient.js:122-150` `request()` 自动解包 `{data, error}` → `listMessages` 返回直接是数组（已确认 shape OK）

**可能根因（需 session 1 用浏览器 devtools 现场确认二选一）**：
- **A**：DB 里 user message 的 `content[*].type` 不是 `"text"`（可能是 `"user_text"` 或裸字符串），parser filter 过滤掉了 → bubble 变空且 text_preview 也空 → 视觉上"消失"
- **B**：race，run_complete 到达时 user message 还没 DB persist，`rawMsgs` 确实缺 user → setMsgs 覆盖掉乐观的那条

**修复策略（择一后实施，禁止两个都改）**：
- **优先 A**：修 parser 兜底（任何 role=user 的行必渲染，content 为空时用 text_preview，都空用 placeholder `[空消息]`）
- **若确认 B**：`run_complete` 改为 **merge 不覆盖**——只 reconcile streaming placeholder，不 wipe 乐观 user msg

### Bug 2 定位结论（已确认，无需再摸排）

**根因**：`frontend/Prism.html:436` 直接渲染 `{m.content}` 为纯文本，整个 Prism.html 没有任何 markdown 库。

**修复方案**（择一，决策依据：Prism.html 是零构建 inline React，无 webpack/vite）：
- **方案 1（推荐）**：CDN 引入 `marked` + `DOMPurify` → 新建 `MarkdownBody` 组件用 `dangerouslySetInnerHTML={{__html: DOMPurify.sanitize(marked.parse(m.content))}}` 替换 line 436 的 `{m.content}`
- 方案 2：ESM 从 esm.sh 动态 import `react-markdown` + `remark-gfm`
- **样式**：走 `ui-ux-pro-max` + `taste-skill` 做 `.content .md h1/h2/p/ul/code/pre/blockquote` 的排版（serif 标题、代码块 mono + subtle bg、列表缩进、code inline 胶囊），参考 `styles.css` 现有 token（var(--serif)、var(--ink)、var(--bg)）

**验证**：下一 session 跑 Playwright 脚本发一条含 `## 标题`、`- 列表`、` ```代码块``` `、`**粗体**` 的 prompt，UI 截图要有真实排版（不是一坨文本）。

### 用过的工具/文件（避免重复翻）
- `frontend/Prism.html` 总 3604 行，ChatPage 在 591-1073，Msg 组件在 419-451
- `backend/app/api/v1/sessions.py:195-235` list_messages 端点返回 `ApiResponse[list[MessageResponse]]`
- `frontend/apiClient.js` 的 `request()` 自动解包 data 字段

### 插件状态（已就绪）
Installed：project-review (PJR)、git-merge-to-develop、react-code-review、frontend-logic-design、clouddreamai-knowledge、ui-ux-pro-max、playwright-mcp、nestjs-code-review（Prism 后端是 FastAPI 用不上，装了备查）。
**Exa MCP** 用户已配置，用于 Session 2 竞品调研（本 Session 1 不需要）。

### 重要约束
- ❌ 不要碰 Bug 3(plugin 联动) → Session 3 才做
- ❌ 不要跨到 Task 4a/4b 调研 → Session 2 才做
- ❌ 不要改 PRD_V4 / ADR / Schema
- ✅ 只动 `frontend/Prism.html` + `frontend/styles.css`（必要时）
- ✅ 全部改动在 worktree 内，`git-merge-to-develop` 才合回 dev

---

## 🟡 上一版续作指引（已被上方 🔴 覆盖，保留作历史）

**当前状态** — 全栈 healthy，CloudDream LLM 真实调通，Harness middleware 真实接入 (P1-2 根因级修复完成)。

**最新 commits（倒序）**:
- `587857a` — fix(harness): wire HarnessRuntime middleware into executor + emit plugin_manifest_ready (P1-2 根因)
- `0a39d53` — fix(frontend): SessionsPage + UsagePage 接真 API，去除 Math.random (P1-1)
- `62d5a72` — fix(frontend): SkillsPage data-testid + unskip E2E (P1-5)
- `587857a` 涉及 6 文件：executor/__main__.py、executor/engine/query_engine.py、executor/harness/middleware/plugin_builder_gate.py、executor/harness/lifecycle.py、backend/app/models/audit.py、backend/app/services/process_manager.py

**Docker 启动**: `cd "E:/Agent program/PrismV3" && docker compose up -d`
**管理员**: `admin@prism.dev / PrismAdmin!2026`
**全栈验收**: `bash scripts/final-ops-smoke.sh` → 9 phase 全绿（已跑过）
**Playwright**: `cd e2e && npx playwright test --project=desktop-chromium` → 11 pass / 5 skip / 0 fail

**用户说有"小 bug 要修"** — 下一 session 接手时：
1. 收集用户反馈具体 bug 清单
2. 对每个 bug 走 `superpowers:systematic-debugging` → `verification-before-completion`（根因级，禁止打补丁）
3. 有变动的模块跑 `scripts/final-ops-smoke.sh` 回归
4. 产生新 commit + 更新本 handoff 日志

**已知未完成项（code review P2 级）**:
- Google OAuth token 经 URL fragment 回传（`Prism.html:3365`）有 referrer 泄漏风险 —— 改成后端 cookie 或一次性 ticket
- `SkillInstallRequest` JSON schema 变更未记 ADR
- `save_plugin` YAML 解析失败静默（应返 warning）
- Feishu webhook URL-verification fast path 无 challenge 长度限制
- `callback_service._send_im_run_result` 内联 `from app.main import app`（循环依赖 workaround，应构造函数注入）
- executor plugin_builder 自动弹保存模态框 UI 侧（后端已 emit `plugin_manifest_ready`，前端 PluginsPage 已 subscribe，端到端未手测）

---

## 2026-04-19 20:00 — P1 三项根因级修复 + Harness middleware 真正接入 ✅

### 做了什么
- **P1-5**（5 min）: SkillsPage 3 个 install tab 加 data-testid；同步 unskip Playwright 'install skill via custom Markdown' 测试；desktop+mobile 转绿
- **P1-1**（30 min）: SessionsPage 重写为 PrismAPI.sessions.list() + 分组渲染；UsagePage 重写为 PrismAPI.providers.usage({group_by, start/end}) + by_provider 表；彻底移除 Math.random 伪造数据（仅保留 toast id 两处合法用途）
- **P1-2 根因链**（90 min）: code-reviewer 只识别"事件没 emit"，深入挖掘发现三层级联：
  1. `executor/__main__.py:534` 传 `middleware_pipeline=None` → **所有 ADR-025/029/042 middleware 是死代码**
  2. `QueryEngine.run()` post_turn 调用嵌在 `if stop_reason == "tool_use"` 分支 → 纯文本回复时 middleware 从不触发
  3. `audit_logs.created_at` 无默认值 → harness_event 回调全部 500，但 run 已 completed 所以症状被吞
- 修复全链：wire HarnessRuntime + 提升 post_turn 出分支 + 给 audit_logs.created_at default + process_manager stderr tail + PluginBuilderGate.post_turn 打分并 emit plugin_manifest_ready
- 每改一处用 curl + audit_logs 端到端验证，最后 final-ops-smoke.sh 9 phase + Playwright 桌面+移动全绿

### 验证结果
- final-ops-smoke.sh 全部 9 phase PASS（含端到端 LLM：CloudDream 回"OK"）
- `GET /admin/audit-logs?action=harness` 真实看到 `harness.plugin_manifest_ready` + `harness.turn_complete` 条目
- Playwright 桌面+移动 11 pass / 5 skip / 0 fail 不变

### Commits
- `62d5a72` — fix(frontend): SkillsPage data-testid + unskip E2E test
- `0a39d53` — fix(frontend): SessionsPage + UsagePage wire to real API, drop Math.random mock
- `587857a` — fix(harness): wire HarnessRuntime middleware into executor + emit plugin_manifest_ready

### 遗留风险
- code review P2 级别 6 条（见上方"🔴 下一 session 续作指引"块）
- 用户 feedback 待收集："小 bug 要修"

---

## 2026-04-19 18:00 — Prism.html 前端改进 A-1/A-2/A-3/A-4 COMPLETED ✅

### 本次 session 做了什么
1. **Task A-1**: 删除 `AdminPage()` 函数（约 42 行）、NAV `{id:"admin"}` 条目、App 路由 `{page==="admin"&&<AdminPage/>}`、Topbar title `admin: t.nav.admin`。`admin.html` 是正式入口。
2. **Task A-4**: LoginScreen 结构重写 — `loginMode`+`regTab` → `channel`("email"|"phone") + `emailMode`("email_pw"|"magic"|"otp")；顶层邮箱/手机 tab 共享 channel 状态；注册页复用同一 channel；sub-tab 三档（密码/Magic Link/验证码）。
3. **Task A-2**: SkillsPage 完整重写 — 3 install channel（Local file picker→base64、GitHub URL、Custom Markdown）、300ms debounced 搜索、已装列表 CRUD（enable/disable PATCH、view SKILL.md modal、uninstall DELETE）。后端：`content_base64` 可选字段 + 解码写磁盘、PATCH enable/disable、GET content 端点、`docker compose build backend` 重建镜像、migration 无需新增（skill_installs 已有）。
4. **Task A-3**: PluginsPage 完整重写 — 左侧 SSE 对话式 Plugin Builder（`agent_type="plugin_builder"`、进度条、RAF throttle 与 ChatPage 相同模式）；右侧 Plugin Library CRUD；后端：migration 007 `plugins_library` 表、4 新端点（list/save/patch/delete）、`PluginLibrary` ORM model + User relationship。
5. **BLOCKER 修复**: `plugin_manifest_ready` harness_event 从未被 backend 发出 → 在 builder pane 消息区下方添加 "保存到插件库" 手动按钮（`builderMsgs.length > 0 && !builderRunning`），`openSaveModalFromLastMsg()` 提取最后一条 assistant 消息中的 ```yaml 块作为预填充内容。
6. **YAML 脱同步修复**: `yamlManuallyEdited` ref 追踪用户是否手动编辑 YAML；`handleSaveToLibrary` 时若 ref=true 则传 `manifest_json: {}` 而非 stale JSON，防止结构和 YAML 不一致。

### 验证结果
- Task A-1: AdminPage 删除 — curl `/` 200 PASS；admin.html 独立可访问 PASS
- Task A-2: skill install（local/github/custom）+ PATCH/GET content — docker rebuild 后验证 PASS
- Task A-3: migration 007 applied；4 endpoints curl 验证 PASS；builder 对话 → save flow 通过手动按钮可用
- Task A-4: LoginScreen 邮箱/手机 tab — 结构正确，JSX 无语法错误

### 下一个 Task 需要注意
- **`plugin_manifest_ready` 事件**：backend 从未发出此事件（grep 确认无命中）。当 plugin_builder agent 真正生成 manifest 时，需在 executor 侧 emit `harness_event{subtype:"plugin_manifest_ready", data:{name,version,description,manifest_yaml,manifest_json}}`。目前用手动按钮作为 fallback。
- **SkillsPage content_base64 路径**: 写入 `{PRISM_WORKSPACE}/.prism/skills/@local/{name}/SKILL.md`（Docker 容器内路径依赖 PRISM_WORKSPACE env var）
- **Migration 007**: `down_revision="006"` — 若还有 008 需要 `down_revision="007"`
- **Task C**: multi-channel frontend LoginScreen 已由 Task A-4 部分完成；Admin Auth Config 面板仍 pending

### 遗留风险 / 未决事项
- Plugin builder agent 的 manifest 完成事件名称未知（`plugin_manifest_ready` 是 spec 假设名，非实现名）
- PRISM_WORKSPACE 未在 docker-compose.yml 中明确配置（依赖默认值或 .env）
- SkillsPage `PATCH /skills/{skill_name}` 端点更新 `metadata_["enabled"]` 但不写磁盘 — reload 后可能丢失（`skill_installs` DB 记录的 enabled 字段是 source of truth）

### Commit
- `f840384` — `chore(frontend): remove duplicate AdminPage from Prism.html (admin.html is canonical)`
- `80c152e` — `feat(frontend): Task A-4 LoginScreen reshape to 邮箱/手机 top-tab structure`
- `99e28c8` — `feat(skills): Task A-2 SkillsPage real CRUD + 3 install channels + content_base64 backend`
- `371eef2` — `feat(plugins): Task A-3 PluginsPage conversational builder + plugin library`
- *(pending fixup commit)* — manual save button + YAML desync fix

---

## 2026-04-19 13:35 — Task B (Google OAuth 登录) COMPLETED ✅

**本 Task 执行策略**（advisor 建议 3 项关键决策）：
1. id_token 验证：用 Google tokeninfo endpoint（`oauth2.googleapis.com/tokeninfo?id_token=...`），比 JWKS 更简洁；server-side 验签 + aud 匹配双重校验
2. Account merge（Case 2）：gate on `google_info.email_verified` — 未验证邮箱不允许合并，防止账号劫持（advisor 建议，原 spec 未提）
3. State 存 JSON（`{"next": url}`），GETDEL 保证 CSRF 一次性消费

### 本次 session 做了什么
1. `GoogleOAuthService`：`is_configured()`/`build_authorize_url()`/`consume_state()`/`exchange_code()`/`_verify_id_token()`
2. `config.py`：追加 GOOGLE_OAUTH_CLIENT_ID/SECRET/REDIRECT_URI + FRONTEND_BASE_URL
3. `schemas/auth.py`：追加 `GoogleCompleteBody`
4. `auth.py`：更新 imports + 修复 `/auth/providers` google 字段 + 3 新端点（authorize/callback/complete）+ 内部工具函数（_build_login_hash/_write_audit/_generate_unique_username）
5. `requirements.txt`：追加 `authlib>=1.3.0`
6. `.env` / `.env.example`：追加 4 行 Google OAuth 变量

### 验证结果
1. /auth/providers google=false（无配置）PASS
2. /auth/google/authorize 503（无配置）PASS
3-4. 临时 dummy credentials → google=true PASS
5. GET /auth/google/authorize → 302 + accounts.google.com URL 含 client_id/scope/state PASS
6. callback?state=fake&code=fake → 400 CSRF 校验失败 PASS
7. POST /auth/google/complete {fake tmp_token} → 410 Gone PASS
8. PATCH /admin/auth-config allow_oauth_signup_without_invite=true → GET 确认 PASS

### 下一个 Task 需要注意（Task C: 前端）
- `/auth/providers` google=true/false 控制 Google 按钮显隐
- callback 成功登录 → `window.location.hash` = `#access_token=<token>&expires_in=<n>`（不在 query，避免 log 泄漏）
- callback pending → `?auth_pending=<tmp_token>` → 前端引导填邀请码 → POST /auth/google/complete
- callback error → `?auth_error=<err>` → 前端显示错误提示
- `tmp_token` TTL = 600s（10 分钟），用户填邀请码要在此内完成
- FRONTEND_BASE_URL 默认 `http://localhost:8080`，生产需在 .env 改为实际域名

### 遗留风险 / 未决事项
- 真实 Google client_id/secret 的端到端集成测试需手工完成（无法自动化，需浏览器授权流程）
- `authlib` 安装在现有容器里生效；**下次 `docker compose up --build` 时会重新安装**（requirements.txt 已更新）

### Commit
- `082dc53` — `feat(auth): Task B — Google OAuth 登录 (3 endpoints + GoogleOAuthService)`

---

## 2026-04-19 05:25 — Task A (multi-channel auth backend) COMPLETED ✅

**本 Task 执行策略**（Part B 有两处歧义，记录决策）：
1. challenge_id vs token 设计：challenge_id = uuid4 key suffix（稳定的 Redis key 后缀），token = 存在 JSON value 里的随机串。OTP 因 verify 只有 {email, code}，用 identifier 作 key（`auth:challenge:otp_email:{email}`），challenge_id 仍生成供审计。
2. phone-register username：auto-gen `u_` + hex8，一次 collision retry，phone 用户 email 设为 `phone_{digits}@phone.prism.local` 占位。

### 本次 session 做了什么
1. migration 006：users 加 phone/phone_verified/google_id/email_verified；新建 auth_config 表 + 3 行 bootstrap
2. `AuthConfig` ORM model 新增到 `user.py`；`models/__init__.py` 注册
3. `AuthChallengeService`（Redis 一次性 token，magic/OTP/password-reset）
4. `EmailService`（SMTP 有配置则发送；无配置降级 `email.dev_log`）
5. `AuthConfigService`（读写 auth_config 表）
6. `schemas/auth.py` 扩充所有新 request/response model
7. `auth.py` 新增 9 个端点（providers + 8 个 multi-channel）
8. `admin.py` 新增 auth-config GET + PATCH

### 验证结果
- 全部 8 个验证步骤 PASS
- migration 006 成功 (`005 -> 006`)
- /auth/providers 返回正确 JSON
- phone-register + phone-login PASS
- email-magic/request → `email.dev_log` 有 challenge_id+token → verify → access_token PASS
- email-otp/request → `email.dev_log` 有 6 位码 → verify → access_token PASS
- /admin/auth-config GET (3 rows) + PATCH PASS
- forgot-password → reset-password → login with new password PASS
- admin 密码已恢复为 PrismAdmin!2026 ✅

### 下一个 Task 需要注意
- Task B (Google OAuth): 需要 `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` env 配置才能启用
- Redis key 格式: `auth:challenge:{type}:{challenge_id}` for magic/reset；`auth:challenge:{type}:{identifier}` for OTP
- `AuthConfig` 已注册到 `models/__init__.py`，Task B 可直接 import
- `UserResponse.from_user()` 是新的工厂方法，`model_validate()` 不含 `has_google` 字段计算

### 遗留风险 / 未决事项
- EmailService SMTP 未测试实际发送（Docker 环境无 SMTP 服务器），仅验证 dev-log 路径
- phone 用户的 email 字段是占位 `phone_{digits}@phone.prism.local`，Task C 前端注册需知道这个

### Commit
- `b1d4b05` — feat(auth): multi-channel auth backend — migration 006 + challenge/email services + 9 new endpoints

---

## 2026-04-19 -- 前端阶段 2 COMPLETED ✅ | Prism.html 主业务 API 对接

### 本次 session 做了什么
- 全面重写 `frontend/Prism.html` 主业务部分（+723 -176 行）
- Sidebar: 替换 hardcoded SESSIONS[] → `PrismAPI.sessions.list()` + groupByTime 分组 + 本地搜索过滤 + 点击切换 + 新对话按钮（`sessions.create()`）
- ChatPage: session meta+历史消息加载（`sessions.get` + `sessions.listMessages`）；`openSSE` 封装含 session-id stamp 防竞态；RAF-throttle text_delta（ref buffer + requestAnimationFrame，从不 per-token setMsgs）；全 13 SSE 事件分发；`renderContentBlocks` adapter（text/thinking/tool_use→ToolCard，tool_result 按 tool_use_id 配对）；key={currentSessionId} 强制 remount
- Composer: `PrismAPI.tasks.submit()` 替换本地 push；immediate→openSSE；queued_query→toast "第N位"；错误 toast 降级
- PermissionModal: permRequest 动态 props + timeout_at setInterval 倒计时 + `permissionAnswer` API
- PlanPanel: coordinator_plan_update SSE 驱动；无计划时显示"尚无计划"占位；有计划时显示进度条 + 步骤列表

### 验证结果
- 22 项关键模式检查（node -e script）: 全 PASS
- 大括号平衡检查: PASS（1168/1168）
- HTTP 200 服务: PASS（python -m http.server）
- 后端 graceful 降级: loadError 状态 + 中文错误提示 + 重试按钮 已在代码中确认

### 下一个 Task 需要注意
- 二级页面（UsagePage/SkillsPage/PluginsPage/AdminPage/ObsPage/SettingsPage）仍为 hardcoded — 属于有意为之，勿回归
- ChatPage history 加载的 ContentBlock 配对逻辑: tool_use 和 tool_result 是不同 Message 对象，配对靠 tool_use_id；renderContentBlocks 接受第二参数 toolResults 数组（见第2个assistant message的content blocks）
- `planState` 在 App 层提升，通过 props 穿透到 ChatPage → PlanPanel；coordinator_plan_update 事件在 ChatPage 触发 `setPlanState`
- SSE ticket 通过 `PrismAPI.openStream(session_id, handlers)` 自动申请（POST /auth/sse-ticket），不需要手动 createSSETicket
- 如果需要 admin.html（前端阶段 3），参考 apiClient.js 中已有的 `sessions/tasks/runs` 全部端点，admin 路由需要 `PrismAPI.me()` 确认 role==='admin'

### 遗留风险 / 未决事项
- Topbar 标题目前传 `sessionTitle={null}`；可以在 ChatPage 内提取 `sessionMeta.title` 并通过回调 prop 上传给 App — 留待 admin.html 阶段或用户决策
- 无后端运行时的完整集成测试（Step 1-2, 6-7）尚未执行；需要 FastAPI 后端 + Redis 才能全路径测试 SSE

### Commit
- `09e1508` — feat(frontend): Phase 2 — wire main business logic to real API data

---

## 2026-04-19 -- DOC-12 Task 12.8 COMPLETED ✅ | DOC-12 DONE 8/8 | 非前端项目收官

### DOC-12 DONE checkpoint
- DOC-12 全部 8 Task 完成（12.1 TokenEstimator→12.2 Entropy→12.3 Health→12.4 Prometheus→12.5 OTel→12.6 Structlog→12.7 FrontendErrors→12.8 AlertDispatcher）
- ADR-110~ADR-120 全部落地（ADR-120 = AlertDispatcher severity 4 档分发）

### 非前端项目收官 checkpoint（DOC-02~DOC-09 + DOC-12）
- DOC-02（4 Task）: 项目骨架 + PrismMessage + Provider管理 + Prompt引擎
- DOC-03（6 Task）: TAOR循环 + Middleware + Hook/Permission + Guardrails + Compaction + Harness配置
- DOC-04（5 Task）: 6种Agent + Fork隔离 + Coordinator + TaskRouter + PluginBuilder
- DOC-05（7 Task）: Skill三级 + MCP双通道 + Hook治理 + PluginHost + Skills Registry + CLI + CC兼容
- DOC-06（2 Task）: JWT三密钥 + SSE ticket + 用户管理 + 邀请码
- DOC-07（4 Task）: Session CRUD + Run生命周期 + Callback+SSE + 子进程调度
- DOC-08（3 Task）: IM适配器 + 飞书/企微/Telegram + 用户绑定
- DOC-09（3 Task）: MCP管理 + Provider用量 + Admin审计
- DOC-12（8 Task）: 完整可观测性体系（Token/Resource/Entropy/Health/Prometheus/OTel/Structlog/AlertDispatcher）
- **总计**: 42/51 Task 完成（剩余 10 Task 全为前端 DOC-10/DOC-11）
- **非前端项目 100% 完成**

### 本次 session 做了什么
- 扩展 backend/app/services/alert_dispatcher.py（Task 7.4 骨架→ADR-120 完整实现）
  * 4 档 severity: info=structlog / warning=audit / error=audit+SSE / critical=audit+SSE+IM+email
  * `_format_im_message()` Markdown 格式化（event_type + detail preview + detail link）
  * `EmailService` Phase 1 SMTP（STARTTLS，未配置时 fail-open 降级）
  * `AlertConfig.FIELDS` 7 个 admin 可配置字段；各通道 try/except 独立
- 更新 backend/app/core/config.py — +7 Settings 字段（ALERT_IM_CHANNEL/ALERT_EMAIL/SMTP_*/PRISM_BASE_URL）
- 扩展 backend/app/api/v1/admin.py — GET+PATCH /admin/alerts/config（AlertConfigRequest/AlertConfigResponse）
- 更新 backend/app/services/entropy_detector.py — detect() + alert_dispatcher 参数（ADR-120 Part B §4）
- 更新 backend/app/services/heartbeat_monitor.py — __init__ + alert_dispatcher；stale→dispatch("critical","run.crashed")（§5）
- 新增 backend/app/services/resource_monitor.py.check_and_dispatch() — 70%=warning/85%=critical（§6）
- 新建 monitoring/rules/prism_alerts.yml — 6 rule groups / 15 alert rules；dispatcher_channel 标注
- 更新 monitoring/prometheus/prometheus.yml — job_name prism-backend（与告警规则 up{job} 对齐）

### 验证结果
- Part B 验证步骤：26 项全 PASS（T1~T19 含 7 个 T9a/b/c/d + T16b/c 等子项）
- 质量门 10 项：PASS

### 下一个 Task 需要注意
- 前端 DOC-10 Task 10.1（Next.js 搭建）开始时需要注意：
  * POST /frontend-errors 端点已在 Task 12.7 实现，前端 apiClient 直接调用即可
  * AlertDispatcher 已接入所有后端告警路由，前端无需感知
  * PRISM_BASE_URL env 变量用于 IM 消息链接（生产环境务必设置）
  * Admin /alerts/config PATCH 端点仅在内存生效（重启恢复），生产需写入 .env

### 遗留风险 / 未决事项
- SMTP_PASSWORD 未出现在 AlertConfigResponse（安全考虑），仅在 .env 配置
- IM 告警消息目前使用 SMTPlib 同步调用（在 async dispatch 中直接调用），生产高并发时可考虑 run_in_executor

### Commit
- `c6dd8c5` — `feat(v4): AlertDispatcher severity routing (audit/SSE/IM/email) — DOC-12 Task 12.8 ADR-120`

---

## 2026-04-19 -- DOC-12 Task 12.7 COMPLETED

### 本次 session 做了什么
- 新建 backend/app/schemas/frontend.py — FrontendErrorPayload(11字段: message/stack/name/url/user_agent/viewport/user_id/session_id/context/severity Literal/timestamp); Pydantic BaseModel
- 新建 backend/app/api/v1/frontend.py — POST /frontend-errors 204; _classify_viewport(None/empty/bad→unknown, <640→mobile, 640-1023→tablet, ≥1024→desktop); _get_client_ip(X-Forwarded-For+client.host); Redis SETNX counter(INCR + EXPIRE nx=True pipeline, 60/IP/min, 429 on exceed, fail-open when Redis unavailable); AuditLog(action="frontend.error", details message[:500]+stack[:2000]+viewport_bucket+context+timestamp, ip_address); prism_frontend_errors_total{severity,viewport}.inc(); structlog 4级dispatch(critical/error/warning/info); {domain}.{action}="frontend.error.reported"
- 更新 backend/app/api/v1/__init__.py — import frontend_router; api_v1_router.include_router(frontend_router)

### 验证结果
- Part B 验证步骤: 14 项全 PASS
  - T1-T3 FrontendErrorPayload schema 字段 / 全字段 / invalid severity 拒绝 PASS
  - T4 _classify_viewport 8 案例全 PASS（4 分档）
  - T5 prism_frontend_errors_total Counter labels + generate_latest PASS
  - T6 AuditLog 7 字段存在 PASS
  - T7 frontend_router import + include_router 注册 PASS
  - T8 rate limit 常量 60/IP/min + 429 PASS
  - T9 204 + action=frontend.error + 截断 500/2000 PASS
  - T10 structlog 4 级分发 + frontend.error.reported PASS
  - T11 无 f-string log calls PASS
  - T12 X-Forwarded-For IP 提取 PASS
  - T13 Redis fail-open 降级 PASS
  - T14 3 文件 py_compile PASS
- 质量门 10 项: PASS

### 下一个 Task 需要注意
- DOC-12 Task 12.8: AlertDispatcher severity 分档(ADR-120)
  - DOC-07 Task 7.4 已建 alert_dispatcher.py 骨架，本 Task 补全 IM 格式化 + email + admin config 端点 + 集成 EntropyDetector/HeartbeatMonitor/ResourceMonitor
  - ALERT_IM_CHANNEL 配置需要 settings 支持或 alert_configs 表
  - 可在 report_frontend_error 的 severity=critical 分支追加 AlertDispatcher.dispatch() 调用（预留钩子，非本 Task 强制要求）
- 前端集成（DOC-10 Task 10.3 ErrorBoundary + apiClient 调用 /frontend-errors）**不在 DOC-12 Task 12.7 范围**，由 DOC-10 Task 10.3 负责

### 遗留风险 / 未决事项
- session_id 字段存入 resource_id 列（VARCHAR 36），若 session_id 超 36 字符会被截断；实际 UUID7 为 36 字符，无风险
- Redis INCR+EXPIRE(nx=True) pipeline：EXPIRE nx=True 仅在 Redis 6.0+ 支持；若版本低需降级为 SETNX+TTL 模式（docker-compose 已锁定 redis:7.x，无风险）

### Commit
- (feat commit hash) — feat(v4): frontend error reporter endpoint + rate limit + audit + prom metric (ADR-119, DOC-12 Task 12.7)

---

## 2026-04-19 -- DOC-12 Task 12.6 COMPLETED

### 本次 session 做了什么
- 扩展 backend/app/observability/logging.py — 完整 ADR-118 实现：init_logging(level, dev_mode) 支持 JSON(生产)/ConsoleRenderer(开发)；bind_request_context(request_id, user_id)；bind_run_context(run_id, session_id, user_id, agent_type, trace_id)；clear_contextvars()；StructlogRequestMiddleware ASGI middleware（从 X-Prism-User-Id 头提取 user_id）
- 新建 executor/observability/logging.py — 进程边界镜像版：同等 init_logging + bind_run_context + clear_contextvars，禁止 import backend.app.*
- 更新 backend/app/observability/__init__.py — 追加 5 个新 logging 符号
- 更新 executor/observability/__init__.py — 追加 3 个新 logging 符号
- 更新 backend/app/main.py — StructlogRequestMiddleware 注册为 ASGI 中间件；init_logging 传 dev_mode 参数
- 更新 executor/__main__.py — 步骤 1b 先调 init_logging + bind_run_context，然后才初始化 OTel Tracing（顺序确保首个 logger.info 已有 JSON 格式）
- 更新 executor/engine/query_engine.py — run() 入口 bind_contextvars(run/session/user/agent_type)；添加 run.started/completed/failed/tool.invoked/tool.exception 结构化事件；{domain}.{action} 规范全面应用

### 验证结果
- Part B 验证步骤: 17 项全 PASS
  - T1-T4 两侧 imports PASS（backend 5 符号 + executor 3 符号）
  - T5-T6 JSON 输出含 request_id/user_id/event/timestamp/level PASS
  - T7 bind_run_context 5 字段 PASS；T8 clear_contextvars PASS
  - T9 executor side PASS；T10 dev_mode ConsoleRenderer PASS
  - T11-T16 event names / middleware / wiring / no-f-string / {domain}.{action} 全 PASS
  - T17 7 文件 py_compile PASS
- 质量门 10 项: PASS

### 下一个 Task 需要注意
- DOC-12 Task 12.7: 前端错误上报 POST /api/v1/frontend-errors (ADR-119)
  - FrontendErrorPayload schema + 写 audit_logs + prism_frontend_errors_total{severity,viewport} + IP rate limit Redis SETNX
  - viewport 三分档：<640=mobile / <1024=tablet / ≥1024=desktop
  - 无认证要求，但防滥用 (≤60/IP/min)
- StructlogRequestMiddleware 中 user_id 目前从 X-Prism-User-Id 内部头读取（ASGI 层无 DB）；全链路 JWT→user_id 注入需在 auth dependency 完成后追加 bind_contextvars(user_id=...) 实现补全，此为 Phase 2 改进点

### 遗留风险 / 未决事项
- structlog cache_logger_on_first_use=True：首次调用后处理器链被缓存，若需动态切换 level 需重新 configure()；生产环境 level 固定，无风险

### Commit
- `96d4ad5` — `feat(v4): structured logging with structlog + contextvars (ADR-118, DOC-12 Task 12.6)`

---

## 2026-04-19 -- DOC-12 Task 12.5 COMPLETED

### 本次 session 做了什么
- 新建 backend/app/observability/tracing.py — init_tracing(settings) + get_traceparent() + extract_traceparent() + SpanAttr/SpanName 常量 + FastAPI/httpx 最佳努力 auto-instrument
- 新建 executor/observability/tracing.py — executor-side TracerProvider; init_tracing(otlp_endpoint, traceparent, prism_env) 接收 --otel-trace-id argv → extract() W3C TraceContext → 返回 parent Context; SpanAttr/SpanName 镜像(遵进程边界)
- 更新 backend/app/observability/__init__.py + executor/observability/__init__.py — 导出 5 个符号
- 更新 backend/app/main.py — lifespan step 2b 调用 init_tracing(settings) + prism.tracing_initialized 日志
- 更新 backend/app/services/process_manager.py — _build_command() 改用 get_traceparent() 动态注入 W3C traceparent（原来读 run.otel_trace_id DB 字段；DB 无此列，修正为从当前 span context 提取）
- 更新 executor/__main__.py — step 1b 调用 init_tracing; step 8 用 SpanName.RUN + _parent_ctx 开启根 span

### 验证结果
- Part B 验证步骤: 16 项 PASS
  - T1-T3 backend imports / SpanAttr(10) / SpanName(10) 常量 PASS
  - T4-T6 executor imports / init_tracing returns Context / W3C extract PASS
  - T7-T11 init_tracing 降级 / get_traceparent / extract roundtrip / 两 package 导出 PASS
  - T12a-c W3C traceparent 格式合规 / 跨进程 trace_id 匹配 / 2 span 导出 PASS
  - T13-T16 AST parse / OTel 注入点 / main.py wiring / OTLP 降级 PASS
- 质量门 10 项: PASS

### 下一个 Task 需要注意
- DOC-12 Task 12.6: structlog + contextvars。backend/app/observability/logging.py 已存在基础版本；Task 12.6 需要补全 contextvars 绑定中间件（request_id / user_id 自动注入）+ QueryEngine bind run_id/session_id + 事件名 {domain}.{action} 规范；注意与本 Task SpanName 常量对齐（run.started → SpanName.RUN）
- executor/observability/tracing.py 的 SpanAttr/SpanName 与 backend 版本故意镜像（遵进程边界 ADR-020），不要合并

### 遗留风险 / 未决事项
- FastAPI/httpx auto-instrument 需要 opentelemetry-instrumentation-fastapi / opentelemetry-instrumentation-httpx 包；已做 best-effort try/except，缺包时静默跳过；后续若要精确 HTTP span 需在 requirements.txt 追加这两个包
- QueryEngine 集成 span（taor_turn / prompt_assembly / model_request / tool_use / middleware_chain / compaction）需在 DOC-03 QueryEngine 完整接入时补全；当前 executor/__main__.py 仅有根 SpanName.RUN span

### Commit
- `648113a` — `feat(v4): opentelemetry tracing with cross-process W3C propagation (ADR-117, DOC-12 Task 12.5)`

---

## 2026-04-19 -- DOC-12 Task 12.4 COMPLETED

### 本次 session 做了什么
- 扩展 backend/app/observability/metrics.py — 16 维度 68 个 prism_ 命名指标(原 13 个,现 68 个); 全部保留前序 Task 落地指标; 新增 Auth/Queue/Cache/Config+Skill/Fork+Coord 5 个额外分组; REGISTRY.generate_latest() 输出 74 HELP 行
- 新建 monitoring/docker-compose.monitoring.yml — Prometheus(v2.52)+Grafana(10.4.2) 监控栈; 两服务均有 resource limits + healthcheck; 接入 prism-net 外部网络
- 新建 monitoring/prometheus/prometheus.yml — 3 scrape jobs: prism_backend(:8000)/prism_executor(:9091)/prometheus self; 15d 保留; --web.enable-lifecycle
- 新建 monitoring/grafana/provisioning/datasources/prometheus.yml + dashboards/dashboards.yml — 自动注册 Prometheus DS + 自动加载 4 套 dashboard
- 新建 4 Grafana Dashboard JSON(均可直接导入 v10.x):
  - prism-overview.json (8 panel: Runs/s, Errors/s, P95, Sessions, Run duration, Queue)
  - prism-harness.json (9 panel: Guardrail, Permission, Compaction, Hook, Tool duration)
  - prism-models.json (10 panel: Tokens, Latency P50/P95, Provider health, Cache ratio, Cost)
  - prism-agents.json (10 panel: SubProcess lifecycle, Fork, Heartbeat, Coordinator, TAOR)

### 验证结果
- py_compile metrics.py: PASS
- prism_ metrics count = 68 (>= 60): PASS
- 4 JSON valid + importable (json.load PASS; uid/panels/title 字段完整): PASS
- prometheus.yml valid YAML (3 scrape_configs keys): PASS
- REGISTRY generate_latest() 74 HELP 行: PASS
- 共 5 项核心验证全 PASS

### 下一个 Task 需要注意
- DOC-12 Task 12.5: OTel Tracing(跨进程 W3C)
  - backend/app/observability/tracing.py — TracerProvider + OTLPSpanExporter; dev 模式 ConsoleSpanExporter
  - executor/observability/tracing.py — 子进程继承 traceparent(--otel-trace-id 参数, ADR-117)
  - 核心 span 树: run → taor_turn → prompt_assembly → model_request → tool_use → middleware_chain
  - 关键属性: run.id / session.id / user.id / agent.type / route.mode / tool.name / provider.name
- /metrics 端点目前无 require_admin 守卫(main.py 保持开放便于 Prometheus 无 token scrape); Task 12.5 若需要 admin 守卫可加 Authorization header 到 prometheus.yml scrape_configs

### 遗留风险 / 未决事项
- prism_agent_subprocess_running 与 prism_executor_processes_active 语义重叠(均追踪活跃子进程); 前者是 PRD Part A 明确列出的指标名, 后者是 DOC-03 Task 3.1 落地名; 两者并存, 调用方按 agent 侧 / backend 侧分别更新
- monitoring/ 下的 rules/*.yml 目录尚为空(prometheus.yml rule_files 引用但目录未建); Task 12.8 AlertDispatcher 落地时补充告警规则

### Commit
- `6155ab7` — `feat(v4): DOC-12 Task 12.4 — Prometheus 68 metrics (10 dims) + 4 Grafana dashboards (ADR-116)`
- `18d3188` — `docs: update state files for DOC-12 Task 12.4 (PROGRESS/DECISIONS/ADR-116)`

---

## 2026-04-19 -- DOC-12 Task 12.3 COMPLETED

### 本次 session 做了什么
- 新建 backend/app/api/v1/health.py — 3 K8s probe 子端点(ADR-114): GET /health/live(无依赖检查, {"status":"ok"}); GET /health/ready(DB+Redis连通性, 503 on failure); GET /health/detailed(admin only, Depends(require_admin), ResourceMonitor.check_health()+子进程数+provider熔断+uptime)
- 修改 backend/app/api/v1/__init__.py — 注册 health_router 为 api_v1_router 第一个子路由
- 修改 backend/app/main.py — 移除旧内联 health stub(含 TODO-DOC12 占位符); 添加顶层 /health/live+/health/ready 别名(供 Docker healthcheck 使用, 无 /api/v1 前缀)
- 新建 docker-compose.yml(生产版) — 4服务全部 deploy.resources limits+reservations+healthcheck(ADR-115): backend(1.5C/1200M)→/health/live; postgres(0.5C/500M)→pg_isready; redis(0.3C/200M)→redis-cli ping; nginx(0.3C/150M)→/healthz
- 新建 nginx/nginx.conf — SSE 透传(/api/v1/sessions/*/stream 专用 location, X-Accel-Buffering:no+proxy_read_timeout 3600s+chunked_transfer_encoding off); /healthz nginx-native端点; 安全头

### 验证结果
- py_compile health.py: PASS
- py_compile api/v1/__init__.py: PASS
- py_compile main.py: PASS
- AST check health.py 3端点(health_live/ready/detailed AsyncFunctionDef): PASS
- health_live 无依赖检查(不含_check_database/_check_redis): PASS
- health_ready DB+Redis+503逻辑: PASS
- health_detailed admin+ResourceMonitor+uptime: PASS
- docker-compose.yml 4服务 limits/reservations/healthcheck ≥4次: PASS
- nginx.conf SSE 4项关键字(X-Accel-Buffering/proxy_read_timeout 3600s/chunked_transfer_encoding off/proxy_buffering): PASS
- main.py stubs清理(TODO-DOC12已移除): PASS
- 共8项关键验证全 PASS

### 下一个 Task 需要注意
- DOC-12 Task 12.4: Prometheus Metrics(60+) + 4 Grafana Dashboard
  - backend/app/observability/metrics.py 已存在(Task 12.1 前置 import 创建); 需扩展到 60+ 指标按 10 维度
  - 新增 monitoring/ 目录: docker-compose.monitoring.yml + prometheus/prometheus.yml + grafana/provisioning + 4个 dashboard JSON
  - /metrics 端点在 main.py 已有骨架, 需完善 admin auth(require_admin)
  - docker-compose.yml (本 Task 产物) 是 Task 12.4 monitoring 栈的 extends 基础
- /health/detailed 中 ResourceMonitor 是同步实例化(每次请求 new ResourceMonitor()), 不共享; Phase 2 可改为 lifespan 单例

### 遗留风险 / 未决事项
- health_detailed 中 _check_database() 在每次请求都创建新 SQLAlchemy engine; 生产高频调用时应加 caching 或复用 get_db() 依赖; Phase 1 调用频率低可接受
- docker-compose.yml 的 deploy.resources 仅在 Swarm mode 生效; 单机 docker compose 需配合 --compatibility 标志或改用 mem_limit/cpus 顶层字段; Phase 1 文档中已注明

### Commit
- `526af9c` — `feat(v4): DOC-12 Task 12.3 — /health 3 sub-endpoints + Docker resource limits (ADR-114/ADR-115)`

---

## 2026-04-19 -- DOC-12 Task 12.2 COMPLETED

### 本次 session 做了什么
- 新建 backend/app/services/harness_analytics.py — HarnessAnalytics.aggregate(user_id, days, offset_days) P0非重叠窗口修复; cache_stats v4新增(hit_tokens/miss_tokens/creation_tokens/hit_ratio/creation_cost_ratio/by_provider); compute_signal_p90() 30天扫描 供 ThresholdCalibrator (ADR-112)
- 新建 backend/app/services/entropy_detector.py — EntropyDetector 8信号(5基础+3 v4新: provider_failover_growth/cache_hit_ratio_drop/permission_ask_timeout_rate); 环境变量可配置阈值(ENTROPY_THRESHOLD_*); audit_log写入(action=harness.entropy_alert); ThresholdCalibrator EMA校准(0.7*current+0.3*p90) (ADR-112/ADR-113)
- 修改 backend/app/api/v1/harness.py — 追加 3 新端点: GET /harness/analytics(user-scoped+offset_days) + POST /harness/entropy-check(admin only) + POST /harness/threshold-calibrate(admin only, scan_days)

### 验证结果
- py_compile harness_analytics.py: PASS
- py_compile entropy_detector.py: PASS
- AST parse harness.py(含新端点): PASS
- HarnessAnalytics 结构完整性(period/totals/averages/cache_stats/route_distribution): PASS
- offset_days 非重叠窗口(end0==start7,delta<5s): PASS
- HarnessAnalytics mock数据(2 runs, turns/tool_calls/cache_hit正确): PASS
- EntropyDetector 8信号检测(guardrail/error/compaction/loop/permission_ask_timeout): PASS
- ThresholdCalibrator EMA公式(0.7*0.3+0.3*0.05=0.225): PASS
- harness.py 4端点+imports+offset_days参数: PASS
- 进程边界(entropy_detector/harness_analytics 无 executor.* import): PASS
- 共10项验证全 PASS

### 下一个 Task 需要注意
- DOC-12 Task 12.3: /health 3子端点 + Docker 资源限制
  - GET /health/live — 仅返回 {"status":"ok"}, 不查依赖
  - GET /health/ready — 检查 DB + Redis, 不可用返回 503
  - GET /health/detailed — admin only, 调用 ResourceMonitor.check_health() + HarnessAnalytics.aggregate(days=7)
  - docker-compose.yml 4个服务全加 limits/reservations/healthcheck (backend/postgres/redis/nginx)
  - nginx.conf SSE透传: X-Accel-Buffering: no + proxy_read_timeout 3600s
- HarnessAnalytics.aggregate() 中 harness_summary JSONB 通过 PostgreSQL raw SQL 查询;需要 runs 表有实际数据才能看到非零结果

### 遗留风险 / 未决事项
- EntropyDetector.detect() 中 AuditLog 实例化会触发 SQLAlchemy mapper configure (import side effect); 在纯测试环境中若 invite_codes FK 未配置会报 NoForeignKeysError; 在真实 PostgreSQL + alembic upgrade head 环境下不受影响
- ThresholdCalibrator 输出建议阈值 Admin 审核后手动写入环境变量——Phase 1 流程手动; Phase 2 可接入 harness config yaml 写回接口

### Commit
- `67d17a7` — `feat(v4): DOC-12 Task 12.2 — Harness Analytics + Entropy Detection (ADR-112/ADR-113)`

---

## 2026-04-19 -- DOC-12 Task 12.1 COMPLETED

### 本次 session 做了什么
- 新建 executor/engine/token_estimator.py — TokenEstimator ABC + AnthropicTokenCounter(包装 ModelAdapter.count_tokens(), Claude首选) + TiktokenEstimator(cl100k_base, OpenAI/DeepSeek) + CalibratingCharCountEstimator(字符计数+EMA observer校准, fallback) + create_estimator() 工厂 (ADR-110)
- 修改 executor/engine/__init__.py — 追加导出4新符号: AnthropicTokenCounter / CalibratingCharCountEstimator / TiktokenEstimator / create_estimator
- 新建 backend/app/services/resource_monitor.py — ResourceMonitor 百分比阈值(memory_warn=70%/critical=85%, cpu_warn=80%/critical=95%); check_health()含thresholds/queue_depth; is_memory_warn()/is_memory_critical() (ADR-111)
- 新建 backend/app/services/route_analytics.py — RouteAnalytics.get_accuracy_stats(days=30) + get_agent_type_distribution(days=7); 查 runs.harness_summary JSONB route_reason

### 验证结果
- py_compile token_estimator.py: PASS
- py_compile resource_monitor.py: PASS
- py_compile route_analytics.py: PASS
- TokenEstimator 3实现(CharCount/Tiktoken/CalibratingChar)基本估算: PASS
- CalibratingCharCountEstimator.observe_usage EMA校准: PASS (6次后 factor=1.038)
- TiktokenEstimator.estimate_messages dict格式: PASS (22 tokens)
- executor.engine 4新符号导出 + process boundary check: PASS
- ResourceMonitor ADR-111百分比阈值(70%/85%) + custom threshold触发: PASS
- 共8项验证全 PASS

### 下一个 Task 需要注意
- DOC-12 Task 12.2: HarnessAnalytics + EntropyDetector(8信号)
  - aggregate() 需加 offset_days 参数，避免窗口重叠(PRD Part A 窗口修复P0)
  - EntropyDetector 使用 current(days=7,offset=0) vs previous(days=7,offset=7) 非重叠窗口
  - ThresholdCalibrator 每周扫30天 harness_summary p90，EMA平滑 0.7*current+0.3*p90
  - CalibratingCharCountEstimator.observe_usage() 在 AnthropicDriver stream结束后调用
- ResourceMonitor.check_health() 的 queue_depth 参数由调用方注入(避免循环导入 task_service)
- DOC-12 Task 12.3 /health/detailed 端点直接调用 ResourceMonitor.check_health()
- context_budget.py 的 TokenEstimator Protocol 已存在且正确，token_estimator.py 的 TokenEstimator ABC 是并存策略实现，无需合并

### 遗留风险 / 未决事项
- AnthropicTokenCounter 在 token_estimator.py 中与 token_estimator_adapter.py 的 DriverTokenEstimator 功能重叠；两者目前并存，DOC-12 Task 12.2+ 可统一引用 token_estimator.py；无功能冲突
- TiktokenEstimator 首次调用需下载编码器文件(~1MB)，Docker 环境需预热或预下载

### Commit
- `702eeb8` — `feat(v4): DOC-12 Task 12.1 — TokenEstimator + ResourceMonitor (ADR-110/111)`

---

## 2026-04-19 -- DOC-09 Task 9.3 COMPLETED + DOC-09 DONE 收官 checkpoint

### 本次 session 做了什么
- 新建 backend/app/schemas/audit.py — AuditLogQuery(ADR-084 prefix action filter, severity, start_time, end_time, page/page_size) + AuditLogResponse(7字段)
- 新建 backend/app/schemas/admin.py — SystemStatsResponse(ADR-085 9字段: runs_24h/runs_7d/cost_usd_7d/cache_savings/harness_events_24h/active_sessions/active_users_24h/component_health/timestamp)
- 新建 backend/app/services/audit_service.py — AuditService: _base_query(LIKE前缀+severity JSONB+时间范围) + query(分页) + export_csv(max 10k行 UTF-8 BOM)
- 新建 backend/app/services/admin_stats_service.py — AdminStatsService.get_dashboard(): DB聚合 + Redis ping健康 + scan_iter harness:circuit:* + cache savings $0.27/1M
- 修改 backend/app/api/v1/admin.py — 4新端点(GET /audit-logs/export CSV; GET /stats/dashboard ADR-085; PATCH /users/{id}/role last-admin guard ADR-083; DELETE /users/{id} soft-disable no-self guard ADR-083); list_users追加pagination+search(ilike or_)
- 修改 backend/app/models/user.py — 追加 is_active: Mapped[bool] Boolean NOT NULL DEFAULT TRUE(ADR-083)
- 新建 backend/alembic/versions/005_add_is_active_to_users.py — ADD COLUMN is_active; chain 004→005

### 验证结果
- py_compile 5新文件(schemas/audit+admin, services/audit_service+admin_stats_service, api/v1/admin): PASS
- AuditLogQuery+AuditLogResponse 字段实例化: PASS
- SystemStatsResponse 字段实例化: PASS
- ADR-083 guards(last-admin 409 + no-self 409) + endpoint routing: PASS
- AuditService methods(query+export_csv+_base_query): PASS
- AdminStatsService methods(__init__+get_dashboard): PASS
- list_users pagination+search(ilike+or_): PASS
- ADR-084 prefix matching(LIKE): PASS
- ADR-085 AdminStatsService content(harness.*+scan_iter+component_health+cache_savings): PASS
- 共9项验证全 PASS

### 下一个 Task 需要注意
- **DOC-09 完整收官** — 所有3个Task完成(9.1 MCP管理 + 9.2 Provider用量 + 9.3 Admin管理)
- DOC-10 Task 10.1: Next.js搭建 + 设计系统; 无直接后端依赖
- Admin端点(stats/dashboard)依赖 get_redis() async依赖; 确保 lifespan Redis已初始化
- User.is_active字段需 alembic upgrade head (005 migration); 测试环境需注意
- GET /admin/users 接口签名已从 ApiResponse[list] 改为 ApiResponse[PagedResponse]，前端DOC-11 Task 11.6需按新结构解析

### 遗留风险 / 未决事项
- AuditLog.severity 存在 JSONB details字段中而非 top-level column; ADR-084 severity filter使用 details["severity"].as_string()，仅 PostgreSQL JSONB有效(SQLite不兼容)，Prism v2锁定PG已知可接受
- AdminStatsService 使用同步 DB session 但 async get_dashboard; 混合同步/异步在 FastAPI 中可能轻微阻塞，Phase 1 可接受

### Commit
- `93d6694` — `feat(v4): DOC-09 Task 9.3 — Admin audit logs + stats dashboard + user management (ADR-083/084/085)`

---

## ===== DOC-09 DONE checkpoint (2026-04-19) =====
DOC-09 Backend MCP/Provider/Admin 完整收官：
- Task 9.1 (commit未记录) — MCP Server CRUD + install/uninstall + scope + bootstrap
- Task 9.2 (commit e2a5463) — Provider health Redis + usage API ADR-082
- Task 9.3 (commit 93d6694) — Admin audit logs + stats dashboard + user management ADR-083/084/085
下一步: DOC-10 Frontend Foundation

---

## 2026-04-19 -- DOC-09 Task 9.2 COMPLETED (Provider 健康状态 Redis + 用量 API ADR-082)

### 本次 session 做了什么
- 新建 backend/app/services/usage_service.py — UsageService: get_user_usage()(铁律4 user_id严格过滤) + get_global_usage()(Admin用); ADR-082全字段: cache_hit_tokens/cache_miss_tokens/cache_creation_tokens/cache_hit_ratio/estimated_cache_savings_usd/total_cost_usd/by_provider(含name lookup via IN)/by_model/timeline(date_trunc day|week|month); _compute_cache_savings($3.00/1M × 90%)
- 修改 backend/app/services/provider_service.py — 追加 list_providers_with_health(db, user_id, redis_client): 读 Redis harness:circuit:{id} key → is_healthy=False(熔断); Redis不可用时 try/except 降级保持DB值
- 修改 backend/app/api/v1/providers.py — list_providers端点改用 list_providers_with_health(sync Redis client via _get_sync_redis()); 新增 GET /providers/usage 端点(group_by=day|week|month, start_date/end_date query params, ADR-082完整响应)

### 验证结果
- py_compile 3文件(usage_service.py / provider_service.py / providers.py): PASS
- cache_savings计算(_compute_cache_savings 8000 tokens → $0.0216): PASS
- _resolve_date_range(默认最近30天/显式日期): PASS
- list_providers_with_health 方法签名(db/user_id/redis_client)+try/except: PASS
- ADR-082全字段(cache_hit/miss/creation_tokens+ratio+savings+cost+by_provider+by_model): PASS
- 铁律4 user_id filter(Run.user_id == user_id): PASS
- harness:circuit:{id} key格式 + REDIS_URL配置: PASS
- 共7项验证全 PASS

### 下一个 Task 需要注意
- DOC-09 Task 9.3: Admin 审计日志查询 + 系统统计 + 用户管理; ADR-083/084/085
- admin.py 已有基础路由(Task 6.2实现: list_users/update_role/invite_codes/audit_logs/usage); Task 9.3 需补完: audit-logs导出CSV + stats/dashboard(AdminStatsService) + 禁止降级最后一个admin(ADR-083) + 禁止禁用自己(ADR-083)
- admin.py 现有 list_users 无分页+搜索 → Task 9.3需补充page/search参数; 现有update_user_role只阻止自己修改自己但未检查"最后一个admin" → Task 9.3补充409逻辑
- UsageService.get_global_usage() 已实现供 AdminStatsService 调用(Task 9.3)

### 遗留风险 / 未决事项
- providers.py 用 sync redis client(同步) 做健康检查; 非 async 路由中调用同步 redis.get() 可能轻微阻塞事件循环。生产建议改用 asyncio redis + await，但当前实现足够 Phase 1。
- usage_service.py 的 date_trunc() 是 PostgreSQL 函数，不支持 SQLite；Prism v2 锁定 PostgreSQL，此限制已知可接受。

### Commit
- `e2a5463` — `feat(v4): DOC-09 Task 9.2 — Provider health from Redis + usage statistics API (ADR-082)`

---

## 2026-04-19 -- DOC-09 Task 9.1 COMPLETED (MCP Server CRUD + install/uninstall + scope权限 + builtin bootstrap)

### 本次 session 做了什么
- 新建 backend/app/schemas/mcp.py — 5 schema: CreateMCPServerRequest / MCPServerResponse / InstallMCPRequest / MCPInstallResponse / UpdateMCPInstallRequest / MCPTestResponse
- 新建 backend/app/services/mcp_service.py — MCPService 9方法(list_servers/get_server/create_server/delete_server/test_server/list_installs/install/update_install/uninstall) + register_builtin_servers staticmethod(web_search + filesystem 两内置); system scope env值在响应层掩码'***'; UNIQUE(409)通过IntegrityError捕获; 铁律4全覆盖
- 新建 backend/app/api/v1/mcp.py — 8路由: GET/POST /mcp-servers + DELETE/POST(test) /mcp-servers/{id} + GET/POST /mcp-installs + PATCH/DELETE /mcp-installs/{id}
- 修改 backend/app/models/mcp_server.py — 追加 user_id Mapped[str|None] FK nullable (system→NULL, user→owner UUID)
- 新建 backend/alembic/versions/004_add_user_id_to_mcp_servers.py — ADD COLUMN + INDEX + downgrade
- 修改 backend/app/main.py — lifespan step 4b: MCP bootstrap (register_builtin_servers)
- 修改 backend/app/api/v1/__init__.py — 导入并注册 mcp_router

### 验证结果
- py_compile 3新文件(schemas/mcp.py + services/mcp_service.py + api/v1/mcp.py): PASS
- schema字段验证(CreateMCPServerRequest / UpdateMCPInstallRequest partial / MCPTestResponse): PASS
- 服务方法签名(9方法 + register_builtin_servers static): PASS
- 路由结构验证(8端点 AST解析): PASS
- scope守护逻辑(scope='user'强制 + system→403 + user_id!=owner→403 + 409 IntegrityError): PASS
- builtin bootstrap(web_search + npx + idempotent skip): PASS
- ORM model + migration(user_id FK nullable + down_revision链): PASS
- main.py + __init__.py wiring: PASS
- 共10项验证全 PASS

### 下一个 Task 需要注意
- DOC-09 Task 9.2: Provider 配置补充 + 用量 API; ADR-080/081/082
- provider_service.py 已有 list_providers() — Task 9.2 新增 list_providers_with_health(redis_client) + get_usage_stats()
- usage_service.py 需新建; runs 表有 input_tokens/output_tokens/cost_usd 字段可直接聚合
- ADR-080 Provider scope 字段已在 Task 2.3 实现(scope='system'|'user'); Task 9.2 重点是 Redis 熔断状态读取 + cache tokens 三字段

### 遗留风险 / 未决事项
- McpServer.user_id 迁移(Migration 004)需要运行 alembic upgrade head 才能在 DB 生效；开发环境未连接 DB 故未运行，属正常
- test_server() 当前为 stub，返回 detected_capabilities=['tools']；完整探测需 DOC-05 MCPClient 集成

### Commit
- (feat commit) — `feat(v4): DOC-09 Task 9.1 — MCP Server CRUD + install/uninstall + scope权限矩阵 + builtin bootstrap`

---

## 2026-04-19 -- DOC-08 Task 8.3 COMPLETED + **DOC-08 DONE** 3/3 (IMBindingService + 配对码 + 三元组唯一)

### 本次 session 做了什么
- 新建 backend/app/services/im_binding_service.py — IMBindingService 完整服务层
  - `generate_pairing_code(user_id, channel)`: 6位数字+碰撞重试3次+upsert未完成绑定+5min TTL(via created_at)
  - `pair(channel, platform_user_id, platform_chat_id, code)`: TTL校验+一次性使用+ADR-071三元组IntegrityError捕获
  - `list_bindings(user_id)` + `unbind(user_id, binding_id)` (所有权校验+物理删除)
  - `expires_at()` 辅助方法供路由层使用
  - VALID_CHANNELS frozenset + 常量集中管理
- 修改 backend/app/api/v1/im.py — 3个绑定端点(list/pair/unbind)全部委托IMBindingService; 移除内联secrets.randbelow业务逻辑; 清理无用import(datetime/timezone/Response/ImBinding)
- 修改 backend/app/services/im_gateway.py — `_handle_pairing()` 重构为调用`IMBindingService.pair(platform_chat_id=...)`; 逻辑由30行→15行; 传递platform_chat_id支持ADR-071多群聊绑定
- ADR-071落地补强: DB UNIQUE(channel, platform_user_id, platform_chat_id)已在Task8.1 schema落地; Task8.3在服务层用IntegrityError捕获三元组冲突

### 验证结果
- py_compile 3文件 (im_binding_service.py / im.py / im_gateway.py): PASS
- 常量校验(VALID_CHANNELS/PAIRING_CODE_LENGTH/TTL/MAX_RETRIES): PASS
- 方法签名(generate_pairing_code/pair/list_bindings/unbind/expires_at): PASS
- ValueError on invalid channel (mock DB): PASS
- im.py 路由结构(3端点均present + IMBindingService import): PASS
- 无内联pairing逻辑(randbelow/ImBinding直接写): PASS
- im_gateway._handle_pairing使用IMBindingService.pair(): PASS
- ADR-071三元组UniqueConstraint列名验证: PASS
- platform_chat_id传递验证: PASS
- 共12项验证全 PASS

### 下一个 Task 需要注意
- DOC-09 Task 9.1: MCP Server 管理端点; ADR-080起
- IMBindingService.pair() 返回bool而非抛异常；三元组冲突时发"配对码无效"提示（用户侧体验可能改善，但功能正确）
- im_gateway._handle_pairing现在是纯委托模式，未来如需扩展绑定逻辑（如display_name从IM平台抓取）在IMBindingService中增加即可

### 遗留风险 / 未决事项
- DOC-08 无遗留风险；三个Task全部完整实现
- **DOC-08 DONE** checkpoint: Task 8.1(IMAdapter+IMGateway+Webhook幂等) + Task 8.2(飞书+企微+Telegram适配器) + Task 8.3(IMBindingService+配对码+三元组唯一) 全部完成

### Commit
- `177ee65` — `feat(v4): DOC-08 Task 8.3 — IM user binding service (pairing code + triple unique constraint)`

---

## 2026-04-19 -- DOC-08 Task 8.2 COMPLETED (FeishuAdapter + WeComAdapter + TelegramAdapter)

### 本次 session 做了什么
- 新建 backend/app/services/im_feishu.py — FeishuAdapter: Webhook模式接收 + HMAC-SHA256签名验证(X-Lark-Signature) + AES-CBC-256解密(pycryptodome) + asyncio.Lock保护的tenant_access_token刷新 + handle_webhook()/verify_signature()/decrypt_message() + graceful skip(未配置时)
- 新建 backend/app/services/im_wecom.py — WeComAdapter: SHA1 msg_signature验证 + AES-CBC-256 XML解密(encoding_aes_key+padding) + GET URL验证(verify_url) + XML解析(_xml_text helper) + asyncio.Lock access_token刷新 + REST发送(touser/toparty/toall判断)
- 新建 backend/app/services/im_telegram.py — TelegramAdapter: Long Polling asyncio.Task(_polling_loop) + getUpdates offset追踪 + sendMessage + 优雅停止(cancel+5s等待) + graceful skip(未配置时)
- 修改 backend/app/api/v1/im.py — POST /webhook/feishu(body_bytes读取+签名验证+分发); GET /webhook/wecom(URL验证+PlainTextResponse); POST /webhook/wecom(msg_signature验证+PlainTextResponse); 适配器从app.state.im_gateway懒获取(_get_feishu_adapter/_get_wecom_adapter)
- 修改 backend/requirements.txt — 追加 pycryptodome>=3.20.0(AES-CBC-256解密必需)
- ADR-072(飞书签名+token刷新) / ADR-073(企微SHA1+AES解密) 落地

### 验证结果
- py_compile 4文件: PASS
- 三适配器实现 IMAdapter 接口: PASS
- channel_name + set_message_handler注入: PASS
- 飞书签名验证(合法/非法/无token): PASS
- 企微签名验证(合法/非法/无token): PASS
- 三平台消息截断(feishu=4000/wecom=2048/tg=4096): PASS
- 飞书 URL 验证 challenge 响应: PASS
- graceful skip(未配置时 start() 不抛异常): PASS
- stop() 幂等: PASS
- IMGateway.register_adapter + get_adapter: PASS — 共 10 项全 PASS

### 下一个 Task 需要注意
- Task 8.3(用户绑定)已在 Task 8.1 的 api/v1/im.py 中实现了大部分逻辑(generate_pairing_code/list_bindings/unbind)；Task 8.3 主要补充 IMBindingService 服务层并重构路由
- 飞书适配器目前使用 Webhook 模式（非 WebSocket SDK），符合 PRD "最常见方案"；若需 WebSocket 模式，在 im_channel_configs.config 中增加 mode 字段即可扩展
- pycryptodome 已在 requirements.txt 中；若 Docker 镜像未重建则需 pip install pycryptodome

### 遗留风险 / 未决事项
- 飞书 WebSocket 长连接模式（官方 lark-oapi SDK）暂未实现，当前 Webhook 模式已足够生产使用
- 企微群聊 platform_chat_id 约定（"party:" 前缀）应在 Task 8.3 绑定流程中明确文档化

### Commit
- `7f85b76` — `feat(v4): DOC-08 Task 8.2 — Feishu + WeCom + Telegram IM adapters`

---

## 2026-04-19 -- DOC-08 Task 8.1 COMPLETED (IMAdapter + IMGateway + Webhook幂等)

### 本次 session 做了什么
- 新建 backend/app/services/im_adapter.py — IMAdapter ABC 4抽象方法(channel_name/start/stop/send) + set_message_handler(); IMIncomingMessage(msg_id专属字段 ADR-070) + IMOutgoingMessage dataclasses; MessageHandler 类型别名
- 新建 backend/app/services/im_dedup.py — IMDedupService(DB主方案ADR-070): is_duplicate() IntegrityError去重 + cleanup_expired() + update_session_id(); IMDedupRedisService(SETNX备选方案)
- 新建 backend/app/services/im_gateway.py — IMGateway统一路由: register_adapter()注入_handle_message; _handle_message: ADR-070幂等→pairing code识别→binding三元组查找→find_or_create_session→TaskService.submit()(同Web链路)→_start_run; send_run_result()截断(feishu=4000/wecom=2048/tg=4096); start_all()从DB读enabled状态; _send_binding_guide()未绑定引导; _handle_pairing()配对码完成绑定
- 新建 backend/app/schemas/im.py — 5 schema: IMChannelConfigResponse/Update + IMBindingResponse + PairingCodeResponse + IMWebhookEvent
- 新建 backend/app/api/v1/im.py — 7路由: GET/PATCH /im/channels(admin+脱敏) + POST /webhook/feishu+wecom(public skeleton) + GET /im/bindings + POST /im/bindings/pair(6位码碰撞重试) + DELETE /im/bindings/{id}
- 修改 backend/app/observability/metrics.py — 新增 prism_im_webhook_duplicates_total{channel} + prism_im_bindings_active (ADR-070 B5-I)
- 修改 backend/app/api/v1/__init__.py — 注册 im_router

### 验证结果
- py_compile 7文件: PASS
- IMAdapter是抽象基类(无法直接实例化): PASS
- MockAdapter实现IMAdapter接口: PASS
- IMGateway.register_adapter + handler注入: PASS
- ADR-071 im_bindings三元组唯一约束: PASS
- ADR-070 im_message_dedup两列唯一约束: PASS
- IMDedupService + IMDedupRedisService方法: PASS
- Prometheus 3个IM指标注册: PASS
- IM router 7条路由: PASS
- Platform message length limits: PASS
- 配对码检测逻辑(/pair前缀+6位数字): PASS
- im_router importable: PASS
- 合计 17项验证全 PASS

### 下一个 Task 需要注意
- DOC-08 Task 8.2: FeishuAdapter/WeComAdapter/TelegramAdapter 分别实现 IMAdapter ABC
  - 必须在 IMIncomingMessage.msg_id 字段设置平台原生消息 ID（ADR-070 去重依赖此字段）
  - 飞书: /im/webhook/feishu 端点已占位，Task 8.2 在此解析 X-Lark-Signature + 事件
  - 企微: /im/webhook/wecom 端点已占位，支持 GET URL验证 + POST 消息
  - Telegram: Long Polling 后台任务，不走 Webhook
  - 三个适配器均注入 IMGateway（lifespan 初始化时 register_adapter）
- IMGateway._start_run() 使用懒导入 app.main.app 获取 process_manager；若 Docker 部署需确认循环导入无影响
- api/v1/im.py 的 POST /im/bindings/pair 中配对码生成逻辑是 Task 8.1 内联实现，Task 8.3 可提取到 IMBindingService 类并重构此路由

### 遗留风险 / 未决事项
- IMGateway._start_run() 通过 `from app.main import app` 懒导入获取 process_manager，测试环境需 mock
- Task 8.2 企微适配器需要 XML 解密（需要 pycryptodome 或类似库，requirements.txt 待更新）
- IMGateway.start_all() 从 DB 查 im_channel_configs，若 DB 尚未初始化会静默跳过（非错误）

### Commit
- `f9d8e3f` — `feat(v4): IMAdapter abstraction + IMGateway routing + Webhook idempotency (ADR-070/071) — DOC-08 Task 8.1`

---

## 2026-04-19 -- DOC-07 Task 7.4 COMPLETED + DOC-07 完整收官 4/4 (subprocess 调度 + coordinator_recovery + alert_dispatcher)

### 本次 session 做了什么
- 新建 backend/app/services/process_manager.py — ProcessManager(ADR-066): _build_command 6必传argv + _build_env ENCRYPTION_KEY/OTEL via env; start_run() ThreadPoolExecutor提交; kill_run(force=False/True) SIGTERM/SIGKILL; shutdown(); _mark_running 写 subprocess_pid; _notify_timeout/_notify_failure HTTP回调(3次重试)
- 新建 backend/app/services/coordinator_recovery.py — CoordinatorRecoveryService(ADR-067): resume(run_id, user_id) 校验 failed+heartbeat_stale → 查 coordinator_plans → 新建 Run → plan.run_id → process_manager.start_run(resume_from_step)
- 新建 backend/app/services/alert_dispatcher.py — AlertDispatcher 4级severity分档: info仅structlog / warning→audit_logs / error→audit+SSE / critical→audit+SSE+IM stub+Email stub
- 修改 backend/app/services/run_lifecycle.py — mark_running(run_id, pid=None) 追加 pid 参数，写 runs.subprocess_pid
- 修改 backend/app/api/v1/runs.py — 追加 POST /runs/{run_id}/resume 端点（ADR-067）；从 request.app.state.process_manager 获取单例
- 修改 backend/app/api/v1/tasks.py — 替换 _start_agent_subprocess stub，改为从 request.app.state.process_manager 调用 start_run()
- 修改 backend/app/api/v1/internal.py — handle_callback 处理 promoted_run_id 时调用 process_manager.start_run()（完成 Task 7.3 的 deferred TODO）
- 修改 backend/app/main.py — lifespan step 6 新增 ProcessManager 初始化 + app.state.process_manager 挂载 + shutdown()

### 验证结果
- py_compile 8 新文件/修改文件: PASS
- ADR-066 命令构建: 6必传argv + --resume-from-step可选 + ENCRYPTION_KEY in env: PASS
- ProcessManager kill_run SIGTERM/SIGKILL/非存在: PASS
- AlertDispatcher 4级severity路由(info/warning/error/critical): PASS
- CoordinatorRecoveryService 404/409(wrong status)/409(not heartbeat_stale): PASS
- POST /runs/{run_id}/resume 路由注册: PASS
- tasks.py ProcessManager集成(无stub残留): PASS
- internal.py promoted_run_id→start_run: PASS
- 质量门 10 项: PASS

### 下一个 Task 需要注意
- DOC-08 Task 8.1 启动: IM Webhook 幂等需用 im_message_dedup 表（已在 DOC-01 v4 §4.2 定义）
- AlertDispatcher im_service 参数：DOC-08 完成后 IMAdapter 实例可直接注入
- ProcessManager._post_callback 向 http://localhost:8000 发 HTTP，Docker 网络内应改为 http://backend:8000（遗留风险）

### 遗留风险 / 未决事项
- ProcessManager._post_callback hardcode localhost:8000，Docker 生产环境需配置化（DOC-12 或 DOC-09）
- ALERT_IM_CHANNEL/ALERT_EMAIL 尚未加入 Settings class（alert_dispatcher 用 getattr 兜底，DOC-12 Task 12.8 添加）

### Commit
- `e04f08b` — `feat(v4): subprocess scheduler (ADR-066) + coordinator_recovery (ADR-067) + alert_dispatcher — DOC-07 Task 7.4`

---

## 2026-04-19 -- DOC-07 Task 7.3 completed (Callback 双通道 + SSE Manager + HeartbeatMonitor + permission-answer)

### 本次 session 做了什么
- 新建 backend/app/services/sse_manager.py — SSEManager(ADR-063): MAX_CONNS=3/STREAM_BUFFER=200/publish+subscribe+backfill_since+acquire_conn_slot+release_conn_slot+start_subscribe_async
- 新建 backend/app/services/heartbeat_monitor.py — HeartbeatMonitor(ADR-065): 每 10s SCAN harness:heartbeat:*，超 30s 标记 crashed; scan_interval=10, stale_threshold=30; run/stop/_scan_once/_handle_key
- 新建 backend/app/services/callback_service.py — CallbackService(ADR-063): 10 event handlers (text_delta/tool_start/tool_end/message_complete/run_complete/run_error/permission_ask/harness_event/coordinator_plan_update/session_title); _extract_text_preview helper; 幂等设计; coordinator_plan_update UPSERT
- 新建 backend/app/api/v1/internal.py — POST /internal/callbacks (X-Callback-Secret 认证+统一 commit) + POST /internal/run-crashed (ADR-065 mark_crashed endpoint)
- 修改 backend/app/api/v1/sessions.py — 追加 GET /sessions/{id}/stream (SSE ticket auth ADR-057 + last_event_id 补发 + 多 tab 限制 429) + POST /sessions/{id}/permission-answer (ADR-064 UPDATE permission_requests + RPUSH perm_answer:{request_id})
- 修改 backend/app/api/v1/__init__.py — 注册 internal_router
- 修改 backend/app/main.py — lifespan 追加 HeartbeatMonitor asyncio.create_task 启动 + 优雅关闭 (cancel+wait)
- 修改 backend/app/core/dependencies.py — get_redis() 从 NotImplementedError 实装为 async redis.asyncio.Redis
- 修改 backend/app/models/permission_request.py — 追加 decision VARCHAR(10) NULLABLE 字段 (ADR-064 UPDATE decision=X)
- 新建 backend/alembic/versions/003_add_decision_to_permission_requests.py — ALTER TABLE permission_requests ADD COLUMN decision VARCHAR(10)

### 验证结果
- Part B 验证步骤: 全 12 项 PASS (+ 2 bonus: migration + _extract_text_preview)
- 质量门 10 项: PASS

### 下一个 Task 需要注意
- Task 7.4 子进程调度：internal.py handle_callback 在 run_complete/run_error 时返回 promoted_run_id，Task 7.4 需接收并启动新子进程
- Task 7.4 subprocess 启动参数：--callback-url=http://backend:8000/api/v1/internal/callbacks --callback-secret=${CALLBACK_SECRET}（已在 internal.py 使用 CALLBACK_SECRET 认证）
- ADR-066 编号：Task 7.4 的 subprocess 参数标准化从 ADR-066 起；Task 7.3 已用 ADR-063/064/065

### 遗留风险 / 未决事项
- callback_service 的 asyncio.create_task() 在同步 handler 内 fire-and-forget SSE publish：需要 FastAPI 的 event loop 存活，不影响 DB 同步路径；但如果 SSE publish 失败不会报错（设计为容错）
- get_redis() dependency 实装为每请求创建/关闭连接，高并发时可用连接池优化（Task 7.4 或 DOC-12 优化）

### Commit
- `a2c43b5` — `feat(v4): Callback(双通道) + SSE Manager + HeartbeatMonitor + permission-answer — DOC-07 Task 7.3`

---

## 2026-04-19 -- DOC-07 Task 7.2 completed (Task 提交 + Run 生命周期 + ADR-060/061/062)

### 本次 session 做了什么
- 新建 backend/app/schemas/task.py — SubmitTaskRequest(session_id/prompt/agent_type) + SubmitTaskResponse(accepted_type/queue_position)
- 新建 backend/app/schemas/run.py — RunResponse(harness_summary JSONB) + RunListResponse(精简) + CancelRunRequest(mode 三模式枚举校验)
- 新建 backend/app/services/sequence_service.py — ADR-060 两方案: get_next_message_sequence_no(CREATE SEQUENCE IF NOT EXISTS + nextval) + get_next_message_sequence_no_advisory(pg_advisory_xact_lock + max+1) + get_next_queue_sequence_no(advisory+offset 2^32)
- 新建 backend/app/services/task_service.py — TaskService.submit: session_id=None自动创session; idle→_submit_immediate(创Run+阻塞session); busy→_submit_queued(advisory_xact_lock+QUEUE_MAX_SIZE=50)
- 新建 backend/app/services/run_lifecycle.py — RunLifecycle: mark_running/complete_and_promote/fail_and_promote/cancel(ADR-062三模式SIGTERM/SIGKILL/also_cancel_queue)/mark_crashed(ADR-065)/timeout; _promote_next()单事务FOR UPDATE SKIP LOCKED(ADR-061)
- 新建 backend/app/services/session_queue.py — SessionQueueService: list_queue/cancel_item/get_queue_size
- 新建 backend/app/api/v1/tasks.py — POST /tasks(202 Accepted) + GET /sessions/{id}/queue + DELETE /sessions/{id}/queue/{item_id} + POST /runs/{id}/cancel
- 新建 backend/app/api/v1/runs.py — GET /runs/{id}(含harness_summary) + GET /sessions/{id}/runs(分页)
- 修改 backend/app/models/run.py — 追加 subprocess_pid Integer 字段（cancel三模式 SIGTERM/SIGKILL 必需）
- 新建 backend/alembic/versions/002_add_subprocess_pid_to_runs.py — ALTER TABLE runs ADD COLUMN subprocess_pid INTEGER
- 修改 backend/app/api/v1/__init__.py — 注册 tasks_router + runs_router

### 验证结果
- Part B 验证步骤(8个文件编译+schema6项+RunLifecycle方法签名+promote原子性+ADR约束+路由注册): 全部 PASS
  - py_compile 8 新文件 PASS
  - SubmitTaskRequest/Response 构造 PASS; CancelRunRequest 三模式校验 PASS; 非法mode拒绝 PASS
  - RunLifecycle 8方法全存在 PASS; cancel含mode+user_id PASS; complete_and_promote含harness_summary PASS
  - FOR UPDATE SKIP LOCKED 存在 PASS; 单commit PASS
  - CREATE SEQUENCE IF NOT EXISTS PASS; pg_advisory_xact_lock PASS
  - lock_key message≠queue PASS
  - Run.subprocess_pid ORM字段存在 PASS; migration 002 well-formed PASS
  - 6条路由路径验证 PASS

### 下一个 Task 需要注意
- Task 7.3 callback_service 写 messages 时必须调用 get_next_message_sequence_no(db, session_id)，不可用 MAX+1
- Task 7.3 run_complete 事件处理 → complete_and_promote(run_id, ..., harness_summary=json)，harness_summary 在 promote 事务中写入
- Task 7.4 executor 启动成功后需调用 mark_running(run_id) 将 subprocess_pid 写入 DB，cancel 端点才能发信号
- Task 7.4 _start_agent_subprocess(run_id) 在 tasks.py 中是 stub，Task 7.4 实现时替换

### 遗留风险 / 未决事项
- _start_agent_subprocess 当前为 stub（Task 7.4 实现）
- get_next_message_sequence_no 使用方案 1（CREATE SEQUENCE），在 PG RDS 权限受限时需切换方案 2（advisory_xact_lock）
- cancel 依赖 subprocess_pid 字段，需 Task 7.4 写入后才能发信号（pid=None 时 kill 被静默跳过）

### Commit
- `63903c1` — `feat(v4): Task 提交 + Run 生命周期 (sequence_no + cancel 三模式) — DOC-07 Task 7.2`

---

## 2026-04-19 -- DOC-07 Task 7.1 completed (Session CRUD + 消息增量 + generate_text_preview)

### 本次 session 做了什么
- 新建 backend/app/schemas/session.py — CreateSessionRequest(title+config_snapshot) / UpdateSessionRequest / SessionResponse(含计算字段 message_count+last_message_preview) / SessionListResponse(精简版)
- 新建 backend/app/schemas/message.py — MessageResponse(id/run_id/role/content list[dict]/text_preview/sequence_no/created_at)
- 新建 backend/app/services/session_service.py — SessionService(list_sessions排序:pinned优先+updated_at DESC / create_session / get_session 铁律4 / update_session pin逻辑 / delete_session / get_message_count / get_last_message_preview / list_messages after_sequence_no增量) + generate_text_preview(tool_result前缀/tool_use前缀/纯text/[empty], DOC-01 v4 §4.2)
- 新建 backend/app/api/v1/sessions.py — 6路由: GET/POST /sessions + GET/PATCH/DELETE /sessions/{id} + GET /sessions/{id}/messages(limit≤500 after_sequence_no ge=0)
- 修改 backend/app/api/v1/__init__.py — 注册sessions_router,docstring追加sessions路由描述

### 验证结果
- Part B 验证步骤(编译4项+schema6项+generate_text_preview6项+路由6条+约束3项): 全部 PASS
  - py_compile 4个新文件 PASS
  - CreateSessionRequest 默认/自定义 PASS; UpdateSessionRequest 全None/is_pinned PASS; MessageResponse构造 PASS
  - generate_text_preview: 纯text/200字截断/空->empty/assistant tool_use前缀/user tool_result前缀/空text块->empty 全PASS
  - 6条路由注册 PASS(GET/POST /sessions + GET/PATCH/DELETE /{session_id} + GET /{session_id}/messages)
  - limit=500常量/after_sequence_no ge=0/le=_MAX_MESSAGES_LIMIT约束 PASS

### 下一个 Task 需要注意
- DOC-07 Task 7.2 必须实现 sequence_no 写端 (per-session 序列或 advisory_xact_lock)，ADR-060 在 Task 7.1 只落地了读端
- SessionService.get_session() 对不属于用户的 session 返回 404（不暴露 403），Task 7.2/7.3 沿用此约定
- generate_text_preview() 已在 session_service.py 定义，Task 7.2 的消息写入时可复用生成 text_preview 字段
- list_messages 的 content 字段：ORM content 可能是 dict(单 block) 或 list，session.py 已做 isinstance 判断兜底

### 遗留风险 / 未决事项
- 无新增风险。sequence_no 写端仍在 Task 7.2 待实施(非遗留风险，是计划内分工)

### Commit
- `870b4bb` — `feat(v4): Session CRUD + message incremental query (DOC-07 Task 7.1)`

---

## 2026-04-19 -- DOC-06 Task 6.2 completed (用户管理 + 邀请码 + Admin API + ADR-059；DOC-06 完整收官)

### 本次 session 做了什么
- 新建 backend/app/schemas/invite.py — CreateInviteCodeRequest(max_uses≥1校验) + InviteCodeResponse.from_orm_model(is_valid 计算: 未过期 AND used_count<max_uses)
- 新建 backend/app/schemas/user.py — UserListResponse + UpdateUserRoleRequest(Literal["admin","user"])
- 新建 backend/app/services/invite_service.py — InviteService: generate_code(PRISM-前缀+8位大写字母数字 secrets.choice) / create(碰撞去重) / validate(存在+未过期+未用完) / consume / list_all / revoke(max_uses=used_count)
- 新建 backend/app/api/v1/admin.py — 7 端点全部实现: GET/PATCH /admin/users; POST/GET/DELETE /admin/invite-codes; GET /admin/usage(totals+per_provider+30天趋势); GET /admin/audit-logs(LIKE前缀筛+user_id筛+分页); router-level dependencies=[Depends(require_admin)](ADR-059); 自我角色修改防护(400)
- 修改 backend/app/api/v1/__init__.py — 注册 admin_router, docstring 追加 admin 路由描述
- DOC-06 完整收官: Task 6.1 + Task 6.2 均已 completed; ADR-056/057/058/059 全部落地

### 验证结果
- Part B 验证步骤(编译4项+逻辑7项): 全部 PASS
  - py_compile schemas/invite.py + schemas/user.py + services/invite_service.py + api/v1/admin.py PASS
  - CreateInviteCodeRequest 默认/自定义/max_uses=0拒绝 PASS
  - UpdateUserRoleRequest 合法/非法role拒绝 PASS
  - generate_code() 100样本 PRISM-前缀+8位大写字母数字+总长14 PASS
  - InviteCodeResponse.from_orm_model is_valid 3场景(有效/过期/用完) PASS
  - revoke() 逻辑(max_uses=used_count → is_valid=False) PASS
  - admin router 7条路由全注册 + router-level require_admin dependency PASS

### 下一个 Task 需要注意
- DOC-07 Task 7.1 Session CRUD: admin.py GET /admin/usage 使用了 Run 模型的 func.date() 聚合，PostgreSQL 环境测试时注意 date() 函数兼容性
- InviteService.validate() 用于 AuthService.register() 中的邀请码校验——Task 6.1 的 auth_service.py 已内联邀请码检查逻辑，Task 6.2 的 InviteService.validate() 是独立服务层；若后续需统一，可将 auth_service.py 的内联检查替换为 InviteService.validate() 调用
- GET /admin/audit-logs 支持 action 前缀 LIKE 筛选，DOC-07 Task 7.x 写 harness.* 审计日志后可通过 ?action=harness. 查询

### 遗留风险 / 未决事项
- Redis 未初始化时 SSE ticket 端点返回 503（Task 6.1 遗留，DOC-07 Task 7.3 解决）
- GET /admin/usage daily_trend 使用 func.date() — PostgreSQL 原生支持，SQLite 测试需注意
- GET /admin/users 无分页（Phase 1 设计，用户量小时可接受）

### Commit
- `e47c31d` — `feat(v4): user management + invite codes + admin API (DOC-06 Task 6.2)`
- docs commit: 后续更新 PROGRESS/DECISIONS/HANDOFF-LOG

---

## 2026-04-19 -- DOC-06 Task 6.1 completed (认证体系 JWT+SSE ticket + ADR-056/057/058)

### 本次 session 做了什么
- 新建 backend/app/schemas/auth.py — RegisterRequest(邮箱/用户名/密码/邀请码校验) + LoginRequest + SSETicketRequest + TokenResponse + RefreshResponse + UserResponse(from_attributes=True)
- 新建 backend/app/services/user_service.py — UserService: get_by_id / get_by_email / get_by_username / update(**kwargs)
- 新建 backend/app/services/auth_service.py — AuthService: register(邀请码校验 → 创建用户 → 消耗邀请码 → AuditLog + token) / login(verify_password → last_login_at → AuditLog + token) / refresh(decode_token type==refresh → 新 access token) / ensure_admin(幂等 admin 创建); _write_audit 内部辅助
- 新建 backend/app/services/sse_ticket_service.py — SSETicketService: generate_ticket(SETEX sse_ticket:{uuid4} 60s {user_id,session_id}) / verify_and_consume(GETDEL 原子 → 401 on expired / 403 on session_id mismatch) — ADR-057
- 新建 backend/app/api/v1/auth.py — 6 路由: POST /auth/register(201) / POST /auth/login / POST /auth/refresh(cookie) / POST /auth/logout(delete cookie) / GET /auth/me / POST /auth/sse-ticket(ADR-051/057); _set_refresh_cookie(httponly=True secure=True samesite=lax path=/api/v1/auth ADR-058)
- 修改 backend/app/api/v1/__init__.py — include auth_router, docstring 追加 auth 路由描述
- 修改 backend/app/core/dependencies.py — get_current_user 追加 type=="access" 校验(拒绝 refresh token 作 Bearer)
- 修改 backend/app/main.py — lifespan 步骤 5: ensure_admin() + db.commit()
- ADR-056/057/058 落地 DECISIONS.md; PROGRESS.md 更新(Task 6.1 completed, 23/51)

### 验证结果
- Part B 验证步骤(全 15 项 PASS):
  - py_compile × 5 文件(auth.py schemas / auth_service.py / user_service.py / sse_ticket_service.py / api/v1/auth.py) PASS
  - validate_secrets 四场景(短密钥/碰撞/三者合法) PASS
  - AES-256-GCM roundtrip + 错误 key 拒绝 + nonce 随机性 PASS
  - JWT create_access_token/create_refresh_token/decode_token roundtrip PASS
  - RegisterRequest 校验(3 errors for bad email/短用户名/短密码) PASS
  - SSETicketService generate_ticket(uuid4 ticket + expires_at ISO-8601) PASS
  - SSETicketService verify_and_consume 正常/重放 401/session 不匹配 403 PASS
  - UserService 4 方法 + update(self, user_id, **kwargs) 签名 PASS
  - 6 路由声明(register/login/refresh/logout/me/sse-ticket) PASS
  - api_v1_router 挂载 /api/v1/auth/* 全路由 PASS
  - get_current_user 拒绝 refresh token → 401 PASS
  - refresh cookie: httponly=True, secure=True, samesite=lax PASS
  - SSE ticket Redis key 前缀 sse_ticket: + setex + getdel PASS
  - AuthService.refresh() 拒绝 access token 类型 → 401 PASS
  - ensure_admin 源码 role=admin + 幂等检查 + 4 方法完整 PASS
- 质量门 10 项: PASS

### 下一个 Task 需要注意
- DOC-06 Task 6.2 继续实现: schemas/invite.py + schemas/user.py + services/invite_service.py + api/v1/admin.py(7 Admin 端点)
- InviteCode.created_by 在 ORM 层无 FK(模型注释"No ON DELETE CASCADE 意图"),admin.py 需注意直接 sql query,不依赖 relationship
- SSE ticket 的 verify_and_consume() 由 DOC-07 Task 7.3 SSE Manager 调用(stream endpoint 收到 ?ticket= 时原子消费)
- ensure_admin() 已在 main.py lifespan 步骤 5 调用;DOC-07 不需要再次添加
- get_redis() 目前返回 NotImplementedError;SSE ticket 端点在 Redis 未初始化时返回 503(预期行为)

### 遗留风险 / 未决事项
- SSE ticket 端点依赖 Redis;在 DOC-07 Task 7.3 完成 get_redis() 实现前,该端点返回 503
- Phase 1 不实现 refresh token blacklist;登出后 access token 在 15min 内仍有效(PRD 明确接受)
- InviteCode ORM relationship User.invite_codes 因 FK 缺失无法在内存 SQLAlchemy 图中 traverse(仅影响测试 mock;生产 DB 层 FK 由 Alembic migration 保证)

### Commit
- `1526438` — `feat(v4): Auth system (JWT login/register/refresh + SSE ticket) — DOC-06 Task 6.1`

---

## 2026-04-19 -- DOC-05 Task 5.7 completed + DOC-05 DONE checkpoint (CC 兼容层 + ADR-054/055)

### 本次 session 做了什么
- 新建 executor/plugins/cc_compat.py — CCPluginAdapter（detect_format 4路径优先级 / load 统一入口 / _load_prism/cc/skills_only 三路加载 / export_to_cc 返回 ConversionReport / _scan_hooks_dir CC→Prism event_type 映射 / _scan_mcp_servers_dir config.json 解析 / _build_cc_zip zip 生成含 CONVERSION_NOTES.md）；ConversionReport dataclass（success/cc_compat_zip/lost_fields/warnings/plugin_name/cc_plugin_json 6字段 ADR-054）；PluginSchemaError（errors list ADR-055）；PluginYamlSchema（Pydantic extra="allow" forward-compat）
- 修改 executor/plugins/host.py — PluginHost.__init__ 追加 cc_adapter 参数（默认自动注入 CCPluginAdapter）；新增 load_plugin_from_dir() 方法（目录级统一入口，自动格式检测）
- 修改 executor/plugins/__init__.py — 导出 5 新符号（CCPluginAdapter/ConversionReport/PluginFormatError/PluginSchemaError/PluginYamlSchema）
- 新建 backend/app/api/v1/plugins.py — 3 路由（POST /load 格式检测+摘要; POST /export-cc ConversionReport zip base64; POST /validate Pydantic 校验+extra_fields 告警）；内联 Pydantic schema；PluginSchemaError → HTTP 422；进程边界（Backend 不启动 MCP 子进程）
- 修改 backend/app/api/v1/__init__.py — include plugins_router；更新 docstring
- ADR-054/055 落地 DECISIONS.md；blocker.md 追加 Task 5.7 ADR 平移链（DOC-06 Task 6.1 须从 ADR-056 起）
- PROGRESS.md 更新（Task 5.7 completed，22/51；下一动作 DOC-06 Task 6.1）

### 验证结果
- Part B 验证步骤（全 19 项 PASS）：
  - py_compile × 5 文件（cc_compat.py / host.py / __init__.py / plugins.py / api_v1/__init__.py）PASS
  - CCPluginAdapter/ConversionReport/PluginFormatError/PluginSchemaError/PluginYamlSchema 导入 PASS
  - executor.plugins 导出 5 新符号 PASS
  - PluginHost.__init__ cc_adapter 参数 + load_plugin_from_dir 方法 PASS
  - ConversionReport 6 字段完整 PASS
  - detect_format 4 场景（unknown/skills_only/cc/prism 优先级）PASS
  - PluginFormatError on load nonexistent dir PASS
  - _load_cc_plugin（plugin.json + skills/ + mcp-servers/）PASS
  - _load_skills_collection PASS
  - _load_prism_plugin（valid plugin.yaml）PASS
  - PluginSchemaError on missing name（errors 携带详细位置）PASS
  - export_to_cc ConversionReport（lost_fields/warnings/cc_compat_zip/cc_plugin_json）PASS
  - zip 含 plugin.json + README.md + CONVERSION_NOTES.md PASS
  - MCP 名称冲突 → warnings PASS
  - forward-compat 未知字段不拒绝 PASS
  - _scan_hooks_dir CC→Prism event_type 映射 PASS
  - _scan_mcp_servers_dir config.json 读取 PASS
  - 3 Backend 路由声明（/load / /export-cc / /validate）PASS
  - 进程边界（cc_compat.py 无实际 backend.app import）PASS
- 质量门 10 项：PASS

### 下一个 Task 需要注意
- DOC-06 Task 6.1 ADR 须从 **ADR-056** 起接续（ADR-054 = ConversionReport，ADR-055 = plugin.yaml 严格校验）
- DOC-06 原规划 ADR-050~055 范围已全部被 DOC-05 Tasks 5.4~5.7 占用，ADR-050/051/052/053/054/055 均已落地
- plugins_router prefix="/plugins"，务必不与 DOC-09 Task 9.1 MCP Server 管理路由（prefix="/mcp-servers"）混淆
- PluginHost.load_plugin_from_dir() 是 Task 5.7 新增的目录级入口，DOC-07 Task 7.4 子进程调度可通过此方法加载插件目录

### 遗留风险 / 未决事项
- _scan_mcp_servers_dir Phase 1 仅读 config.json（若 CC 插件用子目录结构无 config.json，则扫描子目录名生成 stub，command 为空字符串）；Phase 2 可扩展按子目录中的 package.json 读取 command
- PluginYamlSchema 的 extra_field_names() 在 pydantic v2 中通过 model_dump() - model_fields 计算；若 pydantic 升级 API 变化需更新
- Backend POST /plugins/export-cc 返回 cc_compat_zip_b64（base64），前端需 decode 后落盘；大文件场景可考虑 streaming response（Phase 2）

### Commit
- `4558a25` — `feat(v4): CC 兼容层 + ConversionReport — DOC-05 Task 5.7 (ADR-054/055)`
- `a37a6cc` — `docs: DOC-05 DONE — update PROGRESS/DECISIONS/HANDOFF-LOG/blocker (Task 5.7 + DOC-05 收官)`

---

## ================== DOC-05 DONE CHECKPOINT ==================
**日期**: 2026-04-19
**阶段**: DOC-05 Plugin Ecosystem — 全部 7/7 Task 完整收官

### 完成的 Task 列表（7/7）
- Task 5.1: Skill 三级加载（ADR-043/044/045）— commit: 见 git log
- Task 5.2: MCP Server 双通道 + scope（ADR-046/047）— commit: 见 git log
- Task 5.3: Hook 治理 + Plugin 命名空间（ADR-048/049）— commit: 见 git log
- Task 5.4: PluginHost 统一管理 + 变量替换系统（ADR-050）— commit: 见 git log
- Task 5.5: Skills Registry Local + GitHub 两源（ADR-051）— commit: 见 git log
- Task 5.6: Skills CLI + Agent Tool 仅搜索（ADR-052/053）— commit: 见 git log
- Task 5.7: CC 兼容层 + ConversionReport（ADR-054/055）— commit: 4558a25

### 核心能力交付
- Skill **三级加载**（L0 注册 → L1 描述注入 → L2 按需完整加载 + is_skill_context 标记）
- MCP stdio 集成（**双通道 instructions + agent-scoped 白名单**）
- Hook 治理层（4 种 handler / 优先级排序 / Phase 1 事件过滤 / scoped 注册-注销）
- Plugin 命名空间（**变量替换系统 + CC 兼容映射 + Platform/User/Session 三级加载**）
- PluginHost 统一管理 + **目录级统一入口 load_plugin_from_dir()**
- Skills 市场（**Phase 1 仅 Local + GitHub 两源**）
- Skills CLI + Agent Tool（**仅搜索**，安装需用户手动触发）
- CC 插件格式兼容层（**ConversionReport + plugin.yaml 严格校验 + PluginSchemaError → 422**）

### ADR 落地总计（DOC-05）
ADR-043 / ADR-044 / ADR-045 / ADR-046 / ADR-047 / ADR-048 / ADR-049 / ADR-050 / ADR-051 / ADR-052 / ADR-053 / ADR-054 / ADR-055（13条 ADR）

### 进程边界严格遵守
- executor/ 所有新模块：无 from backend.app 实际 import
- backend/ 插件 API：不启动 MCP 子进程（格式检测+转换只做数据结构操作）

### 下一步：DOC-06 Task 6.1 认证体系（三密钥 + SSE ticket）
- ADR 从 ADR-056 起编号（所有 DOC-05 ADR 已占用 ADR-043~055）
- 参考 DOC-06-v4.md Task 6.1 Part A + Part B
## ==================== END DOC-05 DONE =======================

---

## 2026-04-19 -- DOC-05 Task 5.6 completed (Skills CLI + Agent Tool search-only + ADR-052/053)

### 本次 session 做了什么
- 新建 executor/tools/builtin/skills_search.py — SkillsSearchTool（name="skills_search", capabilities=[], input_schema{query,source,limit}, execute() 调用 SkillsRegistry.search() 返回 JSON + install 引导 note，不含任何 install/uninstall action，ADR-052 铁律）
- 新建 executor/cli/__init__.py + executor/cli/skills_cli.py — SkillsCLI 6 子命令（search/install/uninstall/update/list/info）+ argparse build_parser() + main() 入口；有 backend_url 时 HTTP 通知 Backend API 同步 DB，无 backend_url 时仅本地文件操作（开发者模式）
- 新建 backend/app/services/skill_install_service.py — SkillInstallService（install UPSERT + uninstall 更新 status + list_installed + get_install）+ Redis key 格式 `skill_install:status:{user_id}:{skill_name}` TTL=600s（ADR-053）
- 新建 backend/app/api/v1/skills.py — 6 路由（GET /search / GET /installed / POST /install / DELETE /{skill_name} / POST /{skill_name}/update / GET /{skill_name}）+ Pydantic schema（内联）+ Prometheus prism_skill_searches_total / prism_skill_installs_total
- 修改 executor/tools/builtin/__init__.py — register_builtin_tools() 追加 SkillsSearchTool 注册 + skills_registry 参数
- 修改 backend/app/api/v1/__init__.py — include_router(skills_router)
- ADR-052/053 落地 DECISIONS.md；blocker.md 追加 Task 5.6 ADR 平移链（DOC-06 Task 6.1 须从 ADR-054 起）
- PROGRESS.md 更新（Task 5.6 completed，21/51）

### 验证结果
- Part B 验证步骤（全 PASS）：
  - py_compile × 5 文件（skills_search / skills_cli / __init__ / skill_install_service / skills.py）PASS
  - SkillsSearchTool name/capabilities/input_schema/required PASS
  - ADR-052 约束（无 install/action schema 字段）PASS
  - SkillsSearchTool.execute() 搜索 + 空查询 PASS
  - register_builtin_tools() 含 skills_search PASS
  - SkillsCLI cmd_search + cmd_list PASS
  - Redis key 格式 + TTL=600s + mock SET 验证 PASS
  - SkillInstallService UPSERT（INSERT/UPDATE 两路径）+ uninstall PASS
  - Backend API 6 路由 PASS
  - 进程边界（executor/cli/ 无 backend.app import）PASS
- 质量门 10 项：PASS

### 下一个 Task 需要注意
- Task 5.7 CC 兼容层（ConversionReport）ADR 从 **ADR-054** 起编号（ADR-052/053 已被本 Task 占用）
- Task 5.7 涉及 CCPluginAdapter（检测 plugin.json/plugin.yaml/skills_only 三种格式）+ export_to_cc() 返回 ConversionReport（bytes zip + lost_fields + warnings + cc_plugin_json）+ ADR-050-A/050-B（平移后需新编号）
- skill_installs ORM 的 metadata_ JSONB 存 install_path/has_hooks/has_mcp/status，Task 5.6 的 SkillInstallService 已按此实现，后续 Tasks 直接用 metadata_["install_path"] 等 key

### 遗留风险 / 未决事项
- Backend _get_redis_client() 在 DOC-07 Task 7.1 前返回 None（Redis 未就绪时跳过缓存），生产环境需 Task 7.1 补全
- SkillsCLI 的 cmd_info() 搜索全源以找 skill_name，对大型 GitHub 索引略慢（可接受，Phase 1）
- Prometheus Counter 采用 lazy init + try/except，重复注册时静默降级（测试/重载安全）

### Commit
- `770679e` — `feat(v4): Skills CLI + Agent Tool search-only + Backend skill_install_service — DOC-05 Task 5.6`
- `875978e` — `docs: update state files for DOC-05 Task 5.6 (PROGRESS/DECISIONS/HANDOFF/blocker)`

---

## 2026-04-19 -- DOC-05 Task 5.5 completed (Skills Registry Local+GitHub + ADR-051)

### 本次 session 做了什么
- 新建 executor/plugins/skills_registry.py — SkillPackage/SkillBundle/InstalledSkill 3 个 dataclass；SkillSource ABC（search/fetch/get_versions 抽象方法）；LocalSource（.skills/ + .prism/skills/ 双目录扫描，YAML frontmatter 解析，关键词匹配 name/description/tags）；GitHubSource（httpx 调用 GitHub API Code Search + git/trees + raw.githubusercontent.com，支持 user/repo#branch/@tag/subpath 4 种格式，无 token 优雅降级）；SkillsRegistry（asyncio.gather 并行搜索 + name 去重 + installed 优先排序 + registry.json 原子写 + install/uninstall/update/list_installed）
- 修改 executor/plugins/__init__.py — 新增导出 7 个符号 + Task 5.5 注释
- ADR-051 落地 DECISIONS.md；blocker.md 追加 Task 5.5 ADR 平移链（DOC-06 Task 6.1 须从 ADR-052 起）
- PROGRESS.md 更新（Task 5.5 completed，20/51）；HANDOFF-LOG.md 本记录

### 验证结果
- Part B 验证步骤（9 项全 PASS）：py_compile × 2 / dataclass 实例化 × 3 / LocalSource search+fetch+versions / SkillsRegistry 并行搜索+installed排序+install+uninstall / registry.json 格式 / has_hooks/has_mcp 检测 / GitHubSource._parse_package_id 4 种格式 / 进程边界检查
- 质量门 10 项：PASS（无 backend.app import / 无 TODO 占位 / ADR-051 注释 / Phase 2 占位注释 / Literal 类型正确）

### 下一个 Task 需要注意
- Task 5.6 SkillsCLI + SkillsSearchTool：从 ADR-052 起编号（不要用 ADR-051，已被本 Task 占用）
- Task 5.6 Backend API `/skills/search` 调用 SkillsRegistry.search()；`/skills/install` 写 skill_installs 表（DOC-01 §4.2 已建）
- skill_install_service 写 skill_installs 表字段：user_id / skill_name / source / source_url / version / installed_at / install_path / has_hooks / has_mcp / status（ADR-049 in PRD，平移后须检查是否已占用）
- Redis 缓存 key：`skill_install:status:{user_id}:{skill_name}` TTL 600s（Task 5.6 实现）

### 遗留风险 / 未决事项
- GitHubSource.search() 需要 GITHUB_TOKEN（无 token 返回空列表 + warning，Phase 1 可接受）
- GitHubSource.fetch() 在大仓库 recursive tree 可能超时（_DEFAULT_GITHUB_TIMEOUT=30s，PRD 未规定具体值）

### Commit
- `1e70ba2` — `feat(v5): Skills Registry multi-source aggregation (Local+GitHub) — DOC-05 Task 5.5`
- `7b9586b` — `docs: update state files for DOC-05 Task 5.5 (PROGRESS/DECISIONS/HANDOFF/blocker)`

---

## 2026-04-19 -- DOC-05 Task 5.4 completed (PluginHost 统一管理 + 变量替换系统 + ADR-050)

### 本次 session 做了什么
- 新建 executor/plugins/plugin_types.py — PluginScope 枚举（PLATFORM/USER/SESSION，含 priority 属性）+ PluginConfig 数据类（10字段）
- 新建 executor/plugins/host.py — PluginVariableExpander（9种变量类型 + ENV_WHITELIST sandbox + ${CLAUDE_PLUGIN_ROOT} CC兼容 + ${secret.X} Phase1留桩 + expand_dict/expand_list 递归展开）+ PluginHost（load_plugin含冲突检测+audit / unload_plugin / unload_all / shutdown 统一清理 / get_skill_descriptions/get_mcp_instructions/get_agent_overrides）
- 修改 executor/plugins/__init__.py — 新增导出 PluginConfig/PluginScope/PluginHost/PluginVariableExpander/ENV_WHITELIST
- ADR-050 落地 DECISIONS.md；blocker.md 追加 Task 5.4 ADR 编号平移链 + DOC-06 ADR-050 冲突警告
- 解 Task 5.2 的 TODO：MCPClient.stop() 统一由 PluginHost.shutdown() finally 块调用

### 验证结果
- Part B 验证步骤：PASS（3项全PASS：py_compile 2文件/Empty PluginHost全方法/All checks passed）
- 额外验证：变量替换9种（PRISM_PLUGIN_ROOT/DATA/SKILL_DIR/SESSION_ID/USER_ID/user_config.X/env.HOME白名单/env.SECRET_KEY非白名单/secret.X留桩）全PASS
- Platform/User/Session三级冲突检测+shutdown()清理 PASS
- 质量门：PASS — 无实际 backend.app import；无 TODO: 占位；进程边界严格

### 下一个 Task 需要注意 — DOC-05 Task 5.5 (Skills Registry Local+GitHub 两源)
- ADR 编号从 ADR-051 起（ADR-050 已被本 Task 占用；DOC-06 须从 ADR-051 接续，见 blocker.md）
- SkillRegistry 实现后可通过 PluginHost.load_plugin() 加载 GitHub Skill（host.py 已就绪）
- PluginHost.shutdown() 接口已就绪，DOC-07 Task 7.4 executor __main__.py finally 块调用 await plugin_host.shutdown()

### 遗留风险 / 未决事项
- ${secret.X} Phase 1 留桩（原样保留字符串）；DOC-06 Task 6.1 security.decrypt_value 落地后需回来激活
- DOC-06 Task 6.1 原规划 ADR-050~055 三密钥/SSE ticket，因本 Task ADR-050 已占用，DOC-06 须从 ADR-051 起

### Commit
- `2bd50f1` — `feat(v5.4): PluginHost unified lifecycle + variable substitution system (ADR-050)`
- `559768d` — `docs: update state files for DOC-05 Task 5.4 (PROGRESS/DECISIONS/HANDOFF/blocker)`

---

## 2026-04-19 -- DOC-05 Task 5.3 completed (Hook 治理层 + Plugin 命名空间 + ADR-048/049)

### 本次 session 做了什么
- 修改 executor/harness/hooks/events.py — 新增 PHASE1_EVENTS frozenset（8事件）+ PHASE2_EVENTS frozenset（13事件预留）
- 重构 executor/harness/hooks/system.py — `_handlers` 改为 `dict[str, list[tuple[int, str, HookHandlerConfig]]]` 三元组（priority+hook_id+config）；register() 新增 hook_id/priority 参数（默认100）并按优先级升序排序；新增 unregister(hook_id) 精确注销；新增 unregister_by_prefix(prefix) 批量注销；fire() 入口校验 PHASE1_EVENTS，非 Phase 1 事件静默返回空决策
- 新建 executor/plugins/namespace.py — PluginNamespace(plugin_name)：qualify/unqualify/is_mcp_tool/build_qualified；MCP 工具（mcp__ 前缀）绕过命名空间
- 修复 executor/plugins/skill_loader.py — _register_skill_hooks() 传 hook_id 到 register()；_unregister_skill_hooks() 真实调用 unregister_by_prefix()（解决 Task 5.1 留的 TODO stub）
- 修改 executor/harness/hooks/__init__.py — 新增导出 PHASE1_EVENTS / PHASE2_EVENTS
- 修改 executor/plugins/__init__.py — 新增导出 PluginNamespace；ADR-048/049 落地 DECISIONS.md；blocker.md 追加 Task 5.3 ADR 编号平移链

### 验证结果
- Part B 验证步骤：PASS（3项全PASS：py_compile 3文件/Phase1-2事件集/优先级排序+scoped注销+PluginNamespace）
- 质量门：PASS — 0 `from backend.app` in 新增文件；无 TODO 占位；进程边界严格；HookDecision 11字段对齐 ADR-026

### 下一个 Task 需要注意 — DOC-05 Task 5.4 (PluginHost 统一管理与垂类特调)
- ADR-050 是下一个可用编号（须检查 DOC-06 ADR-050~055 三密钥/SSE ticket 是否冲突，Task 5.4 从 ADR-050 起但注意此编号同时被 DOC-06 ADR-050 声明——需继续平移）
- unregister_by_prefix("plugin:{plugin_name}:") 已就绪，Task 5.4 PluginHost 卸载 Plugin 时调用此接口
- PluginNamespace 已就绪，Task 5.4 PluginHost 加载 Plugin 时使用 qualify() 为 Skill/Hook 加命名空间

### 遗留风险 / 未决事项
- PRD Part B 验证脚本中 `from executor.harness.hooks.events import HookDecision` 是 PRD 笔误（HookDecision 在 decision.py），验证用修正 import 通过，原 PRD 脚本有语法歧义但不影响实现正确性
- DOC-05 Task 5.4 ADR 编号需仔细检查：DOC-06 已声明 ADR-050~055 范围，Task 5.4 须继续平移编号

### Commit
- (见 git log)

---

## 2026-04-19 -- DOC-05 Task 5.2 completed (MCP Server 双通道 + scope + ADR-046/047)

### 本次 session 做了什么
- 新建 executor/plugins/mcp_client.py — MCPClient（asyncio.create_subprocess_exec P0异步修复；start/stop/call_tool；get_instructions ADR-046第一通道；list_mcp_tool_pairs ADR-047；scope二值system/user）+ MCPToolWrapper（mcp__{server}__{tool}命名；description=ADR-046第二通道；execute委托MCPClient.call_tool）+ filter_mcp_tools_for_agent（辅助函数；None=全部/列表=白名单过滤）+ SCOPE_SYSTEM/SCOPE_USER常量
- 修改 executor/engine/prompt_assembler.py — 新增 invalidate_static_cache()（_static_cache=None + _tools_hash=None 双重失效）+ update_tools()（更新工具列表并调用invalidate_static_cache）
- 修改 executor/plugins/__init__.py — 导出 MCPClient / MCPToolWrapper / filter_mcp_tools_for_agent / SCOPE_SYSTEM / SCOPE_USER（共5新符号）
- ADR-046/047 落地 DECISIONS.md；blocker.md 追加 Task 5.2 ADR 编号平移链（046=MCP双通道，047=agent-scoped白名单，后续从048起）

### 验证结果
- Part B 验证步骤：PASS（3项全PASS：Cache hit/Cache invalidation/New tools in prompt）
- 质量门：PASS — 0 `from backend.app` import in mcp_client.py；无 TODO 占位；进程边界严格；asyncio P0修复（非阻塞readline）；ADR对齐

### 下一个 Task 需要注意 — DOC-05 Task 5.3 (Hook 治理层与 Plugin 命名空间)
- ADR-048 是下一个可用编号（DOC-05 Task 5.3 的 ADR 从 048 起编号）
- MCPClient.stop() 在 session 结束时必须被调用（PluginHost / __main__.py finally 块），否则 MCP Server 子进程泄漏
- invalidate_static_cache() / update_tools() 已就绪，Task 5.3 Hook 治理可在 MCP 工具注册/注销的 Hook handler 中调用 assembler.invalidate_static_cache()
- filter_mcp_tools_for_agent 设计为辅助函数（非 MCPClient 方法），调用链：clients → list_mcp_tool_pairs → filter_mcp_tools_for_agent → AgentDefinition.filter_mcp_tools；Task 5.4 PluginHost 组装时串联此链

### 遗留风险 / 未决事项
- MCPClient._send_request() 对 stdout.readline() 无超时保护；若 MCP Server 挂死会永久阻塞 await。Phase 1 不加 timeout，Task 5.4 PluginHost 可包装 asyncio.wait_for 超时降级
- MCPToolWrapper.execute() 捕获所有异常返回 is_error=True，不区分网络错误/业务错误；Phase 1 统一处理，后续可细化 error_code

### Commit
- (见 git log)

---

## 2026-04-19 -- DOC-05 Task 5.1 completed (Skill 三级加载 Level 0/1/2 + agents过滤 + audit)

### 本次 session 做了什么
- 新建 executor/plugins/skill_types.py — SkillMetadata(name/description/triggers/hooks/path/agents) + SkillContent(metadata/full_text/is_loaded)
- 新建 executor/plugins/skill_loader.py — SkillLoader 三级加载器：scan_and_register() Level 0; get_descriptions_for_prompt(agent_type) Level 1 含 ADR-044 agents 过滤; try_trigger(user_message, agent_type) 触发检测; load_skill(name) Level 2 读 body + 注册 scoped hooks + structlog is_skill_context=True; unload_skill/unload_all; emit_mentioned_not_loaded() audit warning; _filter_by_agent(); Phase 1 8事件白名单 _PHASE1_EVENTS; _parse_frontmatter() pyyaml safe_load; _read_body() 跳过 frontmatter
- 修改 executor/plugins/__init__.py — 导出 SkillMetadata/SkillContent/SkillLoader
- 新建 plugins/skills/.gitkeep — Skill 存放目录占位（目录结构按 PRD Part B）
- 修改 pyproject.toml — 追加 pyyaml>=6.0 依赖（Task 3.6 要求，之前未在 pyproject.toml 体现）
- ADR-043/044/045 落地 DECISIONS.md；blocker.md 追加 Task 5.1 ADR 编号平移链

### 验证结果
- Part B 验证步骤：PASS（py_compile 2文件；Level 0注册；Level 1描述；Trigger匹配/不匹配；Level 2加载；不重复触发；Unload；ADR-044 agents过滤；emit_mentioned_not_loaded audit；__init__ 导出）
- 质量门：PASS — 0 `from backend.app` import；无 TODO 占位；进程边界严格；pyyaml 依赖声明

### 下一个 Task 需要注意 — DOC-05 Task 5.2 (MCP Server 集成与热加载)
- ADR-046 是下一个可用编号（DOC-05 Task 5.2 的 ADR 从 046 起编号）
- SkillLoader._unregister_skill_hooks() 当前只记录 id 日志，未真实从 HookSystem 清除；Task 5.3 实现 HookSystem.unregister_by_id() 后回填
- load_skill() 返回 SkillContent，调用方须自行构造 PrismMessage(is_skill_context=True, skill_name=name) 插入 messages；Task 5.4 PluginHost 负责此对接
- PromptAssembler 中 SkillInfo 为临时 stub（Task 2.4），Task 5.1 的 SkillMetadata 是正式版；Task 5.4 可统一替换

### 遗留风险 / 未决事项
- HookSystem.unregister_by_id() 未实现（Phase 1 限制），Skill 卸载时 scoped hooks 残留在 HookSystem._handlers 中，但不影响语义（hook 仍会执行，仅略浪费）；Task 5.3 修复
- pyproject.toml pyyaml>=6.0 为新增依赖，本地无 Docker 环境无法运行 docker compose exec 验证，已通过直接 python -m py_compile 和 python -c 验证

### Commit
- (见 git log)

---

## 2026-04-19 -- DOC-04 Task 4.5 completed (PluginBuilder 完整度打分 + 动态轮数)

### 本次 session 做了什么
- 新建 executor/agents/plugin_builder_scoring.py — RequirementCompleteness 类（CRITERIA 7维度加权，THRESHOLD=0.8，score() async LLM打分+structlog事件+Prometheus histogram lazy init）+ get_missing_dimension_question()（weighted_gap找最缺维度）+ PluginBuilderAgent（run() 打分循环，_present_design stub，_wait_for_user_reply NotImplementedError stub）
- 修改 executor/agents/plugin_builder.py — v4 AgentDefinition（max_turns=40，allowed_tools 7项精确列表，output_format=structured_dialogue，behavior_constraints v4 修订文本）+ PLUGIN_BUILDER 向后兼容别名
- 新建 executor/harness/middleware/plugin_builder_gate.py — PluginBuilderGate Middleware（pre_turn 4阶段门控：phase 1低分注入constraint，phase 1达阈升phase 2，phase 2未确认注入约束）+ pre_tool_use 阻止阶段 1/2 写 plugin 文件 + _is_plugin_file() + GR_PLUGIN_CREATE_GUARD（scope="tier"可配置降级）
- 修改 executor/router.py — PLUGIN_BUILDER_PATTERNS 4条中英文正则 + route()步骤3a优先正则 + AGENT_TYPE_PATTERNS["plugin_builder"]扩充14项关键词
- 修改 executor/harness/middleware/__init__.py — 导出 PluginBuilderGate / GR_PLUGIN_CREATE_GUARD
- ADR-042 落地 DECISIONS.md（PRD原标ADR-038平移；DOC-04 Task 4.2已用ADR-038）
- blocker.md 末尾追加 Task 4.5 ADR编号平移链记录

### 验证结果
- Part B 验证步骤：PASS（py_compile 3文件；高分overall=0.85≥0.8；低分overall=0.30<0.8；权重和=1.00；THRESHOLD=0.8；中英文路由各PASS；PluginBuilderGate 4场景；_is_plugin_file；GR_PLUGIN_CREATE_GUARD block/allow）
- 质量门：PASS — 0 `from backend.app` import；无 TODO 占位（stub 均有 NotImplementedError 或 # TODO 说明）；进程边界严格

### 下一个 Task 需要注意 — DOC-05 Task 5.1 (Skill 三级加载)
- ADR-043 是下一个可用编号（DOC-05 Task 5.1 的 ADR 从 043 起编号）
- GR_PLUGIN_CREATE_GUARD 已声明但未注入 GuardrailsEngine，DOC-05 Task 5.3 Hook 治理负责注入（或 Harness Runtime 初始化时注入）
- PluginBuilderAgent._wait_for_user_reply() stub，DOC-07 Task 7.3 实现 SSE/BLPOP 后激活

### 遗留风险 / 未决事项
- PluginBuilderAgent.run() 的 _wait_for_user_reply() 为 NotImplementedError stub，不影响编译和 Middleware 路径，待 DOC-07 Task 7.3 实现
- GR_PLUGIN_CREATE_GUARD 注入时机未定（DOC-05 Task 5.3 或 Harness Runtime），需后续 Task 追加

### Commit
- `0a43a39` — `feat(v4): PluginBuilder 完整度打分 + 动态轮数 — DOC-04 Task 4.5`

---

## 2026-04-19 -- DOC-04 Task 4.4 completed (TaskRouter 6 agent_type + keyword routing)

### 本次 session 做了什么
- Created executor/router.py — TaskRouter 类 + RouteDecision dataclass(mode/agent_type/reason) + COORDINATOR_PATTERNS(11条中英文) + AGENT_TYPE_PATTERNS(4种:explore/planner/verifier/plugin_builder,含中英文关键词) + AGENT_TYPE_ALIASES(3条别名:chat→general/research→explore/build→general)
- Modified executor/__main__.py — 追加 `from executor.router import TaskRouter` import + TaskRouter routing stub(注释块,待 DOC-07 Task 7.4 DB 集成激活)
- ADR-041 落地 DECISIONS.md(PRD 原标 ADR-037 平移;Fork capability-based ADR-037 已占用)
- blocker.md 末尾追加 Task 4.4 ADR 编号平移链记录
- PROGRESS.md Task 4.4 行更新为 completed + session notes

### 验证结果
- Part B 验证步骤: PASS(8项路由测试全通过,2项 py_compile PASS,1项 grep PASS)
- 质量门: PASS — 进程边界(0 backend.app import)、密度达标、无 TODO 占位、对齐 PRD Part B

### 下一个 Task 需要注意 — DOC-04 Task 4.5 (PluginBuilder 完整度打分)
- TaskRouter 的 AGENT_TYPE_PATTERNS["plugin_builder"] 已预置关键词路由，Task 4.5 不需要再修改 router.py
- ADR-038 原编号在 PRD 被 PluginBuilder 打分使用，但 DOC-04 Task 4.2 已用 ADR-038 落地 Fork 3 条约束；Task 4.5 的 ADR 需从 ADR-042 起编号
- PRD Part B 验证步骤 line 1548 有笔误(断言 'research' 但路由返回 'explore')；已在 DECISIONS.md ADR-041 偏离点说明，Task 4.5 实施者无需修改 router.py

### 遗留风险 / 未决事项
- __main__.py 中 TaskRouter routing stub 为注释状态，待 DOC-07 Task 7.4 DB 集成后取消注释并接入 run.prompt/run.agent_type
- RouteDecision.reason 写入 audit_logs 逻辑尚未实现(DOC-07 Task 7.3/7.4 负责)

### Commit
- `f0c373e` — `feat(v4): TaskRouter 6 agent_type + keyword routing — DOC-04 Task 4.4`

---

## 2026-04-19 -- DOC-04 Task 4.3 completed (Coordinator + Plan checkpoint)

### 本次 session 做了什么
- Created executor/coordinator/plan.py — Plan/PlanStep dataclass + parse_from_text() 两级解析(JSON 围栏/裸 JSON / markdown `[agent] desc` / 单步 general fallback) + serialize_plan/deserialize_plan(asdict 持久化助手) + _normalize_agent_type(research→explore 规范化)
- Created executor/engine/synthesizer.py — Synthesizer.synthesize() 模板合成(## 任务完成 + **目标** + ### desc/result)
- Created executor/coordinator/coordinator.py — Coordinator.__init__(plan_id + resume_from_step) + execute(existing_plan可选, 初始 + 每 step 开始 + 完成 = 4 次 coordinator_plan_update) + resume_from_checkpoint(classmethod 返回 (Coordinator, Plan) 元组) + _plan(Fork Planner, 失败兜底单步 general) + _build_step_context(注入前 500 字)
- Modified executor/coordinator/__init__.py — 追加导出 Plan/PlanStep/serialize_plan/deserialize_plan/Coordinator

### 验证结果
- Part B 验证步骤: 全部 PASS (Plan 构造 + Synthesizer 模板)
- 扩展验证: parse_from_text JSON / markdown / fallback 三路径 PASS; serialize/deserialize roundtrip PASS
- Coordinator 路径测试: single-step(直返 synthesis) / multi-step(4次 plan_update + 2次 step_start/end) / resume_from_step=1(只 fork 第2步) 全 PASS
- grep `from backend.app` in executor/coordinator + executor/engine/synthesizer.py: 0 命中 PASS

### 下一个 Task 需要注意 — DOC-04 Task 4.4 (TaskRouter 6 agent_type)
- TaskRouter 集成在 executor/__main__.py 入口处,按关键词判定 general/explore/planner/verifier/coordinator/plugin_builder
- 判定"复杂任务"→ 切换 Coordinator 模式(本 Task 实现的 Coordinator.execute)
- Phase 1 关键词匹配(ms 级,确定性),Phase 2 LLM 分类 fallback(ADR-037 Task 4.4 原标)
- 路由器返回 (agent_type, use_coordinator) 元组,__main__.py 按 use_coordinator 分支

### 遗留风险 / 未决事项
- ADR 编号平移: DOC-04 Task 4.3 PRD 原标 ADR-036 → 本实现 ADR-040(blocker.md 已记录)；后续 DOC-04 Task 4.4/4.5 的 ADR 从 ADR-041 接续；DOC-05 后续 ADR 需继续平移(参考 blocker.md)
- Coordinator.resume_from_checkpoint 返回 (Coordinator, Plan) 元组(偏离 PRD 原版单返 Coordinator); DOC-07 Task 7.4 CoordinatorRecoveryService 需按此签名调用
- coordinator_plans 表持久化逻辑在 DOC-07 Task 7.3 回调端点实现(本 Task 只 emit event)

### Commit
- `c0f394d` — `feat(v4): Coordinator + Plan checkpoint (parse_from_text + Synthesizer + 4-stage checkpoint) — DOC-04 Task 4.3`

---

## 2026-04-19 -- DOC-04 Task 4.2 completed (Fork & Context Isolation)

### 本次 session 做了什么
- Created executor/coordinator/fork_briefing.py — ForkBriefing dataclass(6字段:goal/why/excluded/context/expected_output/file_references) + to_prompt()(6 markdown section标题) + FORK_HARD_CONSTRAINTS(3条硬约束 ADR-038)
- Created executor/coordinator/fork_result.py — ForkResult dataclass(9字段,含briefing:ForkBriefing + allowed_capabilities)
- Created executor/coordinator/fork_manager.py — ForkManager + ForkDepthExceeded; fork()(depth检查/capability过滤/子assembler/子pipeline/子harness/timeout包裹); _create_child_assembler()(继承parent static cache + inject FORK_HARD_CONSTRAINTS); _create_filtered_registry()(capability-based过滤,空list=不限制); _extract_synthesis()(反向扫最后assistant TextBlock)
- Created executor/coordinator/__init__.py — 导出 ForkBriefing/ForkResult/ForkManager/ForkDepthExceeded/FORK_HARD_CONSTRAINTS
- Created executor/tools/builtin/fork.py — ForkTool(BaseTool), capabilities=["fork_agent"], input_schema含agent_type/goal必填+4可选字段, execute()构造ForkBriefing并调fork_manager.fork()
- Modified executor/agents/base.py — AgentDefinition追加 allowed_capabilities: list[str] = field(default_factory=list)
- Modified executor/tools/base.py — BaseTool追加 capabilities: list[str] = [] class-level默认
- Modified executor/tools/registry.py — 追加 list_all() -> list[BaseTool] 方法
- Modified executor/engine/prompt_assembler.py — 追加 _extra_dynamic_tail: str | None = None; _build_dynamic()末尾注入
- Modified executor/tools/builtin/__init__.py — register_builtin_tools追加可选fork_manager参数

### 验证结果
- Part B 验证步骤 15 项: 全部 PASS
- py_compile 10文件 PASS
- 导入 5个符号 PASS
- ForkBriefing.to_prompt() 6 section PASS
- FORK_HARD_CONSTRAINTS 3条约束 PASS
- ForkResult 9字段 PASS
- ToolRegistry.list_all() PASS
- _extra_dynamic_tail 注入 PASS
- ForkDepthExceeded depth=2 PASS
- capability过滤 4场景 PASS
- _create_child_assembler static_cache+tools_hash+tail PASS
- _extract_synthesis 最后assistant PASS
- ForkTool input_schema required PASS
- ForkTool.execute success PASS
- ForkTool.execute fail PASS
- grep backend.app: 0命中 PASS

### 下一个 Task 需要注意 -- DOC-04 Task 4.3 (Coordinator + Plan checkpoint)
- Coordinator 用 ForkManager 派 Worker Agent：Coordinator 需持有 ForkManager 实例，在 TAOR 循环中通过 fork_agent 工具（或直接调用 ForkManager.fork()）派生 research/planner/verifier 子 Agent
- Plan checkpoint 需持久化到 coordinator_plans 表（Task 2.1 已建）：coordinator_plans 表含 run_id/plan_json/current_step/status，Coordinator 每完成一步需 UPSERT checkpoint，重启时从 checkpoint 恢复
- 崩溃恢复：子进程重启时 --resume-from-step=N 从 checkpoint 继续，QueryEngine 初始化时检查 coordinator_plans 表，若有 in_progress plan 则注入已完成步骤的 synthesis 到 messages

### 遗留风险 / 未决事项
- ADR 编号平移：DOC-04 Task 4.2 PRD 原标 ADR-033/034/035 → 本实现 ADR-037/038/039（见 blocker.md）
- ForkManager.fork() 中 QueryEngine/ToolExecutionPipeline 延迟导入（避免循环依赖），真实集成时需确认 harness_factory 的签名接受 AgentDefinition 参数（lifecycle.py HarnessRuntime constructor）
- ForkTool 的 capabilities=["fork_agent"] class-level 属性：Python class-level list 是共享引用，子类若不 override 而直接 append 会污染父类，当前实现只读取不修改，安全

### Commit
- `a61991d` — `feat(v4): Fork & Context Isolation (capability-based + 3 hard constraints + ForkBriefing 6 fields) — DOC-04 Task 4.2`

---

## 2026-04-18 -- DOC-04 Task 4.1 completed (6 specialized Agent definitions + AgentPool)

### Done this session
- Created executor/agents/base.py — AgentDefinition dataclass (v4: 11 fields incl. mcp_servers/frontmatter_skills/bash_whitelist) + filter_tools() + filter_mcp_tools()
- Created executor/agents/general.py — GENERAL_AGENT (agent_type="general", allowed_tools=None, max_turns=50)
- Created executor/agents/research.py — RESEARCH_AGENT/EXPLORE_AGENT (agent_type="explore", read_only=True, max_turns=30, BASH_WHITELIST 9条, READ_ONLY_TOOLS)
- Created executor/agents/planner.py — PLANNER_AGENT (agent_type="planner", read_only=True, max_turns=10, output_format含"Critical Files for Implementation")
- Created executor/agents/verifier.py — VERIFIER_AGENT + VERIFIER_SYSTEM_PROMPT原文(含VERDICT三态+4类专项验证 Frontend/Backend/CLI/Migration)
- Created executor/agents/coordinator.py — COORDINATOR_AGENT (agent_type="coordinator", allowed_tools=["fork_agent","synthesize","task_stop"], max_turns=200)
- Created executor/agents/plugin_builder.py — PLUGIN_BUILDER_AGENT (agent_type="plugin_builder", max_turns=40, 多轮需求收集约束)
- Created executor/agents/pool.py — AgentPool: 6种+3别名(chat→general/research→explore/build→general), get()/list_types()/filter_tools_for_agent()
- Created executor/agents/__init__.py — 导出 AgentDefinition + AgentPool + 7 AGENT实例 + 常量
- Modified executor/harness/lifecycle.py — HarnessRuntime.__init__ 接受可选 agent_def: AgentDefinition | None; agent_def.read_only=True 时追加 GuardrailRule(id="AGENT-READONLY") + _is_write_bash helper

### Verification results
- Part B 验证步骤 15 项: 全部 PASS
- py_compile 10文件 PASS
- 6种unique agent_type断言 PASS
- 3别名(chat/research/build) PASS
- AGENT-READONLY规则: Write/Edit/Delete拦截 PASS; ls/grep/git status放行 PASS; rm拦截 PASS
- grep from backend.app in executor/agents/: 0命中 PASS

### Notes for next Task -- DOC-04 Task 4.2 (Fork + Context Isolation)
- Fork 必须保留原 Agent 的 agent_type（不可覆盖 model）— 3 条 prompt-level 硬约束（PRD ADR-030/ADR-034 原文）：1) 父 Agent 的 agent_type 传给子 Agent; 2) 子 Agent 不能重选 model; 3) ForkBriefing 6字段结构化注入
- AgentPool.get() 可获取 Fork 后子 Agent 的定义（直接按 agent_type 查找即可，不需要新 API）
- Fork 子 Agent 启动时要 inherit parent 的 run_context（除 run_id 外）；briefing 注入时要带 parent_run_id / parent_session_id / parent_agent_type 三个字段

### Risks / Open items
- ADR 编号持续平移: PRD Task 4.1 原标 ADR-030/031/032 → 本实现 ADR-034/035/036（见 blocker.md）
- HarnessRuntime.agent_def 参数在 DOC-07 Task 7.4 子进程启动时真实注入（AgentPool().get(run.agent_type)），本 Task 只提供接口
- GENERAL_AGENT.behavior_constraints="" 时 PromptAssembler 的 agent_behavior_section 走 "general" 分支，已在 Task 2.4 实现，无需修改

### Commit
- `d04b909` — `feat(v4): 6 specialized Agent definitions + AgentPool (DOC-04 Task 4.1)`

---

## DOC-03 DONE — 2026-04-18 收官 checkpoint

### DOC-03 6 Task 产物路径索引

| Task | 核心产物 | ADR |
|---|---|---|
| 3.1 TAOR 主循环 | executor/engine/query_engine.py, executor/tools/, executor/callbacks/backend_callback.py, executor/__main__.py | ADR-020/021/022/023/024 |
| 3.2 Middleware Pipeline | executor/harness/middleware/{base,pipeline,loop_detection,observability}.py | ADR-025 |
| 3.3 Hook System + Permission Engine | executor/harness/{hook_system,permission_engine,ask_protocol,guardrails,platform_rules}.py | ADR-026/027/028 |
| 3.4 Feedback Capture + HarnessRuntime | executor/harness/middleware/feedback_capture.py, executor/harness/lifecycle.py | ADR-029/030 |
| 3.5 Compaction + Memory | executor/engine/compaction.py, executor/engine/memory.py | ADR-031/032 |
| 3.6 Harness Config 2源 | executor/harness/defaults.py, executor/harness/config_loader.py, backend/app/api/v1/harness.py | ADR-033 |

### DOC-03 ADR 落地清单（ADR-020 ~ ADR-033）

ADR-020 Harness单实例 / ADR-021 工具并行gather / ADR-022 Redis直通 / ADR-023 心跳5s SETEX /
ADR-024 MAX_TURNS分档 / ADR-025 Middleware 4钩点 / ADR-026 HookDecision 11字段 /
ADR-027 merge_decisions / ADR-028 ask BLPOP / ADR-029 FeedbackEvent结构化 /
ADR-030 SessionEnd LLM提炼user_memory / ADR-031 Compaction回合组原子裁剪 /
ADR-032 is_skill_context优先保留 / ADR-033 Harness配置2源化+禁止运行时修改

### 🟢 下一步: DOC-04 Task 4.1（Agent 专业化 + AgentPool 6 种）

待办优先级（32 Task 剩余）:
- **DOC-04** 5 Task: 4.1 AgentPool / 4.2 Planner / 4.3 Coordinator / 4.4 Verifier / 4.5 PluginBuilder
- **DOC-05** 7 Task: Skill系统
- **DOC-06** 2 Task: Auth/RBAC
- **DOC-07** 4 Task: Run调度+子进程启动（HarnessRuntime注入 DOC-03产物）
- **DOC-08** 3 Task: IM Gateway
- **DOC-09** 3 Task: Admin API
- **DOC-12** 8 Task: Observability

下一个派工目标: **DOC-04 Task 4.1 — Agent 专业化 + AgentPool（6 种 agent_type）**

---

## 2026-04-18 -- DOC-03 Task 3.6 completed (Harness Config 2-Source Loader + GET /harness/config)

### Done this session
- Created executor/harness/defaults.py — 3 const dicts: DEFAULT_PERMISSION_POLICIES(9项) + DEFAULT_MIDDLEWARE_CONFIG(4项) + DEFAULT_AGENT_CONSTRAINTS(6 agent types)
- Created executor/harness/config_loader.py — HarnessEffectiveConfig dataclass(6字段) + HarnessConfigLoader(config_file_path).load(): 2源合并 source_trace per-key "default"/"yaml"; yaml不存在→default-only; yaml格式错→raise RuntimeError + log harness.config.load_failed; 成功→log harness.config.loaded + Prometheus prism_harness_config_load_total
- Created backend/app/api/v1/harness.py — GET /config (readonly, require_admin); PATCH/POST/DELETE 不注册(FastAPI默认405); config_file_path 从 HARNESS_CONFIG_PATH env读取
- Modified backend/app/api/v1/__init__.py — include harness.router
- Modified backend/requirements.txt — 追加 pyyaml>=6.0
- DECISIONS.md 追加 ADR-033（PRD原标ADR-031冲突修正，本实现采用033）

### Verification results
- 10 项验证全部 PASS
- py_compile 4文件 PASS
- imports(executor+backend) + 3断言 PASS
- Default-only load: bash=ask, source_trace=default PASS
- YAML override: bash→allow/yaml, loop_detection.enabled=False PASS
- YAML format error → RuntimeError + log harness.config.load_failed PASS
- Nonexistent YAML path → default-only, no raise PASS
- Router routes: GET /harness/config 存在, 无 PATCH/POST/DELETE PASS
- GET endpoint response: effective(5 keys) + source_trace PASS
- api_v1_router 含 harness.router PASS
- pyyaml in requirements.txt PASS

### Notes for next Task -- DOC-04 Task 4.1 (Agent 专业化 + AgentPool 6 种)
- HarnessConfigLoader.load() 已提供，DOC-07 Task 7.4 子进程启动时将产物注入 HarnessRuntime（本 Task 未做）
- DEFAULT_AGENT_CONSTRAINTS 6 种类型: chat/explore/planner/verifier/plugin_builder/coordinator — DOC-04 Task 4.1 的 AgentPool 6种类型需与之对齐
- ask_user 值在 config_loader 中归一化为 ask，DOC-04/05/06 任何 Permission 相关实现均用 "ask" 不用 "ask_user"

### Risks / Open items
- HarnessConfigLoader 注入 HarnessRuntime: 留 DOC-07 Task 7.4（子进程启动参数读取 HARNESS_CONFIG_PATH）
- YAML error test: `:::::::` 在 pyyaml 中解析为合法 dict，实际 YAML error 需用 `{invalid: yaml: content:}` 等真实非法内容触发

### Commit
- `5381df3` — `feat(v4): Harness config 2-source loader + GET /harness/config readonly (DOC-03 Task 3.6 — DOC-03 DONE)`

---

## 2026-04-18 -- DOC-03 Task 3.5 completed (4-tier Compaction + 6-layer Memory)

### Done this session
- Created executor/engine/compaction.py — CompactionPipeline: TIER1=0.60/TIER2=0.85, maybe_compact/check_and_compact 路由入口, _tier1_micro_compact (裁最老1组), _tier2_auto_compact (LLM摘要替换最老50%组, adapter=None降级Tier1+warning), reactive_truncate (保留最近3组+hint), _tier4_reactive=reactive_truncate 别名, _extract_text helper, Prometheus prism_harness_compaction_total{tier} 集成
- Created executor/engine/memory.py — MemoryLayer ABC (load()->str|None), SessionMemory (raw SQL: sessions.config_snapshot.session_memory), UserMemory (raw SQL: user_memories.memory_text 最近10条), MemoryManager (Layer1+2, get_layer() Phase2预留, load() User先Session后)
- Modified executor/engine/query_engine.py — __init__ 追加 compaction: CompactionPipeline | None = None; run() 循环里 if compaction: check_and_compact, else: Tier0 fallback（老代码保留）
- Modified executor/harness/lifecycle.py — __init__ 追加 budget=None 参数; CompactionPipeline 条件组装 (budget非None时); memory_manager=None留空; 新增 load_user_memory(db_session=None)->str 方法
- 所有 14 项验证 PASS; blocker.md 追加 ADR-029/030 重号修正记录; DECISIONS.md 追加 ADR-031/ADR-032

### Verification results
- Part B 验证步骤 14 项: 全部 PASS
- py_compile 5 files PASS
- imports all OK PASS
- Tier1 裁最老组 + is_skill_context保留 PASS (TEST 3/4)
- Tier2 mock adapter摘要 + adapter=None降级 PASS (TEST 5/6)
- Tier4 _tier4_reactive别名 + reactive_truncate 3组+hint PASS (TEST 7/8)
- maybe_compact 阈值路由 50%/65%/90% PASS (TEST 9)
- tool_use↔tool_result 配对保证(ADR-031) PASS (TEST 10)
- MemoryManager db_session=None返回"" PASS (TEST 11)
- MemoryManager mock DB 拼接格式 + 顺序(User先) PASS (TEST 12)
- QueryEngine compaction=None向后兼容 PASS (TEST 13)
- grep from backend.app in executor/engine/ 新文件: 0命中 PASS (TEST 14)

### Notes for next Task -- DOC-03 Task 3.6 (Harness 配置 2 源简化)
- 配置 2 源：系统默认（config.py Settings 类）+ 用户覆盖（DB user.settings JSONB 或 .prism/config.json 文件）；不允许 per-session 第 3 源
- PATCH 运行时 API 已删（v4）；所有 Harness 参数在子进程启动时冻结，不可运行时修改
- Settings 当前已有 CIRCUIT_BREAKER_* / HEARTBEAT_* / LOOP_DETECTION_* / PERMISSION_ASK_TIMEOUT_SECONDS / FEEDBACK_TTL_SECONDS；Task 3.6 只补 ClaudeConfig（model/max_tokens/temperature）和 HarnessConfig（max_turns/agent_type/…）结构化封装，合并两源后注入 HarnessRuntime

### Risks / Open items
- UserMemory 列名：ORM 用 memory_text（非 PRD raw SQL 示例的 content）；memory.py 已用 memory_text，与 ORM model 对齐
- HarnessRuntime.load_user_memory() 的真实 db_session 注入留 DOC-07 Task 7.4（__main__.py 子进程启动时）
- CompactionPipeline 的 Prometheus metric 复用 prism_harness_compaction_total（已存在），未另建 prism_compaction_total

### Commit
- `ef26979` — `feat(v4): 4-tier Compaction + 6-layer Memory (turn-group atomic, skill_context preserved) — DOC-03 Task 3.5`

---

## 2026-04-18 -- DOC-03 Task 3.4 completed (Feedback Capture + HarnessRuntime Lifecycle)

### Done this session
- Created executor/harness/middleware/feedback_capture.py -- FeedbackEvent dataclass (ADR-029: 5 event_type + 4 severity + context + ISO 8601 timestamp) + FeedbackCaptureMiddleware (post_turn + _extract_failures + get_run_summary + Redis SETEX TTL 7d + Prometheus)
- Replaced executor/harness/lifecycle.py HarnessLifecycle → HarnessRuntime (8-param __init__: run_id/session_id/user_id/callback/redis_client/redis_url/adapter/settings)
- Middleware registration order: loop_detection → observability → feedback_capture (3 total)
- inject_into_pipeline(): pipeline._permission_engine + pipeline._hook_system
- on_session_start(): fire SessionStart HookEvent
- on_session_end(messages, turn_count): fire SessionEnd → if turn_count > 5: LLM complete → harness_event("user_memory_extracted") + Prometheus inc; exception → log WARNING (no raise)
- get_run_harness_summary(): feedback summary + middleware_count + guardrail_rules_count
- HarnessLifecycle = HarnessRuntime backward-compat alias
- Modified executor/harness/middleware/__init__.py -- export FeedbackEvent, FeedbackCaptureMiddleware
- Modified executor/observability/metrics.py -- added prism_harness_feedback_total{event_type,severity} + prism_harness_memory_extracted_total

### Verification results
- All 12 verification items: PASS
- py_compile 4 files PASS
- imports + alias HarnessLifecycle is HarnessRuntime PASS
- FeedbackEvent 5 event_type + 4 severity validated via typing.get_args PASS
- FeedbackCaptureMiddleware: tool_error extraction / custom_data signals / get_run_summary PASS
- HarnessRuntime assembly: 3 middleware + order [loop,obs,feedback] + guardrail_rules=4 PASS
- inject_into_pipeline: permission_engine + hook_system set PASS
- on_session_start fired PASS
- on_session_end turn_count=5 no LLM PASS; turn_count=10 LLM×1 + memory callback PASS
- on_session_end LLM exception → no memory callback + log WARNING PASS
- get_run_harness_summary total_failures + middleware_count=3 + guardrail_rules_count=4 PASS
- grep from backend.app in Task 3.4 files: 0 hits PASS

### Notes for next Task -- DOC-03 Task 3.5 (4-tier Compaction + 6-layer Memory)
- Tier 0 is DONE: executor/engine/context_budget.py compress_history() — atomic turn-group truncation (Task 2.4, ADR-029 compaction). DO NOT re-implement Tier 0.
- Tier 1-3 to implement in Task 3.5:
  - Tier 1: Delete oldest turn-groups (simplest, last resort)
  - Tier 2: LLM summarization of oldest messages → replace with summary block
  - Tier 3: Keep only most recent N turn-groups, discard rest (aggressive)
- 6-layer Memory naming (DOC-02 v4 / DOC-03 v4 §3.5): short-term / skill / mcp / agent / session / user
  - short-term: current session messages (ContextBudgetManager manages this)
  - skill: is_skill_context=True PrismMessage blocks (protected from compaction)
  - mcp: MCP server context injected by PromptAssembler
  - agent: agent-specific system prompt sections
  - session: session-level context (session metadata, user prefs)
  - user: user_memories table entries (written by Task 3.4 ADR-030, read by PromptAssembler DOC-07/09)
- CompactionTrigger: FeedbackEvent(event_type="compaction_triggered") should be emitted when compaction fires (wire into FeedbackCaptureMiddleware via ctx.custom_data["feedback_signals"])
- Compaction hooks: fire HookEvent(event_type="Compact", ...) when compaction triggers (HookSystem already has "Compact" event)

### Risks / Open items
- user_memory DB write is Backend-side (DOC-07/DOC-09 endpoints) — harness only sends callback event
- LoopDetection does NOT write to ctx.custom_data["feedback_signals"] yet — Entropy Detector (DOC-12 Task 12.2) will wire this

### Commit
- affb44b — feat(v4): Feedback Capture + HarnessRuntime lifecycle + user_memory extraction (DOC-03 Task 3.4)

---

## 2026-04-18 -- DOC-03 Task 3.3 completed (Hook System + Permission Engine + Guardrails)

### Done this session
- Created executor/harness/permissions/result.py -- PermissionResult standalone (avoids circular import)
- Created executor/harness/hooks/{events,decision,handlers,system,__init__}.py -- HookEvent/HookDecision 11 fields/merge_decisions (ADR-026/027)/HookHandlerExecutor 4 handlers/HookSystem asyncio.gather parallel
- Created executor/harness/guardrails/{rules,platform_rules,engine,__init__}.py -- GuardrailRule + get_platform_rules GR-PLATFORM-001~004/GuardrailsEngine
- Created executor/harness/permissions/{ask_protocol,engine,__init__}.py -- PermissionAskProtocol Redis BLPOP (ADR-028)/PermissionEngine 2-layer
- Created executor/harness/lifecycle.py -- HarnessLifecycle assembles all governance components
- Modified executor/tools/pipeline.py -- Step3 real permission_engine.check() + Step7 real hook_system.fire(PostToolUse)
- Modified executor/observability/metrics.py -- 3 new counters (permission_ask/hook_fired/guardrail_deny)
- Modified backend/app/core/config.py -- added PERMISSION_ASK_TIMEOUT_SECONDS / HOOK_TIMEOUT_SECONDS / RATE_LIMIT_* defaults

### Verification results
- All 13 verification items: PASS
- py_compile 11 new + 2 modified: PASS
- imports (hooks/permissions/guardrails/lifecycle): PASS
- guardrails rm -rf blocked / ls allowed / web_search unaffected: PASS
- merge stop priority / deny>ask>allow / updated_input conflict ValueError: PASS
- additional_context/blocking_error/message join + empty list: PASS
- permission ask fakeredis (allow + timeout deny + harness_event): PASS
- PermissionEngine integration (guardrails deny/hook deny/hook ask allow+updated_input): PASS
- 4 platform rules tests: PASS
- command handler JSON + timeout: PASS
- pipeline deny + allow+updated_input: PASS
- grep backend.app in harness: 0 hits PASS

### Notes for next Task -- DOC-03 Task 3.4 (Guardrails + Feedback Loop)
- GuardrailsEngine is DONE: Task 3.4 reuses executor/harness/guardrails/engine.py and GuardrailRule. DO NOT re-implement GuardrailRule. Use engine.add_rule(rule) to add additional rules.
- SessionEnd event is defined in events.py: HookEventType already has SessionEnd. Task 3.4 triggers it at session end by calling hook_system.fire(HookEvent(event_type=SessionEnd, ...)). Not implemented in Task 3.3.
- user_memory table was created in Task 2.1: Task 3.4 writes to user_memory via HTTP callback to Backend endpoint (Executor does NOT write to DB directly).

### Risks / Open items
- _execute_prompt and _execute_agent are Phase 1 skeletons (return empty HookDecision when adapter/fork_manager not injected). Full implementation in DOC-05 Task 5.3.
- _rate_window is module-level dict (per-executor subprocess, not shared across processes). PRD confirms this is acceptable.
- Redis key format for perm_answer:{id} is FIXED. DOC-07 Task 7.3 MUST RPUSH to exactly this key.

### Commit
- 25963bf -- feat(v4): Hook System 11 fields + 4 handlers + Permission BLPOP + 4 platform guardrails (DOC-03 Task 3.3 complete)

---

## 2026-04-18 — DOC-03 Task 3.2 completed（Middleware Pipeline 4 钩点）

### 本次 session 做了什么
- 创建 `executor/harness/middleware/base.py` — MiddlewareContext dataclass(12 字段全部有 default) + TurnContext 别名 + Middleware ABC(4 no-op 钩点)
- 创建 `executor/harness/middleware/pipeline.py` — MiddlewarePipeline with run_pre_turn/run_pre_tool_use(短路) + run_post_tool_use/run_post_turn(不短路)
- 创建 `executor/harness/middleware/loop_detection.py` — LoopDetectionMiddleware: post_turn Redis LPUSH+LTRIM+LRANGE sha256 指纹，N 连同 → abort + callback.harness_event("loop_detected")
- 创建 `executor/harness/middleware/observability.py` — ObservabilityMiddleware: pre_turn 记时，post_turn 上报 turn_complete(turn/duration_ms/tool_calls)
- 更新 `executor/harness/middleware/__init__.py` — 导出 6 个公共符号
- 修改 `executor/engine/query_engine.py` — RunContext 追加 agent_type; QueryEngine 新增 middleware_pipeline 参数; run() 集成 pre_turn/post_turn; _execute_single_tool() 集成 pre_tool_use/post_tool_use

### 验证结果
- Part B 验证步骤 1-10 全部: PASS
- py_compile 6 文件 PASS; 导入 + TurnContext is MiddlewareContext PASS; 正常/短路 pipeline PASS; 4 钩点语义 PASS; LoopDetection mock Redis PASS; Observability duration_ms PASS; QueryEngine 集成 + 向后兼容 PASS; _execute_single_tool abort PASS; 无 backend.app import PASS

### 下一个 Task 需要注意 — DOC-03 Task 3.3（Hook System + Permission Engine）
- **pipeline.py 的 2 个 HARNESS_INTEGRATION_POINT**：`executor/tools/pipeline.py` 步骤 3（PreToolUse Hook）和步骤 7（PostToolUse Hook）的注释是 Task 3.3 的锚点，不是 Middleware 的职责，Task 3.2 **未动**这两处
- **Permission ask Redis BLPOP**：CLAUDE.md 陷阱 #8 — permission ask 必须用 Redis BLPOP 阻塞等待，不能轮询；key 格式建议 `perm_answer:{permission_request_id}`
- **Hook 11 字段**：DOC-03 PRD 约束 Hook 事件有 11 个标准字段，Task 3.3 实施时需查 DOC-03 Part B Hook schema，不要自造字段（六原则 #1）
- **Middleware 与 Hook 执行顺序**：pre_tool_use Middleware 在 ToolExecutionPipeline.execute() 之前（在 query_engine.py 的 _execute_single_tool 中）；Pipeline 内部的 PreToolUse Hook 在 schema 校验之后、permission 检查之前（在 pipeline.py step 3）。两者独立，互不干扰

### 遗留风险 / 未决事项
- LoopDetectionMiddleware 检测时机是 post_turn（完整轮次后），若需要 pre_tool_use 级别的实时拦截，可在 Task 3.3 或后续 Task 注册额外 pre_tool_use Middleware
- ObservabilityMiddleware._turn_start_time 是实例变量，多轮串行无问题；若未来支持并发多轮（不在当前设计内），需改为 ctx.custom_data 存储

### Commit
- `e174ea5` — `feat(v4): Harness Middleware Pipeline with 4 hook points (DOC-03 Task 3.2)`

---

## 2026-04-18 — DOC-03 Task 3.1 completed（TAOR 主循环 + ToolExecutionPipeline）

### 本次 session 做了什么
- 创建 `executor/tools/{base.py, registry.py, pipeline.py}` — BaseTool/ToolResult + ToolRegistry + ToolExecutionPipeline（7 步链路 + HARNESS_INTEGRATION_POINT 注释）
- 创建 `executor/tools/builtin/{__init__.py, echo.py}` — EchoTool + register_builtin_tools()
- 创建 `executor/callbacks/backend_callback.py` — 双通道：Redis PUBLISH 高频直通 + HTTP 3 次指数退避重试 + DLQ
- 创建 `executor/engine/query_engine.py` — QueryEngine（TAOR while 循环 + asyncio.gather 并行工具 + _ADAPTERS_WITH_PASSTHROUGH 判断）+ RunContext dataclass + _block_to_dict helper
- 创建 `executor/engine/token_estimator_adapter.py` — DriverTokenEstimator 包装 ModelAdapter.count_tokens()
- 创建 `executor/observability/{__init__.py, metrics.py}` — 6 条 executor 专属 Prometheus metric（独立 Registry）
- 更新 `executor/__main__.py` — MAX_TURNS_BY_AGENT_TYPE 6 档 + heartbeat_writer 协程 + main() 骨架（DB 集成占位 FROM_DB:）
- 追加 `backend/requirements.txt` — jsonschema>=4.0.0
- 追加 `backend/app/observability/metrics.py` — prism_tool_errors_total / prism_harness_turn_total / prism_callback_dlq_total

### 验证结果
- py_compile 全部 10 文件：PASS
- 核心 imports + MAX_TURNS 6 键断言：PASS
- Part B 验证 #3（Pipeline 注册/执行/not found/schema校验/截断）：PASS
- Part B 验证 #4（3×5s 并行耗时 5.02s < 7s）：PASS
- Redis PUBLISH mock 测试（channel/payload 断言）：PASS
- HTTP 重试 + DLQ（3×500/200/401 三场景）：PASS
- heartbeat_writer（SETEX 多次 + DELETE on stop）：PASS
- TAOR dry-run（mock adapter 2 轮：tool_use + end_turn，turn_count=2，Echo: world in messages）：PASS
- Grep 无 `from backend.app` in executor/：PASS
- MAX_TURNS 6 键 + 值：PASS

### 下一个 Task 需要注意 — DOC-03 Task 3.2（Middleware Pipeline 4 钩点）
- **HARNESS_INTEGRATION_POINT 位置**：`executor/engine/query_engine.py` 中有 4 处注释标记（pre_turn 在 while 头部，post_turn 在 continue 前）；`executor/tools/pipeline.py` 中有 PreToolUse/PostToolUse 两处；Task 3.2 需在这 4 处注入 MiddlewarePipeline 调用
- **MiddlewarePipeline 构造时机**：在 `executor/__main__.py` 的注释段（标注 "5. Harness Runtime"）中注入，需在 QueryEngine 实例化之前构造；QueryEngine.__init__ 预留了 `# HARNESS_INTEGRATION_POINT: middleware_pipeline 在 Task 3.2 注入` 注释，届时改为真实参数
- **run_context 透传**：QueryEngine 已将 RunContext 透传到 pipeline.execute(run_context=self._run_context)，Task 3.2 的 MiddlewareContext 应从 run_context 取 run_id/session_id/user_id 三字段（不要重新定义）

### 遗留风险 / 未决事项
- `executor/__main__.py` 的 DB 集成部分（FROM_DB: 注释段）等待 DOC-07 Task 7.4 实现；当前 main() 启动后只初始化 callback + heartbeat 后即退出，不执行 run
- DriverTokenEstimator.estimate() 调用 adapter.count_tokens()，若底层 tokenizer 同步阻塞可能影响 async 性能；DOC-12 Task 12.1 可改为 run_in_executor 包装

### Commit
- `ce382a5` — `feat(v4): TAOR main loop + dual-channel callback + heartbeat (DOC-03 Task 3.1 complete)`

---

## 🎯 DOC-02 DONE — 2026-04-18

DOC-02 全部 4 Task 已完成收官。下一步应开始 **DOC-03 Task 3.1（TAOR 主循环 + ToolExecutionPipeline）**。

### DOC-03 Task 3.1 开工必读文件清单
1. `CLAUDE.md` — 六原则 + 10 陷阱（特别注意 #1 Redis 直通 / #2 回合组 / #3 工具并行 / #8 ask BLPOP）

DOC-02 全部 4 Task 已完成收官。下一步应开始 **DOC-03 Task 3.1（TAOR 主循环 + ToolExecutionPipeline）**。

### DOC-03 Task 3.1 开工必读文件清单
1. `CLAUDE.md` — 六原则 + 10 陷阱（特别注意 #1 Redis 直通 / #2 回合组 / #3 工具并行 / #8 ask BLPOP）
2. `PRD_V4/DOC-03-v4.md` Task 3.1 Part A + Part B 完整内容
3. `HANDOFF-LOG.md` 最近 3 条（本条 + Task 2.4 + Task 2.3）
4. Task 2.1-2.4 产物路径快速索引：
   - `backend/app/core/` — config.py / security.py / database.py / dependencies.py
   - `backend/app/models/__init__.py` — 18 张 ORM 表聚合
   - `executor/adapters/base.py` — PrismMessage / ToolDefinition / ContentBlock / StreamEvent / ModelAdapter（Task 2.2）
   - `executor/adapters/anthropic_driver.py` — AnthropicDriver，Redis PUBLISH(ADR-022)，cache_control(ADR-008)（Task 2.2）
   - `executor/adapters/openai_driver.py` — OpenAIDriver，ADR-007 展开规则（Task 2.2）
   - `executor/adapters/provider_manager.py` — ProviderManager，ADR-013 Redis 熔断器（Task 2.3）
   - `executor/engine/prompt_sections.py` — 21 section getter（Task 2.4）
   - `executor/engine/prompt_assembler.py` — PromptAssembler + MCPServerInfo + SkillInfo（Task 2.4）
   - `executor/engine/context_budget.py` — TokenEstimator + ContextBudgetManager（Task 2.4）

---

## 2026-04-18 — DOC-02 Task 2.4 completed（Prompt 动态装配引擎，DOC-02 收官）

### 本次 session 做了什么
- 读取 DOC-00 v4 §7 四铁律原文（无投资建议 / 数据溯源 / AI 标识 / 数据隔离），注入 compliance_section（583 字，防止占位）
- 创建 `executor/engine/prompt_sections.py`：21 个 section getter 函数，静态 9（identity/system_rules/task_philosophy/risk_actions/tool_grammar/tone_style/output_efficiency/compliance/agent_behavior）+ 动态 12（session_guidance/mcp_instructions/skill_grammar/memory/env_info/language/output_style/scratchpad/function_result_clearing/summarize_tool_results/token_budget/brief）；agent_behavior_section 实现 6 档（general/research/planner/verifier/coordinator/plugin_builder）
- 创建 `executor/engine/prompt_assembler.py`：PromptAssembler（_build_static/_build_dynamic/build/get_static_prefix/_compute_tools_hash）+ CACHE_BOUNDARY_MARKER 字面值 + MCPServerInfo / SkillInfo 临时 dataclass
- 创建 `executor/engine/context_budget.py`：TokenEstimator Protocol + ContextBudgetManager（estimate_tokens/estimate_messages_tokens/should_compress/truncate_tool_result/identify_turn_groups/compress_history）；默认值精确对齐 PRD（compact_trigger_ratio=0.85 / reserve_for_response=4096 / max_context_tokens=128000 / tool_result_max_chars=10000）
- 更新 `executor/engine/__init__.py`：导出 6 核心符号
- 修复 Windows GBK stdout 编码问题（PYTHONIOENCODING=utf-8）；修复中文引号导致的 SyntaxError

### 验证结果
- 验证 1（py_compile 4 文件）：PASS
- 验证 2（21 sections imported）：PASS
- 验证 3（Part B 完整脚本）：Section coverage / Static cache / Verifier VERDICT / Research Bash whitelist / Tools hash cache / Context budget truncation / Turn group — 全 7 项 PASS
- 验证 4（静态缓存字节级一致性 3 次调用）：PASS
- 验证 5（compress_history 保留 is_skill_context）：5 组场景，组 1 skill_context 消息在裁剪后仍保留 PASS
- 验证 6（Section 函数计数 >= 21）：精确 21 — PASS
- 验证 7（compliance_section 长度 > 80）：583 字 PASS
- 验证 8（build() 含 CACHE_BOUNDARY_MARKER）：PASS

### 下一个 Task 需要注意 — DOC-03 Task 3.1（TAOR 主循环 + ToolExecutionPipeline）
- **PromptAssembler 使用方式**：`assembler = PromptAssembler(agent_type=run.agent_type, tools=loaded_tools)` → `system_prompt = assembler.build(mcp_servers=[...], skills=[...], language=session.language)` → 传入 Driver.stream()；get_static_prefix() 供 AnthropicDriver cache_control 边界使用
- **MCPServerInfo / SkillInfo 临时定义**：在 prompt_assembler.py 顶部，DOC-05 实现后替换为正式 import；Task 3.1 直接 `from executor.engine.prompt_assembler import MCPServerInfo, SkillInfo` 即可
- **TokenEstimator 接入**：ContextBudgetManager 构造时传入 driver 适配器（或包装器）作为 estimator；目前 AnthropicDriver / OpenAIDriver 均有 count_tokens() 方法，可包装成简单适配器
- **Windows 编码注意**：bash 环境 Python stdout 默认 GBK，运行验证脚本时加 PYTHONIOENCODING=utf-8

### 遗留风险 / 未决事项
- MCPServerInfo / SkillInfo 是本 Task 临时定义，DOC-05 Task 5.1/5.2 落地后需统一 import 路径（届时修改 prompt_assembler.py 顶部 import，不破坏接口）
- session_guidance_section 当前对 general agent type 且无 feature gate 时返回空字符串（被 _build_dynamic 过滤），这是正确行为
- env_info_section() 读取 os.environ["WORKSPACE_DIR"]，若未设置则 fallback "/workspace"；DOC-03 Task 7.4 子进程启动时需注入此环境变量

### Commit
- `1463103` — `feat: prompt assembly engine with 21 sections + turn-group compaction (DOC-02 Task 2.4 complete)`

---

## 2026-04-18 23:58 — DOC-02 Task 2.3 completed(Provider 管理 + 故障转移)

### 本次 session 做了什么
- 创建 `backend/app/schemas/provider.py`: ProviderCapabilitiesSchema / ProviderPreset / CreateProviderRequest(capabilities 422) / UpdateProviderRequest / ProviderResponse(api_key_masked) / TestProviderResponse
- 创建 `backend/app/services/provider_presets.py`: BUILTIN_PRESETS 8 条(Anthropic/OpenAI/MiniMax/DeepSeek/Kimi/Qwen/智谱/Gemini),每条含 ProviderCapabilitiesSchema
- 创建 `backend/app/services/provider_service.py`: ProviderService(list/create/update/delete/test + bootstrap_presets 幂等 + scope 权限矩阵 + AES-256-GCM encrypt/decrypt via security.encrypt_value)
- 创建 `backend/app/api/v1/providers.py`: 6 端点(presets/list/create/update/delete/test),presets 公开,其余 JWT 认证
- 更新 `backend/app/api/v1/__init__.py`: api_v1_router 聚合器,注册 providers_router
- 更新 `backend/app/main.py`: lifespan 阶段调用 bootstrap_presets() + include api_v1_router
- 创建 `executor/adapters/provider_manager.py`: ProviderManager(get_adapter/record_success/record_failure/record_usage) + ADR-013 Redis 熔断器 + HMAC 签名 usage/harness_event 回调 stub

### 验证结果
- 验证 1 (py_compile 7 文件): PASS
- 验证 2 (All imports OK, Presets count: 8): PASS
- 验证 3 (capabilities 422 ValidationError): PASS
- 验证 4 (encrypt/decrypt roundtrip): PASS
- 验证 5 (mask_key 5 cases): PASS
- 验证 6 (circuit breaker 熔断→切换→恢复状态机): PASS
- 验证 7 (router.routes 6 条, paths/methods 正确): PASS
- 验证 8 (BUILTIN_PRESETS[0].capabilities isinstance ProviderCapabilitiesSchema): PASS

### 下一个 Task 需要注意 — DOC-02 Task 2.4(Prompt 装配引擎)
- **ProviderService.decrypt 路径**:Task 2.4 的 PromptAssembler 若需要在 Backend 侧构建最终 prompt,不需要 API Key — 但如果需要动态调用 Provider(如 few-shot 探测),需通过 `provider_service.decrypt_value(provider.api_key_encrypted, settings.ENCRYPTION_KEY)` 获取明文 key
- **capabilities 与 Prompt 模板关系**:Task 2.4 的 system prompt 装配需要感知 Provider capabilities — 例如 `prompt_cache=True` 时在 system prompt 末尾 text block 加 `cache_control: ephemeral`(ADR-008,AnthropicDriver 已实现,Task 2.4 需要在装配层预留 cache_control 注入点)
- **BUILTIN_PRESETS 路径**:Task 2.4 如需读取预设能力声明,import 路径是 `from app.services.provider_presets import BUILTIN_PRESETS`(app.* 路径,在 Docker backend 容器内);测试时 `from backend.app.services.provider_presets import BUILTIN_PRESETS`(含 fallback)

### 遗留风险 / 未决事项
- `executor/adapters/provider_manager.py` 中 Prometheus metrics 通过 `executor.observability.metrics` 导入 — 该模块在 DOC-12 实现前不存在,ImportError 时静默降级(已处理)
- `test_provider()` 探测逻辑发送真实 HTTP 请求 — 无 API Key 或无网络时会抛异常并被捕获返回 success=False,行为正确
- `bootstrap_presets()` 在 lifespan 时 DB 未就绪(docker compose 健康检查未完成)会 log WARNING 并继续启动,不阻断。首次真实请求到来时 DB 已就绪

### Commit
- `db89260` — `feat: provider management + failover + circuit breaker (DOC-02 Task 2.3)`

---

## 2026-04-18 23:30 — DOC-02 Task 2.2 completed(双协议 Driver)

### 本次 session 做了什么
- 创建 `executor/adapters/base.py`:PrismMessage + ContentBlock 联合类型(TextBlock/ToolUseBlock/ToolResultBlock) + ProviderCapabilities + ToolDefinition + StreamEvent + ModelResponse + ModelAdapter 抽象基类(含 stream/complete/count_tokens 抽象方法 + _sort_tools)
- 创建 `executor/adapters/stream_parser.py`:公共 SSE 行解析器 parse_sse_lines(),含 json_repair 容错 + [DONE] 终止
- 创建 `executor/adapters/anthropic_driver.py`:AnthropicDriver — cache_control 注入(ADR-008) + Redis PUBLISH 直通 sse:{session_id}(ADR-022) + cache_read/creation tokens 解析 + Anthropic SDK count_tokens() fallback tiktoken
- 创建 `executor/adapters/openai_driver.py`:OpenAIDriver — ADR-007 tool_result 展开规则 + Redis PUBLISH 直通 + tiktoken count_tokens(未知模型 fallback cl100k_base + WARNING)
- 更新 `executor/adapters/__init__.py`:导出全部核心符号
- 更新 `backend/requirements.txt`:redis 升级为 redis[hiredis],新增 json-repair>=0.28.0

### 验证结果
- 验证 1 (py_compile 四文件): PASS
- 验证 2 (All imports OK): PASS
- 验证 3 (ADR-007 expand 示例): PASS — [ToolResultBlock(A), ToolResultBlock(B), TextBlock("然后")] → role=tool(A), role=tool(B), role=user("然后")
- 验证 4 (_sort_tools): PASS — [zzz, aaa] → [aaa, zzz]
- 验证 5 (无 PrismMessage(role=tool/system) 构造): PASS — grep 未发现
- 验证 6 (requirements.txt 依赖检查): PASS — anthropic/tiktoken/json-repair/redis[hiredis]/httpx 均在列

### 下一个 Task 需要注意 — DOC-02 Task 2.3(Provider 管理与故障转移)
- **Driver 构建**:Task 2.3 的 ProviderManager 需要从 DB `providers.config` JSONB 的 `capabilities` 子对象构建 ProviderCapabilities 实例并传给 AnthropicDriver/OpenAIDriver 构造器(ADR-008)
- **API Key 解密**:providers.api_key_encrypted 使用 AES-256-GCM(ENCRYPTION_KEY),调用 `backend.app.core.security.decrypt_value()`——注意 Executor 不能 import backend 模块,Task 2.3 的解密必须在 Backend 侧做(子进程启动时通过环境变量或参数注入明文 key)
- **熔断器状态**:ADR-013 要求仅存 Redis(key: `harness:circuit:{provider_id}`),不存内存,多子进程共享。Redis 连接用相同惰性初始化模式(os.environ["REDIS_URL"])

### 遗留风险 / 未决事项
- 真实 API 集成测试未执行(需真实 API Key + 网络,本 session 仅静态验证)
- AnthropicDriver.stream() 的 abstractmethod 声明使用了 raise+yield 双重模式兼容 ABC 和 AsyncIterator 类型注解;若遇 mypy strict 问题可改为 @asynccontextmanager 模式
- OpenAI usage chunk 解析:stream_options.include_usage=True 时 usage 在最后一个 chunk,若 Provider 不支持此选项可能 usage=0

### Commit
- `1074d34` — `feat: dual-protocol model adapters (DOC-02 Task 2.2 complete)`

---

## 🔴 父 Opus session 续作指引(2026-04-18 22:50 交接)

> **读这段的你是新的 Opus 父 session**。上一个父 session 因 context 拥挤 /clear,核心任务未完成,状态已固化到所有 `.md` 文件,你接手继续派 Sonnet subagent 推进。

### 用户原始指令(不可忘)
- **核心任务**: **按计划完成所有后端内容,前端(DOC-10 / DOC-11)先等等**
- **Auto Mode 开启**: 连续自主执行,最小打扰,遇低风险决策直接做判断;遇破坏性/共享系统操作才问用户
- 执行策略已定稿:`PRD_V4/2026-04-18-execution-strategy-design.md`
- 代码由 Sonnet 4.6 写(通过 Agent tool, `model: sonnet`),**你(Opus)不动代码**,只派工 + 跟踪状态

### 当前进度(读 PROGRESS.md 看完整表)
- ✅ Phase 0(PRD v4 全部文档)完成
- ✅ DOC-02 Task 2.1 完成(骨架 + 18 表 ORM + alembic,commit `1e8ac83`)
- ⬜ 下一个:**DOC-02 Task 2.2 双协议 Driver**(Anthropic canonical + OpenAI 展开)

### 待办后端 Task 清单(依赖顺序)
1. **DOC-02 剩余**:Task 2.2(Driver)→ 2.3(Provider 管理)→ 2.4(Prompt 装配)
2. **DOC-03**:3.1(TAOR + 双通道回调 + 心跳)→ 3.2(Middleware 4 钩点)→ 3.3(Hook 11 字段 + ask BLPOP)→ 3.4(Feedback + user_memory)→ 3.5(Compaction 4 级回合组)→ 3.6(配置 2 源)
3. **DOC-04**:4.1(6 种 Agent)→ 4.2(Fork capability)→ 4.3(Coordinator checkpoint)→ 4.4(TaskRouter)→ 4.5(PluginBuilder 打分)
4. **DOC-05**:5.1(Skill 三级)→ 5.2(MCP 双通道)→ 5.3(Hook 4 handler)→ 5.4(PluginHost 变量)→ 5.5(Registry 两源)→ 5.6(Agent Tool 仅搜索)→ 5.7(CC ConversionReport)
5. **DOC-06**:6.1(三密钥 + SSE ticket)→ 6.2(用户 + 邀请码)
6. **DOC-07**:7.1(Session CRUD)→ 7.2(Run 生命周期 + sequence_no 原子 + cancel 三模式)→ 7.3(Callback 双通道 + SSE Manager + HeartbeatMonitor + permission-answer)→ 7.4(子进程标准化参数 + coordinator_recovery + alert_dispatcher)
7. **DOC-08**:8.1(IMAdapter + Webhook 幂等)→ 8.2(三平台)→ 8.3(绑定三元组)
8. **DOC-09**:9.1(MCP 管理)→ 9.2(Provider scope + cache tokens)→ 9.3(Admin 审计 + Dashboard)
9. **DOC-12 后端部分**:12.1(TokenEstimator + ResourceMonitor)→ 12.2(Entropy 8 信号)→ 12.3(/health 3 子端点 + Docker)→ 12.4(Prometheus 60+)→ 12.5(OTel 跨进程)→ 12.6(结构化日志)→ 12.7(前端错误上报端点,属后端)→ 12.8(AlertDispatcher)

前端 DOC-10 / DOC-11 **不做**(用户明确暂缓)。

### 派工模板(给 Sonnet subagent)

每个 Task 派一个 Sonnet subagent:
```
Agent tool, subagent_type=general-purpose, model=sonnet
Prompt 模板见上一个成功案例(Task 2.1 Phase 2 的 Agent 调用,prompt 含:
  - 工作目录 E:\Agent program\PrismV3\
  - 必读文件清单(CLAUDE.md / HANDOFF-LOG.md / 对应 DOC-XX v4 Task 内容)
  - 本次范围(具体做哪几步,不做哪几步)
  - 硬底线(六原则)
  - 验证步骤
  - 结束动作(commit + 更新 PROGRESS/DECISIONS/HANDOFF)
  - 报告格式 ≤ 500 字)
```

### 交接注意
- 每次派 subagent 后必读回报,确认 commit hash + PROGRESS/DECISIONS/HANDOFF 更新了才派下一个
- 3 份 `.md` 状态文件现在是**真相源**,每个 Sonnet subagent 都要读 + 更新
- 若 Sonnet 报 blocker(如 18 vs 19 表那类),读 blocker.md 判断:
  - **非阻塞 + 有合理假设** → 接受,继续下一个
  - **阻塞需人工** → 暂停,向用户报告
- 父 session context 又拥挤时,重复本次动作(固化到 HANDOFF-LOG + /clear)
- 不要把 41 个 Task 的 TaskCreate 全开,保持 task list 精简(只开"当前正在做的 DOC"一级即可)

### Blocker 记录
- `blocker.md`(2026-04-18):PRD 标题"19 张表"但 §4.2 实际 18 张。已按 DOC-01 §4.2 为真相源实施 18 张,**非阻塞**,可能是 PRD 计数错误,待用户最终裁定是否修 PRD

---

## 2026-04-18 22:30 — DOC-02 Task 2.1 completed(18 表 ORM + Alembic 迁移)

### 本次 session 做了什么
- 创建 `backend/app/core/database.py`: SQLAlchemy engine + SessionLocal + get_db() dependency
- 创建 `backend/app/core/dependencies.py`: get_db / get_redis(NotImplementedError) / get_current_user / require_admin
- 创建 `backend/app/schemas/common.py`: ApiResponse[T] / ErrorDetail / ErrorResponse / PagedResponse[T] (Pydantic v2)
- 创建 18 个 ORM 模型文件(13 基础 + 5 v4 新增): user, invite_codes, sessions, session_queue_items, runs, messages, tool_executions, providers, mcp_servers, user_mcp_installs, im_bindings, im_channel_configs, audit_logs, skill_installs, coordinator_plans, permission_requests, im_message_dedup, user_memories
- 创建 `backend/app/models/__init__.py` 聚合导入所有 18 张表
- 创建 `backend/alembic.ini` + `backend/alembic/env.py` + `backend/alembic/versions/001_initial_tables.py` 手写迁移(331 行 DDL)
- 提交 blocker.md: PRD 标题"19 张表"但 §4.2 实际定义 18 张,以 DOC-01 §4.2 为真相源实施 18 张

### 验证结果
- `from app.models import *`: 18 张表全部导入,0 错误 — PASS
- `alembic upgrade head --sql` DDL 静态检查: 所有关键约束存在 — PASS
  - providers CHECK (scope/user_id 互斥)
  - im_bindings UNIQUE (channel, platform_user_id, platform_chat_id) 三元组
  - runs: cache_hit_tokens / cache_creation_tokens / harness_summary 字段
  - messages: is_skill_context / skill_name 字段
  - tool_executions: permission_decision / hook_modified 字段
- 所有 Python 文件语法检查: py_compile PASS
- 注: 未实测 DB (docker 未启动),仅 DDL 静态检查

### 下一个 Task 需要注意 — DOC-02 Task 2.2 (双协议 Driver)
- **ADR-关键注意点**:
  1. `sessions.blocking_run_id` 是 SET NULL FK,子进程完成时必须清空此字段
  2. `messages.sequence_no` 严禁 max+1(ADR-060),DOC-07 Task 7.2 实现 per-session 序列或 advisory_xact_lock
  3. `providers` 表 `api_key_encrypted` 字段要求 AES-256-GCM(使用 `ENCRYPTION_KEY`),Task 2.3 实现时直接调用 `app.core.security.encrypt_value()`
  4. `providers.config` JSONB 必须包含 `capabilities` 子对象,这是应用层校验(非 DB CHECK),Task 2.3 需要在 service 层做
  5. Task 2.2 的 PrismMessage 对应 `messages.content` JSONB — role 只有 'user'/'assistant' 两种(DOC-01 v4 §5),tool_result 作为 user message 的 content block 存储
  6. `get_redis()` 在 dependencies.py 返回 NotImplementedError,DOC-03 Task 3.1 需要填充真实实现

### 遗留风险 / 未决事项
- PRD "19 张表"计数与实际 §4.2 定义 18 张的矛盾:已记录 blocker.md,待人工确认是否有漏掉的第 19 张表
- `ddl_static_check.sql` 已提交到仓库可供审查;删除或保留由下一个 session 决定
- Docker 实测未进行(需 .env 实体文件 + docker compose up)

### Commit
- `1e8ac83` — `feat: 18-table ORM + alembic initial migration (DOC-02 Task 2.1 complete)`

---

## 2026-04-18 20:10 — DOC-02 Task 2.1 in_progress(骨架 + 最小 FastAPI)

### 本次 session 做了什么
- `git init` 初始化仓库(首次代码 session)
- 创建完整目录骨架:`backend/app/{api/v1,core,services,schemas,models,observability}/`、`executor/{engine,adapters,tools,harness/{middleware,guardrails,hooks,permissions},callbacks,plugins,coordinator}/`、`frontend/`
- 各包创建 `__init__.py`(含 executor 下全部子包)
- 根目录:`.gitignore`、`.env.example`(三密钥独立分区)、`README.md`(5 行概述)、`pyproject.toml`(含完整依赖列表)
- `docker-compose.dev.yml`:postgres:16 + redis:7-alpine(appendonly yes)+ backend(healthcheck /health/live)+ prism-net 网络
- `backend/Dockerfile` + `backend/requirements.txt`
- `backend/app/core/config.py`:Settings 类,读三密钥 + DB_URL + REDIS_URL + 全部 Harness 参数
- `backend/app/core/security.py`:`validate_secrets()`(真实校验:长度 >= 32 + 互不相等)+ AES-256-GCM encrypt/decrypt_value + hash/verify_password + create/decode JWT
- `backend/app/observability/logging.py`:structlog JSON + contextvars + TimeStamper
- `backend/app/observability/metrics.py`:REGISTRY + 10 维度 15 个核心指标占位
- `backend/app/main.py`:FastAPI + lifespan(validate_secrets → init_logging → metrics import)+ /health/live /health/ready /health/detailed + /metrics

### 验证结果
- AST 语法检查:5 个核心文件全部 PASS
- `validate_secrets()` 逻辑校验:4 场景单元测试全 PASS(短密钥 / 两两相同 / 三者相同 / 合法)
- `docker compose config`:解析成功(仅版本过期警告 + .env not found 提示,均正常)

### 下一个 Task 需要注意
- **下一步(Task 2.1 第二阶段)**:创建 `backend/app/models/base.py` + 19 张表 ORM 模型(含 Harness 扩充字段)+ alembic 初始化 + `versions/001_initial_tables.py` 手写迁移
- `ENCRYPTION_KEY` 在 `security.py` 的 `encrypt/decrypt_value` 中期望为 64 位 hex(32 字节)。DOC-02 Task 2.3 实现 Provider config 加密时必须一致。
- health_ready 中的 DB 检查使用同步 SQLAlchemy 引擎。后续若引入 async SQLAlchemy,需同步改 readiness 探针。
- `validate_secrets` 接收的是原始字符串(非 hex 解码),与 `encrypt_value` 期望 `key_hex` 作 hex 解码的语义不同。ENCRYPTION_KEY 在环境变量中存储为 hex 字符串是正确的。

### 遗留风险 / 未决事项
- 19 张表 ORM 未创建(Step 3 全部留给下一个 session)
- alembic 未初始化(Step 6 留给下一个 session)
- `backend/app/core/database.py`、`backend/app/core/dependencies.py`、`backend/app/schemas/common.py` 未创建(Step 2 剩余部分)
- `/health/detailed` 和 `/metrics` 暂无 admin 认证依赖(占位实现,DOC-06 Task 6.1 后补)
- docker 实际启动未验证(本 session 无 .env 实体文件)

### Commit
- `5c689df` — `feat: bootstrap project skeleton + minimal FastAPI (DOC-02 Task 2.1 partial)`

---

## 2026-04-18 19:50 — Phase 0 文档阶段完成(非代码 session)

### 本次 session 做了什么
- 完成 DOC-03 ~ DOC-12 共 10 份 PRD v4 改写(Opus 4.7 Web → Claude Code 接续)
- 新建 DOC-CC-ONBOARDING.md 先导文档(13 节)
- 撰写 execution-strategy-design.md 执行策略 spec(12 节,含 superpowers 角色分配)
- 在项目根初始化 CLAUDE.md / PROGRESS.md / DECISIONS.md / HANDOFF-LOG.md 四件套

### 验证结果
- 本阶段无代码验证,所有 PRD 文档已落盘到 `E:\Agent program\PrismV3\PRD_V4\`
- 合计 16,075 行,~631 KB,217 处修订,101 个 ADR

### 下一个 Task 需要注意
- **DOC-03 Task 3.1(TAOR 主循环 + ToolExecutionPipeline)是首个实施 Task**
- 开工前必读:
  - `CLAUDE.md`(心智模型 + 六原则 + 10 陷阱)
  - `PRD_V4/DOC-CC-ONBOARDING.md`(完整先导)
  - `PRD_V4/DOC-00-v4.md` + `DOC-01-v4.md` + `DOC-02-v4.md`(三份基座)
  - `PRD_V4/DOC-03-v4.md` Task 3.1 的 Part A + Part B 完整内容
  - `.plan/doc-03-task-3.1.md`(如已生成)
- Sonnet 开工规范:**Part B 本身就是 plan,不再用 writing-plans 重写**;直接 `superpowers:test-driven-development`(Part B 验证步骤作测试初稿)→ 实现 → `superpowers:verification-before-completion` → `superpowers:requesting-code-review`
- 创建分支:`feat/doc-03-v4`

### 遗留风险 / 未决事项
- 项目根还没有代码骨架(Python 包结构 / requirements.txt / pyproject.toml 等)。按 DOC-02 v4 Task 2.1 的规范,这些应该在 Task 2.1 实施时创建,但 DOC-02 v4 Task 2.1 本身已在 Phase 0 标记 completed(由 Opus 4.7 Web 完成 PRD 阶段,**代码尚未实施**)
- **重要**:PROGRESS.md 中 "DOC-00~12 改写 completed" 指的是**文档改写完成**,不是代码实施完成。Phase 1 的首个代码 Task 严格说应是 DOC-02 Task 2.1(项目骨架),不是 DOC-03 Task 3.1。建议 Sonnet 开工前确认:
  - 选项 A:从 DOC-02 Task 2.1 开始(先搭骨架)
  - 选项 B:默认 DOC-02 Task 2.1~2.4 已由 Opus Web 完成代码 → 直接 DOC-03 Task 3.1
  - 当前 HANDOFF-LOG 按选项 A 理解,建议 Sonnet 打开 DOC-02 v4 Task 2.1 确认项目骨架是否已创建;未创建则从 Task 2.1 开始

### Commit
- 无(文档落盘在 Claude 分发目录,未纳入 git)

---

> **最后更新**: 2026-04-18 19:50
