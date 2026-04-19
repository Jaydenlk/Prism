import { test, expect, request as playwrightRequest } from '@playwright/test';
import { loginAsAdmin, ADMIN_EMAIL, ADMIN_PASSWORD } from '../fixtures/auth';

async function fetchAdminToken(): Promise<string> {
  // Inline to sidestep a pre-existing bug in getAdminToken() where a leading-slash
  // path discards the /api/v1 prefix of baseURL (Playwright treats it as absolute).
  const ctx = await playwrightRequest.newContext({ baseURL: 'http://localhost:8080' });
  const resp = await ctx.post('/api/v1/auth/login', {
    data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
  });
  if (!resp.ok()) throw new Error(`login ${resp.status()}: ${await resp.text()}`);
  const body = await resp.json();
  await ctx.dispose();
  return body.data.access_token;
}

/**
 * marketplace.spec.ts — DOC-SK R1: Skills Marketplace (4th install channel).
 *
 * Contract (Phase 1 Task 6 UI + Task 3/4 backend):
 *   data-testid="skill-install-tab-marketplace"    → 4th tab next to local/github/custom_md
 *   data-testid="skill-install-panel-marketplace"  → tab panel
 *   data-testid="marketplace-url-input"            → .claude-plugin/marketplace.json URL input
 *   data-testid="marketplace-name-input"           → display-name input
 *   data-testid="marketplace-add-submit"           → POST /api/v1/marketplaces
 *   data-testid="marketplace-list-item"            → one entry per registered marketplace
 *   data-testid="marketplace-badge"                → badge on installed skill row whose marketplace_id is non-null
 *
 * Backend contract per spec §5.1 + advisor-confirmed Claude Code format
 * (https://code.claude.com/docs/en/plugin-marketplaces):
 *   POST /api/v1/marketplaces   { url, name }       → 201 { id, name, url, ... }
 *   GET  /api/v1/marketplaces                       → list of registered marketplaces
 *   DELETE /api/v1/marketplaces/{id}                → 204
 *   POST /api/v1/marketplaces/{id}/sync             → 200 (re-fetch catalog)
 */

async function navigateToSkills(page: any) {
  const skillsNav = page.locator('.nav-item').filter({ hasText: '技能市场' });
  await expect(skillsNav.first()).toBeVisible({ timeout: 8_000 });
  await skillsNav.first().click();
}

test.describe('SkillsPage Marketplace tab (DOC-SK R1)', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test('admin can register a marketplace URL and see it in the list', async ({ page }) => {
    await navigateToSkills(page);

    // 4th install tab — does not exist in current main tree
    await page.locator('[data-testid="skill-install-tab-marketplace"]').click();
    const panel = page.locator('[data-testid="skill-install-panel-marketplace"]');
    await expect(panel).toBeVisible({ timeout: 5_000 });

    // Unique URL per run so repeated test runs do not collide on unique constraint
    const uniq = Date.now();
    const url = `https://example.test/mkt-${uniq}/.claude-plugin/marketplace.json`;
    const name = `e2e-mkt-${uniq}`;

    await panel.locator('[data-testid="marketplace-url-input"]').fill(url);
    await panel.locator('[data-testid="marketplace-name-input"]').fill(name);
    await panel.locator('[data-testid="marketplace-add-submit"]').click();

    // List updates with the new entry
    const listItem = page.locator('[data-testid="marketplace-list-item"]').filter({ hasText: name });
    await expect(listItem).toBeVisible({ timeout: 8_000 });
  });

  test('marketplace-sourced skill install is tagged with marketplace_id and shows badge', async ({ page, request }) => {
    // Pre-seed via API: register a marketplace, then install a skill flagged as source=marketplace
    const accessToken = await fetchAdminToken();
    const auth = { Authorization: `Bearer ${accessToken}` };

    const uniq = Date.now();
    const mktUrl = `https://example.test/mkt-badge-${uniq}/.claude-plugin/marketplace.json`;
    const mktName = `e2e-badge-${uniq}`;

    // Register marketplace — endpoint does not exist yet (Task 4)
    const addResp = await request.post('http://localhost:8080/api/v1/marketplaces', {
      headers: auth,
      data: { url: mktUrl, name: mktName },
    });
    expect(addResp.ok()).toBeTruthy();
    const addBody = await addResp.json();
    const marketplaceId = addBody.data?.id ?? addBody.id;
    expect(marketplaceId).toBeTruthy();

    // Install a skill claiming marketplace source. skill_installs.marketplace_id must
    // be persisted (FK added in M1, Task 3) and returned on /skills/installed.
    const installResp = await request.post('http://localhost:8080/api/v1/skills/install', {
      headers: auth,
      data: {
        source: 'marketplace',
        marketplace_id: marketplaceId,
        plugin_name: `mkt-plugin-${uniq}`,
        // v1: plugin=single skill wrapper; backend resolves catalog entry → writes SKILL.md
        content_base64: Buffer.from(
          `---\nname: mkt-plugin-${uniq}\nversion: 1.0.0\ndescription: Installed via marketplace source (e2e)\nauthor: e2e\n---\n# mkt\n`
        ).toString('base64'),
      },
    });
    expect(installResp.ok()).toBeTruthy();

    // Navigate to Installed list and verify badge
    await navigateToSkills(page);
    const installedTab = page.locator('button:has-text("已安装"), .tab:has-text("已安装")').first();
    if (await installedTab.count() > 0) {
      await installedTab.click();
    }

    const badge = page.locator('[data-testid="marketplace-badge"]').first();
    await expect(badge).toBeVisible({ timeout: 8_000 });
  });
});
