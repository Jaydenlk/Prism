import { defineConfig, devices } from '@playwright/test';

/**
 * Prism v2 Playwright configuration.
 *
 * Projects:
 *   desktop-chromium  — 1440×900, Chromium
 *   mobile-safari     — iPhone 13 viewport, WebKit (real Mobile Safari emulation)
 *
 * Browser install: npx playwright install --with-deps chromium webkit
 */
export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  retries: 1,
  fullyParallel: false,   // run tests sequentially to avoid SSE connection stampedes
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],

  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:8080',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'off',
  },

  projects: [
    {
      name: 'desktop-chromium',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1440, height: 900 },
      },
    },
    {
      name: 'mobile-safari',
      use: {
        ...devices['iPhone 13'],
        // browserName: 'webkit' is set by devices['iPhone 13']
      },
    },
  ],
});
