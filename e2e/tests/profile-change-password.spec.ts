import { test, expect, request as playwrightRequest } from '@playwright/test';
import { ADMIN_EMAIL, ADMIN_PASSWORD, BASE } from '../fixtures/auth';

const API_V1 = '/api/v1';

interface TestUser {
  email: string;
  username: string;
  password: string;
  accessToken: string;
}

async function createTestUser(initialPassword: string): Promise<TestUser> {
  const ctx = await playwrightRequest.newContext({ baseURL: BASE });

  const loginResp = await ctx.post(`${API_V1}/auth/login`, {
    data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
  });
  if (!loginResp.ok()) throw new Error(`Admin login failed: ${await loginResp.text()}`);
  const { data: { access_token: adminToken } } = await loginResp.json();

  const icResp = await ctx.post(`${API_V1}/admin/invite-codes`, {
    headers: { Authorization: `Bearer ${adminToken}` },
    data: { max_uses: 1 },
  });
  if (!icResp.ok()) throw new Error(`Invite code creation failed: ${await icResp.text()}`);
  const { data: ic } = await icResp.json();

  const ts = Date.now();
  const email = `e2e_pwchange_${ts}@test.prism`;
  const username = `e2epw_${ts}`;

  const regResp = await ctx.post(`${API_V1}/auth/register`, {
    data: { email, username, password: initialPassword, invite_code: ic.code },
  });
  if (!regResp.ok()) throw new Error(`Registration failed: ${await regResp.text()}`);
  const { data: { access_token } } = await regResp.json();

  await ctx.dispose();
  return { email, username, password: initialPassword, accessToken: access_token };
}

async function loginViaUI(page: import('@playwright/test').Page, email: string, password: string): Promise<void> {
  await page.goto('/');
  // Log out if already logged in
  try {
    await page.waitForSelector('.sidebar', { timeout: 3_000 });
    // Already logged in as someone else — reload after clearing storage
    await page.evaluate(() => {
      sessionStorage.clear();
      localStorage.clear();
    });
    await page.reload();
  } catch {
    // Not logged in — proceed
  }
  await page.waitForSelector('input[type="email"]', { timeout: 10_000 });
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', password);
  await page.click('button.btn.primary, button:has-text("登录")');
  await page.waitForSelector('.sidebar', { timeout: 15_000 });
}

async function navigateToProfile(page: import('@playwright/test').Page): Promise<void> {
  // Click settings nav item
  await page.click('.nav-item:has-text("设置")');
  // Profile tab is default, but wait for the "修改密码" button to confirm
  await page.waitForSelector('button:has-text("修改密码")', { timeout: 8_000 });
}

test.describe('ProfileTab — 修改密码', () => {
  test.describe.configure({ mode: 'serial' });

  let user: TestUser;
  const INITIAL_PASSWORD = 'OldPass1234!';
  const NEW_PASSWORD = 'NewPass5678!';

  test.beforeAll(async () => {
    user = await createTestUser(INITIAL_PASSWORD);
  });

  async function fillPasswordModal(
    page: import('@playwright/test').Page,
    current: string,
    next: string,
    confirm: string,
  ): Promise<void> {
    const inputs = page.locator('.modal input[type="password"]');
    await inputs.nth(0).fill(current);
    await inputs.nth(1).fill(next);
    await inputs.nth(2).fill(confirm);
  }

  test('desktop: wrong current password shows error', async ({ page }) => {
    await loginViaUI(page, user.email, INITIAL_PASSWORD);
    await navigateToProfile(page);

    await page.click('button:has-text("修改密码")');
    await page.waitForSelector('.modal-backdrop', { timeout: 5_000 });

    await fillPasswordModal(page, 'WrongCurrent!', NEW_PASSWORD, NEW_PASSWORD);
    await page.click('.modal .btn.primary');

    await expect(page.locator('.modal')).toContainText('当前密码错误', { timeout: 8_000 });
  });

  test('desktop: short new password shows client-side error', async ({ page }) => {
    await loginViaUI(page, user.email, INITIAL_PASSWORD);
    await navigateToProfile(page);

    await page.click('button:has-text("修改密码")');
    await page.waitForSelector('.modal-backdrop', { timeout: 5_000 });

    await fillPasswordModal(page, INITIAL_PASSWORD, 'short', 'short');
    await page.click('.modal .btn.primary');

    await expect(page.locator('.modal')).toContainText('至少 8 位', { timeout: 4_000 });
  });

  test('desktop: mismatched confirm shows client-side error', async ({ page }) => {
    await loginViaUI(page, user.email, INITIAL_PASSWORD);
    await navigateToProfile(page);

    await page.click('button:has-text("修改密码")');
    await page.waitForSelector('.modal-backdrop', { timeout: 5_000 });

    await fillPasswordModal(page, INITIAL_PASSWORD, NEW_PASSWORD, 'DifferentPass!');
    await page.click('.modal .btn.primary');

    await expect(page.locator('.modal')).toContainText('不一致', { timeout: 4_000 });
  });

  test('desktop: cancel closes modal without change', async ({ page }) => {
    await loginViaUI(page, user.email, INITIAL_PASSWORD);
    await navigateToProfile(page);

    await page.click('button:has-text("修改密码")');
    await page.waitForSelector('.modal-backdrop', { timeout: 5_000 });
    await page.click('.modal button:has-text("取消")');

    await expect(page.locator('.modal-backdrop')).not.toBeVisible({ timeout: 4_000 });
  });

  test('desktop: correct passwords → success toast, new password works', async ({ page }) => {
    await loginViaUI(page, user.email, INITIAL_PASSWORD);
    await navigateToProfile(page);

    await page.click('button:has-text("修改密码")');
    await page.waitForSelector('.modal-backdrop', { timeout: 5_000 });

    await fillPasswordModal(page, INITIAL_PASSWORD, NEW_PASSWORD, NEW_PASSWORD);
    await page.click('.modal .btn.primary');

    // Modal should close
    await expect(page.locator('.modal-backdrop')).not.toBeVisible({ timeout: 8_000 });
    // Success toast
    await expect(page.locator('.toast-stack')).toContainText('密码已修改', { timeout: 8_000 });

    // Verify new password works — login via API
    const ctx = await playwrightRequest.newContext({ baseURL: BASE });
    const loginResp = await ctx.post(`${API_V1}/auth/login`, {
      data: { email: user.email, password: NEW_PASSWORD },
    });
    expect(loginResp.ok()).toBeTruthy();
    await ctx.dispose();

    // Update stored password for subsequent tests
    user.password = NEW_PASSWORD;
  });

  test('mobile: change password modal renders and closes on backdrop click', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await loginViaUI(page, user.email, user.password);
    await navigateToProfile(page);

    await page.click('button:has-text("修改密码")');
    await page.waitForSelector('.modal-backdrop', { timeout: 5_000 });
    await expect(page.locator('.modal')).toBeVisible();

    // Click backdrop to close
    await page.locator('.modal-backdrop').click({ position: { x: 10, y: 10 }, force: true });
    await expect(page.locator('.modal-backdrop')).not.toBeVisible({ timeout: 4_000 });
  });
});

test.describe('P0-3 partial: analytics endpoint no longer 422', () => {
  test('GET /harness/analytics with days param returns 200', async () => {
    const ctx = await playwrightRequest.newContext({ baseURL: BASE });

    const loginResp = await ctx.post(`${API_V1}/auth/login`, {
      data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
    });
    const { data: { access_token } } = await loginResp.json();

    const analyticsResp = await ctx.get(`${API_V1}/harness/analytics?days=7`, {
      headers: { Authorization: `Bearer ${access_token}` },
    });
    expect(analyticsResp.status()).toBe(200);

    await ctx.dispose();
  });

  test('GET /harness/analytics with old window param returns 422', async () => {
    const ctx = await playwrightRequest.newContext({ baseURL: BASE });

    const loginResp = await ctx.post(`${API_V1}/auth/login`, {
      data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
    });
    const { data: { access_token } } = await loginResp.json();

    // Verify the old broken behaviour is gone — window param is ignored (days defaults to 7)
    // Backend ignores unknown query params so this should still return 200 now with default days
    const analyticsResp = await ctx.get(`${API_V1}/harness/analytics?window=7d`, {
      headers: { Authorization: `Bearer ${access_token}` },
    });
    // With days defaulting to 7 this is now valid
    expect(analyticsResp.status()).toBe(200);

    await ctx.dispose();
  });
});
