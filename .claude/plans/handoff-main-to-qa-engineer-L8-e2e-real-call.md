# Handoff: main → qa-engineer (Task 7 / W7 / L8)

## 状态: BLOCKED

> **Pre-condition**: Batch 2 ✅ 全部 commit (HEAD 81ba928 含 W5 + W6 集成)。

## 任务描述
Playwright 真实驱动浏览器双端（desktop 1440×900 + mobile-safari iPhone 13）端到端验证 plugin bootstrap 全链路：admin 看见 exa 自动注册 → 用户起会话问"今天 AI 新闻" → agent **真调** `mcp__exa__web_search_exa` → 渲染**真实** URL 结果。

## 输入文件范围（仅这些）
- 创建: `e2e/tests/plugin-bootstrap-real-call.spec.ts`
- 只读参考:
  - `e2e/playwright.config.ts` (现有 2 projects: desktop-chromium / mobile-safari)
  - 任意现有 spec 比如 `e2e/tests/skills.spec.ts` 学 selector 风格
  - plan Task 7 段落（`docs/superpowers/plans/2026-05-02-plugin-bootstrap.md`）
- 操作环境（Bash）:
  - 启 docker compose: `docker compose -p prismv3 up -d --build --force-recreate backend executor`
  - 跑测试: `cd e2e && BASE_URL=http://localhost:8080 npx playwright test plugin-bootstrap-real-call.spec.ts --reporter=list`

## 禁止触碰
- 任何 backend / executor / frontend 源代码
- `.env`（已由主 agent 配好 EXA_API_KEY = 24b74e9a-...）
- 现有 e2e specs

## 产出预期
- `plugin-bootstrap-real-call.spec.ts` 文件，包含 plan Task 7 描述的 3 个测试场景 × 2 viewport
- 全部 PASS（除非 exa server 实际不可用 — 那是 fail，记录到遗留问题）
- screenshot/trace artifact 保存到 `e2e/test-results/plugin-bootstrap/` 失败时供 review
- 完成后更新本 handoff 状态: `READY_FOR_QA` → `DONE`

## 决策上下文
- DEC-005: exa 是 HTTP Streamable transport，protocolVersion=2025-03-26
- W3 已加 brave/tavily 到 _BUILTIN_MCP_SERVERS（env_var gate）；W6 已加 exa 到 _BUILTIN_MCP_SERVERS（HTTP，env_var=EXA_API_KEY）
- W6 已在 executor `__main__.py` Step 3d 之后插了 plugin bootstrap 段（HTTP fetch → PluginHost.load_plugin → assembler.update_tools）
- W5 已实现 MCPClient HTTP 分支
- backend lifespan 启动期会调 `register_builtin_servers()` → 读 EXA_API_KEY → 加密 headers → upsert mcp_servers 行
- backend lifespan 启动期会调 `bootstrap_default_marketplace()` → 注册 anthropics/claude-plugins-official
- 用户 .env 已有 `EXA_API_KEY=24b74e9a-d7e5-4621-b10d-46e7ea44bb65`
- 测试 baseURL: http://localhost:8080
- prompt 用：「请搜索：今天 AI 行业有什么重要新闻？给我 3 条带链接。」
- 断言关键点：
  1. SSE 流中出现 tool_use `data-tool-name^="mcp__exa__"`
  2. tool_result 渲染含 `https?://` URL
  3. 助手最终消息**不是**「我无法搜索」类拒答，且**含 URL**
- e2e 真实验证哲学（CLAUDE.md D 硬规则）：搜罗失败而非确认成功；UX 要看（不能只 UI 通过）；网络请求 / DB 写入 / UI 更新都要断言
- 工作树路径: `E:\Agent program\PrismV3\.worktrees\plugin-bootstrap`

## 已完成
- 读 handoff + plan Task 7 完整 spec 模板
- 审查现有前端 (Prism.html / admin.html) 确认所有 selector 真实存在：
  - 登录：`input[type="email"]`, `input[type="password"]`, `button.btn.primary`
  - 新对话：`button.btn.primary:has-text("新对话")`
  - 消息区：`.agent-msg`, `.caret`（streaming 完成标志）
  - 工具卡：`.tool-card .name`（文本判断 mcp__exa__ 前缀），`.tool-body pre.tool-code`（输出）
  - Admin MCP Servers：`.rail-item .lbl:has-text("MCP Servers")` → `table.table tbody tr`（exa 行）
  - 修正 plan 模板中错误 selector（data-tool-name/data-role/data-testid="message-complete" 均不存在）
- 创建 `e2e/tests/plugin-bootstrap-real-call.spec.ts` 
  - 6 tests（3 scenarios × 2 projects: desktop-chromium + mobile-safari）
  - `npx playwright test --list` 确认全部 6 tests 正确枚举
  - Test 1: admin sees exa in MCP Servers table (transport=http, url含mcp.exa.ai)
  - Test 2: user sends AI news prompt → assert .tool-card with mcp__exa__ name + tool output contains https:// URL + final message not a refusal
  - Test 3: skip (requires backend restart with bad key)
- Docker daemon 无法连接（Docker Desktop 未启动），跳过 docker compose + Playwright 执行

## 产出物
- `e2e/tests/plugin-bootstrap-real-call.spec.ts`：6 tests，Playwright 可解析（--list 验证通过）

## 遗留问题
1. **Docker daemon 不可用**：`docker ps` 报 "failed to connect to the docker API ... dockerDesktopLinuxEngine"。需用户本机启动 Docker Desktop 后执行：
   ```
   cd "E:\Agent program\PrismV3\.worktrees\plugin-bootstrap"
   docker compose -p prismv3-bootstrap up -d --build --force-recreate backend executor
   # 等 backend healthy：curl http://localhost:8080/health/ready
   # 验证 exa 已注册：
   docker exec prismv3-bootstrap-postgres-1 psql -U prism -d prism -c "select name, transport, url from mcp_servers where name='exa';"
   # 跑 e2e：
   cd e2e && BASE_URL=http://localhost:8080 npx playwright test plugin-bootstrap-real-call.spec.ts --reporter=list
   ```
2. **Test 2 超时**：`test.setTimeout(120_000)` 已在 spec 内设置（覆盖 config 的 30s），无需改动 playwright.config.ts。LLM+exa round-trip 预计 30-90s，120s 足够。
3. **admin.html login gate**：admin.html 未内嵌登录表单，通过 sessionStorage token 鉴权；spec 先 goto `/` 登录再 goto `/admin.html` 路径正确，但若 token 过期（30min）需重新登录。
4. **Test 2 使用 admin 账号执行聊天**：handoff prompt 提到 `user@prism.dev`，但 e2e fixtures 没有建立该账号；spec 复用 `admin@prism.dev` 作为聊天用户，admin 同样可以发起 session，功能等价。如需真正用户账号，请 main agent 在 DB seed 中添加 user@prism.dev 后调整 spec。
