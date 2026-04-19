import { test, expect } from '@playwright/test';
import { loginAsAdmin } from '../fixtures/auth';
import { startNewChatSession } from '../fixtures/chat';

/**
 * Session 1 fixes — Bug 1 (user message disappears) + Bug 2 (markdown not rendered).
 *
 * Bug 1 is a chat-flow bug; tested through the real UI with login + send + assert.
 * Bug 2 is a renderer bug; tested in isolation via a production-guarded mount
 * helper at /?__e2e=1 — does NOT depend on LLM fidelity.
 */

test.describe('Bug 1: user bubble persists after run_complete', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test('user bubble with unique token still visible after assistant reply', async ({ page }) => {
    await startNewChatSession(page);
    const token = `TEST-BUG1-${Date.now()}`;

    const composer = page.locator('.composer-wrap textarea, .composer textarea').first();
    await composer.click();
    await composer.fill(token);
    await composer.press('Enter');

    // Wait for assistant reply to appear and stream to finish
    await expect(page.locator('.agent-msg .content').first()).toBeVisible({ timeout: 30_000 });
    await expect(page.locator('.agent-msg .caret')).toHaveCount(0, { timeout: 20_000 });
    // Settle for run_complete history refresh
    await page.waitForTimeout(1500);

    // Assertion: user bubble with the token MUST still be visible (the bug is its disappearance)
    const userBubble = page.locator('.user-msg .bubble', { hasText: token });
    await expect(userBubble).toBeVisible();
    await expect(userBubble).toContainText(token);
  });
});

test.describe('Bug 2: MarkdownBody renders markdown primitives as sanitized HTML', () => {
  test('renders h2/ul/strong/code/pre/blockquote/table + blocks XSS', async ({ page }) => {
    // Navigate with __e2e=1 flag which exposes the test-only mount helper.
    // No login required — helper is registered at app-script-eval time, independent of auth state.
    await page.goto('/?__e2e=1');

    await page.waitForFunction(
      () => typeof (window as any).__e2e_mountMarkdown === 'function',
      null,
      { timeout: 15_000 }
    );

    const fixtureMd = [
      '## 标题 H2',
      '',
      '- 列表项 A',
      '- 列表项 B',
      '- **粗体文本** 和 `inline code`',
      '',
      '```python',
      'def hello():',
      '    print("hi")',
      '```',
      '',
      '> 引用段落',
      '',
      '| 列 A | 列 B |',
      '|---|---|',
      '| 1 | 2 |',
    ].join('\n');

    await page.evaluate((md) => (window as any).__e2e_mountMarkdown(md), fixtureMd);

    const mdRoot = page.locator('#e2e-md-root .content.md');

    await expect(mdRoot.locator('h2', { hasText: '标题 H2' })).toBeVisible();
    await expect(mdRoot.locator('ul li')).toHaveCount(3);
    await expect(mdRoot.locator('strong', { hasText: '粗体文本' })).toBeVisible();
    await expect(mdRoot.locator('code', { hasText: 'inline code' })).toBeVisible();
    await expect(mdRoot.locator('pre code')).toContainText('def hello');
    await expect(mdRoot.locator('blockquote')).toContainText('引用段落');
    await expect(mdRoot.locator('table thead th')).toHaveCount(2);
    await expect(mdRoot.locator('table tbody tr')).toHaveCount(1);

    await mdRoot.screenshot({ path: `test-results/md-${test.info().project.name}.png` });

    // XSS regression (DOMPurify success path): raw <script> in input must NOT execute.
    const xssInput = '<script>window.__xss_hit = 1</script>ok';
    await page.evaluate((md) => (window as any).__e2e_mountMarkdown(md), xssInput);
    await page.waitForTimeout(300);
    const xssFired = await page.evaluate(() => (window as any).__xss_hit === 1);
    expect(xssFired).toBe(false);
  });

  test('catch-branch: marked throws → textContent escape fallback, still no XSS', async ({ page }) => {
    // Covers the catch-branch in MarkdownBody when marked.parse raises.
    // The fallback must escape raw HTML via textContent/innerHTML — never passes a raw string
    // through dangerouslySetInnerHTML.
    await page.goto('/?__e2e=1');
    await page.waitForFunction(() => typeof (window as any).__e2e_mountMarkdown === 'function', null, { timeout: 15_000 });

    // Force marked.parse to throw so the catch branch is exercised.
    await page.evaluate(() => {
      (window as any).marked = { parse: () => { throw new Error('simulated parse failure'); } };
    });

    const payload = '<script>window.__xss_catch_hit = 1</script>raw & <b>unsafe</b>';
    await page.evaluate((p) => (window as any).__e2e_mountMarkdown(p), payload);
    await page.waitForTimeout(300);

    const xssFired = await page.evaluate(() => (window as any).__xss_catch_hit === 1);
    expect(xssFired).toBe(false);

    const mdRoot = page.locator('#e2e-md-root .content.md');
    // No raw script/b elements in the DOM — content is text, not tags.
    await expect(mdRoot.locator('script')).toHaveCount(0);
    await expect(mdRoot.locator('b')).toHaveCount(0);
    // The payload's literal characters appear as escaped text.
    await expect(mdRoot).toContainText('<script>');
    await expect(mdRoot).toContainText('<b>unsafe</b>');
  });
});
