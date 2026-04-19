import { test, expect, request as playwrightRequest } from '@playwright/test';
import { loginAsAdmin, ADMIN_EMAIL, ADMIN_PASSWORD } from '../fixtures/auth';

async function fetchAdminToken(): Promise<string> {
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
 * plugin-typed-builder.spec.ts — DOC-SK R2+R5: typed plugin manifest.
 *
 * Contract (Phase 1 Task 5 backend + Task 6 UI):
 *   plugin.yaml gains required `type: tool | agent_strategy | extension | trigger`.
 *   plugins_library gets `plugin_type` and `permissions_json` columns (M2).
 *   PluginBuilder first question asks the type — UI exposes a chip per type.
 *   /plugins/save without explicit `type` stores `plugin_type='tool'` (DB
 *   server_default — per plan Task 5 Step 3 migration spec).
 *
 * data-testid selectors expected post-implementation:
 *   data-testid="plugin-type-chip-tool"
 *   data-testid="plugin-type-chip-agent_strategy"
 *   data-testid="plugin-type-chip-extension"
 *   data-testid="plugin-type-chip-trigger"
 */

async function navigateToPlugins(page: any) {
  const nav = page.locator('.nav-item').filter({ hasText: '插件构建' });
  await expect(nav.first()).toBeVisible({ timeout: 8_000 });
  await nav.first().click();
}

test.describe('PluginsPage typed builder (DOC-SK R2+R5)', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test('plugin builder first step exposes a type picker with 4 chips', async ({ page }) => {
    await navigateToPlugins(page);

    // Start a new plugin build — button or CTA; selector contract:
    //   data-testid="plugin-builder-start"
    const startBtn = page.locator('[data-testid="plugin-builder-start"]');
    await expect(startBtn).toBeVisible({ timeout: 5_000 });
    await startBtn.click();

    // First step is the type picker. All 4 chips must be visible.
    await expect(page.locator('[data-testid="plugin-type-chip-tool"]')).toBeVisible({ timeout: 5_000 });
    await expect(page.locator('[data-testid="plugin-type-chip-agent_strategy"]')).toBeVisible();
    await expect(page.locator('[data-testid="plugin-type-chip-extension"]')).toBeVisible();
    await expect(page.locator('[data-testid="plugin-type-chip-trigger"]')).toBeVisible();
  });

  test('saved plugin without explicit type defaults to plugin_type="tool"', async ({ request }) => {
    // API-level test: POST /plugins/save with no type field in the manifest —
    // backend (Task 5) must store with plugin_type='tool' via Pydantic default /
    // DB server_default. Returned library entry reports the stored type.
    const accessToken = await fetchAdminToken();
    const uniq = Date.now();
    const name = `untyped-plugin-${uniq}`;

    const saveResp = await request.post('http://localhost:8080/api/v1/plugins/save', {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: {
        name,
        version: '1.0.0',
        description: 'untyped manifest — backend should default to tool',
        manifest_yaml: `name: ${name}\nversion: 1.0.0\n# no type: line\n`,
        manifest_json: { name, version: '1.0.0' },
      },
    });
    expect(saveResp.ok()).toBeTruthy();

    // List library entries, find ours, verify plugin_type field exists and == 'tool'
    const listResp = await request.get('http://localhost:8080/api/v1/plugins/library', {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    expect(listResp.ok()).toBeTruthy();
    const body = await listResp.json();
    const entries = (body.data ?? body) as Array<any>;
    const mine = entries.find((e) => e.name === name);
    expect(mine).toBeTruthy();
    expect(mine.plugin_type).toBe('tool');
  });
});
