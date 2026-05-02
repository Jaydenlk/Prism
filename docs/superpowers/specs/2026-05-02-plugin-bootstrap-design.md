# Plugin Bootstrap — Skills + MCP 真实运行复活

> **日期**: 2026-05-02
> **作者**: Claude Opus 4.7 + 用户
> **状态**: design — 待实施
> **关联**:
> - `2026-05-02-mcp-http-transport-exa.md`（HTTP transport 子 spec，由 sonnet 调研生成）
> - `../../research/2026-05-02-search-mcp-alternatives.md`（搜索 MCP 备选调研）
> **分支**: `feat/plugin-bootstrap`
> **预计工作量**: 1-2 session（高强度并发 sonnet）

---

## 1. Source of Truth（一手文档清单）

| 主题 | URL / 来源 | 用于 |
|---|---|---|
| MCP Streamable HTTP transport spec | https://modelcontextprotocol.io/specification/2025-03-26/basic/transports | L5b MCPClient HTTP 分支实现 |
| exa MCP server 文档 | https://docs.exa.ai/reference/mcp + curl 探测 `https://mcp.exa.ai/mcp` | exa builtin entry 配置 + 验证协议版本 |
| Brave Search MCP | `@modelcontextprotocol/server-brave-search` (npm) + https://brave.com/search/api/ | L7 Brave stdio builtin |
| Tavily MCP | `tavily-mcp` (npm) + https://docs.tavily.com/docs/mcp | L7 Tavily stdio builtin |
| 用户 Claude Code exa 配置 | `~/.claude.json` `mcpServers.exa` 字段 | L6 exa builtin 1:1 复制 |
| Prism CALLBACK_SECRET 设计 | `PRD_V4/DOC-CC-ONBOARDING.md` "进程边界" §2 + ADR-050 | L1 internal endpoint 鉴权 |
| Prism AES-256-GCM 加密 | `backend/app/services/security_service.py`（`encrypt_value`/`decrypt_value`）| headers_encrypted 字段加密 |

**探测确认（curl + Bearer 24b74e9a-d7e5-4621-b10d-46e7ea44bb65）**:
- exa endpoint 返回 `protocolVersion: 2025-03-26` ✓
- `Content-Type: text/event-stream` ✓
- `Mcp-Session-Id` 头部存在 ✓
- ServerInfo: `mcp-typescript server on vercel` ✓
- Capabilities: tools / prompts / completions / resources（all listChanged）

**Uncertainty**：
- exa 是否需要每次调 tool 都发 `initialize`？还是首次握手后凭 Mcp-Session-Id 复用 session？— 推断**首次握手后复用**（按 spec 默认行为），实施时验证。

---

## 2. 问题与根因

**Phase 1 systematic-debugging 调查结论（已落 DECISIONS）**：

`executor/__main__.py` Step 3d (line 492-509) **从未实例化 PluginHost / SkillLoader**。代码完整性 OK（SkillLoader 84-232 行 / PluginHost 215-550 行 / MCPClient.start 双通道握手），但缺一个调用入口。

三个用户投诉同根：
| 症状 | 实际原因 |
|---|---|
| Skills 装了不生效 | SkillLoader 从未 new，PromptAssembler `skills` 参数永远是 None |
| MCP 注册了 agent 看不见 tool | PluginHost 不存在 → MCPClient.start() 永不调用 → ToolRegistry 零 MCP 工具 → `update_tools()` 永不触发 |
| 搜索是摆设 | 数据源（marketplace_registry catalog_json）默认空，没有任何启动期预注册 |

---

## 3. 数据流（修复后）

```
[Frontend admin/Prism UI]
   ↓ register/install
[Backend FastAPI + Postgres]
   ├ mcp_servers (+transport/url/headers_encrypted [NEW])
   ├ user_mcp_installs
   ├ skill_installs (+filesystem .prism/skills/)
   └ marketplace_registry (NEW: 启动期 bootstrap 自动注册)
   ↓ POST /tasks → ProcessManager.start_run --user-id X
[Executor 子进程]
   └ __main__.py Step 3d [NEW BOOTSTRAP]
      ├ HTTP GET /internal/users/{uid}/installed-skills (CALLBACK_SECRET) [L1]
      ├ HTTP GET /internal/users/{uid}/mcp-servers (CALLBACK_SECRET, headers 解密后返) [L1]
      ├ instantiate SkillLoader → 过滤后 inject 到 prompt
      ├ instantiate PluginHost → load_plugin() per server
      │   ├ stdio 分支 (现有)
      │   └ HTTP 分支 [NEW L5b]: POST + SSE + Mcp-Session-Id
      ├ MCPToolWrapper → ToolRegistry
      └ assembler.update_tools() + skill_grammar_section
   ↓
[QueryEngine.run] agent 真看到 mcp__exa__* / skill 指令
```

---

## 4. 改动清单（11 处文件）

### Backend（8 处）

| # | 文件 | 改动 |
|---|---|---|
| 1 | `backend/app/api/v1/internal.py` | 新增 2 endpoints：`GET /internal/users/{uid}/installed-skills` + `GET /internal/users/{uid}/mcp-servers`，CALLBACK_SECRET 验证（x-callback-secret header），HTTP server 返回时解密 headers |
| 2 | `backend/app/models/mcp_server.py` | 新增字段 `transport: str` (default 'stdio') + `url: str \| None` + `headers_encrypted: str \| None` |
| 3 | `backend/app/schemas/mcp.py` | 字段同步 + validators（transport=http 必有 url；transport=stdio 必有 command；Authorization 在 Response 中 mask 为 `***`） |
| 4 | `backend/alembic/versions/008_mcp_http_transport.py` | migration 加 3 字段，现有行 `transport='stdio'`，新字段 NULL，KEEP `command` NOT NULL（HTTP 行写占位 `__http__`，避免破坏约束） |
| 5 | `backend/app/services/mcp_service.py` | `_BUILTIN_MCP_SERVERS` 加 exa(http)/brave(stdio)/tavily(stdio) 3 条；env var 缺失则 skip 注册（graceful）；`test_server()` 真实现：调 MCPClient transient + list_tools，10s 超时 |
| 6 | `backend/app/services/marketplace_service.py` | 启动期空表自动注册 `anthropics/claude-plugins-official`（一次性，admin 可删） |
| 7 | `backend/app/main.py` | lifespan 启动期调用 marketplace bootstrap |
| 8 | `backend/Dockerfile` | `apt-get install -y nodejs npm`（Brave/Tavily stdio 用 npx） |

### Executor（3 处）

| # | 文件 | 改动 |
|---|---|---|
| 9 | `executor/__main__.py` Step 3d | 新增 bootstrap 段：HTTP fetch L1 endpoints → 实例化 PluginHost + SkillLoader → load_plugin per server → SkillLoader.load_skills(filtered_by_user) → assembler.update_tools()；失败 graceful（log warn + 继续，不崩 run） |
| 10 | `executor/plugins/mcp_client.py` | 加 `HttpStreamableTransport` 分支：POST + Accept text/event-stream + JSON-RPC over SSE 解析 + `Mcp-Session-Id` 持久化 + 重连（410/网络错误）；保留现有 stdio 分支 |
| 11 | `executor/plugins/host.py` | `_start_mcp_server()` 按 `server.transport` 字段 dispatch 到 stdio / http 分支 |

### Frontend（1 处）

| # | 文件 | 改动 |
|---|---|---|
| 12 | `frontend/admin.html` MCP servers tab | 加 transport radio (stdio \| http) + 条件显示 url/headers JSON editor；headers Authorization 显示时 mask 为 `Bearer ***` |

> **Frontend Prism.html**: 不改。搜索流程已在 fix#3+ 接通；marketplace 自动 bootstrap 后空状态消失。

---

## 5. Secret 存储设计

### 5.1 字段：`headers_encrypted: str | None`

- headers dict 整体 `json.dumps()` → `security_service.encrypt_value(plaintext, key=ENCRYPTION_KEY)` → 存 TEXT
- 现有 AES-256-GCM 实现（`backend/app/services/security_service.py`），nonce 自动生成嵌入密文
- 解密：`security_service.decrypt_value(ciphertext)` → JSON parse 还原 dict

### 5.2 Builtin entries 用 env var 模板

builtin 条目 headers 用 `${env:VAR_NAME}` 占位：
```python
{
    "name": "exa",
    "transport": "http",
    "url": "https://mcp.exa.ai/mcp",
    "headers_template": {
        "Authorization": "Bearer ${env:EXA_API_KEY}",
        "Content-Type": "application/json"
    },
    "scope": "system",
}
```

`register_builtin_servers()`:
1. 读 builtin 条目
2. 解析 `${env:X}` → os.environ.get('X')
3. **若 env var 未设 → 跳过该 builtin 注册**（log info，不报错）
4. 否则替换占位 → encrypt headers JSON → upsert mcp_servers 行

### 5.3 解密发生位置（关键）

- **Backend service 层解密**：在 L1 internal endpoint 响应前，service 层调 decrypt → 返明文 headers JSON
- **Executor 不持 ENCRYPTION_KEY**：进程边界 = 信任边界硬底线（CLAUDE.md §六原则 #5/#6 + ADR-050）
- HTTP 通道：本机 / Docker compose 内网，未来 mTLS 或 unix socket 可加固

---

## 6. exa 配置 1:1 复制（用户 .claude.json → Prism builtin）

源（用户 `~/.claude.json` `mcpServers.exa`）：
```json
{
  "type": "http",
  "url": "https://mcp.exa.ai/mcp",
  "headers": {
    "Authorization": "Bearer 24b74e9a-d7e5-4621-b10d-46e7ea44bb65",
    "Content-Type": "application/json"
  }
}
```

目标（Prism `_BUILTIN_MCP_SERVERS`）：
```python
{
    "name": "exa",
    "description": "Exa AI 搜索（神经网络驱动语义搜索 + URL 内容提取）",
    "transport": "http",
    "url": "https://mcp.exa.ai/mcp",
    "headers_template": {
        "Authorization": "Bearer ${env:EXA_API_KEY}",
        "Content-Type": "application/json"
    },
    "scope": "system",
}
```

用户在 Prism `.env` 设 `EXA_API_KEY=24b74e9a-d7e5-4621-b10d-46e7ea44bb65`（不进 git，已 .gitignore）。

---

## 7. 默认 Marketplace 自动注册

- FastAPI `app.startup` lifespan 钩点：
  ```python
  if not db.execute(select(MarketplaceRegistry)).first():
      await marketplace_service.create({
          "name": "anthropics/claude-plugins-official",
          "url": "https://github.com/anthropics/claude-plugins-official",
          "is_default": True,
      })
  ```
- 一次性；admin 可后续 delete
- 让搜索从空状态变可用 — 用户搜 "github"/"todo" 立即出结果

---

## 8. 测试策略

### 8.1 Backend Unit
- `tests/test_mcp_schema_validators.py`: transport=http 缺 url → ValidationError；transport=stdio 缺 command → ValidationError
- `tests/test_mcp_test_server.py`: stdio mock subprocess → success；http mock httpx server → success；超时 → 503
- `tests/test_marketplace_bootstrap.py`: 空表 → 注册 default；非空 → 跳过
- `tests/test_internal_endpoints.py`: 无 CALLBACK_SECRET → 401；正确 secret + 不存在 user → 404；正确 secret + user 有 server → 200 含 plaintext headers

### 8.2 Executor Unit
- `tests/test_plugin_host_dispatch.py`: stdio path / http path 都能 load_plugin（mock transport）
- `tests/test_mcp_client_http.py`: SSE 解析正确 / Mcp-Session-Id 持久化 / 重连逻辑 / list_tools 解码
- `tests/test_skill_loader_user_filter.py`: 给定 user installed list → 只返回交集

### 8.3 e2e Playwright（qa-engineer 真驱动浏览器）

**桌面 1280×720 + 移动 390×844 双端**：
1. 起 docker compose 全栈
2. /admin.html 登录 admin → MCP servers tab → 看到 exa 已自动注册（builtin from .env） + brave/tavily 列表中（若 .env 提供 key）
3. /Prism.html 用户登录 → 安装 exa（如需）→ 起新会话
4. 输入：`今天 AI 行业有什么新闻？给我 3 条`
5. **断言**：
   - SSE 流中出现 `tool_use` block，`name=mcp__exa__web_search_exa`
   - tool_result 包含真实 URL 列表（`https://`）
   - 助手最终消息包含具体新闻条目（非"我不能上网"类拒答）
6. 负例：把 `EXA_API_KEY` 改错 → 重启 backend → admin tab 显示 server inactive；用户问搜索类问题 → agent 回退本地能力（不崩）

---

## 9. 并行实施分批（高强度 sonnet）

### Batch 1（4 worker 全独立，并发）
| Worker | Tasks | 文件范围 |
|---|---|---|
| W1 | T#1 L1 | `backend/app/api/v1/internal.py` (new) |
| W2 | T#3 L3 | `backend/app/services/mcp_service.py` test_server() 部分 + `backend/app/api/v1/mcp.py` test endpoint 部分 |
| W3 | T#4 L4 + T#8 L7 | `backend/app/services/marketplace_service.py` + `backend/app/main.py` lifespan + `backend/app/services/mcp_service.py` `_BUILTIN_MCP_SERVERS` 加 brave/tavily |
| W4 | T#5 L5a | `backend/app/models/mcp_server.py` + `backend/app/schemas/mcp.py` + `backend/alembic/versions/008_*.py` |

### Batch 2（依赖 Batch 1，2 worker 并发）
| Worker | Tasks | 文件范围 |
|---|---|---|
| W5 | T#6 L5b | `executor/plugins/mcp_client.py` HTTP 分支 + `executor/plugins/host.py` dispatch |
| W6 | T#2 L2 + T#7 L6 | `executor/__main__.py` Step 3d bootstrap + `backend/app/services/mcp_service.py` `_BUILTIN_MCP_SERVERS` 加 exa（merge W3 后） |

### Batch 3（依赖 Batch 2 完成）
| Worker | Tasks | 文件范围 |
|---|---|---|
| W7 (qa-engineer) | T#9 L8 | `e2e/tests/plugin-bootstrap-real-call.spec.ts` 双端 |

每个 worker 强制 TDD：失败 tests 先写 → 实现 → Part B 验证全 PASS。

---

## 10. 风险与 Open Questions

| ID | 内容 | 缓解 |
|---|---|---|
| R1 | exa Vercel 不稳 / 429 limit | HTTP branch 优雅 5xx 重试 + 用户友好错误 |
| R2 | nginx SSE 流式被代理缓冲 | `proxy_buffering off` + chunked off（Task 12.3 已配） |
| R3 | 用户没 BRAVE/TAVILY key | builtin 跳过注册（graceful），管理员后填 .env restart 生效 |
| R4 | nodejs 装到 Docker 增加镜像体积 | 接受，~80MB 增量 |
| OQ-1 | Streamable HTTP 是否每次 tool 调用都重 initialize？ | 推断"首次握手后凭 Mcp-Session-Id 复用"；实施时 logging 验证 |
| OQ-2 | HTTP transport 重连时旧 session-id 是否仍有效？ | 旧 session 可能被服务端 GC；实施时 catch 410 → 重 initialize |

---

## 11. Out of Scope（这 PR 不做）

- HTTP MCP 旧版 SSE-only transport（2024-11-05 spec）— 只支持 Streamable HTTP 2025-03-26
- WebSocket transport — 不在 MCP spec 内
- Plugin signing / 私有 registry governance — 单独 PR
- Plugin marketplace 用户级 catalog（vs 系统级）— 单独 PR
- 跨进程 `${secret.X}` 解密（host.py:162 的 stub）— 本 PR 仅用 env var 路径，secret 字段集成单独 PR

---

## 12. 验收标准（Iron Law）

10 项质量门必须全 PASS：
1. ✅ Backend unit + executor unit 全 PASS（无 skip）
2. ✅ e2e Playwright 双端真实调用真返回结果（不是 mock）
3. ✅ Simplify subagent 3 路并发审过（reuse / quality / efficiency）
4. ✅ project-review:pjr lint/build/逻辑/工作区干净
5. ✅ code-reviewer subagent 找错独立审过
6. ✅ git status clean，commit 链有意义
7. ✅ DECISIONS / PROGRESS / HANDOFF-LOG 同步更新
8. ✅ 用户真实账号在浏览器一遍走通（admin → user → 搜索 → 真结果）
9. ✅ 无 mock / no stub / no TODO 残留
10. ✅ 文档置信度：每个 builtin 配置都基于 WebFetch 一手文档

---

## 附：Self-Review

- [x] Placeholder 扫描：无 TBD/TODO 残留
- [x] 内部一致：架构 / 改动清单 / 测试覆盖一一对应
- [x] Scope 检查：单一目标（Plugin bootstrap），可在 1-2 session 完成
- [x] 歧义检查：headers_encrypted 整体 vs 字段级 → 已锁整体；解密位置 backend vs executor → 已锁 backend
