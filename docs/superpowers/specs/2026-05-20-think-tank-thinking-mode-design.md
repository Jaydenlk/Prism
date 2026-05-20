# Think Tank Mode + Thinking Mode Design Spec

> Date: 2026-05-20
> Status: Draft (调研完成，待用户 review)

## 调研结论（群体决策理论）

基于 Delphi Method、Adversarial Collaboration、Six Thinking Hats、认知多样性等研究：

- **最优人数 3-5 人**：多样性比数量重要，5 人讨论优于聚合数千独立意见（Sigman 2018）
- **"固执"agent 优于"随和"agent**：结构化辩论比共识导向准确率高 10%（Du et al. 2023）
- **2-3 轮迭代最优**：Delphi 法 3 轮后收益递减，85% 一致度为收敛阈值
- **至少 1 个对立面**：显性对立角色比全员友好讨论产出更好结论
- **终止条件**：无 persona 改变立场 → 停；无新论点 → 停；硬上限 3 轮
- **简单问题不用智囊团**：事实类问题单 agent 胜率 82.5% > 多 agent 讨论 13.8%（DeliberationBench 2025）
- **输出格式**：对话线程 + 综合卡片（共识/分歧/建议），含少数派报告

---

## 1. 概述

为 Prism V3 新增两种会话模式，扩展现有的普通对话：

| 模式 | 定位 | 核心机制 |
|---|---|---|
| **Normal** | 普通对话（现有） | 单 Agent TAOR 循环 |
| **Thinking Mode** | 长链路深度思考 | 深度推理链 + 自我追问挑战结论 |
| **Think Tank Mode** | 多视角讨论问题 | 多 persona 轮流发言（辩论式/德尔菲式） |

---

## 2. Thinking Mode

### 2.1 用户体验

用户在会话中选择 Thinking Mode 后，发送问题。AI 的回复分两段展示：

1. **推理链**（可折叠）：逐步展示完整思考过程，每步都有明确的推理逻辑
2. **自我追问**（可折叠）：AI 对自己的结论提出 3-5 个挑战性追问（"真的吗？""还有其他可能吗？""如果反过来呢？"），逐一回答
3. **最终结论**：综合推理链和自我追问后的最终答案

### 2.2 技术实现

**方案：Prompt Engineering + 前端渲染**

不改 executor TAOR 循环，通过 system prompt 指令让 LLM 输出结构化内容：

```
你现在进入深度思考模式。请按以下结构回答：

## 🔍 推理链
[逐步展开你的思考过程，每步标注推理依据]

## ❓ 自我追问
[对上述结论提出 3-5 个挑战性追问，并逐一回答]

## 💡 最终结论
[综合以上分析给出最终答案]
```

前端通过 Markdown heading 解析，渲染为可折叠的三段式卡片。

### 2.3 数据模型

Session `config_snapshot` 新增字段：

```json
{
  "mode": "thinking",
  "thinking_config": {
    "min_reasoning_steps": 5,
    "min_self_challenges": 3
  }
}
```

---

## 3. Think Tank Mode

### 3.1 用户体验

用户选择 Think Tank Mode，选择参与的 persona（或使用 Auto 推荐），选择讨论模式（辩论式/德尔菲式），发送问题。

**辩论式流程：**
1. 用户提问
2. Persona A 发表观点
3. Persona B 引用 A 的观点并提出反驳/补充
4. Persona C 从新角度切入，引用 A 和 B
5. ...（所有 persona 轮流发言）
6. 综合者汇总所有观点，给出结构化结论

**德尔菲式流程：**
1. 用户提问
2. 所有 persona 独立回答（不看别人的）
3. 综合者汇总所有观点
4. （可选）第二轮：每个 persona 看到汇总后修正自己的观点
5. 最终综合结论

### 3.2 输出格式

每个 persona 发言以独立消息气泡展示，包含：
- Persona 头像 + 名字（如 "🧠 查理·芒格"）
- 发言内容（带该 persona 的表达 DNA 风格）
- 如果是辩论式，引用前人观点的部分用引用块标记

最终汇总为结构化报告：
- 各方核心观点摘要
- 共识点
- 分歧点 + 各方理由
- 综合结论 + 行动建议

### 3.3 Auto Mode 选人逻辑

根据问题类型自动选择 3-5 个最合适的 persona：

| 问题类型 | 推荐 persona 组合 | 理由 |
|---|---|---|
| 投资决策 | 巴菲特+芒格+塔勒布+纳瓦尔 | 价值投资+逆向思维+风险管理+杠杆思维 |
| 产品设计 | 乔布斯+马斯克+张一鸣 | 极致产品+第一性原理+数据驱动 |
| 创业战略 | 马斯克+乔布斯+纳瓦尔+段永平 | 颠覆式创新+产品力+财富杠杆+长期主义 |
| 学习方法 | 费曼+芒格+张雪峰 | 第一原理教学+多元思维模型+实用主义 |
| 风险评估 | 塔勒布+芒格+巴菲特 | 反脆弱+认知偏误+安全边际 |
| 人生规划 | 纳瓦尔+费曼+张雪峰+段永平 | 财富哲学+好奇心+职业规划+本分 |
| 通用/不确定 | 芒格+费曼+纳瓦尔 | 多元思维+清晰表达+第一性原理 |

Auto 选人基于关键词匹配 + persona SKILL.md 的 description 触发词：
1. 提取用户问题的关键词
2. 匹配每个 persona 的 triggers 列表
3. 按匹配度排序，取 top 3-5
4. 确保认知多样性（不全选同领域的）

### 3.4 技术实现

**方案：多轮 Prompt 编排**

Think Tank 不改 executor 引擎，通过**单次 LLM 调用 + 结构化 prompt**实现：

```
你现在进入智囊团讨论模式。以下是参与讨论的智囊团成员：

{persona_1_skill_content}
{persona_2_skill_content}
{persona_3_skill_content}

用户的问题是：{user_question}

请模式：{debate|delphi}

如果是辩论模式，请按以下格式输出：
### 🧠 {persona_1_name}
[以该 persona 的思维方式和表达风格回答]

### 🔥 {persona_2_name}
[引用 persona_1 的观点并反驳/补充]

### 💡 {persona_3_name}
[从新角度切入，引用前两位的观点]

### 📋 综合分析
- **共识**：...
- **分歧**：...
- **结论**：...
- **行动建议**：...
```

### 3.5 数据模型

Session `config_snapshot`：

```json
{
  "mode": "think_tank",
  "think_tank_config": {
    "sub_mode": "debate",
    "personas": ["elon-musk-perspective", "munger-perspective", "feynman-perspective"],
    "auto_select": true,
    "max_rounds": 1
  }
}
```

SkillInstall 表已有，persona skills 通过现有 skill 安装机制安装。

---

## 4. 前端改动

### 4.1 模式选择器

在聊天输入框上方添加模式切换：`Normal | Thinking | Think Tank`

点击 Think Tank 后弹出配置面板：
- 辩论式 / 德尔菲式 切换
- Auto（默认）/ 手动选择 persona
- 手动模式下显示已安装的 persona skills 列表，可勾选 3-5 个

### 4.2 Thinking Mode 渲染

检测 AI 回复中的 `## 🔍 推理链`、`## ❓ 自我追问`、`## 💡 最终结论` heading，渲染为三段可折叠卡片。

### 4.3 Think Tank 渲染

检测 AI 回复中的 `### 🧠 {name}` heading，每个 persona 发言渲染为带头像的独立消息气泡。`### 📋 综合分析` 渲染为高亮的结论卡片。

---

## 5. 后端改动

### 5.1 新增 API

- `GET /api/v1/personas/recommend` — 根据问题文本返回推荐 persona 列表
- `GET /api/v1/personas/installed` — 返回已安装的 persona skills

### 5.2 Session 创建扩展

`POST /api/v1/sessions` 的 config 参数支持 mode 字段。

### 5.3 Prompt 装配

executor 的 prompt 装配层根据 session mode 注入不同的 system prompt：
- `normal`：现有行为
- `thinking`：注入 thinking mode 指令
- `think_tank`：加载选定 persona 的 SKILL.md 内容 + 注入讨论格式指令

---

## 6. 女娲 Skill + 达芬奇 Skill

### 6.1 女娲（创造蒸馏）

功能：帮助用户蒸馏任何人/角色为 persona skill。

- 输入：目标人物的公开资料（文章、演讲、访谈、社交媒体）
- 输出：标准 SKILL.md 格式的 persona skill 文件
- 流程：收集资料 → 提取思维模型 → 编码表达 DNA → 生成 SKILL.md

### 6.2 达芬奇（自我进化）

功能：已安装的 persona skill 基于新信息自我更新。

- 输入：新的资料/事件（如"马斯克最新的 Twitter 发言"）
- 输出：更新后的 SKILL.md（新增心智模型/修正表达 DNA/更新时间线）
- 流程：加载现有 SKILL.md → 分析新资料 → diff 更新 → 用户确认

---

## 7. 实现顺序

1. **Phase 1**：Thinking Mode（最小改动，prompt + 前端渲染）
2. **Phase 2**：Think Tank Mode（persona 加载 + prompt 编排 + 前端多气泡）
3. **Phase 3**：Auto 选人（关键词匹配 + 认知多样性）
4. **Phase 4**：女娲 + 达芬奇 skill
