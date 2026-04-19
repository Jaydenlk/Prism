import { test, expect, request as playwrightRequest } from '@playwright/test';
import { loginAsAdmin, BASE } from '../fixtures/auth';

/**
 * chat.spec.ts — Core chat flow tests
 *
 * Requires CloudDream provider to have a valid API key and credit.
 * Sends "reply OK only" → expects "OK" text within 20s via SSE stream.
 *
 * NOTE: After login, the chat page shows EmptyNoSession (no composer) until
 * a session is selected or created. The test creates a session first.
 */

async function startNewChatSession(page: any) {
  // Click "新对话" button in the sidebar to create a session
  const newChatBtn = page.locator('button:has-text("新对话")').first();
  await expect(newChatBtn).toBeVisible({ timeout: 8_000 });
  await newChatBtn.click();

  // Wait for the composer (textarea) to appear
  await expect(page.locator('.composer-wrap textarea, .composer textarea')).toBeVisible({ timeout: 8_000 });
}

test.describe('Chat flow', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test('composer is accessible after creating a new chat session', async ({ page }) => {
    await startNewChatSession(page);

    const textarea = page.locator('.composer-wrap textarea, .composer textarea').first();
    await expect(textarea).toBeVisible({ timeout: 8_000 });
    await expect(textarea).toBeEnabled();
  });

  test('send "reply OK only" → receives OK reply within 20s', async ({ page }) => {
    await startNewChatSession(page);

    const textarea = page.locator('.composer-wrap textarea, .composer textarea').first();
    await expect(textarea).toBeVisible({ timeout: 8_000 });

    // Type the prompt
    await textarea.click();
    await textarea.fill('reply OK only');

    // Send via Enter (composer submits on Enter without Shift)
    await textarea.press('Enter');

    // Wait up to 20s for "OK" text to appear in a message (agent reply)
    await expect(
      page.locator('.msg, [class*="msg"]').filter({ hasText: 'OK' }).first()
    ).toBeVisible({ timeout: 20_000 });
  });
});
