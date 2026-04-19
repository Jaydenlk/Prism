import { Page, expect } from '@playwright/test';

/**
 * Shared chat flow helpers. Keep scope-minimal — only shared across multiple
 * spec files (chat.spec.ts, chat-msg-render.spec.ts, etc.).
 */

export async function startNewChatSession(page: Page): Promise<void> {
  const newChatBtn = page.locator('button:has-text("新对话")').first();
  await expect(newChatBtn).toBeVisible({ timeout: 8_000 });
  await newChatBtn.click();
  await expect(
    page.locator('.composer-wrap textarea, .composer textarea').first()
  ).toBeVisible({ timeout: 8_000 });
}
