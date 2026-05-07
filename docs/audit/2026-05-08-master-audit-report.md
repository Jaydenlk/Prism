# PRD vs Reality 全审计 — Master Report (2026-05-08)

**审计范围**: PRD_V4 12 个 DOC + 86 个 backend endpoints + 81+ 个 frontend 交互元素 + 2 个用户报告 bug 复现
**审计模式**: 3 sonnet subagent 并行（PRD inventory / frontend wiring / backend endpoint）+ 主 agent 浏览器 + DB 复现
**结论**: 4 个 P0（用户已踩） + 5 个 P1（潜在死路） + 11 个 P2（边角缺口）

---

## P0（用户已直接踩到 / 阻塞核心流程）

### P0-1. Skills Market 搜索全空（用户硬投诉）
- **现象**: 搜任何 query 都返 `{"data": [], "error": null}`，输入框形同虚设
- **根因（3 层）**:
  1. `marketplace_registry` 表 40 行全部是 e2e 测试残留（`e2e-badge-*` / `e2e-mkt-*`），catalog_json.plugins[] 全空
  2. `MarketplaceService.bootstrap_default_marketplace` 仅检查 `if any rows → skip` → e2e 残留存在 → 默认 anthropic 仓库**从未注册**
  3. 即便注册也需 `sync()` 拉真实 catalog
- **影响**: 用户进 SkillsSettingsTab / SkillsPage 完全看不到任何 skill
- **验证**: 前端 search box → `PrismAPI.skills.search({q})` → `GET /skills/search?q=...` → `q` 真传到 backend；后端 `MarketplaceCatalogSource._marketplace_entry_matches` 真做大小写无关 substring 匹配 — **链路通，但桶里没水**

### P0-2. exa toggle 关闭后仍生效（用户硬投诉）
- **现象**: 用户在"我的 MCP"页 toggle off exa → DB `user_mcp_installs.is_enabled=false` → agent 起会话仍调 `mcp__exa__web_search_exa`
- **根因**: `backend/app/api/v1/internal.py` `get_user_mcp_servers` 系统级查询**完全忽略** `user_mcp_installs.is_enabled`：
  ```python
  system_rows = db.query(McpServer).filter(scope=="system", user_id.is_(None)).all()
  ```
- **影响**: 所有系统级 MCP（exa/searxng/web_search/filesystem/tavily）的用户 toggle 全部装饰化；用户付费 token 在不想用时被消耗
- **修复要点**: LEFT JOIN user_mcp_installs，排除 `(user_id == X AND is_enabled == false)` 的 server_id

### P0-3. ObsPage 整页静态 mock（高严重）
- **现象**: 4 张统计卡片（p50/p95/重试风暴/崩溃恢复率）+ 7 条 trace 全部硬编码（Prism.html line 2651-2686）
- **关联 bug**: `GET /harness/analytics` 端点 frontend 发 `window=7d`（字符串），backend 接 `days: int` — **每次都 422**
- **影响**: ObsPage 即使想真接也接不通；用户看到的"数据"完全骗人
- **修复**: (a) frontend `analytics.{ window: '7d' }` → `{ days: 7 }` (b) Prism.html ObsPage 所有 hardcoded 数组 → real API

### P0-4. ProfileTab 修改密码死按钮（之前 known issue）
- **现象**: Prism.html line 2740 — 按钮 onClick = `onToast({ title: "还没做" })` 纯 toast
- **后端实际**: `POST /auth/change-password` **真存在** (Audit C 验证) — 但前端没 wire
- **修复**: ~30 min — 加 modal + 调 PrismAPI.auth.changePassword

---

## P1（潜在死路 / 用户走到会发现）

### P1-1. `GET /admin/usage` 参数被无视（param-ignored）
- frontend 发 `group_by` / `start_date` / `end_date`，后端 handler **零** query 参数声明 → 永远返"过去 30 天"硬编码窗口
- 影响：admin 切日期 / 改 group → UI 显示不变

### P1-2. `GET /providers/{id}` 端点缺失
- apiClient.js `providers.get(id)` 调 `GET /providers/{id}`，后端 `providers.py` **无对应路由** → 404/405
- 影响：详情页 / 编辑表单可能挂

### P1-3. `GET /admin/audit-logs` 参数名错配
- frontend 发 `start_date` / `end_date`，后端接 `start_time` / `end_time` → 日期过滤静默丢失
- 影响：admin 按日期查日志返回全量

### P1-4. Topbar "更多" 按钮死按钮
- Prism.html line 382，纯装饰

### P1-5. e2e 测试污染 dev DB（间接根因）
- e2e specs 直接操作生产 docker compose 的 postgres → 留下 40 行 marketplace 残留 + 多用户 / session 残留
- 修复：e2e 用独立 docker compose project（如 `prismv3-e2e`）+ 测前 reset

---

## P2（占位/边角，PRD 设计但未实施）

| # | 项 | 现状 |
|---|---|---|
| P2-1 | admin 护栏 tab | `<Placeholder/>` |
| P2-2 | admin Skills 审核 tab | `<Placeholder/>` |
| P2-3 | admin 账务 tab | `<Placeholder/>` |
| P2-4 | admin 基础设施 tab | `<Placeholder/>` |
| P2-5 | admin 可观测 tab | `<Placeholder/>`（部分依赖 P0-3 修完） |
| P2-6 | admin 安全 tab | `<Placeholder/>` |
| P2-7 | UsageTab（Prism.html 用户端用量页） | 在 NAV 但未实现 |
| P2-8 | DOC-10/11 Next.js 前端正式化 | 整套未做（当前用 Prism.html 原型） |
| P2-9 | Multi-channel auth Task C（前端 LoginScreen 多通道 + admin Auth Config） | pending |
| P2-10 | Block 2 IM 三小尾（Slack Socket Mode / 卡片回传 / sensitive key 单一源） | pending |
| P2-11 | Block 3 分布式任务拆解 | pending（spec 阶段都没做） |

---

## 数据完整性 / 卫生 — 必处理

- 40 行 marketplace_registry e2e 残留（应删，纯垃圾）
- 历史 sessions 中可能有重复 tool_use 行（pre-existing 持久化 bug，已记录在 plugin-bootstrap PR scratchpad）
- 部分 mcp_servers 系统级行可能因 builtin 重命名 / 删除而孤立（如先前的 brave-search）

---

## 推荐修复顺序（auto mode 立即可执行的部分）

**Phase 1 — 立刻干（≤4 hours，单一 PR `fix/audit-p0-p1`）**：
1. P0-2: 修 internal.py `get_user_mcp_servers` 让 system MCP 也尊重 user toggle
2. P0-1: 修 marketplace bootstrap 按 name 而非 count 检查 + 注册后立即 sync
3. P0-1: 一次性 SQL 清 40 行 e2e 残留
4. P0-3 partial: 修 frontend `analytics({ window: '7d' })` → `{ days: 7 }`
5. P0-4: ProfileTab 修改密码 wire
6. P1-1, P1-3: 修 admin/usage + audit-logs 参数错配
7. P1-2: 加 GET /providers/{id} 路由
8. e2e 测试加单元测试覆盖以上修复
9. 双端 Playwright 真实复现验证

**Phase 2 — 中期**:
- P0-3 full: ObsPage 全替换为真 API 数据 + 加新的 GET endpoints（如果 PRD 设计但还没写）
- e2e DB 隔离

**Phase 3 — 长期**:
- 6 个 admin placeholder tab
- Block 2 / Block 3
- DOC-10/11 Next.js 重写

---

## 输出文档

- `docs/audit/2026-05-08-prd-feature-inventory.md` — 87 条 PRD 用户可见功能
- `docs/audit/2026-05-08-frontend-wiring-audit.md` — 81 个交互元素分类
- `docs/audit/2026-05-08-backend-endpoint-audit.md` — 86 个 endpoint 状态
- `docs/audit/2026-05-08-reproduction-findings.md` — 用户报告 2 例根因复现
- `docs/audit/2026-05-08-master-audit-report.md` — 本文（聚合）
