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

## Phase 1: Agent 核心(待实施)

> Phase 1 的 ADR 在对应 Task 实施时按模板追加到此处。
> 首个待实施: ADR-020(Harness 单实例,见 DOC-03 Task 3.1)

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

> **最后更新**: 2026-04-18(DOC-02 Task 2.1 Phase 2 — 18 表 ORM + alembic + ADR-017)
