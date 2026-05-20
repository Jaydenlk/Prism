import { test, expect } from '@playwright/test';

test.describe('Poco Login Flow Tests', () => {

  test('[Desktop] Login page loads correctly', async ({ page }) => {
    await page.goto('http://localhost:3100/en/auth/login', { waitUntil: 'networkidle' });
    
    // Verify page title
    const title = await page.title();
    expect(title).toBe('Poco');
    
    // Take screenshot
    await page.screenshot({ path: 'poco-login-form.png' });
    
    // Check for login form elements
    const usernameInput = await page.locator('input[placeholder*="手机号"]').count();
    const passwordInput = await page.locator('input[type="password"]').count();
    const loginButton = await page.locator('button:has-text("登录")').count();
    
    console.log('Username input:', usernameInput);
    console.log('Password input:', passwordInput);
    console.log('Login button:', loginButton);
    
    expect(usernameInput).toBeGreaterThan(0);
    expect(passwordInput).toBeGreaterThan(0);
    expect(loginButton).toBeGreaterThan(0);
  });

  test('[Desktop] Test login with invalid credentials', async ({ page }) => {
    await page.goto('http://localhost:3100/en/auth/login', { waitUntil: 'networkidle' });
    
    // Fill form with invalid credentials
    await page.locator('input[placeholder*="手机号"]').fill('testuser');
    await page.locator('input[type="password"]').fill('wrongpassword');
    
    // Click login button
    await page.locator('button:has-text("登录")').click();
    
    // Wait for response
    await page.waitForTimeout(1000);
    
    // Take screenshot to see error
    await page.screenshot({ path: 'poco-login-error.png' });
    
    // Check for error message
    const errorMessage = await page.locator('[role="alert"], .error, .text-red-600').innerText().catch(() => '');
    console.log('Error message:', errorMessage);
  });

  test('[Mobile] Login page on mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    
    await page.goto('http://localhost:3100/en/auth/login', { waitUntil: 'networkidle' });
    
    await page.screenshot({ path: 'poco-mobile-login.png' });
    
    // Verify form elements exist on mobile
    const usernameInput = await page.locator('input[placeholder*="手机号"]').count();
    expect(usernameInput).toBeGreaterThan(0);
    
    // Check no horizontal scroll needed
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);
  });

  test('[Desktop] Check language support', async ({ page }) => {
    await page.goto('http://localhost:3100/en/auth/login', { waitUntil: 'networkidle' });
    
    const pageText = await page.locator('body').innerText();
    
    // Check for Chinese text (if default language is Chinese)
    const hasChinese = pageText.includes('登录') || pageText.includes('密码');
    console.log('Has Chinese text:', hasChinese);
    
    // Check if there's language switcher
    const langSwitcher = await page.locator('[class*="lang"], [aria-label*="language" i]').count();
    console.log('Language switcher found:', langSwitcher > 0);
  });

  test('[Desktop] Verify API 400 vs 401 error codes', async ({ page }) => {
    const responses: { url: string, status: number, code?: number }[] = [];
    
    page.on('response', async resp => {
      if (resp.url().includes('/api/v1/')) {
        let code: number | undefined;
        try {
          const json = await resp.json();
          code = json.code;
        } catch (e) {}
        responses.push({ url: resp.url(), status: resp.status(), code });
      }
    });
    
    await page.goto('http://localhost:3100/en/auth/login', { waitUntil: 'networkidle' });
    
    console.log('API responses without auth:', responses);
    
    // Check if 400 responses have correct error code
    const badAuthResponses = responses.filter(r => r.status === 400 && r.code === 40100);
    console.log('Auth required 400 errors:', badAuthResponses.length);
    
    // BUG: Should return 401 Unauthorized, not 400 Bad Request
    const shouldBe401 = responses.some(r => r.status === 400 && r.code === 40100);
    if (shouldBe401) {
      console.log('BUG FOUND: Authentication errors return 400 instead of 401');
    }
  });
});
