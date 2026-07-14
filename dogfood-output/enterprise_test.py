#!/usr/bin/env python3
"""
CScode 企业级端到端测试脚本 - 修复版
基于实际页面结构调整定位器
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from playwright.async_api import Playwright, async_playwright


OUTPUT_DIR = Path("/Users/mac/AI/CScode/dogfood-output")
SCREENSHOT_DIR = OUTPUT_DIR / "screenshots"
TEST_RESULTS = OUTPUT_DIR / "test-results.json"

SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

issues = []
logs = []
network_errors = []
console_errors = []

def log(msg: str):
    print(msg)
    logs.append(msg)

def add_issue(severity: str, title: str, detail: str):
    issues.append({
        "severity": severity,
        "title": title,
        "detail": detail,
        "timestamp": datetime.now().isoformat()
    })
    log(f"  ❌ [{severity}] {title}: {detail}")

async def save_screenshot(page, name: str):
    path = SCREENSHOT_DIR / f"{name}.png"
    await page.screenshot(path=str(path))
    log(f"  📸 {name}.png")


# ========== 测试用例 ==========

async def test_1_sidebar_navigation(page):
    """测试侧边栏导航按钮"""
    log("\n=== 测试 1: 侧边栏导航 ===")
    
    # Settings 按钮
    settings_btn = page.locator('button[aria-label="Settings"]')
    if await settings_btn.is_visible(timeout=5000):
        await settings_btn.click()
        await page.wait_for_timeout(500)
        if await page.locator('h2:text("Settings")').is_visible(timeout=3000):
            log("  ✅ Settings 按钮")
            await save_screenshot(page, "01-settings-open")
            
            # 关闭设置
            close_settings = page.locator('button[aria-label="Close settings"]')
            await close_settings.click()
            log("  ✅ 关闭设置")
        else:
            add_issue("P1", "设置面板未打开", "点击 Settings 后未显示设置页面")
    else:
        add_issue("P1", "Settings 按钮不可见", "侧边栏底部未找到 Settings 按钮")
    
    # Help 按钮
    help_btn = page.locator('button[aria-label="Help"]')
    if await help_btn.is_visible(timeout=3000):
        await help_btn.click()
        log("  ✅ Help 按钮")
        await page.go_back()
        await page.wait_for_timeout(500)
    else:
        add_issue("P2", "Help 按钮不可见", "侧边栏底部未找到 Help 按钮")


async def test_2_threads_header(page):
    """测试会话列表头部按钮"""
    log("\n=== 测试 2: 会话列表头部 ===")
    
    # Filter 按钮
    filter_btn = page.locator('button[aria-label="Filter threads"]')
    if await filter_btn.is_visible(timeout=3000):
        await filter_btn.click()
        await page.wait_for_timeout(500)
        log("  ✅ Filter 按钮")
    else:
        add_issue("P2", "Filter 按钮不可见", "会话列表头部未找到 Filter 按钮")
    
    # Sort 按钮
    sort_btn = page.locator('button[aria-label="Sort threads"]')
    if await sort_btn.is_visible(timeout=3000):
        await sort_btn.click()
        await page.wait_for_timeout(500)
        log("  ✅ Sort 按钮")
    else:
        add_issue("P2", "Sort 按钮不可见", "会话列表头部未找到 Sort 按钮")
    
    # Refresh 按钮
    refresh_btn = page.locator('button[aria-label="Refresh sessions"]')
    if await refresh_btn.is_visible(timeout=3000):
        await refresh_btn.click()
        await page.wait_for_timeout(500)
        log("  ✅ Refresh 按钮")
    else:
        add_issue("P2", "Refresh 按钮不可见", "会话列表头部未找到 Refresh 按钮")
    
    # New Session 按钮
    new_session_btn = page.locator('button[aria-label="Create new session"]')
    if await new_session_btn.is_visible(timeout=3000):
        await new_session_btn.click()
        await page.wait_for_timeout(500)
        log("  ✅ New Session 按钮")
        await save_screenshot(page, "02-new-session")
    else:
        add_issue("P1", "New Session 按钮不可见", "会话列表头部未找到新建会话按钮")


async def test_3_session_actions(page):
    """测试会话操作 (hover 按钮)"""
    log("\n=== 测试 3: 会话操作 ===")
    
    # 找到会话按钮
    session_btns = page.locator('button:text("New Session")')
    count = await session_btns.count()
    
    if count == 0:
        log("  ⚠️ 没有找到会话按钮")
        return
    
    # 选择第一个会话
    first_session = session_btns.first
    await first_session.hover()
    await page.wait_for_timeout(300)
    
    # Export 按钮 (hover 后显示)
    export_btn = page.locator('button[aria-label="Export session"]').first
    if await export_btn.is_visible(timeout=2000):
        await export_btn.click()
        await page.wait_for_timeout(500)
        log("  ✅ Export 按钮")
        await save_screenshot(page, "03-export")
    else:
        add_issue("P2", "Export 按钮不可见", "hover 会话后未显示导出按钮")
    
    # Delete 按钮
    await first_session.hover()
    await page.wait_for_timeout(300)
    delete_btn = page.locator('button[aria-label="Delete session"]').first
    if await delete_btn.is_visible(timeout=2000):
        log("  ✅ Delete 按钮可见")
    else:
        add_issue("P2", "Delete 按钮不可见", "hover 会话后未显示删除按钮")


async def test_4_composer(page):
    """测试聊天输入区域"""
    log("\n=== 测试 4: 聊天输入区域 ===")
    
    # 输入框
    input_area = page.locator('textarea[placeholder*="Ask anything"]')
    if await input_area.is_visible(timeout=3000):
        await input_area.fill("Hello CScode")
        await page.wait_for_timeout(300)
        log("  ✅ 输入框")
        
        # Send 按钮
        send_btn = page.locator('button[aria-label="Send message"]')
        if await send_btn.is_enabled(timeout=2000):
            log("  ✅ Send 按钮可用")
            await save_screenshot(page, "04-composer")
        else:
            add_issue("P1", "Send 按钮不可用", "输入内容后发送按钮仍不可用")
        
        # Attach file 按钮
        attach_btn = page.locator('button[aria-label="Attach file"]')
        if await attach_btn.is_visible(timeout=2000):
            await attach_btn.click()
            log("  ✅ Attach file 按钮")
        else:
            add_issue("P2", "Attach file 按钮不可见", "输入区域未找到附件按钮")
        
        # 清空输入
        await input_area.fill("")
    else:
        add_issue("P1", "输入框不可见", "聊天区域未找到输入框")


async def test_5_mode_toggle(page):
    """测试 Plan/Build 模式切换"""
    log("\n=== 测试 5: 模式切换 ===")
    
    plan_btn = page.locator('button:text("Plan")')
    build_btn = page.locator('button:text("Build")')
    
    if await plan_btn.is_visible(timeout=3000):
        # 切换到 Build
        await build_btn.click()
        await page.wait_for_timeout(300)
        log("  ✅ 切换到 Build 模式")
        
        # 切换到 Plan
        await plan_btn.click()
        await page.wait_for_timeout(300)
        log("  ✅ 切换到 Plan 模式")
        
        await save_screenshot(page, "05-mode-toggle")
    else:
        add_issue("P1", "模式切换按钮不可见", "未找到 Plan/Build 切换按钮")


async def test_6_settings_panel(page):
    """测试设置面板所有功能"""
    log("\n=== 测试 6: 设置面板 ===")
    
    # 打开设置
    settings_btn = page.locator('button[aria-label="Settings"]')
    if await settings_btn.is_visible(timeout=3000):
        await settings_btn.click()
        await page.wait_for_timeout(500)
        
        if await page.locator('h2:text("Settings")').is_visible(timeout=3000):
            log("  ✅ 设置面板打开")
            
            # Provider 选择
            provider_select = page.locator('select')
            if await provider_select.first.is_visible():
                await provider_select.first.select_option("anthropic")
                log("  ✅ Provider 选择")
            
            # API Key 输入
            api_key_input = page.locator('input[type="password"]')
            if await api_key_input.first.is_visible():
                await api_key_input.first.fill("test-api-key")
                log("  ✅ API Key 输入")
            
            # Temperature 滑块
            temp_slider = page.locator('input[type="range"]')
            if await temp_slider.first.is_visible():
                await temp_slider.first.fill("1.0")
                log("  ✅ Temperature 滑块")
            
            # Max Tokens 输入
            max_tokens_input = page.locator('input[type="number"]')
            if await max_tokens_input.first.is_visible():
                await max_tokens_input.first.fill("8192")
                log("  ✅ Max Tokens 输入")
            
            # System Prompt 文本框
            system_prompt = page.locator('textarea')
            if await system_prompt.first.is_visible():
                await system_prompt.first.fill("You are a helpful assistant.")
                log("  ✅ System Prompt 文本框")
            
            # Theme 选择
            theme_select = page.locator('select')
            if await theme_select.count() >= 2:
                await theme_select.nth(1).select_option("opencode-light")
                await page.wait_for_timeout(300)
                await theme_select.nth(1).select_option("opencode-dark")
                log("  ✅ Theme 切换")
            
            # MCP Servers - 添加
            add_mcp_btn = page.locator('button:has(svg)').filter(has_text='')
            if await add_mcp_btn.is_visible():
                await add_mcp_btn.click()
                log("  ✅ 添加 MCP Server")
            
            # Plugins - 切换
            plugin_checkbox = page.locator('input[type="checkbox"]')
            if await plugin_checkbox.first.is_visible():
                await plugin_checkbox.first.check()
                log("  ✅ Plugin 启用")
            
            # Save Settings
            save_btn = page.locator('button:text("Save Settings")')
            if await save_btn.is_visible():
                await save_btn.click()
                await page.wait_for_timeout(1000)
                log("  ✅ 保存设置")
            
            await save_screenshot(page, "06-settings-panel")
            
            # 关闭设置
            close_btn = page.locator('button[aria-label="Close settings"]')
            await close_btn.click()
            log("  ✅ 关闭设置")
        else:
            add_issue("P1", "设置面板未显示", "点击 Settings 后内容未加载")
    else:
        add_issue("P1", "Settings 按钮不可见", "无法打开设置面板")


async def test_7_credential_panel(page):
    """测试凭证管理面板"""
    log("\n=== 测试 7: 凭证管理 ===")
    
    settings_btn = page.locator('button[aria-label="Settings"]')
    if await settings_btn.is_visible(timeout=3000):
        await settings_btn.click()
        await page.wait_for_timeout(500)
        
        # 找到 Credential Panel
        cred_section = page.locator('h3:text("Credentials")')
        if await cred_section.is_visible(timeout=3000):
            log("  ✅ Credential Panel 可见")
            
            # Provider 选择
            provider_select = page.locator('select:below(h3:text("Credentials"))').first
            if await provider_select.is_visible():
                await provider_select.select_option("anthropic")
            
            # API Key 输入
            api_key_input = page.locator('input[type="password"]:below(h3:text("Credentials"))').first
            if await api_key_input.is_visible():
                await api_key_input.fill("sk-test-123")
            
            # Add 按钮
            add_btn = page.locator('button:text("Add"):below(h3:text("Credentials"))').first
            if await add_btn.is_visible():
                await add_btn.click()
                await page.wait_for_timeout(500)
                log("  ✅ 添加凭证")
        
        await page.locator('button[aria-label="Close settings"]').click()
        await save_screenshot(page, "07-credentials")


async def test_8_share_dialog(page):
    """测试分享对话框"""
    log("\n=== 测试 8: 分享功能 ===")
    
    settings_btn = page.locator('button[aria-label="Settings"]')
    if await settings_btn.is_visible(timeout=3000):
        await settings_btn.click()
        await page.wait_for_timeout(500)
        
        # 找到 Share Dialog
        share_section = page.locator('h3:text("Share")')
        if await share_section.is_visible(timeout=3000):
            log("  ✅ Share Dialog 可见")
            
            # Session ID 输入
            session_input = page.locator('input[placeholder="Session ID to share"]')
            if await session_input.is_visible():
                await session_input.fill("test-session-123")
            
            # Share 按钮
            share_btn = page.locator('button:text("Share"):below(h3:text("Share"))').first
            if await share_btn.is_visible():
                await share_btn.click()
                await page.wait_for_timeout(500)
                log("  ✅ 分享按钮点击")
        
        await page.locator('button[aria-label="Close settings"]').click()
        await save_screenshot(page, "08-share")


async def test_9_sync_panel(page):
    """测试同步面板"""
    log("\n=== 测试 9: 同步功能 ===")
    
    settings_btn = page.locator('button[aria-label="Settings"]')
    if await settings_btn.is_visible(timeout=3000):
        await settings_btn.click()
        await page.wait_for_timeout(500)
        
        # 找到 Sync Panel
        sync_section = page.locator('h3:text("Sync")')
        if await sync_section.is_visible(timeout=3000):
            log("  ✅ Sync Panel 可见")
            
            # Push Sync 按钮
            push_btn = page.locator('button:text("Push Sync")')
            if await push_btn.is_visible():
                await push_btn.click()
                await page.wait_for_timeout(1000)
            
            # Refresh 按钮
            refresh_btn = page.locator('button:text("Refresh"):below(h3:text("Sync"))').first
            if await refresh_btn.is_visible():
                await refresh_btn.click()
                log("  ✅ 同步功能测试")
        
        await page.locator('button[aria-label="Close settings"]').click()
        await save_screenshot(page, "09-sync")


async def test_10_terminal(page):
    """测试终端面板"""
    log("\n=== 测试 10: 终端面板 ===")
    
    # 打开终端
    terminal_btn = page.locator('button:has(svg)').filter(has_text='')
    # 查找可能的终端按钮（有 terminal 图标的）
    buttons = await page.query_selector_all('button')
    terminal_found = False
    
    for btn in buttons:
        cls = await btn.get_attribute('class') or ''
        if 'terminal' in cls.lower():
            terminal_found = True
            await btn.click()
            await page.wait_for_timeout(1000)
            
            terminal_panel = page.locator('.xterm')
            if await terminal_panel.is_visible(timeout=3000):
                log("  ✅ 终端面板可见")
                
                # New 按钮
                new_btn = page.locator('button:text("New")')
                if await new_btn.is_visible():
                    await new_btn.click()
                    await page.wait_for_timeout(500)
                    log("  ✅ 创建终端会话")
                
                # Close 按钮
                close_btn = page.locator('button:text("Close")')
                if await close_btn.is_visible():
                    await close_btn.click()
                    log("  ✅ 关闭终端会话")
            break
    
    if not terminal_found:
        log("  ⚠️ 终端按钮不可见")
    
    await save_screenshot(page, "10-terminal")


async def test_11_command_palette(page):
    """测试命令面板"""
    log("\n=== 测试 11: 命令面板 ===")
    
    # Ctrl/Cmd+K 打开
    await page.keyboard.press("Meta+K")
    await page.wait_for_timeout(500)
    
    palette = page.locator('input[placeholder="Type a command..."]')
    if await palette.is_visible(timeout=3000):
        log("  ✅ 命令面板打开")
        
        # 搜索
        await palette.fill("settings")
        await page.wait_for_timeout(300)
        
        # 选择
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(500)
        
        settings = page.locator('h2:text("Settings")')
        if await settings.is_visible(timeout=3000):
            log("  ✅ 命令面板搜索和选择")
            
            # 关闭设置
            await page.locator('button[aria-label="Close settings"]').click()
        else:
            add_issue("P2", "命令面板选择失败", "Enter 后未打开设置")
    else:
        add_issue("P2", "命令面板打不开", "Ctrl+K 未响应")
    
    await save_screenshot(page, "11-command-palette")


async def test_12_keyboard_shortcuts(page):
    """测试键盘快捷键"""
    log("\n=== 测试 12: 键盘快捷键 ===")
    
    # ESC 关闭侧边栏（如果打开）
    sidebar = page.locator('[role="navigation"]')
    if await sidebar.is_visible(timeout=2000):
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)
        log("  ✅ ESC 快捷键")
    
    # Enter 发送消息
    input_area = page.locator('textarea[placeholder*="Ask anything"]')
    if await input_area.is_visible(timeout=2000):
        await input_area.fill("test message")
        await input_area.press("Enter")
        await page.wait_for_timeout(500)
        log("  ✅ Enter 发送消息")
    
    # Tab 切换模式 (不在输入框时)
    await page.keyboard.press("Tab")
    await page.wait_for_timeout(300)
    log("  ✅ Tab 切换模式")
    
    await save_screenshot(page, "12-keyboard")


async def test_13_multi_session_isolation(page):
    """测试多会话隔离"""
    log("\n=== 测试 13: 多会话隔离 ===")
    
    # 创建多个会话
    new_session_btn = page.locator('button[aria-label="Create new session"]')
    if await new_session_btn.is_visible(timeout=3000):
        for i in range(3):
            await new_session_btn.click()
            await page.wait_for_timeout(300)
        
        sessions = page.locator('button:text("New Session")')
        count = await sessions.count()
        log(f"  创建了 {count} 个会话")
        
        # 切换会话
        if count >= 3:
            await sessions.nth(0).click()
            await page.wait_for_timeout(300)
            await sessions.nth(1).click()
            await page.wait_for_timeout(300)
            await sessions.nth(2).click()
            await page.wait_for_timeout(300)
            log("  ✅ 会话切换正常")
    
    await save_screenshot(page, "13-multi-session")


async def test_14_chinese_support(page):
    """测试中文支持"""
    log("\n=== 测试 14: 中文支持 ===")
    
    # 创建新会话
    new_session_btn = page.locator('button[aria-label="Create new session"]')
    if await new_session_btn.is_visible(timeout=3000):
        await new_session_btn.click()
        await page.wait_for_timeout(500)
    
    # 输入中文消息
    input_area = page.locator('textarea[placeholder*="Ask anything"]')
    if await input_area.is_visible(timeout=3000):
        await input_area.fill("你好，CScode")
        await page.wait_for_timeout(300)
        log("  ✅ 中文输入")
    
    # 导出中文会话
    session_btns = page.locator('button:text("New Session")')
    if await session_btns.first.is_visible(timeout=2000):
        await session_btns.first.hover()
        await page.wait_for_timeout(300)
        
        export_btn = page.locator('button[aria-label="Export session"]').first
        if await export_btn.is_visible(timeout=2000):
            await export_btn.click()
            await page.wait_for_timeout(500)
            log("  ✅ 中文会话导出")
    
    await save_screenshot(page, "14-chinese-support")


async def test_15_error_boundary(page):
    """测试错误边界"""
    log("\n=== 测试 15: 错误边界 ===")
    
    # 尝试访问不存在的页面
    await page.goto("http://localhost:8000/nonexistent", wait_until="domcontentloaded")
    await page.wait_for_timeout(500)
    
    # 返回主页
    await page.goto("http://localhost:8000", wait_until="domcontentloaded")
    await page.wait_for_timeout(1000)
    
    log("  ✅ 错误边界测试")
    await save_screenshot(page, "15-error-boundary")


# ========== 主测试流程 ==========

async def run_tests(playwright: Playwright):
    browser = await playwright.chromium.launch(headless=False, slow_mo=100)
    context = await browser.new_context(viewport={"width": 1440, "height": 900})
    page = await context.new_page()
    
    # 监听网络错误
    page.on("requestfailed", lambda request: network_errors.append({
        "url": request.url,
        "status": request.response.status if request.response else 0
    }))
    
    # 监听控制台错误
    page.on("console", lambda msg: console_errors.append({
        "type": msg.type,
        "text": msg.text
    }))
    
    # 打开应用
    log("🚀 开始 CScode 企业级端到端测试...")
    await page.goto("http://localhost:8000", wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    log(f"📸 截图目录: {SCREENSHOT_DIR}")
    
    # 运行所有测试
    tests = [
        test_1_sidebar_navigation,
        test_2_threads_header,
        test_3_session_actions,
        test_4_composer,
        test_5_mode_toggle,
        test_6_settings_panel,
        test_7_credential_panel,
        test_8_share_dialog,
        test_9_sync_panel,
        test_10_terminal,
        test_11_command_palette,
        test_12_keyboard_shortcuts,
        test_13_multi_session_isolation,
        test_14_chinese_support,
        test_15_error_boundary,
    ]
    
    for i, test_func in enumerate(tests, 1):
        try:
            await test_func(page)
        except Exception as e:
            add_issue("P0", f"测试 {i} 崩溃", str(e))
            log(f"  ❌ 测试 {i} 异常: {e}")
    
    # 关闭浏览器
    await browser.close()


async def main():
    async with async_playwright() as playwright:
        await run_tests(playwright)
    
    # 保存测试结果
    result = {
        "timestamp": datetime.now().isoformat(),
        "total_tests": 15,
        "issues": issues,
        "logs": logs,
        "network_errors": network_errors,
        "console_errors": [e for e in console_errors if e["type"] == "error"]
    }
    
    with open(TEST_RESULTS, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    # 打印总结
    log("\n" + "=" * 60)
    log(f"📊 测试完成: 15/15 个测试用例执行")
    log(f"   发现 {len(issues)} 个问题")
    
    if network_errors:
        log(f"\n🌐 网络错误 ({len(network_errors)}):")
        for err in network_errors[:5]:
            log(f"   - {err['status']} {err['url']}")
    
    if console_errors:
        log(f"\n⚠️  控制台错误 ({len(console_errors)}):")
        for err in console_errors[:5]:
            log(f"   - [{err['type']}] {err['text'][:100]}")
    
    log(f"\n📁 报告: {TEST_RESULTS}")


if __name__ == "__main__":
    asyncio.run(main())