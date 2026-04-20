import { test, expect } from '@playwright/test';
import { loginAsAdmin } from '../fixtures/auth';

/**
 * plugin-consent-dialog.spec.ts — Session 4a (ADR-087 偏离点 #2/#3/#4).
 *
 * Production happy path — no mocks:
 *   1. User opens PluginsPage and clicks "新建 Plugin"
 *   2. User picks a type chip → `tasks.submit` is fired with session_metadata.plugin_type
 *      + sessionId is created
 *   3. Once a type is picked (even before the builder agent responds), the
 *      "保存到插件库" CTA becomes enabled so the user can skip chat if they
 *      prefer to hand-edit the manifest
 *   4. Clicking that CTA opens the Consent dialog showing type + permissions
 *   5. Allow → save modal opens (existing flow);  Cancel → modal closes, save does not open
 *
 * Contracts (post-impl):
 *   data-testid="plugin-builder-start"           (Session 3, 已有)
 *   data-testid="plugin-type-chip-${t}"          (Session 3, 已有)
 *   data-testid="plugin-open-consent"            (本 session 新增 CTA)
 *   data-testid="plugin-consent-modal"
 *   data-testid="plugin-consent-type-chip"
 *   data-testid="plugin-consent-permissions"
 *   data-testid="plugin-consent-allow"
 *   data-testid="plugin-consent-cancel"
 *   data-testid="plugin-save-modal"              (wrap existing saveModal root)
 */

async function openPluginsPage(page: any) {
  const nav = page.locator('.nav-item').filter({ hasText: '插件构建' });
  await expect(nav.first()).toBeVisible({ timeout: 8_000 });
  await nav.first().click();
}

async function clickStart(page: any) {
  const btn = page.locator('[data-testid="plugin-builder-start"]');
  await expect(btn).toBeVisible({ timeout: 5_000 });
  await btn.evaluate((el: HTMLButtonElement) => el.click());
}

async function pickChipCapturing(page: any, t: string): Promise<() => any> {
  let captured: any = null;
  await page.route('**/api/v1/tasks', async (route: any) => {
    if (captured === null) {
      try {
        captured = await route.request().postDataJSON();
      } catch {
        captured = route.request().postData();
      }
    }
    await route.continue();
  });
  const chip = page.locator(`[data-testid="plugin-type-chip-${t}"]`);
  await expect(chip).toBeVisible({ timeout: 5_000 });
  await chip.evaluate((el: HTMLButtonElement) => el.click());
  return () => captured;
}

async function pickChip(page: any, t: string) {
  const chip = page.locator(`[data-testid="plugin-type-chip-${t}"]`);
  await expect(chip).toBeVisible({ timeout: 5_000 });
  await chip.evaluate((el: HTMLButtonElement) => el.click());
}

async function openConsent(page: any) {
  const cta = page.locator('[data-testid="plugin-open-consent"]');
  await expect(cta).toBeVisible({ timeout: 10_000 });
  await cta.evaluate((el: HTMLButtonElement) => el.click());
}

test.describe('Plugin Consent Dialog (Session 4a)', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  for (const t of ['tool', 'agent_strategy', 'extension', 'trigger'] as const) {
    test(`chip ${t} fires tasks.submit with session_metadata.plugin_type=${t}`, async ({ page }) => {
      await openPluginsPage(page);
      await clickStart(page);
      const getCaptured = await pickChipCapturing(page, t);
      await page.waitForTimeout(2500);
      const captured = getCaptured();
      expect(captured, 'tasks submit payload captured').toBeTruthy();
      expect(captured.session_metadata?.plugin_type).toBe(t);
    });
  }

  test('consent dialog renders type chip + permissions rows + two buttons', async ({ page }) => {
    await openPluginsPage(page);
    await clickStart(page);
    await pickChip(page, 'tool');
    await openConsent(page);

    await expect(page.locator('[data-testid="plugin-consent-modal"]')).toBeVisible({ timeout: 5_000 });
    await expect(page.locator('[data-testid="plugin-consent-type-chip"]')).toContainText('tool');
    await expect(page.locator('[data-testid="plugin-consent-permissions"]')).toBeVisible();
    await expect(page.locator('[data-testid="plugin-consent-allow"]')).toBeVisible();
    await expect(page.locator('[data-testid="plugin-consent-cancel"]')).toBeVisible();
  });

  test('consent allow transitions to save modal', async ({ page }) => {
    await openPluginsPage(page);
    await clickStart(page);
    await pickChip(page, 'tool');
    await openConsent(page);
    await expect(page.locator('[data-testid="plugin-consent-modal"]')).toBeVisible({ timeout: 5_000 });
    await page.locator('[data-testid="plugin-consent-allow"]').evaluate((el: HTMLButtonElement) => el.click());
    await expect(page.locator('[data-testid="plugin-save-modal"]')).toBeVisible({ timeout: 5_000 });
    await expect(page.locator('[data-testid="plugin-consent-modal"]')).not.toBeVisible();
  });

  test('consent cancel closes modal without opening save', async ({ page }) => {
    await openPluginsPage(page);
    await clickStart(page);
    await pickChip(page, 'tool');
    await openConsent(page);
    await expect(page.locator('[data-testid="plugin-consent-modal"]')).toBeVisible({ timeout: 5_000 });
    await page.locator('[data-testid="plugin-consent-cancel"]').evaluate((el: HTMLButtonElement) => el.click());
    await expect(page.locator('[data-testid="plugin-consent-modal"]')).not.toBeVisible();
    await expect(page.locator('[data-testid="plugin-save-modal"]')).not.toBeVisible();
  });

  test('mobile viewport stacks consent buttons vertically', async ({ page, viewport }) => {
    if (!viewport || viewport.width >= 500) {
      test.skip(true, 'only meaningful on mobile viewport');
    }
    await openPluginsPage(page);
    await clickStart(page);
    await pickChip(page, 'tool');
    await openConsent(page);
    await expect(page.locator('[data-testid="plugin-consent-modal"]')).toBeVisible({ timeout: 5_000 });
    const allowBox = await page.locator('[data-testid="plugin-consent-allow"]').boundingBox();
    const cancelBox = await page.locator('[data-testid="plugin-consent-cancel"]').boundingBox();
    expect(allowBox && cancelBox).toBeTruthy();
    expect(Math.abs((allowBox!.y) - (cancelBox!.y))).toBeGreaterThan(5);
  });
});
