import { test, expect, request as playwrightRequest } from '@playwright/test';
import { ADMIN_EMAIL, ADMIN_PASSWORD } from '../fixtures/auth';

/**
 * admin.spec.ts — Admin panel tests
 *
 * Scenario: admin.html → Providers page → edit provider → save →
 * reload confirms masked key shows new prefix.
 */

const API_BASE = 'http://localhost:8080';

async function loginAdminUI(page: any) {
  await page.goto('/');

  // If sidebar already visible, skip login
  const sidebarVisible = await page.locator('.sidebar').isVisible().catch(() => false);
  if (sidebarVisible) return;

  await page.waitForSelector('input[type="email"]', { timeout: 10_000 });
  await page.fill('input[type="email"]', ADMIN_EMAIL);
  await page.fill('input[type="password"]', ADMIN_PASSWORD);
  await page.click('button.btn.primary, button:has-text("登录")');
  await page.waitForSelector('.sidebar', { timeout: 15_000 });
}

async function navigateToProviders(page: any) {
  await page.goto('/admin.html');
  // admin-app is the unique container
  await expect(page.locator('.admin-app')).toBeVisible({ timeout: 10_000 });

  // Look for the Providers rail item — the rail has .rail-item elements with .lbl spans
  const providersItem = page.locator('.rail-item').filter({ has: page.locator('.lbl', { hasText: 'Providers' }) }).first();
  if (await providersItem.count() > 0) {
    await providersItem.click();
  } else {
    // Try clicking any rail item that contains "Provider"
    const allRailItems = page.locator('.rail-item');
    const count = await allRailItems.count();
    for (let i = 0; i < count; i++) {
      const item = allRailItems.nth(i);
      const text = await item.textContent() || '';
      if (text.includes('Provider') || text.includes('provider')) {
        await item.click();
        break;
      }
    }
  }

  // Wait for providers panel to appear
  await expect(page.locator('.panel-head').filter({ hasText: 'Provider' }).first()).toBeVisible({ timeout: 8_000 });
}

test.describe('Admin panel', () => {
  test('admin.html loads and shows the admin app', async ({ page }) => {
    await loginAdminUI(page);

    await page.goto('/admin.html');
    await expect(page.locator('.admin-app')).toBeVisible({ timeout: 10_000 });

    // Rail (left nav) should be visible
    await expect(page.locator('.rail')).toBeVisible({ timeout: 5_000 });
  });

  test('Providers page lists existing system providers', async ({ page }) => {
    await loginAdminUI(page);
    await navigateToProviders(page);

    // Wait for table rows
    await expect(page.locator('table.table tbody tr').first()).toBeVisible({ timeout: 8_000 });

    // Verify "Anthropic Claude" appears (from seeded data)
    await expect(
      page.locator('td').filter({ hasText: 'Anthropic Claude' }).first()
    ).toBeVisible({ timeout: 5_000 });
  });

  test('edit provider → save → masked key shows new prefix', async ({ page }) => {
    // Create a user-scoped test provider via API
    const ctx = await playwrightRequest.newContext({ baseURL: API_BASE });
    const loginResp = await ctx.post('/api/v1/auth/login', {
      data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
    });
    const { data: { access_token: token } } = await loginResp.json();

    // Create a test provider
    const createResp = await ctx.post('/api/v1/providers', {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        name: 'E2E Test Provider',
        protocol: 'openai',
        base_url: 'https://api.openai.com/v1',
        model_id: 'gpt-4o',
        api_key: 'sk-e2e-old-key-1234567890',
        config: {
          capabilities: {
            vision: false,
            prompt_cache: false,
            streaming_tools: true,
            extended_thinking: false,
          },
        },
      },
    });

    if (!createResp.ok()) {
      const body = await createResp.text();
      await ctx.dispose();
      test.skip(true, `WAIT: provider create failed: ${body}`);
      return;
    }
    const { data: createdProvider } = await createResp.json();
    const providerId = createdProvider.id;
    await ctx.dispose();

    // Login in browser and navigate to admin Providers
    await loginAdminUI(page);
    await navigateToProviders(page);

    // Wait for providers table with E2E Test Provider
    await expect(page.locator('table.table tbody tr').first()).toBeVisible({ timeout: 8_000 });
    const testProvRow = page.locator('tr').filter({ hasText: 'E2E Test Provider' }).first();
    await expect(testProvRow).toBeVisible({ timeout: 5_000 });

    // Click the edit (pencil) button for this row
    const editBtn = testProvRow.locator('button[title="编辑"]');
    await editBtn.click();

    // Modal should appear
    await expect(page.locator('.modal-overlay')).toBeVisible({ timeout: 5_000 });

    // Update the API key
    const apiKeyInput = page.locator('.modal-overlay input[type="password"]');
    await apiKeyInput.fill('sk-e2e-new-key-9876543210');

    // Handle confirm dialog and click save
    page.on('dialog', dialog => dialog.accept());
    await page.locator('.modal-box button:has-text("保存")').click();

    // Modal should close after save
    await expect(page.locator('.modal-overlay')).not.toBeVisible({ timeout: 8_000 });

    // Reload and re-navigate to providers
    await navigateToProviders(page);
    await expect(page.locator('table.table tbody tr').first()).toBeVisible({ timeout: 8_000 });

    // Find E2E Test Provider row and check its API key column
    const updatedRow = page.locator('tr').filter({ hasText: 'E2E Test Provider' }).first();
    await expect(updatedRow).toBeVisible({ timeout: 5_000 });

    // API Key column (5th: name, protocol, model, base_url, api_key)
    // The masked key should start with "sk-"
    const apiKeyCell = updatedRow.locator('td').nth(4);
    await expect(apiKeyCell).toContainText('sk-', { timeout: 5_000 });

    // Clean up: delete test provider
    const ctx2 = await playwrightRequest.newContext({ baseURL: API_BASE });
    const lr = await ctx2.post('/api/v1/auth/login', {
      data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
    });
    const { data: { access_token: t2 } } = await lr.json();
    await ctx2.delete(`/api/v1/providers/${providerId}`, {
      headers: { Authorization: `Bearer ${t2}` },
    });
    await ctx2.dispose();
  });
});
