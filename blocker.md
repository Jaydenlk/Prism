# Blocker Report — DOC-02 Task 2.1 Phase 2

**Date**: 2026-04-18
**Reporter**: Sonnet 4.6 (DOC-02 Task 2.1 second phase session)
**Status**: Non-blocking (resolved with documented assumption)

---

## Issue: PRD table count says 19 but §4.2 defines 18 unique tables

### Evidence

DOC-01 v4 §4.2 heading: "Phase 1，**19 张表**"

DOC-01 v4 §4.2 commentary: "Phase 1 新增 5 张表(相对 v3 的 14 张)"
→ implies v3 had 14 tables, v4 = 14 + 5 = 19

DOC-02 v4 Task 2.1 Part B Step 3 heading: "ORM 模型（**19 张表**,v4 从 14 扩展）"

DOC-02 v4 Verification step 4 expected list:
```
users, invite_codes, sessions, session_queue_items, runs, messages,
tool_executions, providers, mcp_servers, user_mcp_installs, im_bindings,
im_channel_configs, audit_logs, skill_installs, coordinator_plans,
permission_requests, im_message_dedup, user_memories
```
→ Count: **18** table names, not 19.

DOC-01 v4 §4.2 explicit table headers found via grep:
```
users, invite_codes, sessions, session_queue_items, runs, messages,
tool_executions, providers, mcp_servers, user_mcp_installs, im_bindings,
im_channel_configs, audit_logs, skill_installs, coordinator_plans,
permission_requests, im_message_dedup, user_memories
```
→ Count: **18** unique tables defined.

### Root cause

PRD v4 §4.2 claims v3 had 14 tables but only 13 appear in the schema
section (users, invite_codes, sessions, session_queue_items, runs, messages,
tool_executions, providers, mcp_servers, user_mcp_installs, im_bindings,
im_channel_configs, audit_logs). Adding the 5 v4-new tables = 18, not 19.

The discrepancy originates in the PRD source. The heading "19 张表" is
inconsistent with the table definitions and the verification list.

### Resolution (per CLAUDE.md Six Principles)

CLAUDE.md Rule 4 states: "发现超出 Task 范围的改动,写 blocker.md 停下"
The task instructions say: "如发现 DOC-01 v4 §4.2 … 字段说法冲突 → 以 DOC-01 v4 为真相源"

**Decision**: Implement the 18 tables **explicitly defined** in DOC-01 v4 §4.2.
The "19" in headings is treated as a PRD typo. The DOC-02 verification
expected-list (18 names) is authoritative for implementation.

This report is created per Rule 4 to document the discrepancy; implementation
proceeds with 18 tables (which are fully aligned with §4.2 schema definitions).

---

**2026-04-18 ADR-029/030 编号在 DOC-03 Task 3.4 和 3.5 重用（PRD 笔误），本实现将 Task 3.5 的两条改编为 ADR-031/032**（Compaction 按回合组原子裁剪 = ADR-031；is_skill_context 优先保留 = ADR-032）。DECISIONS.md 已按 ADR-031/032 落地，Task 3.4 的 ADR-029/030 编号不变。

**ADR 编号持续平移：DOC-03 原标 ADR-031 用 ADR-033；DOC-04 Task 4.1 原标 ADR-030/031/032 用 ADR-034/035/036**（因 DOC-03 Task 3.4/3.5/3.6 已各占用 ADR-030/031/032/033，DOC-04 Task 4.1 的三条 ADR 依次平移为 034/035/036）。后续 DOC-04 Task 4.2+ 的 ADR 继续从 ADR-037 接续。

**DOC-04 Task 4.2 原标 ADR-033/034/035 用 ADR-037/038/039**（PRD ADR-033 被 DOC-03 Task 3.6 Harness 配置 2 源化占用；ADR-034/035 被 DOC-04 Task 4.1 MCP 白名单/frontmatter skills 占用；Task 4.2 的 Fork capability-based/Fork 3 硬约束/ForkBriefing 依次平移为 ADR-037/038/039）。后续 DOC-04 Task 4.3+ 的 ADR 从 ADR-040 接续（但须检查与 DOC-05 范围是否冲突）。

**DOC-04 Task 4.3 原标 ADR-036 用 ADR-040**（PRD ADR-036 被 DOC-04 Task 4.1 Verifier VERDICT 占用，Task 4.3 的 Coordinator Plan checkpoint 持久化平移至 ADR-040）。后续 DOC-04 Task 4.4/4.5 的 ADR 从 ADR-041 接续（DOC-05 原定 ADR-040~050 范围已被 Task 4.3 吃掉一个编号，后续 DOC-05 从 ADR-041 起编号）。

**DOC-04 Task 4.4 原标 ADR-037 用 ADR-041**（PRD ADR-037 被 DOC-04 Task 4.2 Fork capability-based 工具白名单占用，Task 4.4 的 TaskRouter Phase 1 关键词路由平移至 ADR-041）。后续 DOC-04 Task 4.5 的 ADR 从 ADR-042 接续；DOC-05 后续 ADR 继续从 ADR-042 起编号（需继续平移检查）。

**DOC-04 Task 4.5 原标 ADR-038 用 ADR-042**（PRD ADR-038 被 DOC-04 Task 4.2 Fork 3 硬约束占用，Task 4.5 的 PluginBuilder 需求完整度打分（7 维度加权）平移至 ADR-042）。后续 DOC-05 Task 5.1+ 的 ADR 从 ADR-043 接续（DOC-05 原定 ADR-040~050 范围已被 Task 4.3/4.5 吃掉 ADR-040/042，后续从 ADR-043 起编号）。

**DOC-05 Task 5.1 原标 ADR-040/041/042 用 ADR-043/044/045**（PRD ADR-040 被 DOC-04 Task 4.3 Coordinator checkpoint 占用；ADR-041 被 DOC-04 Task 4.1 frontmatter_skills 已占用方向关联；ADR-042 被 DOC-04 Task 4.5 PluginBuilder 打分占用。Task 5.1 的三条 ADR 依次平移为 ADR-043/044/045：Skill 三级加载规范=ADR-043，Skill 匹配强制执行+agents过滤=ADR-044，is_skill_context 标记=ADR-045）。后续 DOC-05 Task 5.2+ 的 ADR 从 ADR-046 接续。

**DOC-05 Task 5.2 原标 ADR-044/045 用 ADR-046/047**（PRD ADR-044 被 DOC-05 Task 5.1 Skill agents过滤占用；ADR-045 被 DOC-05 Task 5.1 is_skill_context 标记占用。Task 5.2 的两条 ADR 依次平移为 ADR-046/047：MCP instructions 双通道注入=ADR-046，agent-scoped MCP 白名单=ADR-047）。后续 DOC-05 Task 5.3+ 的 ADR 从 ADR-048 接续。

**DOC-05 Task 5.3 原标 ADR-043（Hook 4 种 handler）用 ADR-048/049**（PRD ADR-043 已被 DOC-05 Task 5.1 Skill 三级加载规范占用。Task 5.3 的两条 ADR 依次平移为 ADR-048/049：HookSystem 优先级+Phase1过滤+scoped注销=ADR-048；Plugin 命名空间=ADR-049）。后续 DOC-05 Task 5.4+ 的 ADR 从 ADR-050 接续（须检查与 DOC-06 ADR-050~055 三密钥/SSE ticket 范围是否冲突）。

---

### Action required from human reviewer

If a 19th table actually exists (perhaps from a review batch that did not make
it into the §4.2 table list), please amend DOC-01 v4 §4.2 and re-run this Task.
Otherwise, amend the §4.2 heading from "19" to "18" to match the actual definitions.
