/**
 * Plugin Bootstrap — e2e real-call validation (Task 7 / W7 / L8)
 *
 * Verifies the full chain:
 *   backend lifespan → register_builtin_servers() registers exa
 *   admin.html → MCP Servers list shows exa row
 *   Prism.html → user asks for news → agent calls mcp__exa__web_search_exa
 *   tool_result rendered with real https:// URLs
 *
 * Runs against both config-defined projects (desktop-chromium 1440×900 +
 * mobile-safari iPhone 13) — viewport is set by playwright.config.ts projects.
 * Do NOT override viewport here; rely on project config.
 *
 * Pre-conditions:
 *   - docker compose -p prismv3-bootstrap up backend executor postgres redis
 *   - EXA_API_KEY present in .env → register_builtin_servers() inserts exa row
 *   - admin@prism.dev / PrismAdmin!2026 exists
 */
import { test, expect } from "@playwright/test";

const ADMIN_EMAIL = "admin@prism.dev";
const ADMIN_PASSWORD = "PrismAdmin!2026";

/** Login via Prism.html UI (both admin and regular user share this gate). */
async function loginViaPrismUI(
  page: any,
  email: string,
  password: string
): Promise<void> {
  await page.goto("/");

  // If sidebar already visible, already logged in
  const sidebarVisible = await page
    .locator(".sidebar")
    .isVisible()
    .catch(() => false);
  if (sidebarVisible) return;

  await page.waitForSelector('input[type="email"]', { timeout: 10_000 });
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', password);
  await page.click('button.btn.primary, button:has-text("登录")');
  await page.waitForSelector(".sidebar", { timeout: 15_000 });
}

// ── Test 1: admin sees exa registered as system MCP server ─────────────────

test("admin sees exa registered as system MCP server", async ({ page }) => {
  // Login via Prism.html first (admin.html redirects unauthenticated users)
  await loginViaPrismUI(page, ADMIN_EMAIL, ADMIN_PASSWORD);

  // Navigate to admin panel
  await page.goto("/admin.html");
  await expect(page.locator(".admin-app")).toBeVisible({ timeout: 10_000 });

  // Click MCP Servers in the rail
  const mcpRailItem = page
    .locator(".rail-item")
    .filter({
      has: page.locator(".lbl", { hasText: "MCP Servers" }),
    })
    .first();
  await expect(mcpRailItem).toBeVisible({ timeout: 8_000 });
  await mcpRailItem.click();

  // Page title confirms correct section
  await expect(page.locator(".page-title", { hasText: "MCP Servers" })).toBeVisible({
    timeout: 8_000,
  });

  // exa row must appear — auto-registered from EXA_API_KEY env var at lifespan
  const exaRow = page.locator("table.table tbody tr").filter({ hasText: "exa" });
  await expect(exaRow).toBeVisible({ timeout: 10_000 });

  // Assert transport = http (exa uses HTTP Streamable, DEC-005)
  const transportCell = exaRow.locator("td").nth(1);
  await expect(transportCell).toContainText("http");

  // Assert URL column shows exa endpoint
  const urlCell = exaRow.locator("td").nth(2);
  await expect(urlCell).toContainText("mcp.exa.ai");
});

// ── Test 2: user asks AI news → agent calls mcp__exa__web_search_exa ───────

test(
  "user asks for AI news → agent calls mcp__exa__web_search_exa with real result",
  async ({ page }) => {
    // LLM + real exa round-trip can take 60-90s; override default 30s timeout.
    test.setTimeout(120_000);

    await loginViaPrismUI(page, ADMIN_EMAIL, ADMIN_PASSWORD);

    // Start a new chat session
    const newChatBtn = page.locator('button.btn.primary:has-text("新对话")').first();
    await expect(newChatBtn).toBeVisible({ timeout: 8_000 });
    await newChatBtn.click();

    // Confirm composer is ready
    const textarea = page.locator(".composer-wrap textarea").first();
    await expect(textarea).toBeVisible({ timeout: 8_000 });
    await expect(textarea).toBeEnabled();

    // Submit the prompt
    await textarea.click();
    await textarea.fill(
      "请搜索：今天 AI 行业有什么重要新闻？给我 3 条带链接。"
    );
    await textarea.press("Enter");

    // Wait for streaming to complete — agent-msg without .streaming class appears
    // and the caret disappears (no .caret span visible in last agent bubble).
    // We wait up to 90s for real exa + LLM round-trip.
    await expect(
      page
        .locator(".agent-msg")
        .filter({ hasNot: page.locator(".caret") })
        .last()
    ).toBeVisible({ timeout: 90_000 });

    // --- Assert tool_use for mcp__exa__ ---
    // ToolCard renders: <div class="tool-card"><div class="tool-head">…<span class="name">tool name</span>
    // We need at least one .tool-card whose .name text starts with "mcp__exa__"
    const toolCards = page.locator(".tool-card");
    const toolCardCount = await toolCards.count();
    expect(toolCardCount).toBeGreaterThan(0);

    let foundExaTool = false;
    for (let i = 0; i < toolCardCount; i++) {
      const nameEl = toolCards.nth(i).locator(".name").first();
      const nameText = await nameEl.textContent();
      if (nameText && nameText.startsWith("mcp__exa__")) {
        foundExaTool = true;
        break;
      }
    }
    expect(
      foundExaTool,
      "Expected at least one tool card with name starting mcp__exa__"
    ).toBe(true);

    // --- Assert tool output contains real https:// URL ---
    // At least one .tool-card .tool-body pre.tool-code must contain a URL
    let foundRealUrl = false;
    for (let i = 0; i < toolCardCount; i++) {
      const nameEl = toolCards.nth(i).locator(".name").first();
      const nameText = await nameEl.textContent();
      if (nameText && nameText.startsWith("mcp__exa__")) {
        // textContent reads DOM content regardless of CSS display state —
        // no need to click-to-expand the tool card.
        const outputPre = toolCards.nth(i).locator(".tool-body pre.tool-code").last();
        const outputText = await outputPre.textContent();
        if (outputText && /https?:\/\/[^\s"']+/.test(outputText)) {
          foundRealUrl = true;
          // Log a sample URL for audit (no token leak — these are exa result URLs)
          const match = outputText.match(/https?:\/\/[^\s"']+/);
          if (match) {
            console.log("[plugin-bootstrap e2e] sample tool_result URL:", match[0].slice(0, 80));
          }
          break;
        }
      }
    }
    expect(
      foundRealUrl,
      "Expected tool_result output to contain at least one https:// URL from exa"
    ).toBe(true);

    // --- Assert assistant final message references content (not a refusal) ---
    const lastAgentMsg = page
      .locator(".agent-msg")
      .filter({ hasNot: page.locator(".caret") })
      .last()
      .locator(".body");
    const finalText = await lastAgentMsg.textContent();

    // Must NOT be a refusal
    expect(finalText ?? "").not.toMatch(
      /我.*不能.*搜索|无法访问网络|我没有.*搜索|unable to search|cannot browse/i
    );

    // Must contain at least one URL (agent summarises with cited links)
    expect(finalText ?? "").toMatch(/https?:\/\//);
  }
);

// ── Test 3: invalid key / graceful degradation ──────────────────────────────

test("invalid EXA_API_KEY → gracefully degraded (manual-only)", async () => {
  // Skipped: requires admin UI editing of server headers or restarting backend
  // with a bad key. Validate manually by setting EXA_API_KEY=invalid in .env
  // and restarting; exa row should still appear in admin (scope=system) but
  // agent tool call will return an error from the exa API, not a hallucinated response.
  test.skip(
    true,
    "Requires backend restart with EXA_API_KEY=invalid — verify manually"
  );
});
