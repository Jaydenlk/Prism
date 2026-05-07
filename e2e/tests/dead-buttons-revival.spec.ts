/**
 * E2E: 复活用户报告的死按钮 + 主题切换持久化
 *
 * 用户硬投诉：
 *   1) Composer 左下角 3 按钮（附件/技能/MCP）— 之前完全无 onClick
 *   2) 消息气泡 3 按钮（复制/再试/分叉）— 之前完全无 onClick
 *   3) 亮/暗主题切换 — 切了刷新就回去（HTML 硬编码 + localStorage 未在 boot 应用）
 *
 * 4 个 viewport-shared scenarios + 2 mobile-specific = 共测 10 effective tests
 */
import { test, expect, devices } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD } from "../fixtures/auth";

const VIEWPORTS = [
  { name: "desktop-chromium", viewport: { width: 1280, height: 720 } },
  { name: "mobile-safari", ...devices["iPhone 13"] },
];

async function login(page: any) {
  await page.goto("/Prism.html");
  await page.locator('input[type="email"]').first().fill(ADMIN_EMAIL);
  await page.locator('input[type="password"]').first().fill(ADMIN_PASSWORD);
  await page.locator('button.btn.primary').first().click();
  await expect(
    page.locator('button.btn.primary:has-text("新对话")').first()
  ).toBeVisible({ timeout: 8_000 });
}

for (const cfg of VIEWPORTS) {
  test.describe(`dead-buttons-revival @${cfg.name}`, () => {
    test.use({ viewport: cfg.viewport });

    test("theme persists across reload (boot hydration script)", async ({ page, context }) => {
      // The bug the user reported: <html data-theme="light"> hardcoded → after
      // toggling dark and reloading, the page reverted to light. The fix is a
      // boot-time script that reads localStorage before React mounts.
      // We test that script directly by setting localStorage and reloading.
      // Start fresh: prior tests may have left prism_theme=dark in storage.
      await page.goto("/Prism.html");
      await page.evaluate(() => localStorage.removeItem("prism_theme"));
      await page.reload();
      await expect(page.locator("html")).toHaveAttribute("data-theme", "light");

      await page.evaluate(() => localStorage.setItem("prism_theme", "dark"));
      await page.reload();
      await expect(page.locator("html")).toHaveAttribute("data-theme", "dark", { timeout: 3_000 });

      await page.evaluate(() => localStorage.setItem("prism_theme", "light"));
      await page.reload();
      await expect(page.locator("html")).toHaveAttribute("data-theme", "light", { timeout: 3_000 });

      // Bad value falls back gracefully — must not crash, html stays one of the two
      await page.evaluate(() => localStorage.setItem("prism_theme", "garbage"));
      await page.reload();
      const finalTheme = await page.locator("html").getAttribute("data-theme");
      expect(["light", "dark"]).toContain(finalTheme);
    });

    test("composer 技能 button navigates to skills page", async ({ page }) => {
      await login(page);
      await page.locator('button.btn.primary:has-text("新对话")').first().click();
      // Composer button by title
      const skillBtn = page.locator('.composer .icon-btn[title*="技能"]').first();
      await expect(skillBtn).toBeVisible({ timeout: 8_000 });
      await skillBtn.click();
      // Skills page renders the section title or a recognizable element
      await expect(
        page.locator(':text("技能"), :text("Skills")').first()
      ).toBeVisible({ timeout: 5_000 });
      // Composer no longer rendered (we're not in chat any more)
      await expect(page.locator('.composer')).toHaveCount(0);
    });

    test("composer MCP button navigates to MCP page", async ({ page }) => {
      await login(page);
      await page.locator('button.btn.primary:has-text("新对话")').first().click();
      const mcpBtn = page.locator('.composer .icon-btn[title*="MCP"]').first();
      await expect(mcpBtn).toBeVisible({ timeout: 8_000 });
      await mcpBtn.click();
      // MyMcpPage renders title containing MCP
      await expect(
        page.locator(':text("我的 MCP"), :text("MCP")').first()
      ).toBeVisible({ timeout: 5_000 });
    });

    test("composer attach button shows informational toast", async ({ page }) => {
      await login(page);
      await page.locator('button.btn.primary:has-text("新对话")').first().click();
      const attachBtn = page.locator('.composer .icon-btn[title*="附件"]').first();
      await expect(attachBtn).toBeVisible({ timeout: 8_000 });
      await attachBtn.click();
      // Toast appears
      await expect(
        page.locator(':text("附件功能开发中"), :text("附件"), .toast').first()
      ).toBeVisible({ timeout: 3_000 });
    });

    test("message bubble fork button creates new session", async ({ page }) => {
      await login(page);
      await page.locator('button.btn.primary:has-text("新对话")').first().click();
      const composer = page.locator('.composer-wrap textarea').first();
      await composer.fill("说一句话作为测试");
      await composer.press("Enter");
      // Wait for agent reply complete
      await expect(async () => {
        const lastBody = await page.locator(".agent-msg .body").last().textContent();
        expect((lastBody ?? "").length).toBeGreaterThan(10);
        const carets = await page.locator(".agent-msg .caret").count();
        expect(carets).toBe(0);
      }).toPass({ timeout: 240_000, intervals: [3_000, 5_000] });

      // Fork button on the agent message
      const forkBtn = page.locator('.agent-msg').last().locator('.icon-btn[title*="分叉"]').first();
      await expect(forkBtn).toBeVisible({ timeout: 5_000 });
      await forkBtn.click();
      await expect(
        page.locator(':text("已创建分叉会话")').first()
      ).toBeVisible({ timeout: 5_000 });
    });
  });
}
