# Skills 生态 + Plugin 编排层 — 设计文档

> **日期**: 2026-05-09
> **状态**: approved
> **范围**: Skills Market 生态接入 + Plugin 编排层重定义 + Plugin Builder v2

---

## 1. 问题

当前 Skills Market 是"盲搜盲装"体验：
- 搜索结果没有来源标识，用户不知道从哪来的
- 安装前看不到具体内容（README、示例、权限）
- 只能选"装/不装"，没有预览或试用
- 没有 CLI 命令支持（`/skill search` 等）
- Manus 生态未接入（仅调研文档，无代码）
- Plugin 定位仅是"manifest 容器"，不是编排层
- Plugin Builder 只做 manifest 生成，不做调研和决策

## 2. 目标

### Skills Market
- **发现**：Manus API + GitHub + 已注册 Marketplace，每条结果标明来源
- **预览**：卡片 → 详情页（README 渲染 + 使用示例 + 权限声明）→ Playground 试用
- **安装**：一键安装，CLI 和 GUI 等价
- **使用**：被动（Agent 自动匹配触发）+ 主动（`/skill-name` 或 `@skill-name`）

### Plugin 编排层
- Plugin = Skills + MCP servers + 脚本 + 子 Agent 的组合包
- 安装一个 Plugin = 一次性获得一整套能力

### Plugin Builder v2
- 深度需求对话 → 在线调研 → 决策（自建/复用/ROI）→ 构建
- 对话持久化，增量修改

## 3. 架构分层

```
Layer 3: Plugin Builder v2（智能构建流程）
    ↓ 构建
Layer 2: Plugin 编排层（Skills + MCP + Scripts + Agents 组合）
    ↓ 组合
Layer 1: Skills 生态（Manus + GitHub + Marketplace + Local）
    ↓ 提供能力
Layer 0: Prism Runtime（PromptAssembler + ToolRegistry + Executor）
```

## 4. Phase 1: Skills Market 体验重做（本期交付）

### 4.1 数据源重构

**现状**：`SkillsRegistry` 聚合 `LocalSource` + `MarketplaceCatalogSource`，搜索结果无来源标识。

**目标**：
- 每个搜索结果带 `source_type`（`manus` / `github` / `marketplace` / `local`）和 `source_url`
- GitHub 源：调用 GitHub API 搜索包含 `SKILL.md` 的仓库
- Manus 源：**文档置信度 BLOCKER** — 需要确认 Manus Skills API 端点和格式

### 4.2 前端 Skills Market 重做

**搜索结果卡片**：
- 来源标签（彩色 badge：Manus / GitHub / Marketplace / Local）
- 名称 + 一句话描述
- 版本 + 作者
- 安装数（如数据源提供）

**详情页**（点击卡片展开）：
- README 全文渲染（Markdown → HTML）
- 使用示例代码块
- 权限声明（读/写/网络/MCP）
- 依赖列表
- "安装"按钮 + "试用"按钮

**Playground 试用**：
- 临时加载 Skill 到当前 session（不持久化安装）
- 用户发一条测试消息，观察 Skill 效果
- 满意后再正式安装

### 4.3 CLI 命令

在 Prism 对话中支持：
- `/skill search <query>` — 搜索 Skills，显示结果列表
- `/skill install <name>` — 安装指定 Skill
- `/skill list` — 列出已安装 Skills
- `/skill remove <name>` — 卸载
- `/skill info <name>` — 查看详情（README + 权限）
- `/<skill-name>` — 主动触发已安装 Skill

### 4.4 Agent 集成（被动/主动双层）

**被动触发**：
- `PromptAssembler.skill_grammar_section()` 已注入已安装 Skills 的描述到 system prompt
- Agent 根据用户消息内容自动判断是否触发某个 Skill
- 触发时通过 `load_skill` 工具加载完整 Skill 上下文

**主动触发**：
- 用户输入 `/<skill-name>` 或 `@<skill-name>`
- 前端拦截，向后端发送带 skill 标记的消息
- Executor 直接加载该 Skill 上下文，跳过匹配逻辑

## 5. Phase 2: Plugin 编排层（下期）

### 5.1 Plugin Manifest v2

```yaml
name: financial-research
version: 1.0.0
type: orchestration  # 新类型，区别于 type: tool
description: 金融研究全套能力

components:
  skills:
    - name: data-cleaning
      source: marketplace
    - name: report-generator
      source: local
  mcp_servers:
    - name: bloomberg-api
      transport: http
      url: https://...
  agents:
    - name: verifier
      type: verifier
      model: haiku
  scripts:
    - name: env-check
      run: "python check_env.py"
      when: install

permissions:
  network: [bloomberg.com]
  tools: [web_search, read_file]
  models: [sonnet, haiku]
```

### 5.2 Plugin 生命周期

安装 → 解析 manifest → 按顺序执行 scripts.when=install → 注册 Skills + MCP + Agents → 可用

## 6. Phase 3: Plugin Builder v2（后期）

### 6.1 构建流程

1. **需求剖析**（多轮深度对话，7+ 维度评分升级）
2. **在线调研**（web_search GitHub / 竞品 / 开源方案）
3. **方案决策**（自建 vs 复用 vs 组合，领域 ROI 评估）
4. **构建执行**（基于决策组装 Plugin manifest + 代码）
5. **验证测试**（加载 + 功能验证）

### 6.2 对话持久化

- Plugin Builder 对话绑定到 `plugins_library` 记录
- 重新打开已有 Plugin → 恢复对话历史 → 增量修改
- 对话上下文包含上次的调研结果和决策记录

## 7. 文档置信度 BLOCKER

### Manus Skills API
- **状态**：未确认
- **需要**：Manus Skills marketplace 的 API 端点、认证方式、Skills 包格式
- **影响**：Phase 1 的 Manus 数据源适配器
- **处理**：先实现 GitHub + Marketplace + Local 三源，Manus 适配器预留接口，等用户提供 API 文档后接入

## 8. 交付计划

| Phase | 范围 | 预计 |
|---|---|---|
| **Phase 1a** | Skills Market GUI 重做（详情页 + 来源标签 + README 预览） | 2-3 sessions |
| **Phase 1b** | CLI 命令 + GitHub 数据源 + Playground 试用 | 2-3 sessions |
| **Phase 1c** | Agent 被动/主动双层调用 | 1-2 sessions |
| **Phase 2** | Plugin 编排层 manifest v2 + 生命周期 | 2-3 sessions |
| **Phase 3** | Plugin Builder v2 深度对话 + 调研 + 持久化 | 3-4 sessions |
| **Manus** | API 适配器（等文档） | 1-2 sessions |

**本 session 开始 Phase 1a**：Skills Market GUI 重做。
