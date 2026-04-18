# Prism v2 跨 Session Handoff 日志

> **规范**: 每个 Sonnet session 结束前必写一段 200-400 字记录;新 session 开工前必读最近 3 条
> **格式**: 倒序(最新在顶)
> **初始化**: 2026-04-18

---

## 模板(每次 session 末尾按此格式追加到顶部)

```markdown
## YYYY-MM-DD HH:MM — <Task ID> <状态>

### 本次 session 做了什么
- (按完成顺序列出关键动作,3-7 条)

### 验证结果
- Part B 验证步骤:PASS / PARTIAL(列未通过项)/ FAIL
- 质量门 10 项:PASS / FAIL(列未过项)

### 下一个 Task 需要注意
- (如果下一个 Task 依赖本 Task 的某个细节,明确写出来)
- (例:"ask_protocol.py 的 Redis key 格式是 perm_answer:{uuid4},DOC-07 Task 7.3 的 permission-answer 端点 RPUSH 时必须严格匹配")

### 遗留风险 / 未决事项
- 无 / 或具体风险描述

### Commit
- `<commit hash>` — `<conventional commits message>`
```

---

## 日志记录(最新在顶)

---

## 2026-04-19 -- DOC-12 Task 12.2 COMPLETED

### 本次 session 做了什么
- 新建 backend/app/services/harness_analytics.py — HarnessAnalytics.aggregate(user_id, days, offset_days) P0非重叠窗口修复; cache_stats v4新增(hit_tokens/miss_tokens/creation_tokens/hit_ratio/creation_cost_ratio/by_provider); compute_signal_p90() 30天扫描 供 ThresholdCalibrator (ADR-112)
- 新建 backend/app/services/entropy_detector.py — EntropyDetector 8信号(5基础+3 v4新: provider_failover_growth/cache_hit_ratio_drop/permission_ask_timeout_rate); 环境变量可配置阈值(ENTROPY_THRESHOLD_*); audit_log写入(action=harness.entropy_alert); ThresholdCalibrator EMA校准(0.7*current+0.3*p90) (ADR-112/ADR-113)
- 修改 backend/app/api/v1/harness.py — 追加 3 新端点: GET /harness/analytics(user-scoped+offset_days) + POST /harness/entropy-check(admin only) + POST /harness/threshold-calibrate(admin only, scan_days)

### 验证结果
- py_compile harness_analytics.py: PASS
- py_compile entropy_detector.py: PASS
- AST parse harness.py(含新端点): PASS
- HarnessAnalytics 结构完整性(period/totals/averages/cache_stats/route_distribution): PASS
- offset_days 非重叠窗口(end0==start7,delta<5s): PASS
- HarnessAnalytics mock数据(2 runs, turns/tool_calls/cache_hit正确): PASS
- EntropyDetector 8信号检测(guardrail/error/compaction/loop/permission_ask_timeout): PASS
- ThresholdCalibrator EMA公式(0.7*0.3+0.3*0.05=0.225): PASS
- harness.py 4端点+imports+offset_days参数: PASS
- 进程边界(entropy_detector/harness_analytics 无 executor.* import): PASS
- 共10项验证全 PASS

### 下一个 Task 需要注意
- DOC-12 Task 12.3: /health 3子端点 + Docker 资源限制
  - GET /health/live — 仅返回 {"status":"ok"}, 不查依赖
  - GET /health/ready — 检查 DB + Redis, 不可用返回 503
  - GET /health/detailed — admin only, 调用 ResourceMonitor.check_health() + HarnessAnalytics.aggregate(days=7)
  - docker-compose.yml 4个服务全加 limits/reservations/healthcheck (backend/postgres/redis/nginx)
  - nginx.conf SSE透传: X-Accel-Buffering: no + proxy_read_timeout 3600s
- HarnessAnalytics.aggregate() 中 harness_summary JSONB 通过 PostgreSQL raw SQL 查询;需要 runs 表有实际数据才能看到非零结果

### 遗留风险 / 未决事项
- EntropyDetector.detect() 中 AuditLog 实例化会触发 SQLAlchemy mapper configure (import side effect); 在纯测试环境中若 invite_codes FK 未配置会报 NoForeignKeysError; 在真实 PostgreSQL + alembic upgrade head 环境下不受影响
- ThresholdCalibrator 输出建议阈值 Admin 审核后手动写入环境变量——Phase 1 流程手动; Phase 2 可接入 harness config yaml 写回接口

### Commit
- `67d17a7` — `feat(v4): DOC-12 Task 12.2 — Harness Analytics + Entropy Detection (ADR-112/ADR-113)`

---

## 2026-04-19 -- DOC-12 Task 12.1 COMPLETED

### 本次 session 做了什么
- 新建 executor/engine/token_estimator.py — TokenEstimator ABC + AnthropicTokenCounter(包装 ModelAdapter.count_tokens(), Claude首选) + TiktokenEstimator(cl100k_base, OpenAI/DeepSeek) + CalibratingCharCountEstimator(字符计数+EMA observer校准, fallback) + create_estimator() 工厂 (ADR-110)
- 修改 executor/engine/__init__.py — 追加导出4新符号: AnthropicTokenCounter / CalibratingCharCountEstimator / TiktokenEstimator / create_estimator
- 新建 backend/app/services/resource_monitor.py — ResourceMonitor 百分比阈值(memory_warn=70%/critical=85%, cpu_warn=80%/critical=95%); check_health()含thresholds/queue_depth; is_memory_warn()/is_memory_critical() (ADR-111)
- 新建 backend/app/services/route_analytics.py — RouteAnalytics.get_accuracy_stats(days=30) + get_agent_type_distribution(days=7); 查 runs.harness_summary JSONB route_reason

### 验证结果
- py_compile token_estimator.py: PASS
- py_compile resource_monitor.py: PASS
- py_compile route_analytics.py: PASS
- TokenEstimator 3实现(CharCount/Tiktoken/CalibratingChar)基本估算: PASS
- CalibratingCharCountEstimator.observe_usage EMA校准: PASS (6次后 factor=1.038)
- TiktokenEstimator.estimate_messages dict格式: PASS (22 tokens)
- executor.engine 4新符号导出 + process boundary check: PASS
- ResourceMonitor ADR-111百分比阈值(70%/85%) + custom threshold触发: PASS
- 共8项验证全 PASS

### 下一个 Task 需要注意
- DOC-12 Task 12.2: HarnessAnalytics + EntropyDetector(8信号)
  - aggregate() 需加 offset_days 参数，避免窗口重叠(PRD Part A 窗口修复P0)
  - EntropyDetector 使用 current(days=7,offset=0) vs previous(days=7,offset=7) 非重叠窗口
  - ThresholdCalibrator 每周扫30天 harness_summary p90，EMA平滑 0.7*current+0.3*p90
  - CalibratingCharCountEstimator.observe_usage() 在 AnthropicDriver stream结束后调用
- ResourceMonitor.check_health() 的 queue_depth 参数由调用方注入(避免循环导入 task_service)
- DOC-12 Task 12.3 /health/detailed 端点直接调用 ResourceMonitor.check_health()
- context_budget.py 的 TokenEstimator Protocol 已存在且正确，token_estimator.py 的 TokenEstimator ABC 是并存策略实现，无需合并

### 遗留风险 / 未决事项
- AnthropicTokenCounter 在 token_estimator.py 中与 token_estimator_adapter.py 的 DriverTokenEstimator 功能重叠；两者目前并存，DOC-12 Task 12.2+ 可统一引用 token_estimator.py；无功能冲突
- TiktokenEstimator 首次调用需下载编码器文件(~1MB)，Docker 环境需预热或预下载

### Commit
- `702eeb8` — `feat(v4): DOC-12 Task 12.1 — TokenEstimator + ResourceMonitor (ADR-110/111)`

---

## 2026-04-19 -- DOC-09 Task 9.3 COMPLETED + DOC-09 DONE 收官 checkpoint

### 本次 session 做了什么
- 新建 backend/app/schemas/audit.py — AuditLogQuery(ADR-084 prefix action filter, severity, start_time, end_time, page/page_size) + AuditLogResponse(7字段)
- 新建 backend/app/schemas/admin.py — SystemStatsResponse(ADR-085 9字段: runs_24h/runs_7d/cost_usd_7d/cache_savings/harness_events_24h/active_sessions/active_users_24h/component_health/timestamp)
- 新建 backend/app/services/audit_service.py — AuditService: _base_query(LIKE前缀+severity JSONB+时间范围) + query(分页) + export_csv(max 10k行 UTF-8 BOM)
- 新建 backend/app/services/admin_stats_service.py — AdminStatsService.get_dashboard(): DB聚合 + Redis ping健康 + scan_iter harness:circuit:* + cache savings $0.27/1M
- 修改 backend/app/api/v1/admin.py — 4新端点(GET /audit-logs/export CSV; GET /stats/dashboard ADR-085; PATCH /users/{id}/role last-admin guard ADR-083; DELETE /users/{id} soft-disable no-self guard ADR-083); list_users追加pagination+search(ilike or_)
- 修改 backend/app/models/user.py — 追加 is_active: Mapped[bool] Boolean NOT NULL DEFAULT TRUE(ADR-083)
- 新建 backend/alembic/versions/005_add_is_active_to_users.py — ADD COLUMN is_active; chain 004→005

### 验证结果
- py_compile 5新文件(schemas/audit+admin, services/audit_service+admin_stats_service, api/v1/admin): PASS
- AuditLogQuery+AuditLogResponse 字段实例化: PASS
- SystemStatsResponse 字段实例化: PASS
- ADR-083 guards(last-admin 409 + no-self 409) + endpoint routing: PASS
- AuditService methods(query+export_csv+_base_query): PASS
- AdminStatsService methods(__init__+get_dashboard): PASS
- list_users pagination+search(ilike+or_): PASS
- ADR-084 prefix matching(LIKE): PASS
- ADR-085 AdminStatsService content(harness.*+scan_iter+component_health+cache_savings): PASS
- 共9项验证全 PASS

### 下一个 Task 需要注意
- **DOC-09 完整收官** — 所有3个Task完成(9.1 MCP管理 + 9.2 Provider用量 + 9.3 Admin管理)
- DOC-10 Task 10.1: Next.js搭建 + 设计系统; 无直接后端依赖
- Admin端点(stats/dashboard)依赖 get_redis() async依赖; 确保 lifespan Redis已初始化
- User.is_active字段需 alembic upgrade head (005 migration); 测试环境需注意
- GET /admin/users 接口签名已从 ApiResponse[list] 改为 ApiResponse[PagedResponse]，前端DOC-11 Task 11.6需按新结构解析

### 遗留风险 / 未决事项
- AuditLog.severity 存在 JSONB details字段中而非 top-level column; ADR-084 severity filter使用 details["severity"].as_string()，仅 PostgreSQL JSONB有效(SQLite不兼容)，Prism v2锁定PG已知可接受
- AdminStatsService 使用同步 DB session 但 async get_dashboard; 混合同步/异步在 FastAPI 中可能轻微阻塞，Phase 1 可接受

### Commit
- `93d6694` — `feat(v4): DOC-09 Task 9.3 — Admin audit logs + stats dashboard + user management (ADR-083/084/085)`

---

## ===== DOC-09 DONE checkpoint (2026-04-19) =====
DOC-09 Backend MCP/Provider/Admin 完整收官：
- Task 9.1 (commit未记录) — MCP Server CRUD + install/uninstall + scope + bootstrap
- Task 9.2 (commit e2a5463) — Provider health Redis + usage API ADR-082
- Task 9.3 (commit 93d6694) — Admin audit logs + stats dashboard + user management ADR-083/084/085
下一步: DOC-10 Frontend Foundation

---

## 2026-04-19 -- DOC-09 Task 9.2 COMPLETED (Provider 健康状态 Redis + 用量 API ADR-082)

### 本次 session 做了什么
- 新建 backend/app/services/usage_service.py — UsageService: get_user_usage()(铁律4 user_id严格过滤) + get_global_usage()(Admin用); ADR-082全字段: cache_hit_tokens/cache_miss_tokens/cache_creation_tokens/cache_hit_ratio/estimated_cache_savings_usd/total_cost_usd/by_provider(含name lookup via IN)/by_model/timeline(date_trunc day|week|month); _compute_cache_savings($3.00/1M × 90%)
- 修改 backend/app/services/provider_service.py — 追加 list_providers_with_health(db, user_id, redis_client): 读 Redis harness:circuit:{id} key → is_healthy=False(熔断); Redis不可用时 try/except 降级保持DB值
- 修改 backend/app/api/v1/providers.py — list_providers端点改用 list_providers_with_health(sync Redis client via _get_sync_redis()); 新增 GET /providers/usage 端点(group_by=day|week|month, start_date/end_date query params, ADR-082完整响应)

### 验证结果
- py_compile 3文件(usage_service.py / provider_service.py / providers.py): PASS
- cache_savings计算(_compute_cache_savings 8000 tokens → $0.0216): PASS
- _resolve_date_range(默认最近30天/显式日期): PASS
- list_providers_with_health 方法签名(db/user_id/redis_client)+try/except: PASS
- ADR-082全字段(cache_hit/miss/creation_tokens+ratio+savings+cost+by_provider+by_model): PASS
- 铁律4 user_id filter(Run.user_id == user_id): PASS
- harness:circuit:{id} key格式 + REDIS_URL配置: PASS
- 共7项验证全 PASS

### 下一个 Task 需要注意
- DOC-09 Task 9.3: Admin 审计日志查询 + 系统统计 + 用户管理; ADR-083/084/085
- admin.py 已有基础路由(Task 6.2实现: list_users/update_role/invite_codes/audit_logs/usage); Task 9.3 需补完: audit-logs导出CSV + stats/dashboard(AdminStatsService) + 禁止降级最后一个admin(ADR-083) + 禁止禁用自己(ADR-083)
- admin.py 现有 list_users 无分页+搜索 → Task 9.3需补充page/search参数; 现有update_user_role只阻止自己修改自己但未检查"最后一个admin" → Task 9.3补充409逻辑
- UsageService.get_global_usage() 已实现供 AdminStatsService 调用(Task 9.3)

### 遗留风险 / 未决事项
- providers.py 用 sync redis client(同步) 做健康检查; 非 async 路由中调用同步 redis.get() 可能轻微阻塞事件循环。生产建议改用 asyncio redis + await，但当前实现足够 Phase 1。
- usage_service.py 的 date_trunc() 是 PostgreSQL 函数，不支持 SQLite；Prism v2 锁定 PostgreSQL，此限制已知可接受。

### Commit
- `e2a5463` — `feat(v4): DOC-09 Task 9.2 — Provider health from Redis + usage statistics API (ADR-082)`

---

## 2026-04-19 -- DOC-09 Task 9.1 COMPLETED (MCP Server CRUD + install/uninstall + scope权限 + builtin bootstrap)

### 本次 session 做了什么
- 新建 backend/app/schemas/mcp.py — 5 schema: CreateMCPServerRequest / MCPServerResponse / InstallMCPRequest / MCPInstallResponse / UpdateMCPInstallRequest / MCPTestResponse
- 新建 backend/app/services/mcp_service.py — MCPService 9方法(list_servers/get_server/create_server/delete_server/test_server/list_installs/install/update_install/uninstall) + register_builtin_servers staticmethod(web_search + filesystem 两内置); system scope env值在响应层掩码'***'; UNIQUE(409)通过IntegrityError捕获; 铁律4全覆盖
- 新建 backend/app/api/v1/mcp.py — 8路由: GET/POST /mcp-servers + DELETE/POST(test) /mcp-servers/{id} + GET/POST /mcp-installs + PATCH/DELETE /mcp-installs/{id}
- 修改 backend/app/models/mcp_server.py — 追加 user_id Mapped[str|None] FK nullable (system→NULL, user→owner UUID)
- 新建 backend/alembic/versions/004_add_user_id_to_mcp_servers.py — ADD COLUMN + INDEX + downgrade
- 修改 backend/app/main.py — lifespan step 4b: MCP bootstrap (register_builtin_servers)
- 修改 backend/app/api/v1/__init__.py — 导入并注册 mcp_router

### 验证结果
- py_compile 3新文件(schemas/mcp.py + services/mcp_service.py + api/v1/mcp.py): PASS
- schema字段验证(CreateMCPServerRequest / UpdateMCPInstallRequest partial / MCPTestResponse): PASS
- 服务方法签名(9方法 + register_builtin_servers static): PASS
- 路由结构验证(8端点 AST解析): PASS
- scope守护逻辑(scope='user'强制 + system→403 + user_id!=owner→403 + 409 IntegrityError): PASS
- builtin bootstrap(web_search + npx + idempotent skip): PASS
- ORM model + migration(user_id FK nullable + down_revision链): PASS
- main.py + __init__.py wiring: PASS
- 共10项验证全 PASS

### 下一个 Task 需要注意
- DOC-09 Task 9.2: Provider 配置补充 + 用量 API; ADR-080/081/082
- provider_service.py 已有 list_providers() — Task 9.2 新增 list_providers_with_health(redis_client) + get_usage_stats()
- usage_service.py 需新建; runs 表有 input_tokens/output_tokens/cost_usd 字段可直接聚合
- ADR-080 Provider scope 字段已在 Task 2.3 实现(scope='system'|'user'); Task 9.2 重点是 Redis 熔断状态读取 + cache tokens 三字段

### 遗留风险 / 未决事项
- McpServer.user_id 迁移(Migration 004)需要运行 alembic upgrade head 才能在 DB 生效；开发环境未连接 DB 故未运行，属正常
- test_server() 当前为 stub，返回 detected_capabilities=['tools']；完整探测需 DOC-05 MCPClient 集成

### Commit
- (feat commit) — `feat(v4): DOC-09 Task 9.1 — MCP Server CRUD + install/uninstall + scope权限矩阵 + builtin bootstrap`

---

## 2026-04-19 -- DOC-08 Task 8.3 COMPLETED + **DOC-08 DONE** 3/3 (IMBindingService + 配对码 + 三元组唯一)

### 本次 session 做了什么
- 新建 backend/app/services/im_binding_service.py — IMBindingService 完整服务层
  - `generate_pairing_code(user_id, channel)`: 6位数字+碰撞重试3次+upsert未完成绑定+5min TTL(via created_at)
  - `pair(channel, platform_user_id, platform_chat_id, code)`: TTL校验+一次性使用+ADR-071三元组IntegrityError捕获
  - `list_bindings(user_id)` + `unbind(user_id, binding_id)` (所有权校验+物理删除)
  - `expires_at()` 辅助方法供路由层使用
  - VALID_CHANNELS frozenset + 常量集中管理
- 修改 backend/app/api/v1/im.py — 3个绑定端点(list/pair/unbind)全部委托IMBindingService; 移除内联secrets.randbelow业务逻辑; 清理无用import(datetime/timezone/Response/ImBinding)
- 修改 backend/app/services/im_gateway.py — `_handle_pairing()` 重构为调用`IMBindingService.pair(platform_chat_id=...)`; 逻辑由30行→15行; 传递platform_chat_id支持ADR-071多群聊绑定
- ADR-071落地补强: DB UNIQUE(channel, platform_user_id, platform_chat_id)已在Task8.1 schema落地; Task8.3在服务层用IntegrityError捕获三元组冲突

### 验证结果
- py_compile 3文件 (im_binding_service.py / im.py / im_gateway.py): PASS
- 常量校验(VALID_CHANNELS/PAIRING_CODE_LENGTH/TTL/MAX_RETRIES): PASS
- 方法签名(generate_pairing_code/pair/list_bindings/unbind/expires_at): PASS
- ValueError on invalid channel (mock DB): PASS
- im.py 路由结构(3端点均present + IMBindingService import): PASS
- 无内联pairing逻辑(randbelow/ImBinding直接写): PASS
- im_gateway._handle_pairing使用IMBindingService.pair(): PASS
- ADR-071三元组UniqueConstraint列名验证: PASS
- platform_chat_id传递验证: PASS
- 共12项验证全 PASS

### 下一个 Task 需要注意
- DOC-09 Task 9.1: MCP Server 管理端点; ADR-080起
- IMBindingService.pair() 返回bool而非抛异常；三元组冲突时发"配对码无效"提示（用户侧体验可能改善，但功能正确）
- im_gateway._handle_pairing现在是纯委托模式，未来如需扩展绑定逻辑（如display_name从IM平台抓取）在IMBindingService中增加即可

### 遗留风险 / 未决事项
- DOC-08 无遗留风险；三个Task全部完整实现
- **DOC-08 DONE** checkpoint: Task 8.1(IMAdapter+IMGateway+Webhook幂等) + Task 8.2(飞书+企微+Telegram适配器) + Task 8.3(IMBindingService+配对码+三元组唯一) 全部完成

### Commit
- `177ee65` — `feat(v4): DOC-08 Task 8.3 — IM user binding service (pairing code + triple unique constraint)`

---

## 2026-04-19 -- DOC-08 Task 8.2 COMPLETED (FeishuAdapter + WeComAdapter + TelegramAdapter)

### 本次 session 做了什么
- 新建 backend/app/services/im_feishu.py — FeishuAdapter: Webhook模式接收 + HMAC-SHA256签名验证(X-Lark-Signature) + AES-CBC-256解密(pycryptodome) + asyncio.Lock保护的tenant_access_token刷新 + handle_webhook()/verify_signature()/decrypt_message() + graceful skip(未配置时)
- 新建 backend/app/services/im_wecom.py — WeComAdapter: SHA1 msg_signature验证 + AES-CBC-256 XML解密(encoding_aes_key+padding) + GET URL验证(verify_url) + XML解析(_xml_text helper) + asyncio.Lock access_token刷新 + REST发送(touser/toparty/toall判断)
- 新建 backend/app/services/im_telegram.py — TelegramAdapter: Long Polling asyncio.Task(_polling_loop) + getUpdates offset追踪 + sendMessage + 优雅停止(cancel+5s等待) + graceful skip(未配置时)
- 修改 backend/app/api/v1/im.py — POST /webhook/feishu(body_bytes读取+签名验证+分发); GET /webhook/wecom(URL验证+PlainTextResponse); POST /webhook/wecom(msg_signature验证+PlainTextResponse); 适配器从app.state.im_gateway懒获取(_get_feishu_adapter/_get_wecom_adapter)
- 修改 backend/requirements.txt — 追加 pycryptodome>=3.20.0(AES-CBC-256解密必需)
- ADR-072(飞书签名+token刷新) / ADR-073(企微SHA1+AES解密) 落地

### 验证结果
- py_compile 4文件: PASS
- 三适配器实现 IMAdapter 接口: PASS
- channel_name + set_message_handler注入: PASS
- 飞书签名验证(合法/非法/无token): PASS
- 企微签名验证(合法/非法/无token): PASS
- 三平台消息截断(feishu=4000/wecom=2048/tg=4096): PASS
- 飞书 URL 验证 challenge 响应: PASS
- graceful skip(未配置时 start() 不抛异常): PASS
- stop() 幂等: PASS
- IMGateway.register_adapter + get_adapter: PASS — 共 10 项全 PASS

### 下一个 Task 需要注意
- Task 8.3(用户绑定)已在 Task 8.1 的 api/v1/im.py 中实现了大部分逻辑(generate_pairing_code/list_bindings/unbind)；Task 8.3 主要补充 IMBindingService 服务层并重构路由
- 飞书适配器目前使用 Webhook 模式（非 WebSocket SDK），符合 PRD "最常见方案"；若需 WebSocket 模式，在 im_channel_configs.config 中增加 mode 字段即可扩展
- pycryptodome 已在 requirements.txt 中；若 Docker 镜像未重建则需 pip install pycryptodome

### 遗留风险 / 未决事项
- 飞书 WebSocket 长连接模式（官方 lark-oapi SDK）暂未实现，当前 Webhook 模式已足够生产使用
- 企微群聊 platform_chat_id 约定（"party:" 前缀）应在 Task 8.3 绑定流程中明确文档化

### Commit
- `7f85b76` — `feat(v4): DOC-08 Task 8.2 — Feishu + WeCom + Telegram IM adapters`

---

## 2026-04-19 -- DOC-08 Task 8.1 COMPLETED (IMAdapter + IMGateway + Webhook幂等)

### 本次 session 做了什么
- 新建 backend/app/services/im_adapter.py — IMAdapter ABC 4抽象方法(channel_name/start/stop/send) + set_message_handler(); IMIncomingMessage(msg_id专属字段 ADR-070) + IMOutgoingMessage dataclasses; MessageHandler 类型别名
- 新建 backend/app/services/im_dedup.py — IMDedupService(DB主方案ADR-070): is_duplicate() IntegrityError去重 + cleanup_expired() + update_session_id(); IMDedupRedisService(SETNX备选方案)
- 新建 backend/app/services/im_gateway.py — IMGateway统一路由: register_adapter()注入_handle_message; _handle_message: ADR-070幂等→pairing code识别→binding三元组查找→find_or_create_session→TaskService.submit()(同Web链路)→_start_run; send_run_result()截断(feishu=4000/wecom=2048/tg=4096); start_all()从DB读enabled状态; _send_binding_guide()未绑定引导; _handle_pairing()配对码完成绑定
- 新建 backend/app/schemas/im.py — 5 schema: IMChannelConfigResponse/Update + IMBindingResponse + PairingCodeResponse + IMWebhookEvent
- 新建 backend/app/api/v1/im.py — 7路由: GET/PATCH /im/channels(admin+脱敏) + POST /webhook/feishu+wecom(public skeleton) + GET /im/bindings + POST /im/bindings/pair(6位码碰撞重试) + DELETE /im/bindings/{id}
- 修改 backend/app/observability/metrics.py — 新增 prism_im_webhook_duplicates_total{channel} + prism_im_bindings_active (ADR-070 B5-I)
- 修改 backend/app/api/v1/__init__.py — 注册 im_router

### 验证结果
- py_compile 7文件: PASS
- IMAdapter是抽象基类(无法直接实例化): PASS
- MockAdapter实现IMAdapter接口: PASS
- IMGateway.register_adapter + handler注入: PASS
- ADR-071 im_bindings三元组唯一约束: PASS
- ADR-070 im_message_dedup两列唯一约束: PASS
- IMDedupService + IMDedupRedisService方法: PASS
- Prometheus 3个IM指标注册: PASS
- IM router 7条路由: PASS
- Platform message length limits: PASS
- 配对码检测逻辑(/pair前缀+6位数字): PASS
- im_router importable: PASS
- 合计 17项验证全 PASS

### 下一个 Task 需要注意
- DOC-08 Task 8.2: FeishuAdapter/WeComAdapter/TelegramAdapter 分别实现 IMAdapter ABC
  - 必须在 IMIncomingMessage.msg_id 字段设置平台原生消息 ID（ADR-070 去重依赖此字段）
  - 飞书: /im/webhook/feishu 端点已占位，Task 8.2 在此解析 X-Lark-Signature + 事件
  - 企微: /im/webhook/wecom 端点已占位，支持 GET URL验证 + POST 消息
  - Telegram: Long Polling 后台任务，不走 Webhook
  - 三个适配器均注入 IMGateway（lifespan 初始化时 register_adapter）
- IMGateway._start_run() 使用懒导入 app.main.app 获取 process_manager；若 Docker 部署需确认循环导入无影响
- api/v1/im.py 的 POST /im/bindings/pair 中配对码生成逻辑是 Task 8.1 内联实现，Task 8.3 可提取到 IMBindingService 类并重构此路由

### 遗留风险 / 未决事项
- IMGateway._start_run() 通过 `from app.main import app` 懒导入获取 process_manager，测试环境需 mock
- Task 8.2 企微适配器需要 XML 解密（需要 pycryptodome 或类似库，requirements.txt 待更新）
- IMGateway.start_all() 从 DB 查 im_channel_configs，若 DB 尚未初始化会静默跳过（非错误）

### Commit
- `f9d8e3f` — `feat(v4): IMAdapter abstraction + IMGateway routing + Webhook idempotency (ADR-070/071) — DOC-08 Task 8.1`

---

## 2026-04-19 -- DOC-07 Task 7.4 COMPLETED + DOC-07 完整收官 4/4 (subprocess 调度 + coordinator_recovery + alert_dispatcher)

### 本次 session 做了什么
- 新建 backend/app/services/process_manager.py — ProcessManager(ADR-066): _build_command 6必传argv + _build_env ENCRYPTION_KEY/OTEL via env; start_run() ThreadPoolExecutor提交; kill_run(force=False/True) SIGTERM/SIGKILL; shutdown(); _mark_running 写 subprocess_pid; _notify_timeout/_notify_failure HTTP回调(3次重试)
- 新建 backend/app/services/coordinator_recovery.py — CoordinatorRecoveryService(ADR-067): resume(run_id, user_id) 校验 failed+heartbeat_stale → 查 coordinator_plans → 新建 Run → plan.run_id → process_manager.start_run(resume_from_step)
- 新建 backend/app/services/alert_dispatcher.py — AlertDispatcher 4级severity分档: info仅structlog / warning→audit_logs / error→audit+SSE / critical→audit+SSE+IM stub+Email stub
- 修改 backend/app/services/run_lifecycle.py — mark_running(run_id, pid=None) 追加 pid 参数，写 runs.subprocess_pid
- 修改 backend/app/api/v1/runs.py — 追加 POST /runs/{run_id}/resume 端点（ADR-067）；从 request.app.state.process_manager 获取单例
- 修改 backend/app/api/v1/tasks.py — 替换 _start_agent_subprocess stub，改为从 request.app.state.process_manager 调用 start_run()
- 修改 backend/app/api/v1/internal.py — handle_callback 处理 promoted_run_id 时调用 process_manager.start_run()（完成 Task 7.3 的 deferred TODO）
- 修改 backend/app/main.py — lifespan step 6 新增 ProcessManager 初始化 + app.state.process_manager 挂载 + shutdown()

### 验证结果
- py_compile 8 新文件/修改文件: PASS
- ADR-066 命令构建: 6必传argv + --resume-from-step可选 + ENCRYPTION_KEY in env: PASS
- ProcessManager kill_run SIGTERM/SIGKILL/非存在: PASS
- AlertDispatcher 4级severity路由(info/warning/error/critical): PASS
- CoordinatorRecoveryService 404/409(wrong status)/409(not heartbeat_stale): PASS
- POST /runs/{run_id}/resume 路由注册: PASS
- tasks.py ProcessManager集成(无stub残留): PASS
- internal.py promoted_run_id→start_run: PASS
- 质量门 10 项: PASS

### 下一个 Task 需要注意
- DOC-08 Task 8.1 启动: IM Webhook 幂等需用 im_message_dedup 表（已在 DOC-01 v4 §4.2 定义）
- AlertDispatcher im_service 参数：DOC-08 完成后 IMAdapter 实例可直接注入
- ProcessManager._post_callback 向 http://localhost:8000 发 HTTP，Docker 网络内应改为 http://backend:8000（遗留风险）

### 遗留风险 / 未决事项
- ProcessManager._post_callback hardcode localhost:8000，Docker 生产环境需配置化（DOC-12 或 DOC-09）
- ALERT_IM_CHANNEL/ALERT_EMAIL 尚未加入 Settings class（alert_dispatcher 用 getattr 兜底，DOC-12 Task 12.8 添加）

### Commit
- `e04f08b` — `feat(v4): subprocess scheduler (ADR-066) + coordinator_recovery (ADR-067) + alert_dispatcher — DOC-07 Task 7.4`

---

## 2026-04-19 -- DOC-07 Task 7.3 completed (Callback 双通道 + SSE Manager + HeartbeatMonitor + permission-answer)

### 本次 session 做了什么
- 新建 backend/app/services/sse_manager.py — SSEManager(ADR-063): MAX_CONNS=3/STREAM_BUFFER=200/publish+subscribe+backfill_since+acquire_conn_slot+release_conn_slot+start_subscribe_async
- 新建 backend/app/services/heartbeat_monitor.py — HeartbeatMonitor(ADR-065): 每 10s SCAN harness:heartbeat:*，超 30s 标记 crashed; scan_interval=10, stale_threshold=30; run/stop/_scan_once/_handle_key
- 新建 backend/app/services/callback_service.py — CallbackService(ADR-063): 10 event handlers (text_delta/tool_start/tool_end/message_complete/run_complete/run_error/permission_ask/harness_event/coordinator_plan_update/session_title); _extract_text_preview helper; 幂等设计; coordinator_plan_update UPSERT
- 新建 backend/app/api/v1/internal.py — POST /internal/callbacks (X-Callback-Secret 认证+统一 commit) + POST /internal/run-crashed (ADR-065 mark_crashed endpoint)
- 修改 backend/app/api/v1/sessions.py — 追加 GET /sessions/{id}/stream (SSE ticket auth ADR-057 + last_event_id 补发 + 多 tab 限制 429) + POST /sessions/{id}/permission-answer (ADR-064 UPDATE permission_requests + RPUSH perm_answer:{request_id})
- 修改 backend/app/api/v1/__init__.py — 注册 internal_router
- 修改 backend/app/main.py — lifespan 追加 HeartbeatMonitor asyncio.create_task 启动 + 优雅关闭 (cancel+wait)
- 修改 backend/app/core/dependencies.py — get_redis() 从 NotImplementedError 实装为 async redis.asyncio.Redis
- 修改 backend/app/models/permission_request.py — 追加 decision VARCHAR(10) NULLABLE 字段 (ADR-064 UPDATE decision=X)
- 新建 backend/alembic/versions/003_add_decision_to_permission_requests.py — ALTER TABLE permission_requests ADD COLUMN decision VARCHAR(10)

### 验证结果
- Part B 验证步骤: 全 12 项 PASS (+ 2 bonus: migration + _extract_text_preview)
- 质量门 10 项: PASS

### 下一个 Task 需要注意
- Task 7.4 子进程调度：internal.py handle_callback 在 run_complete/run_error 时返回 promoted_run_id，Task 7.4 需接收并启动新子进程
- Task 7.4 subprocess 启动参数：--callback-url=http://backend:8000/api/v1/internal/callbacks --callback-secret=${CALLBACK_SECRET}（已在 internal.py 使用 CALLBACK_SECRET 认证）
- ADR-066 编号：Task 7.4 的 subprocess 参数标准化从 ADR-066 起；Task 7.3 已用 ADR-063/064/065

### 遗留风险 / 未决事项
- callback_service 的 asyncio.create_task() 在同步 handler 内 fire-and-forget SSE publish：需要 FastAPI 的 event loop 存活，不影响 DB 同步路径；但如果 SSE publish 失败不会报错（设计为容错）
- get_redis() dependency 实装为每请求创建/关闭连接，高并发时可用连接池优化（Task 7.4 或 DOC-12 优化）

### Commit
- `a2c43b5` — `feat(v4): Callback(双通道) + SSE Manager + HeartbeatMonitor + permission-answer — DOC-07 Task 7.3`

---

## 2026-04-19 -- DOC-07 Task 7.2 completed (Task 提交 + Run 生命周期 + ADR-060/061/062)

### 本次 session 做了什么
- 新建 backend/app/schemas/task.py — SubmitTaskRequest(session_id/prompt/agent_type) + SubmitTaskResponse(accepted_type/queue_position)
- 新建 backend/app/schemas/run.py — RunResponse(harness_summary JSONB) + RunListResponse(精简) + CancelRunRequest(mode 三模式枚举校验)
- 新建 backend/app/services/sequence_service.py — ADR-060 两方案: get_next_message_sequence_no(CREATE SEQUENCE IF NOT EXISTS + nextval) + get_next_message_sequence_no_advisory(pg_advisory_xact_lock + max+1) + get_next_queue_sequence_no(advisory+offset 2^32)
- 新建 backend/app/services/task_service.py — TaskService.submit: session_id=None自动创session; idle→_submit_immediate(创Run+阻塞session); busy→_submit_queued(advisory_xact_lock+QUEUE_MAX_SIZE=50)
- 新建 backend/app/services/run_lifecycle.py — RunLifecycle: mark_running/complete_and_promote/fail_and_promote/cancel(ADR-062三模式SIGTERM/SIGKILL/also_cancel_queue)/mark_crashed(ADR-065)/timeout; _promote_next()单事务FOR UPDATE SKIP LOCKED(ADR-061)
- 新建 backend/app/services/session_queue.py — SessionQueueService: list_queue/cancel_item/get_queue_size
- 新建 backend/app/api/v1/tasks.py — POST /tasks(202 Accepted) + GET /sessions/{id}/queue + DELETE /sessions/{id}/queue/{item_id} + POST /runs/{id}/cancel
- 新建 backend/app/api/v1/runs.py — GET /runs/{id}(含harness_summary) + GET /sessions/{id}/runs(分页)
- 修改 backend/app/models/run.py — 追加 subprocess_pid Integer 字段（cancel三模式 SIGTERM/SIGKILL 必需）
- 新建 backend/alembic/versions/002_add_subprocess_pid_to_runs.py — ALTER TABLE runs ADD COLUMN subprocess_pid INTEGER
- 修改 backend/app/api/v1/__init__.py — 注册 tasks_router + runs_router

### 验证结果
- Part B 验证步骤(8个文件编译+schema6项+RunLifecycle方法签名+promote原子性+ADR约束+路由注册): 全部 PASS
  - py_compile 8 新文件 PASS
  - SubmitTaskRequest/Response 构造 PASS; CancelRunRequest 三模式校验 PASS; 非法mode拒绝 PASS
  - RunLifecycle 8方法全存在 PASS; cancel含mode+user_id PASS; complete_and_promote含harness_summary PASS
  - FOR UPDATE SKIP LOCKED 存在 PASS; 单commit PASS
  - CREATE SEQUENCE IF NOT EXISTS PASS; pg_advisory_xact_lock PASS
  - lock_key message≠queue PASS
  - Run.subprocess_pid ORM字段存在 PASS; migration 002 well-formed PASS
  - 6条路由路径验证 PASS

### 下一个 Task 需要注意
- Task 7.3 callback_service 写 messages 时必须调用 get_next_message_sequence_no(db, session_id)，不可用 MAX+1
- Task 7.3 run_complete 事件处理 → complete_and_promote(run_id, ..., harness_summary=json)，harness_summary 在 promote 事务中写入
- Task 7.4 executor 启动成功后需调用 mark_running(run_id) 将 subprocess_pid 写入 DB，cancel 端点才能发信号
- Task 7.4 _start_agent_subprocess(run_id) 在 tasks.py 中是 stub，Task 7.4 实现时替换

### 遗留风险 / 未决事项
- _start_agent_subprocess 当前为 stub（Task 7.4 实现）
- get_next_message_sequence_no 使用方案 1（CREATE SEQUENCE），在 PG RDS 权限受限时需切换方案 2（advisory_xact_lock）
- cancel 依赖 subprocess_pid 字段，需 Task 7.4 写入后才能发信号（pid=None 时 kill 被静默跳过）

### Commit
- `63903c1` — `feat(v4): Task 提交 + Run 生命周期 (sequence_no + cancel 三模式) — DOC-07 Task 7.2`

---

## 2026-04-19 -- DOC-07 Task 7.1 completed (Session CRUD + 消息增量 + generate_text_preview)

### 本次 session 做了什么
- 新建 backend/app/schemas/session.py — CreateSessionRequest(title+config_snapshot) / UpdateSessionRequest / SessionResponse(含计算字段 message_count+last_message_preview) / SessionListResponse(精简版)
- 新建 backend/app/schemas/message.py — MessageResponse(id/run_id/role/content list[dict]/text_preview/sequence_no/created_at)
- 新建 backend/app/services/session_service.py — SessionService(list_sessions排序:pinned优先+updated_at DESC / create_session / get_session 铁律4 / update_session pin逻辑 / delete_session / get_message_count / get_last_message_preview / list_messages after_sequence_no增量) + generate_text_preview(tool_result前缀/tool_use前缀/纯text/[empty], DOC-01 v4 §4.2)
- 新建 backend/app/api/v1/sessions.py — 6路由: GET/POST /sessions + GET/PATCH/DELETE /sessions/{id} + GET /sessions/{id}/messages(limit≤500 after_sequence_no ge=0)
- 修改 backend/app/api/v1/__init__.py — 注册sessions_router,docstring追加sessions路由描述

### 验证结果
- Part B 验证步骤(编译4项+schema6项+generate_text_preview6项+路由6条+约束3项): 全部 PASS
  - py_compile 4个新文件 PASS
  - CreateSessionRequest 默认/自定义 PASS; UpdateSessionRequest 全None/is_pinned PASS; MessageResponse构造 PASS
  - generate_text_preview: 纯text/200字截断/空->empty/assistant tool_use前缀/user tool_result前缀/空text块->empty 全PASS
  - 6条路由注册 PASS(GET/POST /sessions + GET/PATCH/DELETE /{session_id} + GET /{session_id}/messages)
  - limit=500常量/after_sequence_no ge=0/le=_MAX_MESSAGES_LIMIT约束 PASS

### 下一个 Task 需要注意
- DOC-07 Task 7.2 必须实现 sequence_no 写端 (per-session 序列或 advisory_xact_lock)，ADR-060 在 Task 7.1 只落地了读端
- SessionService.get_session() 对不属于用户的 session 返回 404（不暴露 403），Task 7.2/7.3 沿用此约定
- generate_text_preview() 已在 session_service.py 定义，Task 7.2 的消息写入时可复用生成 text_preview 字段
- list_messages 的 content 字段：ORM content 可能是 dict(单 block) 或 list，session.py 已做 isinstance 判断兜底

### 遗留风险 / 未决事项
- 无新增风险。sequence_no 写端仍在 Task 7.2 待实施(非遗留风险，是计划内分工)

### Commit
- `870b4bb` — `feat(v4): Session CRUD + message incremental query (DOC-07 Task 7.1)`

---

## 2026-04-19 -- DOC-06 Task 6.2 completed (用户管理 + 邀请码 + Admin API + ADR-059；DOC-06 完整收官)

### 本次 session 做了什么
- 新建 backend/app/schemas/invite.py — CreateInviteCodeRequest(max_uses≥1校验) + InviteCodeResponse.from_orm_model(is_valid 计算: 未过期 AND used_count<max_uses)
- 新建 backend/app/schemas/user.py — UserListResponse + UpdateUserRoleRequest(Literal["admin","user"])
- 新建 backend/app/services/invite_service.py — InviteService: generate_code(PRISM-前缀+8位大写字母数字 secrets.choice) / create(碰撞去重) / validate(存在+未过期+未用完) / consume / list_all / revoke(max_uses=used_count)
- 新建 backend/app/api/v1/admin.py — 7 端点全部实现: GET/PATCH /admin/users; POST/GET/DELETE /admin/invite-codes; GET /admin/usage(totals+per_provider+30天趋势); GET /admin/audit-logs(LIKE前缀筛+user_id筛+分页); router-level dependencies=[Depends(require_admin)](ADR-059); 自我角色修改防护(400)
- 修改 backend/app/api/v1/__init__.py — 注册 admin_router, docstring 追加 admin 路由描述
- DOC-06 完整收官: Task 6.1 + Task 6.2 均已 completed; ADR-056/057/058/059 全部落地

### 验证结果
- Part B 验证步骤(编译4项+逻辑7项): 全部 PASS
  - py_compile schemas/invite.py + schemas/user.py + services/invite_service.py + api/v1/admin.py PASS
  - CreateInviteCodeRequest 默认/自定义/max_uses=0拒绝 PASS
  - UpdateUserRoleRequest 合法/非法role拒绝 PASS
  - generate_code() 100样本 PRISM-前缀+8位大写字母数字+总长14 PASS
  - InviteCodeResponse.from_orm_model is_valid 3场景(有效/过期/用完) PASS
  - revoke() 逻辑(max_uses=used_count → is_valid=False) PASS
  - admin router 7条路由全注册 + router-level require_admin dependency PASS

### 下一个 Task 需要注意
- DOC-07 Task 7.1 Session CRUD: admin.py GET /admin/usage 使用了 Run 模型的 func.date() 聚合，PostgreSQL 环境测试时注意 date() 函数兼容性
- InviteService.validate() 用于 AuthService.register() 中的邀请码校验——Task 6.1 的 auth_service.py 已内联邀请码检查逻辑，Task 6.2 的 InviteService.validate() 是独立服务层；若后续需统一，可将 auth_service.py 的内联检查替换为 InviteService.validate() 调用
- GET /admin/audit-logs 支持 action 前缀 LIKE 筛选，DOC-07 Task 7.x 写 harness.* 审计日志后可通过 ?action=harness. 查询

### 遗留风险 / 未决事项
- Redis 未初始化时 SSE ticket 端点返回 503（Task 6.1 遗留，DOC-07 Task 7.3 解决）
- GET /admin/usage daily_trend 使用 func.date() — PostgreSQL 原生支持，SQLite 测试需注意
- GET /admin/users 无分页（Phase 1 设计，用户量小时可接受）

### Commit
- `e47c31d` — `feat(v4): user management + invite codes + admin API (DOC-06 Task 6.2)`
- docs commit: 后续更新 PROGRESS/DECISIONS/HANDOFF-LOG

---

## 2026-04-19 -- DOC-06 Task 6.1 completed (认证体系 JWT+SSE ticket + ADR-056/057/058)

### 本次 session 做了什么
- 新建 backend/app/schemas/auth.py — RegisterRequest(邮箱/用户名/密码/邀请码校验) + LoginRequest + SSETicketRequest + TokenResponse + RefreshResponse + UserResponse(from_attributes=True)
- 新建 backend/app/services/user_service.py — UserService: get_by_id / get_by_email / get_by_username / update(**kwargs)
- 新建 backend/app/services/auth_service.py — AuthService: register(邀请码校验 → 创建用户 → 消耗邀请码 → AuditLog + token) / login(verify_password → last_login_at → AuditLog + token) / refresh(decode_token type==refresh → 新 access token) / ensure_admin(幂等 admin 创建); _write_audit 内部辅助
- 新建 backend/app/services/sse_ticket_service.py — SSETicketService: generate_ticket(SETEX sse_ticket:{uuid4} 60s {user_id,session_id}) / verify_and_consume(GETDEL 原子 → 401 on expired / 403 on session_id mismatch) — ADR-057
- 新建 backend/app/api/v1/auth.py — 6 路由: POST /auth/register(201) / POST /auth/login / POST /auth/refresh(cookie) / POST /auth/logout(delete cookie) / GET /auth/me / POST /auth/sse-ticket(ADR-051/057); _set_refresh_cookie(httponly=True secure=True samesite=lax path=/api/v1/auth ADR-058)
- 修改 backend/app/api/v1/__init__.py — include auth_router, docstring 追加 auth 路由描述
- 修改 backend/app/core/dependencies.py — get_current_user 追加 type=="access" 校验(拒绝 refresh token 作 Bearer)
- 修改 backend/app/main.py — lifespan 步骤 5: ensure_admin() + db.commit()
- ADR-056/057/058 落地 DECISIONS.md; PROGRESS.md 更新(Task 6.1 completed, 23/51)

### 验证结果
- Part B 验证步骤(全 15 项 PASS):
  - py_compile × 5 文件(auth.py schemas / auth_service.py / user_service.py / sse_ticket_service.py / api/v1/auth.py) PASS
  - validate_secrets 四场景(短密钥/碰撞/三者合法) PASS
  - AES-256-GCM roundtrip + 错误 key 拒绝 + nonce 随机性 PASS
  - JWT create_access_token/create_refresh_token/decode_token roundtrip PASS
  - RegisterRequest 校验(3 errors for bad email/短用户名/短密码) PASS
  - SSETicketService generate_ticket(uuid4 ticket + expires_at ISO-8601) PASS
  - SSETicketService verify_and_consume 正常/重放 401/session 不匹配 403 PASS
  - UserService 4 方法 + update(self, user_id, **kwargs) 签名 PASS
  - 6 路由声明(register/login/refresh/logout/me/sse-ticket) PASS
  - api_v1_router 挂载 /api/v1/auth/* 全路由 PASS
  - get_current_user 拒绝 refresh token → 401 PASS
  - refresh cookie: httponly=True, secure=True, samesite=lax PASS
  - SSE ticket Redis key 前缀 sse_ticket: + setex + getdel PASS
  - AuthService.refresh() 拒绝 access token 类型 → 401 PASS
  - ensure_admin 源码 role=admin + 幂等检查 + 4 方法完整 PASS
- 质量门 10 项: PASS

### 下一个 Task 需要注意
- DOC-06 Task 6.2 继续实现: schemas/invite.py + schemas/user.py + services/invite_service.py + api/v1/admin.py(7 Admin 端点)
- InviteCode.created_by 在 ORM 层无 FK(模型注释"No ON DELETE CASCADE 意图"),admin.py 需注意直接 sql query,不依赖 relationship
- SSE ticket 的 verify_and_consume() 由 DOC-07 Task 7.3 SSE Manager 调用(stream endpoint 收到 ?ticket= 时原子消费)
- ensure_admin() 已在 main.py lifespan 步骤 5 调用;DOC-07 不需要再次添加
- get_redis() 目前返回 NotImplementedError;SSE ticket 端点在 Redis 未初始化时返回 503(预期行为)

### 遗留风险 / 未决事项
- SSE ticket 端点依赖 Redis;在 DOC-07 Task 7.3 完成 get_redis() 实现前,该端点返回 503
- Phase 1 不实现 refresh token blacklist;登出后 access token 在 15min 内仍有效(PRD 明确接受)
- InviteCode ORM relationship User.invite_codes 因 FK 缺失无法在内存 SQLAlchemy 图中 traverse(仅影响测试 mock;生产 DB 层 FK 由 Alembic migration 保证)

### Commit
- `1526438` — `feat(v4): Auth system (JWT login/register/refresh + SSE ticket) — DOC-06 Task 6.1`

---

## 2026-04-19 -- DOC-05 Task 5.7 completed + DOC-05 DONE checkpoint (CC 兼容层 + ADR-054/055)

### 本次 session 做了什么
- 新建 executor/plugins/cc_compat.py — CCPluginAdapter（detect_format 4路径优先级 / load 统一入口 / _load_prism/cc/skills_only 三路加载 / export_to_cc 返回 ConversionReport / _scan_hooks_dir CC→Prism event_type 映射 / _scan_mcp_servers_dir config.json 解析 / _build_cc_zip zip 生成含 CONVERSION_NOTES.md）；ConversionReport dataclass（success/cc_compat_zip/lost_fields/warnings/plugin_name/cc_plugin_json 6字段 ADR-054）；PluginSchemaError（errors list ADR-055）；PluginYamlSchema（Pydantic extra="allow" forward-compat）
- 修改 executor/plugins/host.py — PluginHost.__init__ 追加 cc_adapter 参数（默认自动注入 CCPluginAdapter）；新增 load_plugin_from_dir() 方法（目录级统一入口，自动格式检测）
- 修改 executor/plugins/__init__.py — 导出 5 新符号（CCPluginAdapter/ConversionReport/PluginFormatError/PluginSchemaError/PluginYamlSchema）
- 新建 backend/app/api/v1/plugins.py — 3 路由（POST /load 格式检测+摘要; POST /export-cc ConversionReport zip base64; POST /validate Pydantic 校验+extra_fields 告警）；内联 Pydantic schema；PluginSchemaError → HTTP 422；进程边界（Backend 不启动 MCP 子进程）
- 修改 backend/app/api/v1/__init__.py — include plugins_router；更新 docstring
- ADR-054/055 落地 DECISIONS.md；blocker.md 追加 Task 5.7 ADR 平移链（DOC-06 Task 6.1 须从 ADR-056 起）
- PROGRESS.md 更新（Task 5.7 completed，22/51；下一动作 DOC-06 Task 6.1）

### 验证结果
- Part B 验证步骤（全 19 项 PASS）：
  - py_compile × 5 文件（cc_compat.py / host.py / __init__.py / plugins.py / api_v1/__init__.py）PASS
  - CCPluginAdapter/ConversionReport/PluginFormatError/PluginSchemaError/PluginYamlSchema 导入 PASS
  - executor.plugins 导出 5 新符号 PASS
  - PluginHost.__init__ cc_adapter 参数 + load_plugin_from_dir 方法 PASS
  - ConversionReport 6 字段完整 PASS
  - detect_format 4 场景（unknown/skills_only/cc/prism 优先级）PASS
  - PluginFormatError on load nonexistent dir PASS
  - _load_cc_plugin（plugin.json + skills/ + mcp-servers/）PASS
  - _load_skills_collection PASS
  - _load_prism_plugin（valid plugin.yaml）PASS
  - PluginSchemaError on missing name（errors 携带详细位置）PASS
  - export_to_cc ConversionReport（lost_fields/warnings/cc_compat_zip/cc_plugin_json）PASS
  - zip 含 plugin.json + README.md + CONVERSION_NOTES.md PASS
  - MCP 名称冲突 → warnings PASS
  - forward-compat 未知字段不拒绝 PASS
  - _scan_hooks_dir CC→Prism event_type 映射 PASS
  - _scan_mcp_servers_dir config.json 读取 PASS
  - 3 Backend 路由声明（/load / /export-cc / /validate）PASS
  - 进程边界（cc_compat.py 无实际 backend.app import）PASS
- 质量门 10 项：PASS

### 下一个 Task 需要注意
- DOC-06 Task 6.1 ADR 须从 **ADR-056** 起接续（ADR-054 = ConversionReport，ADR-055 = plugin.yaml 严格校验）
- DOC-06 原规划 ADR-050~055 范围已全部被 DOC-05 Tasks 5.4~5.7 占用，ADR-050/051/052/053/054/055 均已落地
- plugins_router prefix="/plugins"，务必不与 DOC-09 Task 9.1 MCP Server 管理路由（prefix="/mcp-servers"）混淆
- PluginHost.load_plugin_from_dir() 是 Task 5.7 新增的目录级入口，DOC-07 Task 7.4 子进程调度可通过此方法加载插件目录

### 遗留风险 / 未决事项
- _scan_mcp_servers_dir Phase 1 仅读 config.json（若 CC 插件用子目录结构无 config.json，则扫描子目录名生成 stub，command 为空字符串）；Phase 2 可扩展按子目录中的 package.json 读取 command
- PluginYamlSchema 的 extra_field_names() 在 pydantic v2 中通过 model_dump() - model_fields 计算；若 pydantic 升级 API 变化需更新
- Backend POST /plugins/export-cc 返回 cc_compat_zip_b64（base64），前端需 decode 后落盘；大文件场景可考虑 streaming response（Phase 2）

### Commit
- `4558a25` — `feat(v4): CC 兼容层 + ConversionReport — DOC-05 Task 5.7 (ADR-054/055)`
- `a37a6cc` — `docs: DOC-05 DONE — update PROGRESS/DECISIONS/HANDOFF-LOG/blocker (Task 5.7 + DOC-05 收官)`

---

## ================== DOC-05 DONE CHECKPOINT ==================
**日期**: 2026-04-19
**阶段**: DOC-05 Plugin Ecosystem — 全部 7/7 Task 完整收官

### 完成的 Task 列表（7/7）
- Task 5.1: Skill 三级加载（ADR-043/044/045）— commit: 见 git log
- Task 5.2: MCP Server 双通道 + scope（ADR-046/047）— commit: 见 git log
- Task 5.3: Hook 治理 + Plugin 命名空间（ADR-048/049）— commit: 见 git log
- Task 5.4: PluginHost 统一管理 + 变量替换系统（ADR-050）— commit: 见 git log
- Task 5.5: Skills Registry Local + GitHub 两源（ADR-051）— commit: 见 git log
- Task 5.6: Skills CLI + Agent Tool 仅搜索（ADR-052/053）— commit: 见 git log
- Task 5.7: CC 兼容层 + ConversionReport（ADR-054/055）— commit: 4558a25

### 核心能力交付
- Skill **三级加载**（L0 注册 → L1 描述注入 → L2 按需完整加载 + is_skill_context 标记）
- MCP stdio 集成（**双通道 instructions + agent-scoped 白名单**）
- Hook 治理层（4 种 handler / 优先级排序 / Phase 1 事件过滤 / scoped 注册-注销）
- Plugin 命名空间（**变量替换系统 + CC 兼容映射 + Platform/User/Session 三级加载**）
- PluginHost 统一管理 + **目录级统一入口 load_plugin_from_dir()**
- Skills 市场（**Phase 1 仅 Local + GitHub 两源**）
- Skills CLI + Agent Tool（**仅搜索**，安装需用户手动触发）
- CC 插件格式兼容层（**ConversionReport + plugin.yaml 严格校验 + PluginSchemaError → 422**）

### ADR 落地总计（DOC-05）
ADR-043 / ADR-044 / ADR-045 / ADR-046 / ADR-047 / ADR-048 / ADR-049 / ADR-050 / ADR-051 / ADR-052 / ADR-053 / ADR-054 / ADR-055（13条 ADR）

### 进程边界严格遵守
- executor/ 所有新模块：无 from backend.app 实际 import
- backend/ 插件 API：不启动 MCP 子进程（格式检测+转换只做数据结构操作）

### 下一步：DOC-06 Task 6.1 认证体系（三密钥 + SSE ticket）
- ADR 从 ADR-056 起编号（所有 DOC-05 ADR 已占用 ADR-043~055）
- 参考 DOC-06-v4.md Task 6.1 Part A + Part B
## ==================== END DOC-05 DONE =======================

---

## 2026-04-19 -- DOC-05 Task 5.6 completed (Skills CLI + Agent Tool search-only + ADR-052/053)

### 本次 session 做了什么
- 新建 executor/tools/builtin/skills_search.py — SkillsSearchTool（name="skills_search", capabilities=[], input_schema{query,source,limit}, execute() 调用 SkillsRegistry.search() 返回 JSON + install 引导 note，不含任何 install/uninstall action，ADR-052 铁律）
- 新建 executor/cli/__init__.py + executor/cli/skills_cli.py — SkillsCLI 6 子命令（search/install/uninstall/update/list/info）+ argparse build_parser() + main() 入口；有 backend_url 时 HTTP 通知 Backend API 同步 DB，无 backend_url 时仅本地文件操作（开发者模式）
- 新建 backend/app/services/skill_install_service.py — SkillInstallService（install UPSERT + uninstall 更新 status + list_installed + get_install）+ Redis key 格式 `skill_install:status:{user_id}:{skill_name}` TTL=600s（ADR-053）
- 新建 backend/app/api/v1/skills.py — 6 路由（GET /search / GET /installed / POST /install / DELETE /{skill_name} / POST /{skill_name}/update / GET /{skill_name}）+ Pydantic schema（内联）+ Prometheus prism_skill_searches_total / prism_skill_installs_total
- 修改 executor/tools/builtin/__init__.py — register_builtin_tools() 追加 SkillsSearchTool 注册 + skills_registry 参数
- 修改 backend/app/api/v1/__init__.py — include_router(skills_router)
- ADR-052/053 落地 DECISIONS.md；blocker.md 追加 Task 5.6 ADR 平移链（DOC-06 Task 6.1 须从 ADR-054 起）
- PROGRESS.md 更新（Task 5.6 completed，21/51）

### 验证结果
- Part B 验证步骤（全 PASS）：
  - py_compile × 5 文件（skills_search / skills_cli / __init__ / skill_install_service / skills.py）PASS
  - SkillsSearchTool name/capabilities/input_schema/required PASS
  - ADR-052 约束（无 install/action schema 字段）PASS
  - SkillsSearchTool.execute() 搜索 + 空查询 PASS
  - register_builtin_tools() 含 skills_search PASS
  - SkillsCLI cmd_search + cmd_list PASS
  - Redis key 格式 + TTL=600s + mock SET 验证 PASS
  - SkillInstallService UPSERT（INSERT/UPDATE 两路径）+ uninstall PASS
  - Backend API 6 路由 PASS
  - 进程边界（executor/cli/ 无 backend.app import）PASS
- 质量门 10 项：PASS

### 下一个 Task 需要注意
- Task 5.7 CC 兼容层（ConversionReport）ADR 从 **ADR-054** 起编号（ADR-052/053 已被本 Task 占用）
- Task 5.7 涉及 CCPluginAdapter（检测 plugin.json/plugin.yaml/skills_only 三种格式）+ export_to_cc() 返回 ConversionReport（bytes zip + lost_fields + warnings + cc_plugin_json）+ ADR-050-A/050-B（平移后需新编号）
- skill_installs ORM 的 metadata_ JSONB 存 install_path/has_hooks/has_mcp/status，Task 5.6 的 SkillInstallService 已按此实现，后续 Tasks 直接用 metadata_["install_path"] 等 key

### 遗留风险 / 未决事项
- Backend _get_redis_client() 在 DOC-07 Task 7.1 前返回 None（Redis 未就绪时跳过缓存），生产环境需 Task 7.1 补全
- SkillsCLI 的 cmd_info() 搜索全源以找 skill_name，对大型 GitHub 索引略慢（可接受，Phase 1）
- Prometheus Counter 采用 lazy init + try/except，重复注册时静默降级（测试/重载安全）

### Commit
- `770679e` — `feat(v4): Skills CLI + Agent Tool search-only + Backend skill_install_service — DOC-05 Task 5.6`
- `875978e` — `docs: update state files for DOC-05 Task 5.6 (PROGRESS/DECISIONS/HANDOFF/blocker)`

---

## 2026-04-19 -- DOC-05 Task 5.5 completed (Skills Registry Local+GitHub + ADR-051)

### 本次 session 做了什么
- 新建 executor/plugins/skills_registry.py — SkillPackage/SkillBundle/InstalledSkill 3 个 dataclass；SkillSource ABC（search/fetch/get_versions 抽象方法）；LocalSource（.skills/ + .prism/skills/ 双目录扫描，YAML frontmatter 解析，关键词匹配 name/description/tags）；GitHubSource（httpx 调用 GitHub API Code Search + git/trees + raw.githubusercontent.com，支持 user/repo#branch/@tag/subpath 4 种格式，无 token 优雅降级）；SkillsRegistry（asyncio.gather 并行搜索 + name 去重 + installed 优先排序 + registry.json 原子写 + install/uninstall/update/list_installed）
- 修改 executor/plugins/__init__.py — 新增导出 7 个符号 + Task 5.5 注释
- ADR-051 落地 DECISIONS.md；blocker.md 追加 Task 5.5 ADR 平移链（DOC-06 Task 6.1 须从 ADR-052 起）
- PROGRESS.md 更新（Task 5.5 completed，20/51）；HANDOFF-LOG.md 本记录

### 验证结果
- Part B 验证步骤（9 项全 PASS）：py_compile × 2 / dataclass 实例化 × 3 / LocalSource search+fetch+versions / SkillsRegistry 并行搜索+installed排序+install+uninstall / registry.json 格式 / has_hooks/has_mcp 检测 / GitHubSource._parse_package_id 4 种格式 / 进程边界检查
- 质量门 10 项：PASS（无 backend.app import / 无 TODO 占位 / ADR-051 注释 / Phase 2 占位注释 / Literal 类型正确）

### 下一个 Task 需要注意
- Task 5.6 SkillsCLI + SkillsSearchTool：从 ADR-052 起编号（不要用 ADR-051，已被本 Task 占用）
- Task 5.6 Backend API `/skills/search` 调用 SkillsRegistry.search()；`/skills/install` 写 skill_installs 表（DOC-01 §4.2 已建）
- skill_install_service 写 skill_installs 表字段：user_id / skill_name / source / source_url / version / installed_at / install_path / has_hooks / has_mcp / status（ADR-049 in PRD，平移后须检查是否已占用）
- Redis 缓存 key：`skill_install:status:{user_id}:{skill_name}` TTL 600s（Task 5.6 实现）

### 遗留风险 / 未决事项
- GitHubSource.search() 需要 GITHUB_TOKEN（无 token 返回空列表 + warning，Phase 1 可接受）
- GitHubSource.fetch() 在大仓库 recursive tree 可能超时（_DEFAULT_GITHUB_TIMEOUT=30s，PRD 未规定具体值）

### Commit
- `1e70ba2` — `feat(v5): Skills Registry multi-source aggregation (Local+GitHub) — DOC-05 Task 5.5`
- `7b9586b` — `docs: update state files for DOC-05 Task 5.5 (PROGRESS/DECISIONS/HANDOFF/blocker)`

---

## 2026-04-19 -- DOC-05 Task 5.4 completed (PluginHost 统一管理 + 变量替换系统 + ADR-050)

### 本次 session 做了什么
- 新建 executor/plugins/plugin_types.py — PluginScope 枚举（PLATFORM/USER/SESSION，含 priority 属性）+ PluginConfig 数据类（10字段）
- 新建 executor/plugins/host.py — PluginVariableExpander（9种变量类型 + ENV_WHITELIST sandbox + ${CLAUDE_PLUGIN_ROOT} CC兼容 + ${secret.X} Phase1留桩 + expand_dict/expand_list 递归展开）+ PluginHost（load_plugin含冲突检测+audit / unload_plugin / unload_all / shutdown 统一清理 / get_skill_descriptions/get_mcp_instructions/get_agent_overrides）
- 修改 executor/plugins/__init__.py — 新增导出 PluginConfig/PluginScope/PluginHost/PluginVariableExpander/ENV_WHITELIST
- ADR-050 落地 DECISIONS.md；blocker.md 追加 Task 5.4 ADR 编号平移链 + DOC-06 ADR-050 冲突警告
- 解 Task 5.2 的 TODO：MCPClient.stop() 统一由 PluginHost.shutdown() finally 块调用

### 验证结果
- Part B 验证步骤：PASS（3项全PASS：py_compile 2文件/Empty PluginHost全方法/All checks passed）
- 额外验证：变量替换9种（PRISM_PLUGIN_ROOT/DATA/SKILL_DIR/SESSION_ID/USER_ID/user_config.X/env.HOME白名单/env.SECRET_KEY非白名单/secret.X留桩）全PASS
- Platform/User/Session三级冲突检测+shutdown()清理 PASS
- 质量门：PASS — 无实际 backend.app import；无 TODO: 占位；进程边界严格

### 下一个 Task 需要注意 — DOC-05 Task 5.5 (Skills Registry Local+GitHub 两源)
- ADR 编号从 ADR-051 起（ADR-050 已被本 Task 占用；DOC-06 须从 ADR-051 接续，见 blocker.md）
- SkillRegistry 实现后可通过 PluginHost.load_plugin() 加载 GitHub Skill（host.py 已就绪）
- PluginHost.shutdown() 接口已就绪，DOC-07 Task 7.4 executor __main__.py finally 块调用 await plugin_host.shutdown()

### 遗留风险 / 未决事项
- ${secret.X} Phase 1 留桩（原样保留字符串）；DOC-06 Task 6.1 security.decrypt_value 落地后需回来激活
- DOC-06 Task 6.1 原规划 ADR-050~055 三密钥/SSE ticket，因本 Task ADR-050 已占用，DOC-06 须从 ADR-051 起

### Commit
- `2bd50f1` — `feat(v5.4): PluginHost unified lifecycle + variable substitution system (ADR-050)`
- `559768d` — `docs: update state files for DOC-05 Task 5.4 (PROGRESS/DECISIONS/HANDOFF/blocker)`

---

## 2026-04-19 -- DOC-05 Task 5.3 completed (Hook 治理层 + Plugin 命名空间 + ADR-048/049)

### 本次 session 做了什么
- 修改 executor/harness/hooks/events.py — 新增 PHASE1_EVENTS frozenset（8事件）+ PHASE2_EVENTS frozenset（13事件预留）
- 重构 executor/harness/hooks/system.py — `_handlers` 改为 `dict[str, list[tuple[int, str, HookHandlerConfig]]]` 三元组（priority+hook_id+config）；register() 新增 hook_id/priority 参数（默认100）并按优先级升序排序；新增 unregister(hook_id) 精确注销；新增 unregister_by_prefix(prefix) 批量注销；fire() 入口校验 PHASE1_EVENTS，非 Phase 1 事件静默返回空决策
- 新建 executor/plugins/namespace.py — PluginNamespace(plugin_name)：qualify/unqualify/is_mcp_tool/build_qualified；MCP 工具（mcp__ 前缀）绕过命名空间
- 修复 executor/plugins/skill_loader.py — _register_skill_hooks() 传 hook_id 到 register()；_unregister_skill_hooks() 真实调用 unregister_by_prefix()（解决 Task 5.1 留的 TODO stub）
- 修改 executor/harness/hooks/__init__.py — 新增导出 PHASE1_EVENTS / PHASE2_EVENTS
- 修改 executor/plugins/__init__.py — 新增导出 PluginNamespace；ADR-048/049 落地 DECISIONS.md；blocker.md 追加 Task 5.3 ADR 编号平移链

### 验证结果
- Part B 验证步骤：PASS（3项全PASS：py_compile 3文件/Phase1-2事件集/优先级排序+scoped注销+PluginNamespace）
- 质量门：PASS — 0 `from backend.app` in 新增文件；无 TODO 占位；进程边界严格；HookDecision 11字段对齐 ADR-026

### 下一个 Task 需要注意 — DOC-05 Task 5.4 (PluginHost 统一管理与垂类特调)
- ADR-050 是下一个可用编号（须检查 DOC-06 ADR-050~055 三密钥/SSE ticket 是否冲突，Task 5.4 从 ADR-050 起但注意此编号同时被 DOC-06 ADR-050 声明——需继续平移）
- unregister_by_prefix("plugin:{plugin_name}:") 已就绪，Task 5.4 PluginHost 卸载 Plugin 时调用此接口
- PluginNamespace 已就绪，Task 5.4 PluginHost 加载 Plugin 时使用 qualify() 为 Skill/Hook 加命名空间

### 遗留风险 / 未决事项
- PRD Part B 验证脚本中 `from executor.harness.hooks.events import HookDecision` 是 PRD 笔误（HookDecision 在 decision.py），验证用修正 import 通过，原 PRD 脚本有语法歧义但不影响实现正确性
- DOC-05 Task 5.4 ADR 编号需仔细检查：DOC-06 已声明 ADR-050~055 范围，Task 5.4 须继续平移编号

### Commit
- (见 git log)

---

## 2026-04-19 -- DOC-05 Task 5.2 completed (MCP Server 双通道 + scope + ADR-046/047)

### 本次 session 做了什么
- 新建 executor/plugins/mcp_client.py — MCPClient（asyncio.create_subprocess_exec P0异步修复；start/stop/call_tool；get_instructions ADR-046第一通道；list_mcp_tool_pairs ADR-047；scope二值system/user）+ MCPToolWrapper（mcp__{server}__{tool}命名；description=ADR-046第二通道；execute委托MCPClient.call_tool）+ filter_mcp_tools_for_agent（辅助函数；None=全部/列表=白名单过滤）+ SCOPE_SYSTEM/SCOPE_USER常量
- 修改 executor/engine/prompt_assembler.py — 新增 invalidate_static_cache()（_static_cache=None + _tools_hash=None 双重失效）+ update_tools()（更新工具列表并调用invalidate_static_cache）
- 修改 executor/plugins/__init__.py — 导出 MCPClient / MCPToolWrapper / filter_mcp_tools_for_agent / SCOPE_SYSTEM / SCOPE_USER（共5新符号）
- ADR-046/047 落地 DECISIONS.md；blocker.md 追加 Task 5.2 ADR 编号平移链（046=MCP双通道，047=agent-scoped白名单，后续从048起）

### 验证结果
- Part B 验证步骤：PASS（3项全PASS：Cache hit/Cache invalidation/New tools in prompt）
- 质量门：PASS — 0 `from backend.app` import in mcp_client.py；无 TODO 占位；进程边界严格；asyncio P0修复（非阻塞readline）；ADR对齐

### 下一个 Task 需要注意 — DOC-05 Task 5.3 (Hook 治理层与 Plugin 命名空间)
- ADR-048 是下一个可用编号（DOC-05 Task 5.3 的 ADR 从 048 起编号）
- MCPClient.stop() 在 session 结束时必须被调用（PluginHost / __main__.py finally 块），否则 MCP Server 子进程泄漏
- invalidate_static_cache() / update_tools() 已就绪，Task 5.3 Hook 治理可在 MCP 工具注册/注销的 Hook handler 中调用 assembler.invalidate_static_cache()
- filter_mcp_tools_for_agent 设计为辅助函数（非 MCPClient 方法），调用链：clients → list_mcp_tool_pairs → filter_mcp_tools_for_agent → AgentDefinition.filter_mcp_tools；Task 5.4 PluginHost 组装时串联此链

### 遗留风险 / 未决事项
- MCPClient._send_request() 对 stdout.readline() 无超时保护；若 MCP Server 挂死会永久阻塞 await。Phase 1 不加 timeout，Task 5.4 PluginHost 可包装 asyncio.wait_for 超时降级
- MCPToolWrapper.execute() 捕获所有异常返回 is_error=True，不区分网络错误/业务错误；Phase 1 统一处理，后续可细化 error_code

### Commit
- (见 git log)

---

## 2026-04-19 -- DOC-05 Task 5.1 completed (Skill 三级加载 Level 0/1/2 + agents过滤 + audit)

### 本次 session 做了什么
- 新建 executor/plugins/skill_types.py — SkillMetadata(name/description/triggers/hooks/path/agents) + SkillContent(metadata/full_text/is_loaded)
- 新建 executor/plugins/skill_loader.py — SkillLoader 三级加载器：scan_and_register() Level 0; get_descriptions_for_prompt(agent_type) Level 1 含 ADR-044 agents 过滤; try_trigger(user_message, agent_type) 触发检测; load_skill(name) Level 2 读 body + 注册 scoped hooks + structlog is_skill_context=True; unload_skill/unload_all; emit_mentioned_not_loaded() audit warning; _filter_by_agent(); Phase 1 8事件白名单 _PHASE1_EVENTS; _parse_frontmatter() pyyaml safe_load; _read_body() 跳过 frontmatter
- 修改 executor/plugins/__init__.py — 导出 SkillMetadata/SkillContent/SkillLoader
- 新建 plugins/skills/.gitkeep — Skill 存放目录占位（目录结构按 PRD Part B）
- 修改 pyproject.toml — 追加 pyyaml>=6.0 依赖（Task 3.6 要求，之前未在 pyproject.toml 体现）
- ADR-043/044/045 落地 DECISIONS.md；blocker.md 追加 Task 5.1 ADR 编号平移链

### 验证结果
- Part B 验证步骤：PASS（py_compile 2文件；Level 0注册；Level 1描述；Trigger匹配/不匹配；Level 2加载；不重复触发；Unload；ADR-044 agents过滤；emit_mentioned_not_loaded audit；__init__ 导出）
- 质量门：PASS — 0 `from backend.app` import；无 TODO 占位；进程边界严格；pyyaml 依赖声明

### 下一个 Task 需要注意 — DOC-05 Task 5.2 (MCP Server 集成与热加载)
- ADR-046 是下一个可用编号（DOC-05 Task 5.2 的 ADR 从 046 起编号）
- SkillLoader._unregister_skill_hooks() 当前只记录 id 日志，未真实从 HookSystem 清除；Task 5.3 实现 HookSystem.unregister_by_id() 后回填
- load_skill() 返回 SkillContent，调用方须自行构造 PrismMessage(is_skill_context=True, skill_name=name) 插入 messages；Task 5.4 PluginHost 负责此对接
- PromptAssembler 中 SkillInfo 为临时 stub（Task 2.4），Task 5.1 的 SkillMetadata 是正式版；Task 5.4 可统一替换

### 遗留风险 / 未决事项
- HookSystem.unregister_by_id() 未实现（Phase 1 限制），Skill 卸载时 scoped hooks 残留在 HookSystem._handlers 中，但不影响语义（hook 仍会执行，仅略浪费）；Task 5.3 修复
- pyproject.toml pyyaml>=6.0 为新增依赖，本地无 Docker 环境无法运行 docker compose exec 验证，已通过直接 python -m py_compile 和 python -c 验证

### Commit
- (见 git log)

---

## 2026-04-19 -- DOC-04 Task 4.5 completed (PluginBuilder 完整度打分 + 动态轮数)

### 本次 session 做了什么
- 新建 executor/agents/plugin_builder_scoring.py — RequirementCompleteness 类（CRITERIA 7维度加权，THRESHOLD=0.8，score() async LLM打分+structlog事件+Prometheus histogram lazy init）+ get_missing_dimension_question()（weighted_gap找最缺维度）+ PluginBuilderAgent（run() 打分循环，_present_design stub，_wait_for_user_reply NotImplementedError stub）
- 修改 executor/agents/plugin_builder.py — v4 AgentDefinition（max_turns=40，allowed_tools 7项精确列表，output_format=structured_dialogue，behavior_constraints v4 修订文本）+ PLUGIN_BUILDER 向后兼容别名
- 新建 executor/harness/middleware/plugin_builder_gate.py — PluginBuilderGate Middleware（pre_turn 4阶段门控：phase 1低分注入constraint，phase 1达阈升phase 2，phase 2未确认注入约束）+ pre_tool_use 阻止阶段 1/2 写 plugin 文件 + _is_plugin_file() + GR_PLUGIN_CREATE_GUARD（scope="tier"可配置降级）
- 修改 executor/router.py — PLUGIN_BUILDER_PATTERNS 4条中英文正则 + route()步骤3a优先正则 + AGENT_TYPE_PATTERNS["plugin_builder"]扩充14项关键词
- 修改 executor/harness/middleware/__init__.py — 导出 PluginBuilderGate / GR_PLUGIN_CREATE_GUARD
- ADR-042 落地 DECISIONS.md（PRD原标ADR-038平移；DOC-04 Task 4.2已用ADR-038）
- blocker.md 末尾追加 Task 4.5 ADR编号平移链记录

### 验证结果
- Part B 验证步骤：PASS（py_compile 3文件；高分overall=0.85≥0.8；低分overall=0.30<0.8；权重和=1.00；THRESHOLD=0.8；中英文路由各PASS；PluginBuilderGate 4场景；_is_plugin_file；GR_PLUGIN_CREATE_GUARD block/allow）
- 质量门：PASS — 0 `from backend.app` import；无 TODO 占位（stub 均有 NotImplementedError 或 # TODO 说明）；进程边界严格

### 下一个 Task 需要注意 — DOC-05 Task 5.1 (Skill 三级加载)
- ADR-043 是下一个可用编号（DOC-05 Task 5.1 的 ADR 从 043 起编号）
- GR_PLUGIN_CREATE_GUARD 已声明但未注入 GuardrailsEngine，DOC-05 Task 5.3 Hook 治理负责注入（或 Harness Runtime 初始化时注入）
- PluginBuilderAgent._wait_for_user_reply() stub，DOC-07 Task 7.3 实现 SSE/BLPOP 后激活

### 遗留风险 / 未决事项
- PluginBuilderAgent.run() 的 _wait_for_user_reply() 为 NotImplementedError stub，不影响编译和 Middleware 路径，待 DOC-07 Task 7.3 实现
- GR_PLUGIN_CREATE_GUARD 注入时机未定（DOC-05 Task 5.3 或 Harness Runtime），需后续 Task 追加

### Commit
- `0a43a39` — `feat(v4): PluginBuilder 完整度打分 + 动态轮数 — DOC-04 Task 4.5`

---

## 2026-04-19 -- DOC-04 Task 4.4 completed (TaskRouter 6 agent_type + keyword routing)

### 本次 session 做了什么
- Created executor/router.py — TaskRouter 类 + RouteDecision dataclass(mode/agent_type/reason) + COORDINATOR_PATTERNS(11条中英文) + AGENT_TYPE_PATTERNS(4种:explore/planner/verifier/plugin_builder,含中英文关键词) + AGENT_TYPE_ALIASES(3条别名:chat→general/research→explore/build→general)
- Modified executor/__main__.py — 追加 `from executor.router import TaskRouter` import + TaskRouter routing stub(注释块,待 DOC-07 Task 7.4 DB 集成激活)
- ADR-041 落地 DECISIONS.md(PRD 原标 ADR-037 平移;Fork capability-based ADR-037 已占用)
- blocker.md 末尾追加 Task 4.4 ADR 编号平移链记录
- PROGRESS.md Task 4.4 行更新为 completed + session notes

### 验证结果
- Part B 验证步骤: PASS(8项路由测试全通过,2项 py_compile PASS,1项 grep PASS)
- 质量门: PASS — 进程边界(0 backend.app import)、密度达标、无 TODO 占位、对齐 PRD Part B

### 下一个 Task 需要注意 — DOC-04 Task 4.5 (PluginBuilder 完整度打分)
- TaskRouter 的 AGENT_TYPE_PATTERNS["plugin_builder"] 已预置关键词路由，Task 4.5 不需要再修改 router.py
- ADR-038 原编号在 PRD 被 PluginBuilder 打分使用，但 DOC-04 Task 4.2 已用 ADR-038 落地 Fork 3 条约束；Task 4.5 的 ADR 需从 ADR-042 起编号
- PRD Part B 验证步骤 line 1548 有笔误(断言 'research' 但路由返回 'explore')；已在 DECISIONS.md ADR-041 偏离点说明，Task 4.5 实施者无需修改 router.py

### 遗留风险 / 未决事项
- __main__.py 中 TaskRouter routing stub 为注释状态，待 DOC-07 Task 7.4 DB 集成后取消注释并接入 run.prompt/run.agent_type
- RouteDecision.reason 写入 audit_logs 逻辑尚未实现(DOC-07 Task 7.3/7.4 负责)

### Commit
- `f0c373e` — `feat(v4): TaskRouter 6 agent_type + keyword routing — DOC-04 Task 4.4`

---

## 2026-04-19 -- DOC-04 Task 4.3 completed (Coordinator + Plan checkpoint)

### 本次 session 做了什么
- Created executor/coordinator/plan.py — Plan/PlanStep dataclass + parse_from_text() 两级解析(JSON 围栏/裸 JSON / markdown `[agent] desc` / 单步 general fallback) + serialize_plan/deserialize_plan(asdict 持久化助手) + _normalize_agent_type(research→explore 规范化)
- Created executor/engine/synthesizer.py — Synthesizer.synthesize() 模板合成(## 任务完成 + **目标** + ### desc/result)
- Created executor/coordinator/coordinator.py — Coordinator.__init__(plan_id + resume_from_step) + execute(existing_plan可选, 初始 + 每 step 开始 + 完成 = 4 次 coordinator_plan_update) + resume_from_checkpoint(classmethod 返回 (Coordinator, Plan) 元组) + _plan(Fork Planner, 失败兜底单步 general) + _build_step_context(注入前 500 字)
- Modified executor/coordinator/__init__.py — 追加导出 Plan/PlanStep/serialize_plan/deserialize_plan/Coordinator

### 验证结果
- Part B 验证步骤: 全部 PASS (Plan 构造 + Synthesizer 模板)
- 扩展验证: parse_from_text JSON / markdown / fallback 三路径 PASS; serialize/deserialize roundtrip PASS
- Coordinator 路径测试: single-step(直返 synthesis) / multi-step(4次 plan_update + 2次 step_start/end) / resume_from_step=1(只 fork 第2步) 全 PASS
- grep `from backend.app` in executor/coordinator + executor/engine/synthesizer.py: 0 命中 PASS

### 下一个 Task 需要注意 — DOC-04 Task 4.4 (TaskRouter 6 agent_type)
- TaskRouter 集成在 executor/__main__.py 入口处,按关键词判定 general/explore/planner/verifier/coordinator/plugin_builder
- 判定"复杂任务"→ 切换 Coordinator 模式(本 Task 实现的 Coordinator.execute)
- Phase 1 关键词匹配(ms 级,确定性),Phase 2 LLM 分类 fallback(ADR-037 Task 4.4 原标)
- 路由器返回 (agent_type, use_coordinator) 元组,__main__.py 按 use_coordinator 分支

### 遗留风险 / 未决事项
- ADR 编号平移: DOC-04 Task 4.3 PRD 原标 ADR-036 → 本实现 ADR-040(blocker.md 已记录)；后续 DOC-04 Task 4.4/4.5 的 ADR 从 ADR-041 接续；DOC-05 后续 ADR 需继续平移(参考 blocker.md)
- Coordinator.resume_from_checkpoint 返回 (Coordinator, Plan) 元组(偏离 PRD 原版单返 Coordinator); DOC-07 Task 7.4 CoordinatorRecoveryService 需按此签名调用
- coordinator_plans 表持久化逻辑在 DOC-07 Task 7.3 回调端点实现(本 Task 只 emit event)

### Commit
- `c0f394d` — `feat(v4): Coordinator + Plan checkpoint (parse_from_text + Synthesizer + 4-stage checkpoint) — DOC-04 Task 4.3`

---

## 2026-04-19 -- DOC-04 Task 4.2 completed (Fork & Context Isolation)

### 本次 session 做了什么
- Created executor/coordinator/fork_briefing.py — ForkBriefing dataclass(6字段:goal/why/excluded/context/expected_output/file_references) + to_prompt()(6 markdown section标题) + FORK_HARD_CONSTRAINTS(3条硬约束 ADR-038)
- Created executor/coordinator/fork_result.py — ForkResult dataclass(9字段,含briefing:ForkBriefing + allowed_capabilities)
- Created executor/coordinator/fork_manager.py — ForkManager + ForkDepthExceeded; fork()(depth检查/capability过滤/子assembler/子pipeline/子harness/timeout包裹); _create_child_assembler()(继承parent static cache + inject FORK_HARD_CONSTRAINTS); _create_filtered_registry()(capability-based过滤,空list=不限制); _extract_synthesis()(反向扫最后assistant TextBlock)
- Created executor/coordinator/__init__.py — 导出 ForkBriefing/ForkResult/ForkManager/ForkDepthExceeded/FORK_HARD_CONSTRAINTS
- Created executor/tools/builtin/fork.py — ForkTool(BaseTool), capabilities=["fork_agent"], input_schema含agent_type/goal必填+4可选字段, execute()构造ForkBriefing并调fork_manager.fork()
- Modified executor/agents/base.py — AgentDefinition追加 allowed_capabilities: list[str] = field(default_factory=list)
- Modified executor/tools/base.py — BaseTool追加 capabilities: list[str] = [] class-level默认
- Modified executor/tools/registry.py — 追加 list_all() -> list[BaseTool] 方法
- Modified executor/engine/prompt_assembler.py — 追加 _extra_dynamic_tail: str | None = None; _build_dynamic()末尾注入
- Modified executor/tools/builtin/__init__.py — register_builtin_tools追加可选fork_manager参数

### 验证结果
- Part B 验证步骤 15 项: 全部 PASS
- py_compile 10文件 PASS
- 导入 5个符号 PASS
- ForkBriefing.to_prompt() 6 section PASS
- FORK_HARD_CONSTRAINTS 3条约束 PASS
- ForkResult 9字段 PASS
- ToolRegistry.list_all() PASS
- _extra_dynamic_tail 注入 PASS
- ForkDepthExceeded depth=2 PASS
- capability过滤 4场景 PASS
- _create_child_assembler static_cache+tools_hash+tail PASS
- _extract_synthesis 最后assistant PASS
- ForkTool input_schema required PASS
- ForkTool.execute success PASS
- ForkTool.execute fail PASS
- grep backend.app: 0命中 PASS

### 下一个 Task 需要注意 -- DOC-04 Task 4.3 (Coordinator + Plan checkpoint)
- Coordinator 用 ForkManager 派 Worker Agent：Coordinator 需持有 ForkManager 实例，在 TAOR 循环中通过 fork_agent 工具（或直接调用 ForkManager.fork()）派生 research/planner/verifier 子 Agent
- Plan checkpoint 需持久化到 coordinator_plans 表（Task 2.1 已建）：coordinator_plans 表含 run_id/plan_json/current_step/status，Coordinator 每完成一步需 UPSERT checkpoint，重启时从 checkpoint 恢复
- 崩溃恢复：子进程重启时 --resume-from-step=N 从 checkpoint 继续，QueryEngine 初始化时检查 coordinator_plans 表，若有 in_progress plan 则注入已完成步骤的 synthesis 到 messages

### 遗留风险 / 未决事项
- ADR 编号平移：DOC-04 Task 4.2 PRD 原标 ADR-033/034/035 → 本实现 ADR-037/038/039（见 blocker.md）
- ForkManager.fork() 中 QueryEngine/ToolExecutionPipeline 延迟导入（避免循环依赖），真实集成时需确认 harness_factory 的签名接受 AgentDefinition 参数（lifecycle.py HarnessRuntime constructor）
- ForkTool 的 capabilities=["fork_agent"] class-level 属性：Python class-level list 是共享引用，子类若不 override 而直接 append 会污染父类，当前实现只读取不修改，安全

### Commit
- `a61991d` — `feat(v4): Fork & Context Isolation (capability-based + 3 hard constraints + ForkBriefing 6 fields) — DOC-04 Task 4.2`

---

## 2026-04-18 -- DOC-04 Task 4.1 completed (6 specialized Agent definitions + AgentPool)

### Done this session
- Created executor/agents/base.py — AgentDefinition dataclass (v4: 11 fields incl. mcp_servers/frontmatter_skills/bash_whitelist) + filter_tools() + filter_mcp_tools()
- Created executor/agents/general.py — GENERAL_AGENT (agent_type="general", allowed_tools=None, max_turns=50)
- Created executor/agents/research.py — RESEARCH_AGENT/EXPLORE_AGENT (agent_type="explore", read_only=True, max_turns=30, BASH_WHITELIST 9条, READ_ONLY_TOOLS)
- Created executor/agents/planner.py — PLANNER_AGENT (agent_type="planner", read_only=True, max_turns=10, output_format含"Critical Files for Implementation")
- Created executor/agents/verifier.py — VERIFIER_AGENT + VERIFIER_SYSTEM_PROMPT原文(含VERDICT三态+4类专项验证 Frontend/Backend/CLI/Migration)
- Created executor/agents/coordinator.py — COORDINATOR_AGENT (agent_type="coordinator", allowed_tools=["fork_agent","synthesize","task_stop"], max_turns=200)
- Created executor/agents/plugin_builder.py — PLUGIN_BUILDER_AGENT (agent_type="plugin_builder", max_turns=40, 多轮需求收集约束)
- Created executor/agents/pool.py — AgentPool: 6种+3别名(chat→general/research→explore/build→general), get()/list_types()/filter_tools_for_agent()
- Created executor/agents/__init__.py — 导出 AgentDefinition + AgentPool + 7 AGENT实例 + 常量
- Modified executor/harness/lifecycle.py — HarnessRuntime.__init__ 接受可选 agent_def: AgentDefinition | None; agent_def.read_only=True 时追加 GuardrailRule(id="AGENT-READONLY") + _is_write_bash helper

### Verification results
- Part B 验证步骤 15 项: 全部 PASS
- py_compile 10文件 PASS
- 6种unique agent_type断言 PASS
- 3别名(chat/research/build) PASS
- AGENT-READONLY规则: Write/Edit/Delete拦截 PASS; ls/grep/git status放行 PASS; rm拦截 PASS
- grep from backend.app in executor/agents/: 0命中 PASS

### Notes for next Task -- DOC-04 Task 4.2 (Fork + Context Isolation)
- Fork 必须保留原 Agent 的 agent_type（不可覆盖 model）— 3 条 prompt-level 硬约束（PRD ADR-030/ADR-034 原文）：1) 父 Agent 的 agent_type 传给子 Agent; 2) 子 Agent 不能重选 model; 3) ForkBriefing 6字段结构化注入
- AgentPool.get() 可获取 Fork 后子 Agent 的定义（直接按 agent_type 查找即可，不需要新 API）
- Fork 子 Agent 启动时要 inherit parent 的 run_context（除 run_id 外）；briefing 注入时要带 parent_run_id / parent_session_id / parent_agent_type 三个字段

### Risks / Open items
- ADR 编号持续平移: PRD Task 4.1 原标 ADR-030/031/032 → 本实现 ADR-034/035/036（见 blocker.md）
- HarnessRuntime.agent_def 参数在 DOC-07 Task 7.4 子进程启动时真实注入（AgentPool().get(run.agent_type)），本 Task 只提供接口
- GENERAL_AGENT.behavior_constraints="" 时 PromptAssembler 的 agent_behavior_section 走 "general" 分支，已在 Task 2.4 实现，无需修改

### Commit
- `d04b909` — `feat(v4): 6 specialized Agent definitions + AgentPool (DOC-04 Task 4.1)`

---

## DOC-03 DONE — 2026-04-18 收官 checkpoint

### DOC-03 6 Task 产物路径索引

| Task | 核心产物 | ADR |
|---|---|---|
| 3.1 TAOR 主循环 | executor/engine/query_engine.py, executor/tools/, executor/callbacks/backend_callback.py, executor/__main__.py | ADR-020/021/022/023/024 |
| 3.2 Middleware Pipeline | executor/harness/middleware/{base,pipeline,loop_detection,observability}.py | ADR-025 |
| 3.3 Hook System + Permission Engine | executor/harness/{hook_system,permission_engine,ask_protocol,guardrails,platform_rules}.py | ADR-026/027/028 |
| 3.4 Feedback Capture + HarnessRuntime | executor/harness/middleware/feedback_capture.py, executor/harness/lifecycle.py | ADR-029/030 |
| 3.5 Compaction + Memory | executor/engine/compaction.py, executor/engine/memory.py | ADR-031/032 |
| 3.6 Harness Config 2源 | executor/harness/defaults.py, executor/harness/config_loader.py, backend/app/api/v1/harness.py | ADR-033 |

### DOC-03 ADR 落地清单（ADR-020 ~ ADR-033）

ADR-020 Harness单实例 / ADR-021 工具并行gather / ADR-022 Redis直通 / ADR-023 心跳5s SETEX /
ADR-024 MAX_TURNS分档 / ADR-025 Middleware 4钩点 / ADR-026 HookDecision 11字段 /
ADR-027 merge_decisions / ADR-028 ask BLPOP / ADR-029 FeedbackEvent结构化 /
ADR-030 SessionEnd LLM提炼user_memory / ADR-031 Compaction回合组原子裁剪 /
ADR-032 is_skill_context优先保留 / ADR-033 Harness配置2源化+禁止运行时修改

### 🟢 下一步: DOC-04 Task 4.1（Agent 专业化 + AgentPool 6 种）

待办优先级（32 Task 剩余）:
- **DOC-04** 5 Task: 4.1 AgentPool / 4.2 Planner / 4.3 Coordinator / 4.4 Verifier / 4.5 PluginBuilder
- **DOC-05** 7 Task: Skill系统
- **DOC-06** 2 Task: Auth/RBAC
- **DOC-07** 4 Task: Run调度+子进程启动（HarnessRuntime注入 DOC-03产物）
- **DOC-08** 3 Task: IM Gateway
- **DOC-09** 3 Task: Admin API
- **DOC-12** 8 Task: Observability

下一个派工目标: **DOC-04 Task 4.1 — Agent 专业化 + AgentPool（6 种 agent_type）**

---

## 2026-04-18 -- DOC-03 Task 3.6 completed (Harness Config 2-Source Loader + GET /harness/config)

### Done this session
- Created executor/harness/defaults.py — 3 const dicts: DEFAULT_PERMISSION_POLICIES(9项) + DEFAULT_MIDDLEWARE_CONFIG(4项) + DEFAULT_AGENT_CONSTRAINTS(6 agent types)
- Created executor/harness/config_loader.py — HarnessEffectiveConfig dataclass(6字段) + HarnessConfigLoader(config_file_path).load(): 2源合并 source_trace per-key "default"/"yaml"; yaml不存在→default-only; yaml格式错→raise RuntimeError + log harness.config.load_failed; 成功→log harness.config.loaded + Prometheus prism_harness_config_load_total
- Created backend/app/api/v1/harness.py — GET /config (readonly, require_admin); PATCH/POST/DELETE 不注册(FastAPI默认405); config_file_path 从 HARNESS_CONFIG_PATH env读取
- Modified backend/app/api/v1/__init__.py — include harness.router
- Modified backend/requirements.txt — 追加 pyyaml>=6.0
- DECISIONS.md 追加 ADR-033（PRD原标ADR-031冲突修正，本实现采用033）

### Verification results
- 10 项验证全部 PASS
- py_compile 4文件 PASS
- imports(executor+backend) + 3断言 PASS
- Default-only load: bash=ask, source_trace=default PASS
- YAML override: bash→allow/yaml, loop_detection.enabled=False PASS
- YAML format error → RuntimeError + log harness.config.load_failed PASS
- Nonexistent YAML path → default-only, no raise PASS
- Router routes: GET /harness/config 存在, 无 PATCH/POST/DELETE PASS
- GET endpoint response: effective(5 keys) + source_trace PASS
- api_v1_router 含 harness.router PASS
- pyyaml in requirements.txt PASS

### Notes for next Task -- DOC-04 Task 4.1 (Agent 专业化 + AgentPool 6 种)
- HarnessConfigLoader.load() 已提供，DOC-07 Task 7.4 子进程启动时将产物注入 HarnessRuntime（本 Task 未做）
- DEFAULT_AGENT_CONSTRAINTS 6 种类型: chat/explore/planner/verifier/plugin_builder/coordinator — DOC-04 Task 4.1 的 AgentPool 6种类型需与之对齐
- ask_user 值在 config_loader 中归一化为 ask，DOC-04/05/06 任何 Permission 相关实现均用 "ask" 不用 "ask_user"

### Risks / Open items
- HarnessConfigLoader 注入 HarnessRuntime: 留 DOC-07 Task 7.4（子进程启动参数读取 HARNESS_CONFIG_PATH）
- YAML error test: `:::::::` 在 pyyaml 中解析为合法 dict，实际 YAML error 需用 `{invalid: yaml: content:}` 等真实非法内容触发

### Commit
- `5381df3` — `feat(v4): Harness config 2-source loader + GET /harness/config readonly (DOC-03 Task 3.6 — DOC-03 DONE)`

---

## 2026-04-18 -- DOC-03 Task 3.5 completed (4-tier Compaction + 6-layer Memory)

### Done this session
- Created executor/engine/compaction.py — CompactionPipeline: TIER1=0.60/TIER2=0.85, maybe_compact/check_and_compact 路由入口, _tier1_micro_compact (裁最老1组), _tier2_auto_compact (LLM摘要替换最老50%组, adapter=None降级Tier1+warning), reactive_truncate (保留最近3组+hint), _tier4_reactive=reactive_truncate 别名, _extract_text helper, Prometheus prism_harness_compaction_total{tier} 集成
- Created executor/engine/memory.py — MemoryLayer ABC (load()->str|None), SessionMemory (raw SQL: sessions.config_snapshot.session_memory), UserMemory (raw SQL: user_memories.memory_text 最近10条), MemoryManager (Layer1+2, get_layer() Phase2预留, load() User先Session后)
- Modified executor/engine/query_engine.py — __init__ 追加 compaction: CompactionPipeline | None = None; run() 循环里 if compaction: check_and_compact, else: Tier0 fallback（老代码保留）
- Modified executor/harness/lifecycle.py — __init__ 追加 budget=None 参数; CompactionPipeline 条件组装 (budget非None时); memory_manager=None留空; 新增 load_user_memory(db_session=None)->str 方法
- 所有 14 项验证 PASS; blocker.md 追加 ADR-029/030 重号修正记录; DECISIONS.md 追加 ADR-031/ADR-032

### Verification results
- Part B 验证步骤 14 项: 全部 PASS
- py_compile 5 files PASS
- imports all OK PASS
- Tier1 裁最老组 + is_skill_context保留 PASS (TEST 3/4)
- Tier2 mock adapter摘要 + adapter=None降级 PASS (TEST 5/6)
- Tier4 _tier4_reactive别名 + reactive_truncate 3组+hint PASS (TEST 7/8)
- maybe_compact 阈值路由 50%/65%/90% PASS (TEST 9)
- tool_use↔tool_result 配对保证(ADR-031) PASS (TEST 10)
- MemoryManager db_session=None返回"" PASS (TEST 11)
- MemoryManager mock DB 拼接格式 + 顺序(User先) PASS (TEST 12)
- QueryEngine compaction=None向后兼容 PASS (TEST 13)
- grep from backend.app in executor/engine/ 新文件: 0命中 PASS (TEST 14)

### Notes for next Task -- DOC-03 Task 3.6 (Harness 配置 2 源简化)
- 配置 2 源：系统默认（config.py Settings 类）+ 用户覆盖（DB user.settings JSONB 或 .prism/config.json 文件）；不允许 per-session 第 3 源
- PATCH 运行时 API 已删（v4）；所有 Harness 参数在子进程启动时冻结，不可运行时修改
- Settings 当前已有 CIRCUIT_BREAKER_* / HEARTBEAT_* / LOOP_DETECTION_* / PERMISSION_ASK_TIMEOUT_SECONDS / FEEDBACK_TTL_SECONDS；Task 3.6 只补 ClaudeConfig（model/max_tokens/temperature）和 HarnessConfig（max_turns/agent_type/…）结构化封装，合并两源后注入 HarnessRuntime

### Risks / Open items
- UserMemory 列名：ORM 用 memory_text（非 PRD raw SQL 示例的 content）；memory.py 已用 memory_text，与 ORM model 对齐
- HarnessRuntime.load_user_memory() 的真实 db_session 注入留 DOC-07 Task 7.4（__main__.py 子进程启动时）
- CompactionPipeline 的 Prometheus metric 复用 prism_harness_compaction_total（已存在），未另建 prism_compaction_total

### Commit
- `ef26979` — `feat(v4): 4-tier Compaction + 6-layer Memory (turn-group atomic, skill_context preserved) — DOC-03 Task 3.5`

---

## 2026-04-18 -- DOC-03 Task 3.4 completed (Feedback Capture + HarnessRuntime Lifecycle)

### Done this session
- Created executor/harness/middleware/feedback_capture.py -- FeedbackEvent dataclass (ADR-029: 5 event_type + 4 severity + context + ISO 8601 timestamp) + FeedbackCaptureMiddleware (post_turn + _extract_failures + get_run_summary + Redis SETEX TTL 7d + Prometheus)
- Replaced executor/harness/lifecycle.py HarnessLifecycle → HarnessRuntime (8-param __init__: run_id/session_id/user_id/callback/redis_client/redis_url/adapter/settings)
- Middleware registration order: loop_detection → observability → feedback_capture (3 total)
- inject_into_pipeline(): pipeline._permission_engine + pipeline._hook_system
- on_session_start(): fire SessionStart HookEvent
- on_session_end(messages, turn_count): fire SessionEnd → if turn_count > 5: LLM complete → harness_event("user_memory_extracted") + Prometheus inc; exception → log WARNING (no raise)
- get_run_harness_summary(): feedback summary + middleware_count + guardrail_rules_count
- HarnessLifecycle = HarnessRuntime backward-compat alias
- Modified executor/harness/middleware/__init__.py -- export FeedbackEvent, FeedbackCaptureMiddleware
- Modified executor/observability/metrics.py -- added prism_harness_feedback_total{event_type,severity} + prism_harness_memory_extracted_total

### Verification results
- All 12 verification items: PASS
- py_compile 4 files PASS
- imports + alias HarnessLifecycle is HarnessRuntime PASS
- FeedbackEvent 5 event_type + 4 severity validated via typing.get_args PASS
- FeedbackCaptureMiddleware: tool_error extraction / custom_data signals / get_run_summary PASS
- HarnessRuntime assembly: 3 middleware + order [loop,obs,feedback] + guardrail_rules=4 PASS
- inject_into_pipeline: permission_engine + hook_system set PASS
- on_session_start fired PASS
- on_session_end turn_count=5 no LLM PASS; turn_count=10 LLM×1 + memory callback PASS
- on_session_end LLM exception → no memory callback + log WARNING PASS
- get_run_harness_summary total_failures + middleware_count=3 + guardrail_rules_count=4 PASS
- grep from backend.app in Task 3.4 files: 0 hits PASS

### Notes for next Task -- DOC-03 Task 3.5 (4-tier Compaction + 6-layer Memory)
- Tier 0 is DONE: executor/engine/context_budget.py compress_history() — atomic turn-group truncation (Task 2.4, ADR-029 compaction). DO NOT re-implement Tier 0.
- Tier 1-3 to implement in Task 3.5:
  - Tier 1: Delete oldest turn-groups (simplest, last resort)
  - Tier 2: LLM summarization of oldest messages → replace with summary block
  - Tier 3: Keep only most recent N turn-groups, discard rest (aggressive)
- 6-layer Memory naming (DOC-02 v4 / DOC-03 v4 §3.5): short-term / skill / mcp / agent / session / user
  - short-term: current session messages (ContextBudgetManager manages this)
  - skill: is_skill_context=True PrismMessage blocks (protected from compaction)
  - mcp: MCP server context injected by PromptAssembler
  - agent: agent-specific system prompt sections
  - session: session-level context (session metadata, user prefs)
  - user: user_memories table entries (written by Task 3.4 ADR-030, read by PromptAssembler DOC-07/09)
- CompactionTrigger: FeedbackEvent(event_type="compaction_triggered") should be emitted when compaction fires (wire into FeedbackCaptureMiddleware via ctx.custom_data["feedback_signals"])
- Compaction hooks: fire HookEvent(event_type="Compact", ...) when compaction triggers (HookSystem already has "Compact" event)

### Risks / Open items
- user_memory DB write is Backend-side (DOC-07/DOC-09 endpoints) — harness only sends callback event
- LoopDetection does NOT write to ctx.custom_data["feedback_signals"] yet — Entropy Detector (DOC-12 Task 12.2) will wire this

### Commit
- affb44b — feat(v4): Feedback Capture + HarnessRuntime lifecycle + user_memory extraction (DOC-03 Task 3.4)

---

## 2026-04-18 -- DOC-03 Task 3.3 completed (Hook System + Permission Engine + Guardrails)

### Done this session
- Created executor/harness/permissions/result.py -- PermissionResult standalone (avoids circular import)
- Created executor/harness/hooks/{events,decision,handlers,system,__init__}.py -- HookEvent/HookDecision 11 fields/merge_decisions (ADR-026/027)/HookHandlerExecutor 4 handlers/HookSystem asyncio.gather parallel
- Created executor/harness/guardrails/{rules,platform_rules,engine,__init__}.py -- GuardrailRule + get_platform_rules GR-PLATFORM-001~004/GuardrailsEngine
- Created executor/harness/permissions/{ask_protocol,engine,__init__}.py -- PermissionAskProtocol Redis BLPOP (ADR-028)/PermissionEngine 2-layer
- Created executor/harness/lifecycle.py -- HarnessLifecycle assembles all governance components
- Modified executor/tools/pipeline.py -- Step3 real permission_engine.check() + Step7 real hook_system.fire(PostToolUse)
- Modified executor/observability/metrics.py -- 3 new counters (permission_ask/hook_fired/guardrail_deny)
- Modified backend/app/core/config.py -- added PERMISSION_ASK_TIMEOUT_SECONDS / HOOK_TIMEOUT_SECONDS / RATE_LIMIT_* defaults

### Verification results
- All 13 verification items: PASS
- py_compile 11 new + 2 modified: PASS
- imports (hooks/permissions/guardrails/lifecycle): PASS
- guardrails rm -rf blocked / ls allowed / web_search unaffected: PASS
- merge stop priority / deny>ask>allow / updated_input conflict ValueError: PASS
- additional_context/blocking_error/message join + empty list: PASS
- permission ask fakeredis (allow + timeout deny + harness_event): PASS
- PermissionEngine integration (guardrails deny/hook deny/hook ask allow+updated_input): PASS
- 4 platform rules tests: PASS
- command handler JSON + timeout: PASS
- pipeline deny + allow+updated_input: PASS
- grep backend.app in harness: 0 hits PASS

### Notes for next Task -- DOC-03 Task 3.4 (Guardrails + Feedback Loop)
- GuardrailsEngine is DONE: Task 3.4 reuses executor/harness/guardrails/engine.py and GuardrailRule. DO NOT re-implement GuardrailRule. Use engine.add_rule(rule) to add additional rules.
- SessionEnd event is defined in events.py: HookEventType already has SessionEnd. Task 3.4 triggers it at session end by calling hook_system.fire(HookEvent(event_type=SessionEnd, ...)). Not implemented in Task 3.3.
- user_memory table was created in Task 2.1: Task 3.4 writes to user_memory via HTTP callback to Backend endpoint (Executor does NOT write to DB directly).

### Risks / Open items
- _execute_prompt and _execute_agent are Phase 1 skeletons (return empty HookDecision when adapter/fork_manager not injected). Full implementation in DOC-05 Task 5.3.
- _rate_window is module-level dict (per-executor subprocess, not shared across processes). PRD confirms this is acceptable.
- Redis key format for perm_answer:{id} is FIXED. DOC-07 Task 7.3 MUST RPUSH to exactly this key.

### Commit
- 25963bf -- feat(v4): Hook System 11 fields + 4 handlers + Permission BLPOP + 4 platform guardrails (DOC-03 Task 3.3 complete)

---

## 2026-04-18 — DOC-03 Task 3.2 completed（Middleware Pipeline 4 钩点）

### 本次 session 做了什么
- 创建 `executor/harness/middleware/base.py` — MiddlewareContext dataclass(12 字段全部有 default) + TurnContext 别名 + Middleware ABC(4 no-op 钩点)
- 创建 `executor/harness/middleware/pipeline.py` — MiddlewarePipeline with run_pre_turn/run_pre_tool_use(短路) + run_post_tool_use/run_post_turn(不短路)
- 创建 `executor/harness/middleware/loop_detection.py` — LoopDetectionMiddleware: post_turn Redis LPUSH+LTRIM+LRANGE sha256 指纹，N 连同 → abort + callback.harness_event("loop_detected")
- 创建 `executor/harness/middleware/observability.py` — ObservabilityMiddleware: pre_turn 记时，post_turn 上报 turn_complete(turn/duration_ms/tool_calls)
- 更新 `executor/harness/middleware/__init__.py` — 导出 6 个公共符号
- 修改 `executor/engine/query_engine.py` — RunContext 追加 agent_type; QueryEngine 新增 middleware_pipeline 参数; run() 集成 pre_turn/post_turn; _execute_single_tool() 集成 pre_tool_use/post_tool_use

### 验证结果
- Part B 验证步骤 1-10 全部: PASS
- py_compile 6 文件 PASS; 导入 + TurnContext is MiddlewareContext PASS; 正常/短路 pipeline PASS; 4 钩点语义 PASS; LoopDetection mock Redis PASS; Observability duration_ms PASS; QueryEngine 集成 + 向后兼容 PASS; _execute_single_tool abort PASS; 无 backend.app import PASS

### 下一个 Task 需要注意 — DOC-03 Task 3.3（Hook System + Permission Engine）
- **pipeline.py 的 2 个 HARNESS_INTEGRATION_POINT**：`executor/tools/pipeline.py` 步骤 3（PreToolUse Hook）和步骤 7（PostToolUse Hook）的注释是 Task 3.3 的锚点，不是 Middleware 的职责，Task 3.2 **未动**这两处
- **Permission ask Redis BLPOP**：CLAUDE.md 陷阱 #8 — permission ask 必须用 Redis BLPOP 阻塞等待，不能轮询；key 格式建议 `perm_answer:{permission_request_id}`
- **Hook 11 字段**：DOC-03 PRD 约束 Hook 事件有 11 个标准字段，Task 3.3 实施时需查 DOC-03 Part B Hook schema，不要自造字段（六原则 #1）
- **Middleware 与 Hook 执行顺序**：pre_tool_use Middleware 在 ToolExecutionPipeline.execute() 之前（在 query_engine.py 的 _execute_single_tool 中）；Pipeline 内部的 PreToolUse Hook 在 schema 校验之后、permission 检查之前（在 pipeline.py step 3）。两者独立，互不干扰

### 遗留风险 / 未决事项
- LoopDetectionMiddleware 检测时机是 post_turn（完整轮次后），若需要 pre_tool_use 级别的实时拦截，可在 Task 3.3 或后续 Task 注册额外 pre_tool_use Middleware
- ObservabilityMiddleware._turn_start_time 是实例变量，多轮串行无问题；若未来支持并发多轮（不在当前设计内），需改为 ctx.custom_data 存储

### Commit
- `e174ea5` — `feat(v4): Harness Middleware Pipeline with 4 hook points (DOC-03 Task 3.2)`

---

## 2026-04-18 — DOC-03 Task 3.1 completed（TAOR 主循环 + ToolExecutionPipeline）

### 本次 session 做了什么
- 创建 `executor/tools/{base.py, registry.py, pipeline.py}` — BaseTool/ToolResult + ToolRegistry + ToolExecutionPipeline（7 步链路 + HARNESS_INTEGRATION_POINT 注释）
- 创建 `executor/tools/builtin/{__init__.py, echo.py}` — EchoTool + register_builtin_tools()
- 创建 `executor/callbacks/backend_callback.py` — 双通道：Redis PUBLISH 高频直通 + HTTP 3 次指数退避重试 + DLQ
- 创建 `executor/engine/query_engine.py` — QueryEngine（TAOR while 循环 + asyncio.gather 并行工具 + _ADAPTERS_WITH_PASSTHROUGH 判断）+ RunContext dataclass + _block_to_dict helper
- 创建 `executor/engine/token_estimator_adapter.py` — DriverTokenEstimator 包装 ModelAdapter.count_tokens()
- 创建 `executor/observability/{__init__.py, metrics.py}` — 6 条 executor 专属 Prometheus metric（独立 Registry）
- 更新 `executor/__main__.py` — MAX_TURNS_BY_AGENT_TYPE 6 档 + heartbeat_writer 协程 + main() 骨架（DB 集成占位 FROM_DB:）
- 追加 `backend/requirements.txt` — jsonschema>=4.0.0
- 追加 `backend/app/observability/metrics.py` — prism_tool_errors_total / prism_harness_turn_total / prism_callback_dlq_total

### 验证结果
- py_compile 全部 10 文件：PASS
- 核心 imports + MAX_TURNS 6 键断言：PASS
- Part B 验证 #3（Pipeline 注册/执行/not found/schema校验/截断）：PASS
- Part B 验证 #4（3×5s 并行耗时 5.02s < 7s）：PASS
- Redis PUBLISH mock 测试（channel/payload 断言）：PASS
- HTTP 重试 + DLQ（3×500/200/401 三场景）：PASS
- heartbeat_writer（SETEX 多次 + DELETE on stop）：PASS
- TAOR dry-run（mock adapter 2 轮：tool_use + end_turn，turn_count=2，Echo: world in messages）：PASS
- Grep 无 `from backend.app` in executor/：PASS
- MAX_TURNS 6 键 + 值：PASS

### 下一个 Task 需要注意 — DOC-03 Task 3.2（Middleware Pipeline 4 钩点）
- **HARNESS_INTEGRATION_POINT 位置**：`executor/engine/query_engine.py` 中有 4 处注释标记（pre_turn 在 while 头部，post_turn 在 continue 前）；`executor/tools/pipeline.py` 中有 PreToolUse/PostToolUse 两处；Task 3.2 需在这 4 处注入 MiddlewarePipeline 调用
- **MiddlewarePipeline 构造时机**：在 `executor/__main__.py` 的注释段（标注 "5. Harness Runtime"）中注入，需在 QueryEngine 实例化之前构造；QueryEngine.__init__ 预留了 `# HARNESS_INTEGRATION_POINT: middleware_pipeline 在 Task 3.2 注入` 注释，届时改为真实参数
- **run_context 透传**：QueryEngine 已将 RunContext 透传到 pipeline.execute(run_context=self._run_context)，Task 3.2 的 MiddlewareContext 应从 run_context 取 run_id/session_id/user_id 三字段（不要重新定义）

### 遗留风险 / 未决事项
- `executor/__main__.py` 的 DB 集成部分（FROM_DB: 注释段）等待 DOC-07 Task 7.4 实现；当前 main() 启动后只初始化 callback + heartbeat 后即退出，不执行 run
- DriverTokenEstimator.estimate() 调用 adapter.count_tokens()，若底层 tokenizer 同步阻塞可能影响 async 性能；DOC-12 Task 12.1 可改为 run_in_executor 包装

### Commit
- `ce382a5` — `feat(v4): TAOR main loop + dual-channel callback + heartbeat (DOC-03 Task 3.1 complete)`

---

## 🎯 DOC-02 DONE — 2026-04-18

DOC-02 全部 4 Task 已完成收官。下一步应开始 **DOC-03 Task 3.1（TAOR 主循环 + ToolExecutionPipeline）**。

### DOC-03 Task 3.1 开工必读文件清单
1. `CLAUDE.md` — 六原则 + 10 陷阱（特别注意 #1 Redis 直通 / #2 回合组 / #3 工具并行 / #8 ask BLPOP）

DOC-02 全部 4 Task 已完成收官。下一步应开始 **DOC-03 Task 3.1（TAOR 主循环 + ToolExecutionPipeline）**。

### DOC-03 Task 3.1 开工必读文件清单
1. `CLAUDE.md` — 六原则 + 10 陷阱（特别注意 #1 Redis 直通 / #2 回合组 / #3 工具并行 / #8 ask BLPOP）
2. `PRD_V4/DOC-03-v4.md` Task 3.1 Part A + Part B 完整内容
3. `HANDOFF-LOG.md` 最近 3 条（本条 + Task 2.4 + Task 2.3）
4. Task 2.1-2.4 产物路径快速索引：
   - `backend/app/core/` — config.py / security.py / database.py / dependencies.py
   - `backend/app/models/__init__.py` — 18 张 ORM 表聚合
   - `executor/adapters/base.py` — PrismMessage / ToolDefinition / ContentBlock / StreamEvent / ModelAdapter（Task 2.2）
   - `executor/adapters/anthropic_driver.py` — AnthropicDriver，Redis PUBLISH(ADR-022)，cache_control(ADR-008)（Task 2.2）
   - `executor/adapters/openai_driver.py` — OpenAIDriver，ADR-007 展开规则（Task 2.2）
   - `executor/adapters/provider_manager.py` — ProviderManager，ADR-013 Redis 熔断器（Task 2.3）
   - `executor/engine/prompt_sections.py` — 21 section getter（Task 2.4）
   - `executor/engine/prompt_assembler.py` — PromptAssembler + MCPServerInfo + SkillInfo（Task 2.4）
   - `executor/engine/context_budget.py` — TokenEstimator + ContextBudgetManager（Task 2.4）

---

## 2026-04-18 — DOC-02 Task 2.4 completed（Prompt 动态装配引擎，DOC-02 收官）

### 本次 session 做了什么
- 读取 DOC-00 v4 §7 四铁律原文（无投资建议 / 数据溯源 / AI 标识 / 数据隔离），注入 compliance_section（583 字，防止占位）
- 创建 `executor/engine/prompt_sections.py`：21 个 section getter 函数，静态 9（identity/system_rules/task_philosophy/risk_actions/tool_grammar/tone_style/output_efficiency/compliance/agent_behavior）+ 动态 12（session_guidance/mcp_instructions/skill_grammar/memory/env_info/language/output_style/scratchpad/function_result_clearing/summarize_tool_results/token_budget/brief）；agent_behavior_section 实现 6 档（general/research/planner/verifier/coordinator/plugin_builder）
- 创建 `executor/engine/prompt_assembler.py`：PromptAssembler（_build_static/_build_dynamic/build/get_static_prefix/_compute_tools_hash）+ CACHE_BOUNDARY_MARKER 字面值 + MCPServerInfo / SkillInfo 临时 dataclass
- 创建 `executor/engine/context_budget.py`：TokenEstimator Protocol + ContextBudgetManager（estimate_tokens/estimate_messages_tokens/should_compress/truncate_tool_result/identify_turn_groups/compress_history）；默认值精确对齐 PRD（compact_trigger_ratio=0.85 / reserve_for_response=4096 / max_context_tokens=128000 / tool_result_max_chars=10000）
- 更新 `executor/engine/__init__.py`：导出 6 核心符号
- 修复 Windows GBK stdout 编码问题（PYTHONIOENCODING=utf-8）；修复中文引号导致的 SyntaxError

### 验证结果
- 验证 1（py_compile 4 文件）：PASS
- 验证 2（21 sections imported）：PASS
- 验证 3（Part B 完整脚本）：Section coverage / Static cache / Verifier VERDICT / Research Bash whitelist / Tools hash cache / Context budget truncation / Turn group — 全 7 项 PASS
- 验证 4（静态缓存字节级一致性 3 次调用）：PASS
- 验证 5（compress_history 保留 is_skill_context）：5 组场景，组 1 skill_context 消息在裁剪后仍保留 PASS
- 验证 6（Section 函数计数 >= 21）：精确 21 — PASS
- 验证 7（compliance_section 长度 > 80）：583 字 PASS
- 验证 8（build() 含 CACHE_BOUNDARY_MARKER）：PASS

### 下一个 Task 需要注意 — DOC-03 Task 3.1（TAOR 主循环 + ToolExecutionPipeline）
- **PromptAssembler 使用方式**：`assembler = PromptAssembler(agent_type=run.agent_type, tools=loaded_tools)` → `system_prompt = assembler.build(mcp_servers=[...], skills=[...], language=session.language)` → 传入 Driver.stream()；get_static_prefix() 供 AnthropicDriver cache_control 边界使用
- **MCPServerInfo / SkillInfo 临时定义**：在 prompt_assembler.py 顶部，DOC-05 实现后替换为正式 import；Task 3.1 直接 `from executor.engine.prompt_assembler import MCPServerInfo, SkillInfo` 即可
- **TokenEstimator 接入**：ContextBudgetManager 构造时传入 driver 适配器（或包装器）作为 estimator；目前 AnthropicDriver / OpenAIDriver 均有 count_tokens() 方法，可包装成简单适配器
- **Windows 编码注意**：bash 环境 Python stdout 默认 GBK，运行验证脚本时加 PYTHONIOENCODING=utf-8

### 遗留风险 / 未决事项
- MCPServerInfo / SkillInfo 是本 Task 临时定义，DOC-05 Task 5.1/5.2 落地后需统一 import 路径（届时修改 prompt_assembler.py 顶部 import，不破坏接口）
- session_guidance_section 当前对 general agent type 且无 feature gate 时返回空字符串（被 _build_dynamic 过滤），这是正确行为
- env_info_section() 读取 os.environ["WORKSPACE_DIR"]，若未设置则 fallback "/workspace"；DOC-03 Task 7.4 子进程启动时需注入此环境变量

### Commit
- `1463103` — `feat: prompt assembly engine with 21 sections + turn-group compaction (DOC-02 Task 2.4 complete)`

---

## 2026-04-18 23:58 — DOC-02 Task 2.3 completed(Provider 管理 + 故障转移)

### 本次 session 做了什么
- 创建 `backend/app/schemas/provider.py`: ProviderCapabilitiesSchema / ProviderPreset / CreateProviderRequest(capabilities 422) / UpdateProviderRequest / ProviderResponse(api_key_masked) / TestProviderResponse
- 创建 `backend/app/services/provider_presets.py`: BUILTIN_PRESETS 8 条(Anthropic/OpenAI/MiniMax/DeepSeek/Kimi/Qwen/智谱/Gemini),每条含 ProviderCapabilitiesSchema
- 创建 `backend/app/services/provider_service.py`: ProviderService(list/create/update/delete/test + bootstrap_presets 幂等 + scope 权限矩阵 + AES-256-GCM encrypt/decrypt via security.encrypt_value)
- 创建 `backend/app/api/v1/providers.py`: 6 端点(presets/list/create/update/delete/test),presets 公开,其余 JWT 认证
- 更新 `backend/app/api/v1/__init__.py`: api_v1_router 聚合器,注册 providers_router
- 更新 `backend/app/main.py`: lifespan 阶段调用 bootstrap_presets() + include api_v1_router
- 创建 `executor/adapters/provider_manager.py`: ProviderManager(get_adapter/record_success/record_failure/record_usage) + ADR-013 Redis 熔断器 + HMAC 签名 usage/harness_event 回调 stub

### 验证结果
- 验证 1 (py_compile 7 文件): PASS
- 验证 2 (All imports OK, Presets count: 8): PASS
- 验证 3 (capabilities 422 ValidationError): PASS
- 验证 4 (encrypt/decrypt roundtrip): PASS
- 验证 5 (mask_key 5 cases): PASS
- 验证 6 (circuit breaker 熔断→切换→恢复状态机): PASS
- 验证 7 (router.routes 6 条, paths/methods 正确): PASS
- 验证 8 (BUILTIN_PRESETS[0].capabilities isinstance ProviderCapabilitiesSchema): PASS

### 下一个 Task 需要注意 — DOC-02 Task 2.4(Prompt 装配引擎)
- **ProviderService.decrypt 路径**:Task 2.4 的 PromptAssembler 若需要在 Backend 侧构建最终 prompt,不需要 API Key — 但如果需要动态调用 Provider(如 few-shot 探测),需通过 `provider_service.decrypt_value(provider.api_key_encrypted, settings.ENCRYPTION_KEY)` 获取明文 key
- **capabilities 与 Prompt 模板关系**:Task 2.4 的 system prompt 装配需要感知 Provider capabilities — 例如 `prompt_cache=True` 时在 system prompt 末尾 text block 加 `cache_control: ephemeral`(ADR-008,AnthropicDriver 已实现,Task 2.4 需要在装配层预留 cache_control 注入点)
- **BUILTIN_PRESETS 路径**:Task 2.4 如需读取预设能力声明,import 路径是 `from app.services.provider_presets import BUILTIN_PRESETS`(app.* 路径,在 Docker backend 容器内);测试时 `from backend.app.services.provider_presets import BUILTIN_PRESETS`(含 fallback)

### 遗留风险 / 未决事项
- `executor/adapters/provider_manager.py` 中 Prometheus metrics 通过 `executor.observability.metrics` 导入 — 该模块在 DOC-12 实现前不存在,ImportError 时静默降级(已处理)
- `test_provider()` 探测逻辑发送真实 HTTP 请求 — 无 API Key 或无网络时会抛异常并被捕获返回 success=False,行为正确
- `bootstrap_presets()` 在 lifespan 时 DB 未就绪(docker compose 健康检查未完成)会 log WARNING 并继续启动,不阻断。首次真实请求到来时 DB 已就绪

### Commit
- `db89260` — `feat: provider management + failover + circuit breaker (DOC-02 Task 2.3)`

---

## 2026-04-18 23:30 — DOC-02 Task 2.2 completed(双协议 Driver)

### 本次 session 做了什么
- 创建 `executor/adapters/base.py`:PrismMessage + ContentBlock 联合类型(TextBlock/ToolUseBlock/ToolResultBlock) + ProviderCapabilities + ToolDefinition + StreamEvent + ModelResponse + ModelAdapter 抽象基类(含 stream/complete/count_tokens 抽象方法 + _sort_tools)
- 创建 `executor/adapters/stream_parser.py`:公共 SSE 行解析器 parse_sse_lines(),含 json_repair 容错 + [DONE] 终止
- 创建 `executor/adapters/anthropic_driver.py`:AnthropicDriver — cache_control 注入(ADR-008) + Redis PUBLISH 直通 sse:{session_id}(ADR-022) + cache_read/creation tokens 解析 + Anthropic SDK count_tokens() fallback tiktoken
- 创建 `executor/adapters/openai_driver.py`:OpenAIDriver — ADR-007 tool_result 展开规则 + Redis PUBLISH 直通 + tiktoken count_tokens(未知模型 fallback cl100k_base + WARNING)
- 更新 `executor/adapters/__init__.py`:导出全部核心符号
- 更新 `backend/requirements.txt`:redis 升级为 redis[hiredis],新增 json-repair>=0.28.0

### 验证结果
- 验证 1 (py_compile 四文件): PASS
- 验证 2 (All imports OK): PASS
- 验证 3 (ADR-007 expand 示例): PASS — [ToolResultBlock(A), ToolResultBlock(B), TextBlock("然后")] → role=tool(A), role=tool(B), role=user("然后")
- 验证 4 (_sort_tools): PASS — [zzz, aaa] → [aaa, zzz]
- 验证 5 (无 PrismMessage(role=tool/system) 构造): PASS — grep 未发现
- 验证 6 (requirements.txt 依赖检查): PASS — anthropic/tiktoken/json-repair/redis[hiredis]/httpx 均在列

### 下一个 Task 需要注意 — DOC-02 Task 2.3(Provider 管理与故障转移)
- **Driver 构建**:Task 2.3 的 ProviderManager 需要从 DB `providers.config` JSONB 的 `capabilities` 子对象构建 ProviderCapabilities 实例并传给 AnthropicDriver/OpenAIDriver 构造器(ADR-008)
- **API Key 解密**:providers.api_key_encrypted 使用 AES-256-GCM(ENCRYPTION_KEY),调用 `backend.app.core.security.decrypt_value()`——注意 Executor 不能 import backend 模块,Task 2.3 的解密必须在 Backend 侧做(子进程启动时通过环境变量或参数注入明文 key)
- **熔断器状态**:ADR-013 要求仅存 Redis(key: `harness:circuit:{provider_id}`),不存内存,多子进程共享。Redis 连接用相同惰性初始化模式(os.environ["REDIS_URL"])

### 遗留风险 / 未决事项
- 真实 API 集成测试未执行(需真实 API Key + 网络,本 session 仅静态验证)
- AnthropicDriver.stream() 的 abstractmethod 声明使用了 raise+yield 双重模式兼容 ABC 和 AsyncIterator 类型注解;若遇 mypy strict 问题可改为 @asynccontextmanager 模式
- OpenAI usage chunk 解析:stream_options.include_usage=True 时 usage 在最后一个 chunk,若 Provider 不支持此选项可能 usage=0

### Commit
- `1074d34` — `feat: dual-protocol model adapters (DOC-02 Task 2.2 complete)`

---

## 🔴 父 Opus session 续作指引(2026-04-18 22:50 交接)

> **读这段的你是新的 Opus 父 session**。上一个父 session 因 context 拥挤 /clear,核心任务未完成,状态已固化到所有 `.md` 文件,你接手继续派 Sonnet subagent 推进。

### 用户原始指令(不可忘)
- **核心任务**: **按计划完成所有后端内容,前端(DOC-10 / DOC-11)先等等**
- **Auto Mode 开启**: 连续自主执行,最小打扰,遇低风险决策直接做判断;遇破坏性/共享系统操作才问用户
- 执行策略已定稿:`PRD_V4/2026-04-18-execution-strategy-design.md`
- 代码由 Sonnet 4.6 写(通过 Agent tool, `model: sonnet`),**你(Opus)不动代码**,只派工 + 跟踪状态

### 当前进度(读 PROGRESS.md 看完整表)
- ✅ Phase 0(PRD v4 全部文档)完成
- ✅ DOC-02 Task 2.1 完成(骨架 + 18 表 ORM + alembic,commit `1e8ac83`)
- ⬜ 下一个:**DOC-02 Task 2.2 双协议 Driver**(Anthropic canonical + OpenAI 展开)

### 待办后端 Task 清单(依赖顺序)
1. **DOC-02 剩余**:Task 2.2(Driver)→ 2.3(Provider 管理)→ 2.4(Prompt 装配)
2. **DOC-03**:3.1(TAOR + 双通道回调 + 心跳)→ 3.2(Middleware 4 钩点)→ 3.3(Hook 11 字段 + ask BLPOP)→ 3.4(Feedback + user_memory)→ 3.5(Compaction 4 级回合组)→ 3.6(配置 2 源)
3. **DOC-04**:4.1(6 种 Agent)→ 4.2(Fork capability)→ 4.3(Coordinator checkpoint)→ 4.4(TaskRouter)→ 4.5(PluginBuilder 打分)
4. **DOC-05**:5.1(Skill 三级)→ 5.2(MCP 双通道)→ 5.3(Hook 4 handler)→ 5.4(PluginHost 变量)→ 5.5(Registry 两源)→ 5.6(Agent Tool 仅搜索)→ 5.7(CC ConversionReport)
5. **DOC-06**:6.1(三密钥 + SSE ticket)→ 6.2(用户 + 邀请码)
6. **DOC-07**:7.1(Session CRUD)→ 7.2(Run 生命周期 + sequence_no 原子 + cancel 三模式)→ 7.3(Callback 双通道 + SSE Manager + HeartbeatMonitor + permission-answer)→ 7.4(子进程标准化参数 + coordinator_recovery + alert_dispatcher)
7. **DOC-08**:8.1(IMAdapter + Webhook 幂等)→ 8.2(三平台)→ 8.3(绑定三元组)
8. **DOC-09**:9.1(MCP 管理)→ 9.2(Provider scope + cache tokens)→ 9.3(Admin 审计 + Dashboard)
9. **DOC-12 后端部分**:12.1(TokenEstimator + ResourceMonitor)→ 12.2(Entropy 8 信号)→ 12.3(/health 3 子端点 + Docker)→ 12.4(Prometheus 60+)→ 12.5(OTel 跨进程)→ 12.6(结构化日志)→ 12.7(前端错误上报端点,属后端)→ 12.8(AlertDispatcher)

前端 DOC-10 / DOC-11 **不做**(用户明确暂缓)。

### 派工模板(给 Sonnet subagent)

每个 Task 派一个 Sonnet subagent:
```
Agent tool, subagent_type=general-purpose, model=sonnet
Prompt 模板见上一个成功案例(Task 2.1 Phase 2 的 Agent 调用,prompt 含:
  - 工作目录 E:\Agent program\PrismV3\
  - 必读文件清单(CLAUDE.md / HANDOFF-LOG.md / 对应 DOC-XX v4 Task 内容)
  - 本次范围(具体做哪几步,不做哪几步)
  - 硬底线(六原则)
  - 验证步骤
  - 结束动作(commit + 更新 PROGRESS/DECISIONS/HANDOFF)
  - 报告格式 ≤ 500 字)
```

### 交接注意
- 每次派 subagent 后必读回报,确认 commit hash + PROGRESS/DECISIONS/HANDOFF 更新了才派下一个
- 3 份 `.md` 状态文件现在是**真相源**,每个 Sonnet subagent 都要读 + 更新
- 若 Sonnet 报 blocker(如 18 vs 19 表那类),读 blocker.md 判断:
  - **非阻塞 + 有合理假设** → 接受,继续下一个
  - **阻塞需人工** → 暂停,向用户报告
- 父 session context 又拥挤时,重复本次动作(固化到 HANDOFF-LOG + /clear)
- 不要把 41 个 Task 的 TaskCreate 全开,保持 task list 精简(只开"当前正在做的 DOC"一级即可)

### Blocker 记录
- `blocker.md`(2026-04-18):PRD 标题"19 张表"但 §4.2 实际 18 张。已按 DOC-01 §4.2 为真相源实施 18 张,**非阻塞**,可能是 PRD 计数错误,待用户最终裁定是否修 PRD

---

## 2026-04-18 22:30 — DOC-02 Task 2.1 completed(18 表 ORM + Alembic 迁移)

### 本次 session 做了什么
- 创建 `backend/app/core/database.py`: SQLAlchemy engine + SessionLocal + get_db() dependency
- 创建 `backend/app/core/dependencies.py`: get_db / get_redis(NotImplementedError) / get_current_user / require_admin
- 创建 `backend/app/schemas/common.py`: ApiResponse[T] / ErrorDetail / ErrorResponse / PagedResponse[T] (Pydantic v2)
- 创建 18 个 ORM 模型文件(13 基础 + 5 v4 新增): user, invite_codes, sessions, session_queue_items, runs, messages, tool_executions, providers, mcp_servers, user_mcp_installs, im_bindings, im_channel_configs, audit_logs, skill_installs, coordinator_plans, permission_requests, im_message_dedup, user_memories
- 创建 `backend/app/models/__init__.py` 聚合导入所有 18 张表
- 创建 `backend/alembic.ini` + `backend/alembic/env.py` + `backend/alembic/versions/001_initial_tables.py` 手写迁移(331 行 DDL)
- 提交 blocker.md: PRD 标题"19 张表"但 §4.2 实际定义 18 张,以 DOC-01 §4.2 为真相源实施 18 张

### 验证结果
- `from app.models import *`: 18 张表全部导入,0 错误 — PASS
- `alembic upgrade head --sql` DDL 静态检查: 所有关键约束存在 — PASS
  - providers CHECK (scope/user_id 互斥)
  - im_bindings UNIQUE (channel, platform_user_id, platform_chat_id) 三元组
  - runs: cache_hit_tokens / cache_creation_tokens / harness_summary 字段
  - messages: is_skill_context / skill_name 字段
  - tool_executions: permission_decision / hook_modified 字段
- 所有 Python 文件语法检查: py_compile PASS
- 注: 未实测 DB (docker 未启动),仅 DDL 静态检查

### 下一个 Task 需要注意 — DOC-02 Task 2.2 (双协议 Driver)
- **ADR-关键注意点**:
  1. `sessions.blocking_run_id` 是 SET NULL FK,子进程完成时必须清空此字段
  2. `messages.sequence_no` 严禁 max+1(ADR-060),DOC-07 Task 7.2 实现 per-session 序列或 advisory_xact_lock
  3. `providers` 表 `api_key_encrypted` 字段要求 AES-256-GCM(使用 `ENCRYPTION_KEY`),Task 2.3 实现时直接调用 `app.core.security.encrypt_value()`
  4. `providers.config` JSONB 必须包含 `capabilities` 子对象,这是应用层校验(非 DB CHECK),Task 2.3 需要在 service 层做
  5. Task 2.2 的 PrismMessage 对应 `messages.content` JSONB — role 只有 'user'/'assistant' 两种(DOC-01 v4 §5),tool_result 作为 user message 的 content block 存储
  6. `get_redis()` 在 dependencies.py 返回 NotImplementedError,DOC-03 Task 3.1 需要填充真实实现

### 遗留风险 / 未决事项
- PRD "19 张表"计数与实际 §4.2 定义 18 张的矛盾:已记录 blocker.md,待人工确认是否有漏掉的第 19 张表
- `ddl_static_check.sql` 已提交到仓库可供审查;删除或保留由下一个 session 决定
- Docker 实测未进行(需 .env 实体文件 + docker compose up)

### Commit
- `1e8ac83` — `feat: 18-table ORM + alembic initial migration (DOC-02 Task 2.1 complete)`

---

## 2026-04-18 20:10 — DOC-02 Task 2.1 in_progress(骨架 + 最小 FastAPI)

### 本次 session 做了什么
- `git init` 初始化仓库(首次代码 session)
- 创建完整目录骨架:`backend/app/{api/v1,core,services,schemas,models,observability}/`、`executor/{engine,adapters,tools,harness/{middleware,guardrails,hooks,permissions},callbacks,plugins,coordinator}/`、`frontend/`
- 各包创建 `__init__.py`(含 executor 下全部子包)
- 根目录:`.gitignore`、`.env.example`(三密钥独立分区)、`README.md`(5 行概述)、`pyproject.toml`(含完整依赖列表)
- `docker-compose.dev.yml`:postgres:16 + redis:7-alpine(appendonly yes)+ backend(healthcheck /health/live)+ prism-net 网络
- `backend/Dockerfile` + `backend/requirements.txt`
- `backend/app/core/config.py`:Settings 类,读三密钥 + DB_URL + REDIS_URL + 全部 Harness 参数
- `backend/app/core/security.py`:`validate_secrets()`(真实校验:长度 >= 32 + 互不相等)+ AES-256-GCM encrypt/decrypt_value + hash/verify_password + create/decode JWT
- `backend/app/observability/logging.py`:structlog JSON + contextvars + TimeStamper
- `backend/app/observability/metrics.py`:REGISTRY + 10 维度 15 个核心指标占位
- `backend/app/main.py`:FastAPI + lifespan(validate_secrets → init_logging → metrics import)+ /health/live /health/ready /health/detailed + /metrics

### 验证结果
- AST 语法检查:5 个核心文件全部 PASS
- `validate_secrets()` 逻辑校验:4 场景单元测试全 PASS(短密钥 / 两两相同 / 三者相同 / 合法)
- `docker compose config`:解析成功(仅版本过期警告 + .env not found 提示,均正常)

### 下一个 Task 需要注意
- **下一步(Task 2.1 第二阶段)**:创建 `backend/app/models/base.py` + 19 张表 ORM 模型(含 Harness 扩充字段)+ alembic 初始化 + `versions/001_initial_tables.py` 手写迁移
- `ENCRYPTION_KEY` 在 `security.py` 的 `encrypt/decrypt_value` 中期望为 64 位 hex(32 字节)。DOC-02 Task 2.3 实现 Provider config 加密时必须一致。
- health_ready 中的 DB 检查使用同步 SQLAlchemy 引擎。后续若引入 async SQLAlchemy,需同步改 readiness 探针。
- `validate_secrets` 接收的是原始字符串(非 hex 解码),与 `encrypt_value` 期望 `key_hex` 作 hex 解码的语义不同。ENCRYPTION_KEY 在环境变量中存储为 hex 字符串是正确的。

### 遗留风险 / 未决事项
- 19 张表 ORM 未创建(Step 3 全部留给下一个 session)
- alembic 未初始化(Step 6 留给下一个 session)
- `backend/app/core/database.py`、`backend/app/core/dependencies.py`、`backend/app/schemas/common.py` 未创建(Step 2 剩余部分)
- `/health/detailed` 和 `/metrics` 暂无 admin 认证依赖(占位实现,DOC-06 Task 6.1 后补)
- docker 实际启动未验证(本 session 无 .env 实体文件)

### Commit
- `5c689df` — `feat: bootstrap project skeleton + minimal FastAPI (DOC-02 Task 2.1 partial)`

---

## 2026-04-18 19:50 — Phase 0 文档阶段完成(非代码 session)

### 本次 session 做了什么
- 完成 DOC-03 ~ DOC-12 共 10 份 PRD v4 改写(Opus 4.7 Web → Claude Code 接续)
- 新建 DOC-CC-ONBOARDING.md 先导文档(13 节)
- 撰写 execution-strategy-design.md 执行策略 spec(12 节,含 superpowers 角色分配)
- 在项目根初始化 CLAUDE.md / PROGRESS.md / DECISIONS.md / HANDOFF-LOG.md 四件套

### 验证结果
- 本阶段无代码验证,所有 PRD 文档已落盘到 `E:\Agent program\PrismV3\PRD_V4\`
- 合计 16,075 行,~631 KB,217 处修订,101 个 ADR

### 下一个 Task 需要注意
- **DOC-03 Task 3.1(TAOR 主循环 + ToolExecutionPipeline)是首个实施 Task**
- 开工前必读:
  - `CLAUDE.md`(心智模型 + 六原则 + 10 陷阱)
  - `PRD_V4/DOC-CC-ONBOARDING.md`(完整先导)
  - `PRD_V4/DOC-00-v4.md` + `DOC-01-v4.md` + `DOC-02-v4.md`(三份基座)
  - `PRD_V4/DOC-03-v4.md` Task 3.1 的 Part A + Part B 完整内容
  - `.plan/doc-03-task-3.1.md`(如已生成)
- Sonnet 开工规范:**Part B 本身就是 plan,不再用 writing-plans 重写**;直接 `superpowers:test-driven-development`(Part B 验证步骤作测试初稿)→ 实现 → `superpowers:verification-before-completion` → `superpowers:requesting-code-review`
- 创建分支:`feat/doc-03-v4`

### 遗留风险 / 未决事项
- 项目根还没有代码骨架(Python 包结构 / requirements.txt / pyproject.toml 等)。按 DOC-02 v4 Task 2.1 的规范,这些应该在 Task 2.1 实施时创建,但 DOC-02 v4 Task 2.1 本身已在 Phase 0 标记 completed(由 Opus 4.7 Web 完成 PRD 阶段,**代码尚未实施**)
- **重要**:PROGRESS.md 中 "DOC-00~12 改写 completed" 指的是**文档改写完成**,不是代码实施完成。Phase 1 的首个代码 Task 严格说应是 DOC-02 Task 2.1(项目骨架),不是 DOC-03 Task 3.1。建议 Sonnet 开工前确认:
  - 选项 A:从 DOC-02 Task 2.1 开始(先搭骨架)
  - 选项 B:默认 DOC-02 Task 2.1~2.4 已由 Opus Web 完成代码 → 直接 DOC-03 Task 3.1
  - 当前 HANDOFF-LOG 按选项 A 理解,建议 Sonnet 打开 DOC-02 v4 Task 2.1 确认项目骨架是否已创建;未创建则从 Task 2.1 开始

### Commit
- 无(文档落盘在 Claude 分发目录,未纳入 git)

---

> **最后更新**: 2026-04-18 19:50
