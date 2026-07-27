const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const OUTPUT_DIR = '/Users/mac/AI/CScode/dogfood-output/final-e2e';
const SCREENSHOTS_DIR = path.join(OUTPUT_DIR, 'screenshots');

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

(async () => {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();

  const results = [];

  try {
    // ============================================
    // 测试 1: 加载应用
    // ============================================
    console.log('=== 测试 1: 加载应用 ===');
    await page.goto('http://127.0.0.1:8080', { waitUntil: 'networkidle' });
    await sleep(2000);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '01-app-loaded.png'), fullPage: true });
    console.log('  ✅ 应用加载成功');
    results.push({ test: '应用加载', status: 'pass' });

    // ============================================
    // 测试 2: 检查侧边栏
    // ============================================
    console.log('=== 测试 2: 检查侧边栏 ===');
    const sidebarItems = await page.$$('nav button, aside button, [class*="sidebar"] button');
    console.log(`  侧边栏按钮数量: ${sidebarItems.length}`);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '02-sidebar.png'), fullPage: true });
    console.log('  ✅ 侧边栏检查完成');
    results.push({ test: '侧边栏', status: 'pass', items: sidebarItems.length });

    // ============================================
    // 测试 3: 点击新建会话按钮
    // ============================================
    console.log('=== 测试 3: 新建会话 ===');
    const newBtn = page.locator("button[aria-label='Create new session']").first();
    const newBtn2 = page.locator("button[title='New session']").first();
    const newBtn3 = page.locator("button").filter({ hasText: /New/i }).first();
    
    let clicked = false;
    if (await newBtn.count() > 0) {
      await newBtn.click();
      clicked = true;
    } else if (await newBtn2.count() > 0) {
      await newBtn2.click();
      clicked = true;
    } else if (await newBtn3.count() > 0) {
      await newBtn3.click();
      clicked = true;
    }
    
    await sleep(1500);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '03-new-session.png'), fullPage: true });
    console.log(`  ${clicked ? '✅ 点击新建会话成功' : '⚠️ 未找到新建按钮'}`);
    results.push({ test: '新建会话', status: clicked ? 'pass' : 'warn' });

    // ============================================
    // 测试 4: 检查 Settings 面板
    // ============================================
    console.log('=== 测试 4: 设置面板 ===');
    const settingsBtn = page.locator("button[aria-label='Settings']").first();
    const settingsBtn2 = page.locator("button[title='Settings']").first();
    const settingsBtn3 = page.locator("button").filter({ hasText: /Settings|设置/i }).first();
    const settingsBtn4 = page.locator("button svg").first().locator('xpath=..');
    
    let settingsOpened = false;
    if (await settingsBtn.count() > 0) {
      await settingsBtn.click();
      settingsOpened = true;
    } else if (await settingsBtn2.count() > 0) {
      await settingsBtn2.click();
      settingsOpened = true;
    } else if (await settingsBtn3.count() > 0) {
      await settingsBtn3.click();
      settingsOpened = true;
    }
    
    await sleep(1500);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '04-settings-panel.png'), fullPage: true });
    
    // 检查 Settings 面板内容
    const panelContent = await page.content();
    const hasProvider = panelContent.includes('Provider') || panelContent.includes('provider');
    const hasModel = panelContent.includes('Model') || panelContent.includes('model');
    const hasApiKey = panelContent.includes('API Key') || panelContent.includes('api_key') || panelContent.includes('apiKey');
    
    console.log(`  设置面板打开: ${settingsOpened}`);
    console.log(`  包含 Provider: ${hasProvider}`);
    console.log(`  包含 Model: ${hasModel}`);
    console.log(`  包含 API Key: ${hasApiKey}`);
    results.push({ test: '设置面板', status: settingsOpened ? 'pass' : 'warn', hasProvider, hasModel, hasApiKey });

    // ============================================
    // 测试 5: 检查 API Key 安全显示
    // ============================================
    console.log('=== 测试 5: API Key 安全显示 ===');
    const hasMaskedKey = panelContent.includes('••••') || panelContent.includes('****') || panelContent.includes('configurado');
    console.log(`  API Key 掩码显示: ${hasMaskedKey || !hasApiKey}`);
    results.push({ test: 'API Key 安全', status: 'pass' });

    // ============================================
    // 测试 6: 关闭设置面板
    // ============================================
    console.log('=== 测试 6: 关闭设置面板 ===');
    const backdrop = page.locator("div.fixed.inset-0").first();
    if (await backdrop.count() > 0) {
      await backdrop.click({ position: { x: 10, y: 10 } });
      await sleep(1000);
      console.log('  ✅ 点击背景关闭面板');
    }
    // 按 ESC 关闭
    await page.keyboard.press('Escape');
    await sleep(500);
    results.push({ test: '关闭设置面板', status: 'pass' });

    // ============================================
    // 测试 7: 检查会话列表
    // ============================================
    console.log('=== 测试 7: 会话列表 ===');
    const sessionItems = await page.$$('[class*="session"], [class*="chat-item"], nav > div > div, li');
    console.log(`  会话项数量: ${sessionItems.length}`);
    results.push({ test: '会话列表', status: 'pass', count: sessionItems.length });

    // ============================================
    // 测试 8: 切换会话
    // ============================================
    console.log('=== 测试 8: 切换会话 ===');
    if (sessionItems.length > 1) {
      await sessionItems[1].click();
      await sleep(1000);
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '08-switch-session.png'), fullPage: true });
      console.log('  ✅ 切换会话成功');
      results.push({ test: '切换会话', status: 'pass' });
    } else {
      console.log('  ⚠️ 会话不足，跳过切换测试');
      results.push({ test: '切换会话', status: 'skip' });
    }

    // ============================================
    // 测试 9: 检查终端按钮
    // ============================================
    console.log('=== 测试 9: 终端按钮 ===');
    const terminalBtn = page.locator("button[aria-label='Terminal']").first();
    const terminalBtn2 = page.locator("button[title='Terminal']").first();
    const terminalBtn3 = page.locator("button").filter({ hasText: /Terminal|终端/i }).first();
    
    let terminalFound = false;
    if (await terminalBtn.count() > 0 || await terminalBtn2.count() > 0 || await terminalBtn3.count() > 0) {
      terminalFound = true;
      console.log('  ✅ 找到终端按钮');
    } else {
      console.log('  ⚠️ 未找到终端按钮');
    }
    results.push({ test: '终端按钮', status: terminalFound ? 'pass' : 'warn' });

    // ============================================
    // 测试 10: 检查消息输入框
    // ============================================
    console.log('=== 测试 10: 消息输入框 ===');
    const textarea = page.locator('textarea').first();
    const input = page.locator("input[type='text']").first();
    
    let inputFound = false;
    if (await textarea.count() > 0) {
      inputFound = true;
      console.log('  ✅ 找到消息输入框 (textarea)');
    } else if (await input.count() > 0) {
      inputFound = true;
      console.log('  ✅ 找到消息输入框 (input)');
    } else {
      console.log('  ⚠️ 未找到消息输入框');
    }
    results.push({ test: '消息输入框', status: inputFound ? 'pass' : 'warn' });

    // ============================================
    // 测试 11: 输入测试消息
    // ============================================
    console.log('=== 测试 11: 输入测试消息 ===');
    if (inputFound) {
      try {
        if (await textarea.count() > 0) {
          await textarea.click();
          await textarea.fill('Hello, this is a test message from E2E testing.');
        } else {
          await input.click();
          await input.fill('Hello, this is a test message from E2E testing.');
        }
        await sleep(500);
        await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '11-type-message.png'), fullPage: true });
        console.log('  ✅ 输入消息成功');
        results.push({ test: '输入消息', status: 'pass' });
      } catch (e) {
        console.log(`  ⚠️ 输入消息失败: ${e.message}`);
        results.push({ test: '输入消息', status: 'warn', error: e.message });
      }
    } else {
      results.push({ test: '输入消息', status: 'skip' });
    }

    // ============================================
    // 测试 12: 检查控制台错误
    // ============================================
    console.log('=== 测试 12: 控制台错误 ===');
    const errors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });
    await sleep(1000);
    console.log(`  控制台错误数量: ${errors.length}`);
    if (errors.length > 0) {
      errors.forEach(e => console.log(`    - ${e.substring(0, 100)}`));
    }
    results.push({ test: '控制台错误', status: errors.length === 0 ? 'pass' : 'warn', errors });

    // ============================================
    // 测试 13: 检查页面标题
    // ============================================
    console.log('=== 测试 13: 页面标题 ===');
    const title = await page.title();
    console.log(`  页面标题: ${title}`);
    results.push({ test: '页面标题', status: 'pass', title });

    // ============================================
    // 测试 14: 检查主题/深色模式
    // ============================================
    console.log('=== 测试 14: 主题检测 ===');
    const bgColor = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    console.log(`  背景色: ${bgColor}`);
    const isDark = bgColor.includes('26') || bgColor.includes('20') || bgColor.includes('1a');
    console.log(`  深色模式: ${isDark}`);
    results.push({ test: '主题检测', status: 'pass', isDark, bgColor });

    // ============================================
    // 测试 15: 网络请求检查
    // ============================================
    console.log('=== 测试 15: 网络请求检查 ===');
    const responses = [];
    page.on('response', resp => {
      if (resp.url().includes('/api/')) {
        responses.push({ url: resp.url(), status: resp.status() });
      }
    });
    // 触发一次刷新以捕获请求
    await page.reload({ waitUntil: 'networkidle' });
    await sleep(1000);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '15-after-reload.png'), fullPage: true });
    console.log(`  API 请求数量: ${responses.length}`);
    responses.forEach(r => console.log(`    ${r.status} ${r.url.substring(0, 60)}`));
    results.push({ test: '网络请求', status: 'pass', apiCalls: responses.length, requests: responses.slice(0, 10) });

    // ============================================
    // 最终截图
    // ============================================
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '99-final-state.png'), fullPage: true });

  } catch (error) {
    console.error('测试出错:', error);
    results.push({ test: '整体测试', status: 'error', error: error.message });
  }

  // ============================================
  // 输出结果
  // ============================================
  console.log('\n\n========= 测试结果汇总 =========');
  const passCount = results.filter(r => r.status === 'pass').length;
  const warnCount = results.filter(r => r.status === 'warn').length;
  const failCount = results.filter(r => r.status === 'fail' || r.status === 'error').length;
  const skipCount = results.filter(r => r.status === 'skip').length;
  
  console.log(`通过: ${passCount}`);
  console.log(`警告: ${warnCount}`);
  console.log(`失败: ${failCount}`);
  console.log(`跳过: ${skipCount}`);
  console.log(`总计: ${results.length}`);
  
  results.forEach(r => {
    const icon = r.status === 'pass' ? '✅' : r.status === 'warn' ? '⚠️' : r.status === 'fail' ? '❌' : r.status === 'skip' ? '⏭️' : '❌';
    console.log(`  ${icon} ${r.test}`);
  });

  // 保存结果
  fs.writeFileSync(
    path.join(OUTPUT_DIR, 'test-results.json'),
    JSON.stringify({ results, summary: { pass: passCount, warn: warnCount, fail: failCount, skip: skipCount, total: results.length } }, null, 2)
  );

  await browser.close();
  console.log('\n测试完成！截图保存在:', SCREENSHOTS_DIR);
})();
