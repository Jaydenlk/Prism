# Spec: HTTP MCP Transport + Exa Integration

**Date**: 2026-05-02
**Scope**: mcp_servers 表扩展 + executor HTTP 分支 + exa 内置条目
**Status**: SPEC ONLY — 不含代码实现

---

## 1. Source of Truth

### 1.1 MCP Transport Specification

**Primary source**: `https://modelcontextprotocol.io/specification/2025-03-26/basic/transports`
(WebFetch 2026-05-02 — 完整内容已获取)

**Protocol version**: `2025-03-26`（替代旧 `2024-11-05` 的 HTTP+SSE transport）

**关键字段摘录**:

- Transport 名称: **Streamable HTTP**（非旧 HTTP+SSE，两者不同）
- MCP endpoint: 单一 URL，同时支持 POST（发送消息）和 GET（监听 SSE 推送）
- 握手流程:
  1. `POST <endpoint>` with `InitializeRequest`，`Accept: application/json, text/event-stream`
  2. Server 响应 `InitializeResult`（JSON），可选携带 `Mcp-Session-Id` header
  3. `POST <endpoint>` with `InitializedNotification`（无 id）→ 202 Accepted
  4. 后续每次 tool call = 新的 `POST <endpoint>` with `Mcp-Session-Id` header
- 响应模式: Server 可返回 `Content-Type: application/json`（单 JSON）或 `Content-Type: text/event-stream`（SSE 流）
- Client 必须同时支持两种响应模式
- 断连不等于取消；取消须显式发 `CancelledNotification`
- Session 终止: 客户端 `DELETE <endpoint>` with `Mcp-Session-Id`
- 旧 SSE transport 兼容: 若 POST InitializeRequest 返回 4xx，回退到 GET 等待 `endpoint` event

### 1.2 Exa MCP Server

**Primary sources**:
- `https://exa.ai/mcp` (WebFetch 2026-05-02)
- `https://github.com/exa-labs/exa-mcp-server` (WebFetch 2026-05-02)
- `https://mcp.exa.ai/` (401 — 需认证，无法直接 fetch)

**Endpoint**: `https://mcp.exa.ai/mcp`

**Transport 类型**: Streamable HTTP（基于 GitHub 源码及用户提供的 Claude Code 配置判断）

**认证**: `Authorization: Bearer <EXA_API_KEY>` header

**默认启用工具**（来自 GitHub README）:
- `web_search_exa` — 实时网页搜索，返回 clean content
- `web_fetch_exa` — 抓取指定 URL 全文

**可选工具（默认禁用）**:
- `web_search_advanced_exa` — 高级过滤（域名、日期等）
- `company_research_exa`、`linkedin_search_exa`、`crawling_exa`
- `deep_researcher_start`、`deep_researcher_check`（多步研究）

**UNCERTAINTY 标注**:

| 字段 | 置信度 | 来源 |
|---|---|---|
| Transport 类型 = Streamable HTTP | 中（GitHub 文档未明确说明，基于配置格式推断） | GitHub README + 用户 Claude Code 配置 |
| `Mcp-Session-Id` 是否返回 | 低（未能直接 fetch endpoint） | 无一手数据 |
| 工具列表完整性 | 中（来自 GitHub README，可能非最新） | GitHub |
| MCP 协议版本 (`2024-11-05` vs `2025-03-26`) | 低（endpoint 需握手才能获知） | 推断 |

**建议**: 实施前用以下命令探测实际协议版本:
```bash
curl -X POST https://mcp.exa.ai/mcp \
  -H "Authorization: Bearer <KEY>" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"prism","version":"2.0"}}}'
```

---

## 2. DB Migration（最小改动）

### 2.1 改动概述

`mcp_servers` 表现有 stdio-only 字段：`command` (String, NOT NULL)、`args` (JSONB)、`env` (JSONB)。

新增 3 个字段以支持 HTTP transport:

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `transport` | `VARCHAR(10)` | NOT NULL, default `'stdio'` | `'stdio'` \| `'http'` \| `'sse'`（sse 保留位，向后兼容旧协议） |
| `url` | `TEXT` | nullable | HTTP transport endpoint URL |
| `headers_encrypted` | `TEXT` | nullable | AES-256-GCM 加密的 JSON 字符串，存 `{"Authorization": "Bearer ..."}` 等 header |

注意：`command` 字段保持 `NOT NULL`（历史约束），但 HTTP transport 行在 `command` 写入占位字符串 `"__http__"`。Service 层按 `transport` 值路由，不依赖 `command` 是否有意义。

**现有 stdio 行兼容性**: 迁移不修改已有数据。`transport` 使用 `server_default='stdio'`，现有行自动填充；`url` / `headers_encrypted` 保持 NULL。`register_builtin_servers` 写入时只处理已知字段，新字段使用 DB default。

### 2.2 Migration 文件

**文件名**: `010_add_http_transport_to_mcp_servers.py`

**Revision chain**: `009` → `010`

```python
"""Add HTTP transport fields to mcp_servers

Revision ID: 010
Revises: 009
Create Date: 2026-05-02

Adds transport type discriminator + HTTP-specific fields to mcp_servers table.
Existing stdio rows get transport='stdio' via server_default (no data migration needed).
headers_encrypted stores AES-256-GCM envelope of JSON headers dict (Authorization etc.).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: str = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mcp_servers",
        sa.Column(
            "transport",
            sa.String(10),
            nullable=False,
            server_default="stdio",
        ),
    )
    op.add_column(
        "mcp_servers",
        sa.Column("url", sa.Text(), nullable=True),
    )
    op.add_column(
        "mcp_servers",
        sa.Column("headers_encrypted", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_mcp_servers_transport",
        "mcp_servers",
        ["transport"],
    )


def downgrade() -> None:
    op.drop_index("ix_mcp_servers_transport", table_name="mcp_servers")
    op.drop_column("mcp_servers", "headers_encrypted")
    op.drop_column("mcp_servers", "url")
    op.drop_column("mcp_servers", "transport")
```

### 2.3 为什么不用 `JSONB` 存 `headers`

`headers` 是敏感数据（含 Bearer token），整体加密为 TEXT envelope（`<nonce_hex>:<ciphertext_hex>`）。若存 JSONB，字段结构对 DB 管理员可见；TEXT 加密列不暴露结构。详见 §4。

---

## 3. Pydantic Schema 改动

### 3.1 `CreateMCPServerRequest`

现有字段: `name`, `description`, `command` (required), `args`, `env`

新增字段:
```python
transport: Literal["stdio", "http", "sse"] = "stdio"
url: str | None = None
headers: dict[str, str] | None = None  # 明文入参，Service 层加密后存 headers_encrypted
```

**验证规则** (Pydantic `@model_validator`):
- `transport == "http"` 或 `"sse"` → `url` 必须存在且非空；`command` 可为空字符串（置为 `"__http__"`）
- `transport == "stdio"` → `command` 必须非空（保持原有逻辑）
- `url` 非空时必须以 `https://` 或 `http://` 开头

### 3.2 `MCPServerResponse`

新增字段（只读）:
```python
transport: str                    # 'stdio' | 'http' | 'sse'
url: str | None                   # HTTP endpoint URL，明文返回
headers_masked: dict[str, str] | None  # Authorization 等 header 键存在但值 masked 为 '***'
```

**Masking 规则**: `headers_encrypted` 解密后，所有 key 保留，value 统一替换为 `"***"`。不返回明文 token。

### 3.3 `MCPServerResponse` model_config

现有: `model_config = {"from_attributes": True}`  
不变，但 `headers_masked` 需要在 `_to_server_response()` 静态方法中手动填充（不能直接 from ORM attr）。

### 3.4 `UpdateMCPServerRequest`（需新增，当前无此 schema）

UNCERTAINTY: 当前 API 没有 PATCH /mcp-servers/{id}。若要支持 HTTP server 后续更新 Bearer token，需新增此 endpoint。本 spec 不包含，记为 Open Question。

---

## 4. Secret 加密

### 4.1 现有加密机制

`backend/app/core/security.py` 已实现：
- `encrypt_value(plaintext: str, key_hex: str) -> str`：AES-256-GCM，envelope 格式 `<nonce_hex>:<ciphertext_hex>`
- `decrypt_value(envelope: str, key_hex: str) -> str`：反向操作
- Key 来源：`settings.ENCRYPTION_KEY`（启动时由 `validate_secrets()` 校验，≥32 chars，与 JWT_SECRET / CALLBACK_SECRET 独立）

### 4.2 存储策略：整体加密 headers JSON

**推荐方案**: 将 `headers` dict 序列化为 JSON 字符串，整体用 `encrypt_value()` 加密，存入 `headers_encrypted TEXT` 列。

```
headers_encrypted = encrypt_value(
    json.dumps({"Authorization": "Bearer sk-xxx", "Content-Type": "application/json"}),
    settings.ENCRYPTION_KEY
)
# 存储结果形如: "a3f1b2c4...:<hex-ciphertext>"
```

**Why 整体加密而非单独 token 字段**:
- headers dict 的 key 名本身也可能泄露信息（如自定义认证方案的 header 名）
- 整体加密 = 单一字段、单一解密路径，KISS 原则
- 与 `env` 字段的处理形成对比：`env` 以 JSONB 存明文并在响应层 mask；headers 由于更高安全需求（直接是 token）选择静态加密

**不选"单独 token 字段"的理由**: 不同 HTTP MCP server 可能有不同 auth header（`X-Api-Key`、`Authorization`、自定义），强制统一为一个 `token` 字段限制了扩展性。

### 4.3 Decrypt 位置：Backend Service 层（非 Executor）

**进程边界 = 信任边界** (CLAUDE.md 六原则 §6)。

Executor 是独立子进程，不 import `backend.app.*`。Secret 不能直接传给 Executor——需通过有界通道传递。

**推荐流程**:
1. Backend `MCPService.get_server_for_executor(server_id, user_id)` 解密 `headers_encrypted`，返回明文 `headers` dict
2. Backend 通过 **executor 启动参数**（JSON-encoded env var 或 HTTP CALLBACK）将解密后的 headers 注入 executor 启动上下文
3. Executor 只持有当前 session 所需的明文 headers，不持有 ENCRYPTION_KEY

UNCERTAINTY: 具体注入通道（env var vs Redis vs 启动时 HTTP POST to executor）取决于 executor 启动协议（DOC-05），需与 DOC-05 Task 5.x 对齐。本 spec 不决策此细节。

---

## 5. MCPClient HTTP 分支（executor side）

### 5.1 当前 stdio 实现概览

`executor/plugins/mcp_client.py` `MCPClient`:
- `__init__(server_name, command, args, env, scope)` — stdio 参数
- `start()` — `asyncio.create_subprocess_exec` + JSON-RPC initialize + tools/list
- `call_tool(tool_name, arguments)` — `tools/call` via stdio
- `_send_request()` / `_send_notification()` — JSON-RPC 2.0 over stdin/stdout

### 5.2 HTTP 分支设计原则

**不用 MCP Python SDK**（`mcp` 包）的理由：
- `mcp` 包未在 `backend/requirements.txt` 中，executor 依赖应保持最小
- `httpx>=0.27.0` 已在项目 requirements 中，直接使用即可
- Streamable HTTP 协议足够简单（POST → JSON/SSE），不需要 SDK 抽象层

**使用 `httpx.AsyncClient`**，单一 client 实例复用（keep-alive）。

### 5.3 HTTP MCPClient 构造函数扩展

```python
# 新增可选参数，stdio 路径完全不变
class MCPClient:
    def __init__(
        self,
        server_name: str,
        command: str,
        args: list[str],
        env: dict[str, str],
        scope: str = SCOPE_USER,
        # --- HTTP transport 新增 ---
        transport: str = "stdio",          # "stdio" | "http"
        url: str | None = None,            # HTTP endpoint
        http_headers: dict[str, str] | None = None,  # 解密后的明文 headers
    ) -> None:
        ...
        self._transport = transport
        self._url = url
        self._http_headers = http_headers or {}
        self._session_id: str | None = None   # Mcp-Session-Id（HTTP 握手后填充）
        self._http_client: httpx.AsyncClient | None = None
```

### 5.4 HTTP 分支伪代码

```python
async def start(self) -> None:
    if self._transport == "stdio":
        # 原有 stdio 路径，不变
        ...
        return

    # --- HTTP 分支 ---
    import httpx
    self._http_client = httpx.AsyncClient(
        headers=self._http_headers,
        timeout=30.0,
    )

    # Step 1: Initialize
    init_result = await self._http_request(
        "initialize",
        {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "prism", "version": "2.0"},
        },
    )
    # 保存 Session ID（若 server 返回）
    # self._session_id 由 _http_request 在 response header 中读取

    self._instructions = init_result.get("instructions", "")

    # Step 2: notifications/initialized（notification = 无 id）
    await self._http_notify("notifications/initialized", {})

    # Step 3: tools/list
    tools_result = await self._http_request("tools/list", {})
    self._tools = tools_result.get("tools", [])


async def _http_request(self, method: str, params: dict) -> dict:
    """HTTP transport JSON-RPC request。
    
    POST to self._url, Accept: application/json, text/event-stream
    Handles both application/json and text/event-stream response.
    """
    assert self._http_client is not None
    self._request_id += 1
    body = {
        "jsonrpc": "2.0",
        "id": self._request_id,
        "method": method,
        "params": params,
    }
    req_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if self._session_id:
        req_headers["Mcp-Session-Id"] = self._session_id

    response = await self._http_client.post(
        self._url,
        json=body,
        headers=req_headers,
    )
    response.raise_for_status()

    # 读取 Mcp-Session-Id（initialize 响应时写入）
    if session_id := response.headers.get("mcp-session-id"):
        self._session_id = session_id

    content_type = response.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        return await self._parse_sse_response(response)
    else:
        data = response.json()
        if "error" in data:
            raise RuntimeError(f"MCP HTTP Error from {self._server_name}: {data['error']}")
        return data.get("result", {})


async def _parse_sse_response(self, response: httpx.Response) -> dict:
    """从 SSE 流中提取 JSON-RPC response（等待对应 id 的 result）。
    
    按行读取 text/event-stream，找到含 result 或 error 的 data: 行。
    """
    result: dict = {}
    async for line in response.aiter_lines():
        if line.startswith("data:"):
            data_str = line[5:].strip()
            if not data_str:
                continue
            msg = json.loads(data_str)
            if "result" in msg and msg.get("id") == self._request_id:
                result = msg["result"]
                break
            if "error" in msg and msg.get("id") == self._request_id:
                raise RuntimeError(
                    f"MCP SSE Error from {self._server_name}: {msg['error']}"
                )
    return result


async def _http_notify(self, method: str, params: dict) -> None:
    """HTTP transport notification（无 id，期望 202 Accepted）。"""
    assert self._http_client is not None
    body = {"jsonrpc": "2.0", "method": method, "params": params}
    req_headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if self._session_id:
        req_headers["Mcp-Session-Id"] = self._session_id
    response = await self._http_client.post(self._url, json=body, headers=req_headers)
    # 202 Accepted expected; raise if server returns error
    if response.status_code not in (200, 202):
        response.raise_for_status()


async def stop(self) -> None:
    if self._transport == "http" and self._http_client and self._session_id:
        # 显式终止 session
        try:
            await self._http_client.delete(
                self._url,
                headers={"Mcp-Session-Id": self._session_id},
            )
        except Exception:
            pass
        await self._http_client.aclose()
        self._http_client = None
    elif self._transport == "stdio":
        # 原有 stdio 关闭路径，不变
        ...
```

### 5.5 心跳 / 重连策略

**exa 的 stateless 特性**（基于推断，UNCERTAINTY 中等）：
- exa HTTP MCP 可能是无状态模式（每次 tool call 独立），不维持 persistent SSE stream
- 若 `Mcp-Session-Id` 缺失（server 未返回），则每次 `call_tool()` 都相当于重新握手
- 不需要心跳；连接断开时 `_http_client` 自动重建

**有状态 session 的断连处理**（如 server 返回 404 on session expired）:
- 捕获 `httpx.HTTPStatusError(status_code=404)`
- 重置 `self._session_id = None`
- 重新调用 `start()` 完成新握手
- 最多重试 1 次（超出则 raise RuntimeError，由 PluginHost 记录错误）

### 5.6 PluginHost._start_mcp_server 扩展

`host.py` 中 `_start_mcp_server()` 需接受 `transport` / `url` / `http_headers` 三个新参数并传给 `MCPClient.__init__`。Plugin yaml 的 `mcp_servers` 列表 dict 中可包含这些键，变量替换系统已支持 dict 递归展开。

---

## 6. `_BUILTIN_MCP_SERVERS` 加 exa 条目

### 6.1 exa 条目字面量

```python
_BUILTIN_MCP_SERVERS: list[dict] = [
    # --- 现有 stdio 条目 ---
    {
        "name": "web_search",
        "description": "网页搜索 — Anthropic MCP Web Search",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@anthropic/mcp-web-search"],
        "env": {},
    },
    {
        "name": "filesystem",
        "description": "文件系统访问 — 读写本地文件",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"],
        "env": {},
    },
    # --- 新增 HTTP transport ---
    {
        "name": "exa",
        "description": "Exa AI 网页搜索 + 内容抓取 (HTTP MCP)",
        "transport": "http",
        "command": "__http__",          # 占位，HTTP transport 不启动子进程
        "args": [],
        "env": {},
        "url": "https://mcp.exa.ai/mcp",
        "headers_encrypted": None,     # 由 admin 通过 register_builtin_servers 扩展或 .env EXA_API_KEY 注入
    },
]
```

### 6.2 EXA_API_KEY 注入策略

**阶段 1（最简实现）**: `register_builtin_servers()` 启动时读取 `os.environ.get("EXA_API_KEY")`，若存在则调用 `encrypt_value()` 写入 DB。伪代码：

```python
# 在 register_builtin_servers() 中，处理 transport='http' 条目时:
exa_api_key = os.environ.get("EXA_API_KEY", "")
if exa_api_key:
    headers_plain = {"Authorization": f"Bearer {exa_api_key}"}
    spec["headers_encrypted"] = encrypt_value(
        json.dumps(headers_plain),
        settings.ENCRYPTION_KEY,
    )
```

**阶段 2（user-scope 支持）**: 用户自行创建 `transport='http'` server，在 `CreateMCPServerRequest.headers` 中传入 Bearer token，`create_server()` 调用 `encrypt_value()` 后存 DB。此路径复用阶段 1 的加密逻辑。

UNCERTAINTY: Claude Code 用户配置中 token 是 hardcode（`24b74e9a-...`）。Prism 中是否允许 system-scope server 存用户级别的 token？建议 exa 保持 `scope='system'`，token 由 `.env EXA_API_KEY` 配置，而不是绑定到某个用户。

---

## 7. 风险 + Open Questions

### OQ-1: exa 实际 transport 类型（高风险）

- **问题**: exa `https://mcp.exa.ai/mcp` 是 Streamable HTTP（2025-03-26）还是旧 HTTP+SSE（2024-11-05）？
- **影响**: 若是旧 SSE transport，握手流程完全不同（GET 先建立 SSE 流，`endpoint` event 返回 POST URL）
- **验证方法**: 用上述 curl 命令探测（§1.2）
- **Fallback 方案**: MCPClient 实现向后兼容探测逻辑（先 POST，4xx 则改走 GET+SSE），见 MCP spec 向后兼容章节

### OQ-2: Bearer token 暴露风险

- **日志风险**: `httpx` 默认不记录 request headers，但若 `structlog` 记录了 `self._http_headers` dict 则会泄露 token
- **缓解**: `_start_mcp_server()` 传递 `http_headers` 时不做 structlog 日志；logger 日志中替换为 `{"Authorization": "***"}`
- **metrics 风险**: OpenTelemetry spans 的 HTTP 属性不应包含 Authorization header

### OQ-3: Stateless vs Persistent session

- **问题**: exa 是否每次 tool call 都需要重新握手？若是，`self._tools` 缓存（在 `start()` 中填充一次）还是否有效？
- **影响**: 若 stateless，tools list 在 `start()` 阶段就完成（exa tools 固定）；若有 session expiry，需实现重新握手
- **推断**: exa 作为托管服务，极可能是 stateless（无 Mcp-Session-Id），每次 POST 独立。这意味着 `stop()` 不需要发 DELETE，只需 `aclose()` httpx client

### OQ-4: `command` 字段 NOT NULL 约束

- **问题**: HTTP transport 行在 `command` 写入占位符 `"__http__"` 以满足 NOT NULL 约束
- **风险**: `PluginHost._start_mcp_server()` 中有 `if not command: return` 守卫，需确保 `"__http__"` 不触发此守卫
- **解决**: 守卫改为 `if transport == "stdio" and not command: return`；或将 `command` 改为 nullable（需额外 migration）
- **推荐**: 守卫改逻辑（不改 schema，minimal change）

### OQ-5: PATCH /mcp-servers/{id} 缺失

- 当前没有更新 server 配置的 endpoint（只有 create/delete）
- Bearer token 过期或更换时无法热更新，需重新 create server
- 超出本 spec 范围，记录为未来 task

### OQ-6: MCPClient.call_tool() 的 HTTP 路径下 `session_id` 管理

- `call_tool()` 是 `async def`，需确保 `_http_client` 已初始化（start() 已调用）
- exa stateless 场景下 `_session_id` 为 None，每次 call_tool 发 POST 不含 session header
- 此路径最简，不需要额外处理

---

## 8. 实施分工预估

### Backend 改动

| 文件 | 改动类型 | 估算 LOC |
|---|---|---|
| `backend/alembic/versions/010_add_http_transport_to_mcp_servers.py` | 新建 | ~50 LOC |
| `backend/app/models/mcp_server.py` | 新增 3 字段 (`transport`, `url`, `headers_encrypted`) | +10 LOC |
| `backend/app/schemas/mcp.py` | `CreateMCPServerRequest` 新字段 + validator；`MCPServerResponse` 新字段 | +40 LOC |
| `backend/app/services/mcp_service.py` | `create_server()` 加密逻辑；`_to_server_response()` mask headers；`register_builtin_servers()` exa 条目 + EXA_API_KEY 注入 | +60 LOC |

**Backend 总计**: 4 文件，约 +160 LOC（净增，不含删除）

### Executor 改动

| 文件 | 改动类型 | 估算 LOC |
|---|---|---|
| `executor/plugins/mcp_client.py` | `MCPClient.__init__()` 扩展参数；`start()` HTTP 分支；`stop()` HTTP 分支；`_http_request()`；`_parse_sse_response()`；`_http_notify()`；`call_tool()` transport 路由 | +120 LOC |
| `executor/plugins/host.py` | `_start_mcp_server()` 传递新参数 | +15 LOC |

**Executor 总计**: 2 文件，约 +135 LOC

### Tests

| 测试类型 | 数量 | 说明 |
|---|---|---|
| Unit — Schema validation | 3 | stdio/http/sse transport validator；http 无 url 422；stdio 无 command 422 |
| Unit — `encrypt_value` / `decrypt_value` round-trip | 1 | 已有，验证 headers_encrypted 路径 |
| Unit — `MCPClient` HTTP 分支 | 4 | `start()` mock httpx；`call_tool()` json response；`call_tool()` SSE response；`stop()` DELETE session |
| Unit — `register_builtin_servers` exa 注入 | 1 | EXA_API_KEY env var 存在/不存在两路径 |
| Integration — Backend MCP CRUD | 2 | POST /mcp-servers with transport=http；GET /mcp-servers response headers_masked |

**Tests 总计**: 约 11 个测试用例

### 总人时估算（Sonnet 工作量）

- Backend migration + model + schema: 1 session (~1.5h)
- Backend service 加密逻辑 + exa bootstrap: 1 session (~1.5h)
- Executor HTTP 分支实现: 1 session (~2h)
- Tests + E2E 验证: 1 session (~1.5h)

**总计**: 4 个 Sonnet session，~6.5 工时（不含 OQ-1 的 transport 类型确认等待时间）

---

## 附录：依赖确认

- `httpx>=0.27.0` — 已在 `backend/requirements.txt`，executor 独立 requirements 需确认同样包含（UNCERTAINTY: executor 的 requirements 未在本次 spec 读取范围内）
- `cryptography>=42.0.0` — 已在 `backend/requirements.txt`，`encrypt_value()` 使用 `AESGCM`
- MCP Python SDK (`mcp` 包) — 不引入，httpx 直接实现
