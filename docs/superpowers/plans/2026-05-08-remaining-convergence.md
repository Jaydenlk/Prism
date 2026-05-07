# Remaining PRD Convergence — 后续 Session 执行计划

> **日期**: 2026-05-08
> **上下文**: Phase 1 (mock 清零 + admin tabs) 已完成，Skills 安装根因已修，飞书 IM 已跑通
> **剩余工作**: 按 PRD 愿景逐项收尾

---

## 已完成（本 session）

- [x] Phase 1: ObsPage 真数据 + Admin 5 tabs + Entropy 调度 + mock 清零
- [x] Skills 安装根因修复（SKILL.md 文件物化到永久目录）
- [x] 飞书 IM WebSocket 长连接模式（lark_oapi SDK，收发消息全链路跑通）
- [x] Simplify 3-agent 审查 + PJR + E2E Playwright 验证

---

## 下一 Session 优先级排序

### P0: Prompt Caching 真集成（PRD DOC-02 §3.1 核心能力）

**为什么 P0**: PRD 把 Prompt Caching 定义为"缓存经济学"的核心——静态/动态边界、cache_control 集成、节省金额可见。当前 CACHE_BOUNDARY_MARKER 定义了但 AnthropicDriver 从未使用。这是 PRD 远景和现实的最大架构差距。

**范围**:
- `executor/adapters/anthropic_driver.py`: 在 system prompt 的静态前缀 content block 上添加 `cache_control: {"type": "ephemeral"}`
- `executor/engine/prompt_assembler.py`: 确认 CACHE_BOUNDARY_MARKER 位置正确
- 验证: 真实 API 调用后检查 response.usage 中 `cache_read_input_tokens > 0`
- 前端: UsagePage 已经展示 cache 数据（API 就绪），只需确认数据流通

**文档置信度**: 需要 WebFetch Anthropic 官方 prompt caching 文档确认 cache_control 字段格式

**预计**: 1 个 worktree，2-3 commits

---

### P1: Plugin Builder 清理 + 完善（PRD DOC-05 §Task 5.4-5.5）

**为什么 P1**: 用户直接反馈"plugin 也是空的"。插件库有大量 `untyped-plugin-*` 垃圾条目（e2e 测试残留），Plugin Builder 的创建流程需要验证端到端可用。

**范围**:
- 清除 DB 中所有 `untyped-plugin-*` 和 `mkt-plugin-*` 垃圾记录
- Playwright 走完 Plugin Builder 完整流程: 新建 → 描述 → Agent 生成 manifest → 保存到库
- 验证保存的 plugin 能被 executor 加载
- 前端: Plugin Builder 页面的 UX 改进（如果发现问题）

**预计**: 1 个 worktree，3-4 commits

---

### P2: Sessions 侧栏 + Topbar 清理（PRD DOC-11 §Task 11.2）

**为什么 P2**: 审计未覆盖的区域，可能有死按钮。

**范围**:
- Playwright 验证 Sessions 侧栏: rename/delete 按钮是否接通
- Playwright 验证 Topbar 3 个 dev preview 按钮（L4294-4296）: 保留或删除
- 如发现断链路，用 systematic-debugging 定位根因修复

**预计**: 1 个 worktree，1-3 commits

---

### P3: 企业微信适配器接通（PRD DOC-08 §Task 8.2）

**为什么 P3**: 用户已表达意向，但需要先拿到企业微信凭证。

**范围**:
- 类似飞书的处理: 检查现有 `im_wecom.py` 代码完整度
- 确认 XML 签名验证 + AES 解密逻辑正确（参考企微官方文档）
- 如果企微也有官方 Python SDK，考虑集成
- 等用户提供 CorpID + Secret 后真实对接

**前置**: 用户创建企业微信自建应用并提供凭证

**预计**: 1 个 worktree，2-4 commits

---

### P4: 前端 UX 细节打磨（PRD DOC-10/11 视觉标准）

**为什么 P4**: 用户说"细节还有问题"。需要 Playwright 全面扫一遍。

**范围**:
- 移动端响应式修复（ObsPage 侧栏重叠问题）
- Skills 安装成功后的 toast 反馈（当前无反馈）
- 主题切换在移动端的验证
- Admin 页面移动端适配

**预计**: 1 个 worktree，3-5 commits

---

## 执行规范（每项必遵）

```
superpowers:brainstorming (如涉及新功能)
  → superpowers:writing-plans
  → superpowers:using-git-worktrees (隔离开发)
  → superpowers:test-driven-development
  → 实现
  → simplify (3 subagent 并行审查)
  → project-review:pjr (lint + build + 逻辑)
  → E2E Playwright (桌面 1280 + 移动 390×844)
  → git-merge-to-develop
```

前端改动追加: `frontend-design` + `ui-ux-pro-max`
调试 bug: `superpowers:systematic-debugging` (Phase 1 没完不许提 fix)
反打补丁: 严格禁止，根因修复，最终代码最简
