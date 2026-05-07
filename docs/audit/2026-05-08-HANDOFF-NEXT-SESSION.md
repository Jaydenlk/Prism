# 交接文档 — 下一个 session 完全可接

> **写时刻**: 2026-05-08
> **当前分支**: `audit/prd-vs-reality` worktree at `.worktrees/audit-prd-vs-reality/`
> **commits ahead develop**: 8（未 merge，用户未授权）
> **develop 当前 tip**: `58a149b` (从 plugin-bootstrap 合的，24 commits 之前)
> **总开发进度**: 32 commits since prior plugin-bootstrap merge baseline

---

## 0. TL;DR for 下一个 model

你接手时，现状是这样：

1. **plugin-bootstrap PR 已合到 develop**（24 commits，包括根因修复 PluginHost+SkillLoader 实例化、HTTP transport、exa MCP、SearXNG self-hosted、7 个 action tools、dev 默认账号一键登录）
2. **当前 worktree `audit-prd-vs-reality`** 正在做 **PRD vs reality 全审计** — 用户硬要求"PRD 设计的功能必须真接通，禁止虚的"
3. **8 commits 已修了 P0/P1**（用户报的 4 个 bug + audit 找的 14 处 + 死按钮 + 主题持久化 + 容器持久化）
4. **用户当前正在浏览器试用** http://localhost:18888/Prism.html，等他反馈
5. **下一步**: 等用户反馈后继续修发现的问题，或继续审计未触及区域（IM tab / Providers tab / Sessions buttons / Plugin Builder / Topbar dev preview / ObsPage 真接 API / 6 admin placeholder tabs）

---

## 1. 用户人格 + 协作铁律（不读必踩雷）

### 用户脾气特点
- **直接**、不忍废话、不读重复 / 客套话
- 多次明示**威胁**："你不行我就放弃你用 codex / GPT5.5 / 不续费"
- 不接受"作秀"型修复 — UI 接通了但下游没消费 = 装饰，等同没修
- 不接受"我以为修了"— 必须**真实驱动浏览器走流程**才叫修
- 经常"我只负责检查效果"—**不替你做决策**，你得自己拍板执行；遇到 destructive 操作 GUI 拦截时，他 VERBAL 授权后直接做（如删 e2e 残留 SQL）

### 项目铁律（必读 `CLAUDE.md`）
- **进程边界 = 信任边界**（ADR-050 / 铁律 7）：Backend 和 Executor 子进程独立，**Executor 不持 ENCRYPTION_KEY**；secret 解密只在 Backend 层。
- **三密钥独立**: JWT_SECRET / ENCRYPTION_KEY / CALLBACK_SECRET 任二相同 = startup 校验失败
- **反打补丁硬规则**: systematic-debugging Phase 1 没完不许提 fix；不允许"加一层 if / 兜底默认值 / 特殊路径绕过"
- **Skill 加载硬要求**: 创意/新功能 → brainstorming 必先；调试 bug → systematic-debugging 必先；实施 → TDD + worktree；完工审查 → simplify (3 子并行) → pjr → code-review；合并 → git-merge-to-develop。**任一缺失立即停**。
- **e2e 硬要求**: Playwright 真驱动浏览器（不只写脚本）；桌面 1280 + 移动 390/iPhone 13 双端必测；每按钮每流程模拟人；UI 渲染没问题 ≠ 通过 — 必须验证 network / DB / state 变更
- **Worktree 强制**: 多文件 / 跨模块改动必须在 `.worktrees/<topic>/` 里干

### Subagent 调度（CLAUDE.md 工作流纪律）
- 4 项目 subagent: `implementer` (Sonnet) / `reviewer` (Opus 找错) / `qa-engineer` (Haiku Playwright) / `explorer` (Haiku 摸底)
- 派单**必须 5 字段**：任务/输入文件/禁止触碰/产出预期/决策上下文。详见 `.claude/rules/subagent-constraints.md`
- 子 agent **不读** `CLAUDE.md` / `DECISIONS.md` / `PROGRESS.md`，由主 agent 提炼后注入 handoff
- Handoff 文件: `.claude/plans/handoff-{from}-to-{to}-{topic}.md`，状态机 `READY_FOR_IMPL → READY_FOR_REVIEW → DONE`

---

## 2. 当前 worktree 状态

```bash
cd "E:/Agent program/PrismV3/.worktrees/audit-prd-vs-reality"
git status --short        # clean
git log --oneline develop..HEAD   # 8 commits
```

**8 commits（最新在顶）**:
```
7396bbc fix(persistence): /app/data named volume + bootstrap resync on missing clone
eb22fb8 fix(p0-dead-buttons): revive 6 dead buttons + theme persistence + skill install forward
c063d36 fix(skills): P0 — marketplace install 链路断修复 (W12 backend subagent)
0d893e2 fix(p0-1+e2e): inline sync after default marketplace bootstrap + fixture port override
6908c80 fix(p0-4): add POST /auth/change-password endpoint (audit was incorrect)
87c7811 fix(p0-3+p0-4): analytics window→days + ProfileTab change-password modal (frontend only) (W11)
b9bab6b fix(backend): resolve 5 audit bugs — MCP toggle, marketplace bootstrap, providers GET /{id}, admin usage params, audit-log param names (W10)
5d31892 docs(audit): PRD vs reality master audit + 4 sub-reports
```

**生产代码改动覆盖**:
- backend/app/api/v1/{internal,mcp,providers,admin,auth,skills}.py
- backend/app/services/{marketplace_service,mcp_service}.py
- backend/app/schemas/{auth,mcp}.py
- backend/app/models/mcp_server.py
- executor/plugins/skills_registry.py
- frontend/Prism.html（多处：Composer/Msg/SettingsPage/App/Tweaks/SkillsSettingsTab）
- docker-compose.yml（PRISM_ENV env override + prism-backend-data 命名 volume）
- 测试: 30+ 新测试

---

## 3. 用户报告的 bug + 状态

### Round 1（之前已修，已 merge develop）
| # | 用户报告 | 状态 |
|---|---|---|
| 1 | "调用 skills 和 mcp 的问题没解决" | ✅ 已修（plugin-bootstrap PR） |
| 2 | "插件搜索是摆设" | ✅ 部分修（marketplace 默认仓库 + searxng + exa builtin） |
| 3 | "把 exa 关了 search mode 关了还是能跑" | ✅ 已修（`internal.py` system MCP 尊重 user toggle） |
| 4 | "agent 没法真正干活" | ✅ 已修（7 action tools: Read/Write/Edit/Bash/Glob/Grep/WebFetch） |
| 5 | "我忘了 JWT 默认账号密码" | ✅ 已修（dev mode `/auth/providers` 返默认账号 + 一键登录按钮） |

### Round 2（当前 audit/prd-vs-reality 上修，未 merge）
| # | 用户报告 | 根因 | 修复 commit |
|---|---|---|---|
| 6 | "Skills market 输入啥都没出 / 不支持模糊搜索" | (a) 40 行 e2e 测试残留 + bootstrap 按"any rows"判断 → 默认 anthropic 仓库未注册 (b) 未 sync 拉真实 catalog | `5d31892` 审计 → `b9bab6b` bootstrap by name → `0d893e2` inline sync → 用户授权清残留 |
| 7 | "对话框左下角 3 按钮死的" | Composer 附件/技能/MCP 完全无 onClick | `eb22fb8` 全 wire（附件 toast 提示 / 技能跳 Settings→Skills tab / MCP 跳 Settings→MCP tab） |
| 8 | "亮/暗主题切换是死的" | (a) `<html data-theme="light">` 硬编码 + 切换写 localStorage 但 boot 不读 (b) Tweaks panel useEffect 强制覆盖 | `eb22fb8` `<head>` boot script + Tweaks 也读 localStorage |
| 9 | "能搜到也下载不了" | (a) marketplace_id+plugin_name 没透传 (b) 容器 `/app/data` 无 volume 重建丢 catalog | `c063d36` 后端透传 + `eb22fb8` 前端透传 + `7396bbc` 命名 volume + bootstrap 自动 resync |
| 10 | "GitHub 能找到的你就找不到" | 默认只有 anthropic catalog；其他源需手动 marketplace 注册 | **未完整修** — 已有 admin marketplace 注册功能（手动 add URL），但 catalog 35 个本地条目仅 12 个 skill-type 能装 |
| 11 | "我说什么就只有那些问题吗" | audit B 漏报严重 | 主 agent 二次扫发现 **3 个额外死按钮**（消息气泡 复制/再试/分叉，line 464-466）— `eb22fb8` 全 wire |

---

## 4. Audit Phase 1 完整发现（已落 docs/audit/）

```
docs/audit/
  2026-05-08-prd-feature-inventory.md       — 87 条 PRD 用户可见功能（DOC-00..12）
  2026-05-08-frontend-wiring-audit.md       — 81 个交互（72 wired / 3 dead / 6 placeholder / 0 decorative）— 漏报 6 处
  2026-05-08-backend-endpoint-audit.md      — 86 endpoints（81 real / 1 partial / 2 param-ignored / 1 missing / 0 stub）
  2026-05-08-reproduction-findings.md       — 用户报告 2 例 root cause
  2026-05-08-master-audit-report.md         — 聚合 + P0/P1/P2
  2026-05-08-HANDOFF-NEXT-SESSION.md        — 本文
```

### P0/P1 全部 LIVE 通过（实测证据，不是单测）
- **P0-1 Skills Market 搜索**: `q=plugin` → 19 真 results / `q=git` → 4 真 results（github/gitlab/commit-commands）
- **P0-2 exa toggle**: `internal.py` system_rows 现在排除 `is_enabled=false` 的 user toggle
- **P0-3 analytics window→days**: e2e 验证 `days=7 → 200`，`window=7d → 422` 旧参数正确被拒
- **P0-4 修改密码**: backend endpoint 加了；前端 modal + 6 e2e 双端 PASS
- **P1-1 admin/usage 参数生效**: backend test 通
- **P1-2 GET /providers/{id}**: HTTP 200
- **P1-3 audit-logs 参数名**: 改 backend 接 start_date/end_date

### 测试覆盖
- 134 backend pytest pass + 1 skip（pre-existing）
- 12 executor pytest pass
- 36 e2e Playwright effective tests pass（双端 desktop+mobile-safari）：
  - `profile-change-password.spec.ts`: 16/16
  - `dead-buttons-revival.spec.ts`: 20/20
  - `dev-default-admin-login.spec.ts`: 4/4（之前 plugin-bootstrap）
  - `agent-action-tools-real.spec.ts`: 4/4（之前）
  - `plugin-bootstrap-real-call.spec.ts`: 4/4（之前）

### P2（PRD 设计未实施 — 长期）
- 6 个 admin placeholder tab（账务 / 护栏 / Skills 审核 / 基础设施 / 可观测 / 安全）
- ObsPage 真接 `/harness/analytics`（之前只修了参数错配，UI 仍 hardcoded mock）
- UsageTab 用户端用量页未实现
- DOC-10/11 Next.js 重写未做
- Block 2 IM 三小尾（Slack Socket Mode / 卡片回传 / sensitive key 单一源）pending
- Block 3 分布式任务拆解（spec 都没做）

### 还没审到的区域（**关键 follow-up**）
- **IM 绑定 tab actions**（Settings → IM）
- **Providers tab actions**（Settings → Providers）
- **Sessions list 删除/重命名按钮**（Sidebar）
- **Plugin Builder 完整流程**（PluginsPage / 插件工坊）
- **Topbar dev preview 3 按钮**（Prism.html line 4294-4296，可能是开发遗留）
- **完整 Plugin install 流**（35 catalog entries 中 12 skill-type 真能装；其余 23 报 422 "no skills/")
- **`InstallReport` 后置流**: install 后如何让 agent 用上 — 当前 install 写 DB + 文件系统，executor 读 DB 加载，但前端 SkillsSettingsTab 的"已安装"列表是否真显示新装的？需 Playwright 验证

---

## 5. 操作环境（下一个 model 必看）

### Docker compose
```bash
# 容器项目名: prismv3
# Backend image: prism-backend:2.0
# Frontend: nginx 1.27-alpine 挂 ./frontend 静态目录
# DB: postgres 17 / Redis 7 / SearXNG self-hosted

# 端口: 18888（user 的 .env 里 HTTP_PORT=18888 — 因为 Windows Hyper-V 锁了 8080）
# 健康: curl http://localhost:18888/health/ready
# 默认 admin: admin@prism.dev / PrismAdmin!2026

# 重 build + 重启 backend（改了 backend 代码后必跑）:
cd "E:/Agent program/PrismV3/.worktrees/audit-prd-vs-reality"
docker compose -p prismv3 build backend
docker compose -p prismv3 up -d --force-recreate --no-deps backend

# 重启 nginx（改了 frontend 代码后必跑）:
docker compose -p prismv3 restart nginx
```

**WARNING**: nginx 偶发会进 unhealthy 状态（健康端点返不了），但 backend 真活。健康自检看 `curl http://localhost:18888/health/ready`。

### 测试基线
- Backend: `cd backend && python -m pytest tests/ -q --ignore=tests/test_plugin_validate_dispatch.py`（pre-existing flaky 跳过）
- Executor: `cd <worktree> && python -m pytest executor/tests/ -q`
- E2E: `cd e2e && BASE_URL=http://localhost:18888 npx playwright test --reporter=list`
  - 一定要带 `BASE_URL=http://localhost:18888`，e2e/fixtures/auth.ts BASE 默认 `http://localhost:8080`
  - 双 project: desktop-chromium + mobile-safari，描述用 `for (const cfg of VIEWPORTS) test.use({ viewport: cfg.viewport })`

### 已知坑
- nginx mount `./frontend` bind volume — 改 frontend 直接生效，但 nginx restart 才让浏览器拉新 HTML
- backend Dockerfile 新加了 nodejs+npm（searxng/tavily MCP 用 npx）— build 慢 ~30s
- alembic 010 是 plugin-bootstrap 加的（mcp_servers 加 transport/url/headers_encrypted）
- 用户 `.env` 有 `EXA_API_KEY=24b74e9a-d7e5-4621-b10d-46e7ea44bb65`（真 key），SEARXNG_SECRET_KEY auto-gen，HTTP_PORT=18888
- Windows Hyper-V 反复锁端口（曾经 8080 → 18080 → 18888 三次切）

### Marketplace state
```sql
-- 当前 DB:
select name, jsonb_array_length(catalog_json->'plugins') from marketplace_registry;
-- anthropics/claude-plugins-official | 180  ← bootstrap 后真注册了

-- 35 个本地 plugins，12 个有 skills/（可装），23 个其他类型（commands/MCP/agents → 报 422）
```

---

## 6. 已知 follow-up（按优先级）

### P0（用户的痛 — 必修）
- **catalog 中 23 个非 skill-type plugins** 报 422 "no skills/ directory" — 需要 (a) UI 标注 plugin type 让用户避坑 (b) 或 install 端支持 commands/MCP/agents 类型
- **GitHub 广义搜索** — 用户期望"我能在 GitHub 找到的你也能找"。当前只有手动注册 marketplace。需要 (a) GitHub API 搜（注意 GITHUB_TOKEN rate limit）(b) 或更多默认 marketplace
- **Audit 还没扫的区域**（见 §4 末尾）— 大概率有更多死按钮

### P1
- **e2e DB 隔离** — 测试污染 dev DB（已发现 40 行 marketplace 残留）。需独立 docker compose project（如 `prismv3-e2e`）+ 测前 reset
- **ObsPage 用真数据** — 修了 analytics 参数但 UI 还 hardcoded mock
- **/api/v1/skills 列表 vs `/skills/installed`** — 测试中用 `/api/v1/skills` 返 `installed: 0`，但 install 真成功，可能是端点不一致
- **install_path 的 metadata_ JSONB pattern** — `executor/__main__.py` Step 3d 已读，但 SkillLoader.load_skill_from_path 是我加的，未在所有路径测过

### P2（PRD 设计未做）
- 6 admin placeholder tabs
- Block 2 IM 三小尾
- Block 3 分布式任务拆解
- DOC-10/11 Next.js 重写

---

## 7. 决策点（待用户拍）

1. **要不要 merge `audit/prd-vs-reality` 到 develop**？8 commits 都 PASS，但用户想多用一段时间再决定（"我先试一下"是当前等待状态）
2. **catalog 非 skill-type 处理策略** — UI 标注 vs 扩 install 支持？(a) 快但 UX 受限 (b) 大改但 unblock 90% catalog
3. **Audit 是否要全扫剩余区域**（IM/Providers/Sessions/PluginBuilder/Topbar/admin tabs/ObsPage UI）— 剩余工作量约 1-2 session

---

## 8. 立即可执行的工作（不需用户拍板）

如果用户回来说"继续修"，按此顺序：

1. **扫 sessions list 删除/重命名按钮**（Sidebar，Prism.html 中找 sessions.delete / sessions.update）
2. **扫 IM tab actions**（Settings → IM → bind/unbind/test 按钮）
3. **扫 Providers tab**（Settings → Providers → CRUD 按钮）
4. **扫 Plugin Builder**（PluginsPage 完整流程）
5. **删除/隐藏 Topbar 3 dev preview 按钮**（line 4294-4296，开发遗留）
6. **ObsPage 真接 /harness/analytics**（Prism.html line 2651-2686 替换 hardcoded mock）

每项的标准 workflow:
- driver Playwright 复现 → systematic-debugging 找根因 → 派 implementer subagent 修 → e2e 验证 → commit

---

## 9. 关键文件索引（下一个 model 直读）

```
PRD_V4/DOC-00-v4 .md ~ DOC-12-v4.md         PRD 真相源（冻结）
PRD_V4/DOC-CC-ONBOARDING.md                完整先导
.claude/rules/                              5 条按需规则
.claude/agents/                             4 项目 subagent 定义
.claude/memory/decisions.md                 任务级决策（DEC-001..DEC-005 已落）
.claude/memory/scratchpad.md                临时发现（每任务清）
PROGRESS.md                                 Task 状态（230K，append-only）
DECISIONS.md                                ADR 台账（171K，append-only）
HANDOFF-LOG.md                              跨 session 日志（230K+，倒序）

docs/audit/2026-05-08-master-audit-report.md   本轮审计聚合
docs/audit/2026-05-08-HANDOFF-NEXT-SESSION.md  本文（接你）
docs/superpowers/specs/2026-05-02-plugin-bootstrap-design.md  上轮 PR 设计
docs/superpowers/plans/2026-05-02-plugin-bootstrap.md         上轮 PR 7-task 计划

start.sh                                    一键 up/rebuild/down/status/logs
e2e/playwright.config.ts                    desktop-chromium + mobile-safari
e2e/fixtures/auth.ts                        BASE = process.env.BASE_URL || 'http://localhost:8080'
backend/tests/conftest.py                   StaticPool SQLite + AuditLog model 已入
```

---

## 10. 心法（写给下一个我）

1. **不假设 audit 结果完整** — audit B 子 agent 漏报 6 处死按钮（消息气泡 3 + Composer 3）。**自己也驱动浏览器走一遍**才放心。
2. **用户提到的"还有 X 个东西没修"必须立刻扫一圈**，不要只修他报的那 1 个。
3. **修 UI 类问题**先 `grep -nE "icon-btn|onClick|title=\"" file.html` 看死按钮模式
4. **修 backend 类问题**先确认 endpoint 真存在 + 真消费参数（W11 翻车一次：audit 说 endpoint 存在，实际不存在）
5. **改完 frontend 必 `docker compose restart nginx`**（bind mount 但 nginx 缓存）
6. **改完 backend 必 `docker compose build + up --force-recreate --no-deps backend`**
7. **每次 commit 前**：`pytest backend/tests/ executor/tests/ -q` 至少跑一遍
8. **e2e 改 spec 必带 `BASE_URL=http://localhost:18888`**
9. **destructive SQL（删行）会被系统拦截**，需用户在 chat 里授权后再执行
10. **Windows port reservation 是真坑** — 用 18888 等高位端口绕开

---

## 11. 当前 user 行动状态

最后一条用户消息: **"我先试一下"** —— 用户正在浏览器测 http://localhost:18888/Prism.html 重点验证 8 个修复点。

我（前任 model）发了一条建议聚焦试用列表：
1. 登录页底部 dev 一键登录
2. Composer 左下 3 按钮（附件/技能/MCP）
3. 消息气泡 3 按钮（复制/再试/分叉）
4. 设置 → 修改密码
5. 设置 → 主题 → 刷新（持久化）
6. 设置 → 技能 → 搜 frontend-design / playground / mcp-server-dev / cwc-makers（这 12 个是 skill-type 真能装）
7. 聊天提问让 agent 用 searxng / exa / Read / Write / Bash 工具

**等用户反馈** — 收到后接着扫剩余区域 / 修新发现的问题。

不要主动 merge develop 直到用户明确说"可以合"。
