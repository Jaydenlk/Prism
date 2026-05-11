# Phase D: UserBrain Verification Layer

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Agent self-checks results before returning to user. Weak model compensation. "放心交给他。"

**Depends on:** Phase C complete (memory working)

**Spec:** `docs/superpowers/specs/2026-05-11-prism-architecture-redesign.md` §Phase D

---

## Task 1: Design Verification Pipeline

- [ ] Define verification stages:
  1. **Completeness check** — did agent answer the full question?
  2. **Fact check** — are claims verifiable? Use Context7 + web search
  3. **Consistency check** — does output contradict itself or user's known facts?
  4. **Confidence scoring** — HIGH (>80%) / MEDIUM (50-80%) / LOW (<50%)
- [ ] Define when to verify (not every response):
  - Research/analysis tasks → always verify
  - Factual claims → verify
  - Simple chat/acknowledgment → skip
- [ ] Document design
- [ ] Commit

## Task 2: Implement Context7 Client

- [ ] Create `executor_v2/userbrain/context7.py`:
```python
class Context7Client:
    BASE_URL = "https://context7.com/api/v2"
    
    async def resolve_library(self, name: str) -> list[Library]:
        """Find libraries matching name"""
        
    async def get_docs(self, library_id: str, query: str) -> str:
        """Get documentation context for a specific library/topic"""
        
    async def fact_check(self, claim: str) -> FactCheckResult:
        """Verify a factual claim against documentation"""
```
- [ ] Rate limiting: respect 429, exponential backoff
- [ ] Caching: cache library resolutions for 1 hour
- [ ] Commit

## Task 3: Implement VerifyAgent

- [ ] Create `executor_v2/userbrain/verify.py`:
```python
class VerifyAgent:
    async def verify(self, task: str, result: str, context: VerifyContext) -> VerifyResult:
        """Run verification pipeline on agent output"""
        
    async def _check_completeness(self, task: str, result: str) -> float:
        """Score 0-1: did the result address the full task?"""
        
    async def _check_facts(self, result: str) -> list[FactCheckResult]:
        """Extract claims → verify each via Context7 + search"""
        
    async def _check_consistency(self, result: str, user_memories: list) -> float:
        """Score 0-1: does result contradict known facts?"""
        
    async def _compute_confidence(self, completeness, facts, consistency) -> Confidence:
        """Aggregate scores → HIGH/MEDIUM/LOW"""
```
- [ ] Verification prompt: use small model to evaluate (not the same model that generated)
- [ ] For fact checking: extract factual claims → query Context7 → cross-reference
- [ ] Commit

## Task 4: Integrate Verification into Agent Loop

- [ ] Create `executor_v2/hooks/verify_hook.py`:
  - **post-response**: intercept agent output before returning to user
  - If task type = research/analysis → run VerifyAgent
  - If confidence HIGH → return as-is
  - If confidence MEDIUM → add warning badge, return with notes
  - If confidence LOW → don't return result, ask user to confirm uncertain points
- [ ] Modify callback: add `confidence` field to message_complete event
- [ ] Commit

## Task 5: Weak Model Compensation Strategies

- [ ] Implement in VerifyAgent:
  - **Multi-source cross-validation**: same fact from 2+ sources
  - **Step-by-step execution**: break research into search → filter → extract → verify → synthesize
  - **Structured output templates**: force model to fill template, not free-form
- [ ] Create research template:
```
## 调研报告: {topic}

### 1. 概述
{2-3 sentence summary}

### 2. 关键发现
| 发现 | 来源 | 验证状态 |
|------|------|----------|
| {finding} | {source_url} | ✓ 已验证 / ⚠ 待确认 |

### 3. 分析
{analysis}

### 4. 建议
{recommendations}

置信度: {HIGH/MEDIUM/LOW}
```
- [ ] Commit

## Task 6: Frontend Confidence UI

- [ ] Update `frontend-react/src/pages/Chat/MessageBubble.tsx`:
  - If message has confidence field → show badge:
    - HIGH (green): no badge (clean)
    - MEDIUM (amber): "⚠ 部分内容待确认" badge
    - LOW (red): "❓ 需要你确认以下内容" card with uncertain points
- [ ] Update `frontend-react/src/api/types.ts`: add confidence to Message type
- [ ] Commit

## Task 7: Integration Test

- [ ] Test with Claude: "帮我调研一下 2026 年最火的 AI Agent 框架" → verify result has confidence
- [ ] Test with DeepSeek: same task → compare confidence scores
- [ ] Test LOW confidence: ask something obscure → agent should say "我不太确定"
- [ ] Test Context7: technical question → facts verified against docs
- [ ] Commit

## Verification Criteria
- [ ] Research tasks produce verified, structured output
- [ ] Confidence scoring works (HIGH/MEDIUM/LOW)
- [ ] LOW confidence triggers user confirmation instead of blind output
- [ ] Context7 fact-checking integrated
- [ ] DeepSeek output quality improved via verification (closer to Claude)
- [ ] Frontend shows confidence badges
