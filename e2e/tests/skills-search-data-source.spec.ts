/**
 * Fix #3+ — Skills search 数据源根因式重构 e2e
 *
 * 验证 MarketplaceCatalogSource(替代 GitHubSource)+ Linear-style empty state。
 * 4 场景 × 桌面+移动 = 8 tests。
 */
import { test, expect, Page } from '@playwright/test';
import { loginAsAdmin } from '../fixtures/auth';

const MP_PLUGIN = {
  name: 'demo-plugin',
  description: 'A plugin for fix#3+ search test',
  version: '2.0.0',
  source: 'marketplace',
  source_url: 'marketplace://test-mp/demo-plugin',
  author: 'tester',
  tags: ['demo', 'test'],
  installed: false,
  installed_version: null,
};

async function setupSettingsSkills(page: Page, opts: {
  marketplaces?: any[]; searchData?: any[]; installedData?: any[];
} = {}) {
  await page.route('**/api/v1/marketplaces**', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ data: opts.marketplaces ?? [], error: null }),
      });
    } else {
      await route.continue();
    }
  });
  await page.route('**/api/v1/skills/search**', async (route) => {
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ data: opts.searchData ?? [], error: null }),
    });
  });
  await page.route('**/api/v1/skills/installed**', async (route) => {
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ data: opts.installedData ?? [], error: null }),
    });
  });
  await loginAsAdmin(page);
  await page.getByText('设置', { exact: true }).first().click();
  await page.getByText('技能', { exact: true }).first().click();
}

test.describe('Fix #3+ Skills search 数据源(找茬找错)', () => {
  test('1. 0 marketplaces + 搜无 match → empty state 显示"去注册"链接', async ({ page }) => {
    await setupSettingsSkills(page, { marketplaces: [], searchData: [] });
    await page.fill('input[placeholder*="搜索技能名"]', 'nothing');
    const respPromise = page.waitForResponse(r => r.url().includes('/skills/search'));
    await page.click('button:has-text("搜索")');
    await respPromise;
    const empty = page.locator('[data-testid="skills-search-empty"]');
    await expect(empty).toBeVisible({ timeout: 10000 });
    await expect(empty).toContainText('无匹配 "nothing"');
    await expect(empty).toContainText('还没注册 marketplace');
    await expect(
      page.locator('[data-testid="skills-search-empty-register-link"]')
    ).toBeVisible();
  });

  test('2. 有 marketplace + query 无 match → empty state 不含"去注册"', async ({ page }) => {
    await setupSettingsSkills(page, {
      marketplaces: [{ id: 'm1', name: 'mp', url: 'x', plugin_count: 0, catalog_json: null, last_fetched_at: null, created_by: 'u', created_at: '' }],
      searchData: [],
    });
    await page.fill('input[placeholder*="搜索技能名"]', 'zzz');
    await page.click('button:has-text("搜索")');
    const empty = page.locator('[data-testid="skills-search-empty"]');
    await expect(empty).toBeVisible({ timeout: 10000 });
    await expect(empty).toContainText('无匹配 "zzz"');
    await expect(empty).not.toContainText('还没注册 marketplace');
    await expect(
      page.locator('[data-testid="skills-search-empty-register-link"]')
    ).toHaveCount(0);
  });

  test('3. 有 marketplace + query match → 出结果 + 安装按钮可见', async ({ page }) => {
    await setupSettingsSkills(page, {
      marketplaces: [{ id: 'm1', name: 'mp', url: 'x', plugin_count: 1, catalog_json: { plugins: [MP_PLUGIN] }, last_fetched_at: null, created_by: 'u', created_at: '' }],
      searchData: [MP_PLUGIN],
    });
    await page.fill('input[placeholder*="搜索技能名"]', 'demo');
    await page.click('button:has-text("搜索")');
    await expect(
      page.locator('[data-testid="skills-search-empty"]')
    ).toHaveCount(0);
    const installBtn = page.locator(
      `[data-testid="skill-search-install-marketplace-${MP_PLUGIN.name}"]`
    );
    await expect(installBtn).toBeVisible();
    await expect(installBtn).toContainText('安装');
  });

  test('4. 移动 viewport: empty state 文案 + 链接可见,无溢出', async ({ page, browserName }) => {
    test.skip(browserName !== 'webkit', 'mobile-only check on mobile-safari project');
    await page.setViewportSize({ width: 390, height: 844 });
    await setupSettingsSkills(page, { marketplaces: [], searchData: [] });
    await page.fill('input[placeholder*="搜索技能名"]', 'mobile-test');
    await page.click('button:has-text("搜索")');
    const empty = page.locator('[data-testid="skills-search-empty"]');
    await expect(empty).toBeVisible({ timeout: 10000 });
    const link = page.locator('[data-testid="skills-search-empty-register-link"]');
    await expect(link).toBeVisible();
    // 链接 hit area 不为 0
    const box = await link.boundingBox();
    expect(box).toBeTruthy();
    expect(box!.width).toBeGreaterThan(0);
  });
});
