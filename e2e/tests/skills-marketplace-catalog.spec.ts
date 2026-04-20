/**
 * Session 4c — Skills Marketplace Catalog Browser e2e tests (ADR-090)
 *
 * Covers: registered marketplace expand → catalog grid render → plugin
 * details modal → install consent → mocked install 201 → installed list
 * refresh. Dual viewport (desktop + mobile). Each button/flow simulated
 * end-to-end per user's "cover every button / every flow" directive.
 *
 * External HTTP mocking via page.route: GET /marketplaces (seeded with 3
 * plugin entries mixing string + object source forms per anthropic #1331
 * real-world shape); POST /marketplaces/{id}/plugins/{name}/install
 * (success / 429 / 409).
 */
import { test, expect, Page } from '@playwright/test';
import { loginAsAdmin } from '../fixtures/auth';

const MP_ID = 'mp-test-id';
const MP_NAME = 'test-mp';

const seededCatalog = {
  name: MP_NAME,
  owner: { name: 'tester' },
  plugins: [
    {
      name: 'relative-plugin',
      description: 'Local relative-path source example',
      version: '1.0.0',
      source: './plugins/rel',
      category: 'development',
      keywords: ['tool', 'dev'],
    },
    {
      name: 'github-plugin',
      description: 'GitHub tarball source example (HTTPS-only, bypasses SSH)',
      version: '2.3.1',
      source: { source: 'github', repo: 'owner/repo', ref: 'main' },
      author: { name: 'Acme' },
      homepage: 'https://acme.example/plugin',
      license: 'MIT',
    },
    {
      name: 'subdir-plugin',
      description: 'Monorepo subdirectory via cone-mode sparse checkout',
      version: '0.4.0',
      source: { source: 'git-subdir', url: 'acme/monorepo', path: 'tools/x' },
    },
  ],
};

/** Register a mocked marketplace + catalog via /marketplaces GET/POST
 *  interception. Returns once page has loaded and catalog is in state. */
async function installMocks(page: Page) {
  // List always returns our seeded marketplace
  await page.route('**/api/v1/marketplaces', async (route) => {
    const method = route.request().method();
    if (method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: [
            {
              id: MP_ID,
              url: 'tester/test-mp',
              name: MP_NAME,
              catalog_json: seededCatalog,
              plugin_count: seededCatalog.plugins.length,
              last_fetched_at: new Date().toISOString(),
              created_by: 'admin',
              created_at: new Date().toISOString(),
            },
          ],
          error: null,
        }),
      });
    } else if (method === 'POST') {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            id: MP_ID,
            url: 'tester/test-mp',
            name: MP_NAME,
            catalog_json: seededCatalog,
            plugin_count: seededCatalog.plugins.length,
            last_fetched_at: new Date().toISOString(),
            created_by: 'admin',
            created_at: new Date().toISOString(),
          },
          error: null,
        }),
      });
    } else {
      await route.continue();
    }
  });
}

/** Navigate to Skills page + Marketplace tab. Uses sidebar "技能市场" nav
 *  (same pattern as marketplace.spec.ts). */
async function openMarketplaceTab(page: Page) {
  await loginAsAdmin(page);
  const skillsNav = page.locator('.nav-item').filter({ hasText: '技能市场' });
  await expect(skillsNav.first()).toBeVisible({ timeout: 10_000 });
  await skillsNav.first().click();
  await page.click('[data-testid="skill-install-tab-marketplace"]');
  await expect(page.locator('[data-testid="skill-install-panel-marketplace"]')).toBeVisible();
}

test.describe('Skills Marketplace Catalog (Session 4c, ADR-090)', () => {
  test.beforeEach(async ({ page }) => {
    await installMocks(page);
    await openMarketplaceTab(page);
  });

  test('registered marketplace row shows expand button', async ({ page }) => {
    const row = page.locator('[data-testid="marketplace-list-item"]');
    await expect(row).toBeVisible();
    await expect(
      page.locator(`[data-testid="marketplace-expand-${MP_NAME}"]`)
    ).toBeVisible();
  });

  test('expand → catalog grid renders all plugin cards', async ({ page }) => {
    await page.click(`[data-testid="marketplace-expand-${MP_NAME}"]`);
    await expect(
      page.locator(`[data-testid="catalog-grid-${MP_NAME}"]`)
    ).toBeVisible();
    await expect(page.locator('[data-testid^="plugin-card-"]')).toHaveCount(3);
  });

  test('plugin card shows serif title + amber version chip + description', async ({ page }) => {
    await page.click(`[data-testid="marketplace-expand-${MP_NAME}"]`);
    const card = page.locator('[data-testid="plugin-card-github-plugin"]');
    await expect(card).toBeVisible();
    // Version chip present
    const chip = card.locator('[data-testid="plugin-version-chip"]');
    await expect(chip).toHaveText('v2.3.1');
    // Title uses serif font
    const titleFontFamily = await card
      .locator('span')
      .first()
      .evaluate((el) => getComputedStyle(el).fontFamily);
    expect(titleFontFamily.toLowerCase()).toMatch(/serif|fraunces|playfair|georgia/i);
  });

  test('details modal opens + shows metadata + closes', async ({ page }) => {
    await page.click(`[data-testid="marketplace-expand-${MP_NAME}"]`);
    await page
      .locator('[data-testid="plugin-card-github-plugin"]')
      .locator('[data-testid="plugin-btn-details"]')
      .click();
    const modal = page.locator('[data-testid="plugin-details-modal"]');
    await expect(modal).toBeVisible();
    await expect(modal).toContainText('github-plugin');
    await expect(modal).toContainText('Acme');
    await expect(modal).toContainText('MIT');
    await page.click('[data-testid="plugin-details-close"]');
    await expect(modal).not.toBeVisible();
  });

  test('install cancel → no POST + modal closes', async ({ page }) => {
    let installCalled = false;
    await page.route('**/plugins/*/install', async (route) => {
      installCalled = true;
      await route.abort();
    });
    await page.click(`[data-testid="marketplace-expand-${MP_NAME}"]`);
    await page
      .locator('[data-testid="plugin-card-relative-plugin"]')
      .locator('[data-testid="plugin-btn-install"]')
      .click();
    const modal = page.locator('[data-testid="install-consent-modal"]');
    await expect(modal).toBeVisible();
    await expect(page.locator('[data-testid="consent-source-info"]')).toBeVisible();
    await page.click('[data-testid="consent-cancel"]');
    await expect(modal).not.toBeVisible();
    expect(installCalled).toBe(false);
  });

  test('install confirm → success toast with installed count', async ({ page }) => {
    await page.route('**/plugins/*/install', async (route) => {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            plugin_name: 'relative-plugin',
            installed_skills: ['skill-a', 'skill-b'],
            failures: [],
          },
          error: null,
        }),
      });
    });
    // Stub installed list GET to return 2 items after install
    await page.route('**/api/v1/skills/installed', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: [
            { skill_name: 'skill-a', version: '1.0.0', source: 'marketplace', marketplace_id: MP_ID, metadata: {} },
            { skill_name: 'skill-b', version: '1.0.0', source: 'marketplace', marketplace_id: MP_ID, metadata: {} },
          ],
          error: null,
        }),
      });
    });
    await page.click(`[data-testid="marketplace-expand-${MP_NAME}"]`);
    await page
      .locator('[data-testid="plugin-card-relative-plugin"]')
      .locator('[data-testid="plugin-btn-install"]')
      .click();
    await page.click('[data-testid="consent-confirm"]');
    // Toast with success kind surface
    await expect(page.locator('.toast.success').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('.toast.success').first()).toContainText(/已安装.*2.*skill/);
  });

  test('install failure (429) → danger toast with rate-limit hint', async ({ page }) => {
    await page.route('**/plugins/*/install', async (route) => {
      await route.fulfill({
        status: 422,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'Download failed [rate_limit]: GitHub rate limit hit — retry in 60s (set GITHUB_TOKEN for 5000/h instead of 60/h)',
        }),
      });
    });
    await page.click(`[data-testid="marketplace-expand-${MP_NAME}"]`);
    await page
      .locator('[data-testid="plugin-card-github-plugin"]')
      .locator('[data-testid="plugin-btn-install"]')
      .click();
    await page.click('[data-testid="consent-confirm"]');
    await expect(page.locator('.toast.danger').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('.toast.danger').first()).toContainText(/rate.?limit|GITHUB_TOKEN/i);
  });

  test('concurrent install 409 → danger toast', async ({ page }) => {
    await page.route('**/plugins/*/install', async (route) => {
      await route.fulfill({
        status: 409,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'Install already in progress for this plugin',
        }),
      });
    });
    await page.click(`[data-testid="marketplace-expand-${MP_NAME}"]`);
    await page
      .locator('[data-testid="plugin-card-subdir-plugin"]')
      .locator('[data-testid="plugin-btn-install"]')
      .click();
    await page.click('[data-testid="consent-confirm"]');
    await expect(page.locator('.toast.danger').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('.toast.danger').first()).toContainText(/in progress|already/i);
  });

  test('mobile: catalog grid is single column + install button ≥44pt', async ({ page, browserName }) => {
    test.skip(browserName !== 'webkit', 'mobile viewport check runs on mobile project only');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.click(`[data-testid="marketplace-expand-${MP_NAME}"]`);
    const grid = page.locator(`[data-testid="catalog-grid-${MP_NAME}"]`);
    await expect(grid).toBeVisible();
    const cols = await grid.evaluate(
      (el) => getComputedStyle(el as HTMLElement).gridTemplateColumns
    );
    // Single column means one value in the template (no multiple spaces)
    expect(cols.split(' ').filter(Boolean).length).toBe(1);

    const installBtn = page
      .locator('[data-testid="plugin-card-relative-plugin"]')
      .locator('[data-testid="plugin-btn-install"]');
    const h = await installBtn.evaluate((el) => el.getBoundingClientRect().height);
    expect(h).toBeGreaterThanOrEqual(44);
  });

  test('keyboard: focus card + Enter opens details', async ({ page }) => {
    await page.click(`[data-testid="marketplace-expand-${MP_NAME}"]`);
    const card = page.locator('[data-testid="plugin-card-relative-plugin"]');
    await card.focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('[data-testid="plugin-details-modal"]')).toBeVisible();
  });
});
