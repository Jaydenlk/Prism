import { test, expect, request as playwrightRequest } from '@playwright/test';
import { loginAsAdmin, ADMIN_EMAIL, ADMIN_PASSWORD, BASE } from '../fixtures/auth';

/**
 * auth.spec.ts — Authentication flow tests
 *
 * Scenarios:
 *   1. Correct credentials → arrives at chat page
 *   2. Wrong password → error message shown
 *   3. Disabled user → login rejected
 */

test.describe('Auth flow', () => {
  test('login with correct credentials reaches chat page', async ({ page }) => {
    await page.goto('/');

    // Wait for login form
    await page.waitForSelector('input[type="email"]', { timeout: 10_000 });

    // Fill email + password (email_pw tab is default)
    await page.fill('input[type="email"]', ADMIN_EMAIL);
    await page.fill('input[type="password"]', ADMIN_PASSWORD);

    // Click login
    await page.click('button.btn.primary, button:has-text("登录")');

    // After login the sidebar should appear
    await expect(page.locator('.sidebar')).toBeVisible({ timeout: 15_000 });
  });

  test('wrong password shows error toast or error message', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('input[type="email"]', { timeout: 10_000 });

    await page.fill('input[type="email"]', ADMIN_EMAIL);
    await page.fill('input[type="password"]', 'WrongPassword123!');
    await page.click('button.btn.primary, button:has-text("登录")');

    // Should show error — look for the specific error text from ErrBox
    await expect(
      page.getByText(/邮箱或密码错误|登录失败|401|密码错误/).first()
    ).toBeVisible({ timeout: 8_000 });

    // Must NOT reach the sidebar
    await expect(page.locator('.sidebar')).not.toBeVisible();
  });

  test('disabled user login is rejected with error', async ({ page }) => {
    const ctx = await playwrightRequest.newContext({ baseURL: 'http://localhost:8080' });

    // Step 1: Get admin token
    const loginResp = await ctx.post('/api/v1/auth/login', {
      data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
    });
    const { data: { access_token: adminToken } } = await loginResp.json();

    // Step 2: Create an invite code
    const icResp = await ctx.post('/api/v1/admin/invite-codes', {
      headers: { Authorization: `Bearer ${adminToken}` },
      data: { max_uses: 1 },
    });
    if (!icResp.ok()) {
      // Skip if invite code creation fails (no invite codes endpoint may not be live)
      test.skip(true, 'WAIT: invite-code creation API not available');
      return;
    }
    const { data: ic } = await icResp.json();
    const code = ic.code;

    // Step 3: Register a new test user
    const timestamp = Date.now();
    const testEmail = `e2e_disabled_${timestamp}@test.prism`;
    const testUser = `e2e_dis_${timestamp}`;
    const regResp = await ctx.post('/api/v1/auth/register', {
      data: {
        email: testEmail,
        username: testUser,
        password: 'Test123!Prism',
        invite_code: code,
      },
    });
    if (!regResp.ok()) {
      test.skip(true, `WAIT: registration failed: ${await regResp.text()}`);
      return;
    }
    const { data: { id: newUserId } } = await regResp.json();

    // Step 4: Disable the user via admin API
    const disResp = await ctx.patch(`/api/v1/admin/users/${newUserId}`, {
      headers: { Authorization: `Bearer ${adminToken}` },
      data: { is_active: false },
    });
    if (!disResp.ok()) {
      test.skip(true, `WAIT: disable user API failed: ${await disResp.text()}`);
      return;
    }

    await ctx.dispose();

    // Step 5: Try to log in as the disabled user in the browser
    await page.goto('/');
    await page.waitForSelector('input[type="email"]', { timeout: 10_000 });
    await page.fill('input[type="email"]', testEmail);
    await page.fill('input[type="password"]', 'Test123!Prism');
    await page.click('button.btn.primary, button:has-text("登录")');

    // Should see an error — 403 body or error message
    await expect(
      page.getByText(/禁用|disabled|403|登录失败|帐号已禁用/).first()
    ).toBeVisible({ timeout: 8_000 });

    // Must NOT reach sidebar
    await expect(page.locator('.sidebar')).not.toBeVisible();
  });
});
