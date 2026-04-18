# 用户历史要求归档 — Prism v2 项目

> 通过 conversation_search 从历史对话中挖掘的用户文档要求、质量标准、风格偏好。
> 用途: Batch 1-5 review 的基准 + 最终 13 份 PRD 改写的 ground truth。

---

## 一、产品定位(已明确)

- **Prism v2 = 自托管 Agent Operating System**
- **参考竞品**: Manus (产品形态) + Claude Code (架构深度)
- **基于 CC 重新设计**,不是简单包装
- **定位**: 自己用,5-20 人团队,**不是 demo,是最终完整应用**
- **Prism v2 ≠ Prism v1 迁移**: 完全重写,从底层重新设计
- **参考价值的 v1 资产**: 金融 MCP / 合规 Hook / 认证流程可作参考,但必须按 v2 架构重新实现

## 二、核心技术决策(已锁定)

| 决策点 | 结论 |
|---|---|
| Agent Runtime | 自研 query() 主循环,**不用 claude_agent_sdk** |
| 模型协议 | 双协议 (Anthropic Mode + OpenAI Mode),用户配 base_url + api_key + 协议类型 |
| Executor | Backend 内部 CLI 子进程(不是独立容器) |
| 服务拓扑 | 4 个: backend / postgres / redis / nginx |
| 后端 | Python 3.12 + FastAPI + SQLAlchemy 2.0 **sync** + Alembic |
| 前端 | 从零搭建 Next.js,**Claude.ai 网页端视觉风格**: 衬线标题字体、深灰/暖白、大量留白、简洁对话区 |
| 前端组件 | shadcn/ui + Tailwind + TanStack React Query v5 + Zustand(少量) |
| 前端体积 | 源码 < 10MB,构建 standalone < 150MB(Poco 原版 5MB 源码,Prism v1 膨胀到 1.2GB 是不可接受的) |
| 数据库迁移 | 开发环境 `create_all()` / `alembic upgrade head`;生产环境**手写 Alembic**,**禁止 autogenerate** |
| 硬件预算 | 2C2G 可运行 → 用户后来明确 **4C8G 作为质量优先基线** |
| 主键 | UUIDv7 (时间有序、可排序、全局唯一) |
| API 响应 | 统一 `ApiResponse<T>` 封装: `{ data: T, error?: { code, message } }` |

## 三、开发五原则(硬标准,不可违反)

1. **单一职责原则** — 每个服务/方法只负责一个明确的职责域,避免职责混乱
2. **最简代码原则** — 不做向后兼容,宁愿破坏性更新也要保证代码最简化,删除所有冗余代码
3. **类型严格原则** — TypeScript 不用 `any`,Python 完整 type hints,编译/类型检查错误必须立即修复
4. **KISS 原则** — 保持简单直接,如果需要解释就是太复杂了
5. **文档置信度原则** — 绝不基于推测写代码,涉及关键功能文档置信度不高必须停止并要求准确资料
6. **(后加的第 6 条)禁止打补丁原则** — 所有修改必须深度融入代码逻辑,通过重构或调整现有逻辑实现。**严禁不从根源解决问题而用补丁绕过**。代码过程可以复杂,但最终结果必须是最简洁且完整实现需求的形态

## 四、Task 验收流程(9 步,硬标准)

```
1. 编译通过 — Python: mypy/pyright 零错误,TypeScript: npx tsc --noEmit 零错误
2. 后端非 AI 接口 — 常规场景 + 边界场景(权限不足/数据不存在/参数错误等)
3. 后端 AI 接口(涉及 Agent 工具时)— 模糊自然语言场景化测试,模拟不同用户身份,
   不用 ID、不用结构化参数
4. 前端(涉及前端时)— Playwright E2E 桌面端(1280x800)+ 移动端(375x812),
   **每个按钮每个流程走一遍**
5. 文档更新 — PROGRESS.md 状态 + DECISIONS.md 新 ADR(如有技术决策)
6. 代码规范 — 遵循现有风格、UUIDv7、ApiResponse<T>、丰富注释、不写魔法数字
7. 代码质量审查(Simplify skill 可用则用,否则手动等效操作)— 代码复用、质量、效率
8. lint/build/逻辑验证(PJR skill 可用则用,否则手动等效操作)
9. 合并 — git merge to dev 流程,合并回 dev 分支
```

**关键约束**:
- Worktree 中开发
- 涉及前端: 加载 frontend-design + uiuxpromax skill
- Skill 必须加载,找不到**立即停止任务上报**,不得盲目在没有 skill 的情况下执行
- Playwright E2E 不是写测试脚本,是直接用 Playwright 测试
- 每个按钮每个流程,**完全模拟人走一遍**,不是"页面效果没问题就没问题"

## 五、Task 文档结构(标准格式,所有 Task 统一)

每份文档内按 Task 拆分,**每个 Task 必须包含两部分**:

### Part A — 设计与解释
- 问题陈述(当前缺失什么 / CC 的对标方案是什么)
- 设计决策与理由(含 ADR 编号)
- 数据模型 / 接口定义 / 时序图(如适用)
- 与 CC 架构的映射关系(具体到 CC 的文件或函数名)
- Harness 层的交互说明(该 Task 涉及哪些 Harness 子系统)
- 验收标准(可验证的具体条件)

### Part B — Claude Code 执行 Prompt
- **上下文**(说明当前 Task 在整体中的位置、前置 Task 状态)
- **Skill 加载指令**(必须的 skill 列表,找不到停止任务)
- **前置条件检查指令**(验证上一 Task 产出正常)
- **要创建的文件**(精确到目录树)
- **实现规范**(精确到文件路径 / 类型定义 / 函数签名 / 代码骨架)
- **验证步骤**(编译检查、测试场景、E2E 指令,**含期望输出**)
- **完成后**(PROGRESS.md / DECISIONS.md 更新指令 + Simplify/PJR 审查 + git commit 指令)

## 六、质量标准(明确表达)

原话(多次强调):

> "每个文档,每个 task 的质量都要高质量,高准度,高精度的准则"
> "质量只准升,不准降,我会审核的"
> "我要求质量与结果,以及维护难度"
> "我还是只非常注重地看维护难度,结果,代码质量"
> "自己用的,没有 MVP 阶段"
> "以高质,品质这种为先"

**解读**:
- 不接受"Phase 1 最小可行交付"思维
- 每一层必须做到 Production-grade 才推进
- 质量维度涵盖: **产出物质量** + **系统质量** + **使用体验** + **可维护性**
- 文档密度要"4.6 能按此直接写代码零猜测"
- 宁可拖长时间,不可降低质量

## 七、命名规范

| 类别 | 规范 | 示例 |
|---|---|---|
| 数据库表名 | snake_case 复数 | `agent_sessions`, `agent_runs` |
| Python 类 | PascalCase | `SessionService`, `ToolExecutionPipeline` |
| Python 函数/变量 | snake_case | `enqueue_task()`, `run_id` |
| TypeScript 组件 | PascalCase | `ChatMessage`, `SessionList` |
| TypeScript 函数/变量 | camelCase | `fetchMessages()`, `sessionId` |
| API 路径 | kebab-case | `/api/v1/mcp-servers` |
| 主键 | UUIDv7 |  |
| API 响应 | `ApiResponse<T>` 统一封装 |  |

## 八、前端风格偏好

**Claude.ai 网页端视觉语言**:
- 衬线标题字体(类似 Tiempos / Freight Text / Claude 自己的字体)
- 无衬线正文(类似 Söhne / Inter)
- 深灰 / 暖白配色
- **大量留白**
- 对话区域**干净简洁**
- 工具卡片折叠式

**风格关键词**(用户原话):
> "低沉而准确,稳定这种感觉"

**Poco 功能完整移植**:
- Poco 前端全部交互功能保留(Session 列表、消息流、工具卡片、模型选择器、MCP 配置页、文件预览等)
- UI 风格换成 Claude 风格,但**接口和功能一个都不能少**

## 九、参考资料(已经内化,但要在改写时显式对照)

1. **Xiao Tan 的 CC 源码深度研究 PDF**(最新一轮用户已上传) — 26 页增强完整版,覆盖:
   - 源码结构全景 (src/entrypoints/ / constants/ / tools/ / services/ / utils/ / commands/ / coordinator/ / memdir/ / plugins/ / hooks/ / bootstrap/ / tasks/)
   - `src/constants/prompts.ts` 主系统提示词装配器(10+ section getter 函数)
   - SYSTEM_PROMPT_DYNAMIC_BOUNDARY 分界
   - `src/tools/AgentTool/prompt.ts` Agent 协议说明书
   - 6 种 built-in agents (General / Explore / Plan / Verification / Claude Code Guide / Statusline Setup)
   - AgentTool → runAgent → query 三层调度链
   - fork path 的 cache-identical prefix 优化
   - foreground / background / remote / teammate 四种 agent 生命周期
   - agent-specific MCP servers 支持
   - frontmatter hooks + frontmatter skills
   - toolExecution.ts 完整 pipeline (input check → PreToolUse hooks → permission → execute → analytics → PostToolUse hooks → structured output)
   - Hook 协议(exit code + JSON,permissionBehavior / updatedInput / preventContinuation / additionalContexts)
   - Explore Agent Bash 白名单: `ls, git status, git log, git diff, find, grep, cat, head, tail`
   - Verification Agent "try to break it" 反制逻辑 + VERDICT: PASS/FAIL/PARTIAL 强制格式
2. **Max For AI X 分析**: Prompt Cache 字节级精打细算、Coordinator-Workers、Fork 继承缓存、YOLO Classifier 动态权限、Dream 记忆架构、ToolSearch 按需加载
3. **huangserva X 分析**: 缓存黑科技 + 自我进化 + 多 Agent 协作 + 遥测监控
4. **Yuker X 分析**: Claude Code 为什么比别人好用
5. **billtheinvestor X 分析**: CC 架构解读

## 十、工作流强制约束(用户多次强调)

**Skill 加载严格性**:
- 所有 skill(using-superpowers、Simplify、PJR、frontend-design、uiuxpromax)**必须加载**
- 找不到立即停止任务上报,**不得盲目执行**
- 但后来用户放宽: "推荐加载,如果 Skill 不可用,执行等效的手动审查步骤" — 这是 v3.1 的修订

**禁止打补丁**(用户原话,极其强调):
> "绝对不可以为了解决某个需求,不从根源上解决问题,而是打补丁,这个是严格禁止的!"
> "必须要遵循最佳实践原则,深度的融合到代码逻辑内部,通过重构或调整或结合现有逻辑的方式来实现改变"

**端到端测试真实性**:
> "用 Playwright 直接测试...一定要桌面端和移动端都尽可能去测试,并且尽可能把每一个按钮、每一个流程,就完全模拟人的走一遍,而不只是看到页面效果没问题就没问题了"

## 十一、开发顺序偏好

用户版本(v3.1):
```
Phase 0 — 设计(不写代码): DOC-00 → DOC-01 → DOC-02 设计部分
Phase 1 — Agent 核心 + Harness: DOC-02(实现) → DOC-03 → DOC-04 → DOC-05
Phase 2 — 后端功能模块: DOC-06 → DOC-07 → DOC-08 → DOC-09
Phase 3 — 前端(无 Mock,基于真实 API): DOC-10 → DOC-11
Phase 4 — 可观测性 + 运维: DOC-12
```

## 十二、四条铁律(合规要求,Harness 多层强制)

1. **无投资建议** — 系统不得生成任何可被解释为投资建议的内容
2. **数据溯源** — 所有引用的数据必须标注来源
3. **AI 标识** — 所有 Agent 生成的内容必须标注 AI 生成标识
4. **数据隔离** — 不同用户的数据严格隔离,不得跨用户访问

## 十三、会话恢复协议(已确立)

新的 Claude Code 会话开始时,标准恢复序列:
```
1. 读取 docs/00-Vision-and-Principles.md        ← 全局纲领 + Harness 哲学
2. 读取 docs/0X-[当前工作文档].md                ← 当前任务详情
3. 读取 PROGRESS.md                             ← 最后进度状态
4. 读取 DECISIONS.md                            ← 架构决策记录
5. git log --oneline -10                        ← 最近提交
6. 执行对应验证命令                              ← 确认当前状态
7. 加载必需 Skill                               ← 按场景加载
8. 继续未完成的任务                              ← 断点恢复
```

## 十四、用户关于 review 和改写的最新立场(第 9 轮 / 第 10 轮)

- **Review 不是最终产物**,最终产物是重写后的 13 份 PRD
- **节奏**: 先全部 Batch 1-5 完成,**再统一改写**。不采用"Batch N 完就改 DOC-N"
- 理由: "你改前面的时候就不考虑后面了吧? 所以我的意思就是 batch 很重要,后面会根据这个改写"
- **补丁式修订允许**: "之前的要是不合格我不介意重新改一点(不是重写)"
- **先导文档**: Q4 选 c,DOC-00 保留愿景,新文件讲执行先导,**两份并存**
- Sonnet 4.6 看完先导再逐 Task 执行

## 十五、Anthropic 4.6 降智问题(用户担忧)

- **所有 AUDIT 都是 4.6 用 brainstorming 自审**
- 用户怀疑: "之前 opus4.6 降智很厉害,我怀疑有很多 bug"
- **改写任务的执行者**: Sonnet 4.6 "文档的第一版是由 sonnet4.6 进行 coding"
- 所以: **文档必须极其详细**,降低 4.6 需要自己推理的空间

---

## 附录: 我(Claude 4.7)的解读

基于以上归档,**改写阶段**的最高优先级:

1. **每个 Task 的 Part B Prompt 要像"手把手教学"**,文件路径、函数签名、类型定义、代码骨架、验证命令、期望输出,**全部显式写出**。不能有"按 CC 思路实现"这种模糊话
2. **Part A 必须解释"为什么这么设计"**,不是只写"做什么"。理由要引用 CC 源码的具体实现
3. **每个 Task 验收标准必须可执行**:具体命令 + 具体输出匹配。"AI 接口决策能力测试"要给可 assert 的样例
4. **一致性**: 跨 Task 引用时必须路径精确 (比如 Task 3.2 引用 Task 3.1 的 `QueryEngine.run()`,必须给出完整 import 路径)
5. **陷阱清单**: 每份 PRD 末尾列出"已知陷阱" + "4.6 容易犯的错",让 Sonnet 4.6 看完警惕
6. **断点恢复**: 每个 Task 都要有"如果执行到一半中断,如何从断点恢复"的明确指令

这些是质量的具体体现,不是装饰。
