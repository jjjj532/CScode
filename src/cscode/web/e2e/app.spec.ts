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
    const sendButton = page.locator('button:has(svg), button:has-text("Send"), button:has-text("发送")').last();
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
    
    // Settings panel should be visible — look for the heading inside the panel
    const heading = page.locator('h2:has-text("Settings")');
    await expect(heading).toBeVisible();
  });
});

test.describe('Theme Switching', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('theme can be changed via settings', async ({ page }) => {
    // Open settings
    const settingsBtn = page.locator('button:has-text("Settings")').first();
    await settingsBtn.click();
    await page.waitForTimeout(300);

    // Theme dropdown should exist in settings panel
    const themeSelect = page.locator('select').filter({ has: page.locator('option:has-text("Dark")') });
    await expect(themeSelect).toBeVisible();
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
    
    // ModeToggle uses aria-checked for active state
    await expect(planButton).toHaveAttribute('aria-checked', 'true');
  });

  test('can switch to Build mode', async ({ page }) => {
    const buildButton = page.locator('button:has-text("Build"), button:has-text("构建")').first();
    await buildButton.click();
    
    await expect(buildButton).toHaveAttribute('aria-checked', 'true');
  });
});

test.describe('Session Management', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('session list exists', async ({ page }) => {
    // Sidebar uses role="navigation" with aria-label
    const sidebar = page.locator('[role="navigation"]');
    await expect(sidebar).toBeVisible();
  });

  test('new session button exists', async ({ page }) => {
    const newSessionButton = page.locator('button:has-text("New"), button:has-text("新建"), button[aria-label*="new session" i]');
    await expect(newSessionButton.first()).toBeVisible();
  });

  test('can create new session', async ({ page }) => {
    const newSessionButton = page.locator('button[aria-label*="new session" i]').first();
    await newSessionButton.click();
    await page.waitForTimeout(1000);
    
    // Verify by checking API directly that sessions exist
    const resp = await page.request.get('/api/sessions');
    expect(resp.ok(), `API returned ${resp.status()}`).toBeTruthy();
    const data = await resp.json();
    expect(Array.isArray(data)).toBeTruthy();
    expect(data.length).toBeGreaterThanOrEqual(1);
  });
});

test.describe('Settings Panel - MCP Servers', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // Open settings
    const settingsBtn = page.locator('button:has-text("Settings"), button:has-text("设置")').first();
    await settingsBtn.click();
    await page.waitForTimeout(500);
  });

  test('MCP Servers section is visible', async ({ page }) => {
    await expect(page.getByText('MCP Servers', { exact: true }).first()).toBeVisible();
  });

  test('can add an MCP server', async ({ page }) => {
    const addBtn = page.locator('button[title="Add MCP server"]');
    await addBtn.click();

    await page.locator('input[placeholder="Server name"]').fill('filesystem');
    await page.locator('input[placeholder="Command (e.g. npx)"]').fill('npx');

    await expect(page.locator('input[placeholder="Server name"]')).toHaveValue('filesystem');
  });

  test('can remove an MCP server', async ({ page }) => {
    const addBtn = page.locator('button[title="Add MCP server"]');
    await addBtn.click();
    await page.locator('input[placeholder="Server name"]').fill('to-delete');

    const removeBtn = page.locator('button[title="Remove server"]');
    await removeBtn.click();

    await expect(page.getByText('No MCP servers configured.')).toBeVisible();
  });

  test('can save MCP server settings', async ({ page }) => {
    await page.locator('button[title="Add MCP server"]').click();
    await page.locator('input[placeholder="Server name"]').fill('test-srv');
    await page.locator('input[placeholder="Command (e.g. npx)"]').fill('echo');

    const saveBtn = page.locator('button:has-text("Save Settings")');
    await saveBtn.click();
    await page.waitForTimeout(1000);

    // Save button shows "Saved ✓" on success
    await expect(page.getByText('Saved').first()).toBeVisible();
  });
});

test.describe('Settings Panel - Plugins', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    const settingsBtn = page.locator('button:has-text("Settings"), button:has-text("设置")').first();
    await settingsBtn.click();
    await page.waitForTimeout(500);
  });

  test('Plugins section shows known plugins', async ({ page }) => {
    await expect(page.locator('text=Plugins')).toBeVisible();
    await expect(page.locator('text=code-reviewer')).toBeVisible();
    await expect(page.locator('text=test-engineer')).toBeVisible();
    await expect(page.locator('text=security-auditor')).toBeVisible();
  });

  test('can toggle plugin checkbox', async ({ page }) => {
    const checkbox = page.locator('text=code-reviewer').locator('..').locator('input[type="checkbox"]');
    await checkbox.check();
    await expect(checkbox).toBeChecked();

    const saveBtn = page.locator('button:has-text("Save Settings")');
    await saveBtn.click();
    await page.waitForTimeout(300);
  });
});

test.describe('Settings Panel - Keybindings', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    const settingsBtn = page.locator('button:has-text("Settings"), button:has-text("设置")').first();
    await settingsBtn.click();
    await page.waitForTimeout(500);
  });

  test('Keybindings section is visible', async ({ page }) => {
    await expect(page.locator('text=Keybindings')).toBeVisible();
  });

  test('can add a keybinding', async ({ page }) => {
    const actionInput = page.locator('input[placeholder="Action name"]');
    const keyInput = page.locator('input[placeholder="Shortcut"]');

    await actionInput.fill('toggle_dark_mode');
    await keyInput.fill('Ctrl+D');

    const plusBtn = page.locator('button[title="Add keybinding"]');
    await plusBtn.click();
    await page.waitForTimeout(200);

    await expect(page.locator('text=toggle_dark_mode')).toBeVisible();
  });

  test('can edit a keybinding', async ({ page }) => {
    // Add one first
    const actionInput = page.locator('input[placeholder="Action name"]');
    const keyInput = page.locator('input[placeholder="Shortcut"]');
    await actionInput.fill('send_message');
    await keyInput.fill('Enter');
    const plusBtn = page.locator('button[title="Add keybinding"]');
    await plusBtn.click();
    await page.waitForTimeout(200);

    // Edit the value
    const shortcutInput = page.locator('input[value="Enter"]');
    await shortcutInput.fill('Ctrl+Enter');

    await expect(page.locator('input[value="Ctrl+Enter"]')).toBeVisible();
  });

  test('can remove a keybinding', async ({ page }) => {
    const actionInput = page.locator('input[placeholder="Action name"]');
    const keyInput = page.locator('input[placeholder="Shortcut"]');
    await actionInput.fill('test_remove');
    await keyInput.fill('Ctrl+R');
    const plusBtn = page.locator('button[title="Add keybinding"]');
    await plusBtn.click();
    await page.waitForTimeout(200);

    const removeBtns = page.locator('button[title="Remove keybinding"]');
    const countBefore = await removeBtns.count();
    await removeBtns.last().click();
    const countAfter = await removeBtns.count();
    expect(countAfter).toBeLessThan(countBefore);
  });
});

test.describe('Settings Panel - Permission Rules', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    const settingsBtn = page.locator('button:has-text("Settings"), button:has-text("设置")').first();
    await settingsBtn.click();
    await page.waitForTimeout(500);
  });

  test('Permission Rules section is visible', async ({ page }) => {
    await expect(page.getByText('Permission Rules', { exact: true }).first()).toBeVisible();
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
    
    // Filter out non-critical errors
    const criticalErrors = errors.filter(err => 
      !err.includes('DevTools')
    );
    
    expect(criticalErrors.length).toBe(0);
  });
});
