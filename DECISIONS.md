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
| DOC-04 实施编号平移 | ADR-034 / ADR-035 / ADR-036 | Task 4.1 落地编号（PRD ADR-030/031/032 因 DOC-03 冲突平移至 ADR-034/035/036）|
| DOC-04 Task 4.2 实施编号平移 | ADR-037 / ADR-038 / ADR-039 | Task 4.2 落地编号（PRD ADR-033/034/035 因 DOC-03 Task 3.6 ADR-033 冲突，平移至 ADR-037/038/039）|
| DOC-04 Task 4.3 实施编号平移 | ADR-040 | Task 4.3 Coordinator Plan checkpoint（PRD ADR-036 因 DOC-04 Task 4.1 Verifier VERDICT 已占用 ADR-036，平移至 ADR-040）|
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

---

## DOC-04 Task 4.1: Agent 专业化定义 + AgentPool（ADR-034 / ADR-035 / ADR-036）

## ADR-034: agent-scoped MCP 白名单（DOC-04 Task 4.1）
- **来源**: PRD v4 DOC-04 Task 4.1 Part A ADR-030（PRD 原标 ADR-030，因 DOC-03 Task 3.4 已用 ADR-030，编号平移至 ADR-034）
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `executor/agents/base.py` — AgentDefinition.mcp_servers: list[str] | None 字段
  - `executor/agents/base.py` — AgentDefinition.filter_mcp_tools(all_mcp_tools) 方法：mcp_servers=None 时返回全部；非 None 时只返回白名单 server 的工具
- **实施 commit**: d04b909
- **偏离点**: 无。mcp_servers=None 语义为"不限制"，空列表语义为"禁止所有 MCP 工具"（隐含不同）。验证测试 PASS。
- **验证结果**: filter_mcp_tools([("srv1","t1"),("srv2","t2")]) 当 mcp_servers=["srv1"] 时返回 ["t1"] PASS；mcp_servers=None 时返回 ["t1","t2"] PASS
- **下游影响**: DOC-05 Task 5.2 MCP 双通道实现时，PromptAssembler 在组装 MCP 工具时调用 agent_def.filter_mcp_tools() 过滤

## ADR-035: agent-specific frontmatter skills（DOC-04 Task 4.1）
- **来源**: PRD v4 DOC-04 Task 4.1 Part A ADR-031（PRD 原标 ADR-031，因 DOC-03 Task 3.5 已用 ADR-031，编号平移至 ADR-035）
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `executor/agents/base.py` — AgentDefinition.frontmatter_skills: list[str] = [] 字段
  - 6 种 Agent 实例（general/explore/planner/verifier/coordinator/plugin_builder）均含此字段（默认空列表，表示对所有 agent_type 生效）
- **实施 commit**: d04b909
- **偏离点**: 无。Skill 的 frontmatter `agents: [research, explore]` 过滤逻辑在 DOC-05 Task 5.1 实现（本 Task 仅落地字段声明）。
- **验证结果**: AgentDefinition 含 frontmatter_skills 字段 PASS（通过 dataclass 字段检查）
- **下游影响**: DOC-05 Task 5.1 Skill 三级加载时，根据 agent_def.frontmatter_skills 白名单过滤可激活的 Skill

## ADR-036: Verifier VERDICT 协议强制（DOC-04 Task 4.1）
- **来源**: PRD v4 DOC-04 Task 4.1 Part A ADR-032（PRD 原标 ADR-032，因 DOC-03 Task 3.5 已用 ADR-032，编号平移至 ADR-036）
- **实施状态**: ✅ 2026-04-18
- **落地位置**:
  - `executor/agents/verifier.py` — VERIFIER_SYSTEM_PROMPT 完整原文（含 try to break it 使命 + 两种失败模式 + 4 类专项验证 Frontend/Backend/CLI/Migration + VERDICT 三态格式）
  - `executor/agents/verifier.py` — VERIFIER_AGENT.behavior_constraints = VERIFIER_SYSTEM_PROMPT
  - `executor/agents/verifier.py` — VERIFIER_AGENT.output_format 明确要求以 VERDICT: PASS|FAIL|PARTIAL 结尾
- **实施 commit**: d04b909
- **偏离点**: 无。VERIFIER_SYSTEM_PROMPT 99% 按 PRD Part B 原文保留，仅将 ASCII 引号统一为中文标点（保持中文文档一致性）。VERDICT 三态协议完整注入。
- **验证结果**: behavior_constraints 含 "VERDICT" PASS；含 "try to break" PASS；含 "Frontend"/"Backend"/"CLI"/"Migration" 4 类 PASS
- **下游影响**: DOC-04 Task 4.4 TaskRouter 路由到 verifier 时，PromptAssembler 使用 VERIFIER_AGENT.behavior_constraints 注入 VERDICT 协议；DOC-05 Task 5.3 Hook 4 handler 可读取 VERDICT 状态

---

---

## DOC-04 Task 4.2: Fork & Context Isolation（ADR-037 / ADR-038 / ADR-039）

## ADR-037: Fork capability-based 工具白名单（DOC-04 Task 4.2）
- **来源**: PRD v4 DOC-04 Task 4.2 Part A ADR-033（PRD 原标 ADR-033，因 DOC-03 Task 3.6 已用 ADR-033，编号平移至 ADR-037）
- **实施状态**: ✅ 2026-04-19
- **落地位置**:
  - `executor/tools/base.py` — BaseTool.capabilities: list[str] = []（class-level 默认空列表，子类 override）
  - `executor/tools/builtin/fork.py` — ForkTool.capabilities = ["fork_agent"]
  - `executor/agents/base.py` — AgentDefinition.allowed_capabilities: list[str] 字段
  - `executor/coordinator/fork_manager.py` — ForkManager._create_filtered_registry()：allowed_caps 空时保留所有工具；非空时 tool_caps.issubset(allowed_caps) 过滤
  - `executor/tools/registry.py` — ToolRegistry.list_all() 方法（返回 BaseTool 实例列表，过滤源）
- **实施 commit**: a61991d
- **偏离点**: 无。空 allowed_caps 语义"不限制"与 allowed_tools=None 保持一致（父 Agent 行为）。
- **验证结果**: 4 个过滤场景 PASS（单 cap 过滤/空列表保留所有/None 保留所有/多 cap 两工具）
- **下游影响**: DOC-04 Task 4.3 Coordinator 调用 ForkManager.fork() 时，根据子任务需求传入 required_capabilities 限制子 Agent 工具

## ADR-038: Fork 3 条 prompt-level 硬约束（DOC-04 Task 4.2）
- **来源**: PRD v4 DOC-04 Task 4.2 Part A ADR-034（PRD 原标 ADR-034，平移至 ADR-038）
- **实施状态**: ✅ 2026-04-19
- **落地位置**:
  - `executor/coordinator/fork_briefing.py` — FORK_HARD_CONSTRAINTS 常量（3 条：禁止覆盖 model / 禁止偷窥 outputFile / 禁止预言结果）
  - `executor/coordinator/fork_manager.py` — _create_child_assembler()：inject_constraints=True 时设 child._extra_dynamic_tail = FORK_HARD_CONSTRAINTS
  - `executor/engine/prompt_assembler.py` — PromptAssembler.__init__ 追加 _extra_dynamic_tail: str | None = None；_build_dynamic() 末尾 if self._extra_dynamic_tail: sections.append(self._extra_dynamic_tail)
- **实施 commit**: a61991d
- **偏离点**: 无。3 条约束文本 99% 按 PRD 原文，微调中文标点（禁止偷窥/禁止预言完整保留）。_extra_dynamic_tail 字段不影响非 Fork 的 PromptAssembler（默认 None，不注入）。
- **验证结果**: _extra_dynamic_tail 注入验证 PASS（TEST_TAIL 在 prompt 末尾）；3 条约束内容 grep PASS
- **下游影响**: DOC-04 Task 4.3 Coordinator 通过 ForkManager 派生子 Agent 时，子 Agent 的 system prompt 自动含 3 条约束；不影响主 Agent

## ADR-039: ForkBriefing 结构化 6 字段（DOC-04 Task 4.2）
- **来源**: PRD v4 DOC-04 Task 4.2 Part A ADR-035（PRD 原标 ADR-035，平移至 ADR-039）
- **实施状态**: ✅ 2026-04-19
- **落地位置**:
  - `executor/coordinator/fork_briefing.py` — ForkBriefing dataclass（6 字段：goal/why/excluded/context/expected_output/file_references）+ to_prompt()（6 markdown section 标题）
  - `executor/coordinator/fork_result.py` — ForkResult dataclass（9 字段，含 briefing: ForkBriefing）
  - `executor/coordinator/fork_manager.py` — ForkManager.fork() 接受 briefing: ForkBriefing；child_engine.run(briefing.to_prompt())
  - `executor/tools/builtin/fork.py` — ForkTool.execute() 从 tool_input 构造 ForkBriefing（goal 必填，其他可选）；input_schema 对齐 ForkBriefing 6 字段
  - `executor/coordinator/__init__.py` — 导出 ForkBriefing, ForkResult, ForkManager, ForkDepthExceeded, FORK_HARD_CONSTRAINTS
- **实施 commit**: a61991d
- **偏离点**: ForkTool input_schema 保留 "agent_type"/"goal" 为 required，其余 4 字段为 optional（对应 ForkBriefing 的 field(default_factory=list)/默认 "" 字段）。ForkDepthExceeded 定义在 fork_manager.py 顶部（非独立文件，符合 Task 指令）。
- **验证结果**: ForkBriefing.to_prompt() 6 section 标题全部存在 PASS；ForkResult 9 字段验证 PASS；ForkTool.execute() success/fail 两路径 PASS
- **下游影响**: DOC-04 Task 4.3 Coordinator 必须通过 ForkBriefing 6 字段传递任务入参，不允许回退为 free-form string；DOC-07 Task 7.4 日志记录 ForkBriefing.goal（前 200 字）作为 fork_start 事件

---

---

## DOC-04 Task 4.3: Coordinator + Plan checkpoint（ADR-040）

## ADR-040: Coordinator Plan checkpoint 持久化 + 崩溃恢复（DOC-04 Task 4.3）
- **来源**: PRD v4 DOC-04 Task 4.3 Part A ADR-036（PRD 原标 ADR-036，因 DOC-04 Task 4.1 Verifier VERDICT 已占用 ADR-036，平移至 ADR-040）
- **实施状态**: ✅ 2026-04-19
- **落地位置**:
  - `executor/coordinator/plan.py` — Plan/PlanStep dataclass + `parse_from_text()`(两级解析: JSON 围栏代码块/裸 JSON → markdown 列表 `[agent] desc` → 单步 general fallback) + `serialize_plan/deserialize_plan`(asdict 持久化) + `_normalize_agent_type`(research→explore 别名兼容)
  - `executor/engine/synthesizer.py` — Synthesizer.synthesize()(模板化:`## 任务完成 + **目标** + ### desc/result` )
  - `executor/coordinator/coordinator.py` — Coordinator.__init__(plan_id + resume_from_step) + execute(existing_plan 可选) + resume_from_checkpoint(classmethod 读 coordinator_plans 表) + _plan(Fork Planner) + _build_step_context(注入已完成步骤前 500 字)
  - Checkpoint 时序: (1)初始 `coordinator_plan_update(plan_json, current_step, total_steps, status='running')` → (2)每 step 开始前 `coordinator_plan_update(current_step=i)` + `harness_event("step_start")` → (3)step 完成后 fork/synthesis + `harness_event("step_end")` → (4)最终 `coordinator_plan_update(status='completed')`
  - `executor/coordinator/__init__.py` — 导出 Plan / PlanStep / serialize_plan / deserialize_plan / Coordinator
- **实施 commit**: c0f394d
- **偏离点**:
  - ADR 编号从 PRD 原标 036 平移到 040（见 blocker.md 编号平移链）
  - resume_from_checkpoint 签名改为返回 `(Coordinator, Plan)` 元组(PRD 原版只返 Coordinator 实例，但 resume 路径 execute(user_prompt, existing_plan=plan) 需要 Plan 实例，合并返回避免二次 DB 查询)
  - `_serialize_plan` 从 Part B 内联助手提升为 `plan.serialize_plan()` 模块级函数（便于 reuse + unit test）
- **验证结果**: 全部 6 项 PASS
  - py_compile 3 文件 PASS
  - Plan construction(2 steps 断言) PASS
  - Synthesizer 模板(task_summary + desc 包含) PASS
  - parse_from_text JSON(research→explore 规范化) PASS
  - parse_from_text markdown(2 步 `[research]`/`[general]`) PASS
  - parse_from_text fallback(自由文本 → 单步 general) PASS
  - serialize/deserialize roundtrip PASS
  - Coordinator execute single-step(fork 1 次，直返 synthesis) PASS
  - Coordinator execute multi-step(4 次 plan_update + 2 次 step_start + 2 次 step_end) PASS
  - Coordinator execute resume_from_step=1(只 fork 第 2 步，跳过已完成) PASS
  - grep `from backend.app` in executor/coordinator + executor/engine/synthesizer.py: 0 命中 PASS
- **下游影响**:
  - DOC-07 Task 7.3 回调端点需实现 `coordinator_plan_update` 事件处理（UPSERT coordinator_plans 表 current_step_index + plan_json + status）
  - DOC-07 Task 7.4 CoordinatorRecoveryService 子进程重启时传 `--resume-from-step=N` → `Coordinator.resume_from_checkpoint(plan_id, db)` 恢复
  - DOC-04 Task 4.4 TaskRouter 判定复杂任务时 → 切换 Coordinator 模式(Planner 拆解 → 本 Task 实现的 execute)

---

---

## DOC-04 Task 4.4: TaskRouter 6 agent_type + keyword routing（ADR-041）

## ADR-041: TaskRouter Phase 1 关键词路由——确定性规则优先，Phase 2 升级 LLM 分类（DOC-04 Task 4.4）
- **来源**: PRD v4 DOC-04 Task 4.4 Part A ADR-037（PRD 原标 ADR-037，因 DOC-04 Task 4.2 Fork capability-based 已占用 ADR-037，平移至 ADR-041）
- **实施状态**: ✅ 2026-04-19
- **落地位置**:
  - `executor/router.py` — TaskRouter 类 + RouteDecision dataclass（mode/agent_type/reason 3字段）+ COORDINATOR_PATTERNS（11条，中英文）+ AGENT_TYPE_PATTERNS（4种：explore/planner/verifier/plugin_builder，含中英文关键词）+ AGENT_TYPE_ALIASES（3条别名：chat→general/research→explore/build→general）
  - `executor/__main__.py` — 追加 `from executor.router import TaskRouter` import + routing stub（commented，待 DOC-07 Task 7.4 DB 集成后激活）
- **实施 commit**: f0c373e
- **偏离点**:
  - ADR 编号从 PRD 原标 037 平移到 041（见 blocker.md 编号平移链；037 已被 DOC-04 Task 4.2 占用）
  - PRD Part B 验证步骤 line 1548 断言 `r.agent_type == 'research'`（PRD 内部笔误），实际 AGENT_TYPE_PATTERNS key 为 `"explore"`（Task 4.1 canonical type），验证断言修正为 `== 'explore'`；AGENT_TYPE_ALIASES 提供 research→explore 别名映射，通过 explicit_agent_type 路径规范化
  - Phase 2 LLM fallback（Haiku 意图分类）仅在 Part A 声明，本 Task 不实现（注释说明）
  - 文件路径：PRD Part B 顶部目录图标注 `executor/router.py`（非 `executor/routing/task_router.py`），按 Part B 落地
- **验证结果**: 全部 8 项 PASS
  - py_compile executor/router.py PASS
  - Simple task direct/general PASS
  - Search task direct/explore PASS
  - Verify task direct/verifier PASS
  - Complex task coordinator PASS
  - Explicit planner PASS
  - plugin_builder keyword PASS
  - alias research→explore PASS
  - alias chat→general PASS
  - py_compile executor/__main__.py PASS
  - grep `from backend.app` in router/main: 0 命中 PASS
- **下游影响**:
  - DOC-07 Task 7.4：子进程入口激活 TaskRouter 路由（取消 __main__.py 中的注释，从 DB 读取 run.prompt + run.agent_type）
  - DOC-04 Task 4.5：PluginBuilder 由 AGENT_TYPE_PATTERNS["plugin_builder"] 路由，无需 Coordinator 模式
  - DOC-12 Task 12.x：RouteDecision.reason 写入 audit_logs（当前仅 stub，DOC-07 实现后激活）

---

## DOC-04 Task 4.5: PluginBuilder 完整度打分 + 动态轮数（ADR-042）

## ADR-042: PluginBuilder 需求完整度打分——7 维度加权，overall ≥ 0.8 触发生成（DOC-04 Task 4.5）
- **来源**: PRD v4 DOC-04 Task 4.5 Part A ADR-038（PRD 原标 ADR-038，因 DOC-04 Task 4.2 Fork 3 硬约束已占用 ADR-038，平移至 ADR-042）
- **实施状态**: ✅ 2026-04-19
- **落地位置**:
  - `executor/agents/plugin_builder_scoring.py`（新文件）— RequirementCompleteness 类（7 维度 CRITERIA dict，THRESHOLD=0.8，score() async LLM 打分，_record_completeness Prometheus，structlog 事件 agent.plugin_builder.completeness_scored）+ get_missing_dimension_question() + PluginBuilderAgent（run() 打分循环，_present_design stub，_wait_for_user_reply stub）
  - `executor/agents/plugin_builder.py`（修改）— PLUGIN_BUILDER_AGENT 更新为 v4 AgentDefinition（max_turns=40，output_format=structured_dialogue，behavior_constraints v4 修订文本）+ PLUGIN_BUILDER 别名
  - `executor/harness/middleware/plugin_builder_gate.py`（新文件）— PluginBuilderGate Middleware（pre_turn 阶段门控：phase 1 < 0.8 注入 constraint；phase 1 ≥ 0.8 升至 phase 2；phase 2 未 confirmed 注入约束）+ pre_tool_use（阶段 1/2 阻止写 plugin 文件）+ _is_plugin_file 检测函数 + GR_PLUGIN_CREATE_GUARD（scope="tier" 可配置降级）
  - `executor/router.py`（修改）— PLUGIN_BUILDER_PATTERNS（4 条中英文正则）+ route() 步骤 3a 正则优先于关键词表 + AGENT_TYPE_PATTERNS["plugin_builder"] 扩充 14 项关键词
  - `executor/harness/middleware/__init__.py`（修改）— 导出 PluginBuilderGate / GR_PLUGIN_CREATE_GUARD
- **实施 commit**: 0a43a39
- **偏离点**:
  1. ADR 编号从 PRD 原标 038 平移到 042（见 blocker.md 编号平移链）
  2. PluginBuilderAgent._wait_for_user_reply() 为 stub（NotImplementedError），实际 SSE 回复等待依赖 DOC-07 Task 7.3 的 callback/BLPOP 机制；_present_design() 返回 stub dict
  3. Prometheus histogram 采用 lazy init + 降级安全（导入失败不影响主路径）
  4. GR_PLUGIN_CREATE_GUARD 在 plugin_builder_gate.py 中声明但不自动注入 GuardrailsEngine；注入时机为 DOC-05 Task 5.3 Hook 治理或 Harness Runtime 初始化时（TODO stub）
- **验证结果**: 全部验证 PASS
  - py_compile 3 文件 PASS
  - 高分 scores overall=0.85 ≥ 0.8 PASS；低分 overall=0.30 < 0.8 PASS
  - CRITERIA 权重之和=1.00 PASS；THRESHOLD=0.8 PASS
  - 中文路由"帮我创建一个金融分析插件" → plugin_builder PASS
  - 英文路由"please create a new plugin for X" → plugin_builder PASS
  - PluginBuilderGate phase 1 低分注入 constraint PASS；高分升至 phase 2 PASS
  - Phase 2 未确认注入约束 PASS；非 plugin_builder Agent no-op PASS
  - _is_plugin_file 检测 plugin.yaml/SKILL.md/hooks/ PASS
  - GR_PLUGIN_CREATE_GUARD block 非 plugin_builder / allow plugin_builder PASS
  - grep `from backend.app` in 3 新增文件: 0 命中 PASS
- **下游影响**:
  - DOC-05 Task 5.3：Hook 治理时注入 GR_PLUGIN_CREATE_GUARD 到 GuardrailsEngine
  - DOC-07 Task 7.3：实现 _wait_for_user_reply() 的 SSE/BLPOP 机制（激活 PluginBuilderAgent.run()）
  - DOC-12 Task 12.4：prism_plugin_builder_completeness_histogram Prometheus 指标接入 Grafana

---

## DOC-05 Task 5.1: Skill 三级加载（ADR-043 / ADR-044 / ADR-045）

## ADR-043: Skill 三级加载规范（Level 0 注册 / Level 1 描述注入 / Level 2 完整按需加载）（DOC-05 Task 5.1）
- **来源**: PRD v4 DOC-05 Task 5.1 Part A ADR-040（PRD 原标 ADR-040，因 DOC-04 Task 4.3 Coordinator Plan checkpoint 已占用 ADR-040，平移至 ADR-043）
- **实施状态**: ✅ 2026-04-19
- **落地位置**:
  - `executor/plugins/skill_types.py` — SkillMetadata / SkillContent 数据类
  - `executor/plugins/skill_loader.py` — SkillLoader 三级加载器（scan_and_register / get_descriptions_for_prompt / try_trigger / load_skill / unload_skill / unload_all）
  - `executor/plugins/__init__.py` — 导出 SkillMetadata / SkillContent / SkillLoader
  - `plugins/skills/.gitkeep` — Skill 存放目录占位
  - `pyproject.toml` — 追加 pyyaml>=6.0
- **实施 commit**: (本 Task commit)
- **偏离点**:
  1. ADR 编号从 PRD 原标 040 平移到 043（见 blocker.md 编号平移链）
  2. HookSystem Phase 1 无 unregister-by-id 接口；_unregister_skill_hooks() 记录日志 + 清除本地 id 映射，实际从 HookSystem 注销留给 DOC-05 Task 5.3 扩展
  3. PRD Part B 中 hook 注册代码示例是注释掉的 stub，本实现根据 HookSystem.register() 签名做了真实注册（hook_system 非 None 时）
- **验证结果**: 全部 7 项验证 PASS
  - py_compile skill_types.py / skill_loader.py PASS
  - Level 0 注册 'test-skill' in registry PASS
  - Level 1 get_descriptions_for_prompt 包含 test-skill + 触发词 PASS
  - Trigger 匹配 '帮我测试一下' → ['test-skill'] PASS
  - Trigger 不匹配 '帮我翻译' → [] PASS
  - Level 2 load_skill is_loaded=True，body 包含 '完整内容' PASS
  - 已加载不重复触发 PASS；unload 清除 PASS
  - grep `from backend.app` in executor/plugins/: 0 命中 PASS
- **下游影响**:
  - DOC-05 Task 5.3：HookSystem 扩展 unregister_by_id()，激活 _unregister_skill_hooks() 真实清除
  - DOC-05 Task 5.4：PluginHost 集成 SkillLoader，管理 Skill 生命周期
  - DOC-05 Task 5.5/5.6：SkillRegistry 多源聚合后需更新 SkillLoader._registry

## ADR-044: Skill 匹配时强制执行（frontmatter.agents 字段过滤 + skill_mentioned_not_loaded 审计）（DOC-05 Task 5.1）
- **来源**: PRD v4 DOC-05 Task 5.1 Part A ADR-041（PRD 原标 ADR-041，因 DOC-04 Task 4.1 MCP 白名单已占用 ADR-035，frontmatter skills 已占用 ADR-035，平移至 ADR-044）
- **实施状态**: ✅ 2026-04-19
- **落地位置**:
  - `executor/plugins/skill_loader.py` — `_filter_by_agent()` 按 frontmatter.agents 过滤可见 Skill
  - `executor/plugins/skill_loader.py` — `emit_mentioned_not_loaded()` 触发 skill_mentioned_not_loaded structlog warning（audit=True）
  - `executor/plugins/skill_types.py` — SkillMetadata.agents 字段
- **实施 commit**: (本 Task commit)
- **偏离点**: emit_mentioned_not_loaded() 由调用方（QueryEngine / Middleware）主动调用，非 SkillLoader 自行检测（SkillLoader 无 messages 上下文）
- **验证结果**: PASS
  - agents=[] 全 agent 可见 PASS；agents=['explore'] 仅 explore 可见、general 不可见 PASS
  - emit_mentioned_not_loaded 触发 warning 日志 PASS
- **下游影响**: DOC-03 QueryEngine 或 DOC-05 Task 5.3 Hook 可订阅 skill_mentioned_not_loaded 事件补充处理

## ADR-045: is_skill_context=True 标记 Level 2 加载的 user message（DOC-05 Task 5.1）
- **来源**: PRD v4 DOC-05 Task 5.1 Part A ADR-042（PRD 原标 ADR-042，因 DOC-04 Task 4.5 PluginBuilder 打分已占用 ADR-042，平移至 ADR-045）
- **实施状态**: ✅ 2026-04-19
- **落地位置**:
  - `executor/plugins/skill_loader.py` — load_skill() 文档 + structlog 标注 is_skill_context=True
  - `executor/adapters/base.py` — PrismMessage.is_skill_context 字段（Task 2.2 已落地）
  - `executor/engine/compaction.py` — is_skill_context=True 消息 Compaction 优先保留（Task 3.5 已落地 ADR-032）
- **实施 commit**: (本 Task commit)
- **偏离点**: Level 2 产生的 user message 由调用方构造（SkillLoader.load_skill() 返回 SkillContent，调用方负责 PrismMessage(role='user', is_skill_context=True, skill_name=name) 构造并插入 messages）。SkillLoader 只保证 SkillContent.is_loaded=True 语义一致。
- **验证结果**: PASS（structlog is_skill_context=True 日志确认）
- **下游影响**: DOC-05 Task 5.4 PluginHost 在注入 skill message 时设置 is_skill_context=True

---

## DOC-05 Task 5.2: MCP Server 双通道 + scope（ADR-046 / ADR-047）

## ADR-046: MCP instructions 双通道注入（Registry instructions + Tool instructions）（DOC-05 Task 5.2）
- **来源**: PRD v4 DOC-05 Task 5.2 Part A ADR-044（PRD 原标 ADR-044，因 DOC-05 Task 5.1 agents过滤已占用 ADR-044，平移至 ADR-046）
- **实施状态**: ✅ 2026-04-19
- **落地位置**:
  - `executor/plugins/mcp_client.py` — MCPClient.start() 从 initialize 响应提取 `instructions`（第一通道：Registry instructions → PromptAssembler `<mcp_instructions>` section）
  - `executor/plugins/mcp_client.py` — MCPToolWrapper.description 返回 mcp_tool["description"]（第二通道：Tool instructions → tool_grammar_section）
  - `executor/engine/prompt_assembler.py` — 新增 invalidate_static_cache() + update_tools()：MCP 工具注册后调用 update_tools() 使 _static_cache=None/_tools_hash=None，下次 build() 重建静态 section 含新工具列表
  - `executor/plugins/__init__.py` — 导出 MCPClient / MCPToolWrapper / filter_mcp_tools_for_agent / SCOPE_SYSTEM / SCOPE_USER
- **实施 commit**: (本 Task commit)
- **偏离点**:
  1. 异步修复 (P0)：Part A 明确要求使用 asyncio.create_subprocess_exec + process.stdout.readline()（非阻塞），Part B 示例代码使用 subprocess.Popen（阻塞），本实现按 Part A P0 要求采用 asyncio 版本，避免阻塞事件循环。
  2. ADR 编号从 PRD 原标 044 平移到 046（见 blocker.md 编号平移链）
  3. update_tools() 同时置 _tools_hash=None（双重失效），确保 get_static_prefix() 路径也强制重建，不仅依赖 _static_cache=None
- **验证结果**: Part B 全部 3 项验证 PASS
  - Cache hit：get_static_prefix() is static1（同对象引用）PASS
  - Cache invalidation：update_tools() 后 assembler._static_cache is None PASS
  - New tools in prompt：re-build 后 'mcp__search__web' in prompt3 PASS
- **下游影响**:
  - DOC-05 Task 5.4 PluginHost 启动时调用 update_tools() 将 MCP 工具列表同步给 PromptAssembler
  - DOC-05 Task 5.3 Hook 治理：MCP 工具注册/注销事件可触发 hook → 调用 invalidate_static_cache()
  - DOC-09 Task 9.1 MCP Server 管理端点负责 Backend 侧 CRUD（executor 侧 MCPClient 在子进程内，不 import backend.app）

## ADR-047: agent-scoped MCP 白名单（AgentDefinition.mcp_servers 过滤）（DOC-05 Task 5.2）
- **来源**: PRD v4 DOC-05 Task 5.2 Part A ADR-045（PRD 原标 ADR-045，因 DOC-05 Task 5.1 is_skill_context 标记已占用 ADR-045，平移至 ADR-047）
- **实施状态**: ✅ 2026-04-19
- **落地位置**:
  - `executor/plugins/mcp_client.py` — MCPClient.scope（"system"|"user"，对齐 McpServer.scope 字段）
  - `executor/plugins/mcp_client.py` — MCPClient.list_mcp_tool_pairs()：返回 [(server_name, tool_name)] 列表
  - `executor/plugins/mcp_client.py` — filter_mcp_tools_for_agent(all_clients, mcp_servers_whitelist)：汇总所有 client 的工具对，按白名单过滤
  - `executor/agents/base.py` — AgentDefinition.filter_mcp_tools()（Task 4.1 已落地 ADR-034/035）：接收 [(server_name, tool_name)] 列表，按 mcp_servers 白名单返回允许的 tool_name
- **实施 commit**: (本 Task commit)
- **偏离点**: filter_mcp_tools_for_agent() 是辅助函数（非方法），调用链为：all_clients → list_mcp_tool_pairs() → filter_mcp_tools_for_agent() → AgentDefinition.filter_mcp_tools()。后者在 Task 4.1 已实现，本 Task 补全前两步。
- **验证结果**: PASS
  - filter_mcp_tools_for_agent([client1, client2], None)：返回全部 3 个工具对 PASS
  - filter_mcp_tools_for_agent([client1, client2], ['github'])：只返回 github 的 2 个工具对 PASS
  - AgentDefinition.filter_mcp_tools(all_pairs)：github 白名单 → send_message 被过滤 PASS
- **下游影响**:
  - DOC-04 Task 4.2 Fork：子 Agent ToolRegistry 创建时调用此过滤链，确保 Fork 后子 Agent 只能看到白名单 MCP 工具
  - DOC-05 Task 5.4 PluginHost：统一管理 MCPClient 列表，启动时调用 filter_mcp_tools_for_agent 为每个 agent_type 生成工具子集

---

## DOC-05 Task 5.3: Hook 治理层与 Plugin 命名空间（ADR-048 / ADR-049）

## ADR-048: HookSystem 优先级排序 + Phase 1 事件过滤 + scoped 注销（DOC-05 Task 5.3）
- **来源**: PRD v4 DOC-05 Task 5.3 Part A ADR-043（PRD 原标 ADR-043，因 DOC-05 Task 5.1 Skill 三级加载规范已占用 ADR-043，平移至 ADR-048）
- **实施状态**: ✅ 2026-04-19
- **落地位置**:
  - `executor/harness/hooks/events.py` — 新增 `PHASE1_EVENTS: frozenset[str]`（8 事件）+ `PHASE2_EVENTS: frozenset[str]`（13 事件，预留）
  - `executor/harness/hooks/system.py` — HookSystem 重构：
    - `_handlers: dict[str, list[tuple[int, str, HookHandlerConfig]]]` 改为三元组存储（priority, hook_id, config）
    - `register(event_type, config, hook_id="", priority=100) -> str`：自动生成 hook_id，按 priority 升序排序
    - `unregister(hook_id: str)` 精确注销
    - `unregister_by_prefix(prefix: str)` 前缀批量注销（Skill/Plugin 卸载）
    - `fire()` 入口校验 `event_type not in PHASE1_EVENTS` → 直接返回空 HookDecision
  - `executor/harness/hooks/__init__.py` — 新增导出 PHASE1_EVENTS / PHASE2_EVENTS
  - `executor/plugins/skill_loader.py` — `_register_skill_hooks()` 传 hook_id 给 `register()`；`_unregister_skill_hooks()` 调用 `unregister_by_prefix("skill:{skill_name}:")`（解决 Task 5.1 TODO stub）
- **实施 commit**: (见 git log)
- **偏离点**:
  1. PRD Part B 验证脚本中 `from executor.harness.hooks.events import HookEvent, HookDecision` 为 PRD 笔误（HookDecision 在 decision.py 非 events.py）；验证用修正后的正确 import 路径通过。
  2. register() 接受 config=None（用于测试用例），内部对 config is None 时安全取 type/matcher 字段。
- **验证结果**: 全部验证 PASS
  - py_compile 3 文件 PASS
  - PHASE1_EVENTS=8 / PreToolUse in / SubAgentStart not in / SubAgentStart in PHASE2_EVENTS PASS
  - 优先级排序 high/mid/low PASS
  - unregister_by_prefix 保留 global:compliance / 移除 2 条 skill:finance: PASS
  - PluginNamespace qualify/unqualify/is_mcp_tool PASS
- **下游影响**:
  - DOC-05 Task 5.4 PluginHost 调用 `hook_system.unregister_by_prefix(f"plugin:{plugin_name}:")` 完成 Plugin 级注销
  - DOC-05 Task 5.4 MCP 工具注册/注销时可 fire "PreToolUse" Phase 1 事件通知 HookSystem

## ADR-049: Plugin 命名空间（冒号分隔，避免跨 Plugin 名称冲突）（DOC-05 Task 5.3）
- **来源**: PRD v4 DOC-05 Task 5.3 Part A §CC 架构映射；ADR-043 原文描述 Plugin 命名约定
- **实施状态**: ✅ 2026-04-19
- **落地位置**:
  - `executor/plugins/namespace.py` — PluginNamespace 类：
    - `qualify(resource_name) -> str`：加前缀，MCP 工具（mcp__ 开头）不加前缀
    - `unqualify(qualified_name) -> tuple[str, str]`：拆分为 (plugin_name, resource_name)
    - `is_mcp_tool(name) -> bool`：静态方法
    - `build_qualified(plugin_name, resource_name) -> str`：静态构造工具
  - `executor/plugins/__init__.py` — 导出 PluginNamespace
- **实施 commit**: (见 git log)
- **偏离点**: 无。命名约定 `{plugin_name}:{resource_name}` 严格按 PRD 描述实现；MCP 工具 mcp__{server}__{tool} 格式绕过命名空间（DOC-05 Task 5.2 ADR-047 已定义）。
- **验证结果**: PluginNamespace qualify/unqualify/is_mcp_tool 全 PASS
- **下游影响**:
  - DOC-05 Task 5.4 PluginHost 加载 Plugin 时使用 PluginNamespace 实例管理资源命名
  - DOC-05 Task 5.5 SkillRegistry 注册 Skill 时使用 qualify() 生成命名空间限定名

---

## DOC-05 Task 5.4: PluginHost 统一管理 + 变量替换系统（ADR-050）

## ADR-050: PluginHost 统一生命周期 + Plugin 变量替换系统（DOC-05 Task 5.4）
- **来源**: PRD v4 DOC-05 Task 5.4 Part A ADR-046（PRD 原标 ADR-046；注意 DOC-06 也预留了 ADR-050~055 范围，此处平移存在编号冲突，见 blocker.md 说明，实施仍采用 ADR-050 编号，DOC-06 Task 6.1 落地时须向后平移至 ADR-051+）
- **实施状态**: ✅ 2026-04-19
- **落地位置**:
  - `executor/plugins/plugin_types.py` — PluginScope 枚举（PLATFORM/USER/SESSION，含 priority 属性）+ PluginConfig 数据类（8 字段：name/description/version/skills_dir/hooks_config/mcp_servers/agent_overrides/scope/plugin_root/user_config）
  - `executor/plugins/host.py` — PluginVariableExpander（expand/expand_dict/expand_list，ENV_WHITELIST sandbox，secret.X Phase 1 留桩）+ PluginHost（load_plugin/unload_plugin/unload_all/shutdown/get_skill_descriptions/get_mcp_instructions/get_agent_overrides）
  - `executor/plugins/__init__.py` — 导出 PluginConfig/PluginScope/PluginHost/PluginVariableExpander/ENV_WHITELIST
- **实施 commit**: (本 Task feat commit)
- **偏离点**:
  1. ADR 编号从 PRD 原标 046 平移至 ADR-050（原 ADR-046/047 已被 DOC-05 Task 5.2 MCP 双通道/agent 白名单占用，见 blocker.md）
  2. PRD Part B 完成后行"记录 ADR-022"为笔误（ADR-022 是 DOC-03 Task 3.1 Redis 直通），实际记录 ADR-050
  3. unload_plugin() Phase 1 简化：MCP Client 不按 Plugin 精确追踪，shutdown() 统一停止所有 MCPClient.stop()（解 Task 5.2 TODO）；Phase 2 可细化按 Plugin 追踪
  4. ${secret.X} Phase 1 留桩（原样保留）；跨进程场景需走 security.decrypt_value（DOC-06 Task 6.1 落地后激活）
  5. PluginVariableExpander.expand_dict() 不展开 agent_overrides（语义敏感）；skills_dir/mcp_servers/hooks_config 全递归展开
- **验证结果**: 全部验证 PASS
  - py_compile plugin_types.py / host.py PASS
  - Empty PluginHost：get_skill_descriptions() str，get_mcp_instructions() == {}，get_agent_overrides() == {} PASS
  - 变量替换：PRISM_PLUGIN_ROOT / CLAUDE_PLUGIN_ROOT CC 兼容 / PRISM_SESSION_ID / PRISM_USER_ID / user_config.X / env.HOME（白名单）PASS
  - sandbox：env.SECRET_KEY（非白名单保持原样）/ secret.DB_PASSWORD（留桩）PASS
  - expand_dict 递归展开 PASS
  - Platform→User→Session 三级冲突检测：高优先级覆盖 + audit log / 低优先级跳过 PASS
  - shutdown() 统一清理 MCP + 清空 loaded_plugins PASS
  - 无实际 backend.app import / 无 TODO: 占位符 PASS
- **下游影响**:
  - DOC-05 Task 5.5/5.6 SkillRegistry 可通过 PluginHost.load_plugin() 加载 GitHub Skill
  - DOC-06 Task 6.1 落地三密钥 ADR 时，须将原 DOC-06 ADR-050 编号平移至 ADR-051（已在 blocker.md 标注）
  - DOC-07 Task 7.4 executor 子进程 finally 块调用 await plugin_host.shutdown() 保证 MCP 子进程清理

  - DOC-07 Task 7.4 executor 子进程 finally 块调用 await plugin_host.shutdown() 保证 MCP 子进程清理

---

## DOC-05 Task 5.5: Skills Registry Local + GitHub 两源（ADR-051）

## ADR-051: Skills Registry Phase 1 仅 Local + GitHub 两源（DOC-05 Task 5.5）
- **来源**: PRD v4 DOC-05 Task 5.5 Part A ADR-047（PRD 原标 ADR-047；因 DOC-05 Task 5.2 已占用 ADR-047 MCP agent 白名单，平移至 ADR-051，见 blocker.md）
- **实施状态**: ✅ 2026-04-19
- **落地位置**:
  - `executor/plugins/skills_registry.py` — 新建文件，含：
    - `SkillPackage` dataclass（source: Literal["local","github"]，Phase 1 收窄）
    - `SkillBundle` dataclass（files: dict[str, bytes]）
    - `InstalledSkill` dataclass（8 字段）
    - `SkillSource` ABC（search/fetch/get_versions 抽象方法）
    - `LocalSource`（扫描 .skills/ + .prism/skills/，关键词匹配 name/description/tags）
    - `GitHubSource`（httpx 调用 GitHub API + raw.githubusercontent.com 下载，支持 user/repo#branch/@tag/subpath 4 种格式）
    - `SkillsRegistry`（asyncio.gather 并行搜索 + 按 name 去重 + installed 优先排序 + registry.json 原子写）
  - `executor/plugins/__init__.py` — 新增导出 7 个符号（SkillPackage/SkillBundle/InstalledSkill/SkillSource/LocalSource/GitHubSource/SkillsRegistry）
- **实施 commit**: (本 Task feat commit)
- **偏离点**:
  1. ADR 编号从 PRD 原标 ADR-047 平移至 ADR-051（ADR-047 已被 DOC-05 Task 5.2 MCP agent-scoped 白名单占用，见 blocker.md）
  2. NpmSource / ManusSource Phase 2 预留（SkillSource 抽象基类已保留扩展点，文件末尾占位注释）
  3. GitHubSource 无 Token 时 search 返回空列表 + log warning（而非 raise），符合 Phase 1 降级策略
  4. Backend skill_installs 表由 Backend skill_install_service 写入（Task 5.6 实现）；executor 侧 SkillsRegistry 只管文件系统 + registry.json
  5. SkillsRegistry.install() 不直接调用 PluginHost（解耦），上层调用方（CLI/Backend service）负责触发 reload
- **验证结果**: 全部 9 项验证 PASS
  - py_compile skills_registry.py / __init__.py PASS
  - SkillPackage/SkillBundle/InstalledSkill 数据类实例化 PASS
  - LocalSource.search(空查询返回全部 / 关键词过滤) PASS
  - LocalSource.fetch(返回 SkillBundle 含 SKILL.md) PASS
  - LocalSource.get_versions PASS
  - SkillsRegistry.search(多源并行 + installed 优先排序) PASS
  - SkillsRegistry.install(文件写入 + registry.json 更新) PASS
  - SkillsRegistry.uninstall(文件删除 + registry.json 更新) PASS
  - registry.json 格式（version: "1.0", skills 列表）PASS
  - has_hooks/has_mcp 检测（hooks/ 目录 + frontmatter / mcp/ 目录）PASS
  - GitHubSource._parse_package_id（4 种格式）PASS
  - 进程边界检查（无 backend.app 导入）PASS
  - Phase 2 占位注释存在 PASS
- **下游影响**:
  - DOC-05 Task 5.6 SkillsCLI + SkillsSearchTool 依赖 SkillsRegistry.search()
  - DOC-06 Task 6.1 落地三密钥 ADR 时，DOC-06 原 ADR-050 编号已被占用（ADR-050 = PluginHost，见 blocker.md），须从 ADR-051 之后继续（ADR-052+）
  - Backend skill_install_service（Task 5.6）调用 SkillsRegistry.install() 后写 skill_installs 表

---

## DOC-05 Task 5.6: Skills CLI + Agent Tool 仅搜索（ADR-052 / ADR-053）

## ADR-052: Agent Tool 仅搜索权限——无 install/uninstall/update（DOC-05 Task 5.6）
- **来源**: PRD v4 DOC-05 Task 5.6 Part A ADR-048（PRD 原标 ADR-048；因 DOC-05 Task 5.3 HookSystem 优先级+Phase1过滤+scoped注销已占用 ADR-048，平移至 ADR-052，见 blocker.md）
- **实施状态**: ✅ 2026-04-19
- **落地位置**:
  - `executor/tools/builtin/skills_search.py` — SkillsSearchTool（name="skills_search"，capabilities=[]，input_schema: {query,source,limit}，execute() 调用 SkillsRegistry.search()，返回 JSON 含 note 提示用户走 UI/CLI 安装）
  - `executor/tools/builtin/__init__.py` — register_builtin_tools() 追加 SkillsSearchTool 注册 + skills_registry 参数
- **实施 commit**: (本 Task feat commit)
- **偏离点**:
  1. ADR 编号从 PRD 原标 ADR-048 平移至 ADR-052（见 blocker.md 编号平移链）
  2. SkillsSearchTool 支持 limit 参数（默认 20，最大 50），PRD 未指定但合理添加
  3. 无 GITHUB_TOKEN 时 GitHubSource 返回空列表 + warning（不 raise），符合 Phase 1 降级策略
  4. SkillsSearchTool 懒加载默认 SkillsRegistry（LocalSource + GitHubSource），也接受注入的 registry 实例
- **验证结果**: 全部验证 PASS
  - py_compile PASS
  - tool.name == "skills_search" PASS
  - tool.capabilities == [] PASS
  - input_schema required == ["query"] PASS
  - source enum == ["local","github"] PASS
  - execute() 搜索测试（含临时 Skill）PASS
  - ADR-052 约束（无 install/action 字段）PASS
  - register_builtin_tools() 注册 skills_search PASS
  - 进程边界（无 backend.app import）PASS
- **下游影响**:
  - DOC-11 Task 11.5 Skills Store 页面展示 skills_search 返回结果
  - DOC-07 Task 7.4 executor 子进程注册 SkillsSearchTool 时可注入 PluginHost 的 SkillsRegistry 实例

## ADR-053: Backend 写 skill_installs 表——Redis 缓存 key 格式 skill_install:status:{user_id}:{skill_name} TTL 600s（DOC-05 Task 5.6）
- **来源**: PRD v4 DOC-05 Task 5.6 Part A ADR-049（PRD 原标 ADR-049；因 DOC-05 Task 5.3 Plugin 命名空间已占用 ADR-049，平移至 ADR-053，见 blocker.md）
- **实施状态**: ✅ 2026-04-19
- **落地位置**:
  - `backend/app/services/skill_install_service.py` — SkillInstallService（install/uninstall/list_installed/get_install）+ Redis key 格式 `skill_install:status:{user_id}:{skill_name}` TTL=600s + UPSERT 语义（同 user_id+skill_name 冲突则更新）
  - `backend/app/api/v1/skills.py` — 6 条路由（GET /search / GET /installed / POST /install / DELETE /{skill_name} / POST /{skill_name}/update / GET /{skill_name}）+ SkillPackageResponse/SkillInstallRequest/SkillInstallResponse/SkillUpdateRequest Pydantic schema + Prometheus `prism_skill_searches_total` / `prism_skill_installs_total`
  - `backend/app/api/v1/__init__.py` — include_router(skills_router)
  - `executor/cli/skills_cli.py` — SkillsCLI（cmd_search/cmd_install/cmd_uninstall/cmd_update/cmd_list/cmd_info + backend_url 可选 HTTP 同步）+ build_parser() argparse + main() 入口
  - `executor/cli/__init__.py` — 新建 cli 子包，导出 SkillsCLI
- **实施 commit**: (本 Task feat commit)
- **偏离点**:
  1. ADR 编号从 PRD 原标 ADR-049 平移至 ADR-053（见 blocker.md）
  2. CLI 无 backend_url 时直接操作文件系统（开发者模式），有 backend_url 时发 HTTP 同步 DB；PRD 未明确拆分，此实现更灵活
  3. skill_installs ORM 表现有 metadata_ JSONB 列，Task 5.6 将 install_path/has_hooks/has_mcp/status 存入 metadata_ 而非新增列（schema frozen 原则，不跑 alembic revision）
  4. Backend skills.py 中 _get_redis_client() 在 DOC-07 Task 7.1 前返回 None（Redis 未就绪时不阻断请求，只跳过缓存）
  5. Prometheus Counter 采用 lazy init + try/except 防重复注册（测试环境 / 重载）
- **验证结果**: 全部验证 PASS
  - py_compile PASS（skills_search.py / skills_cli.py / skill_install_service.py / skills.py / api/v1/__init__.py）
  - Redis key == "skill_install:status:{user_id}:{skill_name}" PASS
  - Redis TTL == 600s PASS
  - Redis SET mock 调用验证 PASS
  - SkillInstallService.install UPSERT（UPDATE 路径不调用 add）PASS
  - SkillInstallService.uninstall（found=True / found=False）PASS
  - Backend API 路由 6 条（/search / /installed / /install / /{skill_name} / /{skill_name}/update / /{skill_name}）PASS
  - SkillsCLI cmd_search + cmd_list PASS
  - 进程边界（executor/cli/ 无 backend.app import）PASS
- **下游影响**:
  - DOC-06 Task 6.1 落地三密钥 ADR 时，须从 ADR-054 起编号（ADR-052/053 已被本 Task 占用）
  - DOC-07 Task 7.1 实现 Redis 连接池后，_get_redis_client() 切换为真实连接
  - DOC-11 Task 11.5 Skills Store UI 页面调用 GET /api/v1/skills/search + POST /api/v1/skills/install

---

## DOC-05 Task 5.7: CC 兼容层（ConversionReport）（ADR-054 / ADR-055）

## ADR-054: export_to_cc 返回 ConversionReport 结构化报告（DOC-05 Task 5.7）
- **来源**: PRD v4 DOC-05 Task 5.7 Part A ADR-050-A（PRD 原标 ADR-050-A；因 DOC-05 Task 5.4 PluginHost 统一生命周期已占用 ADR-050，平移至 ADR-054；DOC-06 Task 6.1 落地时须从 ADR-056 起编号，见 blocker.md）
- **实施状态**: ✅ 2026-04-19
- **落地位置**:
  - `executor/plugins/cc_compat.py` — `ConversionReport` dataclass（6 字段：success/cc_compat_zip/lost_fields/warnings/plugin_name/cc_plugin_json）
  - `executor/plugins/cc_compat.py` — `CCPluginAdapter.export_to_cc(config)` 返回 `ConversionReport`，不直接写文件
  - `executor/plugins/cc_compat.py` — `_build_cc_zip()` 构建 zip（plugin.json + README.md + CONVERSION_NOTES.md）
  - `backend/app/api/v1/plugins.py` — `POST /api/v1/plugins/export-cc` 返回 `ConversionReportResponse`（cc_compat_zip_b64 base64 编码）
  - `executor/plugins/__init__.py` — 新增导出 CCPluginAdapter / ConversionReport / PluginFormatError / PluginSchemaError / PluginYamlSchema
- **实施 commit**: (本 Task feat commit)
- **偏离点**:
  1. ADR 编号从 PRD 原标 ADR-050-A 平移至 ADR-054（ADR-050 已被 DOC-05 Task 5.4 占用，见 blocker.md）
  2. 双向不对称（PRD 明确允许）：CC→Prism 完整支持；Prism→CC 可能 lost_fields 非空（vertical_tuning/harness_overrides CC 不支持）
  3. zip 包含 CONVERSION_NOTES.md 详尽说明 lost_fields + warnings（禁止静默成功，PRD 明确要求）
  4. Backend API 返回 cc_compat_zip_b64（base64）而非二进制流，便于 JSON 响应体一致性；调用方 decode 后落盘
  5. MCP server 名称冲突写 warnings（不 raise），保证 export 始终返回有效 ConversionReport（success=True）
- **验证结果**: 全部验证 PASS
  - ConversionReport 6 字段完整 PASS（success/cc_compat_zip/lost_fields/warnings/plugin_name/cc_plugin_json）
  - export_to_cc prism plugin（含 vertical_tuning/harness_overrides）→ lost_fields 含 "prism.vertical_tuning"/"prism.harness_overrides" PASS
  - cc_compat_zip 是合法 zip，含 plugin.json + README.md + CONVERSION_NOTES.md PASS
  - plugin.json 内容与 cc_plugin_json 一致 PASS
  - MCP server 名称冲突 → warnings 含冲突告警 PASS
  - 进程边界（cc_compat.py 无 backend.app import）PASS
- **下游影响**:
  - DOC-06 Task 6.1 落地三密钥 ADR 时，须从 ADR-056 起编号（ADR-054/055 已被本 Task 占用）
  - DOC-11 Task 11.5 Skills/Plugin 子页可展示 ConversionReport.lost_fields 清单，提示用户人工审查
  - PluginHost.load_plugin_from_dir() 集成 CCPluginAdapter，实现目录级统一入口

## ADR-055: plugin.yaml Pydantic 严格校验（缺字段 422）（DOC-05 Task 5.7）
- **来源**: PRD v4 DOC-05 Task 5.7 Part A ADR-050-B（PRD 原标 ADR-050-B；因 ADR-050 已被占用，平移至 ADR-055，与 ADR-054 配对）
- **实施状态**: ✅ 2026-04-19
- **落地位置**:
  - `executor/plugins/cc_compat.py` — `PluginYamlSchema`（Pydantic BaseModel，必填 name，extra="allow" forward-compat）
  - `executor/plugins/cc_compat.py` — `PluginSchemaError`（含 errors: list[dict] 与 Pydantic ValidationError 格式对齐）
  - `executor/plugins/cc_compat.py` — `CCPluginAdapter._validate_plugin_yaml()` 捕获 ValidationError → 抛 PluginSchemaError
  - `backend/app/api/v1/plugins.py` — `POST /api/v1/plugins/load` + `POST /api/v1/plugins/validate`：捕获 PluginSchemaError → HTTP 422 + `{"message": ..., "errors": [...]}`
- **实施 commit**: (本 Task feat commit)
- **偏离点**:
  1. ADR 编号从 PRD 原标 ADR-050-B 平移至 ADR-055（见 ADR-054 偏离点）
  2. pydantic 不可用时 fallback：手动检查 `name` 字段存在性，保证降级场景不崩溃
  3. 未识别字段（extra="allow"）收集后写 structlog WARNING（不拒绝），forward-compat 策略，符合 PRD 描述
  4. extra_field_names() 方法区分 schema 已知字段 vs 动态额外字段，供 Backend validate 端点返回 `extra_fields` 列表
- **验证结果**: 全部验证 PASS
  - plugin.yaml 缺 name → PluginSchemaError，errors[0].loc==['name'] PASS
  - plugin.yaml 含额外字段 → 加载成功（不拒绝）+ structlog WARNING "plugin.yaml.unknown_fields" PASS
  - PluginSchemaError.errors 携带详细错误位置 PASS
  - Backend POST /plugins/validate extra_fields 返回额外字段列表 PASS
- **下游影响**:
  - DOC-09 Task 9.1 MCP Server 管理可复用 PluginYamlSchema 进行 Plugin 元数据 API 校验
  - DOC-11 Task 11.5 Plugin 子页上传 plugin.yaml 时，422 响应体的 errors 列表可直接展示给用户

> **最后更新**: 2026-04-19（DOC-05 Task 5.7 — CC 兼容层 + ConversionReport + ADR-054/055）

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
