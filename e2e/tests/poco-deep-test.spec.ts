import { test, expect } from '@playwright/test';

test.describe('Poco Deep E2E Tests', () => {

  test('[Desktop] Full page load with network debugging', async ({ page }) => {
    const resourceErrors: string[] = [];
    
    // Capture failed resource loads
    page.on('response', response => {
      if (response.status() === 400 || response.status() >= 500) {
        console.log(`[${response.status()}] ${response.url()}`);
        resourceErrors.push(`${response.status()} ${response.url()}`);
      }
    });
    
    await page.goto('http://localhost:3100/', { waitUntil: 'domcontentloaded' });
    
    // Wait longer for the page to actually load content
    await page.waitForTimeout(3000);
    
    // Take screenshot to see what's on the page
    await page.screenshot({ path: 'poco-deep-01.png' });
    
    // Try to get actual page content
    const html = await page.content();
    console.log('HTML length:', html.length);
    console.log('Has image tag:', html.includes('<img'));
    
    // Check what actually rendered
    const visibleText = await page.locator('body *').evaluateAll(elements => {
      return elements
        .filter(el => {
          const style = window.getComputedStyle(el);
          return style.display !== 'none' && style.visibility !== 'hidden';
        })
        .filter(el => el.textContent && el.textContent.trim().length > 0)
        .map(el => ({
          tag: el.tagName,
          text: el.textContent?.slice(0, 50),
          classes: el.className
        }))
        .slice(0, 10);
    });
    
    console.log('Visible elements:', visibleText);
    console.log('Resource errors:', resourceErrors.length, resourceErrors.slice(0, 5));
  });

  test('[Desktop] Check if page is in loading state', async ({ page }) => {
    await page.goto('http://localhost:3100/', { waitUntil: 'domcontentloaded' });
    
    // Check for loading indicators
    const hasLoadingSpinner = await page.locator('[class*="load"], [class*="spin"], .loader').count() > 0;
    const hasSuspense = await page.locator('svg, [role="progressbar"]').count() > 0;
    
    console.log('Has loading spinner:', hasLoadingSpinner);
    console.log('Has suspense elements:', hasSuspense);
    
    // Check the actual DOM structure
    const rootContent = await page.locator('#root, [role="main"], main').first().innerText().catch(() => 'NOT FOUND');
    console.log('Root content length:', rootContent !== 'NOT FOUND' ? rootContent.length : rootContent);
    
    // Wait for actual navigation
    await page.waitForURL(/.*/, { timeout: 5000 }).catch(() => {});
    const finalUrl = page.url();
    console.log('Final URL:', finalUrl);
    
    // Check if redirected to actual content
    const isHome = finalUrl.includes('/en/home');
    const isAuth = finalUrl.includes('/auth') || finalUrl.includes('/login');
    console.log('Is at home:', isHome);
    console.log('Is at auth:', isAuth);
  });

  test('[Desktop] Wait for all resources to load', async ({ page }) => {
    const failedLoads: { url: string, status: number }[] = [];
    
    page.on('response', resp => {
      if (resp.status() >= 400) {
        failedLoads.push({ url: resp.url(), status: resp.status() });
      }
    });
    
    await page.goto('http://localhost:3100/', { waitUntil: 'networkidle' });
    
    const title = await page.title();
    const url = page.url();
    
    console.log('Title:', title);
    console.log('URL:', url);
    console.log('Failed resource loads:', failedLoads);
    
    // Take screenshot after full load
    await page.screenshot({ path: 'poco-deep-full-load.png' });
  });

  test('[Desktop] Check what causes 400 errors', async ({ page }) => {
    const requests: { url: string, method: string }[] = [];
    
    page.on('request', req => {
      requests.push({ url: req.url(), method: req.method() });
    });
    
    await page.goto('http://localhost:3100/', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);
    
    // Filter for API calls that might fail
    const apiCalls = requests.filter(r => r.url.includes('/api'));
    console.log('API calls made:', apiCalls.slice(0, 5));
    
    // Check response details
    const pageRequests = await page.evaluate(() => {
      return (window as any).performance?.getEntriesByType?.('resource') || [];
    });
    console.log('Performance entries:', pageRequests.length);
  });

  test('[Mobile] Full page load on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    
    const failedLoads: string[] = [];
    page.on('response', resp => {
      if (resp.status() >= 400) {
        failedLoads.push(`${resp.status()} ${resp.url()}`);
      }
    });
    
    await page.goto('http://localhost:3100/', { waitUntil: 'networkidle' });
    
    const title = await page.title();
    console.log('[Mobile] Title:', title);
    console.log('[Mobile] Failed loads:', failedLoads.length);
    
    await page.screenshot({ path: 'poco-mobile-full-load.png' });
  });
});
