# Prism v2 ADR 落地台账

> **规范**: 每个 ADR 在对应 Task 实施完成时追加条目;偏离点必须说明
> **ADR 编号空间**: ADR-001 ~ ADR-120(PRD v4 已分配)
> **初始化**: 2026-04-18

---

## ADR 来源索引(按 DOC 分片,便于查找)

| DOC | ADR 范围 | 主题 |
|---|---|---|
| DOC-00 v4 | ADR-001 ~ ADR-003 | 愿景 / 铁律 / P1-P7 原则 |
| DOC-02 v4 | ADR-004 ~ ADR-017 | Schema / 三密钥 / tokenizer / Prompt 装配 / 回合组 |
| DOC-03 v4 | ADR-020 ~ ADR-031 | Harness 单实例 / 工具并行 / Redis 直通 / 心跳 / Hook 11 字段 / ask BLPOP / Compaction 4 级 / 配置 2 源 |
| DOC-04 v4 | ADR-030 ~ ADR-038 | MCP 白名单 / Verifier VERDICT / Fork 3 约束 / ForkBriefing / Coordinator checkpoint / TaskRouter / PluginBuilder 打分 |
| DOC-05 v4 | ADR-040 ~ ADR-050 | Skill 三级 / 强制调用 / is_skill_context / Hook 4 handler / MCP 双通道 / 变量系统 / Skills 两源 / ConversionReport |
| DOC-06 v4 | ADR-050 ~ ADR-055 | 三密钥独立 / SSE ticket / Refresh cookie |
| DOC-07 v4 | ADR-060 ~ ADR-067 | sequence_no 原子 / promote 事务 / cancel 三模式 / 回调方案 A / permission-answer / HeartbeatMonitor / subprocess 参数 / coordinator_recovery |
| DOC-08 v4 | ADR-070 ~ ADR-073 | Webhook 幂等 / im_bindings 三元组 |
| DOC-09 v4 | ADR-080 ~ ADR-085 | Provider scope / capabilities 探测 / 用量 cache tokens / Admin 权限边界 |
| DOC-10 v4 | ADR-090 ~ ADR-095 | useSSE 状态机 / ticket 换取 / 指数退避 / apiClient 错误分类 / AbortController / 错误上报 |
| DOC-11 v4 | ADR-100 ~ ADR-108 | ChatHeader 双态 / run_crashed UX / 会话扩展 / IM UX / Cache 突出 / Store 两源 / 打分进度条 / Config 只读 / Obs 独立 |
| DOC-12 v4 | ADR-110 ~ ADR-120 | 精确 tokenizer / 百分比阈值 / Entropy 8 信号 / 阈值校准 / health 拆分 / Docker 限制 / Prometheus / OTel / structlog / 前端上报 / AlertDispatcher |

---

## 落地记录

### 模板

```markdown
## ADR-XXX: <标题>(DOC-YY Task Z.Z)
- **来源**: PRD v4 DOC-YY Task Z.Z Part A
- **实施状态**: ✅ YYYY-MM-DD / ⏳ in_progress / 🚫 blocked
- **落地位置**: <文件路径列表>
- **实施 commit**: <git hash>
- **偏离点**: 无 / 或"因 X 原因微调为 Y,见 commit"
- **验证结果**: Part B 验证步骤全部 PASS / 或列出未通过项
- **下游影响**: (可选)哪些后续 Task 依赖此 ADR 的具体实现
```

---

## Phase 1 Prelude: 骨架(DOC-02 Task 2.1 partial)

## ADR-004: 三密钥独立 — 启动校验落地(DOC-02 Task 2.1 / DOC-06 ADR-050)
- **来源**: PRD v4 DOC-02 Task 2.1 Part B Step 5; DOC-06 ADR-050
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `backend/app/core/security.py` — `validate_secrets(jwt_secret, encryption_key, callback_secret)`
  - `backend/app/main.py` — lifespan 首步调用 `validate_secrets()`
  - `.env.example` — 三密钥分区注释,各有独立占位符
- **实施 commit**: 5c689df(Phase 1); Phase 2 commit TBD
- **偏离点**: 无。三密钥均要求 >= 32 字符且互不相等,不满足则 RuntimeError 阻止启动。
- **验证结果**: 四场景单元测试全 PASS(短密钥 / 两两相同 / 三者相同 / 合法输入)
- **下游影响**: DOC-06 Task 6.1 实现 SSE ticket 时需引用 `CALLBACK_SECRET`;DOC-02 Task 2.3 Provider encrypt 时需引用 `ENCRYPTION_KEY`

## ADR-004 第二阶段落地: Schema 对齐 18 表 ORM + Alembic 迁移(DOC-02 Task 2.1 Phase 2)
- **来源**: DOC-01 v4 §4.2; DOC-02 Task 2.1 Part B Step 2-3 + Step 6
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `backend/app/core/database.py` — engine + SessionLocal + get_db()
  - `backend/app/core/dependencies.py` — get_db / get_redis(NotImplementedError) / get_current_user / require_admin
  - `backend/app/schemas/common.py` — ApiResponse[T] / ErrorDetail / ErrorResponse / PagedResponse[T]
  - `backend/app/models/base.py` — Base + TimestampMixin + generate_uuid() (uuid_extensions.uuid7)
  - `backend/app/models/{user,session,run,message,tool_execution,provider,mcp_server,im,audit}.py` — 13 base tables
  - `backend/app/models/{skill_install,coordinator_plan,permission_request,im_dedup,user_memory}.py` — 5 v4 new tables
  - `backend/app/models/__init__.py` — aggregated import of all 18 tables
  - `backend/alembic.ini` — Alembic config
  - `backend/alembic/env.py` — env.py reading Base.metadata
  - `backend/alembic/versions/001_initial_tables.py` — hand-written migration (18 tables + all indexes + constraints)
- **实施 commit**: 1e8ac83
- **偏离点**:
  1. PRD heading says "19 张表" but §4.2 defines only 18 unique tables (13 base + 5 v4-new). See `blocker.md` for full analysis. Implemented exactly what §4.2 defines (18 tables).
  2. `uuid7` pip package installs as Python module `uuid_extensions` (not `uuid7`). Used `from uuid_extensions import uuid7` in base.py. requirements.txt retains `uuid7>=0.1.0` (correct pip name).
  3. `sessions.blocking_run_id` circular FK (sessions→runs→sessions) handled by creating sessions first without FK, then `ALTER TABLE` after runs table created.
- **验证结果**: DDL 静态检查 PASS
  - `from backend.app.models import *` — 18 tables, 0 errors
  - `alembic upgrade head --sql` — 331-line DDL generated, all key constraints present:
    - `CHECK ((scope = 'system' AND user_id IS NULL) OR (scope = 'user' AND user_id IS NOT NULL))`
    - `UNIQUE (channel, platform_user_id, platform_chat_id)`
    - `cache_hit_tokens`, `cache_creation_tokens`, `harness_summary` fields in runs
    - `permission_decision`, `hook_modified` in tool_executions
    - `is_skill_context`, `skill_name` in messages
  - 注：未实测 DB (docker 未启动), 仅 DDL 静态检查
- **下游影响**: DOC-02 Task 2.2 可直接使用 Run / Message / Provider ORM; DOC-06 Task 6.1 使用 User / InviteCode ORM

## ADR-017: is_skill_context 字段落地(DOC-01 v4 §5 / DOC-05 ADR-042)
- **来源**: DOC-01 v4 §5 PrismMessage 结构; 任务指令明确要求
- **实施状态**: ✅ 2026-04-18
- **落地位置**: `backend/app/models/message.py` — `is_skill_context: Mapped[bool]` + `skill_name: Mapped[str | None]`
- **实施 commit**: 1e8ac83
- **偏离点**: 无。字段按 DOC-01 v4 §5 定义精确添加,与 PrismMessage dataclass 字段对齐。
- **验证结果**: DDL 包含 `is_skill_context BOOLEAN DEFAULT 'false' NOT NULL, skill_name VARCHAR(200)`
- **下游影响**: DOC-03 Task 3.5 Compaction Engine 使用 `is_skill_context` 优先保留 Skill 注入的上下文消息

---

## DOC-02 Task 2.2: 双协议 Driver(ADR-007 / ADR-008 / ADR-009)

## ADR-007: PrismMessage canonical Anthropic 语义(DOC-02 Task 2.2)
- **来源**: PRD v4 DOC-02 Task 2.2 Part A / Part B
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `executor/adapters/base.py` — PrismMessage(role: Literal["user","assistant"]),TextBlock / ToolUseBlock / ToolResultBlock / ContentBlock 类型定义
  - `executor/adapters/openai_driver.py` — `_convert_messages_to_openai()` 实现 ADR-007 展开规则:含 ToolResultBlock 的 user PrismMessage 展开为多条 role=tool 消息;混合(ToolResult+Text)时先 tool_result 后 user
  - `executor/adapters/anthropic_driver.py` — `_convert_messages_to_anthropic()` 直接映射(canonical 语义本就是 Anthropic 格式)
- **实施 commit**: 1074d34
- **偏离点**: 无。role 严格限定 Literal["user","assistant"],代码中无 PrismMessage(role="tool") 或 PrismMessage(role="system") 构造。
- **验证结果**:
  - 验收示例 [ToolResultBlock(A), ToolResultBlock(B), TextBlock("然后")] → role=tool(A), role=tool(B), role=user("然后") — PASS
  - 完整对话序列(5 消息)测试 PASS
  - grep 确认无 PrismMessage(role=tool/system) — PASS
- **下游影响**: DOC-03 TAOR 主循环的消息存储以 PrismMessage 为单位;DOC-05 Compaction 依赖 is_skill_context 字段

## ADR-008: Driver 接口强制接受 provider_capabilities(DOC-02 Task 2.2)
- **来源**: PRD v4 DOC-02 Task 2.2 Part A
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `executor/adapters/base.py` — ModelAdapter.__init__ 接受 `capabilities: ProviderCapabilities | None`;ProviderCapabilities dataclass(prompt_cache / streaming_tools / extended_thinking / vision)
  - `executor/adapters/anthropic_driver.py` — 按 capabilities.prompt_cache 决定是否注入 cache_control(ephemeral 标记加在 system 最后 text block 和最后 user message 最后 text block)
  - `executor/adapters/openai_driver.py` — capabilities.prompt_cache 对 OpenAI 恒为 False;cache_* tokens 恒为 0
- **实施 commit**: 1074d34
- **偏离点**: 无。两个 Driver 均在 constructor 接受 capabilities 参数,保守降级:capabilities=None 时默认 ProviderCapabilities()(全 False)。
- **验证结果**: 导入和语法检查 PASS
- **下游影响**: DOC-02 Task 2.3 ProviderManager 在构建 Driver 实例时必须传入正确的 capabilities(从 DB providers.config.capabilities 读取)

## ADR-009: 精确 tokenizer 集成 Driver 层(DOC-02 Task 2.2)
- **来源**: PRD v4 DOC-02 Task 2.2 Part A
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `executor/adapters/base.py` — ModelAdapter.count_tokens() 抽象方法定义
  - `executor/adapters/anthropic_driver.py` — count_tokens() 优先 Anthropic SDK client.messages.count_tokens();失败 fallback tiktoken cl100k_base + log WARNING
  - `executor/adapters/openai_driver.py` — count_tokens() 使用 tiktoken.encoding_for_model(self.model);未知模型 fallback cl100k_base + log WARNING(含 per-message overhead 4 + reply priming 3)
  - `backend/requirements.txt` — 新增 json-repair>=0.28.0;redis 升级为 redis[hiredis]>=5.0.0
- **实施 commit**: 1074d34
- **偏离点**: OpenAI 国产模型(DeepSeek/Kimi/Qwen)tiktoken 可能不精确,fallback cl100k_base 并 WARNING 提示人工校准。这是 PRD 明确允许的 fallback 路径。
- **验证结果**: 导入和语法检查 PASS
- **下游影响**: DOC-12 Task 12.1 TokenEstimator 会调用 count_tokens() 接口;DOC-03 Task 3.5 Compaction 计算上下文窗口占用

---

## DOC-03 Task 3.3: Hook System + Permission Engine(ADR-026 / ADR-027 / ADR-028)

## ADR-026: HookDecision 11 字段完整定义(DOC-03 Task 3.3)
- **来源**: PRD v4 DOC-03 Task 3.3 Part A ADR-026; PDF 补丁 P4
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `executor/harness/hooks/decision.py` — HookDecision 11 字段完整定义(permission_decision / updated_input / updated_mcp_tool_output / prevent_continuation / stop / stop_reason / additional_context / message / blocking_error / reason / handler_name)
  - `executor/harness/hooks/__init__.py` — 导出 HookDecision
- **实施 commit**: 25963bf
- **偏离点**: 无。严格对标 CC toolHooks.ts，全部 11 字段，无砍字段，无添加字段。
- **验证结果**: py_compile PASS; 11字段完整性验证 PASS
- **下游影响**: DOC-05 Task 5.3 Hook 4 handler 扩展时复用此 dataclass

## ADR-027: merge_decisions() 合并规则严格度降序(DOC-03 Task 3.3)
- **来源**: PRD v4 DOC-03 Task 3.3 Part A ADR-027; PDF 补丁 P4 Batch 2 §A3-6
- **实施状态**: ✅ 2026-04-18
- **落地位置**: `executor/harness/hooks/decision.py` — merge_decisions() 函数
- **实施 commit**: 25963bf
- **偏离点**: 无。合并顺序精确对齐 PRD：stop → prevent_continuation → permission(deny>ask>allow) → updated_input 冲突 ValueError → updated_mcp_tool_output 冲突 ValueError → additional_context 拼接"\\n\\n" → blocking_error 拼接"; " → message 拼接"\\n"；空 list 返回空 HookDecision。
- **验证结果**: 7 项合并规则测试全 PASS（stop优先级/deny>ask>allow/updated_input冲突ValueError/additional_context join/blocking_error join/message join/空list）
- **下游影响**: HookSystem.fire() 调用 merge_decisions() 汇总所有并行 handler 决策

## ADR-028: permission ask Redis BLPOP 反向通信协议(DOC-03 Task 3.3)
- **来源**: PRD v4 DOC-03 Task 3.3 Part A ADR-028; Batch 2 §A3-7; PDF 补丁
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `executor/harness/permissions/ask_protocol.py` — PermissionAskProtocol.ask() 完整实现
    - uuid7(fallback uuid4) 生成 request_id
    - SETEX `perm_req:{request_id}` TTL=timeout_seconds
    - HTTP callback.permission_ask() 通知 Backend → SSE → 前端弹窗
    - BLPOP `perm_answer:{request_id}` 阻塞等待（timeout=timeout_seconds，不传 0）
    - 超时 fail-safe deny + harness_event("permission_ask_timeout")
    - 非法 answer（非 allow/deny）视为 deny
  - `executor/harness/permissions/engine.py` — ask 分支调用 ask_protocol.ask()
- **实施 commit**: 25963bf
- **偏离点**: Redis key 格式严格对齐（perm_req:{id} / perm_answer:{id}），DOC-07 Task 7.3 的 permission-answer 端点 RPUSH 时必须严格匹配此 key 格式。
- **验证结果**: fakeredis 场景1(2s内allow) + 场景2(1s超时deny) 均 PASS；harness_event 超时回调验证 PASS
- **下游影响**: DOC-07 Task 7.3 实现 `/sessions/{id}/permission-answer` 端点时 RPUSH `perm_answer:{request_id}`（key 格式已固化）

---

## DOC-02 Task 2.3: Provider 管理与故障转移(ADR-010 / ADR-011 / ADR-012 / ADR-013)

## ADR-010: providers.scope 二值权限矩阵(DOC-02 Task 2.3)
- **来源**: PRD v4 DOC-02 Task 2.3 Part A; DOC-09 ADR-080
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `backend/app/schemas/provider.py` — ProviderResponse.scope: str ('system'|'user')
  - `backend/app/services/provider_service.py` — list/create/update/delete 全部按 scope 校验
    - `list_providers()`: SELECT WHERE scope='system' OR (scope='user' AND user_id=current)
    - `create_provider()`: 强制 scope='user', user_id=current_user
    - `update_provider()` / `delete_provider()`: user scope 要求 owner; system scope 要求 admin
  - `backend/app/services/provider_presets.py` + `ProviderService.bootstrap_presets()` — scope='system' 预设幂等注册
- **实施 commit**: db89260
- **偏离点**: 本 Task 保守地只允许 user scope 创建(system 预设仅由 bootstrap 注入)。PRD 未明确说 admin 可通过 API 创建 system scope,遵守最小授权原则。
- **验证结果**: 8 项验证全 PASS; scope 权限矩阵路径全部有代码实现
- **下游影响**: DOC-09 Task 9.2 实现更完整的 Provider 用量 API 时需对齐此 scope 语义

## ADR-011: config.capabilities 强制字段 + 内置预设 capabilities 声明(DOC-02 Task 2.3)
- **来源**: PRD v4 DOC-02 Task 2.3 Part A
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `backend/app/schemas/provider.py` — CreateProviderRequest.capabilities_required() @field_validator: 缺失 "capabilities" key → ValueError → FastAPI 422
  - `backend/app/services/provider_presets.py` — BUILTIN_PRESETS(8条): 每个 ProviderPreset 含 ProviderCapabilitiesSchema 实例
  - `backend/app/services/provider_service.py` — update_provider() 若传入 config 则二次校验 capabilities 存在
  - `backend/app/api/v1/providers.py` — GET /providers/presets 公开端点(无需认证)
- **实施 commit**: db89260
- **偏离点**: test_provider() 探测策略: Anthropic 协议发 cache_control 探测 prompt_cache; OpenAI 协议保守设 prompt_cache=False; vision/extended_thinking 保守 False(需人工确认)。
- **验证结果**: Pydantic 422 校验测试 PASS; BUILTIN_PRESETS[0].capabilities isinstance ProviderCapabilitiesSchema PASS
- **下游影响**: DOC-03 TAOR 主循环使用 ProviderManager.get_adapter() 时需要 capabilities 完整(影响 AnthropicDriver cache_control 注入行为)

## ADR-012: API Key AES-256-GCM 加密 + 掩码响应(DOC-02 Task 2.3)
- **来源**: PRD v4 DOC-02 Task 2.3 Part A; DOC-02 Task 2.1 ADR-004
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `backend/app/services/provider_service.py` — create_provider(): `encrypt_value(api_key, settings.ENCRYPTION_KEY)`; update_provider(): 同上; _to_response(): `decrypt_value(api_key_encrypted, settings.ENCRYPTION_KEY)` 仅用于生成掩码
  - `backend/app/schemas/provider.py` — `_mask_key()`: len<8 → '***'; else 首3 + '...' + 末4
  - `executor/adapters/provider_manager.py` — ProviderManager 只接受已解密明文 key(Backend 侧解密后注入)
- **实施 commit**: db89260
- **偏离点**: 复用 Task 2.1 已实现的 `security.encrypt_value` / `security.decrypt_value`(nonce:ciphertext hex 格式),未新增 encrypt_api_key / decrypt_api_key 函数(PRD Part B 示例为风格参考,实际以已有实现为准)。
- **验证结果**: 加密/解密 roundtrip PASS; 掩码逻辑 5 case 全 PASS
- **下游影响**: DOC-07 Task 7.4 子进程启动时需从 Backend 获取已解密的 API Key(通过参数或环境变量注入)

## ADR-013: 熔断器仅存 Redis + 多进程共享(DOC-02 Task 2.3)
- **来源**: PRD v4 DOC-02 Task 2.3 Part A
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `executor/adapters/provider_manager.py`:
    - key: `harness:circuit:{provider_id}`
    - value: JSON `{"failures": N, "opened_at": ts, "last_error": "..."}`
    - TTL: `CIRCUIT_BREAKER_RECOVERY_SECONDS` (setex)
    - CLOSED: key 不存在; OPEN: key 存在且 failures >= threshold; 恢复: DELETE key
    - record_failure(): 累计 → 达阈值触发熔断 + Prometheus prism_provider_healthy=0 + harness_event stub
    - record_success(): DELETE key + prism_provider_healthy=1
    - get_adapter(): 遍历 providers 按 (is_default, -priority) 选第一个 CLOSED; 切换时 prism_provider_failover_total +1
- **实施 commit**: db89260
- **偏离点**: Prometheus metrics 通过 executor.observability.metrics 导入(ImportError 时静默降级 — executor 侧 metrics 模块在 DOC-12 实现前不存在)。进程边界严格: ProviderManager 无任何 backend.app.* import。
- **验证结果**: 熔断状态机测试(FakeRedis mock): 3次失败触发熔断→切换备用→record_success恢复→主 Provider 重新选中 — 全 PASS
- **下游影响**: DOC-07 Task 7.3 实现 /internal/callback/harness_event 接收端; DOC-07 Task 7.4 实际启动子进程并传入解密后的 ProviderConfig 列表

---

## DOC-02 Task 2.4: Prompt 动态装配引擎(ADR-014 / ADR-015 / ADR-016 / ADR-017 第二次补强)

## ADR-014: PromptSection 对齐 CC 10+ getter 粒度(DOC-02 Task 2.4)
- **来源**: PRD v4 DOC-02 Task 2.4 Part A §设计决策
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `executor/engine/prompt_sections.py` — 21 个独立 section getter 函数（静态 9 + 动态 12）
  - `executor/engine/prompt_assembler.py` — PromptAssembler._build_static()（9 section）+ _build_dynamic()（12 section）
- **实施 commit**: 1463103
- **偏离点**: 无。21 个 section 全部落地，每个独立函数独立可测；`task_philosophy_section()` header 使用"任务哲学 & 执行原则"（包含 PRD 验证步骤断言的子串"任务哲学"）。
- **验证结果**: Section coverage PASS（任务哲学/工具使用/合规要求/输出规范 四个子串全在 prompt 中）；Section 函数计数 21 PASS
- **下游影响**: DOC-03 TAOR 主循环调用 PromptAssembler.build() 生成 system prompt；DOC-04 各 Agent 类型通过 agent_type 参数选择行为约束；DOC-05 Skill/MCP 通过 SkillInfo/MCPServerInfo 注入动态 section

## ADR-015: TokenEstimator Protocol + 精确 tokenizer 依赖注入(DOC-02 Task 2.4)
- **来源**: PRD v4 DOC-02 Task 2.4 Part A §设计决策（ADR-015 v4）
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `executor/engine/context_budget.py` — TokenEstimator Protocol（estimate + estimate_messages 两个方法）
  - `executor/engine/context_budget.py` — ContextBudgetManager.__init__(estimator: TokenEstimator)，必传参数
- **实施 commit**: 1463103
- **偏离点**: 无。TokenEstimator 为 Protocol（结构子类型），不是 ABC（不强制继承）。AnthropicDriver / OpenAIDriver 已实现 count_tokens()，DOC-12 Task 12.1 实现正式 TokenEstimator 适配器时需包装 count_tokens() 接口。
- **验证结果**: FakeEstimator 实现 Protocol 接口，ContextBudgetManager 构造成功，truncate/should_compress 方法 PASS
- **下游影响**: DOC-03 Task 3.5 Compaction Pipeline 使用 ContextBudgetManager(estimator=driver_adapter) 构造实例；DOC-12 Task 12.1 实现正式 TokenEstimator 包装器

## ADR-016: Compaction 按回合组（turn group）为原子单元裁剪(DOC-02 Task 2.4)
- **来源**: PRD v4 DOC-02 Task 2.4 Part A §设计决策（ADR-016 v4）；CLAUDE.md 陷阱 #2
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `executor/engine/context_budget.py` — ContextBudgetManager.identify_turn_groups()（按 user query 边界识别回合组）
  - `executor/engine/context_budget.py` — ContextBudgetManager.compress_history()（整组删除，绝不单独删除 assistant 或 tool_result）
- **实施 commit**: 1463103
- **偏离点**: 无。identify_turn_groups 严格按 PRD 定义："user query = role=user AND content 不含任何 tool_result block"。Part B 验证断言 groups == [(0, 3), (4, 5)] 通过。
- **验证结果**: Turn group identification PASS（精确匹配 [(0, 3), (4, 5)]）；compress_history 5 组场景测试 PASS
- **下游影响**: DOC-03 Task 3.5 Compaction Pipeline Tier 1-3 在 compress_history 骨架上实现 LLM 摘要替换；绝不破坏 tool_use ↔ tool_result 配对（防止 Anthropic API 400）

## ADR-017: is_skill_context 标记优先保留(DOC-02 Task 2.4 第二次补强)
- **来源**: PRD v4 DOC-02 Task 2.4 Part A §设计决策（ADR-017 v4）；DOC-05 ADR-042
- **实施状态**: ✅ 2026-04-18（第一次落地：Task 2.1 DB 字段；第二次落地：本 Task 运行时语义）
- **落地位置**:
  - `executor/engine/context_budget.py` — compress_history() 中 `elif getattr(msg, 'is_skill_context', False)` 保留路径
  - （复用）`executor/adapters/base.py` — PrismMessage.is_skill_context 字段（Task 2.2 落地）
  - （复用）`backend/app/models/message.py` — is_skill_context / skill_name DB 字段（Task 2.1 落地）
- **实施 commit**: 1463103
- **偏离点**: 无。is_skill_context 消息跨越回合组边界保留，即使整个回合组被删除，组内含 True 的消息也单独保留。
- **验证结果**: compress_history 5 组测试 + skill_context 消息在组 1（被裁剪）中仍保留 — PASS
- **下游影响**: DOC-05 Skill Level 2 注入逻辑写入 is_skill_context=True 时，Compaction 自动优先保留

---

## Phase 1: Agent 核心(DOC-03 Task 3.1 落地)

## ADR-020: Harness 单实例 — Backend 不持有 Harness 对象(DOC-03 Task 3.1)
- **来源**: PRD v4 DOC-03 Task 3.1 Part A §设计决策; Batch 2 §A3-1, Master M1
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `executor/engine/query_engine.py` — QueryEngine 只在 executor 子进程内实例化
  - `executor/__main__.py` — 主入口，Backend 通过 subprocess 启动（不 import Harness）
  - `executor/` 全目录 — 无任何 `from backend.app.*` import（Grep 验证 PASS）
- **实施 commit**: ce382a5
- **偏离点**: 无。进程边界严格执行：executor 侧不 import backend.app.*；backend 侧不持有 Harness 实例。
- **验证结果**: Grep 无 `from backend.app` in executor/ PASS
- **下游影响**: DOC-07 Task 7.4 子进程调度需通过命令行参数（--run-id / --callback-url 等）注入配置，不能共享 Python 对象

## ADR-021: 工具并行 gather(DOC-03 Task 3.1)
- **来源**: PRD v4 DOC-03 Task 3.1 Part A; PDF 补丁, Batch 2 §A3-1
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `executor/engine/query_engine.py` — `_execute_tools()`: `asyncio.gather(*tool_coros, return_exceptions=True)`
  - `executor/engine/query_engine.py` — `_execute_single_tool()`: 单工具执行，Pipeline 透传 run_context
- **实施 commit**: ce382a5
- **偏离点**: Phase 1 保守实现"全部并行"（无依赖声明检测）。DOC-04 Coordinator 模式下可精细化 `{{tool_result:X}}` 占位符依赖分析。结果按 block 顺序收集为单条 user message（canonical Anthropic 语义）。
- **验证结果**: 3×5s 工具并行总耗时 5.02s < 7s 断言 PASS
- **下游影响**: DOC-04 Task 4.3 Coordinator 实现细粒度依赖分析；Task 3.3 Hook/Permission 通过 run_context 参数接入

## ADR-022: Redis 直通 — text_delta/tool_use_delta 走 Redis PUBLISH(DOC-03 Task 3.1)
- **来源**: PRD v4 DOC-03 Task 3.1 Part A; Master M2, Batch 1 §3.3 D3; CLAUDE.md 陷阱 #1
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `executor/callbacks/backend_callback.py` — `text_delta()` / `tool_use_delta()` 走 `redis.publish("run:{run_id}:stream", ...)`
  - `executor/engine/query_engine.py` — `_ADAPTERS_WITH_PASSTHROUGH` frozenset 判断；Driver 已做直通则 no-op（不 double-publish）
- **实施 commit**: ce382a5
- **偏离点**: ProviderCapabilities 未添加 `redis_passthrough` 字段（避免改 Task 2.2 产物）。改为 QueryEngine 内 `_ADAPTERS_WITH_PASSTHROUGH = frozenset(["AnthropicDriver", "OpenAIDriver"])` 判断，通过 `type(self._adapter).__name__` 比较。语义等价，未来第三方 Adapter 只需从 frozenset 移除。
- **验证结果**: Redis PUBLISH mock 测试 PASS（channel=`run:test-run:stream`, payload type=text_delta）
- **下游影响**: DOC-07 Task 7.3 Backend SSE Manager 订阅 `run:{run_id}:stream` channel 并 forward 给前端

## ADR-023: 心跳机制 — 子进程每 5s SETEX harness:heartbeat:*(DOC-03 Task 3.1)
- **来源**: PRD v4 DOC-03 Task 3.1 Part A; Batch 2 §B-2, Batch 3 B3-2
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `executor/__main__.py` — `heartbeat_writer(run_id, redis_url, stop_event)` 协程 + `asyncio.create_task()` 启动
  - `executor/__main__.py` — HEARTBEAT_INTERVAL=5s, HEARTBEAT_TTL=60s（环境变量可覆盖）
  - `executor/__main__.py` — finally 块 DELETE key + aclose redis（graceful stop）
- **实施 commit**: ce382a5
- **偏离点**: 无。key 命名精确 `harness:heartbeat:{run_id}`，TTL=60，值=Unix 时间戳字符串。stop_event 触发后 finally 块优雅清理。
- **验证结果**: mock 测试 PASS（SETEX 多次调用，key/TTL 正确；stop 后 DELETE 被调用）
- **下游影响**: DOC-07 Task 7.3 Backend HeartbeatMonitor 每 10s SCAN `harness:heartbeat:*`，超 30s 无更新标记 Run crashed

## ADR-024: MAX_TURNS 按 agent_type 分档(DOC-03 Task 3.1)
- **来源**: PRD v4 DOC-03 Task 3.1 Part A; Batch 2 §A3-1, PDF 补丁
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `executor/__main__.py` — `MAX_TURNS_BY_AGENT_TYPE = {"chat":50,"explore":30,"build":100,"coordinator":200,"verifier":20,"plugin_builder":40}`
  - `executor/engine/query_engine.py` — `run()` 开头 `if self._turn_count >= self._max_turns: await callback.run_error(...)`
- **实施 commit**: ce382a5
- **偏离点**: 无。6 档精确对齐 PRD。默认兜底值 50（`MAX_TURNS_BY_AGENT_TYPE.get(agent_type, 50)`）。
- **验证结果**: len(MAX_TURNS_BY_AGENT_TYPE)==6 且 6 键全部存在 PASS；值逐一断言 PASS
- **下游影响**: DOC-04 Task 4.1 Agent 专业化时 agent_type 路由必须使用此常量；DOC-07 Task 7.4 subprocess 启动时通过 run.agent_type 查表

---

## DOC-03 Task 3.5: 4 级 Compaction Pipeline + 6 层 Memory（ADR-031 / ADR-032）

## ADR-031: Compaction 按回合组原子裁剪（DOC-03 Task 3.5）
- **来源**: PRD v4 DOC-03 Task 3.5 Part A ADR-029（PRD 笔误重号，本实现用 ADR-031 编号，见 blocker.md）
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `executor/engine/compaction.py` — CompactionPipeline._tier1_micro_compact()：identify_turn_groups() → 整组保留/删除，绝不按 index 单独裁
  - `executor/engine/compaction.py` — CompactionPipeline._tier2_auto_compact()：split_point=len(groups)//2，old_groups/recent_groups 均按组边界切分
  - `executor/engine/compaction.py` — CompactionPipeline.reactive_truncate()：groups[-3:] 整组保留
  - `executor/engine/context_budget.py`（Task 2.4）— identify_turn_groups() 识别边界（本 Task 不修改）
- **实施 commit**: ef26979
- **偏离点**: 无。tool_use↔tool_result 配对保证验证 PASS（Test 10：4组消息含 tool_use/tool_result，Tier1/Tier4 裁后 pairs 完整）
- **验证结果**: TEST 10 PASS（所有 tier 裁剪后 tool_use id 集合 == tool_result id 集合，无悬空对）
- **下游影响**: DOC-07 任何调用 CompactionPipeline 的上下文必须通过 identify_turn_groups() 识别组边界，不得手工按 index 裁

## ADR-032: is_skill_context 优先保留（DOC-03 Task 3.5）
- **来源**: PRD v4 DOC-03 Task 3.5 Part A ADR-030（PRD 笔误重号，本实现用 ADR-032 编号，见 blocker.md）
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `executor/engine/compaction.py` — Tier 1 _tier1_micro_compact()：`i in to_keep or getattr(msg, 'is_skill_context', False)` 保留逻辑
  - `executor/engine/compaction.py` — Tier 2 _tier2_auto_compact()：old_messages 排除 is_skill_context=True；result 末尾追加所有 skill_context
  - `executor/engine/compaction.py` — Tier 4 reactive_truncate()：`i in keep_indices or getattr(msg, 'is_skill_context', False)` 保留逻辑
- **实施 commit**: ef26979
- **偏离点**: 无。Tier 4 hint message is_skill_context=False（hint 本身不是 Skill 注入，可参与后续裁剪）
- **验证结果**: TEST 4 PASS（Tier1 保留 skill_context）；TEST 8 PASS（Tier4 保留 old group 的 skill_context）；TEST 5 PASS（Tier2 摘要后 skill_context 完整）
- **下游影响**: DOC-05 Skill 注入的 PrismMessage（is_skill_context=True）在所有 Compaction Tier 均被保留

---

---

## DOC-03 Task 3.6: Harness 配置 2 源简化（ADR-033）

## ADR-033: Harness 配置 2 源化 + 禁止运行时修改（DOC-03 Task 3.6）
- **来源**: PRD v4 DOC-03 Task 3.6 Part A ADR-031（PRD 原标 ADR-031，因与 DOC-03 Task 3.5 ADR-031「Compaction 回合组原子裁剪」冲突，本实现采用 ADR-033 编号）
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `executor/harness/defaults.py` — DEFAULT_PERMISSION_POLICIES（9 项：bash/Bash/Write/Edit/Read/Grep/WebFetch/WebSearch/skill_install）+ DEFAULT_MIDDLEWARE_CONFIG（4 项：loop_detection/rate_limit/feedback_capture/observability）+ DEFAULT_AGENT_CONSTRAINTS（6 种 agent type）
  - `executor/harness/config_loader.py` — HarnessEffectiveConfig dataclass（6 字段：custom_guardrail_rules/permission_policies/middleware_config/hook_registrations/agent_constraints/source_trace）+ HarnessConfigLoader.load()：先填默认打 source_trace="default"，再 yaml 覆盖打 "yaml"；yaml 缺失→default-only（不raise）；yaml 格式错误→raise RuntimeError（快速失败）；structlog `harness.config.loaded/load_failed`；Prometheus `prism_harness_config_load_total{source}`
  - `backend/app/api/v1/harness.py` — GET /config（readonly，require_admin）；PATCH/POST/DELETE 不注册→FastAPI 返回 405
  - `backend/app/api/v1/__init__.py` — include harness.router
  - `backend/requirements.txt` — pyyaml>=6.0
- **实施 commit**: 5381df3
- **偏离点**:
  - PRD 示例 yaml 用 `ask_user` 值，本实现统一为 `ask`（与 HookDecision.permission_decision Literal["allow","ask","deny"] 对齐）；yaml 中 ask_user 归一化为 ask（`.replace("ask_user","ask")`）
  - ADR 编号修正：PRD 原标 ADR-031 与 Task 3.5 ADR-031 冲突，故本 ADR 使用 033
  - config_file_path 从 os.environ.get("HARNESS_CONFIG_PATH","/app/config/harness_config.yaml") 读取（不硬编码）
  - Backend 侧 import executor.harness.config_loader 是允许的单向依赖（config_loader 纯 yaml+stdlib，不反向 import backend.app）
- **验证结果**: 10 项验证全部 PASS（py_compile 4文件/imports/default-only load/YAML override/YAML error raise/nonexistent path/router路由/GET响应结构/api_v1_router含harness.router/pyyaml in requirements）
- **下游影响**:
  - DOC-07 Task 7.4：subprocess 启动时调用 HarnessConfigLoader(config_file_path=...).load() 并将产物注入 HarnessRuntime（本 Task 只提供 loader，不做 HarnessRuntime 注入）
  - DOC-05 Task 5.x：Plugin install 时一次性写入 harness_config.yaml 的 plugins 段 + 重启

---

## Phase 2: Backend 模块(待实施)

> (占位)

---

## Phase 3: 前端(待实施)

> (占位)

---

## Phase 4: 运维封装(待实施)

> (占位)

---

---

## DOC-03 Task 3.2: Middleware Pipeline 4 钩点(ADR-025)

## ADR-025: Middleware 4 钩点 — 可插拔治理逻辑与 TAOR 循环分离(DOC-03 Task 3.2)
- **来源**: PRD v4 DOC-03 Task 3.2 Part A §设计决策; PDF 补丁, Batch 2 §A3-5
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `executor/harness/middleware/base.py` — MiddlewareContext dataclass(12 字段全部有 default，兼容短构造) + TurnContext 别名 + Middleware ABC(4 no-op 钩点方法)
  - `executor/harness/middleware/pipeline.py` — MiddlewarePipeline.register() + run_pre_turn/run_pre_tool_use(短路) + run_post_tool_use/run_post_turn(不短路)
  - `executor/harness/middleware/loop_detection.py` — LoopDetectionMiddleware: post_turn 检测 Redis list harness:loop:{run_id} 最近 N 轮 sha256 指纹，全同时 ctx.abort=True + callback.harness_event("loop_detected")
  - `executor/harness/middleware/observability.py` — ObservabilityMiddleware: pre_turn 记录 monotonic 起始时间，post_turn 上报 callback.harness_event("turn_complete", {turn, duration_ms, tool_calls})
  - `executor/harness/middleware/__init__.py` — 导出 6 个公共符号
  - `executor/engine/query_engine.py` — RunContext 追加 agent_type 字段; QueryEngine.__init__ 新增 middleware_pipeline/agent_type 参数; run() 注入 pre_turn/post_turn 钩点; _execute_single_tool() 注入 pre_tool_use/post_tool_use 钩点
- **实施 commit**: e174ea5
- **偏离点**:
  1. Part B 示例中 `ctx.metadata` 实为笔误，MiddlewareContext 字段名为 `custom_data`，以 base.py 定义为准。observability.py 使用 `ctx.custom_data.get("tool_call_count", 0)`。
  2. pre_turn 构造 MiddlewareContext 时 system_prompt 传空字符串（system prompt 在 assembler.build() 调用后才可用），可在后续 Task 通过在 build() 后更新 ctx 优化。
  3. LoopDetectionMiddleware 检测触发点改为 post_turn（不是 pre_tool_use），因为需要累积完整轮次数据后才能检测模式，符合 PRD Part A "在 post_turn 阶段检查" 语义。
- **验证结果**: 全部 10 项验证 PASS
  - py_compile 6 文件 PASS; 导入检查 PASS; TurnContext is MiddlewareContext PASS
  - 正常 pipeline / abort 短路 PASS; pre_tool_use 短路 / post_tool_use 不短路 PASS
  - LoopDetection mock Redis 3 轮相同触发 / 不同不触发 PASS
  - Observability duration_ms > 0 + tool_calls 正确 PASS
  - QueryEngine 集成 pre_turn×2 / post_turn×1 PASS; middleware=None 向后兼容 PASS
  - _execute_single_tool abort → pipeline.execute 不调用 + ToolResultBlock(is_error=True) PASS
  - grep no `from backend.app` in executor/harness/ PASS
- **下游影响**: DOC-03 Task 3.3 Hook System + Permission Engine 将在 pipeline.py 的 PreToolUse/PostToolUse HARNESS_INTEGRATION_POINT（步骤 3/7）实现，与 Middleware 钩点独立；Task 3.3 的 permission ask 需用 Redis BLPOP（CLAUDE.md 陷阱 #8）

> **最后更新**: 2026-04-18(DOC-03 Task 3.2 — Middleware Pipeline 4 钩点 + ADR-025)

---

## DOC-03 Task 3.4: Feedback Capture + HarnessRuntime 生命周期控制器(ADR-029 / ADR-030)

## ADR-029: Feedback 事件结构化(DOC-03 Task 3.4)
- **来源**: PRD v4 DOC-03 Task 3.4 Part A §设计决策; Batch 2 §A3-8
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `executor/harness/middleware/feedback_capture.py` — FeedbackEvent dataclass (event_type 5枚举 + severity 4枚举 + context dict + timestamp ISO 8601) + FeedbackCaptureMiddleware
  - `executor/harness/middleware/__init__.py` — 导出 FeedbackEvent / FeedbackCaptureMiddleware
  - `executor/observability/metrics.py` — prism_harness_feedback_total{event_type,severity} Counter + prism_harness_memory_extracted_total Counter
- **实施 commit**: affb44b
- **偏离点**: 无。event_type 严格 5 值，severity 严格 4 值，与 ADR-029 完全对齐。
- **验证结果**: 全部 12 项验证 PASS
  - tool_error 提取 / custom_data feedback_signals 追加 / get_run_summary 正确汇总 PASS
  - Redis SETEX TTL 7天 / redis_client=None 跳过 / Prometheus inc PASS
- **下游影响**: DOC-12 Task 12.2 Entropy Detector 扫描 Redis `feedback:{run_id}:{timestamp}` key

## ADR-030: SessionEnd user_memory 提炼(DOC-03 Task 3.4)
- **来源**: PRD v4 DOC-03 Task 3.4 Part A §设计决策; Batch 2 §A3-9
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `executor/harness/lifecycle.py` — HarnessRuntime.on_session_end(): turn_count>5 时 LLM complete → callback.harness_event("user_memory_extracted", {content, source_session_id, source_run_id})
  - `executor/observability/metrics.py` — prism_harness_memory_extracted_total
- **实施 commit**: affb44b
- **偏离点**:
  1. HarnessLifecycle Task 3.3 类名替换为 HarnessRuntime(PRD v4 Part B §2 原文类名)，保留 `HarnessLifecycle = HarnessRuntime` 别名。
  2. __init__ 参数从 Task 3.3 的 5 参数扩展为 8 参数 (run_id, session_id, user_id, callback, redis_client, redis_url, adapter, settings)。
  3. 异常捕获 log WARNING 不 raise，确保不影响主循环（on_session_end 失败不中断 run）。
- **验证结果**: 全部 12 项验证 PASS
  - turn_count=5 LLM 未调用 PASS; turn_count=10 LLM 调用 1 次 + memory callback PASS
  - LLM 异常 log WARNING + memory callback 未触发 PASS; source_session_id / content 字段正确 PASS
- **下游影响**: DOC-07 / DOC-09 Backend 端点写入 user_memories 表；PromptAssembler 后续读取

> **最后更新**: 2026-04-18(DOC-03 Task 3.4 — Feedback Capture + HarnessRuntime + ADR-029/030)
