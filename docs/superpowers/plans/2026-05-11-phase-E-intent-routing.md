# Phase E: UserBrain Intent Router + Built-in Skills

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** User says natural language, system auto-routes to correct workflow. "顺手好用。"

**Depends on:** Phase D complete (verification working)

**Spec:** `docs/superpowers/specs/2026-05-11-prism-architecture-redesign.md` §Phase E

---

## Task 1: Implement IntentRouter

- [ ] Create `executor_v2/userbrain/router.py`:
```python
INTENT_CATEGORIES = [
    "memo",        # 备忘/记录
    "reminder",    # 提醒/日程
    "research",    # 搜索/调研
    "brainstorm",  # 讨论/研讨
    "writing",     # 写作/文档
    "analysis",    # 数据分析
    "meeting",     # 会议记录
    "chat",        # 日常对话（fallback）
]

class IntentRouter:
    async def classify(self, message: str, user_context: dict) -> Intent:
        """Use small model to classify user intent"""
        
    async def route(self, intent: Intent) -> Skill:
        """Map intent to skill"""
```
- [ ] Classification prompt: 让小模型（Haiku/DeepSeek-lite）从 8 类中选一个
- [ ] User memory 影响权重: "这个用户经常做调研" → research 权重提高
- [ ] Commit

## Task 2: Implement Skill Base Class

- [ ] Create `executor_v2/skills/base.py`:
```python
class Skill:
    name: str
    description: str
    system_prompt_addition: str  # 注入到 agent prompt 的指令
    tools: list[Tool]           # 此 skill 需要的工具
    verify: bool                # 是否需要验证层
    
    async def pre_run(self, context: SkillContext) -> SkillContext:
        """Skill-specific setup before agent run"""
        
    async def post_run(self, context: SkillContext, result: str) -> str:
        """Skill-specific post-processing"""
```
- [ ] Commit

## Task 3: Implement 4 Core Skills (Batch 1)

- [ ] Create `executor_v2/skills/chat.py` — **ChatSkill**:
  - 日常对话，记忆注入，自然回复
  - verify = False
  - system_prompt: 友好、简洁、记住上下文

- [ ] Create `executor_v2/skills/memo.py` — **MemoSkill**:
  - "帮我记一下 X" → 存储为结构化备忘
  - tools: memory store
  - post_run: 确认已存储
  - verify = False

- [ ] Create `executor_v2/skills/research.py` — **ResearchSkill**:
  - 多源搜索 → 交叉验证 → 结构化报告
  - tools: web_search, context7
  - verify = True (强制验证)
  - system_prompt: 分步执行（搜索→筛选→提取→验证→综合）
  - 输出模板: 调研报告格式

- [ ] Create `executor_v2/skills/brainstorm.py` — **BrainstormSkill**:
  - 框架引导（MECE/SWOT/五力/蓝海）
  - 多角度挑战用户假设
  - verify = False
  - system_prompt: 不顺从，反驳，深度思考
  
- [ ] Commit

## Task 4: Implement 4 Extended Skills (Batch 2)

- [ ] Create `executor_v2/skills/reminder.py` — **ReminderSkill**:
  - 定时提醒（存储 + 未来触发）
  - tools: memory store with timestamp tag
  - post_run: 确认提醒已设置

- [ ] Create `executor_v2/skills/writing.py` — **WritingSkill**:
  - 写作（邮件/报告/周报/文案）
  - 模板 + 审查流程
  - verify = True

- [ ] Create `executor_v2/skills/analysis.py` — **AnalysisSkill**:
  - 数据分析（Excel/CSV 处理）
  - tools: read file, python execution
  - verify = True

- [ ] Create `executor_v2/skills/meeting.py` — **MeetingSkill**:
  - 会议纪要（输入会议内容 → 摘要 + 行动项 + 跟进）
  - 输出模板: 会议纪要格式
  - verify = False

- [ ] Commit

## Task 5: Integrate Router into Agent Loop

- [ ] Create `executor_v2/hooks/router_hook.py`:
  - **setup**: classify intent → select skill → inject skill prompt + tools
  - Frontend event: emit `skill_matched` with skill name for UI display
- [ ] Modify `executor_v2/agent.py`: accept dynamic system_prompt from router
- [ ] Commit

## Task 6: Frontend Skill UI

- [ ] Update MessageBubble: show "正在使用 XX 技能" badge when skill_matched event received
- [ ] Add skill manual override: dropdown to force a specific skill
- [ ] Commit

## Task 7: Integration Test

- [ ] "帮我记一下明天下午3点开会" → MemoSkill
- [ ] "帮我查一下最近的 AI 新闻" → ResearchSkill
- [ ] "跟我讨论一下产品方向" → BrainstormSkill
- [ ] "帮我写一封邮件" → WritingSkill
- [ ] "你好" → ChatSkill
- [ ] Verify intent classification accuracy > 90%
- [ ] Commit

## Verification Criteria
- [ ] 7/8 intent categories correctly classified
- [ ] Each skill produces appropriate output format
- [ ] ResearchSkill uses verification layer
- [ ] BrainstormSkill actually pushes back (not agreeable)
- [ ] Frontend shows skill badge
