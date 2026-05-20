# Prism v2 — 全量项目审计报告

> **审计日期**: 2026-05-16
> **审计模型**: Opus 4.6 (1M context)
> **方法**: 12 个独立 subagent 并行审计（6 探索 + 6 深度审计）
> **覆盖范围**: 安全 / 架构合规 / 代码质量 / 前端质量 / DevOps / 功能完整性 / 竞品对标
> **前序报告**: `2026-05-14-prism-vs-poco-audit.md`（竞品）、`2026-05-15-product-audit-report.md`（产品验证）

---

## 一、总览评分

| 维度 | 评分 | 说明 |
|------|------|------|
| **安全性** | **D** | 4 CRITICAL + 6 HIGH；密钥泄露、auth 绕过、HTTPS 缺失 |
| **架构合规** | **A-** | 10 条 ADR 中 9 条 PASS，1 条 PARTIAL（进程边界） |
| **代码质量** | **C+** | 类型严格性不足、核心服务零测试、静默错误吞没 |
| **前端质量** | **C** | XSS 漏洞、React 开发模式上线、单文件 4800+ 行 |
| **DevOps** | **D+** | 无 TLS、无 CI/CD、Redis 无密码、镜像臃肿 |
| **功能完整性** | **A** | 后端 98% 真实完成，前端 0%（正确标注为待启） |
| **竞品对标** | **B+** | 架构 43/50 vs Poco 27/50；功能广度 Poco 领先 40% |

**综合**: 技术基座扎实（架构设计一流），但**安全和运维是上线前的硬伤**。

---

## 二、CRITICAL 问题清单（必须立即修复，共 13 项）

### 安全类（4 项）

| # | 问题 | 位置 | 影响 | 修复建议 |
|---|------|------|------|----------|
| S-C1 | .env 包含真实密钥（CloudDream/Feishu/EXA/admin 密码），`.claude/worktrees/` 未加入 .gitignore | `.env`, `.claude/worktrees/` | 全服务接管：JWT 伪造 + 第三方账户控制 | 立即轮换所有密钥；`git log --all --diff-filter=A -- '*.env'` 排查历史；`.claude/worktrees/` 加入 .gitignore |
| S-C2 | 非 production 模式公开 API 返回明文 admin 密码 | `backend/app/api/v1/auth.py:396-413` | docker-compose 默认 development，忘设 PRISM_ENV 即暴露 | 删除 `dev_default_admin` 功能，或限制 localhost |
| S-C3 | 禁用用户仍可无限续期 JWT | `backend/app/core/dependencies.py:86-118` | admin 禁用用户功能形同虚设 | `get_current_user()` 和 `refresh()` 中检查 `is_active` |
| S-C4 | `secure=True` cookie + HTTP-only nginx = refresh token 永不发送 | `auth.py:91` + `nginx.conf` | token 刷新完全失效，用户每 15 分钟被踢 | 配 HTTPS 或按环境条件设 secure |

### DevOps 类（6 项）

| # | 问题 | 位置 | 影响 | 修复建议 |
|---|------|------|------|----------|
| D-C1 | Dockerfile 无 multi-stage build，镜像含 git/npm/build 全套，预计 2-3GB+ | `backend/Dockerfile` | 攻击面大、拉取慢、存储浪费 | 分 builder + runtime 两阶段 |
| D-C2 | Nginx 无 TLS，全流量明文 | `nginx/nginx.conf` | 中间人攻击可截获所有凭证 | 加 Let's Encrypt 或前置 Caddy |
| D-C3 | Redis 无密码，任何同网络容器可读写 | `docker-compose.yml:59-64` | 横向移动：篡改 SSE ticket、权限应答、心跳 | 加 `requirepass` + 更新 REDIS_URL |
| D-C4 | `/metrics` 端点无鉴权，公开暴露 79 个 Prometheus 指标 | `backend/app/main.py:465-476` | 泄露 token 用量、用户数、错误率、熔断状态 | 加 admin auth 或 shared secret |
| D-C5 | 健康检查每次新建 SQLAlchemy engine，连接池泄漏 | `backend/app/api/v1/health.py:47-57` | 长期运行后 PG 连接耗尽 | 复用 `app.core.database.engine` |
| D-C6 | Alembic 以 root 运行，失败后无退避直接 crash loop | `backend/Dockerfile:50` | 迁移锁/网络抖动 → 容器无限重启 | entrypoint 加 retry + 用 gosu 降权 |

### 前端类（2 项）

| # | 问题 | 位置 | 影响 | 修复建议 |
|---|------|------|------|----------|
| F-C1 | `simpleMarkdown` 渲染未过 DOMPurify，存储型 XSS | `Prism.html:2375` | 恶意 Skill README 注入 JS 到管理员浏览器 | 输出过 `DOMPurify.sanitize()` |
| F-C2 | `postMessage` 监听无 origin 校验 | `Prism.html:4592-4594` | 任意页面可远程激活 Tweaks 面板 | 加 `e.origin` 白名单校验 |

### 代码质量类（1 项）

| # | 问题 | 位置 | 影响 | 修复建议 |
|---|------|------|------|----------|
| Q-C1 | sequence_service 用 f-string 拼 DDL，潜在 SQL 注入 | `backend/app/services/sequence_service.py:38` | 当前安全（UUID 服务端生成），但函数无输入校验 | 入口校验 UUID 格式 |

---

## 三、HIGH 问题清单（应尽快修复，共 21 项）

### 安全（6 项）
- **H-S1** `/metrics` 无鉴权（同 D-C4）
- **H-S2** 认证端点无速率限制（login/register/OTP 可暴力破解）
- **H-S3** `python-jose` 已停维，存在已知 CVE → 迁移到 PyJWT
- **H-S4** Executor import Backend ORM model（skills_registry → MarketplaceRegistry）
- **H-S5** Google OAuth 回调 URL fragment 携带 access_token（泄露风险）
- **H-S6** Dev compose 暴露 PG 5432 + Redis 6379 到宿主机且 Redis 无密码

### 架构（3 项）
- **H-A1** `mcp_service.py:68` Backend 实例化 Executor 的 MCPClient（进程边界违规）
- **H-A2** `plugins.py:140` Backend 实例化 CCPluginAdapter（文件系统扫描）
- **H-A3** `skills.py:1028` Backend 实例化 SkillsRegistry + GitHubSource + Context7Source

### 代码质量（5 项）
- **H-Q1** 6+ 个 service 文件中 `settings: Any` / `redis_client: Any` 系统性滥用
- **H-Q2** `MiddlewareContext` 的 `tool_use_block: Any` / `tool_result_block: Any`
- **H-Q3** 核心服务零测试：auth_service / session_service / run_lifecycle / task_service / process_manager / callback_service / sse_manager 等 12 个
- **H-Q4** `mcp_service.py` / `provider_service.py` 解密失败静默降级，无日志
- **H-Q5** `process_manager.py:315` `run` 参数无类型注解

### 前端（6 项）
- **H-F1** 消息列表用数组 index 作 React key → 状态错位
- **H-F2** React development.js + Babel standalone 上线（10x 慢、3x 大）
- **H-F3** 消息历史解析逻辑 copy-paste 3 次
- **H-F4** 移动端 sidebar 默认展开（`useState(true)`）
- **H-F5** `reportError` 无 auth 发送 user_id
- **H-F6** admin.html 未加载 DOMPurify

### DevOps（1 项）
- **H-D1** 中国镜像硬编码 Dockerfile，海外构建失败 → 用 `ARG USE_CHINA_MIRRORS`

---

## 四、架构 ADR 合规总表

| ADR | 条款 | 结果 | 证据 |
|-----|------|------|------|
| ADR-022 | 回调风暴 → Redis PUBLISH | **PASS** | `backend_callback.py:59-91` text_delta/tool_use_delta 走 Redis |
| ADR-029/031 | Compaction 原子裁剪 | **PASS** | `context_budget.py:123-158` 回合组识别 + `compaction.py:133-334` 4 tier 全整组 |
| ADR-021 | 工具并行 | **PASS** | `query_engine.py:435-477` asyncio.gather + return_exceptions=True |
| ADR-051 | SSE ticket | **PASS** | `sse_ticket_service.py` SETEX 60s + GETDEL 原子消费 |
| ADR-020 | 进程边界 | **PARTIAL** | 3 处 Backend 实例化 Executor 业务类（H-A1/A2/A3） |
| ADR-060 | sequence_no | **PASS** | `sequence_service.py` CREATE SEQUENCE + advisory_xact_lock |
| ADR-050 | 三密钥独立 | **PASS** | `security.py:27-75` ≥32 字符 + 两两不同 |
| ADR-028 | 权限 BLPOP | **PASS** | `ask_protocol.py:109` Redis BLPOP + 60s timeout deny |
| ADR-034 | Fork 硬约束 | **PASS** | `fork_briefing.py:39-45` 3 条约束注入 system prompt |
| ADR-038 | PluginBuilder 动态 | **PASS** | v2 删除硬编码 5 轮，改 AI 自主判断（max_turns=15） |

**9/10 完全合规，1/10 部分合规。**

---

## 五、功能完整性

| DOC | 范围 | 声称 | 验证 | 完成度 |
|-----|------|------|------|--------|
| DOC-02 | 骨架 + ORM + Driver + Prompt | 4/4 | 4/4 | **100%** |
| DOC-03 | TAOR + Middleware + Hook + Permission + Guardrails + Compaction + Memory | 6/6 | 6/6 | **100%** |
| DOC-04 | 6 Agent + Fork + Coordinator + PluginBuilder | 5/5 | 4/5 | **85%** ¹ |
| DOC-05 | Skill + MCP + Hook governance + PluginHost + CC compat | 7/7 | 7/7 | **100%** |
| DOC-06 | 三密钥 + SSE ticket + 邀请码 | 2/2 | 2/2 | **100%** |
| DOC-07 | Session + Run + Cancel + Callback + SSE + Heartbeat | 4/4 | 4/4 | **100%** |
| DOC-08 | IM Gateway + 3 adapter | 3/3 | 3/3 | **100%** |
| DOC-09 | MCP + Provider + Admin | 3/3 | 3/3 | **100%** |
| DOC-10/11 | Next.js 前端 | 0/10 | 0/10 | **0%** ² |
| DOC-12 | 可观测性全栈 | 8/8 | 8/8 | **100%** |

¹ Task 4.5 PluginBuilder 7 维打分已被 v2 替换，PROGRESS.md 未更新
² 正确标注为待启；Prism.html 原型可用

**后端真实完成度: 98% | 前端: 0%（vanilla 原型不计入 Next.js 计划）**

---

## 六、竞品对标（Prism vs Poco 增量更新）

基于 5/14 审计 + 本次 poco-claw-main 源码深度分析：

### Prism 持续优势
- 架构 43/50 vs 27/50，安全/可观测/Agent 治理全面领先
- SSE 实时推送 vs Poco 的 HTTP polling
- 单容器部署 vs Poco 的 3 服务 + Docker socket 依赖
- 代码量 1/6 覆盖 80% 功能

### Poco 值得学习（本次新发现）
- **Presets 系统**: 统一复用 model/tools/capabilities 配置，减少重复
- **数据库索引**: 精心设计的组合索引（user_id + is_deleted + created_at）
- **类型安全**: 全量 Pydantic 校验，无 `dict[str, Any]` 返回
- **统一错误处理**: 全局 exception_handlers + 错误码体系
- **异步 Job 队列**: SkillStager/PluginStager 分阶段处理

### Prism 需补齐的差距
| 功能 | 优先级 | 估算 |
|------|--------|------|
| 文件上传 | P1 | 2-3 session |
| OAuth 登录 | P1 | 1-2 session |
| 代码高亮 | P1 | 0.5 session |
| 暗色主题 | P2 | 1 session |
| Onboarding 引导 | P2 | 1 session |
| i18n 国际化 | P3 | 3-5 session |
| Server/Channel 协作 | P3 | 5-8 session |

---

## 七、修复优先级路线图

### Phase 0: 紧急（上线阻塞，1-2 session）

1. **轮换所有密钥** — .env 中 CloudDream/Feishu/EXA/JWT/Encryption/Callback 全部重新生成
2. **删除 dev_default_admin** — 或改为仅 localhost 可见
3. **is_active 检查** — `get_current_user()` + `refresh()` 加 active 校验
4. **HTTPS** — nginx 加 TLS 或前置 Caddy；同步修复 cookie secure 条件
5. **Redis requirepass** — docker-compose 加密码配置
6. **simpleMarkdown XSS** — 输出过 DOMPurify.sanitize()
7. **postMessage origin** — 加白名单校验
8. **健康检查连接泄漏** — 复用 database.engine
9. **/metrics 加鉴权** — admin auth 或 shared secret

### Phase 1: 高优（2-3 session）

1. **Dockerfile multi-stage** — builder + runtime 分离，目标 < 800MB
2. **中国镜像条件化** — `ARG USE_CHINA_MIRRORS=false`
3. **python-jose → PyJWT** — 迁移 JWT 库
4. **Auth 速率限制** — per-IP 5/min login, 3/min OTP
5. **React production build** — 去掉 development.js + Babel standalone
6. **进程边界修复** — MCPClient/CCPluginAdapter/SkillsRegistry 改 IPC 调用
7. **类型严格化** — 消除 settings: Any / redis_client: Any
8. **核心服务补测试** — auth/session/run_lifecycle/task/callback 至少基础覆盖

### Phase 2: 计划修复（3-5 session）

1. **sequence_service UUID 校验**
2. **解密失败加 warning 日志**
3. **消息列表 stable key + 虚拟滚动**
4. **Alembic entrypoint retry + gosu**
5. **gzip 压缩 + 安全头补全**
6. **CI/CD pipeline**（GitHub Actions）
7. **数据库备份策略**
8. **PROGRESS.md Task 4.5 更新**

---

## 八、审计方法论

### 探索阶段（6 agent 并行）
| Agent | 范围 | 耗时 |
|-------|------|------|
| 竞品报告定位 | .superpowers + docs | 13s |
| 后端结构 | backend/ + executor/ | 43s |
| 前端结构 | frontend/ | 24s |
| 基础设施 | docker-compose + Dockerfile + nginx + scripts | 54s |
| PRD 文档 | PRD_V4/ + PROGRESS + DECISIONS | 46s |
| 竞品源码 | poco-claw-main/ | 70s |

### 深度审计阶段（6 agent 并行）
| Agent | 维度 | 检查项 | 耗时 |
|-------|------|--------|------|
| Security | 密钥/Auth/IDOR/注入/CORS/进程/Docker | 70+ 检查点 | 4m18s |
| Architecture | 10 条 ADR + Schema 对齐 | 逐条代码验证 | 3m00s |
| Code Quality | TODO/类型/死代码/重复/错误处理/测试 | 128 文件操作 | 10m09s |
| Frontend | XSS/性能/A11y/响应式/错误处理/代码组织 | 59 文件操作 | 3m31s |
| DevOps | Docker/Nginx/Alembic/脚本/监控/CI | 44 文件操作 | 2m32s |
| Feature | DOC-02~12 逐 Task 抽样验证 | 96 文件操作 | 7m23s |

**总计: 12 agent、525+ 文件操作、~35 分钟并行审计时间。**

---

## 九、结论

**Prism v2 的架构设计是一流的**——10 条 ADR 中 9 条完全合规，后端 98% 真实完成，代码量仅 Poco 的 1/3 但覆盖核心功能。六层分层、三密钥隔离、SSE 实时推送、4 级压缩、Redis 双通道回调等设计远超同类开源项目。

**但安全和运维是上线前的硬伤**。13 个 CRITICAL 问题中，密钥泄露、auth 绕过、HTTPS 缺失、Redis 无密码这四项组合起来意味着：当前状态下任何公网部署都是不安全的。Phase 0 修复预计 1-2 session 即可完成。

**前端是最大的欠账**。Prism.html 原型功能可用但代码质量 5.5/10（XSS 漏洞、React 开发模式、4800 行单文件），DOC-10/11 的 Next.js 计划完全未启。这是从"能跑"到"能用"的关键差距。

**建议执行顺序**: Phase 0 安全紧急修复 → Phase 1 运维加固 + 前端生产化 → Phase 2 补测试 + CI/CD → 然后才启动 DOC-10/11 新功能开发。
