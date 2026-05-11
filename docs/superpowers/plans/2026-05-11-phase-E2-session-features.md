# Phase E2: Session Advanced Features (Share/Fork/Tag)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** PRD DOC-11 要求的会话高级功能 — 分享、Fork、Tag、批量操作。

**Depends on:** Phase E complete (intent routing + skills working)

**PRD 对齐:** DOC-11 §11.2 会话管理

---

## Task 1: Session Sharing (分享)

**后端:**
- [ ] Create `backend/app/api/v1/shares.py`:
  - POST /sessions/{id}/share → 生成分享链接（UUID token，可设过期时间）
  - GET /shared/{token} → 只读访问会话内容（无需登录）
  - DELETE /sessions/{id}/share → 撤销分享
- [ ] Create `backend/app/models/session_share.py`: session_id, token, expires_at, created_by
- [ ] Alembic migration

**前端:**
- [ ] Sessions 页 → 每个 session 卡片加"分享"按钮
- [ ] 点击 → Modal：生成链接 + 复制按钮 + 过期时间选择（1天/7天/永久）
- [ ] 分享页面 `/shared/{token}`：只读对话展示，Prism 品牌水印
- [ ] Commit

## Task 2: Session Fork (分支)

**后端:**
- [ ] POST /sessions/{id}/fork → 深拷贝 session + 所有 messages → 新 session
- [ ] 可选参数：from_message_id（从某条消息开始 fork，之后的消息不复制）
- [ ] Fork 记录 parent_session_id 关联

**前端:**
- [ ] 对话页 → 每条消息 hover 显示"从这里分支"按钮
- [ ] 点击 → 创建新 session → 自动跳转
- [ ] Sessions 页显示 fork 关系（tree icon）
- [ ] Commit

## Task 3: Session Tags (标签)

**后端:**
- [ ] Add `tags` JSONB column to sessions table (migration)
- [ ] PATCH /sessions/{id} 支持 tags 字段
- [ ] GET /sessions?tag=xxx 支持按标签筛选

**前端:**
- [ ] Sessions 页 → 标签过滤条（pills）
- [ ] 每个 session 卡片显示标签 badges
- [ ] 点击 session → 编辑标签（输入框 + 回车添加）
- [ ] 预设标签建议：工作、生活、学习、调研、备忘
- [ ] Commit

## Task 4: Batch Operations (批量操作)

**后端:**
- [ ] POST /sessions/batch-delete — body: { session_ids: [] }
- [ ] POST /sessions/batch-tag — body: { session_ids: [], tags: [] }
- [ ] POST /sessions/batch-export — 批量导出为 Markdown zip

**前端:**
- [ ] Sessions 页 → 多选模式（checkbox）
- [ ] 选中后底部出现操作栏：删除 / 添加标签 / 导出
- [ ] 删除需确认 Modal
- [ ] Commit

## Verification Criteria
- [ ] 分享链接生成 + 只读访问 + 撤销
- [ ] Fork 从任意消息分支 + 新 session 正确
- [ ] 标签 CRUD + 筛选
- [ ] 批量操作（删除/标签/导出）
- [ ] 桌面端 + 移动端
