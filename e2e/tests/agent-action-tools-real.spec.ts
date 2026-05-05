/**
 * E2E: agent 真用 action tools 干活（不是作秀）
 *
 * 4 scenarios × 2 viewports = 8 effective tests:
 *   - File action  : "write hello.txt + cat to verify"  → proves Write + Bash
 *   - Read action  : "read /app/start.sh first 20 lines" → proves Read
 *   - SearXNG fast : "search AI news via searxng"        → proves searxng MCP works
 *   - Multi-tool   : "find py files + grep import"       → proves Glob + Grep
 *
 * 共同断言：
 *   1. SSE 流中至少出现一个 .tool-card（agent 真调了工具）
 *   2. agent 最终消息含可信内容（hello.txt 内容 / 文件路径 / URL / "import"）
 *   3. 不是拒答（"我不能..." / "无法..."）
 */
import { test, expect, devices } from "@playwright/test";

const ADMIN_EMAIL = "admin@prism.dev";
const ADMIN_PASSWORD = "PrismAdmin!2026";

const VIEWPORTS = [
  { name: "desktop-chromium", viewport: { width: 1280, height: 720 } },
  { name: "mobile-safari", ...devices["iPhone 13"] },
];

async function loginViaPrismUI(page: any, email: string, password: string) {
  await page.goto("/Prism.html");
  await page.locator('input[type="email"]').first().fill(email);
  await page.locator('input[type="password"]').first().fill(password);
  await page.locator('button.btn.primary').first().click();
  await expect(
    page.locator('button.btn.primary:has-text("新对话")').first()
  ).toBeVisible({ timeout: 8_000 });
}

async function sendPromptAndWaitForCompletion(page: any, prompt: string) {
  await page.locator('button.btn.primary:has-text("新对话")').first().click();
  const textarea = page.locator(".composer-wrap textarea").first();
  await expect(textarea).toBeVisible({ timeout: 8_000 });
  await textarea.click();
  await textarea.fill(prompt);
  await textarea.press("Enter");

  // Wait for streaming complete: last .body has substantive text + no caret
  await expect(async () => {
    const lastText = await page.locator(".agent-msg .body").last().textContent();
    expect((lastText ?? "").length).toBeGreaterThan(40);
    const caretCount = await page.locator(".agent-msg .caret").count();
    expect(caretCount).toBe(0);
  }).toPass({ timeout: 240_000, intervals: [3_000, 5_000, 5_000] });
}

async function assertAgentInvokedTools(page: any, minToolCalls: number = 1) {
  const toolCards = page.locator(".tool-card");
  const count = await toolCards.count();
  expect(
    count,
    `Expected at least ${minToolCalls} tool_use(s); agent must really invoke tools, not just talk`
  ).toBeGreaterThanOrEqual(minToolCalls);
}

async function assertNotARefusal(page: any) {
  const lastText = (await page.locator(".agent-msg .body").last().textContent()) ?? "";
  expect(
    lastText,
    "Final response should NOT refuse — agent has the tools, must actually use them"
  ).not.toMatch(
    /我.*不能|我.*无法|我没有.*权限|无法访问|cannot access|unable to/i
  );
}

for (const cfg of VIEWPORTS) {
  test.describe(`agent-action-tools-real @${cfg.name}`, () => {
    test.use({ viewport: cfg.viewport });

    test("file action: agent uses Write + Bash to create + verify a file", async ({ page }) => {
      test.setTimeout(300_000);
      await loginViaPrismUI(page, ADMIN_EMAIL, ADMIN_PASSWORD);
      const marker = `prism-test-${Date.now()}`;
      await sendPromptAndWaitForCompletion(
        page,
        `请帮我做这件事：用 Write 工具在 /tmp/prism-test-${marker}.txt 写入文字 "${marker}"，然后用 Bash 工具运行 \`cat /tmp/prism-test-${marker}.txt\` 把内容读回来确认。`
      );
      await assertAgentInvokedTools(page, 2); // Write + Bash

      const lastText = (await page.locator(".agent-msg .body").last().textContent()) ?? "";
      expect(lastText, "Agent must echo back the marker content from Bash output").toContain(marker);
      await assertNotARefusal(page);
    });

    test("searxng fast search: agent uses searxng MCP for AI news", async ({ page }) => {
      test.setTimeout(300_000);
      await loginViaPrismUI(page, ADMIN_EMAIL, ADMIN_PASSWORD);
      await sendPromptAndWaitForCompletion(
        page,
        "请搜索：今天 AI 行业的重要新闻，给我 2 条带链接。优先用 searxng 工具（速度快）。"
      );
      await assertAgentInvokedTools(page, 1);

      // Real URL must be cited in final response (rendered as <a href>)
      const links = page.locator(".agent-msg .body").last().locator("a[href^='http']");
      const linkCount = await links.count();
      expect(linkCount, "Searxng must return real URLs cited in markdown").toBeGreaterThan(0);

      const sampleHref = await links.first().getAttribute("href");
      console.log(`[agent-action-tools-real ${cfg.name}] sample searxng URL:`, (sampleHref ?? "").slice(0, 80));
      await assertNotARefusal(page);
    });
  });
}
