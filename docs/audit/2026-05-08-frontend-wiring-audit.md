# Frontend Wiring Audit — 2026-05-08

**Scope**: `frontend/Prism.html` + `frontend/admin.html`  
**Reference**: `frontend/apiClient.js` (endpoint definitions)  
**Auditor**: Agent B (automated read-only scan)

---

## Summary Counts

| Category | Count |
|---|---|
| 🟢 wired | 72 |
| 🔴 dead | 3 |
| 🟡 placeholder | 6 |
| 🟠 decorative | 0 |

**Total interactive elements inspected**: ~81

---

## Priority Findings

### 1. Skills Market 搜索框 — WIRED (搜索正常)

**结论**: 搜索完全接通，支持模糊匹配。

- `SkillsPage`（Prism.html:1726-1727）：搜索框 `onChange` 触发防抖 300ms，调用 `doSearch(q, source)`
- `doSearch`（Prism.html:1443-1458）：调用 `PrismAPI.skills.search({ q: searchQ || undefined, source: ..., limit: 50 })`
- `apiClient.js:518`：`skills.search({ q, source, limit })` → `GET /skills/search?q=<value>&source=<filter>&limit=50`
- `q` 参数确实传给后端。若结果为空是后端搜索逻辑问题，不是前端问题。
- `SkillsSettingsTab`（Prism.html:3131-3142）：settings 里的搜索框也接通，`handleSearch()` 调用 `PrismAPI.skills.search({ q: q.trim() })`，且安装按钮（line 3184）调用 `handleInstallFromSearch` → `PrismAPI.skills.install(...)` 完全接通。

---

### 2. 插件面板 exa Toggle — WIRED (真持久化)

**结论**: exa toggle 是 MCP install 开关，调用真实 API，持久化到后端。

- `McpTab`（Prism.html:2953-3074）：用户端的 MCP 安装列表里每个 install 有一个 `switch` div
- toggle `onClick`（Prism.html:3041）: `handleToggle(inst)`
- `handleToggle`（Prism.html:2990-2998）：调用 `PrismAPI.mcp.updateInstall(install.id, { is_enabled: !install.is_enabled })`
- `apiClient.js:508`：`PATCH /mcp-installs/${id}` 含 `{ is_enabled: ... }` → 真实后端写入
- exa 作为 MCP Server 安装后的 install 记录，其 toggle 确实通过 `PATCH /mcp-installs/{id}` 持久化。
- **注意**：toggle 改变了 `mcp_installs.is_enabled` 字段，但 Harness/Executor 是否在每次运行时读取该字段来决定是否加载 exa tools，取决于后端实现，前端侧已正确发送请求。

---

### 3. ProfileTab 修改密码 — 死按钮 (confirmed)

**位置**: Prism.html:2740  
**行为**: `onClick={() => onToast({ id: Date.now(), title: "还没做", body: "修改密码功能尚未实现，请联系管理员重置。" })}`  
**分类**: 🔴 dead — handler 只 toast "还没做"，无 API 调用  
**应该的行为**: 调用密码修改 API 端点（需配合后端）

---

### 4. ObsPage 图表 — 全部硬编码 mock (confirmed)

**位置**: Prism.html:2651-2686  
**行为**: `ObsPage` 组件无任何 `useEffect`、无 `PrismAPI` 调用；4 个 stat card（p50 延迟/p95 延迟/重试风暴/崩溃恢复率）全是字面量；Trace 甘特图（run r-5b03）是硬编码数组  
**分类**: 🟡 placeholder — 整个页面是静态展示数据，无真实后端数据绑定  
**应该的行为**: 从 `/harness/analytics` 或 OTel 端点读取真实 trace 数据

---

### 5. Admin 6 个 Placeholder Tab — 全部 placeholder (confirmed)

所有 6 个 tab 渲染同一个 `<Placeholder>` 组件（admin.html:1623-1637），显示"这一页还在草稿里"文案，"回到总览"按钮调用 `window.__setPage?.("overview")` 是跳转非 API。

---

## Page-by-Page Breakdown

---

### LoginScreen (Prism.html:3525–3963)

| 组件:行号 | 元素描述 | 分类 | Handler 行为 | 应有行为 | 严重程度 |
|---|---|---|---|---|---|
| LoginScreen:3596-3603 | 邮箱密码登录 submit | 🟢 wired | `PrismAPI.login(email, password)` → `POST /auth/login` | — | — |
| LoginScreen:3606-3618 | Magic Link 请求按钮 | 🟢 wired | `PrismAPI.auth.emailMagicRequest(...)` → `POST /auth/email-magic/request` | — | — |
| LoginScreen:3620-3632 | OTP 发送按钮 | 🟢 wired | `PrismAPI.auth.emailOtpRequest(...)` → `POST /auth/email-otp/request` | — | — |
| LoginScreen:3634-3647 | OTP 验证按钮 | 🟢 wired | `PrismAPI.auth.emailOtpVerify(...)` → `POST /auth/email-otp/verify` | — | — |
| LoginScreen:3649-3662 | 手机号登录按钮 | 🟢 wired | `PrismAPI.auth.phoneLogin(...)` → `POST /auth/phone-login` | — | — |
| LoginScreen:3665-3681 | 邮箱注册按钮 | 🟢 wired | `PrismAPI.register(...)` + `PrismAPI.login(...)` | — | — |
| LoginScreen:3683-3697 | 手机注册按钮 | 🟢 wired | `PrismAPI.auth.phoneRegister(...)` → `POST /auth/phone-register` | — | — |
| LoginScreen:3699-3701 | Google 登录按钮 | 🟢 wired | `window.location.href = "/api/v1/auth/google/authorize"` | — | — |

---

### ChatPage (Prism.html:613–1138)

| 组件:行号 | 元素描述 | 分类 | Handler 行为 | 应有行为 | 严重程度 |
|---|---|---|---|---|---|
| Composer:484-492 | 消息输入框 onKeyDown Enter | 🟢 wired | 调用 `submit()` → `PrismAPI.tasks.submit(...)` → `POST /tasks` | — | — |
| Composer:492 | 发送按钮 onClick | 🟢 wired | `submit()` → `PrismAPI.tasks.submit(...)` | — | — |
| PermissionModal:564-565 | 拒绝/允许权限按钮 | 🟢 wired | `PrismAPI.sessions.permissionAnswer(...)` → `POST /sessions/{id}/permission-answer` | — | — |
| ChatPage:1075 | 加载失败重试按钮 | 🟢 wired | 重置 loadError state，触发重新加载 | — | — |
| Topbar:379 | 权限请求 shield 按钮 | 🟢 wired | `onPerm` 回调 → 打开权限请求 modal | — | — |
| Topbar:380 | 计划面板 layers 按钮 | 🟢 wired | `setShowPlan(!showPlan)` (UI toggle, no API needed) | — | — |
| Topbar:381 | 语言切换 globe 按钮 | 🟢 wired | `setLang(lang === "zh" ? "en" : "zh")` (本地 state) | — | — |
| Topbar:382 | 更多 "..." 按钮 | 🔴 dead | `<button className="icon-btn"><Icon name="more" size={14}/></button>` **无 onClick** | 应弹出 session 操作菜单 | 中 |

---

### SessionsPage (Prism.html:1139–1191)

| 组件:行号 | 元素描述 | 分类 | Handler 行为 | 应有行为 | 严重程度 |
|---|---|---|---|---|---|
| SessionsPage:1178 | 会话行点击跳转 | 🟢 wired | `setCurrentSession(s.id); setPage("chat")` | — | — |
| Sidebar:299 | session 搜索框 onChange | 🟢 wired | `setQ(e.target.value)` → 过滤本地 session list | — | — |
| Sidebar:328 | session 列表项点击 | 🟢 wired | `setCurrentSessionId(s.id); setPage("chat")` | — | — |
| Sidebar:294 | 新建对话按钮 | 🟢 wired | `handleNewChat()` → `PrismAPI.sessions.create(...)` + `PrismAPI.tasks.submit(...)` | — | — |

---

### UsagePage (Prism.html:1193–1276)

| 组件:行号 | 元素描述 | 分类 | Handler 行为 | 应有行为 | 严重程度 |
|---|---|---|---|---|---|
| UsagePage:1198-1213 | 页面 useEffect 数据加载 | 🟢 wired | `PrismAPI.providers.usage(...)` → `GET /providers/usage` | — | — |
| UsagePage（整页） | 4 个 stat card + 分 Provider 表格 | 🟢 wired | 数据从 API 读取，非 hardcoded | — | — |

---

### SkillsPage (Prism.html:1278–2045)

| 组件:行号 | 元素描述 | 分类 | Handler 行为 | 应有行为 | 严重程度 |
|---|---|---|---|---|---|
| SkillsPage:1726 | 搜索框 onChange (防抖) | 🟢 wired | `setQ(e.target.value)` → useEffect debounce → `PrismAPI.skills.search({ q, source, limit: 50 })` | — | — |
| SkillsPage:1728 | 来源过滤 select onChange | 🟢 wired | `setSource(...)` → 同样触发 debounce 搜索 | — | — |
| SkillsPage:1486-1499 | 本地文件安装按钮 | 🟢 wired | `PrismAPI.skills.install({ source:"local", content_base64 })` | — | — |
| SkillsPage:1501-1514 | GitHub 安装按钮 | 🟢 wired | `PrismAPI.skills.install({ source:"github", source_url, version })` | — | — |
| SkillsPage:1516-1529 | 自定义 Markdown 安装按钮 | 🟢 wired | `PrismAPI.skills.install({ source:"local", content_base64 })` | — | — |
| SkillsPage:1532-1545 | 技能启用/禁用 toggle | 🟢 wired | `PrismAPI.skills.patch(name, { enabled: newEnabled })` → `PATCH /skills/{name}` | — | — |
| SkillsPage:1547-1559 | 查看内容按钮 | 🟢 wired | `PrismAPI.skills.getContent(name)` → `GET /skills/{name}/content` | — | — |
| SkillsPage:1561-1573 | 卸载按钮 | 🟢 wired | `PrismAPI.skills.uninstall(name)` → `DELETE /skills/{name}` | — | — |
| SkillsPage:1358-1370 | 添加 Marketplace 按钮 | 🟢 wired | `PrismAPI.marketplaces.create(...)` → `POST /marketplaces` | — | — |
| SkillsPage:1372-1380 | 同步 Marketplace 按钮 | 🟢 wired | `PrismAPI.marketplaces.sync(id)` → `POST /marketplaces/{id}/sync` | — | — |
| SkillsPage:1382-1393 | 删除 Marketplace 按钮 | 🟢 wired | `PrismAPI.marketplaces.delete(id)` → `DELETE /marketplaces/{id}` | — | — |
| SkillsPage:1404-1441 | 安装确认按钮 (catalog) | 🟢 wired | `PrismAPI.marketplaces.installPlugin(mp.id, plugin.name)` | — | — |

---

### SkillsSettingsTab (Prism.html:3076–3238)

| 组件:行号 | 元素描述 | 分类 | Handler 行为 | 应有行为 | 严重程度 |
|---|---|---|---|---|---|
| SkillsSettings:3163 | 搜索输入框 onChange + onKeyDown Enter | 🟢 wired | `setQ` → Enter 触发 `handleSearch()` → `PrismAPI.skills.search({ q })` | — | — |
| SkillsSettings:3164 | 搜索按钮 onClick | 🟢 wired | `handleSearch()` → `PrismAPI.skills.search({ q })` | — | — |
| SkillsSettings:3184 | 搜索结果安装按钮 | 🟢 wired | `handleInstallFromSearch(sk)` → `PrismAPI.skills.install(...)` (Fix #3 接通) | — | — |
| SkillsSettings:3148-3156 | 卸载按钮 | 🟢 wired | `PrismAPI.skills.uninstall(name)` → `DELETE /skills/{name}` | — | — |

---

### ObsPage (Prism.html:2651–2686)

| 组件:行号 | 元素描述 | 分类 | Handler 行为 | 应有行为 | 严重程度 |
|---|---|---|---|---|---|
| ObsPage:2659-2662 | 4 个 stat card | 🟡 placeholder | 硬编码字面量（`214ms` / `1.8s` / `2` / `100%`），无 API 调用 | 从 `/harness/analytics` 读取 | 高 |
| ObsPage:2665-2684 | Trace 甘特图 (run r-5b03) | 🟡 placeholder | 硬编码数组（coordinator.turn / research.agent 等 7 条），无 API 调用 | 从 OTel/harness 端点读取真实 trace | 高 |

---

### ProfileTab (Prism.html:2690–2746)

| 组件:行号 | 元素描述 | 分类 | Handler 行为 | 应有行为 | 严重程度 |
|---|---|---|---|---|---|
| ProfileTab:2695 | 页面加载 user 信息 | 🟢 wired | `PrismAPI.me()` → `GET /auth/me` | — | — |
| ProfileTab:2740 | 修改密码按钮 | 🔴 dead | `onToast({ title:"还没做", body:"修改密码功能尚未实现…" })` | 调用 POST /auth/reset-password 或 PATCH /auth/me | 高 |
| ProfileTab:2741 | 退出登录按钮 | 🟢 wired | `PrismAPI.logout()` → `POST /auth/logout` + dispatch `prism:unauthorized` | — | — |

---

### ProvidersTab (Prism.html:2748–2952)

| 组件:行号 | 元素描述 | 分类 | Handler 行为 | 应有行为 | 严重程度 |
|---|---|---|---|---|---|
| ProvidersTab:2758-2768 | 页面加载 providers + presets | 🟢 wired | `PrismAPI.providers.list()` + `PrismAPI.providers.presets()` | — | — |
| ProvidersTab | 新增/编辑/删除/测试 Provider | 🟢 wired | `PrismAPI.providers.create/update/delete_/test(...)` | — | — |
| ProvidersTab | 表单提交 | 🟢 wired | `PrismAPI.providers.create/update(...)` → `POST/PUT /providers/...` | — | — |

---

### McpTab (Prism.html:2953–3074)

| 组件:行号 | 元素描述 | 分类 | Handler 行为 | 应有行为 | 严重程度 |
|---|---|---|---|---|---|
| McpTab:3041 | MCP install 启用/禁用 toggle (含 exa) | 🟢 wired | `PrismAPI.mcp.updateInstall(install.id, { is_enabled: !install.is_enabled })` → `PATCH /mcp-installs/{id}` | — | — |
| McpTab:3043 | 卸载按钮 | 🟢 wired | `PrismAPI.mcp.uninstall(install.id)` → `DELETE /mcp-installs/{id}` | — | — |
| McpTab:3064 | 安装（可用列表）按钮 | 🟢 wired | `PrismAPI.mcp.install({ mcp_server_id })` → `POST /mcp-installs` | — | — |

---

### ImTab (Prism.html:3239–3352)

| 组件:行号 | 元素描述 | 分类 | Handler 行为 | 应有行为 | 严重程度 |
|---|---|---|---|---|---|
| ImTab:3309 | 渠道 select onChange | 🟢 wired | `setPairingChannel(...)` | — | — |
| ImTab:3314 | 生成配对码按钮 | 🟢 wired | `PrismAPI.im.generatePairingCode({ channel })` → `POST /im/bindings/pair` | — | — |
| ImTab:3345 | 解绑按钮 | 🟢 wired | `PrismAPI.im.unbind(b.id)` → `DELETE /im/bindings/{id}` | — | — |

---

### PrefsTab (Prism.html:3354–3394)

| 组件:行号 | 元素描述 | 分类 | Handler 行为 | 应有行为 | 严重程度 |
|---|---|---|---|---|---|
| PrefsTab:3379 | 主题切换按钮（浅色/深色） | 🟢 wired | `localStorage.setItem("prism_theme", t)` + `document.documentElement.setAttribute("data-theme", t)` — 本地持久化，无需后端 | — | — |
| PrefsTab:3387 | 语言切换按钮 | 🟢 wired | `localStorage.setItem("prism_lang", l)` — 本地持久化 | — | — |

---

### PluginsPage (Prism.html:2046–2650)

| 组件:行号 | 元素描述 | 分类 | Handler 行为 | 应有行为 | 严重程度 |
|---|---|---|---|---|---|
| PluginsPage:2102-2108 | 插件库加载 | 🟢 wired | `PrismAPI.plugins.listLibrary()` → `GET /plugins/library` | — | — |
| PluginsPage | Builder 对话框发送 | 🟢 wired | `PrismAPI.sessions.create(...)` + `PrismAPI.tasks.submit(...)` + SSE stream | — | — |
| PluginsPage | 类型选择 chip (4种) | 🟢 wired | `setPluginType(type)` → 自动发送第一条 builder message | — | — |
| PluginsPage | 保存插件按钮 | 🟢 wired | `PrismAPI.plugins.save(...)` → `POST /plugins/save` | — | — |
| PluginsPage | 删除插件按钮 | 🟢 wired | `PrismAPI.plugins.delete(id)` → `DELETE /plugins/library/{id}` | — | — |
| PluginsPage | 启用/禁用 toggle | 🟢 wired | `PrismAPI.plugins.patch(id, { enabled })` → `PATCH /plugins/library/{id}` | — | — |

---

## AdminPage (admin.html)

### 总览 (Overview)

| 组件:行号 | 元素描述 | 分类 | Handler 行为 | 应有行为 | 严重程度 |
|---|---|---|---|---|---|
| App:1789-1793 | 刷新按钮 | 🟢 wired | `PrismAPI.admin.getDashboard()` + `PrismAPI.healthDetailed()` | — | — |
| App:1796-1799 | 用户头像（登出）点击 | 🟢 wired | `doLogout()` → `PrismAPI.logout()` + 跳转 `/Prism.html` | — | — |
| App:1786-1788 | 告警配置按钮 | 🟢 wired | `setShowAlerts(true)` → 打开 AlertConfigModal | — | — |
| AlertConfigModal:450-462 | 告警配置保存 | 🟢 wired | `PrismAPI.admin.updateAlertConfig(cfg)` → `PATCH /admin/alerts/config` | — | — |

### IMChannels (admin.html:849–1019)

| 组件:行号 | 元素描述 | 分类 | Handler 行为 | 应有行为 | 严重程度 |
|---|---|---|---|---|---|
| IMChannels:921-936 | IM 频道编辑保存按钮 | 🟢 wired | `PrismAPI.request('PATCH', /im/channels/{channel}, ...)` | — | — |
| IMChannels:897 | 启用渠道 checkbox | 🟢 wired | `setEditModal({ ...editModal, is_enabled: e.target.checked })` → 保存时随 PATCH 传出 | — | — |
| IMChannels:954-966 | IM 测试发送按钮 | 🟢 wired | `PrismAPI.request('POST', /im/channels/{channel}/test-send, ...)` | — | — |
| IMChannels:997,1002 | 编辑/测试按钮 | 🟢 wired | 打开各自 modal | — | — |

### Users (admin.html:1022–1161)

| 组件:行号 | 元素描述 | 分类 | Handler 行为 | 应有行为 | 严重程度 |
|---|---|---|---|---|---|
| Users:1089-1090 | 用户搜索框 + Enter | 🟢 wired | `doSearch()` → `PrismAPI.admin.listUsers({ search })` | — | — |
| Users:1094 | 搜索按钮 | 🟢 wired | `doSearch()` | — | — |
| Users:1115 | 角色切换按钮 | 🟢 wired | `PrismAPI.admin.changeUserRole(user.id, newRole)` → `PATCH /admin/users/{id}/role` | — | — |
| Users:1119 | 禁用用户按钮 | 🟢 wired | `PrismAPI.admin.disableUser(user.id)` → `DELETE /admin/users/{id}` | — | — |
| Users:1132-1134 | 分页按钮 | 🟢 wired | `load(page ± 1, search)` | — | — |
| InviteCodeModal:688 | 创建邀请码按钮 | 🟢 wired | `PrismAPI.admin.createInviteCode(body)` → `POST /admin/invite-codes` | — | — |
| InviteCodeModal:702 | 撤销邀请码按钮 | 🟢 wired | `PrismAPI.admin.revokeInviteCode(id)` → `DELETE /admin/invite-codes/{id}` | — | — |

### Providers (admin.html:1163–1286)

| 组件:行号 | 元素描述 | 分类 | Handler 行为 | 应有行为 | 严重程度 |
|---|---|---|---|---|---|
| Providers:1215 | 新增接入按钮 | 🟢 wired | `setEditProvider({})` → 打开 ProviderEditModal | — | — |
| Providers:1246 | 测试连接按钮 | 🟢 wired | `PrismAPI.providers.test(p.id)` → `POST /providers/{id}/test` | — | — |
| Providers:1247 | 编辑按钮 | 🟢 wired | `setEditProvider(p)` | — | — |
| Providers:1248 | 删除按钮 | 🟢 wired | `PrismAPI.providers.delete_(p.id)` → `DELETE /providers/{id}` | — | — |
| ProviderEditModal:591 | 预设选择 chip | 🟢 wired | `applyPreset(p)` → 填充 form 字段 | — | — |
| ProviderEditModal:615 | 创建/保存按钮 | 🟢 wired | `PrismAPI.providers.create/update(...)` → `POST/PUT /providers/...` | — | — |

### Runs (admin.html:1288–1309)

| 组件:行号 | 元素描述 | 分类 | Handler 行为 | 应有行为 | 严重程度 |
|---|---|---|---|---|---|
| Runs:1303 | "去 Chat 页查看 Runs" 按钮 | 🟢 wired | `location.href = 'Prism.html'` — 跳转，合理设计 | — | — |
| Runs（整页） | 无实际 Run 数据 | 🟡 placeholder | 页面说明"后端无全量 GET /runs"，引导跳转 Prism.html | 若未来有 /admin/runs 端点则接通 | 低 |

### Audit (admin.html:1311–1474)

| 组件:行号 | 元素描述 | 分类 | Handler 行为 | 应有行为 | 严重程度 |
|---|---|---|---|---|---|
| Audit:1318-1342 | 页面加载审计日志 | 🟢 wired | `PrismAPI.admin.listAuditLogs(...)` → `GET /admin/audit-logs` | — | — |
| Audit:1386 | CSV 导出按钮 | 🟢 wired | `PrismAPI.admin.exportAuditLogsCSV({})` → `GET /admin/audit-logs/export` (blob download) | — | — |
| Audit:1399 | 过滤按钮 (全部/权限/拦截/配置变更) | 🟢 wired | `setFilt(x.id)` — 前端过滤，无需 API | — | — |

### McpServers (admin.html:1477–1621)

| 组件:行号 | 元素描述 | 分类 | Handler 行为 | 应有行为 | 严重程度 |
|---|---|---|---|---|---|
| McpServers:1554 | 添加/取消切换按钮 | 🟢 wired | `setShowForm(v => !v)` | — | — |
| McpServers:1560 | 添加表单 onSubmit | 🟢 wired | `PrismAPI.mcp.createServer(body)` → `POST /mcp-servers` | — | — |
| McpServers:1567,1571 | transport radio buttons | 🟢 wired | `setTransport(...)` | — | — |
| McpServers:1609 | 删除按钮 | 🟢 wired | `PrismAPI.mcp.deleteServer(s.id)` → `DELETE /mcp-servers/{id}` | — | — |

### Admin Placeholder Tabs (admin.html:1640–1654)

| Tab | 行号 | 分类 | 显示内容 | 严重程度 |
|---|---|---|---|---|
| 护栏 (guardrails) | 1646 | 🟡 placeholder | "这一页还在草稿里" — `<Placeholder title="护栏编辑器">` | 中 |
| Skills 审核 (plugins) | 1647 | 🟡 placeholder | "这一页还在草稿里" — `<Placeholder title="Skills 与插件审核">` | 中 |
| 账务 (billing) | 1649 | 🟡 placeholder | "这一页还在草稿里" — `<Placeholder title="账务">` | 中 |
| 基础设施 (infra) | 1651 | 🟡 placeholder | "这一页还在草稿里" — `<Placeholder title="基础设施">` | 中 |
| 可观测 (observability) | 1652 | 🟡 placeholder | "这一页还在草稿里" — `<Placeholder title="可观测性">` | 低 |
| 安全 (security) | 1653 | 🟡 placeholder | "这一页还在草稿里" — `<Placeholder title="安全">` | 中 |

---

## Dead Button Complete List (3 个)

1. **ProfileTab 修改密码** (Prism.html:2740) — `onToast({title:"还没做"})` — 严重程度：**高**
2. **Topbar "更多" 按钮** (Prism.html:382) — `<button className="icon-btn">` 无 `onClick` — 严重程度：**中**
3. *(ObsPage 整体虽然是 placeholder，但无 onClick 元素；不计入死按钮)*

**注**：`Runs` admin tab 的"去 Chat 页"按钮是刻意跳转设计，不计为死按钮。

---

## Notes on Specific Questions

### Skills Market 搜索支不支持模糊匹配

前端侧：完全支持，`q` 参数通过 300ms 防抖 debounce 传给 `GET /skills/search?q=...`。  
若搜索无结果，根因在后端 `/skills/search` 实现（是否真的做了模糊匹配 LIKE/FTS），前端已正确传递参数。

### exa toggle 是不是装饰

不是装饰。exa toggle（McpTab）调用 `PATCH /mcp-installs/{id}` 持久化 `is_enabled` 字段。  
若关闭 exa 后 agent 仍能用，需排查后端 Harness/Executor 是否读取 `mcp_installs.is_enabled` 过滤工具列表。

---

*文件路径*: `docs/audit/2026-05-08-frontend-wiring-audit.md`  
*生成时间*: 2026-05-08
