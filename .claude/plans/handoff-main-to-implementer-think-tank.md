# Handoff: Main → Implementer (Think Tank Mode)

## 状态: READY_FOR_REVIEW
## 任务: 实现智囊团模式 — 多 persona 讨论/辩论
## 工作目录: E:\Agent program\PrismV3\.worktrees\think-tank

## 输入文件:
- docs/superpowers/specs/2026-05-20-think-tank-thinking-mode-design.md (§3 Think Tank Mode)
- tempp/persona-skills/*/SKILL.md (42 个 persona skill 文件)
- backend/app/api/v1/tasks.py (任务创建)
- backend/app/api/v1/skills.py (技能API)
- backend/app/services/skill_install_service.py (技能安装)
- frontend-react/src/pages/Chat/ChatPage.tsx (聊天页)
- frontend-react/src/pages/Chat/Composer.tsx (消息发送)

## 禁止触碰:
- executor/ 目录的核心 TAOR 循环
- backend/app/models/ 的表结构 (不加新表)
- 任何测试文件

## 执行计划 (step→verify):

1. 后端: 新增 GET /api/v1/personas/available 端点
   → verify: PASS — 端点在 skills.py 末尾添加，_persona_router 注册在 __init__.py

2. 后端: SKILL.md 解析逻辑读取 tempp/persona-skills/*/SKILL.md
   → verify: PASS — _parse_persona_skill_md() 解析 YAML front matter 提取 name+description+slug

3. 前端: API types + client
   → verify: PASS — PersonaInfo/ThinkTankConfig/ThinkTankDiscussionMode 加入 types.ts；personas.listAvailable() 加入 client.ts

4. 前端: ThinkTankPanel 配置面板
   → verify: PASS — ThinkTankPanel.tsx 展示 persona 列表，支持 2-5 个选择，辩论/德尔菲模式切换

5. 前端: Composer 增加智囊团按钮
   → verify: PASS — Composer.tsx 加 thinkTankConfig/onOpenThinkTank props，显示小按钮；active 时显示 persona 数量

6. 前端: ChatPage 集成
   → verify: PASS — ChatPage.tsx 持有 thinkTankConfig 状态，submit 时调用 buildThinkTankPrompt() 包裹 prompt

7. 前端: ThinkTankMessage 渲染
   → verify: PASS — ThinkTankMessage.tsx 解析 "### 🧠 {name}" 和 "### 📋 综合分析" headings，渲染为独立卡片；MessageBubble.tsx 集成

8. Build 验证
   → verify: PASS — `node_modules/.bin/tsc --noEmit` 零错误；`node_modules/.bin/vite build` 成功

## 已完成:
- 后端 GET /api/v1/personas/available 端点（skills.py + __init__.py）
- 前端 types.ts 新增 PersonaInfo/ThinkTankConfig/ThinkTankDiscussionMode
- 前端 client.ts 新增 personas.listAvailable()
- 新建 ThinkTankPanel.tsx + ThinkTankPanel.module.css（配置面板）
- 新建 ThinkTankMessage.tsx + ThinkTankMessage.module.css（persona 卡片渲染）
- Composer.tsx 增加 thinkTankConfig/onOpenThinkTank props + 智囊团按钮
- Composer.module.css 增加智囊团按钮样式
- ChatPage.tsx 集成智囊团状态 + buildThinkTankPrompt() 函数
- MessageBubble.tsx 集成 ThinkTankMessage 检测和渲染
- frontend build PASS（tsc 零错误，vite build 成功）

## 产出物:
- backend/app/api/v1/skills.py: 末尾新增 PersonaInfo schema + _persona_router + _parse_persona_skill_md() + _find_persona_skills_dir() + GET /personas/available 端点
- backend/app/api/v1/__init__.py: 注册 personas_router
- frontend-react/src/api/types.ts: PersonaInfo / ThinkTankConfig / ThinkTankDiscussionMode 类型
- frontend-react/src/api/client.ts: personas.listAvailable() + PersonaInfo import
- frontend-react/src/pages/Chat/ThinkTankPanel.tsx: 配置面板组件（新建）
- frontend-react/src/pages/Chat/ThinkTankPanel.module.css: 面板样式（新建）
- frontend-react/src/pages/Chat/ThinkTankMessage.tsx: persona 卡片渲染组件（新建）
- frontend-react/src/pages/Chat/ThinkTankMessage.module.css: 卡片样式（新建）
- frontend-react/src/pages/Chat/Composer.tsx: 增加 thinkTankConfig/onOpenThinkTank props + 智囊团按钮
- frontend-react/src/pages/Chat/Composer.module.css: 增加智囊团按钮样式
- frontend-react/src/pages/Chat/ChatPage.tsx: 集成智囊团状态 + buildThinkTankPrompt()
- frontend-react/src/pages/Chat/MessageBubble.tsx: 集成 isThinkTankResponse + ThinkTankMessage

## 验证结果:
- TypeScript 类型检查: PASS (0 errors)
- Vite build: PASS (156 modules, 2.33s, 0 errors)
- Python syntax check (skills.py + __init__.py): PASS

## 遗留问题:
- 后端端点未经真实 HTTP 请求验证（需要运行中的服务器）。路径解析逻辑已覆盖 worktree + 主仓库布局，但如果 PRISM_WORKSPACE 未设置且 cwd 偏移，可能找不到 tempp 目录。
- Think Tank 模式在 session 间不持久（刷新页面后配置丢失）。如需持久化，需要存入 session.config_snapshot，属于超出当前任务范围的改动。
- 辩论式 prompt 中的"互相引用"指令依赖 LLM 的理解能力，实际输出质量未经端到端测试验证。

## 决策上下文:
- 已选方案: 通过 prompt prefix 注入 think_tank 指令（不改 executor TAOR 循环，不加新 DB 表），前端持有配置状态
- 已排除方案: session.config_snapshot 存 think_tank 配置 + executor 侧读取（需改 DB 查询逻辑，超出范围）
