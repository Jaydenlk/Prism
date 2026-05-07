# PRD Feature Inventory — Prism v2

**生成日期**: 2026-05-08  
**来源文档**: DOC-00 ~ DOC-12 v4 + DOC-CC-ONBOARDING  
**总条数**: 87  
**说明**: 仅列用户可见 / 用户能用的功能。纯内部 ADR、数据格式规范、架构原则不计入。

---

| ID | 文档 | 功能名 | 用户场景 (1 句) | 预期 UI 位置 | 预期后端 API |
|---|---|---|---|---|---|
| F-01 | DOC-06 | 邀请码注册 | 新用户凭邀请码注册账号 | 注册页 RegisterForm | POST `/auth/register` |
| F-02 | DOC-06 | 邮箱密码登录 | 已注册用户输入邮箱+密码登录 | 登录页 LoginForm | POST `/auth/login` |
| F-03 | DOC-06 | 刷新 Access Token | Token 过期后自动/手动刷新保持登录态 | 透明(由 apiClient 自动触发) | POST `/auth/refresh` |
| F-04 | DOC-06 | 登出 | 用户退出登录,清除 cookie 和 token | 用户菜单 → 退出 | POST `/auth/logout` |
| F-05 | DOC-06 | 查看当前账号信息 | 用户查看自己的邮箱、用户名、角色 | 设置页 → 账号信息 / Header 用户菜单 | GET `/auth/me` |
| F-06 | DOC-06, DOC-07 | SSE Ticket 换取 | 建立实时流连接前换取一次性凭证 | 透明(由 useSSE hook 自动触发) | POST `/auth/sse-ticket` |
| F-07 | DOC-07 | 创建新会话 | 用户发起新对话,系统创建空会话 | ChatPage 新会话按钮 / 侧边栏 NewSessionButton | POST `/sessions` |
| F-08 | DOC-07 | 查看会话列表 | 用户在侧边栏浏览所有历史会话 | 侧边栏 SessionList | GET `/sessions` |
| F-09 | DOC-07 | 查看会话详情 | 用户点击某个会话查看其配置和状态 | ChatPage `[sessionId]` / SessionCard | GET `/sessions/{id}` |
| F-10 | DOC-07 | 重命名会话 | 用户为会话设置自定义标题 | 侧边栏 SessionItem 右键菜单 → 重命名 | PATCH `/sessions/{id}` |
| F-11 | DOC-07 | 置顶/取消置顶会话 | 用户将常用会话固定在列表顶部 | 侧边栏 SessionItem 右键菜单 → 置顶 | PATCH `/sessions/{id}` (`is_pinned`) |
| F-12 | DOC-07 | 删除会话 | 用户删除不再需要的会话及其所有消息 | 侧边栏 SessionItem 右键菜单 → 删除 + 确认弹窗 | DELETE `/sessions/{id}` |
| F-13 | DOC-07 | 查看会话消息历史 | 用户打开会话后加载历史消息 | ChatPage MessageList | GET `/sessions/{id}/messages` |
| F-14 | DOC-07 | 搜索会话 | 用户按标题关键词搜索历史会话 | 侧边栏 SessionSearchBar | GET `/sessions?q=...` |
| F-15 | DOC-11 | 导出会话 | 用户将会话内容导出为 JSON 或 Markdown 文件 | 侧边栏 SessionItem 右键菜单 → 导出 | GET `/sessions/{id}` [前端拼装] |
| F-16 | DOC-11 | 导入会话 | 用户将已导出的会话文件重新导入系统 | 侧边栏 → 导入按钮 | POST `/sessions` [前端解析后] |
| F-17 | DOC-11 | 分享会话(只读链接) | 用户生成只读分享链接发给他人 | 侧边栏 SessionItem 右键菜单 → 分享 | [推测] POST `/sessions/{id}/share` |
| F-18 | DOC-11 | Fork 会话(新建分支) | 用户以当前会话为起点新建一个分支会话 | 侧边栏 SessionItem 右键菜单 → Fork | [推测] POST `/sessions/{id}/fork` |
| F-19 | DOC-11 | 归档会话 | 用户将会话归档,从主列表隐藏 | 侧边栏 SessionItem 右键菜单 → 归档 | [推测] PATCH `/sessions/{id}` (`archived`) |
| F-20 | DOC-11 | 为会话添加标签 | 用户给会话打多个标签便于分组 | 侧边栏 SessionItem 右键菜单 → 添加标签 | [推测] PATCH `/sessions/{id}` (`tags`) |
| F-21 | DOC-11 | 会话多选批量操作 | 用户选中多个会话后批量归档/删除/导出 | 侧边栏 多选模式 | DELETE/PATCH (多次或批量) |
| F-22 | DOC-07 | 提交任务(发送消息) | 用户在输入框输入消息并发送给 Agent | ChatPage ChatInput → 发送按钮 / Enter | POST `/tasks` |
| F-23 | DOC-07 | 实时流式对话(SSE) | 用户看到 Agent 逐字输出的打字效果 | ChatPage AssistantMessage (streaming) | GET `/sessions/{id}/stream?ticket=` |
| F-24 | DOC-07 | 查看工具调用卡片 | 用户看到 Agent 调用了哪个工具及其参数 | ChatPage ToolCallCard (折叠/展开) | SSE `tool_start/tool_end` 事件 |
| F-25 | DOC-07 | 取消正在执行的 Run | 用户中途取消 Agent 的执行 | ChatPage Header → 停止按钮 | POST `/sessions/{id}/cancel` |
| F-26 | DOC-07 | 查看排队状态 | 用户提交消息时 Session 已有 Run 在跑,看到排队提示 | ChatPage QueueIndicator | GET `/sessions/{id}/queue` + SSE `queue_update` |
| F-27 | DOC-07 | 取消排队消息 | 用户撤回尚未执行的排队消息 | ChatPage QueueIndicator → 取消按钮 | DELETE `/sessions/{id}/queue/{item_id}` |
| F-28 | DOC-07 | 回应 Permission Ask 弹窗 | Agent 请求执行敏感操作时用户允许或拒绝 | ChatPage PermissionAskModal | POST `/sessions/{id}/permission-answer` |
| F-29 | DOC-07 | Run 异常中断后恢复 | Coordinator Run 崩溃后用户点击"恢复执行"重启 | ChatPage RunCrashedBanner → 恢复按钮 | POST `/runs/{id}/resume` |
| F-30 | DOC-07 | 查看 Run 完成状态和用量 | 用户看到对话结束后的 token 消耗、耗时和成本 | ChatPage RunStatusBar | GET `/runs/{id}` + SSE `run_complete` 事件 |
| F-31 | DOC-07 | 查看 Harness 治理通知 | 用户看到护栏触发、循环检测等 Harness 事件 | ChatPage HarnessNotice + Toast | SSE `harness_event` 事件 |
| F-32 | DOC-07 | Coordinator 步骤可视化 | 用户看到多步骤任务的规划进度和当前步骤 | ChatPage CoordinatorPlanPanel / PlanStepList | SSE `plan_step / step_start / step_end` 事件 |
| F-33 | DOC-11 | 选择 Agent 类型 | 用户在发送消息时指定使用哪种 Agent(通用/研究/规划/验证) | ChatPage ChatInput → Agent 类型选择器 | POST `/tasks` (`agent_type` 字段) |
| F-34 | DOC-09 | 查看 Provider 列表 | 用户查看已配置的 AI Provider 及健康状态 | 设置页 → Provider 管理 ProviderCard 列表 | GET `/providers` |
| F-35 | DOC-09 | 添加新 Provider | 用户新增一个 AI Provider 配置(含 API Key) | 设置页 → Provider 管理 → 新增 ProviderForm | POST `/providers` |
| F-36 | DOC-09 | 编辑 Provider | 用户修改已有 Provider 的配置 | 设置页 → Provider 管理 → 编辑 ProviderForm | PATCH `/providers/{id}` |
| F-37 | DOC-09 | 删除 Provider | 用户删除不再使用的 Provider | 设置页 → Provider 管理 → 删除确认 | DELETE `/providers/{id}` |
| F-38 | DOC-09 | 查看 Provider 预设列表 | 用户从内置预设中一键选择厂商配置 | 设置页 → Provider 管理 → 预设下拉 | GET `/providers/presets` |
| F-39 | DOC-09 | 测试 Provider 连通性 | 用户验证 Provider 是否可用并查看能力徽章 | 设置页 → Provider 管理 → 测试按钮 | POST `/providers/{id}/test` |
| F-40 | DOC-09 | 查看 Provider 健康状态 | 用户看到哪些 Provider 正处于熔断状态 | 设置页 → Provider 管理 ProviderCard (`is_healthy`) | GET `/providers` (合并 Redis 熔断状态) |
| F-41 | DOC-09 | 查看用量统计 | 用户查看按 Provider / 日 / 周 / 月的 Token 消耗和费用 | 用量仪表盘 `/usage` | GET `/providers/usage?group_by=day` |
| F-42 | DOC-09 | 查看 Cache 命中率和节省金额 | 用户看到 Prompt Cache 效率和节省了多少费用 | 用量仪表盘 SummaryCards (Cache 命中率卡) | GET `/providers/usage` (cache_hit_ratio + cache_savings) |
| F-43 | DOC-09 | 查看 Provider 用量饼图 | 用户看到按 Provider 分层的 token 消耗比例 | 用量仪表盘 ProviderPieChart | GET `/providers/usage` |
| F-44 | DOC-09 | 查看用量趋势折线图 | 用户看到按日/周/月的成本和 Cache 命中率双轴趋势 | 用量仪表盘 UsageTrendChart | GET `/providers/usage` |
| F-45 | DOC-09 | 查看最近 Run 列表(含 Harness 摘要) | 用户看到最近执行的对话列表及护栏触发等摘要信息 | 用量仪表盘 RecentRunsList | GET `/sessions/{id}/runs` + GET `/runs/{id}` |
| F-46 | DOC-09 | 查看 MCP Server 列表 | 用户查看系统内置和自定义的 MCP Server | 设置页 → MCP 管理 MCPServerCard 列表 | GET `/mcp-servers` |
| F-47 | DOC-09 | 创建自定义 MCP Server | 用户添加一个自定义 MCP Server 配置 | 设置页 → MCP 管理 → 新增表单 | POST `/mcp-servers` |
| F-48 | DOC-09 | 安装/启用 MCP Server | 用户安装某个 MCP Server 到自己的 Agent 环境 | 设置页 → MCP 管理 → 安装按钮 | POST `/mcp-installs` |
| F-49 | DOC-09 | 更新 MCP 安装配置 | 用户覆盖 MCP Server 的特定配置项 | 设置页 → MCP 管理 MCPServerCard → 配置覆盖 | PATCH `/mcp-installs/{id}` |
| F-50 | DOC-09 | 启用/禁用 MCP Server | 用户临时关闭某个 MCP Server 而不卸载 | 设置页 → MCP 管理 MCPServerCard Toggle | PATCH `/mcp-installs/{id}` (`is_enabled`) |
| F-51 | DOC-09 | 卸载 MCP Server | 用户从自己的环境中卸载某个 MCP Server | 设置页 → MCP 管理 → 卸载按钮 | DELETE `/mcp-installs/{id}` |
| F-52 | DOC-08 | 生成 IM 配对码 | 用户在设置页生成 6 位配对码用于绑定 IM 账号 | 设置页 → IM 绑定 IMBindingCard → 生成配对码 | POST `/im/bindings/pair` |
| F-53 | DOC-08 | IM 账号绑定(配对流程) | 用户在 IM 端发送配对码完成绑定 | 设置页 → IM 绑定 — 显示配对码+倒计时+二维码 | GET `/im/bindings` (轮询检测绑定) |
| F-54 | DOC-08 | 查看已绑定 IM 账号 | 用户查看当前已绑定的飞书/企微/Telegram 账号 | 设置页 → IM 绑定 IMBindingCard 列表 | GET `/im/bindings` |
| F-55 | DOC-08 | 解绑 IM 账号 | 用户解除某个 IM 平台的绑定 | 设置页 → IM 绑定 IMBindingCard → 解绑按钮 | DELETE `/im/bindings/{id}` |
| F-56 | DOC-08 | 通过 IM 发送消息给 Agent | 用户在飞书/企微/Telegram 中直接对话 Agent | IM 客户端(飞书/企微/TG)内对话框 | IM Webhook 内部 → POST `/tasks` |
| F-57 | DOC-05 | 浏览 Skills 市场 | 用户在 Skills Store 浏览可安装的 Skill | `/skills` SkillsStorePage SkillGrid | GET `/skills/search` |
| F-58 | DOC-05 | 搜索 Skills | 用户按关键词搜索 Skills | `/skills` SkillSearchBar | GET `/skills/search?q=...` |
| F-59 | DOC-05 | 按来源筛选 Skills | 用户按 Local / GitHub 筛选 Skill 来源 | `/skills` SkillSearchBar 源筛选器 | GET `/skills/search?source=...` |
| F-60 | DOC-05 | 查看 Skill 详情 | 用户点击 Skill 卡片查看详细描述、版本历史和依赖 | `/skills` SkillDetailDrawer | GET `/skills/{name}` |
| F-61 | DOC-05 | 安装 Skill | 用户安装选中的 Skill 到自己的 Agent 环境 | `/skills` SkillCard → 安装 → InstallConfirmDialog | POST `/skills/install` |
| F-62 | DOC-05 | 查看已安装 Skill 列表 | 用户查看自己已安装的 Skill | `/skills` InstalledSkillsList (已安装 Tab) | GET `/skills/installed` |
| F-63 | DOC-05 | 卸载 Skill | 用户卸载不再使用的 Skill | `/skills` InstalledSkillsList → 卸载按钮 | DELETE `/skills/{name}` |
| F-64 | DOC-05 | 更新 Skill | 用户将已安装 Skill 更新到新版本 | `/skills` InstalledSkillsList → 更新按钮 | POST `/skills/{name}/update` |
| F-65 | DOC-04, DOC-11 | 使用 Plugin Builder 向导创建插件 | 用户通过与 PluginBuilder Agent 的多轮对话创建自定义插件 | `/plugins/create` PluginCreatePage | POST `/tasks` (`agent_type=plugin_builder`) |
| F-66 | DOC-04, DOC-11 | 查看插件创建实时预览 | 用户在创建过程中看到插件结构的实时预览和完整度进度条 | `/plugins/create` PluginPreviewPanel + 完整度进度条 | SSE 事件 `plugin_builder.scored` |
| F-67 | DOC-04, DOC-11 | 确认插件设计方案 | 用户在 PluginBuilder 展示完方案后点击确认生成 | `/plugins/create` ConfirmDesignButton | POST `/tasks` (下一轮对话触发生成) |
| F-68 | DOC-03, DOC-11 | 查看 Harness 配置(只读) | 用户查看当前 Harness 配置的来源追踪(代码默认 vs yaml) | `/settings/harness` HarnessConfigPage | GET `/harness/config` |
| F-69 | DOC-12 | 查看 Harness 运行时状态 | Admin 查看当前活跃中间件、熔断器状态等 | `/admin/observability` Harness Analytics Tab 汇总卡 | GET `/harness/status` |
| F-70 | DOC-12 | 查看 Harness 审计轨迹 | Admin 查询护栏触发、Hook 触发等治理事件历史 | `/admin/observability` Harness Analytics Tab Runs 列表 | GET `/harness/traces` |
| F-71 | DOC-12 | 查看指定 Run 的 Harness 摘要 | Admin 展开某个 Run 查看护栏触发次数、Compaction 次数等详情 | `/admin/observability` Runs 列表 → 展开 harness_summary | GET `/runs/{id}/harness-summary` |
| F-72 | DOC-12 | 手动触发熵检测 | Admin 手动运行 Entropy Detection 查看当前 8 个信号指标 | `/admin/observability` Entropy Alerts Tab → 触发检测按钮 | POST `/harness/entropy-check` |
| F-73 | DOC-12, DOC-11 | 查看熵告警列表 | Admin 查看检测到的熵漂移告警(护栏率/工具错误率等异常) | `/admin/observability` Entropy Alerts Tab 告警列表 | GET `/admin/audit-logs?action=harness.entropy_alert` |
| F-74 | DOC-12, DOC-11 | 确认/消除告警 | Admin 对已处理的熵告警点击确认标记为已知 | `/admin/observability` Entropy Alerts → 确认按钮 | POST `/admin/entropy/alerts/{id}/acknowledge` [推测] |
| F-75 | DOC-11 | 跳转 Grafana 仪表盘 | Admin 通过外链直达 4 个预设 Grafana Dashboard | `/admin/observability` External Dashboards Tab | 外链(不经后端) |
| F-76 | DOC-09 | 查看全局用量统计(Admin) | Admin 查看所有用户的汇总 Token 消耗和成本 | `/admin` 首页 或 `/usage` Admin 模式 | GET `/admin/usage` |
| F-77 | DOC-09 | 查看用户列表(Admin) | Admin 查看所有注册用户及其角色 | `/admin/users` UserTable | GET `/admin/users` |
| F-78 | DOC-09 | 修改用户角色(Admin) | Admin 将用户升级为 Admin 或降级为普通用户 | `/admin/users` UserTable → 角色下拉 | PATCH `/admin/users/{id}` |
| F-79 | DOC-09 | 生成邀请码(Admin) | Admin 创建新的邀请码用于邀请新用户 | `/admin/invites` InviteCodeTable → 生成按钮 | POST `/admin/invite-codes` |
| F-80 | DOC-09 | 查看邀请码列表(Admin) | Admin 查看所有邀请码及使用情况 | `/admin/invites` InviteCodeTable | GET `/admin/invite-codes` |
| F-81 | DOC-09 | 撤销邀请码(Admin) | Admin 使某个邀请码立即失效 | `/admin/invites` InviteCodeTable → 撤销按钮 | DELETE `/admin/invite-codes/{id}` |
| F-82 | DOC-09 | 查看审计日志(Admin) | Admin 查询所有用户操作和 Harness 事件日志 | `/admin/audit` AuditLogViewer | GET `/admin/audit-logs` |
| F-83 | DOC-09 | 按 Harness 事件类型筛选审计日志 | Admin 筛选 `harness.*` 前缀事件查看治理历史 | `/admin/audit` AuditLogViewer → action 前缀筛选下拉 | GET `/admin/audit-logs?action=harness.` |
| F-84 | DOC-09 | 导出审计日志(Admin) | Admin 将审计日志导出为 CSV 文件(≤10000 行) | `/admin/audit` AuditLogViewer → 导出 CSV 按钮 | GET `/admin/audit-logs/export?format=csv` |
| F-85 | DOC-09 | 查看系统统计 Dashboard(Admin) | Admin 看到 24h Runs、7d 成本、活跃用户、组件健康等汇总 | `/admin` 首页 Dashboard | GET `/admin/stats/dashboard` |
| F-86 | DOC-08 | 配置 IM 渠道(Admin) | Admin 配置飞书/企微/Telegram 的 App ID、Secret 等连接信息 | [推测] `/admin/settings` 或 `/settings/im`(Admin 专属) | PATCH `/im/channels/{channel}` |
| F-87 | DOC-08 | 查看 IM 渠道状态(Admin) | Admin 查看哪些 IM 渠道已启用 | [推测] 同上 | GET `/im/channels` |

---

## 按文档分布统计

| 文档 | 功能条数 |
|---|---|
| DOC-06 (Auth) | 6 (F-01~F-06) |
| DOC-07 (Session/Run/Task) | 14 (F-07~F-20 含 F-22~F-33 共 14) |
| DOC-11 (Frontend Features) | 与多个文档共享(约 12 条新增/扩充) |
| DOC-09 (MCP/Provider/Admin) | 17 (F-34~F-51, F-76~F-87) |
| DOC-08 (IM Gateway) | 6 (F-52~F-56, F-86~F-87) |
| DOC-05 (Plugin Ecosystem) | 8 (F-57~F-68 含 Plugin Builder) |
| DOC-12 (Observability) | 7 (F-69~F-75) |
| DOC-04 (Agent Orchestration) | 共享 F-65~F-67 |
| DOC-03 (Harness Runtime) | 共享 F-68 |
| DOC-00/01/02/10 | 基础架构,用户可见功能体现在上层文档 |

---

## 备注

- `[推测]` 标注的 API 路径:PRD 未明确给出,根据领域逻辑推断
- F-17/F-18/F-19/F-20 的 share/fork/archive/tag 功能在 DOC-11 v4 ADR-102 中明确要求实现,但对应后端 API 路径未在 DOC-01 API 路由总表中显式列出
- F-74 的 acknowledge 端点未在 DOC-01 总表中,但在 DOC-11 Task 11.6 中描述
- F-86/F-87 IM 渠道配置端点在 DOC-01 §6.8 中已列出:`GET /im/channels` 和 `PATCH /im/channels/{channel}`
