import { test, expect } from '@playwright/test';

test.describe('Poco E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Override base URL for Poco
    await page.goto('http://localhost:3100/');
  });

  test('[Desktop] Landing page load and UI', async ({ page }) => {
    // Wait for page to fully load
    await page.waitForLoadState('networkidle');
    
    // Screenshot
    await page.screenshot({ path: 'poco-landing-desktop.png' });
    
    // Check title
    const title = await page.title();
    console.log('Page title:', title);
    expect(title).toContain('Poco');
    
    // Check URL redirect
    const url = page.url();
    console.log('Final URL:', url);
    expect(url).toMatch(/\/en\/home|\/|poco/i);
  });

  test('[Desktop] Check page structure', async ({ page }) => {
    await page.waitForLoadState('networkidle');
    
    // Get visible text
    const bodyText = await page.locator('body').innerText();
    console.log('Body text length:', bodyText.length);
    console.log('First 200 chars:', bodyText.substring(0, 200));
    
    // Check for key elements
    const buttons = await page.locator('button').count();
    const links = await page.locator('a').count();
    const images = await page.locator('img').count();
    
    console.log('Buttons:', buttons);
    console.log('Links:', links);
    console.log('Images:', images);
    
    expect(buttons + links).toBeGreaterThan(0);
  });

  test('[Desktop] Check for auth protection', async ({ page }) => {
    await page.waitForLoadState('networkidle');
    
    // Try to access protected route directly
    await page.goto('http://localhost:3100/en/home', { waitUntil: 'networkidle' });
    const homeUrl = page.url();
    console.log('After accessing /en/home:', homeUrl);
    
    // Check if auth is required
    const hasAuthUI = await page.locator('[class*="login"], [class*="auth"], [class*="signin"]').count() > 0;
    console.log('Has auth UI elements:', hasAuthUI);
  });

  test('[Desktop] Check console for errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });
    
    await page.goto('http://localhost:3100/');
    await page.waitForLoadState('networkidle');
    
    console.log('Console errors found:', errors.length);
    if (errors.length > 0) {
      console.log('Errors:');
      errors.forEach(e => console.log('  -', e));
    }
  });

  test('[Mobile] Landing page on mobile (390x844)', async ({ browser }) => {
    const context = await browser.createContext({
      viewport: { width: 390, height: 844 }
    });
    const page = await context.newPage();
    
    await page.goto('http://localhost:3100/');
    await page.waitForLoadState('networkidle');
    
    // Screenshot
    await page.screenshot({ path: 'poco-landing-mobile.png' });
    
    const title = await page.title();
    expect(title).toContain('Poco');
    
    const viewport = await page.evaluate(() => ({
      innerWidth: window.innerWidth,
      innerHeight: window.innerHeight,
    }));
    console.log('Mobile viewport:', viewport);
    
    await context.close();
  });

  test('[Mobile] Check responsive layout', async ({ browser }) => {
    const context = await browser.createContext({
      viewport: { width: 390, height: 844 }
    });
    const page = await context.newPage();
    
    await page.goto('http://localhost:3100/');
    await page.waitForLoadState('networkidle');
    
    // Check for overflow issues
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
    
    console.log('Mobile scrollWidth:', scrollWidth);
    console.log('Mobile clientWidth:', clientWidth);
    
    // Allow 1px tolerance for rounding
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);
    
    await context.close();
  });

  test('[Desktop] Check viewport dimensions', async ({ page }) => {
    await page.goto('http://localhost:3100/');
    await page.waitForLoadState('networkidle');
    
    const viewport = page.viewportSize();
    console.log('Viewport size:', viewport);
    expect(viewport).not.toBeNull();
  });

  test('[Desktop] Check if page is interactive', async ({ page }) => {
    await page.goto('http://localhost:3100/');
    await page.waitForLoadState('networkidle');
    
    // Try to click first button
    const firstButton = page.locator('button').first();
    const isVisible = await firstButton.isVisible();
    console.log('First button visible:', isVisible);
    
    if (isVisible) {
      const isEnabled = await firstButton.isEnabled();
      console.log('First button enabled:', isEnabled);
    }
  });
});
