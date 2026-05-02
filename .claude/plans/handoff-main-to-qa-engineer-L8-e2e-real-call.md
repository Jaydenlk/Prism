# Handoff: main → qa-engineer (Task 7 / W7 / L8)

## 状态: PENDING_BATCH_2_COMPLETE

> **Pre-condition**: Batch 2 (Tasks 5 + 6) 全部 commit 后才能开工。

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
（qa-engineer 完成后填）

## 产出物
（qa-engineer 完成后填）

## 遗留问题
（如有，写这里 — 特别是真实 exa 调用是否成功 / 哪些 selector 与现有前端不匹配）
