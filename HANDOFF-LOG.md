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
