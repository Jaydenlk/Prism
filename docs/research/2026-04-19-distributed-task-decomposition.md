# Distributed / Multi-Agent Task Decomposition — Competitive Research for Prism v2

> Date: 2026-04-19
> Author: CC research session
> Scope: Research to inform Prism v2's next iteration beyond the single-TAOR executor loop.

---

## Part 1 — Manus AI Deep Dive

Manus launched March 2025 under Butterfly Effect Pte. Ltd. (originally Beijing, later Singapore); Meta acquired the company for ~USD 2B in late 2025 and Manus now operates as a Meta product.[[Awesome Agents review]](https://awesomeagents.ai/reviews/review-manus/)[[trysliq]](https://www.trysliq.com/blog/perplexity-computer-vs-manus-ai) The iOS app crossed 2M downloads before acquisition.[[MWM listing]](https://mwm.ai/apps/manus-ai/6740909540)

### 1.1 Architecture (public + inferred)

| Layer | What's there | Source |
|---|---|---|
| Foundation models | Claude Sonnet 3.5/3.7 primary, plus Qwen finetunes | [[madikenz gist]](https://gist.github.com/madikenz/5c4cd416ccd8549d51963dbfd3e3b5cf) [[Kite Metric]](https://kitemetric.com/blogs/manus-ai-revolutionizing-ai-assistants-with-multi-agent-systems) |
| Planner/Executor/Verifier trio | Tripartite cognitive architecture — Planner decomposes, Executor invokes tools, Verifier reviews outcomes | [[Proxnox benchmarks]](https://proxnox.github.io/manus-ai-max-real-capabilities-and-performnace) |
| Multi-agent orchestration | A lead executor delegates to specialised sub-agents (browsing, coding, analysis, knowledge retrieval); ~29 integrated tools | [[Awesome Agents]](https://awesomeagents.ai/reviews/review-manus/) [[Kite Metric]](https://kitemetric.com/blogs/manus-ai-revolutionizing-ai-assistants-with-multi-agent-systems) |
| CodeAct action mechanism | Agent writes executable Python rather than JSON tool-calls; observed pattern in reverse-engineered prompts | [[Medium/Pankaj]](https://medium.com/%40pankaj_pandey/inside-manus-the-architecture-that-replaced-tool-calls-with-executable-code-d89e1caea678) [[madikenz gist]](https://gist.github.com/madikenz/5c4cd416ccd8549d51963dbfd3e3b5cf) |
| Virtual-computer sandbox | Per-session Ubuntu Linux VM with shell (sudo), browser (browser-use framework), Python/Node, persistent file system; server-side so the user can close their device | [[Proxnox]](https://proxnox.github.io/manus-ai-max-real-capabilities-and-performnace) [[Manus docs]](https://www.manus.im/docs) |
| Agent loop | Analyze → Plan → Execute → Observe; one tool action per iteration, state appended to event stream | [[madikenz gist]](https://gist.github.com/madikenz/5c4cd416ccd8549d51963dbfd3e3b5cf) |

### 1.2 Task decomposition

The Planner module turns a high-level goal ("compile competitive analysis of top 5 CRMs") into a numbered to-do list. Each sub-task is assigned to a specialised sub-agent, and the Executor layer dispatches them. Independent sub-tasks run in parallel — Manus explicitly markets "parallel sub-task processing" as a differentiator: researching 10 topics completes in roughly the same wall-clock as researching one.[[OpenAIToolsHub review]](https://www.openaitoolshub.org/en/blog/manus-ai-review) The plan is updated on the fly as discoveries emerge.[[madikenz]](https://gist.github.com/madikenz/5c4cd416ccd8549d51963dbfd3e3b5cf)

### 1.3 UX — what the user sees

- Structured to-do list generated on submission, with per-item checkbox state.[[MWM listing]](https://mwm.ai/apps/manus-ai/6740909540)
- Live dashboard showing the agent's current browser frame, terminal output, and file system; user can interrupt and edit prompt mid-task.[[trysliq]](https://www.trysliq.com/blog/perplexity-computer-vs-manus-ai)
- Asynchronous — user closes laptop, receives notification when done.[[MWM]](https://mwm.ai/apps/manus-ai/6740909540)
- Final deliverables: markdown reports, spreadsheets, slide decks, standalone web pages, generated from a single prompt.[[OpenAIToolsHub]](https://www.openaitoolshub.org/en/blog/manus-ai-review)

### 1.4 Long-horizon memory

The Manus team's own writing calls this their #1 lesson: **file system as context**. Web-page content is dropped once the URL is preserved; document body dropped once the sandbox path is preserved — compression is always *restorable*.[[manus.im/blog]](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus) A `todo.md` file is rewritten at each step as an attention-biasing recitation — the plan is literally echoed back into the context tail to defeat "lost in the middle" drift. Failures are kept in context (not scrubbed) so the model's prior shifts away from bad branches. Average tool-call count per task ≈ 50; input-to-output token ratio ≈ 100:1 — motivating aggressive KV-cache optimisation.[[manus.im/blog]](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)

### 1.5 Known limitations

| Limitation | Source |
|---|---|
| Server reliability "unacceptable for a paid product" — frequent overload errors, lost sessions | [[Awesome Agents]](https://awesomeagents.ai/reviews/review-manus/) |
| Credit-based pricing with no cost preview; tasks that require judgement often hallucinate or dead-end | [[Awesome Agents]](https://awesomeagents.ai/reviews/review-manus/) [[OpenAIToolsHub]](https://www.openaitoolshub.org/en/blog/manus-ai-review) |
| Sandbox recycled after 7 d (free) / 21 d (Pro) — memory is effectively session-scoped | [[Proxnox]](https://proxnox.github.io/manus-ai-max-real-capabilities-and-performnace) |
| Coordination complexity grows super-linearly with sub-agent count | [[Kite Metric]](https://kitemetric.com/blogs/manus-ai-revolutionizing-ai-assistants-with-multi-agent-systems) |
| "Wrapper" critique — thin value-add over Claude + tooling; vulnerable to model-pricing swings | [[Kite Metric]](https://kitemetric.com/blogs/manus-ai-revolutionizing-ai-assistants-with-multi-agent-systems) |

---

## Part 2 — Multi-Agent Frameworks Compared

### 2.1 OpenAI Swarm (2024, now superseded by Agents SDK)

Swarm was released October 2024 as an "educational, experimental" framework by the OpenAI Solutions team.[[github.com/openai/swarm]](https://github.com/openai/swarm/tree/main) It is built around two primitives: `Agent` (instructions + functions) and `handoff` (a function that returns another `Agent`). The `client.run()` loop is deliberately thin — each turn gets a completion from the current agent, executes tool calls, and if any tool returned an `Agent` object, control transfers. Swarm is stateless between calls and runs almost entirely on the client; it's a pattern library, not a runtime.[[github.com/openai/swarm]](https://github.com/openai/swarm/tree/main)[[OpenAI cookbook]](https://developers.openai.com/cookbook/examples/orchestrating_agents/) Production users graduated to the OpenAI Agents SDK, which retains the handoff primitive and adds tracing/guardrails/session memory. The current OpenAI docs distinguish **handoffs** (specialist owns the next reply) from **agents-as-tools** (manager synthesises the final answer); the agents-as-tools manager-style pattern is recommended for bounded sub-tasks, handoffs for branched ownership.[[OpenAI orchestration docs]](https://developers.openai.com/api/docs/guides/agents/orchestration)

### 2.2 CrewAI

Role-based Python framework built around four primitives: **Agent** (role/goal/backstory/tools), **Task** (description + expected output + owner agent), **Tools**, and **Crew** (orchestrator). Three execution processes: `Process.sequential`, `Process.hierarchical`, and `Process.custom`. In hierarchical mode a manager agent (auto-created or user-supplied) delegates tasks; `allow_delegation=True` gives agents a "Delegate Work to Coworker" tool automatically.[[CrewAI collaboration docs]](https://docs.crewai.com/concepts/collaboration)[[CrewAI hierarchical]](https://docs.crewai.com/learn/hierarchical-process) 2026 additions include a first-class A2A (Agent-to-Agent) protocol that lets a CrewAI agent delegate to remote agents published as A2A-compliant servers.[[CrewAI A2A docs]](https://docs.crewai.com/en/learn/a2a-agent-delegation) Positioned explicitly as production-oriented (observability, cost control) rather than research-flexible. [[DigitalOcean tutorial]](https://www.digitalocean.com/community/tutorials/crewai-crash-course-role-based-agent-orchestration)

### 2.3 Microsoft AutoGen

AutoGen v0.4 (2024) adopts an **actor model** for multi-agent orchestration: a fully async, event-driven `AgentRuntime` where each `ConversableAgent` is an actor; agents can run in different processes and even different languages.[[Microsoft Research publication]](https://www.microsoft.com/en-us/research/publication/autogen-enabling-next-gen-llm-applications-via-multi-agent-conversation-framework/) The programming model treats collaboration as a *structured conversation*. Key pattern is `GroupChat` (or `SelectorGroupChat`): a `GroupChatManager` broadcasts every message to all participants and picks the next speaker via round-robin, random, manual, custom function, or an LLM selector.[[AutoGen selector group chat docs]](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/selector-group-chat.html) Nested chats package a workflow into one agent. Sweet spot is generate-critique-revise loops (coding/review, research synthesis with a skeptic); the tradeoff is the selector LLM adds one extra call per turn and occasionally misroutes.[[vinayakajyothi]](https://vinayakajyothi.com/blog/2026-02-04-autogen-conversational-agents/)

### 2.4 LangGraph

LangChain's stateful-graph framework. Agent workflows are modelled as `StateGraph`s — nodes are functions, edges are transitions, state is a typed channel dict, and after every node the state is written to a **checkpointer** (`MemorySaver`, `SqliteSaver`, `PostgresSaver`).[[mager.co deep dive]](https://www.mager.co/blog/2026-03-12-langgraph-deep-dive) This persistence makes two LangGraph-specific features possible: crash-recoverable long-running runs, and `interrupt()` — a function you call inside a node that suspends execution, writes state, and waits indefinitely until you resume with a `Command`. Interrupts are keyed by `thread_id`.[[LangChain interrupts concept docs]](https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/)[[LangChain blog on interrupt]](https://blog.langchain.dev/making-it-easier-to-build-human-in-the-loop-agents-with-interrupt) LangGraph explicitly supports three multi-agent topologies: supervisor (central router), network (peer-to-peer), hierarchical (subgraphs nested in supervisors).[[mager.co]](https://www.mager.co/blog/2026-03-12-langgraph-deep-dive)

### 2.5 Anthropic Claude multi-agent (orchestrator-worker)

Anthropic's own Research feature, shipped June 2025, is the most-cited production reference for the orchestrator-worker pattern. A `LeadResearcher` (Opus 4) analyses the query, writes a plan to a Memory tool (because context may truncate past 200K tokens), and spawns `N` parallel subagents (Sonnet 4) with explicit objectives, output formats, tool guidance, and task boundaries. Subagents use interleaved thinking between tool calls, return findings, and a separate `CitationAgent` attaches sources at the end.[[anthropic.com/engineering]](https://www.anthropic.com/engineering/built-multi-agent-research-system) Internal evals: multi-agent beat single-agent Opus 4 by **+90.2%** on the BrowseComp-style research eval; 95% of performance variance was explained by token-use (80%), tool-call count, and model choice. **Cost**: ~15× tokens vs chat, ~4× vs single agent — so the pattern only pays off when the task value is high and parallelisable.[[anthropic.com/engineering]](https://www.anthropic.com/engineering/built-multi-agent-research-system) Claude Code's Sub-Agents feature productised this pattern: built-in `Explore` (Haiku, read-only), `Review`, `Debug` sub-agents, plus custom ones.[[Medium/Jiten Oswal]](https://medium.com/%40jiten.p.oswal/the-architecture-of-scale-a-deep-dive-into-anthropics-sub-agents-6c4faae1abda)

### 2.6 Google Agent Development Kit (ADK)

Publicly open-sourced April 2025; Apache-2.0; available in Python/TypeScript/Go/Java (v1.0+).[[github.com/google/adk-docs]](http://github.com/google/adk-docs) ADK composes systems from `BaseAgent` subclasses: `LlmAgent`, plus workflow agents `SequentialAgent`, `ParallelAgent`, `LoopAgent`, and `CustomAgent`. Hierarchy is explicit via `sub_agents=[...]` on the parent. Two interaction mechanisms: (a) `AgentTool` — wrap a child agent as a tool the parent can call (manager-style), and (b) LLM-driven delegation where the parent's prompt lists sub-agents and Gemini picks who to route to.[[ADK multi-agent docs]](https://google.github.io/adk-docs/agents/multi-agents/) Deployment targets include Cloud Run, GKE, and Vertex AI Agent Engine. ADK is model-agnostic but optimised for Gemini.[[Google Cloud blog]](https://cloud.google.com/blog/products/ai-machine-learning/build-multi-agentic-systems-using-google-adk)

### 2.7 AutoGPT / BabyAGI lineage (historical)

BabyAGI (Yohei Nakajima, April 2023, originally ~200 lines) formalised the three-agent loop: **Execution Agent** (runs current task), **Task Creation Agent** (generates new tasks from result), **Prioritization Agent** (reorders the task queue).[[aiinsightsnews BabyAGI guide]](https://aiinsightsnews.net/babyagi/) Tasks stored in a vector DB (Pinecone/Chroma) as long-term memory. AutoGPT (Significant Gravitas, March 2023) added a reflexion loop (a second "reviewer" LLM critiques each action) plus memory tiering, but became notorious for infinite loops and API-cost blowups.[[aiagentskit comparison]](https://aiagentskit.com/blog/babyagi-vs-autogpt-vs-agentgpt) The AutoGPT team's own "Agent loop v2" PR (#4799, merged July 2023) explicitly separated planner and executor agents after the monolithic loop proved unworkable — a lesson every subsequent framework inherits.[[GitHub PR #4799]](https://github.com/Significant-Gravitas/AutoGPT/pull/4799)[[Issue #3593]](https://github.com/Significant-Gravitas/AutoGPT/issues/3593) These frameworks matter today as *prior art* showing that task-queue + prioritisation alone is insufficient without separated planning, typed state, and cost guardrails.

---

## Part 3 — Pattern Taxonomy

| Pattern | State management | Failure handling | Observability | When to use | When NOT |
|---|---|---|---|---|---|
| **Planner-Executor (hierarchical / orchestrator-worker)** | Orchestrator owns the plan; sub-agents have isolated contexts, return structured results.[[anthropic.com]](https://www.anthropic.com/engineering/built-multi-agent-research-system) | Orchestrator retries or reassigns failed sub-tasks; sub-agent failure contained at boundary.[[contracollective]](https://contracollective.com/blog/multi-agent-orchestration-patterns) | Easy — single control flow to trace, sub-agent spans nest under parent run.[[gurusup]](https://gurusup.com/en/blog/agent-orchestration-patterns) | Decomposable breadth-first work (research, multi-source analysis, fan-out writes).[[anthropic.com]](https://www.anthropic.com/engineering/built-multi-agent-research-system) | Sub-tasks need to talk to each other mid-flight; coding tasks with tight step dependencies; very cheap tasks (~15× token cost).[[anthropic.com]](https://www.anthropic.com/engineering/built-multi-agent-research-system) |
| **Swarm (handoff)** | Stateless between calls, conversation history transferred on handoff; no central coordinator.[[github.com/openai/swarm]](https://github.com/openai/swarm/tree/main) | Convergence undefined — how does anyone know "done"? Cascade handoffs possible.[[gurusup]](https://gurusup.com/en/blog/agent-orchestration-patterns) | Hard — requires distributed tracing + handoff-chain reconstruction.[[gurusup]](https://gurusup.com/en/blog/agent-orchestration-patterns) | Customer-support triage, interactive routing where "the right specialist owns the reply".[[OpenAI orchestration]](https://developers.openai.com/api/docs/guides/agents/orchestration) | Long autonomous runs, regulated workflows that need auditable single owner. |
| **Blackboard (shared memory)** | Typed shared store is the *only* communication channel; agents read/write snapshots.[[contracollective]](https://contracollective.com/blog/multi-agent-orchestration-patterns) | Schema validation at write time prevents context pollution; replay from blackboard snapshots. | Best-in-class — the blackboard state at any timestamp is the full system state.[[contracollective]](https://contracollective.com/blog/multi-agent-orchestration-patterns) | Document/artifact assembly where several specialists converge on one output (e.g., compliance report, legal brief).[[arxiv.org/2508.12683]](https://arxiv.org/html/2508.12683) | Low-latency interactive UX (blackboard write-cycle adds latency); tasks with no shared artifact. |
| **Supervisor-Worker (tree)** | Supervisor holds task tree + progress; workers isolated, no peer knowledge.[[contracollective]](https://contracollective.com/blog/multi-agent-orchestration-patterns) | Supervisor contains cascade failures; retries at supervisor boundary. | Easy — one supervisor log per level; tree structure maps 1:1 to trace. | Classic task decomposition with clear authority; content pipelines, order processing.[[premai blog]](https://blog.premai.io/multi-agent-ai-systems-architecture-communication-and-coordination/) | Peer-collaboration dynamics where workers must see each other's output. |
| **Graph (LangGraph-style)** | Checkpoint per node; typed state channels; `thread_id` = resume cursor.[[langchain interrupts]](https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/) | `interrupt()` pauses and waits for HITL; crash recovery via checkpointer. | Excellent — every state transition is a DB row. | Stateful workflows that need HITL approval, compliance checkpoints, long-running jobs that survive deploys.[[mager.co]](https://www.mager.co/blog/2026-03-12-langgraph-deep-dive) | Simple single-step tasks (graph overhead); throughput-heavy workloads (checkpoint IO). |
| **Router (semantic)** | Router is stateless per-call; downstream agents keep their own state.[[tutorialQ swarm]](https://tutorialq.com/ai/multi-agent/swarm-and-handoff-patterns) | Routing errors visible immediately; fallback to default agent. | Medium — router decisions are observable, but routing chains get deep. | Perplexity Computer-style multi-model routing — "which model is best for this sub-task".[[trysliq]](https://www.trysliq.com/blog/perplexity-computer-vs-manus-ai) | When the same agent should handle the whole conversation. |
| **Debate / consensus** | Each agent keeps private reasoning; shared channel for statements.[[sutra-mas]](https://github.com/balajivis/sutra-mas) | Convergence typically capped by N rounds; LLM-judge arbitration. | Medium — statements logged, but "why this verdict" is implicit. | Open questions benefitting from adversarial reasoning (fact-check, strategic planning).[[vinayakajyothi]](https://vinayakajyothi.com/blog/2026-02-04-autogen-conversational-agents/) | Fact-retrieval, deterministic workflows — multiplies cost without benefit. |

---

## Part 4 — Fit Assessment for Prism v2

Scored 1 (worst) – 5 (best) for Prism's current architecture (single-process executor subprocess, Redis-pubsub streaming, 19-table frozen Postgres schema, CALLBACK_SECRET HTTP for key events).

| Pattern | Impl. cost (5=cheap) | UX clarity (5=clear) | Backward-compat w/ schema (5=zero change) | Distributed scalability (5=trivial fan-out) |
|---|---|---|---|---|
| **Planner-Executor (orchestrator-worker)** | 3 | 5 | 2 (needs `runs.parent_run_id` or new `subtasks` table → ADR) | 5 (sub-agents = sub-executor subprocesses, already separate processes) |
| Agents-as-Tools / Router (fallback) | 5 (no schema change, dispatch is just a new built-in tool) | 3 (user sees tool calls, not a task tree) | 5 | 3 (still one executor subprocess per run) |
| Supervisor-Worker tree (> 2 levels deep) | 2 | 4 | 1 (needs tree table) | 4 |
| Graph / LangGraph-style | 2 (requires checkpointer abstraction over 19 tables) | 4 | 2 | 4 |
| Blackboard (shared memory) | 3 (Redis is already there; need typed schema on shared state) | 2 (invisible to non-technical users) | 3 (can sit in Redis, not Postgres) | 4 |
| Swarm (handoff) | 4 | 2 (who's answering becomes confusing) | 4 | 3 |
| Debate / consensus | 2 | 1 | 3 | 2 |

Dimensions are deliberately unweighted — reading straight sums would favour the cheapest option. For Prism, implementation cost is a one-time amortised expense, while UX clarity and distributed scalability are the permanent product-differentiation axes. Re-weighting those two 2× cleanly separates the top two rows.

### Recommendation

- **Primary: Planner-Executor (orchestrator-worker)**. Converges with every credible production reference: Anthropic Research (90.2% lift, production at Anthropic), Manus's own Planner/Executor/Verifier trio (the system that inspired this effort), CrewAI `Process.hierarchical`, LangGraph supervisor, ADK `SequentialAgent` + `ParallelAgent`. The Manus UX the user cited — "structured to-do list with subtask cards" — *is* the orchestrator-worker rendering. Score 15 reflects a real schema cost, but that cost buys distributed-scalability 5/5 because sub-agents map 1:1 to sub-executor subprocesses.
- **Fallback: Agents-as-Tools**. Keep the single-TAOR loop intact; add one built-in tool `dispatch_subtask(prompt, agent_type)` whose handler spawns a short-lived sub-run and blocks on its result. Zero schema change. Narrow gain (no true parallelism unless the orchestrator calls `dispatch_subtask` multiple times in one turn — but that's already allowed by ADR-021's `asyncio.gather`). Score 16 beats primary on cost, but primary beats on UX/scalability, which is the real product differentiation vs Manus.

---

## Part 5 — Migration Path for the Recommended Pattern

### 5.1 Changes in `executor/engine/query_engine.py`

Concrete, not "refactor":

1. **Extend `RunContext`** with a `run_mode: Literal["single", "orchestrator", "worker"]` field and `parent_run_id: str | None`. Default `"single"` preserves current behaviour.
2. **Dispatch surfaces as an ordinary `tool_use`.** No new `stop_reason`. The orchestrator calls a new built-in tool `dispatch_subtasks` (plural — one call, list of specs — to avoid N sequential tool-result turns); it flows through the existing `_execute_tools` path at line 258 like every other tool. The *handler* does the special work (subprocess fan-out + Redis BLPOP), but the engine loop is unchanged.
3. **New built-in tool `dispatch_subtasks`** registered in `ToolRegistry` with agent-type whitelist. Handler:
   - Writes one row per subtask to a new `subtasks` table (or `runs` child row with `parent_run_id`) — **schema impact, see §5.2**.
   - Spawns `N` child executor subprocesses via the existing `executor/__main__.py` entry, passing `--parent-run-id`, `--subtask-id`, `--agent-type`, and the subtask prompt.
   - Returns a `subtask_batch_id` and a Redis result-key list to the orchestrator.
4. **New `_await_subtasks(batch_id)` method**. Mirrors ADR-028's ask-permission `BLPOP` pattern: the orchestrator blocks on `BLPOP subtask:result:{subtask_id}` with a timeout per subtask. Returns a list of `SubtaskResult` dataclasses, each containing `{subtask_id, status, output_text, artifacts[], tokens_in/out}`.
5. **Worker-side runs are ordinary `QueryEngine` instances** with `run_mode="worker"` and an `on_complete` callback that `LPUSH`es the result to `subtask:result:{subtask_id}`. No new class hierarchy — reuse all existing TAOR, compaction, middleware infrastructure.
6. **Compaction tweak**. When orchestrator receives subtask results, append them as a synthetic `tool_result` block (already a canonical content type — ADR-029 pairing rules work unchanged). Per ADR-029's atomic-round-group compaction, subtask results cannot be split across compaction boundaries.
7. **Middleware**. Add `pre_dispatch` / `post_dispatch` hook points to the `MiddlewarePipeline` for observability-plugin fan-out. Enforce a per-run subtask budget via a new middleware (prevent runaway fan-out, akin to Anthropic's "50 subagents for a simple query" failure mode — §Prompt engineering in [anthropic.com](https://www.anthropic.com/engineering/built-multi-agent-research-system)).

### 5.2 DB schema impact — **NEEDS ADR** (per 六原则 #1, frozen 19-table)

Two minimum-viable options, each requires a new ADR and `alembic revision`:

| Option | Change | Pros | Cons |
|---|---|---|---|
| A. `runs.parent_run_id UUID NULL` | One column added to existing `runs` table | Smallest diff; sub-agents are just runs, inherit every existing index/query | Collides with the "one run = one user-initiated action" invariant elsewhere in the schema; needs `runs.role ENUM('orchestrator','worker','single')` too |
| B. New `subtasks` table | `subtasks(id, parent_run_id, agent_type, prompt, status, result_run_id FK, seq_no, created_at)` | Keeps `runs` semantics clean; makes the task-tree UI query trivial (`SELECT … WHERE parent_run_id=?`) | +1 table, +1 FK, +2 indexes; bumps count from 19 → 20 (PRD requires authorisation) |

**Both options are blocked on user authorisation** per CLAUDE.md 六原则 #1. Recommendation is Option B — cleaner semantics — but flag both in the ADR for user choice.

Also needed (non-schema):
- New harness event types `subtask_dispatched`, `subtask_progress`, `subtask_completed`, `subtask_failed` in the `harness_event` channel. No table change (they ride the existing event-log path).
- New audit-log event types: `MULTI_AGENT_DISPATCHED`, `MULTI_AGENT_CONVERGED`.

### 5.3 Process boundary — 六原则 #6

Workers are **separate executor subprocesses**, not Python objects inside the orchestrator. Implication:
- Orchestrator and workers communicate only via Redis pub/sub (for deltas, per ADR-022) and HTTP with CALLBACK_SECRET (for message_complete / subtask_complete). Zero shared Python objects.
- Same CALLBACK_SECRET is used; worker processes inherit the parent's callback URL but report their own `run_id`.
- Backend stays ignorant of multi-agent semantics at the Harness level — it just sees more runs with a `parent_run_id` link. ADR-020 (Backend doesn't hold Harness instances) holds unchanged.

### 5.4 Prism.html ChatPage UX

Concrete deltas (inspired by Manus's mobile-app to-do UI [[MWM]](https://mwm.ai/apps/manus-ai/6740909540) and Anthropic's research-product subagent panel):

| UI element | Behaviour |
|---|---|
| **Task tree panel** (collapsible left of main transcript) | Renders a tree keyed by `parent_run_id`. Root = user prompt. Level 1 = orchestrator's plan items. Level 2 = subtask runs with their own streaming text. |
| **Subtask card** | Title = subtask prompt's first line; status badge (pending / running / done / failed); inline "View stream" that expands to show the worker run's tokens streamed via its own Redis channel; artifacts list. |
| **Parent progress bar** | `completed_subtasks / total_subtasks` updated by `subtask_completed` harness events. |
| **Live intervention** | "Stop this subtask" button per card — fires a `subtask_cancel` callback that the worker's middleware pipeline intercepts and aborts the run (reuses existing `run_error` flow). |
| **Final synthesis view** | After orchestrator's `end_turn`, the main transcript shows the synthesis message; subtask cards stay accessible for drill-down. |

Non-technical users see **one main answer streaming + a task tree they can ignore**. Power users can expand the tree to see per-worker streams. This matches the Manus UX pattern that inspired the iteration.

### 5.5 Observability additions

| Signal | How |
|---|---|
| Per-subtask token accounting | Worker's `run_complete` callback already reports tokens; orchestrator sums via `subtask_completed` events. |
| Fan-out depth guard | Middleware counts active subtasks in Redis (`INCR subtask:count:{root_run_id}`), aborts dispatch over N (Anthropic's 50-subagent bug). |
| Per-subtask traces | Reuse structlog context-vars pattern (already in query_engine.py L162-167) — workers bind `parent_run_id` so all their log records carry the tree linkage. |
| New Prometheus metrics | `prism_subtask_dispatch_total{agent_type}`, `prism_subtask_duration_seconds{agent_type,status}`, `prism_subtask_depth_gauge` (current open subtasks). Register alongside existing `prism_tool_invocations_total` (query_engine.py L517). |
| Audit log | `MULTI_AGENT_DISPATCHED`, `MULTI_AGENT_CONVERGED` rows in `audit_log` (existing table, no schema change). |

### 5.6 Phasing

| Phase | Scope | Schema impact |
|---|---|---|
| **P0 (single PR)** | `RunContext.run_mode`, `dispatch_subtasks` tool skeleton, worker subprocess launch, Redis result collection — all with `parent_run_id` stored in Redis only (no DB) | None — proves the process-boundary story first |
| **P1 (ADR + PR)** | Migration A or B, persistent subtask rows, audit log, Prometheus metrics | ADR-required |
| **P2** | ChatPage task-tree UI, per-subtask streaming panel, cancel button | None (frontend only) |
| **P3** | `dispatch_subtasks_async` (non-blocking orchestrator — the "synchronous bottleneck" Anthropic called out [[anthropic.com]](https://www.anthropic.com/engineering/built-multi-agent-research-system)) | Possibly — async result reconciliation rows |

The fan-out-depth middleware guard in §5.5 is justified directly by Anthropic's cost data: multi-agent systems burn ~15× the tokens of plain chat [[anthropic.com]](https://www.anthropic.com/engineering/built-multi-agent-research-system) — without a hard cap, a runaway orchestrator can bankrupt a user in a single prompt.

---

## References (primary sources)

- Anthropic Engineering — How we built our multi-agent research system — <https://www.anthropic.com/engineering/built-multi-agent-research-system>
- Manus — Context Engineering for AI Agents — <https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus>
- OpenAI Swarm repo — <https://github.com/openai/swarm/tree/main>
- OpenAI Cookbook — Orchestrating Agents — <https://developers.openai.com/cookbook/examples/orchestrating_agents/>
- OpenAI orchestration docs — <https://developers.openai.com/api/docs/guides/agents/orchestration>
- CrewAI — Hierarchical Process — <https://docs.crewai.com/learn/hierarchical-process>
- CrewAI — Collaboration — <https://docs.crewai.com/concepts/collaboration>
- CrewAI — A2A delegation — <https://docs.crewai.com/en/learn/a2a-agent-delegation>
- Microsoft AutoGen publication — <https://www.microsoft.com/en-us/research/publication/autogen-enabling-next-gen-llm-applications-via-multi-agent-conversation-framework/>
- AutoGen SelectorGroupChat docs — <https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/selector-group-chat.html>
- LangGraph Interrupts concept — <https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/>
- LangChain blog — interrupt primitive — <https://blog.langchain.dev/making-it-easier-to-build-human-in-the-loop-agents-with-interrupt>
- Google ADK multi-agent docs — <https://google.github.io/adk-docs/agents/multi-agents/>
- Google ADK repo — <http://github.com/google/adk-docs>
- Manus documentation — <https://www.manus.im/docs>
- Manus technical investigation (community gist) — <https://gist.github.com/madikenz/5c4cd416ccd8549d51963dbfd3e3b5cf>
- AutoGPT PR #4799 (planner/executor separation) — <https://github.com/Significant-Gravitas/AutoGPT/pull/4799>
- Taxonomy of Hierarchical MAS (arXiv) — <https://arxiv.org/html/2508.12683>
