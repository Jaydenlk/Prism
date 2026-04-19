import { Page, request as playwrightRequest } from '@playwright/test';

const BASE = 'http://localhost:8080/api/v1';
const ADMIN_EMAIL = 'admin@prism.dev';
const ADMIN_PASSWORD = 'PrismAdmin!2026';

export interface AdminSession {
  accessToken: string;
  userId: string;
}

/**
 * Obtain a fresh admin access token via the REST API (no browser needed).
 * Response envelope: { data: { access_token, ... }, error: null }
 */
export async function getAdminToken(): Promise<AdminSession> {
  const ctx = await playwrightRequest.newContext({ baseURL: BASE });
  const resp = await ctx.post('/auth/login', {
    data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
  });
  if (!resp.ok()) {
    const body = await resp.text();
    throw new Error(`Admin login failed ${resp.status()}: ${body}`);
  }
  const envelope = await resp.json();
  const { access_token } = envelope.data;
  // Get userId from /auth/me
  const me = await ctx.get('/auth/me', {
    headers: { Authorization: `Bearer ${access_token}` },
  });
  const meEnv = await me.json();
  await ctx.dispose();
  return { accessToken: access_token, userId: meEnv.data.id };
}

/**
 * Log in as admin via the browser UI and wait for the chat page to load.
 * If the sidebar is already visible (already logged in), skips login form.
 */
export async function loginAsAdmin(page: Page): Promise<void> {
  await page.goto('/');

  // If the sidebar is already visible, we're already logged in
  try {
    await page.waitForSelector('.sidebar', { timeout: 3_000 });
    return; // already logged in
  } catch {
    // Not logged in yet — proceed with login
  }

  // Wait for login form to appear
  await page.waitForSelector('input[type="email"]', { timeout: 10_000 });

  // Fill credentials
  await page.fill('input[type="email"]', ADMIN_EMAIL);
  await page.fill('input[type="password"]', ADMIN_PASSWORD);

  // Click the primary login button
  await page.click('button.btn.primary, button:has-text("登录")');

  // Wait until the sidebar appears (login complete)
  await page.waitForSelector('.sidebar', { timeout: 15_000 });
}

/**
 * Set sessionStorage token directly — faster alternative to UI login.
 * Works when the frontend stores the token under "prism_access_token".
 */
export async function setAdminTokenInStorage(page: Page, token: string): Promise<void> {
  await page.goto('/');
  await page.evaluate((t: string) => {
    sessionStorage.setItem('prism_access_token', t);
    localStorage.setItem('prism_access_token', t);
  }, token);
  await page.reload();
}

export { ADMIN_EMAIL, ADMIN_PASSWORD, BASE };
