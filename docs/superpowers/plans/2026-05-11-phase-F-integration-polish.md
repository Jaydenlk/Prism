# Phase F: Integration Polish + E2E

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Remove old executor, full E2E validation, production-ready.

**Depends on:** Phase E complete (all skills working)

**Spec:** `docs/superpowers/specs/2026-05-11-prism-architecture-redesign.md` §Phase F

---

## Task 1: Remove Old Executor

- [ ] Delete `executor/` directory entirely
- [ ] Rename `executor_v2/` → `executor/`
- [ ] Update all imports across backend
- [ ] Update Dockerfile COPY paths
- [ ] Update ProcessManager command
- [ ] Commit

## Task 2: Docker Compose Update

- [ ] Update `docker-compose.yml`:
  - Backend builds with new executor
  - Add mem0 dependencies (pgvector extension to existing PostgreSQL)
  - Add Context7 MCP server (optional service)
- [ ] Update `backend/Dockerfile`:
  - Install mem0ai, claude-agent-sdk
  - Remove old executor dependencies if any
- [ ] Update `nginx/nginx.conf`:
  - Static files: `frontend/` → `frontend-react/dist/`
  - Verify SSE passthrough still works
- [ ] Rebuild and test: `docker compose build && docker compose up -d`
- [ ] Commit

## Task 3: IM Gateway Validation

- [ ] Verify Feishu adapter works with new executor
- [ ] Verify Telegram adapter works
- [ ] Test: send message via IM → agent responds via IM
- [ ] Fix any broken integration
- [ ] Commit

## Task 4: Frontend Build Integration

- [ ] `cd frontend-react && npm run build`
- [ ] Copy `dist/` to nginx static path
- [ ] Verify: access via nginx (port 80/8080), not Vite dev server
- [ ] Test all pages work in production build
- [ ] Commit

## Task 5: Full E2E Playwright Test (Desktop)

Viewport: 1280×800. Login as admin@prism.dev.

- [ ] **备忘场景**: "帮我记一下明天下午3点跟张总开会讨论Q3计划" → MemoSkill → 存储成功 → Settings 里能看到
- [ ] **调研场景**: "帮我查一下目前市面上主流的 AI Agent 产品有哪些，做个对比" → ResearchSkill → 结构化报告 → 有验证标记
- [ ] **brainstorm 场景**: "我想做一个个人助手产品，你觉得核心差异化在哪" → BrainstormSkill → 框架引导 → 有反驳
- [ ] **写作场景**: "帮我写一封给投资人的项目介绍邮件" → WritingSkill → 格式化输出
- [ ] **对话场景**: "你好，你是谁" → ChatSkill → 自然回复
- [ ] **记忆验证**: 新 session → "我之前让你记的会议是什么时候" → agent 回忆出来
- [ ] **弱模型验证**: 切换到 DeepSeek → 重复调研场景 → 结果有验证 → 质量可接受

## Task 6: Full E2E Playwright Test (Mobile)

Viewport: 390×844. Same scenarios as Task 5, focus on:

- [ ] Sidebar overlay 正常
- [ ] 消息气泡不溢出
- [ ] Skill badge 显示正常
- [ ] Confidence badge 不遮挡内容
- [ ] 触摸目标 ≥ 44px

## Task 7: Simplify Review

- [ ] Run simplify skill (3 parallel agents: reuse, quality, efficiency)
- [ ] Fix all CRITICAL and HIGH issues
- [ ] Commit

## Task 8: PJR

- [ ] Frontend: `npm run lint` + `npm run build` → 0 errors
- [ ] Backend: Python syntax check on all files
- [ ] Docker: rebuild + all services healthy
- [ ] Commit

## Task 9: Final Merge + Documentation

- [ ] Merge to develop (git-merge-to-develop skill)
- [ ] Update PROGRESS.md
- [ ] Update HANDOFF-LOG.md
- [ ] Update DECISIONS.md if needed
- [ ] Final commit

## Verification Criteria (Product Level)
- [ ] 5 场景全部跑通（备忘/调研/brainstorm/写作/对话）
- [ ] 跨 session 记忆生效
- [ ] 弱模型有验证补偿
- [ ] 桌面端 + 移动端全通
- [ ] Docker 一键部署可用
- [ ] 旧 executor 完全移除
