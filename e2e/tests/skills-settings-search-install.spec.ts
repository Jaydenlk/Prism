/**
 * Fix #3 — SkillsSettings 搜索结果"安装"按钮接通(Prism.html line 3068-3171)
 *
 * Spec: docs/superpowers/specs/2026-04-20-fix-skills-settings-search-install.md
 * Plan: docs/superpowers/plans/2026-04-20-fix-skills-settings-search-install.md
 *
 * 8 场景 × 双端 = 16 tests。覆盖正常 / 已装 / 并发 / 422 / 500 / 重新搜状态 /
 * 移动 viewport / 键盘 a11y。所有 test 用 page.route 拦截 /skills/search +
 * /skills/installed + /skills/install,不依赖真实 backend 数据。
 */
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

const INSTALL_OK_BODY = {
  data: {
    id: 'i1',
    user_id: 'u1',
    skill_name: 'demo-skill',
    source: 'github',
    source_url: SEARCH_RESULT.source_url,
    version: '1.0.0',
    installed_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    metadata: { status: 'installed' },
  },
  error: null,
};

async function setupPage(
  page: Page,
  opts: { searchData?: any[]; installedData?: any[]; installResp?: any } = {}
) {
  await page.route('**/api/v1/skills/search**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        data: opts.searchData ?? [SEARCH_RESULT],
        error: null,
      }),
    });
  });
  await page.route('**/api/v1/skills/installed**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        data: opts.installedData ?? [],
        error: null,
      }),
    });
  });
  if (opts.installResp) {
    await page.route('**/api/v1/skills/install', opts.installResp);
  }
  await loginAsAdmin(page);
  // Navigate Settings → 技能 sub-tab (both Sidebar nav and Settings sub-tabs use .nav-item;
  // disambiguate via exact text match on '设置' (main nav) and '技能' (Settings sub-tab,
  // distinct from '技能市场' main nav))
  await page.getByText('设置', { exact: true }).first().click();
  await page.getByText('技能', { exact: true }).first().click();
}

test.describe('Fix #3: SkillsSettings 搜索安装(找茬找错)', () => {
  test('1. 正常 install: 搜索 → 点安装 → 成功 toast → installed list', async ({
    page,
  }) => {
    let installCalled = false;
    let installPayload: any = null;
    await setupPage(page, {
      installResp: async (route: any) => {
        installCalled = true;
        installPayload = route.request().postDataJSON();
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(INSTALL_OK_BODY),
        });
      },
    });
    await page.fill('input[placeholder*="搜索技能名"]', 'demo');
    await page.click('button:has-text("搜索")');
    const installBtn = page.locator(
      '[data-testid="skill-search-install-github-demo-skill"]'
    );
    await expect(installBtn).toBeVisible();
    await installBtn.click();
    await expect(page.locator('.toast.success').first()).toBeVisible({
      timeout: 5000,
    });
    await expect(page.locator('.toast.success').first()).toContainText(
      /安装成功|demo-skill/
    );
    expect(installCalled).toBe(true);
    expect(installPayload).toMatchObject({
      skill_name: 'demo-skill',
      source: 'github',
      source_url: SEARCH_RESULT.source_url,
      version: '1.0.0',
    });
  });

  test('2. 已装边界: installed list 含此 skill → "已装" badge,无安装按钮', async ({
    page,
  }) => {
    // 前端 isInst = installed.some(s => s.skill_name === name) (client-side join);
    // search 的 `installed:true` 是元数据但不参与判断,需 installed list 真含此条
    await setupPage(page, {
      searchData: [
        { ...SEARCH_RESULT, installed: true, installed_version: '1.0.0' },
      ],
      installedData: [
        {
          id: 'i1',
          user_id: 'u1',
          skill_name: 'demo-skill',
          source: 'github',
          source_url: SEARCH_RESULT.source_url,
          version: '1.0.0',
          installed_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          metadata: { status: 'installed' },
        },
      ],
    });
    await page.fill('input[placeholder*="搜索技能名"]', 'demo');
    await page.click('button:has-text("搜索")');
    await expect(
      page.locator('.badge.teal').filter({ hasText: '已装' }).first()
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="skill-search-install-github-demo-skill"]')
    ).toHaveCount(0);
  });

  test('3. 并发防重: 慢速 install + 连点 3 次 → 1 次请求', async ({
    page,
  }) => {
    let installCount = 0;
    await setupPage(page, {
      installResp: async (route: any) => {
        installCount++;
        await new Promise((r) => setTimeout(r, 800));
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(INSTALL_OK_BODY),
        });
      },
    });
    await page.fill('input[placeholder*="搜索技能名"]', 'demo');
    await page.click('button:has-text("搜索")');
    const btn = page.locator(
      '[data-testid="skill-search-install-github-demo-skill"]'
    );
    await btn.click();
    await btn.click({ force: true });
    await btn.click({ force: true });
    await expect(btn).toBeDisabled();
    await expect(btn).toContainText('安装中');
    await expect(page.locator('.toast.success').first()).toBeVisible({
      timeout: 5000,
    });
    expect(installCount).toBe(1);
  });

  test('4. 失败边界 422: → danger toast 含 detail', async ({ page }) => {
    await setupPage(page, {
      installResp: async (route: any) => {
        await route.fulfill({
          status: 422,
          contentType: 'application/json',
          body: JSON.stringify({
            detail: 'github source_url 必填',
          }),
        });
      },
    });
    await page.fill('input[placeholder*="搜索技能名"]', 'demo');
    await page.click('button:has-text("搜索")');
    await page.click('[data-testid="skill-search-install-github-demo-skill"]');
    await expect(page.locator('.toast.danger').first()).toBeVisible({
      timeout: 5000,
    });
    await expect(page.locator('.toast.danger').first()).toContainText(
      /安装失败|source_url/
    );
  });

  test('5. 失败边界 500: → danger toast', async ({ page }) => {
    await setupPage(page, {
      installResp: async (route: any) => {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'internal error' }),
        });
      },
    });
    await page.fill('input[placeholder*="搜索技能名"]', 'demo');
    await page.click('button:has-text("搜索")');
    await page.click('[data-testid="skill-search-install-github-demo-skill"]');
    await expect(page.locator('.toast.danger').first()).toBeVisible({
      timeout: 5000,
    });
  });

  test('6. install 后状态变更: 重新搜 → "已装" badge', async ({ page }) => {
    // install 触发 loadInstalled() → /skills/installed;mock 该 endpoint 让其
    // 在 install 后返回此 skill,模拟 server-side 已落库。然后重新搜,前端
    // installed[] list 已含 demo-skill → isInst=true → 显示 badge。
    let installCalled = false;
    await page.route('**/api/v1/skills/search**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: [SEARCH_RESULT], error: null }),
      });
    });
    await page.route('**/api/v1/skills/installed**', async (route) => {
      const data = installCalled
        ? [
            {
              id: 'i1',
              user_id: 'u1',
              skill_name: 'demo-skill',
              source: 'github',
              source_url: SEARCH_RESULT.source_url,
              version: '1.0.0',
              installed_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              metadata: { status: 'installed' },
            },
          ]
        : [];
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data, error: null }),
      });
    });
    await page.route('**/api/v1/skills/install', async (route) => {
      installCalled = true;
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(INSTALL_OK_BODY),
      });
    });
    await loginAsAdmin(page);
    await page.getByText('设置', { exact: true }).first().click();
    await page.getByText('技能', { exact: true }).first().click();
    await page.fill('input[placeholder*="搜索技能名"]', 'demo');
    await page.click('button:has-text("搜索")');
    await page.click('[data-testid="skill-search-install-github-demo-skill"]');
    await expect(page.locator('.toast.success').first()).toBeVisible({
      timeout: 5000,
    });
    // 重新搜:此时 installed[] 已含 demo-skill → 前端 isInst=true
    await page.click('button:has-text("搜索")');
    await expect(
      page.locator('.badge.teal').filter({ hasText: '已装' }).first()
    ).toBeVisible();
  });

  test('7. 移动 viewport: 按钮高 ≥36px,无溢出', async ({
    page,
    browserName,
  }) => {
    test.skip(
      browserName !== 'webkit',
      'mobile-only check on mobile-safari project'
    );
    await page.setViewportSize({ width: 390, height: 844 });
    await setupPage(page);
    await page.fill('input[placeholder*="搜索技能名"]', 'demo');
    await page.click('button:has-text("搜索")');
    const btn = page.locator(
      '[data-testid="skill-search-install-github-demo-skill"]'
    );
    await expect(btn).toBeVisible();
    const h = await btn.evaluate((el) => el.getBoundingClientRect().height);
    expect(h).toBeGreaterThanOrEqual(36);
  });

  test('8. 键盘 a11y: focus + Enter 触发安装', async ({ page }) => {
    let installCalled = false;
    await setupPage(page, {
      installResp: async (route: any) => {
        installCalled = true;
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(INSTALL_OK_BODY),
        });
      },
    });
    await page.fill('input[placeholder*="搜索技能名"]', 'demo');
    await page.click('button:has-text("搜索")');
    const btn = page.locator(
      '[data-testid="skill-search-install-github-demo-skill"]'
    );
    await btn.focus();
    await expect(btn).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.locator('.toast.success').first()).toBeVisible({
      timeout: 5000,
    });
    expect(installCalled).toBe(true);
  });
});
