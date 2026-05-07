# 用户报告 2 例根因复现（2026-05-08）

## Bug A — Skills Market 搜索全空 / 不支持模糊

### 复现
```
TOKEN=$(login admin@prism.dev)
curl /api/v1/skills/search?q=github → {"data": [], "error": null}
curl /api/v1/skills/search?q=plugin → {"data": [], "error": null}
curl /api/v1/skills/search?q=     → {"data": [], "error": null}
```

### 根因链（3 层）
1. `marketplace_registry` 表有 40 行 e2e 测试残留（`e2e-badge-*`、`e2e-mkt-*`），catalog_json.plugins 全空
2. `MarketplaceService.bootstrap_default_marketplace` 仅在 `total == 0` 时注册默认 → 残留行存在 → **从未注册** anthropic 默认仓库
3. `MarketplaceCatalogSource.search` 遍历所有 marketplace 的 catalog_json.plugins[] 做 substring 匹配 → 全 0 plugin → 任何 query 返 `[]`

### 影响
- 用户进 SkillsSettingsTab 搜索 → 永远空 + 看不到任何 skill
- "模糊搜索不支持" 是次因 — 主因是**根本没数据**

### 修复路径
- bootstrap_default_marketplace 改为按 name 精确检查（只判 anthropic 默认是否存在）
- 启动期或注册后立即触发 sync() 从 GitHub 拉真实 catalog
- 清理 40 行 e2e 残留（一次性 SQL）
- e2e 测试用独立的 docker compose project 而非污染 dev DB

---

## Bug B — exa toggle 是装饰 / 关闭后仍生效

### 复现
- 用户进 Prism.html "我的 MCP" 页（PluginsPage 类似，line 2960+）
- 看见 exa（系统级 + 已 install 的 UserMcpInstall 行）
- 点 toggle 关闭 → API: `PATCH /mcp-installs/{id} {is_enabled: false}`
- DB 更新 ✓
- 起新会话提问"搜新闻" → agent 仍调 `mcp__exa__web_search_exa` ✗

### 根因
`backend/app/api/v1/internal.py` `get_user_mcp_servers`:
```python
system_rows = (
    db.query(McpServer)
    .filter(McpServer.scope == "system", McpServer.user_id.is_(None))
    .all()
)
```

- 系统级 MCP 一律返回，**不读 user_mcp_installs.is_enabled**
- 用户的 toggle 仅影响 user_rows 那部分（user-scope MCPs），对 system-scope 完全无效

### 影响
- 所有系统级 MCP（exa / web_search / filesystem / searxng / tavily）都无法被用户关闭
- 用户付费的 token (exa) 在不想用时仍被消耗
- 隐私 / 数据 / 行为约束的 toggle 全部装饰化

### 修复路径
`get_user_mcp_servers` 改为：
```python
# system rows: include unless user has explicitly disabled via UserMcpInstall
disabled_system_ids = (
    db.query(UserMcpInstall.mcp_server_id)
    .filter(UserMcpInstall.user_id == user_id, UserMcpInstall.is_enabled.is_(False))
    .subquery()
)
system_rows = (
    db.query(McpServer)
    .filter(
        McpServer.scope == "system",
        McpServer.user_id.is_(None),
        McpServer.id.notin_(select(disabled_system_ids)),
    ).all()
)
```

加单元测试：disable system mcp + call internal endpoint → 应不在返回里。
加 e2e：UI 关 exa toggle + 搜索 prompt → agent 不调 mcp__exa__*。

---

## 共同结论

两 bug 都是**进程边界 / 数据流上的"半通"**：UI 真发请求 + DB 真更新，但下游消费方不读这个状态。这是隐蔽的"装饰"类 bug — 比纯死按钮更难发现，因为前端 API 调用看起来工作。

接下来 3 个审计 subagent (PRD inventory / frontend wiring / backend endpoint) 应能扫出更多类似模式。
