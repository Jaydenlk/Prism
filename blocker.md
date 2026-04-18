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

---

### Action required from human reviewer

If a 19th table actually exists (perhaps from a review batch that did not make
it into the §4.2 table list), please amend DOC-01 v4 §4.2 and re-run this Task.
Otherwise, amend the §4.2 heading from "19" to "18" to match the actual definitions.
