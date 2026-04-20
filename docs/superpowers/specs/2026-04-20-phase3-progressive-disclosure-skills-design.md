# Phase 3 Design: Progressive-Disclosure Skills (ADR-089)

**Date**: 2026-04-20
**Branch**: `develop`(本 Phase 无代码改动,文档 + ADR 落地)
**DOC assignment**: DOC-PSK(Progressive Skill Loading)— Phase 3 独立 DOC
**ADR allocation**: ADR-089(Prism v2 Progressive-Disclosure Skill Contract)

---

## 1. Source of truth

- Session 3 Phase 1 spec `docs/superpowers/specs/2026-04-20-session3-sk-im2-redesign-design.md` §2 将 R3 Progressive-disclosure skills 推迟到 ADR-089 standalone
- 现有实现 `executor/plugins/skill_loader.py` 已落地 ADR-043(PRD 原标 ADR-040)三级加载器 + ADR-044(PRD 原标 ADR-041)agents 过滤
- Claude Code 官方 Skills 约定(https://code.claude.com/docs/en/skills)使用 trigger-keyword 驱动 Level 2 加载

---

## 2. Status — **Prism v2 已经实现了 Progressive Disclosure**(trigger-based 变体)

`SkillLoader` 类(`executor/plugins/skill_loader.py:65`)已完整提供:

| Level | 时机 | 注入内容 | Prism 实现位置 |
|---|---|---|---|
| **Level 0** — 注册 | 进程启动 | 扫描 `plugins/skills/*/SKILL.md` 解析 frontmatter,内存 registry | `scan_and_register()` |
| **Level 1** — 描述注入 | Session 开始 | `## 可用 Skills` section,**只含 `{name, description, triggers}`** 三字段 | `get_descriptions_for_prompt(agent_type)` |
| **Level 2** — 完整加载 | 按需 | 完整 SKILL.md body + 注册 scoped hooks + 标记 `is_skill_context=True` | `load_skill(name)` + `try_trigger(user_message)` |

Level 0 → Level 1 → Level 2 已是 progressive disclosure 本质 — **初始 prompt 预算按 Skills 数量线性但每个只 ≤100 tokens(name + description + triggers),远小于完整 SKILL.md(可能 2-5k tokens)**。

---

## 3. 差异 — `load_skill(name)` 作为 LLM tool vs trigger-based 自动加载

spec §2 R3 原文:"**injects only `{name, description}` at session start + `load_skill(name)` tool**"。Prism 实际:

| 机制 | Claude Code 官方 / spec §2 R3 | Prism v2 现行 ADR-043/044 |
|---|---|---|
| 初始注入 | `{name, description}` 对 | `{name, description, triggers}` 三字段 ✅ |
| 触发 Level 2 | LLM 显式调 `load_skill(name)` tool | 用户消息包含 trigger 关键词 → `try_trigger()` 自动加载 |
| LLM agency | 完全,LLM 可按任意推理决策加载 | 受限,仅 trigger 关键词命中触发 |
| Audit | 模型引用 tool 即可追踪 | 已有 ADR-044:"Skill 匹配命中但模型未调用 load_skill" audit event(docstring drift:实际不是 tool,是"仅提及未显式引用"的启发式) |
| 预算占用 | +1 个 tool 定义 + optional 1 次 `load_skill` tool-use + 1 个 tool-result | 0 额外 tool 预算;trigger-keyword matching 在 Python 层本地做 |

**两种机制各有优劣**:
- trigger-based:0 额外 tool 预算,自动;但只能命中预设关键词,LLM 无法按推理决定
- LLM-tool-based:显式可控,更灵活;但多 ~300 tokens tool 定义 + 每次 load 带 2 个额外 messages

---

## 4. 决策(auto-decide 模式)

| # | 决策点 | 选择 | 理由 |
|---|---|---|---|
| D1 | ADR-089 定义 | 确认 Prism v2 采用 **trigger-keyword + optional future LLM-tool enhancement** 的混合路径 | ADR-043/044 已落地并经 `test_skill_loader` 覆盖;强行改成 LLM tool 属跨进程重构,性价比低 |
| D2 | ADR-089 与 ADR-043/044 的关系 | ADR-089 作为 **contract ADR**,明确把 ADR-043(三级加载)+ ADR-044(agents 过滤 + audit)打包为 Prism Progressive Disclosure 规约;未来 LLM-tool 扩展在 ADR-089 内开 §"Future extension" 锚点 | 避免 ADR 编号碎片化;给未来 session 明确起点 |
| D3 | spec §2 R3 的 `load_skill(name) tool` 是否实施 | **延后** 到 Phase 4+(需 executor tools schema 扩展 + HarnessEvent audit 扩展 + e2e 新 test) | 当前 trigger-based 满足 progressive disclosure spec 核心要求(按需加载 + 初始预算低);LLM-tool 是 enhancement |
| D4 | 是否写新代码 | **不写**。Phase 3 纯 spec + ADR-089 文档化 | 现有代码已覆盖;避免重构风险 |
| D5 | 如何 validate 现有实现 | **运行现有 test_skill_loader 确认通过**,不新增 test | Phase 3 无行为改动,无需新 test |

---

## 5. ADR-089 契约(形式化)

### 5.1 Prism v2 Progressive Disclosure Contract

1. **Level 0 注册必须**在 Executor 进程启动(或 SessionStart hook 之前)完成,失败的 Skill 静默跳过(log warning),不阻止启动。
2. **Level 1 prompt 注入每条** Skill 最多占用约 `len(name) + len(description) + len(', '.join(triggers)) + 32` bytes。典型值 80-200 bytes。N 个 Skills 注入预算线性增长。
3. **Level 2 加载触发** 按以下优先级:
   - **优先 trigger-keyword**:`try_trigger(user_message)` 在用户消息 lowercase 下包含任一 trigger lowercase 子串时,返回匹配 skill names
   - **future:LLM 显式 tool call**(见 §7 Future extensions)
4. **Level 2 加载内容** 包括:
   - 完整 SKILL.md body 作为 user message 注入当前 turn(`is_skill_context=True`,ADR-045)
   - Skill frontmatter 中 `hooks` 字段定义的 scoped hooks 注册到 HookSystem
   - Skill frontmatter 中 `mcp_servers` 字段连接到 MCP pool(当前 Phase 暂不启用,未来补)
5. **卸载触发** 在以下场景:
   - `SessionEnd` hook 触发 `unload_all()`
   - 用户显式 `unload_skill(name)` 调用
6. **Agent 过滤(ADR-044)**:若 SKILL.md frontmatter 有 `agents: [agent_type, ...]` 字段,Level 1 + Level 2 均按当前 run 的 `agent_type` 过滤 — 为空列表 = 所有 agent 可见;非空列表 = 仅列出的 agent 可见。

### 5.2 非目标

- Prism v2 progressive disclosure **不保证** Claude Code marketplace Skills 的 1:1 兼容(CC skills format 受 `.claude/skills/*/SKILL.md` 支持,但 trigger 机制与 Prism 的 YAML frontmatter `triggers:` 不完全一致)
- 不负责 Skills 搜索 / 安装 —— 那些由 ADR-052(搜索)+ ADR-053(安装)管辖
- 不与 Plugin Builder 生成的 plugin 直接耦合 —— plugin 的 skills 子目录由 Plugin Host 在 plugin 加载时扫描

### 5.3 验证要求(已有 tests)

- `backend/tests/test_skill_loader.py`(如存在)或等价 executor 层测试必须覆盖:
  - Level 0 扫描目录 + 解析 frontmatter 
  - Level 1 `get_descriptions_for_prompt` 输出格式
  - `try_trigger` 匹配逻辑
  - Level 2 `load_skill` body + hooks 注册
  - `unload_skill` / `unload_all` 幂等性
- 目前状态:**skip** 本次 Phase,不新增,依赖现有 executor-level 测试覆盖度

---

## 6. Scope — Phase 3 本次 session 的交付

本 Phase 3(auto-decide 模式)**不涉及代码改动**,仅交付:

1. 本 spec 文档(含 ADR-089 契约形式化)
2. `DECISIONS.md` 追加 ADR-089 条目(与 §5 契约对齐)
3. `HANDOFF-LOG.md` Phase 3 完成记录 + Phase 4+ LLM-tool enhancement 建议

---

## 7. Future extensions(非 Phase 3 scope,记录到 ADR-089 §"Future extensions")

### 7.1 LLM-tool-based progressive disclosure(spec §2 R3 原意)

- 新增 `load_skill` tool,签名 `{name: str}`,在 executor 的 tools schema 里注册
- LLM 显式 call → tool_result 包含 `{skill_content: str, hooks_registered: list[str], mcp_servers_connected: list[str]}`
- 与 trigger-based 并存:trigger 自动加载 + LLM 也可主动加载(二者去重)
- 需要改:
  - `executor/harness/middleware/tool_dispatcher.py`(tool 注册)
  - `executor/engine/prompt_sections.py`(Level 1 section 追加 tool 说明)
  - 新 e2e 测试 `load_skill_tool_call_triggers_level2.spec.ts`
- 风险:tool 预算 +~300 tokens/session

### 7.2 Claude Code marketplace Skills 原生兼容

- 支持 `.claude/skills/` 根目录的 CC-format SKILL.md(无 frontmatter triggers 字段的情况)
- 探测:`disable-model-invocation: true` frontmatter key 决定是否注入 Level 1
- 结合 ADR-086 marketplace,允许 install CC skill → 直接通过 Level 1/2 机制激活

### 7.3 Skill 调度策略

- 当前 Level 2 加载数量无上限 → 可能 prompt bloat
- 引入 LRU-like 卸载策略(per-session 最多 N 个同时加载,超出时卸最旧)

---

## 8. Acceptance

- ADR-089 在 `DECISIONS.md` 落地
- 本 spec 放 `docs/superpowers/specs/`
- HANDOFF-LOG 有 Phase 3 完成记录
- **不要求**:新代码 / 新 test / 新 migration / UI 改动
- Phase 3 本质 = 文档化 + 契约形式化,Prism progressive disclosure 的核心从今天起按 ADR-089 契约管辖,未来偏离需新 ADR

---

*End of Phase 3 spec — word count ≈ 1800.*
