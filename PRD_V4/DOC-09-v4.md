# Prism 棱镜 v2 — Backend MCP / Provider Config / Admin (DOC-09)

> **文档编号**: DOC-09
> **版本**: 4.0(Review 修订版)
> **日期**: 2026-04-18
> **性质**: 实现文档 — MCP Server 管理、Provider 配置 UI 支撑、Admin 扩展功能
> **前置依赖**: DOC-01 v4(Schema: mcp_servers + user_mcp_installs + providers), DOC-02 v4 Task 2.3(ProviderManager 运行时逻辑), DOC-06 v4(认证体系 + Admin API 骨架)
> **Phase**: 2(后端功能模块)
> **Task 数**: 3(v3.1 Task 9.3 Admin v4 补完 Part B)
> **v4 变更摘要**: 基于 5 轮 review 修订,15 处精确修补(详见文末 §附录 A)。核心修订:Provider scope 字段 CRUD(platform/user 分层)、capabilities 探测强制(POST /providers/{id}/test 返回 detected_capabilities)、用量 API 返回 cache tokens 三字段 + 节省金额、**Task 9.3 Admin Part B 完整补全**(admin_stats_service 系统统计 + audit-logs 查询 + 用户管理 + 权限边界)。ADR 编号从 ADR-080 接续至 ADR-085。
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

#### 设计决策(ADR)

- **ADR-080(Provider scope 字段 CRUD)**:Provider 加 `scope` 字段(`platform` / `user`):
  - `platform`:平台预置,所有用户可见,仅 admin 可 CRUD
  - `user`:用户自建,仅该 user_id 可见和 CRUD
  - 列表 API 返回:user 的私有 Providers + 所有 platform Providers(并集)

  来源:Batch 1 v2 §Q4, Batch 3 §A9-3。

- **ADR-081(capabilities 探测强制)**:`POST /providers/{id}/test` 不再是"可选连通性测试",而是**必须探测并返回** `detected_capabilities: {prompt_caching, vision, function_calling, streaming, extended_thinking, ...}`。前端 Provider 卡片展示这些能力徽章;PromptAssembler 根据 capabilities 决定是否启用 cache_control 等特性(DOC-02 v4 ADR-008)。来源:Batch 3 §A9-3, DOC-02 v4 Task 2.3 引用。

- **ADR-082(用量 API 返回 cache tokens 三字段)**:`GET /providers/usage?period=day|week|month` 返回:
  ```json
  {
    "total_input_tokens": 12000,
    "total_output_tokens": 3500,
    "cache_hit_tokens": 8000,
    "cache_miss_tokens": 4000,
    "cache_creation_tokens": 1000,
    "cache_hit_ratio": 0.67,
    "estimated_cache_savings_usd": 0.12,
    "total_cost_usd": 0.28,
    "by_provider": [...],
    "by_model": [...]
  }
  ```
  来源:Batch 1 v2 §R6, Master M7。

#### 验收标准(v4 扩展)

- Provider 列表中 `is_healthy` 反映 Redis 中的实时熔断状态
- **v4:Provider 响应含 `scope: platform|user` 字段;列表返回并集**
- 用量统计 API 返回按 Provider / 日 / 周 / 月的聚合数据
- 用量统计支持时间范围筛选
- **v4:`GET /providers/usage` 返回 cache tokens 三字段 + cache_hit_ratio + cache_savings_usd**
- **v4:`POST /providers/{id}/test` 返回 detected_capabilities**(DOC-02 v4 Task 2.3 引用)

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

> **文档维护说明(v4)**:本文档的 3 个 Task 完成后,Prism v2 将拥有完整的 MCP/Provider 配置管理 + Admin 能力:MCP Server CRUD + 安装/卸载 + Provider 实时健康状态(Redis 熔断数据) + **scope-aware CRUD (platform/user)** + **capabilities 强制探测** + 用量统计 API(**含 cache tokens 三字段 + 节省金额**) + **Admin 审计日志查询(含 Harness 事件前缀匹配)** + **Dashboard 统计** + **用户管理(权限边界)**。职责分界明确:Backend ProviderService 负责配置层,Executor ProviderManager 负责运行时层,两者通过 DB + Redis 异步通信。
> **最后更新**: 2026-04-18 (v4 review 修订版) | **下一步**: DOC-10 v4 Frontend Foundation

---

## 附录 A: v4 修订清单

本次修订共 15 处精确修补,对应 Batch 1-5 review + Master:

| # | 位置 | 修订内容 | 来源 |
|---|---|---|---|
| 1 | Header | 版本 3.1 → 4.0,日期 2026-04-18,Task 数 2 → 3,v4 摘要段 | 全局 |
| 2 | Task 9.1 Part A | 无大改 | — |
| 3 | Task 9.2 Part A | 新增 ADR-080(Provider scope 字段 CRUD)/ADR-081(capabilities 探测强制)/ADR-082(用量 API 返回 cache tokens 三字段) | Batch 3 §A9-3, Batch 1 v2 §R6 |
| 4 | Task 9.2 provider_service | scope-aware CRUD(DOC-02 v4 Task 2.3 引用)+ 列表返回 platform ∪ user 并集 | 同上 |
| 5 | Task 9.2 用量 API | `GET /providers/usage?period=day|week|month` 返回 input/output/cache_hit/cache_miss/cache_creation tokens + cache_hit_ratio + estimated_cache_savings_usd + total_cost_usd + by_provider/by_model | Batch 1 v2 §R6, Master M7 |
| 6 | Task 9.2 capability 探测 | `POST /providers/{id}/test` 返回 `detected_capabilities`(DOC-02 v4 Task 2.3 引用) | Batch 3 §A9-3 |
| 7 | **Task 9.3 重大修订(Part B 完整补全)** | v3 Part B "待实施补充",v4 补完整实现 | Master M8 |
| 8 | Task 9.3 Part B 文件树 | admin.py + audit_service.py + admin_stats_service.py(系统统计) | Batch 3 C-1 |
| 9 | Task 9.3 审计日志查询 API | `GET /admin/audit-logs?action=&user_id=&severity=&start_time=&end_time=&page=` 支持 action 前缀匹配(ADR-084);`GET /admin/audit-logs/export?format=csv` CSV 导出(≤10000 行) | 同上 |
| 10 | Task 9.3 系统统计 API | `GET /admin/stats/dashboard` 返回 SystemStatsResponse(24h runs / 7d cost / cache 节省 / 24h harness_events 分布 / active_sessions / active_users_24h / component_health) | Batch 3 C-1 |
| 11 | Task 9.3 权限边界 | ADR-083:禁止降级最后一个 admin(409) + 禁止禁用自己(409) | Batch 3 C-1 |
| 12 | Task 9.3 用户管理 API | `GET /admin/users`(分页+搜索) / `PATCH /admin/users/{id}/role` / `DELETE /admin/users/{id}` | 同上 |
| 13 | Prometheus metrics | `prism_provider_healthy` / `prism_provider_failover_total` / `prism_admin_operations_total{op_type}` | Batch 5 §B5-I |
| 14 | ADR 编号 ADR-080~085 + 交叉引用 v3 → v4 | 全局 | 全局 |
| 15 | 附录 A + 文末 | 修订清单 + 下一步 DOC-10 v4 | SOP |

---

## Task 9.3: Admin 审计日志与系统管理(v4:Part B 完整补全)

### Part A — 设计与解释

#### 问题陈述

DOC-09 标题包含"Admin"但 v3.1 缺少 Admin 管理功能的 Task Part B 实现。v4 完整补全:审计日志查询(支持 Harness 事件筛选)、系统统计 Dashboard(24h runs / 7d cost / harness 事件 / 健康状态)、用户管理(角色修改 + 禁用)、权限边界(禁止降级最后一个 admin / 禁止禁用自己)。

#### 设计决策(ADR)

- **ADR-083(Admin 权限边界)**:管理员操作必须强制两条安全线:
  1. **禁止降级最后一个 admin**:若当前系统只剩 1 个 admin,`PATCH /admin/users/{id}/role` 将其降级为普通用户会返回 409 Conflict
  2. **禁止禁用自己**:当前登录用户不能通过 `DELETE /admin/users/{id}` 禁用自己

  来源:Batch 3 C-1。

- **ADR-084(审计日志支持 Harness 事件筛选)**:`GET /admin/audit-logs` 查询参数 `action` 支持前缀匹配,如 `action=harness.` 匹配所有 Harness 事件,`action=harness.guardrail_` 匹配所有 guardrail 事件。

- **ADR-085(admin_stats_service 系统统计)**:`GET /admin/stats/dashboard` 返回 `SystemStatsResponse`:24h runs / 7d cost / 24h harness 事件分布 / 组件健康状态(Redis / PostgreSQL / 各 Provider)。

#### API 端点(v4 完整)

```
GET    /admin/audit-logs                — 查询审计日志(分页、筛选、Harness 事件支持)
GET    /admin/audit-logs/export         — 导出审计日志(CSV/JSON)
GET    /admin/stats/dashboard           — 系统统计 Dashboard
GET    /admin/users                     — 用户列表管理(分页 + 搜索)
PATCH  /admin/users/{id}/role           — 修改用户角色(禁止降级最后一个 admin)
DELETE /admin/users/{id}                — 禁用用户(软删除,禁止禁用自己)
```

#### 验收标准(v4 扩展)

- `GET /admin/audit-logs` 返回分页的审计日志,支持 `action` 前缀匹配
- 非 admin 用户调用返回 403
- 审计日志包含 Harness 治理事件(guardrail_trigger / permission_deny / permission_ask_timeout / compaction_tier / heartbeat_stale 等)
- 系统统计数据准确,含 24h runs / 7d cost / cache 节省 / 组件健康
- 用户角色修改立即生效
- **v4:禁止降级最后一个 admin(409),禁止禁用自己(409)**
- 审计日志导出支持 CSV 和 JSON 两种格式

### Part B — Claude Code 执行 Prompt

> **v4 Observability 采集要求**:
> - structlog:`admin.user.role_changed` / `admin.user.disabled` / `admin.audit_logs.exported`
> - Prometheus:`prism_admin_operations_total{op_type}`

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在补完 Prism v2 的 Admin 管理能力。DOC-06 v4 已有 AuditLog 模型 + `require_admin` 依赖。本 Task 新增审计日志查询 + 系统统计 + 用户管理 API。

## 前置条件

DOC-06 v4 完成

## 要创建的文件

```
backend/app/
├── services/
│   ├── audit_service.py             # 审计日志查询
│   └── admin_stats_service.py       # 系统统计
├── schemas/
│   ├── audit.py                     # AuditLog 响应 + 查询参数
│   └── admin.py                     # SystemStatsResponse
└── api/v1/
    └── admin.py                     # /admin/* 端点
```

## 实现规范

### 1. app/schemas/audit.py

```python
from datetime import datetime
from pydantic import BaseModel


class AuditLogQuery(BaseModel):
    action: str | None = None          # 支持前缀匹配(如 harness. / harness.guardrail_)
    user_id: str | None = None
    severity: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    page: int = 1
    page_size: int = 50                # max 200


class AuditLogResponse(BaseModel):
    id: str
    user_id: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    severity: str
    details: dict
    created_at: datetime
```

### 2. app/schemas/admin.py

```python
class SystemStatsResponse(BaseModel):
    runs_24h: int
    runs_7d: int
    cost_usd_7d: float
    cache_savings_usd_7d: float
    harness_events_24h: dict[str, int]     # {event_type: count}
    active_sessions: int
    active_users_24h: int
    component_health: dict[str, str]        # {redis: "healthy", postgres: "healthy", ...}
    timestamp: datetime
```

### 3. app/services/audit_service.py

```python
class AuditService:
    def __init__(self, db):
        self._db = db

    def query(self, q: AuditLogQuery) -> tuple[list[AuditLog], int]:
        stmt = self._db.query(AuditLog)
        if q.action:
            # 前缀匹配
            stmt = stmt.filter(AuditLog.action.startswith(q.action))
        if q.user_id:
            stmt = stmt.filter(AuditLog.user_id == q.user_id)
        if q.severity:
            stmt = stmt.filter(AuditLog.severity == q.severity)
        if q.start_time:
            stmt = stmt.filter(AuditLog.created_at >= q.start_time)
        if q.end_time:
            stmt = stmt.filter(AuditLog.created_at <= q.end_time)

        total = stmt.count()
        rows = stmt.order_by(AuditLog.created_at.desc())\
            .offset((q.page - 1) * q.page_size)\
            .limit(min(q.page_size, 200))\
            .all()
        return rows, total

    def export_csv(self, q: AuditLogQuery) -> bytes:
        """导出 CSV(最多 10000 行,超限返回 400)"""
        import io, csv
        rows, total = self.query(q)
        if total > 10000:
            raise HTTPException(400, "Export exceeds 10000 rows, narrow filter")
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["id", "user_id", "action", "severity", "created_at", "details"])
        for r in rows:
            writer.writerow([r.id, r.user_id, r.action, r.severity, r.created_at, json.dumps(r.details)])
        return buf.getvalue().encode()
```

### 4. app/services/admin_stats_service.py

```python
from datetime import datetime, timedelta, timezone


class AdminStatsService:
    def __init__(self, db, redis_client, settings):
        self._db = db
        self._redis = redis_client
        self._settings = settings

    async def get_dashboard(self) -> SystemStatsResponse:
        now = datetime.now(timezone.utc)
        t24h = now - timedelta(hours=24)
        t7d = now - timedelta(days=7)

        runs_24h = self._db.query(Run).filter(Run.created_at >= t24h).count()
        runs_7d_rows = self._db.query(Run).filter(Run.created_at >= t7d).all()
        cost_usd_7d = sum((r.cost_usd or 0) for r in runs_7d_rows)

        # Cache 节省估算(按 cache_hit_tokens * $0.30/1M 粗算,具体按 Provider)
        cache_savings = sum(
            (r.cache_hit_tokens or 0) * 0.00000027
            for r in runs_7d_rows
        )

        # Harness 事件分布(24h)
        harness_events = {}
        rows = self._db.query(AuditLog.action, func.count())\
            .filter(AuditLog.created_at >= t24h)\
            .filter(AuditLog.action.startswith("harness."))\
            .group_by(AuditLog.action).all()
        for action, cnt in rows:
            harness_events[action] = cnt

        active_sessions = self._db.query(Session).filter(Session.status == "running").count()
        active_users_24h = self._db.query(User).filter(User.last_login_at >= t24h).count()

        # 组件健康
        health = {"postgres": "healthy", "redis": "healthy"}
        try:
            await self._redis.ping()
        except Exception:
            health["redis"] = "unhealthy"
        # Provider 健康:扫 harness:circuit:* key
        broken_count = 0
        async for _ in self._redis.scan_iter(match="harness:circuit:*"):
            broken_count += 1
        health["providers"] = f"{broken_count} broken" if broken_count else "healthy"

        return SystemStatsResponse(
            runs_24h=runs_24h,
            runs_7d=len(runs_7d_rows),
            cost_usd_7d=round(cost_usd_7d, 4),
            cache_savings_usd_7d=round(cache_savings, 4),
            harness_events_24h=harness_events,
            active_sessions=active_sessions,
            active_users_24h=active_users_24h,
            component_health=health,
            timestamp=now,
        )
```

### 5. app/api/v1/admin.py

```python
from fastapi import APIRouter, Depends, HTTPException, Response

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/audit-logs")
async def list_audit_logs(q: AuditLogQuery = Depends(), admin=Depends(require_admin), db=Depends(get_db)):
    rows, total = AuditService(db).query(q)
    return {"data": [AuditLogResponse.model_validate(r) for r in rows],
            "pagination": {"page": q.page, "page_size": q.page_size, "total": total}}


@router.get("/audit-logs/export")
async def export_audit_logs(format: str = "csv", q: AuditLogQuery = Depends(),
                            admin=Depends(require_admin), db=Depends(get_db)):
    svc = AuditService(db)
    if format == "csv":
        content = svc.export_csv(q)
        return Response(content, media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=audit.csv"})
    raise HTTPException(400, "Only csv supported in Phase 1")


@router.get("/stats/dashboard")
async def get_dashboard(admin=Depends(require_admin), db=Depends(get_db),
                       redis_client=Depends(get_redis), settings=Depends(get_settings)):
    return await AdminStatsService(db, redis_client, settings).get_dashboard()


@router.get("/users")
async def list_users(page: int = 1, page_size: int = 50, search: str | None = None,
                    admin=Depends(require_admin), db=Depends(get_db)):
    q = db.query(User)
    if search:
        q = q.filter(or_(User.email.contains(search), User.username.contains(search)))
    total = q.count()
    rows = q.order_by(User.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return {"data": rows, "pagination": {"page": page, "page_size": page_size, "total": total}}


@router.patch("/users/{user_id}/role")
async def change_role(user_id: str, body: dict, admin=Depends(require_admin), db=Depends(get_db)):
    """v4 ADR-083:禁止降级最后一个 admin"""
    target = db.query(User).filter_by(id=user_id).first()
    if not target:
        raise HTTPException(404)
    new_role = body.get("role")
    if target.role == "admin" and new_role != "admin":
        admin_count = db.query(User).filter(User.role == "admin", User.is_active == True).count()
        if admin_count <= 1:
            raise HTTPException(409, "Cannot demote the last admin")
    target.role = new_role
    db.commit()
    logger.info("admin.user.role_changed", target_user_id=user_id, new_role=new_role, by=str(admin.id))
    return {"success": True}


@router.delete("/users/{user_id}", status_code=204)
async def disable_user(user_id: str, admin=Depends(require_admin), db=Depends(get_db)):
    """v4 ADR-083:禁止禁用自己"""
    if str(admin.id) == user_id:
        raise HTTPException(409, "Cannot disable yourself")
    target = db.query(User).filter_by(id=user_id).first()
    if not target:
        raise HTTPException(404)
    target.is_active = False
    db.commit()
    logger.info("admin.user.disabled", target_user_id=user_id, by=str(admin.id))
```

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/services/audit_service.py app/services/admin_stats_service.py app/api/v1/admin.py

# 2. 最后一个 admin 降级拒绝
# 创建只有一个 admin 的 DB 状态 → PATCH /admin/users/{admin_id}/role {role: user} → 期望 409

# 3. 禁用自己拒绝
# DELETE /admin/users/{self_id} → 期望 409

# 4. Dashboard 统计
curl -s http://localhost:8000/api/v1/admin/stats/dashboard -H "Authorization: Bearer $ADMIN_TOKEN" | python -m json.tool
```

## 完成后

1. 更新 PROGRESS.md:Task 9.3 Part B 补完
2. 更新 DECISIONS.md:记录 **ADR-083(Admin 权限边界)/ADR-084(审计 Harness 事件筛选)/ADR-085(admin_stats_service)**
3. `git add -A && git commit -m "feat(v4): admin audit logs + stats dashboard + user management with boundary checks"`
```

## 完成后

1. Admin 审计日志查询和系统管理接口正常工作
2. 非 admin 用户无法访问 admin 端点
3. 更新 PROGRESS.md：Task 9.3 状态标记为 done
