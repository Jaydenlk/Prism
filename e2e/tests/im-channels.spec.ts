import { test, expect, request as playwrightRequest } from '@playwright/test';
import { loginAsAdmin, ADMIN_EMAIL, ADMIN_PASSWORD } from '../fixtures/auth';

/**
 * im-channels.spec.ts — DOC-IM2 I4 Admin IM Channels UI.
 *
 * Contract: admin page exposes the four IM channels (feishu / wecom / slack /
 * discord) with their current enabled/configured state + a test-send button.
 *
 * Selector contract (post-impl):
 *   data-testid="im-channel-row-slack"    → Slack row
 *   data-testid="im-channel-row-discord"  → Discord row
 *   data-testid="im-channel-row-feishu"   → Feishu row (existing, now labelled)
 *   data-testid="im-channel-row-wecom"    → WeCom row  (existing, now labelled)
 */

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

test.describe('Admin IM Channels (DOC-IM2)', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test('admin page lists slack + discord rows alongside feishu + wecom', async ({ page }) => {
    await page.goto('/admin.html');

    // admin landing is 总览 (overview); click "IM 频道" nav to open the channels page.
    // admin-body intercepts pointer events, so dispatch a DOM click directly.
    const imNav = page.locator('text=IM 频道').first();
    await imNav.evaluate((el: HTMLElement) => (el.closest('[class*="nav"]') as HTMLElement | null || el).click());

    // IM Channels page with 4 rows now. Slack and Discord are new.
    await expect(page.locator('[data-testid="im-channel-row-feishu"]')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('[data-testid="im-channel-row-wecom"]')).toBeVisible();
    await expect(page.locator('[data-testid="im-channel-row-slack"]')).toBeVisible();
    await expect(page.locator('[data-testid="im-channel-row-discord"]')).toBeVisible();
  });

  test('GET /im/channels returns slack + discord in the enumerated list', async () => {
    const token = await fetchAdminToken();
    const ctx = await playwrightRequest.newContext({ baseURL: 'http://localhost:8080' });
    const resp = await ctx.get('/api/v1/im/channels', {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    const channels = body.data ?? body;
    const names = (Array.isArray(channels) ? channels : [])
      .map((c: any) => c.channel ?? c.name)
      .filter(Boolean);
    await ctx.dispose();
    expect(names).toEqual(expect.arrayContaining(['slack', 'discord']));
  });
});
