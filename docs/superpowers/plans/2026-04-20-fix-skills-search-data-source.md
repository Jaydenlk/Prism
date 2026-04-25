# Fix#3+ Skills Search 数据源重构 Plan(紧凑版)

> **For agentic workers:** inline-execute, single-session.

**Goal:** 删 `GitHubSource` + 新 `MarketplaceCatalogSource`(读 Block 1 `marketplace_registry.catalog_json`)+ 前端 empty state(Linear 风格)。

**Spec:** `docs/superpowers/specs/2026-04-20-fix-skills-search-data-source.md` (45d9946)

---

## Task 1: Worktree

```bash
cd "E:/Agent program/PrismV3"
git worktree add .worktrees/fix-skills-search-source -b fix/skills-search-source develop
cp .env .worktrees/fix-skills-search-source/.env
cmd //c "mklink /J .worktrees\fix-skills-search-source\e2e\node_modules e2e\node_modules"
cd .worktrees/fix-skills-search-source
docker compose -p prismv3 up -d --force-recreate nginx
```

## Task 2: 删 GitHubSource + 新 MarketplaceCatalogSource

`executor/plugins/skills_registry.py`:
- 删 L303-401 `class GitHubSource`
- 在 `LocalSource` 之后插入 `MarketplaceCatalogSource`(spec §4 完整代码)
- 修改 `SkillsRegistry.__init__` default sources(若有 GitHubSource 注入)
- 删 `__init__.py` 的 `GitHubSource` export

## Task 3: backend `_get_registry` 注入 db

`backend/app/api/v1/skills.py:611` 修改 `_get_registry`(spec §5 代码)。

## Task 4: Python unit RED → GREEN

写 `backend/tests/test_marketplace_catalog_source.py`(8 tests,spec §7)。
Rebuild backend → run tests → 8/8 pass。

## Task 5: 前端 empty state + e2e RED → GREEN

- `frontend/Prism.html` SkillsSettingsTab: 加 `marketplacesCount` state + empty state 文案 + "去注册"链接
- `frontend/Prism.html` SkillsPage: 类似 empty state(query 无 match 时)
- 写 `e2e/tests/skills-search-data-source.spec.ts`(4 场景 × 双端 = 8 tests)
- nginx force-recreate → e2e 双端 → 8/8 pass

## Task 6: Simplify(inline 自检)

- 单一职责:MarketplaceCatalogSource 只 flatten + filter
- 复用 marketplace_registry 表(无新数据源)
- 删旧 anti-pattern(GitHubSource)非 patch

## Task 7: PJR

- backend AST + import + pytest 全过
- frontend node --check apiClient.js(无改)
- curl smoke /skills/search 返非空(注册 marketplace 后)

## Task 8: code-reviewer subagent + merge + final regression + HANDOFF

- subagent 审 1-commit branch
- 合并 `git merge --no-ff` 到 develop
- nginx 切回主仓
- final regression(skills + marketplace + skills-settings-search-install + skills-search-data-source)
- HANDOFF 更新

---

*End of plan — single-pass workflow inline.*
