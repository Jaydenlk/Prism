import { test, expect } from '@playwright/test';
import { loginAsAdmin } from '../fixtures/auth';

/**
 * im-admin-edit.spec.ts — Session 4b ADR-088 #4 偏离点清零.
 *
 * Production path (no mocks in the UI itself — external Feishu/Slack/Discord
 * API responses are intercepted at route level just to make CI deterministic
 * without real credentials. When admins fill real tokens in /admin.html the
 * exact same code path executes).
 */

async function openImTab(page: any) {
  await page.goto('/admin.html');
  const nav = page.locator('text=IM 频道').first();
  await nav.evaluate((el: HTMLElement) => (el.closest('[class*="nav"]') as HTMLElement | null || el).click());
  await expect(page.locator('[data-testid="im-channel-row-slack"]')).toBeVisible({ timeout: 10_000 });
}

test.describe('Admin IM Channels edit + test-send (Session 4b)', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test('every row has edit + test buttons', async ({ page }) => {
    await openImTab(page);
    for (const ch of ['feishu', 'wecom', 'slack', 'discord']) {
      await expect(page.locator(`[data-testid="im-channel-edit-${ch}"]`)).toBeVisible();
      await expect(page.locator(`[data-testid="im-channel-test-${ch}"]`)).toBeVisible();
    }
  });

  test('edit modal opens + add key/value row + save posts PATCH', async ({ page }) => {
    await openImTab(page);
    await page.locator('[data-testid="im-channel-edit-slack"]').evaluate((el: HTMLButtonElement) => el.click());
    await expect(page.locator('[data-testid="im-channel-edit-modal"]')).toBeVisible({ timeout: 5_000 });

    await page.locator('[data-testid="im-channel-edit-add-row"]').evaluate((el: HTMLButtonElement) => el.click());
    const lastKey = page.locator('[data-testid^="im-channel-edit-row-key-"]').last();
    const lastValue = page.locator('[data-testid^="im-channel-edit-row-value-"]').last();
    await lastKey.fill('bot_token');
    await lastValue.fill('xoxb-test-live-token');

    let patchSent: any = null;
    await page.route('**/api/v1/im/channels/slack', async (route) => {
      if (route.request().method() === 'PATCH') {
        try {
          patchSent = await route.request().postDataJSON();
        } catch {
          patchSent = route.request().postData();
        }
      }
      await route.continue();
    });

    await page.locator('[data-testid="im-channel-edit-save"]').evaluate((el: HTMLButtonElement) => el.click());
    await page.waitForTimeout(1500);

    expect(patchSent).toBeTruthy();
    expect(patchSent.config?.bot_token).toBe('xoxb-test-live-token');
    await expect(page.locator('[data-testid="im-channel-edit-modal"]')).not.toBeVisible();
  });

  test('edit modal cancel closes without posting', async ({ page }) => {
    await openImTab(page);
    await page.locator('[data-testid="im-channel-edit-slack"]').evaluate((el: HTMLButtonElement) => el.click());
    await expect(page.locator('[data-testid="im-channel-edit-modal"]')).toBeVisible();

    let patchCalled = false;
    await page.route('**/api/v1/im/channels/slack', async (route) => {
      if (route.request().method() === 'PATCH') patchCalled = true;
      await route.continue();
    });

    await page.locator('[data-testid="im-channel-edit-cancel"]').evaluate((el: HTMLButtonElement) => el.click());
    await page.waitForTimeout(500);
    expect(patchCalled).toBe(false);
    await expect(page.locator('[data-testid="im-channel-edit-modal"]')).not.toBeVisible();
  });

  test('test-send happy path posts chat_id and shows success toast', async ({ page }) => {
    await openImTab(page);
    await page.locator('[data-testid="im-channel-test-slack"]').evaluate((el: HTMLButtonElement) => el.click());
    await expect(page.locator('[data-testid="im-channel-test-modal"]')).toBeVisible();

    await page.locator('[data-testid="im-channel-test-chat-id"]').fill('C0TEST_MOCKED');

    await page.route('**/api/v1/im/channels/slack/test-send', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: { sent: true, channel: 'slack' }, error: null }),
      });
    });

    await page.locator('[data-testid="im-channel-test-send"]').evaluate((el: HTMLButtonElement) => el.click());
    await expect(page.locator('.toast').filter({ hasText: /成功|sent/i }).first()).toBeVisible({ timeout: 5_000 });
  });

  test('test-send 503 shows failure toast', async ({ page }) => {
    await openImTab(page);
    await page.locator('[data-testid="im-channel-test-slack"]').evaluate((el: HTMLButtonElement) => el.click());
    await expect(page.locator('[data-testid="im-channel-test-modal"]')).toBeVisible();

    await page.locator('[data-testid="im-channel-test-chat-id"]').fill('C0X');

    await page.route('**/api/v1/im/channels/slack/test-send', async (route) => {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: "channel 'slack' not configured" }),
      });
    });

    await page.locator('[data-testid="im-channel-test-send"]').evaluate((el: HTMLButtonElement) => el.click());
    await expect(page.locator('.toast').filter({ hasText: /失败|not configured|发送失败/i }).first()).toBeVisible({ timeout: 5_000 });
  });

  test('test-send cancel closes modal without posting', async ({ page }) => {
    await openImTab(page);
    await page.locator('[data-testid="im-channel-test-slack"]').evaluate((el: HTMLButtonElement) => el.click());
    await expect(page.locator('[data-testid="im-channel-test-modal"]')).toBeVisible();

    let sendCalled = false;
    await page.route('**/api/v1/im/channels/slack/test-send', async (route) => {
      sendCalled = true;
      await route.continue();
    });

    await page.locator('[data-testid="im-channel-test-cancel"]').evaluate((el: HTMLButtonElement) => el.click());
    await expect(page.locator('[data-testid="im-channel-test-modal"]')).not.toBeVisible();
    expect(sendCalled).toBe(false);
  });

  test('sensitive key value renders as password input', async ({ page }) => {
    await openImTab(page);
    await page.locator('[data-testid="im-channel-edit-slack"]').evaluate((el: HTMLButtonElement) => el.click());
    await page.locator('[data-testid="im-channel-edit-add-row"]').evaluate((el: HTMLButtonElement) => el.click());
    const lastKey = page.locator('[data-testid^="im-channel-edit-row-key-"]').last();
    await lastKey.fill('bot_token');
    await lastKey.blur();
    const lastValue = page.locator('[data-testid^="im-channel-edit-row-value-"]').last();
    await expect(lastValue).toHaveAttribute('type', 'password');
  });

  test('mobile viewport stacks edit modal buttons vertically', async ({ page, viewport }) => {
    if (!viewport || viewport.width >= 500) {
      test.skip(true, 'only mobile');
    }
    await openImTab(page);
    await page.locator('[data-testid="im-channel-edit-slack"]').evaluate((el: HTMLButtonElement) => el.click());
    await expect(page.locator('[data-testid="im-channel-edit-modal"]')).toBeVisible();
    const save = await page.locator('[data-testid="im-channel-edit-save"]').boundingBox();
    const cancel = await page.locator('[data-testid="im-channel-edit-cancel"]').boundingBox();
    expect(save && cancel).toBeTruthy();
    expect(Math.abs(save!.y - cancel!.y)).toBeGreaterThan(5);
  });
});
