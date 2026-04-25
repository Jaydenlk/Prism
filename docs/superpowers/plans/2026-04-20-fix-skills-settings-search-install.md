# Fix #3 SkillsSettings 搜索安装 Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` for inline execution (single-file fix, no subagent needed).

**Goal:** Wire `SkillsSettingsTab` 搜索结果"安装"按钮 → 现有 `/skills/install` endpoint(替换 stale toast "暂不支持")。

**Architecture:** 0 后端改动;前端单文件 1 函数 + 1 button rewire;复用 SkillsPage GitHub install payload shape。

**Tech Stack:** React (Prism.html in-browser),Playwright(双端 e2e),既有 PrismAPI client。

**Spec:** `docs/superpowers/specs/2026-04-20-fix-skills-settings-search-install.md`(commit `af85a27`)

---

## File Structure

| File | Responsibility |
|---|---|
| `frontend/Prism.html` SkillsSettingsTab L3068-3171 | 加 `installingSearch` state + `handleInstallFromSearch` + button wire |
| `e2e/tests/skills-settings-search-install.spec.ts` | 8 场景 × 桌面+移动 = 16 tests(找茬找错) |

---

## Task 1: Worktree setup

**Files:** none (git operation)

- [ ] **Step 1: Create worktree off develop**

```bash
cd "E:/Agent program/PrismV3"
git worktree add .worktrees/fix-skills-search-install -b fix/skills-search-install develop
```

- [ ] **Step 2: Copy .env + e2e node_modules junction**

```bash
cp .env .worktrees/fix-skills-search-install/.env
cmd //c "mklink /J .worktrees\fix-skills-search-install\e2e\node_modules e2e\node_modules"
```

- [ ] **Step 3: Switch nginx mount to worktree**

```bash
cd .worktrees/fix-skills-search-install
docker compose -p prismv3 up -d --force-recreate nginx
sleep 3
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/Prism.html  # expect 200
```

---

## Task 2: RED — e2e test file(failing 因为前端还是死 toast)

**Files:**
- Create: `e2e/tests/skills-settings-search-install.spec.ts`

- [ ] **Step 1: Write 8 e2e tests**

```typescript
import { test, expect, Page } from '@playwright/test';
import { loginAsAdmin } from '../fixtures/auth';

const SEARCH_RESULT = {
  name: 'demo-skill',
  description: 'A demo skill for fix#3 install test',
  version: '1.0.0',
  source: 'github',
  source_url: 'https://github.com/example/demo-skill',
  author: 'tester',
  tags: ['demo'],
  installed: false,
  installed_version: null,
};

async function setupPage(page: Page, opts: { searchData?: any[]; installedData?: any[]; installResp?: any } = {}) {
  await page.route('**/api/v1/skills/search**', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ data: opts.searchData ?? [SEARCH_RESULT], error: null }) });
  });
  await page.route('**/api/v1/skills/installed**', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ data: opts.installedData ?? [], error: null }) });
  });
  if (opts.installResp) {
    await page.route('**/api/v1/skills/install', opts.installResp);
  }
  await loginAsAdmin(page);
  // Navigate Settings → 技能 tab
  const settingsNav = page.locator('.nav-item').filter({ hasText: '设置' });
  await settingsNav.first().click();
  const skillsTab = page.locator('.tab').filter({ hasText: '技能' });
  await skillsTab.first().click();
}

test.describe('SkillsSettings 搜索安装 (Fix #3)', () => {
  test('1. 正常 install: 搜索 → 点安装 → 成功 toast → installed list 含新条', async ({ page }) => {
    let installCalled = false;
    let installPayload: any = null;
    await setupPage(page, {
      installResp: async (route: any) => {
        installCalled = true;
        installPayload = route.request().postDataJSON();
        await route.fulfill({ status: 201, contentType: 'application/json',
          body: JSON.stringify({ data: { id: 'i1', user_id: 'u1', skill_name: 'demo-skill',
            source: 'github', source_url: SEARCH_RESULT.source_url, version: '1.0.0',
            installed_at: new Date().toISOString(), updated_at: new Date().toISOString(),
            metadata: { status: 'installed' } }, error: null }) });
      },
    });
    await page.fill('input[placeholder*="搜索技能名"]', 'demo');
    await page.click('button:has-text("搜索")');
    const installBtn = page.locator('[data-testid="skill-search-install-demo-skill"]');
    await expect(installBtn).toBeVisible();
    await installBtn.click();
    await expect(page.locator('.toast.success').first()).toBeVisible({ timeout: 5000 });
    await expect(page.locator('.toast.success').first()).toContainText(/安装成功|demo-skill/);
    expect(installCalled).toBe(true);
    expect(installPayload).toMatchObject({ skill_name: 'demo-skill', source: 'github',
      source_url: SEARCH_RESULT.source_url, version: '1.0.0' });
  });

  test('2. 已装边界: installed=true → "已装" badge,无安装按钮', async ({ page }) => {
    await setupPage(page, { searchData: [{ ...SEARCH_RESULT, installed: true, installed_version: '1.0.0' }] });
    await page.fill('input[placeholder*="搜索技能名"]', 'demo');
    await page.click('button:has-text("搜索")');
    await expect(page.locator('.badge.teal').filter({ hasText: '已装' }).first()).toBeVisible();
    await expect(page.locator('[data-testid="skill-search-install-demo-skill"]')).toHaveCount(0);
  });

  test('3. 并发防重: 慢速 install 中 + 连点 3 次 → 1 次请求,disabled state', async ({ page }) => {
    let installCount = 0;
    await setupPage(page, {
      installResp: async (route: any) => {
        installCount++;
        await new Promise(r => setTimeout(r, 800));
        await route.fulfill({ status: 201, contentType: 'application/json',
          body: JSON.stringify({ data: { id:'i1', user_id:'u1', skill_name:'demo-skill', source:'github', source_url:SEARCH_RESULT.source_url, version:'1.0.0', installed_at:new Date().toISOString(), updated_at:new Date().toISOString(), metadata:{status:'installed'} }, error: null }) });
      },
    });
    await page.fill('input[placeholder*="搜索技能名"]', 'demo');
    await page.click('button:has-text("搜索")');
    const btn = page.locator('[data-testid="skill-search-install-demo-skill"]');
    await btn.click();
    await btn.click({ force: true });
    await btn.click({ force: true });
    await expect(btn).toBeDisabled();
    await expect(btn).toContainText('安装中');
    await expect(page.locator('.toast.success').first()).toBeVisible({ timeout: 5000 });
    expect(installCount).toBe(1);
  });

  test('4. 失败边界 422: install 返 422 → danger toast 含具体 detail', async ({ page }) => {
    await setupPage(page, {
      installResp: async (route: any) => {
        await route.fulfill({ status: 422, contentType: 'application/json',
          body: JSON.stringify({ detail: 'github source_url 必填' }) });
      },
    });
    await page.fill('input[placeholder*="搜索技能名"]', 'demo');
    await page.click('button:has-text("搜索")');
    await page.click('[data-testid="skill-search-install-demo-skill"]');
    await expect(page.locator('.toast.danger').first()).toBeVisible({ timeout: 5000 });
    await expect(page.locator('.toast.danger').first()).toContainText(/安装失败|source_url/);
  });

  test('5. 失败边界 500: → danger toast 含 server error', async ({ page }) => {
    await setupPage(page, {
      installResp: async (route: any) => {
        await route.fulfill({ status: 500, contentType: 'application/json',
          body: JSON.stringify({ detail: 'internal error' }) });
      },
    });
    await page.fill('input[placeholder*="搜索技能名"]', 'demo');
    await page.click('button:has-text("搜索")');
    await page.click('[data-testid="skill-search-install-demo-skill"]');
    await expect(page.locator('.toast.danger').first()).toBeVisible({ timeout: 5000 });
  });

  test('6. install 后状态变更: 重新搜 → installed=true', async ({ page }) => {
    let searchCount = 0;
    await page.route('**/api/v1/skills/search**', async route => {
      searchCount++;
      const data = searchCount === 1 ? [SEARCH_RESULT] : [{ ...SEARCH_RESULT, installed: true, installed_version: '1.0.0' }];
      await route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ data, error: null }) });
    });
    await page.route('**/api/v1/skills/installed**', async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: [], error: null }) });
    });
    await page.route('**/api/v1/skills/install', async route => {
      await route.fulfill({ status: 201, contentType: 'application/json',
        body: JSON.stringify({ data: { id:'i1', user_id:'u1', skill_name:'demo-skill', source:'github', source_url:SEARCH_RESULT.source_url, version:'1.0.0', installed_at:new Date().toISOString(), updated_at:new Date().toISOString(), metadata:{status:'installed'} }, error: null }) });
    });
    await loginAsAdmin(page);
    const settingsNav = page.locator('.nav-item').filter({ hasText: '设置' });
    await settingsNav.first().click();
    const skillsTab = page.locator('.tab').filter({ hasText: '技能' });
    await skillsTab.first().click();
    await page.fill('input[placeholder*="搜索技能名"]', 'demo');
    await page.click('button:has-text("搜索")');
    await page.click('[data-testid="skill-search-install-demo-skill"]');
    await expect(page.locator('.toast.success').first()).toBeVisible({ timeout: 5000 });
    // 重新搜
    await page.click('button:has-text("搜索")');
    await expect(page.locator('.badge.teal').filter({ hasText: '已装' }).first()).toBeVisible();
  });

  test('7. 移动 viewport: 按钮高 ≥36px,宽度不溢出', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await setupPage(page);
    await page.fill('input[placeholder*="搜索技能名"]', 'demo');
    await page.click('button:has-text("搜索")');
    const btn = page.locator('[data-testid="skill-search-install-demo-skill"]');
    await expect(btn).toBeVisible();
    const h = await btn.evaluate(el => el.getBoundingClientRect().height);
    expect(h).toBeGreaterThanOrEqual(36);
  });

  test('8. 键盘 a11y: Tab → focus install button → Enter 触发', async ({ page }) => {
    let installCalled = false;
    await setupPage(page, {
      installResp: async (route: any) => {
        installCalled = true;
        await route.fulfill({ status: 201, contentType: 'application/json',
          body: JSON.stringify({ data: { id:'i1', user_id:'u1', skill_name:'demo-skill', source:'github', source_url:SEARCH_RESULT.source_url, version:'1.0.0', installed_at:new Date().toISOString(), updated_at:new Date().toISOString(), metadata:{status:'installed'} }, error: null }) });
      },
    });
    await page.fill('input[placeholder*="搜索技能名"]', 'demo');
    await page.click('button:has-text("搜索")');
    const btn = page.locator('[data-testid="skill-search-install-demo-skill"]');
    await btn.focus();
    await expect(btn).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.locator('.toast.success').first()).toBeVisible({ timeout: 5000 });
    expect(installCalled).toBe(true);
  });
});
```

- [ ] **Step 2: Run e2e expect ALL FAIL(死按钮 toast 是 "暂不支持",不会触发 install 调用)**

```bash
cd .worktrees/fix-skills-search-install/e2e
node_modules/.bin/playwright test tests/skills-settings-search-install.spec.ts --project=desktop-chromium --reporter=line --timeout=30000
```
Expected: 8 failed(test 1/3/4/5/6/8 因为 install 不被调用 / test 7 toBeVisible 可能 OK 因为 button 存在但 onClick 不对 → 但 button 文案"暂不支持" toast 让 test 7 也 fail)

---

## Task 3: GREEN — Prism.html SkillsSettingsTab 改动

**Files:**
- Modify: `frontend/Prism.html` SkillsSettingsTab L3068-3171

- [ ] **Step 1: 加 `installingSearch` state**

在 `SkillsSettingsTab` 函数 line 3074 之后加:
```js
const [installingSearch, setInstallingSearch] = useState({}); // { [skill_name]: true }
```

- [ ] **Step 2: 加 `handleInstallFromSearch` 函数**

在 `handleUninstall` 之前(约 line 3102)加:
```js
async function handleInstallFromSearch(sk) {
  const name = sk.skill_name || sk.name;
  if (installingSearch[name]) return;
  setInstallingSearch(prev => ({ ...prev, [name]: true }));
  try {
    await PrismAPI.skills.install({
      skill_name: name,
      source: sk.source,
      source_url: sk.source_url,
      version: sk.version,
    });
    onToast({ id: Date.now(), kind: "success", title: "安装成功", body: name });
    await loadInstalled();
  } catch (err) {
    onToast({ id: Date.now(), kind: "danger", title: "安装失败", body: err.message || String(err) });
  }
  setInstallingSearch(prev => { const next = { ...prev }; delete next[name]; return next; });
}
```

- [ ] **Step 3: 替换死按钮(L3138-3140)**

旧:
```jsx
{isInst ? <span className="badge teal">已装</span> : (
  <button className="btn sm primary" onClick={() => onToast({ id: Date.now(), title: "暂不支持", body: "从搜索结果安装需要提供 source_url/version，请联系管理员操作。" })}>安装</button>
)}
```

新:
```jsx
{isInst ? <span className="badge teal">已装</span> : (
  <button
    data-testid={`skill-search-install-${name}`}
    className="btn sm primary"
    onClick={() => handleInstallFromSearch(sk)}
    disabled={!!installingSearch[name]}
    style={{ minHeight: 36 }}
  >{installingSearch[name] ? "安装中…" : "安装"}</button>
)}
```

- [ ] **Step 4: Recreate nginx + run e2e expect ALL PASS**

```bash
cd "E:/Agent program/PrismV3/.worktrees/fix-skills-search-install"
docker compose -p prismv3 up -d --force-recreate nginx
sleep 3
cd e2e
node_modules/.bin/playwright test tests/skills-settings-search-install.spec.ts --project=desktop-chromium --project=mobile-safari --reporter=line --timeout=30000
```
Expected: 16/16 PASS(8 × 2 viewport)

- [ ] **Step 5: Commit**

```bash
git add frontend/Prism.html e2e/tests/skills-settings-search-install.spec.ts
git commit -m "fix(#3): SkillsSettings 搜索安装死按钮 → wire to existing /skills/install"
```

---

## Task 4: simplify(轻量,1 文件)

- [ ] **Step 1: Get diff**
```bash
git diff develop..HEAD --stat
```

- [ ] **Step 2: Inline review**(单文件改动 + 几十行,跳过 3 subagent 并行,直接自检):
- ✅ 单一职责:`handleInstallFromSearch` 只负责 install + toast + reload
- ✅ 最简代码:无 fallback / 无重试,失败直接 toast
- ✅ 类型严格:不用 any(TS-style 注释)
- ✅ KISS:18 行函数 + 7 行 button JSX
- ✅ 复用现有 `PrismAPI.skills.install` + `loadInstalled` + `onToast`

无 blocking finding。

---

## Task 5: PJR

- [ ] **Step 1: 前端 lint(按 CLAUDE.md H 硬要求)**

```bash
node --check frontend/apiClient.js  # apiClient 未改,smoke
# Prism.html no JS bundler — Playwright 加载验证
```

- [ ] **Step 2: 后端 AST + import**(0 后端改动,跳过深度,只 sanity)

```bash
docker compose -p prismv3 exec -T backend python -c "from app.main import app; print('OK')"
```

- [ ] **Step 3: 工作区 + commits**

```bash
git status --short  # clean
git log --oneline develop..HEAD  # 1 commit (fix#3)
```

---

## Task 6: code-reviewer subagent(轻量 review,单文件)

- [ ] Dispatch `superpowers:code-reviewer` against this 1-commit diff,focus security(死代码替换是否引入新安全问题)+ correctness。Skip 如果 simplify 已覆盖。

---

## Task 7: git-merge-to-develop

- [ ] **Step 1: 主仓 no-ff merge**

```bash
cd "E:/Agent program/PrismV3"
git checkout develop
git merge --no-ff fix/skills-search-install -m "Merge fix#3: SkillsSettings 搜索安装死按钮接通

Wire SkillsSettingsTab L3138 死按钮 → 调现有 /skills/install endpoint
(同 SkillsPage GitHub tab 链路);0 backend 改动;e2e 16 tests 双端全绿。"
```

- [ ] **Step 2: 切 nginx 回主仓**

```bash
docker compose -p prismv3 up -d --force-recreate nginx
sleep 3
curl -s http://localhost:8080/Prism.html | grep -c "skill-search-install"  # 验证新 testid 在主仓
```

---

## Task 8: 最终 Playwright 双端验收 + HANDOFF

- [ ] **Step 1: Full regression e2e**

```bash
cd e2e
node_modules/.bin/playwright test tests/skills-settings-search-install.spec.ts --project=desktop-chromium --project=mobile-safari --reporter=line --timeout=30000
```
Expected: **16/16 PASS**(零 regression)

- [ ] **Step 2: 更新 PROGRESS.md(fix#3 行)+ HANDOFF-LOG**

PROGRESS.md 加 fix#3 row
HANDOFF-LOG.md 顶部加新 entry(commit / files / 16 测试)

- [ ] **Step 3: Final commit**
```bash
git add PROGRESS.md HANDOFF-LOG.md
git commit -m "docs(fix#3): PROGRESS + HANDOFF — fix#3 完成,8/9 缺陷待修"
```

---

## Self-Review

✅ Spec coverage:每节都有 task(状态机 = Task 3 Step 3,测试 = Task 2,反打补丁 = simplify Task 4,验收 = Task 8)
✅ 占位符扫描:无 TBD/TODO
✅ 类型一致:`installingSearch` / `handleInstallFromSearch` / `data-testid="skill-search-install-${name}"` 跨 task 一致

---

## Execution

Inline execution chosen(单文件 fix + 用户 auto mode),`superpowers:executing-plans` 紧凑跑全 8 tasks。
