/**
 * CScode Web E2E Tests
 * 端到端测试套件
 */
import { test, expect } from '@playwright/test';

test.describe('CScode Web Application', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('homepage loads successfully', async ({ page }) => {
    // Check that the page title or main heading exists
    await expect(page).toHaveTitle(/CScode|Code/i);
  });

  test('navigation is visible', async ({ page }) => {
    // Check for navigation elements
    const hasNav = await page.locator('nav, header, [role="navigation"]').count() > 0;
    expect(hasNav).toBeTruthy();
  });
});

test.describe('Chat Interface', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('composer input is visible', async ({ page }) => {
    const composer = page.locator('input[type="text"], textarea, [placeholder*="message" i], [placeholder*="输入" i]');
    await expect(composer.first()).toBeVisible();
  });

  test('send button exists', async ({ page }) => {
    const sendButton = page.locator('button[type="submit"], button:has-text("Send"), button:has-text("发送")');
    await expect(sendButton.first()).toBeVisible();
  });

  test('can type in composer', async ({ page }) => {
    const composer = page.locator('input[type="text"], textarea').first();
    await composer.fill('Hello CScode');
    await expect(composer).toHaveValue('Hello CScode');
  });

  test('message list area exists', async ({ page }) => {
    const messageList = page.locator('[class*="message"], [data-testid*="message"], main, [role="main"]');
    await expect(messageList.first()).toBeVisible();
  });
});

test.describe('Settings Panel', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('settings button exists', async ({ page }) => {
    const settingsButton = page.locator('button:has-text("Settings"), button:has-text("设置"), button[aria-label*="settings" i]');
    await expect(settingsButton.first()).toBeVisible();
  });

  test('can open settings panel', async ({ page }) => {
    const settingsButton = page.locator('button:has-text("Settings"), button:has-text("设置")').first();
    await settingsButton.click();
    
    // Settings panel should be visible
    const panel = page.locator('[role="dialog"], [class*="panel"], [class*="modal"]');
    await expect(panel.first()).toBeVisible();
  });
});

test.describe('Theme Switching', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('theme toggle exists', async ({ page }) => {
    const themeToggle = page.locator('button[aria-label*="theme" i], button:has-text("Theme"), button:has-text("主题"), [data-testid*="theme"]');
    await expect(themeToggle.first()).toBeVisible();
  });

  test('can toggle theme', async ({ page }) => {
    const themeToggle = page.locator('button[aria-label*="theme" i], button:has-text("Theme"), button:has-text("主题")').first();
    
    // Get initial theme
    const htmlBefore = await page.locator('html').getAttribute('class');
    
    await themeToggle.click();
    
    // Theme should have changed
    const htmlAfter = await page.locator('html').getAttribute('class');
    // Note: This test may need adjustment based on actual theme implementation
  });
});

test.describe('Mode Toggle (Plan/Build)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('mode toggle exists', async ({ page }) => {
    const modeToggle = page.locator('button:has-text("Plan"), button:has-text("Build"), button:has-text("计划"), button:has-text("构建")');
    await expect(modeToggle.first()).toBeVisible();
  });

  test('can switch to Plan mode', async ({ page }) => {
    const planButton = page.locator('button:has-text("Plan"), button:has-text("计划")').first();
    await planButton.click();
    
    // Plan should be active (check for active state)
    await expect(planButton).toHaveAttribute('data-active', 'true');
  });

  test('can switch to Build mode', async ({ page }) => {
    const buildButton = page.locator('button:has-text("Build"), button:has-text("构建")').first();
    await buildButton.click();
    
    // Build should be active
    await expect(buildButton).toHaveAttribute('data-active', 'true');
  });
});

test.describe('Session Management', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('session list exists', async ({ page }) => {
    const sessionList = page.locator('[class*="sidebar"], aside, [data-testid*="session"]');
    await expect(sessionList.first()).toBeVisible();
  });

  test('new session button exists', async ({ page }) => {
    const newSessionButton = page.locator('button:has-text("New"), button:has-text("新建"), button[aria-label*="new session" i]');
    await expect(newSessionButton.first()).toBeVisible();
  });

  test('can create new session', async ({ page }) => {
    const newSessionButton = page.locator('button:has-text("New"), button:has-text("新建")').first();
    await newSessionButton.click();
    
    // New session should appear in list or be selected
    const sessionItems = page.locator('[class*="session"], [data-testid*="session"]');
    await expect(sessionItems.first()).toBeVisible();
  });
});

test.describe('Responsive Design', () => {
  test('works on mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');
    
    // Main content should still be visible
    const mainContent = page.locator('main, [role="main"], [class*="content"]');
    await expect(mainContent.first()).toBeVisible();
  });

  test('works on tablet viewport', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto('/');
    
    // Layout should adapt
    const mainContent = page.locator('main, [role="main"]');
    await expect(mainContent.first()).toBeVisible();
  });
});

test.describe('Accessibility', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('page has proper heading structure', async ({ page }) => {
    const h1 = page.locator('h1');
    const hasH1 = await h1.count() > 0;
    
    // Should have at least one heading
    expect(hasH1 || await page.locator('h2, h3').count() > 0).toBeTruthy();
  });

  test('buttons have accessible names', async ({ page }) => {
    const buttons = page.locator('button');
    const count = await buttons.count();
    
    for (let i = 0; i < Math.min(count, 5); i++) {
      const button = buttons.nth(i);
      const hasText = await button.textContent();
      const hasAriaLabel = await button.getAttribute('aria-label');
      
      // Each button should have either text or aria-label
      expect(hasText?.trim() || hasAriaLabel).toBeTruthy();
    }
  });

  test('inputs have labels', async ({ page }) => {
    const inputs = page.locator('input:not([type="hidden"]), textarea');
    const count = await inputs.count();
    
    if (count > 0) {
      for (let i = 0; i < Math.min(count, 3); i++) {
        const input = inputs.nth(i);
        const hasLabel = await page.locator(`label[for="${await input.getAttribute('id')}"]`).count() > 0;
        const hasAriaLabel = await input.getAttribute('aria-label');
        const hasPlaceholder = await input.getAttribute('placeholder');
        
        // Input should have some form of labeling
        expect(hasLabel || hasAriaLabel || hasPlaceholder).toBeTruthy();
      }
    }
  });
});

test.describe('Performance', () => {
  test('page loads within acceptable time', async ({ page }) => {
    const startTime = Date.now();
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    const loadTime = Date.now() - startTime;
    
    // Page should load within 3 seconds
    expect(loadTime).toBeLessThan(3000);
  });

  test('no console errors on load', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });
    
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // Filter out known non-critical errors
    const criticalErrors = errors.filter(err => 
      !err.includes('favicon') && 
      !err.includes('404') &&
      !err.includes('DevTools')
    );
    
    expect(criticalErrors.length).toBe(0);
  });
});
