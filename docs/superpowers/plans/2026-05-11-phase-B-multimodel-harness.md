# Phase B: Multi-Model Adaptation + Full Harness Governance (21 Events)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Support DeepSeek/Qwen/GLM via OpenAI-compatible endpoints + migrate FULL Hook System (21 events) + governance layer.

**Depends on:** Phase A complete (SDK executor running with Anthropic)

**Spec:** `docs/superpowers/specs/2026-05-11-prism-architecture-redesign.md` §Phase B

**PRD 对齐:** DOC-03 §Hook System + DOC-04 §Agent Orchestration + DOC-09 §Provider

---

## Task 1: Research SDK Multi-Model Support

- [ ] Check if claude-agent-sdk supports custom model/base_url override
- [ ] If YES: configure DeepSeek endpoint directly in SDK
- [ ] If NO: design ModelRouter wrapper that translates SDK calls to OpenAI-compatible API
- [ ] Document findings
- [ ] Commit

## Task 2: Implement ModelRouter

- [ ] Create `executor_v2/model_router.py`:
  - Read Provider config from DB (protocol, base_url, api_key, model_id, capabilities)
  - If protocol == "anthropic": use SDK native
  - If protocol == "openai": create OpenAI-compatible client wrapper
  - Handle response format translation (OpenAI → SDK expected format)
  - Capability matrix: prompt_cache / streaming_tools / extended_thinking / vision
- [ ] Test with DeepSeek: simple prompt → response
- [ ] Test with Qwen: simple prompt → response
- [ ] Commit

## Task 3: Migrate Full Hook System (21 Events)

PRD DOC-03 定义了 21 个 Hook 事件，分 5 类。全部移植到 executor_v2。

- [ ] Create `executor_v2/hooks/hook_system.py`:

**Session 类 (4 events):**
- SessionStart — agent run 开始时触发
- SessionEnd — agent run 结束时触发
- SessionPause — agent 暂停（用户切换 session）
- SessionResume — agent 恢复

**Tool 类 (6 events):**
- PreToolUse — 工具执行前（可拦截/修改参数）
- PostToolUse — 工具执行后（可修改结果）
- PostToolUseFailure — 工具执行失败
- ToolTimeout — 工具执行超时
- ToolRetry — 工具重试
- ToolBlock — 工具被护栏拦截

**Agent 类 (4 events):**
- PreTurn — agent 每轮开始前
- PostTurn — agent 每轮结束后
- AgentError — agent 出错
- AgentComplete — agent 完成任务

**Task 类 (4 events):**
- TaskEnqueue — 任务入队
- TaskStart — 任务开始执行
- TaskComplete — 任务完成
- TaskFail — 任务失败

**System 类 (3 events):**
- Compaction — context 压缩触发
- LoopDetect — 循环检测触发
- CircuitBreaker — 熔断触发

- [ ] Each event supports 4 handler types: command / http / prompt / agent (from PRD DOC-05)
- [ ] Hook priority ordering (higher priority runs first)
- [ ] asyncio.gather for parallel hook execution
- [ ] Commit

## Task 4: Migrate Permission Hook

- [ ] Create `executor_v2/hooks/permission_hook.py`:
  - Bind to PreToolUse event
  - Three modes: allow / deny / ask
  - Ask mode: publish permission_ask via Redis → BLPOP wait → timeout default deny
  - Reference: old `executor/harness/permissions/`
- [ ] Test: tool call triggers permission_ask → frontend modal → user allows → tool executes
- [ ] Commit

## Task 5: Migrate Guardrail Hook

- [ ] Create `executor_v2/hooks/guardrail_hook.py`:
  - Bind to PreToolUse + PostTurn events
  - Four iron rules:
    1. No investment advice (PostTurn content filter)
    2. Data provenance (PostTurn: numbers without source → warning)
    3. AI labeling (PostTurn: inject [AI · Prism] footer)
    4. User data isolation (PreToolUse: verify user_id scope)
  - Platform rules: destructive op block, rate limit, PII filter
- [ ] Test: ask for investment advice → blocked
- [ ] Commit

## Task 6: Migrate Loop Detection + Circuit Breaker

- [ ] Create `executor_v2/hooks/safety_hook.py`:
  - Bind to PostToolUse event
  - Loop Detection: track recent tool calls, if same tool+args repeated 3x → LoopDetect event → intervention
  - Circuit Breaker: track consecutive failures per provider, threshold 5 → CircuitBreaker event → switch provider
  - Reference: old `executor/harness/middleware/loop_detection.py`
- [ ] Commit

## Task 7: Migrate Observability Hook

- [ ] Create `executor_v2/hooks/observability_hook.py`:
  - Bind to ALL events (logging/metrics passthrough)
  - structlog context binding (run_id, user_id, session_id)
  - Prometheus counters: turns, tool calls, errors, tokens, guardrail triggers, permission denials
  - OpenTelemetry span creation (W3C trace propagation from parent process)
- [ ] Commit

## Task 8: Integration Test with Weak Models

- [ ] Configure DeepSeek provider in Prism Settings
- [ ] Submit: "帮我搜索一下最近的 AI Agent 产品有哪些" → multi-turn research
- [ ] Verify: tools work, permissions work, guardrails work, loop detection works
- [ ] Submit destructive tool call → verify guardrail blocks it
- [ ] Compare quality: same task with Claude vs DeepSeek
- [ ] Document quality gap
- [ ] Commit

## Verification Criteria
- [ ] DeepSeek/Qwen: multi-turn tool calling works
- [ ] Hook System: all 21 events fire at correct lifecycle points
- [ ] Permission modal: frontend shows, user can allow/deny
- [ ] Guardrails: four iron rules enforced
- [ ] Loop Detection: repeated tool calls intercepted
- [ ] Circuit Breaker: consecutive failures trigger provider switch
- [ ] Observability: full metrics + logs + traces
- [ ] No regression: Anthropic provider still works
