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
- **实施状态**: in_progress 2026-04-18
- **落地位置**:
  - `backend/app/core/security.py` — `validate_secrets(jwt_secret, encryption_key, callback_secret)`
  - `backend/app/main.py` — lifespan 首步调用 `validate_secrets()`
  - `.env.example` — 三密钥分区注释,各有独立占位符
- **实施 commit**: TBD(本 session 首次 commit)
- **偏离点**: 无。三密钥均要求 >= 32 字符且互不相等,不满足则 RuntimeError 阻止启动。
- **验证结果**: 四场景单元测试全 PASS(短密钥 / 两两相同 / 三者相同 / 合法输入)
- **下游影响**: DOC-06 Task 6.1 实现 SSE ticket 时需引用 `CALLBACK_SECRET`;DOC-02 Task 2.3 Provider encrypt 时需引用 `ENCRYPTION_KEY`

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

> **最后更新**: 2026-04-18(初始化骨架)
