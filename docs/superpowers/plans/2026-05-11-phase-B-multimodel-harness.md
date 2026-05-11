# Phase B: Multi-Model Adaptation + Harness Governance

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Support DeepSeek/Qwen/GLM via OpenAI-compatible endpoints + migrate essential governance (permissions, guardrails, observability).

**Depends on:** Phase A complete (SDK executor running with Anthropic)

**Spec:** `docs/superpowers/specs/2026-05-11-prism-architecture-redesign.md` §Phase B

---

## Task 1: Research SDK Multi-Model Support

- [ ] Check if claude-agent-sdk supports custom model/base_url override
- [ ] If YES: configure DeepSeek endpoint directly in SDK
- [ ] If NO: design ModelRouter wrapper that translates SDK calls to OpenAI-compatible API
- [ ] Document findings
- [ ] Commit

## Task 2: Implement ModelRouter

- [ ] Create `executor_v2/model_router.py`:
  - Read Provider config from DB (protocol, base_url, api_key, model_id)
  - If protocol == "anthropic": use SDK native
  - If protocol == "openai": create OpenAI-compatible client wrapper
  - Handle response format translation (OpenAI → SDK expected format)
- [ ] Test with DeepSeek: simple prompt → response
- [ ] Test with Qwen: simple prompt → response
- [ ] Commit

## Task 3: Migrate Permission Hook

- [ ] Create `executor_v2/hooks/permission_hook.py`:
  - Pre-tool-use check: does this tool need permission?
  - Three modes: allow / deny / ask
  - Ask mode: publish permission_ask event via Redis → BLPOP wait for answer
  - Timeout (5min) → default deny
  - Reference: old `executor/harness/permissions/engine.py` + `ask_protocol.py`
- [ ] Test: tool call triggers permission_ask → frontend shows modal → user allows → tool executes
- [ ] Commit

## Task 4: Migrate Guardrail Hook

- [ ] Create `executor_v2/hooks/guardrail_hook.py`:
  - Four iron rules (from CLAUDE.md §六原则):
    1. No investment advice
    2. Data provenance (numbers need source)
    3. AI labeling ([AI · Prism] footer)
    4. User data isolation
  - Pre-tool-use: check against rules
  - Post-response: inject AI label
  - Reference: old `executor/harness/guardrails/rules.py`
- [ ] Test: ask for investment advice → blocked
- [ ] Commit

## Task 5: Migrate Observability Hook

- [ ] Create `executor_v2/hooks/observability_hook.py`:
  - structlog context binding (run_id, user_id, session_id)
  - Prometheus counters (turns, tool calls, errors, tokens)
  - OpenTelemetry span creation (W3C trace propagation)
  - Reference: old `executor/observability/`
- [ ] Commit

## Task 6: Integration Test with Weak Models

- [ ] Configure DeepSeek provider in Prism Settings
- [ ] Submit: "帮我搜索一下最近的 AI Agent 产品有哪些" → multi-turn research
- [ ] Verify: tools work, permissions work, guardrails work, result returned
- [ ] Compare quality: same task with Claude vs DeepSeek
- [ ] Document quality gap
- [ ] Commit

## Verification Criteria
- [ ] DeepSeek/Qwen provider: multi-turn tool calling works
- [ ] Permission modal: frontend shows, user can allow/deny
- [ ] Guardrails: investment advice blocked, AI label present
- [ ] Observability: logs with run_id context, Prometheus metrics
- [ ] No regression: Anthropic provider still works
