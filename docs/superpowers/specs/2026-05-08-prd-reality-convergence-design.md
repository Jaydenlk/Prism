# PRD-Reality Convergence — 从"玩具"到"工具"

> **日期**: 2026-05-08
> **触发**: 用户验收发现大量功能为表面功夫，达不到 PRD 设计的远景
> **目标**: 对标 PRD_V4 (DOC-00~12) 愿景，消除所有假数据/死按钮/placeholder/断链路
> **标准**: CLAUDE.md 硬规则 A~H + 六原则 + 验收标准

---

## 0. 现状诊断（基于代码审计，非推测）

### 比预想好的部分
- **UsagePage** 已调真实 API（`PrismAPI.providers.usage()`），非 mock
- **SSE** 已处理 `permission_ask` + `coordinator_plan_update` 事件
- **飞书 Adapter** 440+ 行真实实现（签名验证 + AES 解密 + webhook 路由）
- **后端所有 API 端点**返回真实数据（usage/harness/admin/entropy/stats）

### 真正需要修的
| 问题 | 根因 | 后端就绪? |
|---|---|---|
| ObsPage 纯 mock（4 stat-card + 7 trace 全硬编码） | 前端未调 `/harness/analytics` | ✅ |
| Admin 5 placeholder tab（guardrails/skills/billing/infra/obs） | 前端未消费已有 API | ✅ |
| audit 分支 8 commits 未合并（密码/死按钮/主题持久化） | 用户未授权 merge | ✅ |
| Entropy Detector 无定时调度 | 未挂 scheduler | ✅ 代码 444 行 |
| Sessions 侧栏 rename/delete 按钮未验证 | 审计未覆盖 | 需验证 |
| Plugin Builder 完整流程未验证 | 审计未覆盖 | 需验证 |
| Topbar 3 dev preview 按钮 | 开发遗留 | N/A |
| 飞书主动推送消息（bot push）未实现 | 只做了 webhook 被动接收 | 部分 |
| Prompt Caching 未集成 | CACHE_BOUNDARY_MARKER 定义但未用 | ❌ 需改 Driver |
| Prism.html L122-158 残余 mock 常量 | 开发遗留 | N/A |

---

## 1. 阶段 1：合并 + 清零（基础卫生）

### 1.1 合并 audit/prd-vs-reality 分支
- 验证 8 commits 在 develop 上 rebase clean
- 跑 backend pytest + executor pytest + e2e 全绿
- 合到 develop

### 1.2 ObsPage 接真实数据
**当前**：Prism.html L2651-2686，4 个 stat-card（p50 延迟/p95 延迟/重试风暴/崩溃恢复率）+ 7 条 trace 全硬编码

**改为**：
- 调用 `PrismAPI.harness.analytics({ days: 7 })` 获取真实数据
- stat-card 展示：平均 turn_count / 工具错误率 / compaction 频率 / cache 命中率
- trace 列表替换为最近 runs 的 harness_summary 摘要
- 空数据时显示 empty state（"暂无运行数据"）而非假数据
- 参考 DOC-12 §Task 12.2 的 8 信号设计

### 1.3 Admin 5 个 placeholder tab 补完

**guardrails tab**：
- 调 `PrismAPI.harness.config()` 展示当前护栏规则列表
- 调 `PrismAPI.harness.entropyCheck()` 展示最近 entropy 信号
- 展示 guardrail_triggers 统计（from admin stats）

**skills tab**：
- 调 `PrismAPI.skills.list()` 展示全局 skill 安装情况
- 展示每个 skill 的使用统计（调用次数 / 最近使用）
- 管理操作：启用/禁用/卸载

**billing tab**：
- 调 `PrismAPI.admin.usage()` 展示全局用量
- per_provider 分组饼图
- 30 天趋势折线图
- cache 节省金额卡片

**infra tab**：
- 调 `PrismAPI.health.detailed()` 展示组件健康
- 展示 Provider 熔断状态（from admin stats component_health）
- 展示当前并发 Run 数 / 队列深度

**observability tab**：
- 调 `PrismAPI.harness.analytics()` 展示聚合指标
- 调 `PrismAPI.harness.entropyCheck()` 展示 8 信号雷达图
- 手动触发阈值校准按钮

### 1.4 Entropy Detector 定时调度
- 在 Backend lifespan 中添加 `asyncio.create_task(entropy_scheduler())`
- 每小时自动执行一次 entropy check
- 结果写 audit_logs + 触发 AlertDispatcher（若超阈值）

### 1.5 清除残余 mock 常量
- 删除 Prism.html L122-158 的 PROVIDERS/MCP_SERVERS/IM_CHANNELS/SKILLS/RECENT_RUNS 常量
- 确认无代码依赖这些常量（grep 验证）
- 如有依赖，替换为真实 API 调用

---

## 2. 阶段 2：审计扫净 + 核心深化

### 2.1 Sessions 侧栏
- 用 Playwright 驱动浏览器，验证 rename/delete 按钮
- 如果不通，找根因修复（PATCH/DELETE session API 已存在）

### 2.2 Plugin Builder 完整流程
- Playwright 走完：创建 Plugin → 编写代码 → 验证 → 保存到 library
- 后端 `/plugins/bootstrap` → `/plugins/create-code` → `/plugins/validate` → `/library/import` 链路验证

### 2.3 Topbar dev 遗留按钮
- Prism.html L4294-4296 三个 dev preview 按钮
- 判断：生产环境不需要 → 删除；需要 → 接通真实功能

### 2.4 Prompt Caching 集成
- **AnthropicDriver**：在 system prompt 的静态前缀部分添加 `cache_control: {"type": "ephemeral"}`
- **PromptAssembler**：CACHE_BOUNDARY_MARKER 位置后的 content block 不带 cache_control
- 参考 DOC-02 v4 §3.1 的设计 + Anthropic 官方 prompt caching 文档（需 WebFetch 验证）
- **OpenAIDriver**：不支持 prompt caching，跳过

---

## 3. 阶段 3：飞书 IM 真实对接

### 3.1 调研阶段（文档置信度硬要求）
- 用 exa MCP 搜索飞书开放平台官方文档
- WebFetch 飞书 Bot SDK / 事件订阅 / 消息卡片 / WebSocket 长连接的 primary source
- 理解：应用类型（自建应用 vs 商店应用）、权限配置、事件订阅方式

### 3.2 FeishuAdapter 增强
**现有能力**（保留）：
- Webhook 接收 + 签名验证 + AES 解密
- 消息路由到 IMGateway

**新增能力**：
- Bot 主动发送消息（text / interactive card）
- WebSocket 长连接模式（替代 webhook polling，无需公网 IP）
- 消息卡片模板（Agent 回复格式化）
- 飞书事件订阅（im.message.receive_v1）

### 3.3 用户绑定流程
- 前端 IM 设置页：展示配对码（6 位，5min TTL）
- 用户在飞书群/私聊中发送配对码 → FeishuAdapter 识别 → 调 `im_binding_service.pair()` → 绑定 Prism 用户
- 绑定后飞书消息自动路由到该用户的 Prism session

### 3.4 端到端验证
- 由于需要飞书应用凭证，真实 e2e 测试需要用户提供 App ID / App Secret
- 单元测试 mock 飞书 API 返回，验证路由逻辑
- 前端 IM 配置页 Playwright 验证

---

## 4. 执行策略

### 每阶段执行流程
```
brainstorming (本文档) 
  → writing-plans (详细实施计划)
  → worktree 隔离开发
  → TDD (先写失败测试)
  → 实现
  → simplify (3 subagent 并行审查)
  → pjr (lint + build + 逻辑验证)
  → e2e (Playwright 真驱动浏览器，桌面+移动双端)
  → git-merge-to-develop
```

### 前端改动额外要求
- 加载 `frontend-design` + `ui-ux-pro-max` skill
- PJR 阶段：`node --check frontend/apiClient.js` + 逻辑走查
- 视觉对标 Claude.ai 风格（深灰/暖白/留白/serif 标题）

### 子 agent 调度策略
- 独立的 admin tab 可以并行（billing/guardrails/infra/obs/skills 互不依赖）
- 飞书调研可以和前端清理并行
- Prompt Caching 独立于前端工作

### 决策记录
- 所有技术决策写入 `.claude/memory/decisions.md`
- ADR 级别决策写入项目根 `DECISIONS.md`

---

## 5. 成功标准

按 CLAUDE.md 验收标准逐条对照：

- [ ] 零 mock 数据：所有页面展示真实 API 返回的数据
- [ ] 零 placeholder：Admin 所有 tab 有真实功能
- [ ] 零死按钮：每个 onClick 都接通真实逻辑
- [ ] 链路完整：每条业务链路从用户操作到 DB 变更可追踪
- [ ] E2E 双端：桌面 ≥1280 + 移动 390×844，每按钮每流程模拟人走一遍
- [ ] 状态变更验证：不只看渲染，验证 network 请求 + DB 写入 + UI 更新
- [ ] 代码最简：无冗余、无打补丁、无 TODO 占位
- [ ] 飞书能收能发：从飞书发消息 → Agent 处理 → 飞书回消息（需用户提供凭证）
- [ ] Prompt Caching 真用上：Anthropic 请求中 cache_read_input_tokens > 0
