# Phase A: Claude Agent SDK Integration — Minimum Viable Executor

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the 15K LOC custom executor with Claude Agent SDK, achieve a working multi-turn tool-calling agent.

**Architecture:** New `executor_v2/` directory. Old `executor/` untouched until Phase F. Backend ProcessManager switches to launch executor_v2.

**Tech Stack:** claude-agent-sdk, Python 3.11+, httpx, redis, structlog

**Spec:** `docs/superpowers/specs/2026-05-11-prism-architecture-redesign.md` §Phase A

**Pre-work:** Before starting, read Claude Agent SDK source code. Run `pip install claude-agent-sdk` and study the Agent/Tool/Hook interfaces. Also read `executor/__main__.py` to understand current subprocess protocol (args, env, callback format).

---

## Task 1: Study Claude Agent SDK Interface

- [ ] Install SDK: `pip install claude-agent-sdk`
- [ ] Read SDK source — understand Agent class, Tool interface, Hook interface, streaming
- [ ] Document key APIs: how to create agent, register tools, run with streaming, handle hooks
- [ ] Determine: does SDK support OpenAI-compatible endpoints? (critical for multi-model in Phase B)
- [ ] Determine: does SDK handle thinking blocks natively? (our critical bug)
- [ ] Write findings to `docs/research/2026-05-11-claude-agent-sdk-analysis.md`
- [ ] Commit

## Task 2: Create executor_v2 Project Structure

- [ ] Create directory structure:
```
executor_v2/
├── __init__.py
├── __main__.py          # subprocess entry point
├── agent.py             # SDK Agent wrapper
├── callbacks.py         # Backend callback (HTTP + Redis)
├── config.py            # Run configuration
├── tools/
│   ├── __init__.py
│   ├── bash.py          # Shell command execution
│   ├── read.py          # File reading
│   ├── write.py         # File writing
│   ├── web_search.py    # Web search via SearXNG
│   └── skill_invoke.py  # Skill loading
└── hooks/
    ├── __init__.py
    └── callback_hook.py # Progress callbacks to backend
```
- [ ] Create `requirements.txt` for executor_v2
- [ ] Commit

## Task 3: Implement Core Agent Wrapper

- [ ] Create `executor_v2/agent.py`:
  - Wrap SDK's Agent class
  - Accept: model, api_key, base_url, system_prompt, tools, hooks
  - Method: `async run(prompt, messages) -> AgentResult`
  - Handle streaming events → forward to callback
- [ ] Create `executor_v2/config.py`:
  - Parse subprocess args (same protocol as old executor: --run-id, --session-id, --user-id, --callback-url, --callback-secret, --redis-url)
  - Read provider config from DB (reuse old executor's DB read pattern)
- [ ] Commit

## Task 4: Implement Basic Tools

- [ ] Create `tools/bash.py` — shell command execution (reference old executor/tools/builtin/bash.py)
- [ ] Create `tools/read.py` — file reading
- [ ] Create `tools/write.py` — file writing
- [ ] Create `tools/web_search.py` — SearXNG search (reference old executor's web search)
- [ ] Each tool: SDK Tool interface, name, description, input_schema, execute method
- [ ] Commit

## Task 5: Implement Callback Hook

- [ ] Create `executor_v2/callbacks.py`:
  - HTTP callback to backend (same protocol: POST /api/v1/internal/callbacks)
  - HMAC signature with CALLBACK_SECRET
  - Event types: text_delta, tool_start, tool_end, message_complete, run_complete, run_error
  - Redis direct publish for SSE streaming (channel: sse:{session_id})
- [ ] Create `executor_v2/hooks/callback_hook.py`:
  - SDK Hook interface (setup/response/teardown/error)
  - On each agent response → parse → forward to callback
- [ ] Commit

## Task 6: Implement __main__.py Entry Point

- [ ] Create `executor_v2/__main__.py`:
  - Parse args (same as old executor)
  - Read run config from DB (provider, session, messages)
  - Initialize Agent with provider's API key, model, base_url
  - Register tools
  - Register callback hook
  - Load conversation history
  - Run agent
  - Write heartbeat to Redis (same key: harness:heartbeat:{run_id})
  - Handle SIGTERM gracefully
  - On completion: callback run_complete
  - On error: callback run_error
- [ ] Commit

## Task 7: Switch ProcessManager to executor_v2

- [ ] Modify `backend/app/services/process_manager.py`:
  - Change subprocess command from `python -m executor` to `python -m executor_v2`
  - Keep same args protocol
- [ ] Commit

## Task 8: Integration Test

- [ ] Start Docker (rebuild backend)
- [ ] Submit task: "Hello, what is 2+2?" → verify single-turn works
- [ ] Submit task: "Search the web for today's weather in Shanghai" → verify multi-turn tool use works
- [ ] Submit task with extended_thinking provider → verify thinking blocks handled by SDK
- [ ] Check: SSE streaming works in frontend
- [ ] Check: run status completes (not crash/timeout)
- [ ] Commit final fixes

## Verification Criteria
- [ ] Multi-turn tool calling: agent calls tool → gets result → responds → no crash
- [ ] ThinkingBlock: extended_thinking provider works without HTTP 400
- [ ] SSE streaming: frontend shows real-time text + tool cards
- [ ] Heartbeat: no false crash detection
- [ ] Old executor untouched: `executor/` directory unchanged
