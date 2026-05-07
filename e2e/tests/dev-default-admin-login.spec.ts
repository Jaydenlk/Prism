/**
 * E2E: dev mode 下，LoginScreen 渲染"用默认管理员账号登录"一键按钮，
 * 点击后真正完成登录并进入主应用。
 *
 * 真实驱动浏览器双端（desktop + mobile-safari）。
 */
import { test, expect, devices } from "@playwright/test";

const VIEWPORTS = [
  { name: "desktop-chromium", viewport: { width: 1280, height: 720 } },
  { name: "mobile-safari", ...devices["iPhone 13"] },
];

for (const cfg of VIEWPORTS) {
  test.describe(`dev-default-admin-login @${cfg.name}`, () => {
    test.use({ viewport: cfg.viewport });

    test("button renders + click logs in (no manual password)", async ({ page }) => {
      // Fresh state — clear any prior auth cookies
      await page.context().clearCookies();
      await page.goto("/Prism.html");

      // Email/password fields visible (default login mode)
      await expect(page.locator('input[type="email"]').first()).toBeVisible({ timeout: 8_000 });

      // Dev one-click button must be present + show admin@prism.dev
      const devBtn = page.locator('[data-testid="dev-default-admin-login"]');
      await expect(devBtn).toBeVisible({ timeout: 5_000 });
      const btnText = await devBtn.textContent();
      expect(btnText, "Dev button must surface the actual admin email").toContain("admin@prism.dev");

      // Click → should log in and land on the chat app
      await devBtn.click();

      // Login success indicator: "新对话" button visible (only after login).
      // The LoginScreen would still be mounted on failure, so this is sufficient
      // proof the dev one-click triggered a real login.
      await expect(
        page.locator('button.btn.primary:has-text("新对话")').first()
      ).toBeVisible({ timeout: 12_000 });

      // The LoginScreen is unmounted now — confirm the email/password inputs
      // are gone (would still be visible on failed login).
      await expect(page.locator('input[type="email"]')).toHaveCount(0);
    });
  });
}
