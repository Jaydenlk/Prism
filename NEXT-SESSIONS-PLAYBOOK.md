# Prism v2 Next Sessions Playbook(Session 4c+)

> **目标读者**:下一个 `/clear` 后的 Sonnet session(Opus / Sonnet 任意)
> **作用**:把 Session 4a/4b 已验证的 workflow / 开发标准 / 验收标准 / 剩余工作 / 已知坑 全部集中,让新 session 不用爬 HANDOFF-LOG 也能无缝 pick up。
> **版本**:2026-04-20,Session 4b 完成后写的
> **先读顺序**:本文档 → `HANDOFF-LOG.md` 顶部 3 条 → `CLAUDE.md` → 对应 Session 的 spec + plan

---

## 0. Session 4a / 4b 已完成清单(别重做)

| 组件 | 状态 | ADR | 代码位置 |
|---|---|---|---|
| Skills Marketplace backend + 注册 UI | ✅ Session 3 Phase 1 | ADR-086 | `marketplace_registry` 表 + 4 endpoints + SkillsPage 第 4 tab |
| 类型化 Plugin Manifest(基础设施) | ✅ Session 3 Phase 1 | ADR-087 #1 | `plugins_library.plugin_type` + `permissions_json` 列(migration 009) |
| **Plugin Builder type-aware prompt + /validate dispatch + Install Consent dialog** | ✅ **Session 4a** | ADR-087 #2/#3/#4 清零 | `executor/engine/prompt_sections.py` 4 YAML skeleton + `backend/app/api/v1/plugins.py` `POST /plugins/validate-manifest` + `frontend/Prism.html` consentModal |
| Feishu 卡片签名 fix + Slack + Discord 骨架 | ✅ Session 3 Phase 2 | ADR-088 #1 | `im_feishu.verify_card_signature` + `im_slack.py` + `im_discord.py` + 3 webhook 路由 |
| Progressive Disclosure 契约化 | ✅ Session 3 Phase 3 | ADR-089 | 文档化 `executor/plugins/skill_loader.py` 三级加载器 |
| **IM send_card 三端 + AES-256-GCM credential 加密 + Admin 编辑+测试 UI** | ✅ **Session 4b** | ADR-088 #2/#3/#4 清零 | `im_{feishu,slack,discord}.py::send_card` + `credential_cipher.py` (façade over `app.core.security`) + `admin.html` IMChannels 2 modals + `POST /im/channels/{c}/test-send` |

**验证过的 e2e 总数**(develop HEAD):69 passed / 10 skip / 2-3 pre-existing flaky(cross-test session leak,**不是回归**)

---

## 1. 剩余三问题(Session 4c+ 待做)

### #A. 分布式任务拆解(Manus 式 Planner-Executor)
- **状态**:❌ 未做。Session 2b 调研文档 `docs/research/2026-04-19-distributed-task-decomposition.md` 已存在但未消费
- **工作量**:**4-5 个 session**,架构级
- **影响面**:
  - 新增 `Planner` agent(`executor/engine/planner.py` 或 `executor/agents/planner.py`)
  - `coordinator_plan` 表可能扩展字段(需 ADR 授权)
  - `executor/engine/query_engine.py` 重构以支持 TAOR 嵌套 / Planner → Executor 委派
  - 新增 `fork_task` 等工具给 Planner 使用
  - HarnessEvent 扩展:`planner.step.decomposed` / `planner.subtask.dispatched`
- **建议路径**:先做 **Session 4d = 独立 spec + plan,不实施**(花 0.5 session 调研 + 1 session 写 spec + 1 session 写 plan),之后再以每 session 一个子功能推进:
  1. Planner agent 能拆解任意 prompt 为子任务 list
  2. 子任务调度到现有 executor 子进程池
  3. 子任务结果聚合 + conflict 处理
  4. Planner UI(可视化任务树)
  5. end-to-end 人工真实 prompt 测试
- **置信度要求**:此功能涉及 harness + executor 两层,必须先 WebFetch 确认 Manus 等参考产品的实际 API surface(如果要 CC 兼容),否则按"不基于调研二手总结写代码"原则拒绝开工

### #B. Skills Market catalog browser + source 下载(真实可 install)
- **状态**:🟡 骨架完成(ADR-086),用户能注册 marketplace URL 但**看不到 catalog 里的 plugins 列表,点不了"一键 install"**
- **工作量**:**1-2 session**
- **影响面**:
  - 后端 `marketplace_service.py` 扩 `resolve_plugin_source(marketplace_id, plugin_name)`:按 plugin entry 的 `source` 字段(`"./path"` / `{source:"github", repo}` / `{source:"url"}` / `{source:"git-subdir"}` / `{source:"npm"}`)下载到 local cache
  - 新路由 `POST /api/v1/marketplaces/{id}/plugins/{name}/install` 触发下载 + 写 `skill_installs.marketplace_id`
  - 前端 `SkillsPage` Marketplace tab:注册 marketplace 后展开 catalog grid → 每个 plugin row 有"安装"按钮
  - github source 需要 real github API(`api.github.com/repos/{owner}/{repo}/tarball/{ref}`),CI 测试用 Playwright route 拦截 mock,用户换真 token 后自测
- **真实账号测试路径**:用户注册一个公开 GitHub marketplace(如 anthropic/claude-code-plugins)→ 查看 plugins 列表 → 点击 install → 验证 skill 出现在 Installed list
- **已有 spec 基础**:`docs/superpowers/specs/2026-04-20-session3-sk-im2-redesign-design.md` §5.1 + ADR-086 偏离点清单
- **推荐先做(ROI 最高)**

### #C. IM 剩余延后项(Slack Socket Mode + card button action + sensitive list 单一源)
- **状态**:🟡 核心 Session 4b 完成(send_card + AES + Admin UI 生产可用);三项小尾巴
- **工作量**:**0.5 - 1 session**(小 chore,不是大 feature)
- 具体:
  1. **Slack Socket Mode**:用 `xapp-` app token 建 WebSocket long-poll connection(opt-in,`IM_SLACK_MODE=socket`)。当前只支持 Events HTTP。
  2. **Card button action 回传处理**:用户点击 Feishu/Slack/Discord 卡片上的按钮 → 平台回调 Prism 的 webhook → 需要新 handler 把 `action_id` + user_id 作为一个新的 `IMIncomingMessage` 投到 gateway(或新类型 `IMIncomingAction`)。当前用户点按钮不会触发任何 Prism 逻辑。
  3. **Sensitive key 前后端单一源**:`admin.html:875` 的 `/secret|token|key|password/i` regex 与 `credential_cipher.py::_SENSITIVE_SUBSTRINGS` 重复。改成后端通过 `GET /im/channels` 响应 per-field `sensitive: true` 标记,前端读此值渲染 password input。
- **验证**:3 个 Python unit + 3 个 e2e 应足够

---

## 2. 开发原则(必须遵守)

### 用户硬原则(5 条,凌驾 CLAUDE.md)
1. **单一职责** — 每服务/方法一个职责域。如 Session 4b Simplify 发现 Fernet 重复了 security.py AES-GCM,立即删 Fernet 改 façade。
2. **最简代码** — 不做向后兼容,宁愿破坏性更新。删冗余,不保留"以防万一"代码。
3. **类型严格** — TypeScript / Python 类型必须正确,不使用 any,编译错误立即修。Pydantic v2 用 `Literal` / `Annotated` 而非 str。
4. **KISS** — 需要解释的就是太复杂。admin.html 用 dynamic k/v rows 而不是 JSONB textarea 就是 KISS。
5. **文档置信度** — 绝不基于推测写代码。涉及支付/DB/API 关键功能,文档置信度不高就停下要用户提供。Session 3 Phase 1 WebFetched Claude Code marketplace 格式校正了 spec §5.1 就是例子。

### CLAUDE.md 六原则(见 `CLAUDE.md`)
1. 对齐 Schema(19 表字段已定死,不自造)
2. 99% 原文保留(改 PRD 需授权)
3. 密度达标(禁 `...` / `TODO:` / "下次补")
4. 禁止打补丁(超出 Task 范围写 blocker.md)
5. 三密钥独立(JWT / ENCRYPTION / CALLBACK)
6. 进程边界 = 信任边界(Backend 不 import Harness 跑业务)

### 生产代码原则(Session 4b 新加)
- **mock 只限外部平台 API 响应让 CI 跑通**,**生产代码不含 test-only hook**
- 禁止 `force-open button` / `window.__test_*` / 特殊 URL query 触发 test 行为
- 测试和生产走同一 DOM + 同一 request path;只用 Playwright `page.route` 拦截 *外部* HTTP

---

## 3. Workflow(Session 4a / 4b 已验证的标准流程)

```
1. 加载 superpowers:using-superpowers
2. 加载 superpowers:brainstorming
   └── 必要时 WebFetch 真实文档(D1 = 文档置信度原则),5 秒 auto-proceed 写 spec
3. 写 docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md + commit
4. 加载 superpowers:writing-plans
   └── 写 docs/superpowers/plans/YYYY-MM-DD-<topic>.md,每 Task 含 "Files" + "Step 1 写代码" + "Step 2 跑 expected FAIL" + "Step 3 impl" + "Step 4 跑 expected PASS" + "Step 5 commit",具体 code block,no TBD
5. 加载 superpowers:using-git-worktrees
   └── git worktree add .worktrees/<topic> -b redesign/<topic> develop
   └── powershell New-Item Junction e2e/node_modules → 主仓 node_modules
   └── cp .env 到新 worktree
6. 加载 superpowers:test-driven-development
   └── RED:写单元 + e2e 测试,rebuild backend,expect FAIL,commit
7. GREEN:实现代码(iterative per Task),每 commit 跑相应测试 expect PASS
8. 加载 frontend-design + ui-ux-pro-max(前端改动时)
   └── luxury-refined:serif title + amber chip + framed body + 44pt mobile buttons
9. 加载 simplify skill
   └── 并行派 3 subagent(reuse/quality/efficiency),get diff develop..HEAD
   └── Apply blocking findings(如 Session 4b 的 Fernet → security.py façade)
   └── 跳过 trivial findings,记录到 HANDOFF follow-up
10. PJR checks(本地,避开 pjr skill 中 node lint 对 zero-build 不适用):
    - docker compose exec backend python -c "import ast" on 改动 .py files
    - docker compose exec backend python -c "from app.main import app" 确认 import chain
    - node --check frontend/apiClient.js(Prism.html / admin.html 通过 Playwright 验证)
    - curl smoke endpoints
    - git status clean + commits ahead of develop 数对
11. 加载 git-merge-to-develop skill(或直接 no-ff,无 remote 时按 Session 1 precedent)
    └── cd 主仓 && git checkout develop && git merge --no-ff <branch> -m "<message>"
12. docker compose -p prismv3 up -d --force-recreate nginx(切回主仓 mount)
13. 完整 Playwright regression 双 viewport:npx playwright test --reporter=line --retries=0
    └── 对照 develop 前的 baseline 数,验证 "新增 X passed / 零 regression"
    └── pre-existing flaky(下方清单)不算 regression
14. 更新 DECISIONS.md(对应 ADR 的偏离点 strikethrough + Session 号标记)
15. 更新 HANDOFF-LOG.md(顶部加新 session entry,包含"具体做了什么 / 验证结果 / 用户真实账号测试步骤 / 延后项 / commits")
16. commit final HANDOFF + DECISIONS
17. 对用户说一句:本 session 交付 X / 延后 Y,等用户 /clear
```

---

## 4. 验收标准(量化)

| 维度 | 标准 |
|---|---|
| **TDD 循环完整** | RED commit → GREEN commit 可追溯(不能一把 GREEN 无 RED) |
| **Python unit** | ≥ 每个新功能 3 tests;全 GREEN;rebuild backend 后 in-container pytest |
| **Playwright e2e** | 每个新 UI 功能 ≥ 4 tests × 桌面 + 移动 = ≥ 8 tests;全 GREEN 或 proper skip;`npx playwright test --reporter=line --retries=0` |
| **零回归** | Full regression 新 fail 数 = 0(pre-existing flaky 列表里的不算) |
| **Simplify** | 3 subagent(reuse / quality / efficiency)并行跑完;blocking findings 全 fixed 并 recommit;其他 findings 明确列 HANDOFF follow-up |
| **PJR** | AST parse 100% / in-container import chain 无 ImportError / apiClient.js `node --check` OK / endpoints curl smoke 全 2xx |
| **Merge** | 本地 no-ff merge 到 develop,message 含 "ADR-XXX 偏离点 #Y 清零" 或 "新 ADR-XXX" |
| **Docker** | `docker compose -p prismv3 up -d --force-recreate nginx` 切回主仓 mount;`backend` 健康 200 |
| **DECISIONS.md** | 对应 ADR 偏离点打 ~~strikethrough~~ + ✅ Session X 清零 |
| **HANDOFF-LOG.md** | 新条目含:做了什么(文件清单 + TDD 循环记录) / 验证结果(所有数字) / 用户真实账号测试步骤(如涉及 live API) / 延后项 / commits list |
| **生产代码无 mock** | grep -r "test-only\|force-open\|__test" production code → 0 结果;mock 只限 Playwright `page.route` 对外部 HTTP |
| **用户自主真实账号测试步骤** | 如果功能涉及真实账号(IM / GitHub 等),HANDOFF 必含逐步配置指南 |

---

## 5. 已知 pre-existing flaky tests(别当回归处理)

1. `chat-msg-render.spec.ts:18 Bug 1 user bubble persists` — desktop-chromium 偶发 timeout,单跑 PASS,full suite 触发。Session 1 起已存在。
2. `plugin-consent-dialog.spec.ts:*` 3 tests × mobile-safari — cross-test session-leak(loginAsAdmin 等 `input[type=email]` 10s timeout)。单跑 Session 4a `plugin-consent-dialog.spec.ts` mobile 8/8 PASS;full suite 顺序时不稳。
3. `skills.spec.ts:64 install skill via API` — mobile-safari 同上 session-leak 导致跳或失败。

**Follow-up(可单独一个 0.5 session 修)**:`e2e/fixtures/auth.ts` 加 `test.beforeEach` 清 localStorage/sessionStorage 或用 Playwright `storageState` 固化 admin token。

---

## 6. 关键坑(Session 1 - 4b 踩过的)

1. **Playwright baseURL 带 path**:`ctx.post('/auth/login')` 会 drop 掉 baseURL 的 `/api/v1`(absolute path)。**修法**:baseURL 只设 origin,path 显式写 `/api/v1/auth/login`。Session 4a commit `8ad1105` 已修 fixture。
2. **Docker backend 是 baked image 不是 mount**:修 backend 代码后必须 `docker compose -p prismv3 up -d --build --force-recreate backend`。
3. **pytest 不在 production image**:每次重建后 `docker compose -p prismv3 exec -T backend pip install pytest pytest-asyncio` 临时装(dev extras 未装)。
4. **nginx mount 指向哪个 worktree**:worktree docker-compose.yml 的 nginx volume 是 `./frontend` 相对路径。切 worktree 或 merge 回 develop 后 **必须** `docker compose -p prismv3 up -d --force-recreate nginx` 切 mount。
5. **飞书两套签名算法**:事件订阅 `SHA-256(ts + encrypt_key + body)`;卡片回调 `SHA-1(ts + nonce + verification_token + body)`。别混。
6. **Discord Ed25519 bad sig 必须返 non-2xx**:Discord 会 probe 坏签名验证你拒绝。`im.py:webhook_discord` 返 401。
7. **CLAUDE.md 19 表 schema 定死**:新功能想加字段前先看是否能用现有 JSONB 字段(如 Session 4b 没加 `im_channel_configs.encrypted_at` 而是在 value 里加 `aesgcm:` 前缀)。
8. **Pydantic v2 discriminated union 最简**:比手动 `_TYPE_MAP.get(t)` + 多分支校验干净得多(Session 4a simplify 学到)。
9. **Simplify subagent 的 reuse agent 最易发现重复**:Session 4b reuse subagent 一眼看出 Fernet 重复 security.py,quality/efficiency 都没看到。**务必 3 agent 并行,不跳 reuse**。
10. **外部 webhook URL 测试用 `example.test` 域名**:DNS 必失败,`_try_fetch` 返 (None, None) 不 crash。

---

## 7. Docker / worktree 清理(每 session 结束或 /clear 前可选)

### Worktrees 可清理(每个 ~303 MB)
```bash
cd "E:/Agent program/PrismV3"
git worktree list
# 现有(Session 4b 后):
#   E:/Agent program/PrismV3                      [develop]
#   .worktrees/fix-chat-md                        [fix/chat-msg...]  (Session 1 完成)
#   .worktrees/redesign-doc-sk                    [redesign/doc-sk]  (Session 3 Phase 1 完成)
#   .worktrees/redesign-doc-im2                   [redesign/doc-im2] (Session 3 Phase 2 完成)
#   .worktrees/plugin-builder-typed               [redesign/plugin-builder-typed] (Session 4a 完成)
#   .worktrees/im-sendcard-aes                    [redesign/im-sendcard-aes]      (Session 4b 完成)

# 已合进 develop 的 worktree 可安全 remove:
git worktree remove .worktrees/fix-chat-md
git worktree remove .worktrees/redesign-doc-sk
git worktree remove .worktrees/redesign-doc-im2
git worktree remove .worktrees/plugin-builder-typed
git worktree remove .worktrees/im-sendcard-aes
```

### Docker nginx mount(切回主仓)
```bash
cd "E:/Agent program/PrismV3"
docker compose -p prismv3 up -d --force-recreate nginx
```

### 本 session stale `prism-backend:2.0` image
上次 `.worktrees/im-sendcard-aes` build 的 image 包含 Session 4b 代码,merge 后主仓 develop 内容一致,无需额外 rebuild;若看到 session leak 行为再 `docker compose -p prismv3 up -d --build --force-recreate backend` 一次。

---

## 8. 下一 session 开工 SOP(**必读 3 条**)

1. 读 `HANDOFF-LOG.md` 顶部最新 3 条
2. 读本 `NEXT-SESSIONS-PLAYBOOK.md` §0 已完成清单(避免重做)+ §1 挑一项
3. 确认 docker 健康:`curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/api/v1/health/live` → 200

**然后**按 §3 Workflow 推进。如果单 session 塞不下(如 #A 分布式),就只做 §3 前 4 步(spec + plan)不实施。

---

## 9. 推荐顺序(依据 ROI + 独立性)

1. **Session 4c = #B Skills Market catalog browser**(独立 1-2 session,ROI 最高,用户最能直观感受)
2. **Session 4d = #C IM 三小尾**(0.5-1 session,纯后端 + 小前端,清扫)
3. **Session 4e+ = #A 分布式任务拆解**(独立 4-5 session 系列,最后做,需要 spec-only 第一 session + 逐步实施后续)

---

## 10. code-reviewer 累积队列(终会有一次)

Session 1 / 3-Phase1 / 3-Phase2 / 3-Phase3 / 4a / 4b 总共 **6 次独立 code-reviewer 审查未跑**(quota 问题 + budget 原因)。建议在 Session 4c 开头一次性补跑 `superpowers:requesting-code-review` 对 ADR-086 ~ ADR-089 + Session 4a/4b 的改动一并独立审查。Agent 可能产出 1-2 条 Important findings,单独 commit 修。

---

## 附录 A:每 session 打开前必检查的 5 件事

- [ ] `git log --oneline -5` — develop HEAD 是不是你预期的
- [ ] `git status --short` — 工作区 clean(除 `.claude/settings.json` 等 pre-existing)
- [ ] `docker compose -p prismv3 ps` — backend / postgres / redis healthy
- [ ] `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/api/v1/health/live` → 200
- [ ] 读 `HANDOFF-LOG.md` 顶部最新 session + 本文档 §0

## 附录 B:每 session 收工前必产出

- [ ] `DECISIONS.md` 对应 ADR 偏离点状态更新(~~strikethrough~~ 已清零项)
- [ ] `HANDOFF-LOG.md` 顶部新 session 条目(包含 Files 改动清单 + TDD 循环记录 + 验证数字 + 用户真实测试步骤 + 延后项 + commits list)
- [ ] 如果有新 ADR,追加到 `DECISIONS.md` 末尾
- [ ] 如果新增文件超过 5 个或架构变化,更新 `CLAUDE.md` §关键文件索引(少见)
- [ ] git log --oneline develop..HEAD(合并前)确认 commit chain 清晰
- [ ] Merge 后 git log --oneline -10(确认 merge commit 进 develop)

---

*End of Playbook — 写于 2026-04-20 Session 4b 结束后,2316 字。*
