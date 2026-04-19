# BLOCKER — Bug 1 根因是架构级,超出 plan frontend-only 范围

**Date**: 2026-04-19
**Session**: Session 1 (fix/chat-msg-disappear-and-md-render)
**Discovered during**: Task 3 systematic-debugging 诊断

---

## 证据

### 代码链证据(已读原文)

1. `backend/app/services/task_service.py:105-125` `_create_run`
   只写 `Run.prompt` 列,**不写 Message row**。

2. `backend/app/services/callback_service.py`
   全仓只有三条 Message 持久化路径:
   - L161 `tool_use` → role="assistant"
   - L238 `tool_result` → role="user"(canonical Anthropic tool_result blocks)
   - L280 `message_complete` → role 取自 data(实际调用永远传 assistant)

3. `executor/engine/query_engine.py:179-184`
   ```python
   self._messages.append(
       PrismMessage(role="user", content=[TextBlock(text=user_prompt)])
   )
   ```
   只 append 到 in-memory `self._messages`,**不发 HTTP callback**。

4. `executor/engine/query_engine.py:424-427`
   ```python
   await self._callback.message_complete(
       role="assistant",
       content=[_block_to_dict(b) for b in content_blocks],
   )
   ```
   硬编码 `role="assistant"`,**user 文本永远不走 message_complete 上报**。

### 运行时证据(Playwright diagnostic)

Prompt 发送:`reply OK only. Token: DIAG-1776609693933`

`GET /api/v1/sessions/{sid}/messages?limit=50` 响应:
```json
{"data":[{"id":"069e4e9a-31dd-7a55-8000-7bee5419a969","run_id":"069e4e99-e188-7926-8000-13a74b0cbfc0","role":"assistant","content":[{"text":"OK","type":"text"}],"text_preview":"OK","sequence_no":1,"created_at":"2026-04-19T14:41:39.116309Z"}],"error":null}
```

- 返回只有 **1 条** row
- `role="assistant"`
- `sequence_no=1`(第一条)
- **无 user row**,DIAG token 彻底不在 DB

→ 与 plan 里 Case A(parser starvation)、Case B(race / missing)都不同。
→ 真相:**user prompt 架构上就不存 messages 表,只存 Run.prompt**。

---

## 影响

| 症状 | 描述 | 是否用户报告 |
|---|---|---|
| **Bug 1 live**(已报) | 发送后气泡短暂出现,run_complete 后 `setMsgs(displayMsgs)` 用 DB 视图替换,DB 视图无 user row → 气泡消失 | ✅ |
| **历史丢失**(新发现) | 切 session 或刷新页面后,**用户本人的历史提问全丢**,只剩 AI 回复 | ⚠️ 用户未显式报告,但是同根因,切 session 就能看到 |

---

## 范围决策 — 三选一

### Option A — Frontend-only palliative(守 plan 范围)

只改 `frontend/Prism.html` 的 `run_complete` handler(L772-802):

```js
setMsgs(prev => {
  const dbUserTexts = new Set(
    displayMsgs.filter(m => m.role === "user").map(m => (m.content || "").trim())
  );
  const optimisticTail = prev.filter(
    m => m.role === "user" && m.at === "now" && !dbUserTexts.has((m.content || "").trim())
  );
  return [...displayMsgs, ...optimisticTail];
});
```

- **修好**:live 气泡不再消失
- **修不好**:刷新/切 session 仍然丢用户历史
- 工作量:5 分钟
- 风险:低(纯前端,worktree 已就绪)

### Option B — Executor root fix + frontend merge(推荐)

新增 3 行 executor callback + Option A 的 frontend merge 作为防御纵深。

`executor/engine/query_engine.py:184` 之后加:
```python
# 根因修复:user text prompt 也走 message_complete 持久化(否则 DB 缺 user row)
await self._callback.message_complete(
    role="user",
    content=[{"type": "text", "text": user_prompt}],
)
```

- **修好**:live 气泡(frontend merge)+ 历史完整(executor 持久化)
- 工作量:代码 3 行,executor docker 重建 5 分钟
- 风险:中 — 跨 frontend + executor 双边,需 docker rebuild,执行路径变更需过 harness middleware(middleware 对 message_complete 无拦截,但 logging 会多一条记录)
- 延伸范围:Session 1 从 frontend-only 扩到 frontend + executor

### Option C — Backend root fix + frontend merge

在 `TaskService._create_run` / `_submit_queued` 时预先插入一条 user Message row。

- 架构上"更早",但和 sequence_no 管理(ADR-060 advisory_xact_lock)、run_id 关联(Run 还没 flush 拿到 id)会冲突
- 比 Option B 改动更多,没有明显收益
- **不推荐**

---

## 推荐

**Option B**。理由:

1. user 多次强调"根因级 fix",Option A 是症状补丁
2. user 原则明确:"不做向后兼容,宁愿破坏性更新也要保证代码最简化"
3. message_complete 是 canonical 持久化路径,给它加 role=user 分支是最小、最对称、最符合当前架构的改法
4. Option A frontend merge 仍然有价值(作为 race 防御纵深,即使后端修好,仍可能在 callback 延迟 <100ms 窗口内穿透)
5. Executor 改动 3 行,不涉及 schema/middleware 重构,rebuild 快

**Option B 对 plan 的影响**:

- Task 4 从"二选一 A 或 B"改成"Fix = executor 3 行 + frontend merge"
- 新增 Task 4.5:docker compose build(executor 和 backend 同一 image 构建)+ 回归
- Task 7+ 时间不变

---

## 等待用户裁决

请选 **A / B / C**。选完我:

- **A**:按 plan Task 4 Case B 路径(frontend merge)实施,写 deferred-follow-up 到 HANDOFF 指出历史丢失问题留待单独 session
- **B**:改 executor + frontend,docker rebuild,回归验证,plan 更新记录
- **C**:不建议,但如果选会讨论 sequence_no / run_id 冲突如何解

**当前状态**:
- Worktree 就绪,E2E RED 已 commit(`988f567`)
- Diagnostic `e2e/tests/_diagnostic-bug1.spec.ts` 已验证根因(本文件引用)
- Task 4/5/6/7 待执行,等待决策
