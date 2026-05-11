# Phase C: UserBrain Memory Layer (mem0)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Agent remembers users across sessions. "更懂你。"

**Depends on:** Phase B complete (multi-model executor with governance)

**Spec:** `docs/superpowers/specs/2026-05-11-prism-architecture-redesign.md` §Phase C

---

## Task 1: Research mem0 Integration

- [ ] Install: `pip install mem0ai`
- [ ] Read mem0 docs: how to add/search/update memories
- [ ] Determine storage backend: pgvector (reuse existing PostgreSQL) vs separate vector DB
- [ ] Design memory schema: what to store, how to index, how to recall
- [ ] Document in `docs/research/2026-05-11-mem0-integration.md`
- [ ] Commit

## Task 2: Implement MemoryManager

- [ ] Create `executor_v2/userbrain/__init__.py`
- [ ] Create `executor_v2/userbrain/memory.py`:
```python
class MemoryManager:
    async def extract(self, user_id: str, messages: list) -> list[Memory]:
        """Extract facts/preferences/habits from conversation"""
        
    async def recall(self, user_id: str, query: str, limit: int = 10) -> list[Memory]:
        """Retrieve relevant memories for current context"""
        
    async def inject_prompt(self, user_id: str, current_prompt: str) -> str:
        """Build memory-augmented system prompt section"""
        
    async def store(self, user_id: str, memory: Memory) -> None:
        """Persist a new memory"""
        
    async def delete(self, user_id: str, memory_id: str) -> None:
        """Remove a memory"""
```
- [ ] Memory types: fact ("用户住在上海"), preference ("喜欢简洁输出"), habit ("周末常去杭州")
- [ ] Extraction: use small model (Haiku/DeepSeek-lite) to extract from conversation
- [ ] Commit

## Task 3: Integrate Memory into Agent Loop

- [ ] Create `executor_v2/hooks/memory_hook.py`:
  - **setup** (before agent run): recall relevant memories → inject into system prompt
  - **teardown** (after agent run): extract new memories from conversation → store
- [ ] Memory injection format in prompt:
```
## 关于用户
你已经了解以下信息：
- 用户住在上海（来源：2026-05-09 对话）
- 用户偏好简洁输出（来源：多次反馈）
- 用户周末常去杭州（来源：2026-05-08 对话）
```
- [ ] Commit

## Task 4: Backend Memory API

- [ ] Create `backend/app/api/v1/memories.py`:
  - GET /memories — list user's memories
  - POST /memories — manually add memory
  - DELETE /memories/{id} — delete memory
  - GET /memories/search?q=xxx — search memories
- [ ] Create `backend/app/services/memory_service.py`
- [ ] Commit

## Task 5: Frontend Memory UI

- [ ] Create `frontend-react/src/pages/Settings/MemoryTab.tsx`:
  - List all memories with type badges (fact/preference/habit)
  - Delete button per memory
  - Search input
  - "添加记忆" manual input
- [ ] Wire into Settings page as new tab
- [ ] Commit

## Task 6: Integration Test

- [ ] Session 1: say "我住在上海，周末喜欢去杭州玩"
- [ ] Close session
- [ ] Session 2: say "帮我查一下高铁票" → agent should auto-query 上海→杭州
- [ ] Verify memories in Settings → Memory tab
- [ ] Delete a memory → verify next session doesn't use it
- [ ] Commit

## Verification Criteria
- [ ] Cross-session memory: conversation info persists and influences next conversation
- [ ] Auto-extraction: memories extracted without user explicitly asking
- [ ] Memory recall: relevant memories injected into prompt
- [ ] Memory management: CRUD via API + frontend UI
- [ ] Privacy: memories are per-user, no cross-user leakage
