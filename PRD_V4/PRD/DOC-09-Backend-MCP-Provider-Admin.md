# Prism 棱镜 v2 — Backend MCP / Provider Config / Admin (DOC-09)

> **文档编号**: DOC-09  
> **版本**: 3.1  
> **日期**: 2026-04-02  
> **性质**: 实现文档 — MCP Server 管理、Provider 配置 UI 支撑、Admin 扩展功能  
> **前置依赖**: DOC-01 v3（Schema: mcp_servers + user_mcp_installs + providers）, DOC-02 v3 Task 2.3（ProviderManager 运行时逻辑）, DOC-06（认证体系 + Admin API 骨架）  
> **Phase**: 2（后端功能模块）  
> **Task 数**: 2  
> **审计关注点**:  
> - **Provider 管理的职责分界**：两个模块都涉及 Provider，但职责完全不同：  
>   - `backend/app/services/provider_service.py`（DOC-02 Task 2.3 + 本文档）= **配置层**：CRUD、预设列表、API Key 加密存储、连通性测试。运行在 Backend 进程中，服务于 Web UI 的 Provider 管理页面  
>   - `executor/adapters/provider_manager.py`（DOC-02 Task 2.3）= **运行时层**：Provider 选择、故障转移、熔断、用量记录。运行在 CLI 子进程中，服务于 Agent 执行  
>   - **两者不互相调用**。Backend ProviderService 写 DB → CLI 子进程启动时从 DB 读取 → ProviderManager 在运行时使用。ProviderManager 的熔断状态写 Redis，Backend 可读取 Redis 展示健康状态  
>   - 本文档补充 ProviderService 的 MCP 管理部分，不触碰 ProviderManager 的运行时逻辑

---

## 目录

1. [Task 9.1: MCP Server 管理](#task-91-mcp-server-管理)
2. [Task 9.2: Provider 配置补充与用量 API](#task-92-provider-配置补充与用量-api)
3. [Task 9.3: Admin 审计日志与系统管理](#task-93-admin-审计日志与系统管理)

---

## 职责分界图

```
Web UI (Provider 管理页面)
    │ CRUD 操作
    ▼
Backend ProviderService          ← 配置层（本文档 + DOC-02 Task 2.3 已有部分）
    │ 写 DB (providers 表)
    │ 加密 API Key (ENCRYPTION_KEY)
    │ 返回掩码 api_key_masked
    │
    │ 读 Redis (harness:circuit:*)
    │ 展示 Provider 健康状态
    │
    ▼ ─────── DB ────────────────────────────────────────────
    │
CLI 子进程启动时从 DB 读取 Provider 配置
    │
    ▼
Executor ProviderManager         ← 运行时层（DOC-02 Task 2.3 已完成）
    │ 选择 Provider
    │ 故障转移 / 熔断
    │ 写 Redis (harness:circuit:*)
    │ 记录用量 (runs 表)
```

---

## Task 9.1: MCP Server 管理

### Part A — 设计与解释

#### 问题陈述

用户需要管理 MCP Server 配置——系统内置的（如 Web Search）和用户自定义的。用户可以启用/禁用 MCP Server，覆盖配置参数。MCP Server 的工具在 Agent 执行时通过 PluginHost 加载到 ToolRegistry。

本 Task 只处理 MCP 的配置管理（DB CRUD），实际的 MCP 客户端连接和工具注册在 DOC-05 PluginHost 中实现。

> **数据隔离修复 (P1)**：`list_servers()`, `delete_server()`, `create_server()` 所有方法必须接受 `user_id` 参数并强制按 `user_id` 过滤，确保铁律 4（数据隔离）。

> **MCP API 层 (P0)**：Task 9.1 Part B 必须包含完整的 `app/api/v1/mcp.py` 路由文件实现指导，包括：
> - `POST /mcp-servers` — 创建 MCP Server 配置
> - `GET /mcp-servers` — 列出当前用户的 MCP Server
> - `DELETE /mcp-servers/{id}` — 删除 MCP Server
> - `POST /mcp-servers/{id}/test` — 测试 MCP Server 连通性
> - 所有端点强制 `user_id` 数据隔离

#### 验收标准

- 列出系统内置 + 用户自定义的 MCP Server
- 用户可创建自定义 MCP Server
- 用户可安装/卸载（启用/禁用）MCP Server
- 用户可覆盖已安装 MCP Server 的配置
- 系统内置 MCP Server 不可删除

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的 MCP Server 配置管理。DOC-06 的认证体系已完成。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

DOC-06 全部完成

## 要创建的文件

```
backend/app/
├── schemas/
│   └── mcp.py                 # MCP 请求/响应 Schema
├── services/
│   └── mcp_service.py         # MCP 业务逻辑
└── api/v1/
    └── mcp.py                 # MCP API 端点
```

## 实现规范

### 1. app/schemas/mcp.py

```python
class CreateMCPServerRequest(BaseModel):
    name: str
    description: str | None = None
    command: str                       # 启动命令
    args: list[str] = []              # 命令参数
    env: dict[str, str] = {}          # 环境变量

class MCPServerResponse(BaseModel):
    id: str
    name: str
    description: str | None
    scope: str                         # "system" | "user"
    command: str
    args: list[str]
    env: dict                          # system scope 的 env 不返回明文值
    created_at: datetime

class InstallMCPRequest(BaseModel):
    mcp_server_id: str
    config_override: dict = {}         # 用户级配置覆盖

class MCPInstallResponse(BaseModel):
    id: str
    mcp_server_id: str
    mcp_server_name: str
    is_enabled: bool
    config_override: dict
    created_at: datetime

class UpdateMCPInstallRequest(BaseModel):
    is_enabled: bool | None = None
    config_override: dict | None = None
```

### 2. app/services/mcp_service.py

```python
"""
MCP Server 配置管理

scope 说明：
- system: 系统内置，所有用户可见，不可删除。在 lifespan 中注册。
- user: 用户自定义，只对创建者可见。
"""

class MCPService:
    def __init__(self, db: Session):
        self._db = db
    
    def list_servers(self, include_system: bool = True) -> list["MCPServer"]:
        """列出 MCP Server（system + user scope）"""
        ...
    
    def create_server(self, data: CreateMCPServerRequest) -> "MCPServer":
        """创建自定义 MCP Server（scope=user）"""
        ...
    
    def delete_server(self, server_id: str) -> None:
        """删除自定义 MCP Server。system scope 不可删除 → 403"""
        ...
    
    def list_installs(self, user_id: str) -> list:
        """列出用户已安装的 MCP Server（含 JOIN mcp_servers 获取名称）"""
        ...
    
    def install(self, user_id: str, data: InstallMCPRequest) -> "UserMCPInstall":
        """安装 MCP Server"""
        ...
    
    def update_install(self, user_id: str, install_id: str, data: UpdateMCPInstallRequest) -> "UserMCPInstall":
        ...
    
    def uninstall(self, user_id: str, install_id: str) -> None:
        ...
    
    @staticmethod
    def register_builtin_servers(db: Session) -> None:
        """
        在 lifespan 中调用，注册系统内置 MCP Server。
        如果已存在（按 name 匹配）则跳过。
        """
        builtin = [
            {"name": "web_search", "description": "网页搜索", "command": "npx", "args": ["-y", "@anthropic/mcp-web-search"]},
            # 根据实际可用的 MCP Server 扩展
        ]
        ...
```

### 3. app/api/v1/mcp.py

按 DOC-01 v3 §6.7 的路由表实现全部 6 个端点。

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/schemas/mcp.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/services/mcp_service.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/api/v1/mcp.py

# 2. API 测试
TOKEN="..."

# 列出 MCP Server（应包含内置）
curl -s http://localhost:8000/api/v1/mcp-servers -H "Authorization: Bearer $TOKEN" | python -m json.tool

# 安装
curl -s -X POST http://localhost:8000/api/v1/mcp-installs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"mcp_server_id":"..."}' | python -m json.tool

# 列出已安装
curl -s http://localhost:8000/api/v1/mcp-installs -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

## 完成后

1. 更新 PROGRESS.md
2. 加载 Simplify skill 审查
3. 加载 PJR skill 验证
4. `git add -A && git commit -m "feat: MCP Server config management (CRUD + install/uninstall)"`
```

---

## Task 9.2: Provider 配置补充与用量 API

### Part A — 设计与解释

#### 问题陈述

DOC-02 Task 2.3 已经实现了 `ProviderService`（CRUD + 预设 + 测试）和 `ProviderManager`（运行时选择 + 故障转移）。本 Task 补充两个方面：

1. Provider 健康状态展示：从 Redis 读取 ProviderManager 写入的熔断状态（`harness:circuit:{provider_id}`），在 Provider 列表中展示实时健康状态
2. 用量统计 API：从 runs 表聚合 token 消耗和成本数据，按 Provider / 模型 / 时间维度统计

#### 职责分界再次明确

| 操作 | 执行方 | 位置 |
|------|--------|------|
| Provider CRUD | Backend ProviderService | DOC-02 Task 2.3 已完成 |
| 预设列表 | Backend ProviderService | DOC-02 Task 2.3 已完成 |
| 连通性测试 | Backend ProviderService | DOC-02 Task 2.3 已完成 |
| 运行时选择 + 故障转移 | Executor ProviderManager | DOC-02 Task 2.3 已完成 |
| 熔断状态写入 Redis | Executor ProviderManager | DOC-02 Task 2.3 已完成 |
| **熔断状态读取展示** | **Backend（本 Task）** | 从 Redis 读取，合并到 Provider 列表 |
| **用量统计** | **Backend（本 Task）** | 从 runs 表聚合 |

#### 验收标准

- Provider 列表中 `is_healthy` 反映 Redis 中的实时熔断状态
- 用量统计 API 返回按 Provider / 日 / 周 / 月的聚合数据
- 用量统计支持时间范围筛选

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在补充 Prism v2 的 Provider 配置能力。DOC-02 Task 2.3 的 ProviderService 和 ProviderManager 已完成。本 Task 新增健康状态实时展示和用量统计。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

DOC-02 Task 2.3 已完成

## 要修改的文件

```
backend/app/
├── services/
│   ├── provider_service.py    # 修改：新增 _enrich_health_from_redis() 和 get_usage_stats()
│   └── usage_service.py       # 新增：用量统计独立服务
└── api/v1/
    └── providers.py           # 修改：列表响应合并 Redis 健康状态
```

## 实现规范

### 1. app/services/provider_service.py 修改

```python
# 新增方法

def list_providers_with_health(self, user_id: str, redis_client) -> list[ProviderResponse]:
    """
    列出 Provider，合并 Redis 中的实时熔断状态。
    
    DB 中的 is_healthy 可能滞后（ProviderManager 写 Redis 但不一定即时写 DB）。
    以 Redis 为准：如果 Redis key `harness:circuit:{provider_id}` 存在，
    则该 Provider 正处于熔断状态。
    """
    providers = self.list_providers(user_id)
    for p in providers:
        circuit_key = f"harness:circuit:{p.id}"
        circuit_data = redis_client.get(circuit_key)
        if circuit_data:
            p.is_healthy = False
            # 可选：解析 circuit_data JSON 获取 failures 和 broken_at
        else:
            p.is_healthy = True
    return providers
```

### 2. app/services/usage_service.py

```python
"""
用量统计服务

数据来源：runs 表的 input_tokens / output_tokens / cost_usd 字段。
聚合维度：Provider / 模型 / 日 / 周 / 月。
"""

class UsageService:
    def __init__(self, db: Session):
        self._db = db
    
    def get_user_usage(
        self,
        user_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
        group_by: str = "day",          # "day" | "week" | "month"
    ) -> dict:
        """
        用户维度的用量统计。
        
        返回:
        {
            "summary": {
                "total_runs": 42,
                "total_input_tokens": 150000,
                "total_output_tokens": 50000,
                "total_cost_usd": 1.23,
            },
            "by_provider": [
                {"provider_id": "...", "provider_name": "...", "runs": 30, "tokens": 120000, "cost": 0.95},
            ],
            "by_model": [
                {"model": "MiniMax-M2.7", "runs": 30, "tokens": 120000, "cost": 0.95},
            ],
            "timeline": [
                {"date": "2026-04-01", "runs": 5, "tokens": 15000, "cost": 0.12},
            ],
        }
        """
        # 使用 SQLAlchemy func.sum() + group_by 聚合
        # WHERE user_id = :user_id（铁律 4）
        # WHERE status IN ('completed', 'failed')（排除 pending/cancelled）
        # WHERE created_at BETWEEN start_date AND end_date
        ...
    
    def get_global_usage(self, start_date: date | None = None, end_date: date | None = None) -> dict:
        """
        全局用量统计（Admin 用）。
        同上结构，不做 user_id 过滤。
        """
        ...
```

### 3. API 补充

```python
# providers.py 修改：列表端点使用 list_providers_with_health
# 新增用量端点

@router.get("/providers/usage", response_model=ApiResponse[dict])
def get_provider_usage(
    start_date: date | None = None,
    end_date: date | None = None,
    group_by: str = "day",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """当前用户的 Provider 用量统计"""
    ...
```

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/services/usage_service.py

# 2. 用量统计测试（需要已有 Run 数据）
TOKEN="..."
curl -s "http://localhost:8000/api/v1/providers/usage?group_by=day" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool

# 3. 健康状态展示测试
# 在 Redis 中写入模拟的熔断状态
docker compose -f docker-compose.dev.yml exec redis redis-cli SET "harness:circuit:PROVIDER_ID" '{"failures":3}' EX 300
# 列出 Provider
curl -s http://localhost:8000/api/v1/providers -H "Authorization: Bearer $TOKEN" | python -m json.tool
# 期望：对应 Provider 的 is_healthy=false
```

## 完成后

1. 更新 PROGRESS.md
2. 加载 Simplify skill 审查
3. 加载 PJR skill 验证
4. `git add -A && git commit -m "feat: Provider health from Redis + usage statistics API"`
```

---

> **文档维护说明**：本文档的 2 个 Task 完成后，Prism v2 将拥有完整的 MCP 和 Provider 配置管理能力：MCP Server CRUD + 安装/卸载 + Provider 实时健康状态（Redis 熔断数据）+ 用量统计 API（按 Provider/模型/时间聚合）。职责分界明确：Backend ProviderService 负责配置层，Executor ProviderManager 负责运行时层，两者通过 DB + Redis 异步通信。
> **最后更新**: 2026-04-02 | **下一步**: DOC-10 Frontend Foundation

---

## Task 9.3: Admin 审计日志与系统管理

### Part A — 设计与解释

#### 问题陈述

DOC-09 标题包含"Admin"但缺少 Admin 管理功能的 Task。需要实现管理员审计日志查询和系统管理接口。

#### API 端点

```
GET    /admin/audit-logs          — 查询审计日志（分页、筛选）
GET    /admin/audit-logs/export   — 导出审计日志（CSV/JSON）
GET    /admin/system/stats        — 系统统计（用户数、会话数、Run 数、Token 用量）
GET    /admin/users               — 用户列表管理
PATCH  /admin/users/{id}/role     — 修改用户角色
DELETE /admin/users/{id}          — 禁用用户（软删除）
```

#### 审计日志查询参数

```python
class AuditLogQuery:
    action: str | None = None       # 筛选操作类型（如 "harness.guardrail_trigger"）
    user_id: str | None = None      # 筛选用户
    start_time: str | None = None   # ISO 8601 起始时间
    end_time: str | None = None     # ISO 8601 结束时间
    page: int = 1
    page_size: int = 50             # max 200
```

#### 验收标准

- `GET /admin/audit-logs` 返回分页的审计日志
- 非 admin 用户调用返回 403
- 审计日志包含 Harness 治理事件（guardrail_trigger、permission_deny 等）
- 系统统计数据准确
- 用户角色修改立即生效
- 审计日志导出支持 CSV 和 JSON 两种格式

### Part B — Claude Code 执行 Prompt

> 待实施计划执行阶段补充

## 完成后

1. Admin 审计日志查询和系统管理接口正常工作
2. 非 admin 用户无法访问 admin 端点
3. 更新 PROGRESS.md：Task 9.3 状态标记为 done
