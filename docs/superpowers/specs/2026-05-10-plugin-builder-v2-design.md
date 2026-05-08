# Plugin Builder v2 — 对标 Claude Code Agent 创建流程

> 日期: 2026-05-10
> 优先级: P3（用户反馈）

---

## 业务需求

用户输入自然语言需求（如"做一个读金融 KYC 的 agent"），系统先搜现有方案，有则推荐安装，无则自动构建。全程零技术参数，AI 处理一切。

### 完整链路

```
用户输入需求描述
  → AI 理解意图，提炼 plugin 需求
  → 搜索 marketplace + GitHub 现有方案
  → 找到匹配：展示方案卡片 + "安装" 按钮
  → 未找到：AI 自动推断 type / tools / permissions，生成 plugin
  → 结构化卡片展示结果（名称、类型、工具列表、权限）
  → 用户确认 → 保存到插件库
```

### 用户不需要做的事

- 选 plugin 类型（AI 推断）
- 填端口、API key 格式等技术参数（AI 推断）
- 编辑 YAML（系统内部处理）
- 回答 7 个维度的追问（AI 一轮理解）

---

## 改动范围

### 1. 前端：PluginsPage builder 流程简化

**文件:** `frontend/Prism.html` (PluginsPage 组件，行 2187+)

**删除：**
- 4 型选择器（`typepick` 阶段）
- YAML 手动编辑 textarea（saveModal）
- 多阶段状态机（start → typepick → chat → consent → save）

**替换为：**
- 单输入框 + 发送按钮（类似聊天 composer）
- 用户输入需求 → 发送 → 等待 AI 响应
- AI 响应分两种：
  - **推荐现有方案**：展示搜索结果卡片 + "安装" 按钮
  - **生成新 plugin**：展示结构化 plugin 卡片（名称、类型 badge、描述、工具列表、权限摘要）+ "保存" 按钮
- 错误用 `addToast("danger", ...)` 弹窗，不在对话中显示

**对话流保留：**
- builder 仍然是对话式的（SSE 流式）
- 但对话更短——AI 一轮理解需求 + 搜索 + 生成，而非多轮追问
- 用户可以追加修改（"把名字改成 xxx"、"加上 xxx 工具"）

### 2. 后端 Agent：system prompt 重写 + 搜索集成

**文件:** `executor/agents/plugin_builder.py`

**重写 system prompt：**
```
你是 Prism Plugin Builder。用户描述需求，你负责：

1. 理解需求：从用户描述中提炼 plugin 的目标、需要的工具/API、数据源
2. 搜索现有方案：调用 skills_search 工具搜索 marketplace 和 GitHub
3. 决策：
   - 如果找到高度匹配的现有 plugin → 推荐安装（输出推荐卡片）
   - 如果没有或不够好 → 自动构建
4. 构建：自动推断 type / tools / permissions，生成 plugin manifest
5. 输出：结构化 JSON（不是 YAML），包含 name / type / description / tools / permissions

你不追问技术细节。用户说"做一个天气查询工具"，你就做，不问端口、API key 格式。
你主动推断合理默认值。
```

**删除：**
- `plugin_builder_scoring.py` 的 7 维打分循环
- 硬编码的 `max_turns=40`
- `structured_dialogue` output format

**新增工具：**
- 给 plugin_builder agent 添加 `skills_search` 工具（已存在于 executor/tools/），用于搜索 marketplace + GitHub

### 3. 后端 Agent：输出格式

builder agent 生成后，通过 SSE 事件 `plugin_manifest_ready` 发送结构化数据：

```json
{
  "action": "recommend" | "create",
  "plugin": {
    "name": "kyc-reader",
    "type": "tool",
    "description": "读取并分析金融 KYC 报告",
    "tools": ["read_file", "web_search"],
    "permissions": {
      "network_access": true,
      "storage_scope": "session"
    }
  },
  "search_results": [...],
  "manifest_yaml": "..."
}
```

前端根据 `action` 展示不同 UI：
- `recommend`：搜索结果卡片 + 安装按钮
- `create`：plugin 配置卡片 + 保存按钮

### 4. 前端：结果卡片 UI

**推荐卡片：**
- 插件名 + 来源 badge (Marketplace/GitHub)
- 描述
- "安装" 按钮（复用现有 installPlugin 流程）

**构建卡片：**
- 插件名 + 类型 badge (tool/agent/extension/trigger)
- 描述
- 工具列表（chip 标签）
- 权限摘要（网络访问、存储范围）
- "保存到插件库" 按钮

---

## 不涉及

- 持久化对话 / 增量编辑（未来 v3）
- 模板库（未来）
- ROI 分析面板（未来）
- Plugin 运行时执行改动（保持现有 PluginHost 逻辑不变）
