---
name: decisions-session-2026-05-20
description: 2026-05-20 session 的 10 个关键技术决策记录
metadata:
  type: project
---

## Session 2026-05-20 决策记录（10 项）

### DEC-001: Resend HTTP API（vs Gmail SMTP）
- **Chosen**: Resend HTTP API，三模式降级（Resend > SMTP > dev log）
- **Rejected**: Gmail SMTP — 国内 VPS 封锁 SMTP 端口 465/587
- **Evidence**: `backend/app/core/config.py:150`
- **Tradeoff**: 依赖 SaaS；新域名 mail.xixi.gold QQ 延迟

### DEC-002: Think Tank 辩论式+德尔菲式双模式
- **Chosen**: 双模式用户可选，辩论式互引反驳，德尔菲式独立后汇总
- **Rejected**: 仅辩论 / 仅德尔菲 — 覆盖场景不全
- **Evidence**: Du et al. 2023，结构化辩论准确率高 10%

### DEC-003: Thinking Mode Prompt Engineering（不改 TAOR）
- **Chosen**: System prompt 注入 + 前端 Markdown heading 解析三段卡片
- **Rejected**: 改 executor TAOR 循环 — 影响大，风险高
- **Evidence**: `docs/superpowers/specs/2026-05-20-think-tank-thinking-mode-design.md:44`

### DEC-004: Auto 选人关键词匹配 + 认知多样性
- **Chosen**: triggers 关键词匹配 + 不全选同领域，top 3-5
- **Rejected**: embedding 语义匹配 — KISS，persona 数量有限
- **Evidence**: Sigman 2018（5 人讨论优于聚合数千独立意见）

### DEC-005: Skill 持久化 /app/data（Docker volume）
- **Chosen**: PRISM_WORKSPACE 默认值改为 /app/data
- **Rejected**: os.getcwd()（/app/backend 容器临时层）— 容器重建丢失
- **Evidence**: 修复后 146 文件 vs 修复前 3 文件

### DEC-006: GitHub 下载 git clone --depth 1
- **Chosen**: git clone --depth 1 完整克隆
- **Rejected**: HTTP 逐文件递归 — 目录遍历遗漏，rate limit
- **Evidence**: `backend/app/api/v1/skills.py:961`

### DEC-007: ask_user_question Redis BLPOP 阻塞
- **Chosen**: 复用 permission_ask 的 BLPOP 模式，300s 超时
- **Rejected**: HTTP 轮询 — CLAUDE.md 陷阱第 8 条禁止
- **Evidence**: `executor/tools/builtin/ask_user_question.py:116`

### DEC-008: SSE 429 stale counter reset
- **Chosen**: TTL > 60s 时重置计数器为 1 并放行
- **Rejected**: 降低 MAX_CONNS / 依赖 finally 释放 — 治标不治本
- **Evidence**: `backend/app/services/sse_manager.py:158`

### DEC-009: Desktop App Tauri 2
- **Chosen**: Tauri 2（5MB 包体，系统 WebView，React dist/ 零改动）
- **Rejected**: Electron（120MB 包体）/ PWA（无 Docker 管理能力）
- **Evidence**: `docs/superpowers/specs/2026-05-20-desktop-app-design.md:54`

### DEC-010: VPS 2C2G 不足
- **Chosen**: 短期加 swap，中期升配
- **Rejected**: 禁用 Redis / 内存优化 — Redis 是核心机制，基线已超 2G
- **Evidence**: `HANDOFF-SESSION-2026-05-20.md:74`
